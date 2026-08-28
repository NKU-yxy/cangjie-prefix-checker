#pragma once

#include "semantic_model.h"

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace cangjie {

// 保存正则捕获组在源码中的位置和文本。
struct SnapshotCapture {
    bool matched = false;
    std::size_t offset = std::string::npos;
    std::size_t length = 0;
    std::string text;
};

// 保存一条声明及其花括号范围和捕获组。
struct DeclarationRecord {
    std::size_t offset = 0;
    std::size_t length = 0;
    std::size_t open = 0;
    std::optional<std::size_t> close;
    std::vector<SnapshotCapture> captures;
};

// 缓存一次源码扫描得到的各类声明，避免后续重复运行正则。
struct DeclarationSnapshot {
    std::vector<DeclarationRecord> strict_nominals;
    std::vector<DeclarationRecord> broad_classes;
    std::vector<DeclarationRecord> explicit_functions_single_line;
    std::vector<DeclarationRecord> explicit_functions_multiline_only;
    std::vector<DeclarationRecord> optional_functions_single_line;
    std::vector<DeclarationRecord> optional_functions_multiline_only;
    std::vector<DeclarationRecord> current_functions_single_line;
    std::vector<DeclarationRecord> current_functions_multiline_only;

    // 返回快照中所有声明记录的总数。
    std::size_t RecordCount() const;
};

// 保存源码字段的类型、可变性及静态属性。
struct SourceFieldInfo {
    bool mutable_field = false;
    bool is_static = false;
    bool has_initializer = false;
    std::string type;
};

// 解析泛型类型参数列表。
std::vector<std::string> ParseTypeParameters(std::string_view text);
// 解析函数名称、泛型、参数和返回类型。
FunctionSig ParseFunctionSignature(
    std::string name,
    std::string_view generic_text,
    std::string_view param_text,
    std::string_view result_text
);
// 解析名义类型声明中的父类型列表。
std::vector<std::string> ParseSupers(std::string_view header);
// 判断源码中是否存在跨行的函数、构造器或主函数头。
bool HasMultilineFunctionHeader(std::string_view source);
// 扫描源码并构建可复用的声明快照。
DeclarationSnapshot BuildDeclarationSnapshot(std::string_view source);
// 安全读取声明记录中的捕获组。
const SnapshotCapture& SnapshotCaptureAt(
    const DeclarationRecord& record,
    std::size_t index
);
// 把函数声明快照加入模型。
void CollectFunctions(const DeclarationSnapshot& snapshot, Model* model);
// 把导入名称加入当前模型。
void CollectImports(std::string_view source, Model* model);
// 扫描已遮蔽源码中的顶层字段和方法名称。
std::unordered_map<std::string, SourceFieldInfo> ScanTopLevelSourceFieldsMasked(
    std::string_view body,
    std::vector<std::string>* ordered_field_names = nullptr,
    std::vector<std::string>* ordered_method_names = nullptr
);
// 遮蔽非代码文本后扫描顶层字段。
std::unordered_map<std::string, SourceFieldInfo> ScanTopLevelSourceFields(
    std::string_view body
);
// 把类和接口声明加入模型。
void CollectNominals(
    std::string_view source,
    const DeclarationSnapshot& snapshot,
    Model* model
);

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 对比声明快照与旧正则扫描结果。
void VerifyDeclarationSnapshot(
    std::string_view source,
    const DeclarationSnapshot& snapshot
);
// 使用旧正则实现收集函数以供差分校验。
void CollectFunctionsRegex(std::string_view source, Model* model);
// 使用旧正则实现收集类型以供差分校验。
void CollectNominalsRegex(std::string_view source, Model* model);
// 判断两个符号模型是否完全一致。
bool SameModel(const Model& left, const Model& right);
#endif

}
