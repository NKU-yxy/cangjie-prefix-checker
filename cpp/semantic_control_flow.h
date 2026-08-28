#pragma once

#include "native_semantic.h"
#include "semantic_context.h"
#include "semantic_declarations.h"
#include "semantic_model.h"

#include <optional>
#include <string>
#include <string_view>
#include <unordered_set>
#include <utility>

namespace cangjie {

// 保存变量声明的名称、可选标注类型和初始化表达式。
struct AnyVariableDeclaration {
    std::string name;
    std::string annotated_type;
    std::string expression;
};

// 判断换行前的运算符是否要求继续当前语句。
bool ContinuesAfterNewline(std::string_view statement);
// 判断文本是否可能是一条语句的前缀。
bool IsStatementPrefix(std::string_view line);
// 判断文本是否是尚未写完的关键字。
bool IsUnfinishedKeywordPrefix(std::string_view line);
// 判断语句是否以显式代码块开头。
bool IsExplicitBlockStatement(std::string_view statement);
// 解析带可选类型标注的变量声明。
std::optional<AnyVariableDeclaration> ParseAnyVariableDeclaration(std::string_view line);
// 解析带显式类型标注的变量声明。
std::optional<std::pair<std::string, std::string>> ParseVariableDeclaration(
    std::string_view line
);
// 解析简单变量或字段赋值。
std::optional<std::pair<std::string, std::string>> ParseReassignment(std::string_view line);
// 判断赋值目标是否带显式 this 接收者。
bool HasExplicitThisReceiver(std::string_view line);
// 判断类型是否存在指定前缀的成员。
bool HasMemberPrefix(const Model& model, const std::string& type, const std::string& prefix);
// 判断赋值左侧是否为非法目标。
bool HasInvalidAssignmentTarget(std::string_view line);
// 提取最近一个 if 或 while 条件。
std::optional<std::string> LastCondition(std::string_view source, std::string_view keyword);
// 判断当前位置是否位于循环体内。
bool InsideLoop(std::string_view body);
// 判断类型是否可用于 for-in 遍历。
bool IsIterable(std::string_view type);
// 返回可迭代类型的元素类型。
std::string IterableElement(std::string_view type);
// 跳过循环源码中的空白和行注释。
std::size_t SkipLoopLineTrivia(std::string_view source, std::size_t cursor);
// 删除循环文本中的注释并保留代码。
std::string RemoveLoopComments(std::string_view text);
// 检查已经闭合的循环体语句。
CheckStatus CheckCompletedLoopBodies(
    std::string_view body,
    const Model& model,
    const FunctionContext& context,
    std::string_view full_source
);
// 检查函数和 Lambda 的重复参数。
CheckStatus CheckDuplicateParameter(std::string_view source);
// 判断前缀能否扩展为已知类型名称。
bool HasKnownTypePrefix(
    std::string_view prefix,
    const Model& model,
    const std::unordered_set<std::string>& type_parameters
);
// 检查类字段、方法和构造器名称冲突。
CheckStatus CheckClassMemberNameCollisions(std::string_view source);
// 查找源码类中指定字段的显式类型。
std::string TopLevelSourceFieldType(
    std::string_view source,
    const DeclarationSnapshot& snapshot,
    std::string_view class_name,
    std::string_view field_name
);
// 检查连续简单赋值的目标和右值类型。
CheckStatus CheckCompletedSimpleAssignmentSequence(
    std::string_view statement,
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot,
    const FunctionContext& context
);

}
