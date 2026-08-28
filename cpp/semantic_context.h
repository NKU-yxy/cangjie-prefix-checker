#pragma once

#include "native_semantic.h"
#include "semantic_declarations.h"
#include "semantic_model.h"

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace cangjie {

// 保存当前函数的源码范围、局部变量和所属类型。
struct FunctionContext {
    bool in_function = false;
    bool is_main = false;
    std::string result = "Unit";
    std::string body;
    std::size_t body_start = 0;
    std::size_t body_end = std::string::npos;
    std::unordered_map<std::string, std::string> variables;
    std::unordered_set<std::string> immutable;
    std::unordered_map<std::string, std::string> entry_variables; // 函数入口可见变量。
    std::unordered_set<std::string> entry_immutable;              // 函数入口不可变变量。
    std::string class_name;
};

// 保存从类型出发可用的字段、方法调用和方法值边。
struct PostfixGraph {
    // 保存一个名义类型的泛型参数及所有后缀边。
    struct NominalNode {
        std::vector<std::string> type_params;
        std::unordered_map<std::string, std::string> fields;
        std::unordered_map<std::string,
            std::vector<std::pair<std::vector<std::string>, std::string>>> calls;
        std::unordered_map<std::string, std::string> method_values;
    };

    std::unordered_map<std::string, NominalNode> nodes;

    // 把函数签名转换为统一的函数类型文本。
    static std::string FunctionTypeOf(const FunctionSig& sig);
    // 从完整模型预计算所有可用后缀边。
    static PostfixGraph Build(const Model& model);
};

// 分类最近失败点的符号、尾部结构和语句边界。
FrontierInfo ClassifyFrontier(
    std::string_view source,
    const Model& model,
    const FunctionContext& context
);
// 从声明快照定位当前函数上下文。
FunctionContext CurrentFunctionContext(
    std::string_view source,
    const DeclarationSnapshot& snapshot
);
// 收集函数体中的局部变量。
void CollectLocalVariables(FunctionContext* context);
// 收集当前未闭合 Lambda 的参数。
void CollectActiveLambdaVariables(FunctionContext* context);
// 判断实际类型能否赋给期望类型。
bool Compatible(std::string_view got, std::string_view want, const Model& model);
// 判断类型是否存在于当前模型。
bool KnownType(std::string_view type, const Model& model);
// 判断声明中的嵌套类型是否全部已知。
bool KnownDeclaredType(
    std::string_view type,
    const Model& model,
    const std::unordered_set<std::string>& type_params
);
// 为失败前沿搜索可恢复的后缀见证。
RecoveryWitness ComputeShadowWitness(
    const FrontierInfo& frontier,
    const Model& model,
    const FunctionContext& context,
    const PostfixGraph& graph,
    std::unordered_map<std::string, RecoveryWitness>* cache,
    WitnessStats* stats
);
// 计算调用位置各重载候选的存活状态。
CallFrontierResult ComputeCallFrontier(
    const FrontierInfo& frontier,
    const Model& model,
    const FunctionContext& context
);

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 使用正则旧实现构建函数上下文以供差分校验。
FunctionContext CurrentFunctionContextRegex(std::string_view source);
// 使用正则查找包含指定位置的名义类型参数。
std::unordered_set<std::string> EnclosingNominalTypeParametersRegex(
    std::string_view source,
    std::size_t position
);
#endif

}
