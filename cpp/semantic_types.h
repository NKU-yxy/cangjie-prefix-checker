#pragma once

#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace cangjie {

std::string CompactType(std::string_view input);
std::string TypeHead(std::string_view type);
std::vector<std::string> TypeArgs(std::string_view type);
std::string ApplySubstitution(
    std::string type,
    const std::unordered_map<std::string, std::string>& substitutions
);
extern std::unordered_set<std::string> g_valid_lambda_bodies;
std::string CanonicalLambdaBody(const std::string& text);
bool HasSeenValidLambdaTwin(const std::string& body_so_far);
std::pair<std::vector<std::string>, std::string> FunctionTypeParts(std::string_view type);

}  // namespace cangjie

