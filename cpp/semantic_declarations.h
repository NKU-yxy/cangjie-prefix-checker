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

std::vector<std::string> ParseTypeParameters(std::string_view text);
FunctionSig ParseFunctionSignature(
    std::string name,
    std::string_view generic_text,
    std::string_view param_text,
    std::string_view result_text
);
std::vector<std::string> ParseSupers(std::string_view header);
DeclarationSnapshot BuildDeclarationSnapshot(std::string_view source);
const SnapshotCapture& SnapshotCaptureAt(
    const DeclarationRecord& record,
    std::size_t index
);
void CollectFunctions(const DeclarationSnapshot& snapshot, Model* model);
void CollectImports(std::string_view source, Model* model);
std::unordered_map<std::string, SourceFieldInfo> ScanTopLevelSourceFieldsMasked(
    std::string_view body,
    std::vector<std::string>* ordered_field_names = nullptr,
    std::vector<std::string>* ordered_method_names = nullptr
);
std::unordered_map<std::string, SourceFieldInfo> ScanTopLevelSourceFields(
    std::string_view body
);
void CollectNominals(
    std::string_view source,
    const DeclarationSnapshot& snapshot,
    Model* model
);

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
void VerifyDeclarationSnapshot(
    std::string_view source,
    const DeclarationSnapshot& snapshot
);
void CollectFunctionsRegex(std::string_view source, Model* model);
void CollectNominalsRegex(std::string_view source, Model* model);
bool SameModel(const Model& left, const Model& right);
#endif

}  // namespace cangjie
