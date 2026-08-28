#pragma once

#include "native_semantic.h"
#include "semantic_context.h"
#include "semantic_declarations.h"
#include "semantic_model.h"

#include <string_view>

namespace cangjie {

// 检查类字段声明前缀和初始化约束。
CheckStatus CheckClassFieldPrefixRules(std::string_view source);
// 检查声明名称和类型前缀是否合法。
CheckStatus CheckDeclarationPrefixes(std::string_view source, const Model& model);
// 检查当前函数内的重复局部声明。
CheckStatus CheckDuplicateLocalDeclarations(const FunctionContext& context);
// 检查泛型实参前缀和数量是否合法。
CheckStatus CheckGenericPrefix(std::string_view source, const Model& model);
// 检查类是否完整实现所声明的接口。
CheckStatus CheckInterfaces(
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot
);
// 检查区间端点和步长类型。
CheckStatus CheckRangeSteps(std::string_view source, const Model& model);
// 检查条件分支结果类型能否合并。
CheckStatus CheckIfBranchJoins(std::string_view source, const Model& model);
// 检查构造器调用的参数和重载。
CheckStatus CheckConstructors(
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot
);
// 检查畸形泛型构造和变量绑定。
CheckStatus CheckMalformedGenericConstruct(std::string_view source);

}
