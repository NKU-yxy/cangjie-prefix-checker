#pragma once

#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace cangjie {

// 规范化类型文本并删除无意义空白。
std::string CompactType(std::string_view input);
// 提取泛型类型的主类型名称。
std::string TypeHead(std::string_view type);
// 提取泛型类型实参列表。
std::vector<std::string> TypeArgs(std::string_view type);
// 递归应用泛型类型参数替换。
std::string ApplySubstitution(
    std::string type,
    const std::unordered_map<std::string, std::string>& substitutions
);
extern std::unordered_set<std::string> g_valid_lambda_bodies; // 已验证的 Lambda 函数体集合。
// 生成忽略空白的 Lambda 函数体文本。
std::string CanonicalLambdaBody(const std::string& text);
// 判断 Lambda 前缀是否匹配已验证函数体。
bool HasSeenValidLambdaTwin(const std::string& body_so_far);
// 拆分函数类型的参数列表和返回类型。
std::pair<std::vector<std::string>, std::string> FunctionTypeParts(std::string_view type);

}
