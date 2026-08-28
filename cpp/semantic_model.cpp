#include "semantic_model.h"

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <unordered_set>
#include <utility>

namespace cangjie {
namespace {

// 按固定二进制格式读取预生成的上下文表。
class ContextTableReader {
 public:
    // 校验文件头并把游标移动到数据区。
    explicit ContextTableReader(std::string data) : data_(std::move(data)) {
        static constexpr char magic[8] = {'C', 'J', 'C', 'T', 1, 0, 0, 0};
        if (data_.size() < sizeof(magic) ||
            !std::equal(std::begin(magic), std::end(magic), data_.begin())) {
            throw std::runtime_error("invalid native context table");
        }
        cursor_ = sizeof(magic);
    }

    // 读取一个小端序无符号 32 位整数。
    std::uint32_t U32() {
        if (cursor_ > data_.size() || data_.size() - cursor_ < 4) {
            throw std::runtime_error("truncated native context table");
        }
        const auto* bytes = reinterpret_cast<const unsigned char*>(data_.data() + cursor_);
        cursor_ += 4;
        return static_cast<std::uint32_t>(bytes[0]) |
            (static_cast<std::uint32_t>(bytes[1]) << 8u) |
            (static_cast<std::uint32_t>(bytes[2]) << 16u) |
            (static_cast<std::uint32_t>(bytes[3]) << 24u);
    }

    // 读取一个带长度前缀的 UTF-8 字符串。
    std::string Text() {
        const std::uint32_t size = U32();
        if (size > data_.size() - cursor_) {
            throw std::runtime_error("truncated native context string");
        }
        std::string result = data_.substr(cursor_, size);
        cursor_ += size;
        return result;
    }

    // 读取字符串数组。
    std::vector<std::string> Texts() {
        std::vector<std::string> result;
        const std::uint32_t count = U32();
        result.reserve(count);
        for (std::uint32_t index = 0; index < count; ++index) result.push_back(Text());
        return result;
    }

    // 读取名称到类型的字段映射。
    std::unordered_map<std::string, std::string> Fields() {
        std::unordered_map<std::string, std::string> result;
        const std::uint32_t count = U32();
        for (std::uint32_t index = 0; index < count; ++index) {
            std::string name = Text();
            result.emplace(std::move(name), Text());
        }
        return result;
    }

    // 读取一个函数签名。
    FunctionSig Signature() {
        FunctionSig sig;
        sig.name = Text();
        sig.result = Text();
        sig.type_params = Texts();
        sig.param_names = Texts();
        sig.param_types = Texts();
        sig.required = U32();
        return sig;
    }

    // 读取函数签名数组。
    std::vector<FunctionSig> Signatures() {
        std::vector<FunctionSig> result;
        const std::uint32_t count = U32();
        result.reserve(count);
        for (std::uint32_t index = 0; index < count; ++index) result.push_back(Signature());
        return result;
    }

 private:
    std::string data_;       // 完整的二进制上下文数据。
    std::size_t cursor_ = 0; // 下一个待读取字节的位置。
};

}  // namespace

// 判断类型是否为有符号整数类型。
bool IsInteger(std::string_view type) {
    static const std::unordered_set<std::string> values = {
        "Int8", "Int16", "Int32", "Int64"
    };
    return values.count(std::string(type)) != 0;
}

// 判断类型是否为浮点类型。
bool IsFloat(std::string_view type) {
    return type == "Float32" || type == "Float64";
}

// 判断类型是否可参与数值运算。
bool IsNumeric(std::string_view type) {
    return IsInteger(type) || IsFloat(type) || type == "Rune";
}

// 判断两个数值类型是否属于可直接兼容的同一族。
bool SameNumericFamily(std::string_view left, std::string_view right) {
    return left == right;
}

// 判断规范化类型文本是否表示函数类型。
bool IsFunctionType(std::string_view type) {
    return !type.empty() && type.front() == '(' && type.find("->") != std::string_view::npos;
}

// 从生成的二进制表加载全局变量、函数和名义类型。
void LoadContextTable(const std::string& path, Model* model) {
    if (path.empty()) return;
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("cannot open native context table: " + path);
    ContextTableReader reader(std::string{
        std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()
    });
    const std::uint32_t variable_count = reader.U32();
    for (std::uint32_t index = 0; index < variable_count; ++index) {
        const std::string name = reader.Text();
        model->globals[name] = reader.Text();
        (void)reader.U32();  // 可变性会在变量被赋值时单独记录。
    }
    for (FunctionSig& sig : reader.Signatures()) {
        model->functions[sig.name].push_back(std::move(sig));
    }
    const std::uint32_t nominal_count = reader.U32();
    for (std::uint32_t index = 0; index < nominal_count; ++index) {
        NominalInfo info;
        info.name = reader.Text();
        info.is_interface = reader.U32() != 0;
        info.type_params = reader.Texts();
        info.supers = reader.Texts();
        info.fields = reader.Fields();
        info.static_fields = reader.Fields();
        for (FunctionSig& sig : reader.Signatures()) {
            info.methods[sig.name].push_back(std::move(sig));
        }
        for (FunctionSig& sig : reader.Signatures()) {
            sig.is_static = true;
            info.static_methods[sig.name].push_back(std::move(sig));
        }
        info.constructors = reader.Signatures();
        model->nominals[info.name] = std::move(info);
    }
}

}  // namespace cangjie
