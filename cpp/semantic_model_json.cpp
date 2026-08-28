#include "semantic_model.h"

#include <algorithm>
#include <ostream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace cangjie {


// 把字符串写为 JSON 字符串（含转义）
void JsonWriteString(std::ostream& os, std::string_view value) {
    static const char kHex[] = "0123456789abcdef";
    os << '"';
    for (unsigned char c : value) {
        switch (c) {
            case '"': os << "\\\""; break;
            case '\\': os << "\\\\"; break;
            case '\n': os << "\\n"; break;
            case '\r': os << "\\r"; break;
            case '\t': os << "\\t"; break;
            default:
                if (c < 0x20) {
                    os << "\\u00" << kHex[(c >> 4) & 0xF] << kHex[c & 0xF];
                } else {
                    os << c;
                }
        }
    }
    os << '"';
}

// 把字符串数组写为 JSON 数组
void JsonWriteTexts(std::ostream& os, const std::vector<std::string>& texts) {
    os << '[';
    for (std::size_t index = 0; index < texts.size(); ++index) {
        if (index) os << ", ";
        JsonWriteString(os, texts[index]);
    }
    os << ']';
}

// 把单个函数签名写为 JSON 对象（Context IR schema）
void DumpSignatureJson(std::ostream& os, const FunctionSig& sig) {
    os << "{\"name\": ";
    JsonWriteString(os, sig.name);
    os << ", \"return_type\": ";
    JsonWriteString(os, sig.result);
    os << ", \"type_params\": ";
    JsonWriteTexts(os, sig.type_params);
    os << ", \"param_names\": ";
    JsonWriteTexts(os, sig.param_names);
    os << ", \"param_types\": ";
    JsonWriteTexts(os, sig.param_types);
    os << ", \"required_params\": " << sig.required << '}';
}

// 把函数签名列表写为 JSON 数组
void DumpSignatureListJson(std::ostream& os, const std::vector<FunctionSig>& sigs) {
    os << '[';
    for (std::size_t index = 0; index < sigs.size(); ++index) {
        if (index) os << ", ";
        DumpSignatureJson(os, sigs[index]);
    }
    os << ']';
}

// 按名称排序后输出函数重载映射。
void DumpSignatureMapJson(
    std::ostream& os,
    const std::unordered_map<std::string, std::vector<FunctionSig>>& map
) {
    os << '{';
    std::vector<std::string> names;
    names.reserve(map.size());
    for (const auto& entry : map) names.push_back(entry.first);
    std::sort(names.begin(), names.end());
    bool first = true;
    for (const std::string& name : names) {
        if (!first) os << ", ";
        first = false;
        JsonWriteString(os, name);
        os << ": ";
        DumpSignatureListJson(os, map.at(name));
    }
    os << '}';
}

// 按名称排序后输出字段类型映射。
void DumpFieldMapJson(
    std::ostream& os,
    const std::unordered_map<std::string, std::string>& map
) {
    os << '{';
    std::vector<std::string> names;
    names.reserve(map.size());
    for (const auto& entry : map) names.push_back(entry.first);
    std::sort(names.begin(), names.end());
    bool first = true;
    for (const std::string& name : names) {
        if (!first) os << ", ";
        first = false;
        JsonWriteString(os, name);
        os << ": ";
        JsonWriteString(os, map.at(name));
    }
    os << '}';
}

// 把类型（类/接口）信息写为 JSON 对象
void DumpNominalJson(std::ostream& os, const NominalInfo& info) {
    os << "{\"is_interface\": " << (info.is_interface ? "true" : "false")
       << ", \"type_params\": ";
    JsonWriteTexts(os, info.type_params);
    os << ", \"supers\": ";
    JsonWriteTexts(os, info.supers);
    os << ", \"fields\": ";
    DumpFieldMapJson(os, info.fields);
    os << ", \"static_fields\": ";
    DumpFieldMapJson(os, info.static_fields);
    os << ", \"methods\": ";
    DumpSignatureMapJson(os, info.methods);
    os << ", \"static_methods\": ";
    DumpSignatureMapJson(os, info.static_methods);
    os << ", \"constructors\": ";
    DumpSignatureListJson(os, info.constructors);
    os << '}';
}

// 把整个模型（全局变量、函数、类型）写为 Context IR JSON
void DumpModelJson(std::ostream& os, const Model& model) {
    os << "{\"schema\": \"context-ir-v1\", \"globals\": ";
    DumpFieldMapJson(os, model.globals);
    os << ", \"functions\": ";
    DumpSignatureMapJson(os, model.functions);
    os << ", \"nominals\": ";
    os << '{';
    std::vector<std::string> names;
    names.reserve(model.nominals.size());
    for (const auto& entry : model.nominals) names.push_back(entry.first);
    std::sort(names.begin(), names.end());
    bool first = true;
    for (const std::string& name : names) {
        if (!first) os << ", ";
        first = false;
        JsonWriteString(os, name);
        os << ": ";
        DumpNominalJson(os, model.nominals.at(name));
    }
    os << '}';
    os << '}';
}


}
