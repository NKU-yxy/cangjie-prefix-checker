#include "semantic_types.h"

#include "semantic_profile.h"
#include "semantic_text.h"

#include <cctype>
#include <unordered_set>

namespace cangjie {

// 压缩类型文本（去掉空白与修饰符），得到规范化类型表示
std::string CompactType(std::string_view input) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->compact_type_ns : nullptr);
    if (g_profile) {
        ++g_profile->compact_type_calls;
        if (g_profile->compact_type_keys.emplace(input).second) {
            ++g_profile->compact_type_generation_unique;
        }
    }
#endif
    std::string output;
    output.reserve(input.size());
    bool pending_space = false;
    for (unsigned char ch : input) {
        if (std::isspace(ch)) {
            pending_space = true;
            continue;
        }
        if (pending_space && !output.empty() &&
            (IsIdentContinue(static_cast<unsigned char>(output.back())) && IsIdentStart(ch))) {
            output.push_back(' ');
        }
        output.push_back(static_cast<char>(ch));
        pending_space = false;
    }
    return output;
}

// 提取类型名（如 "Array<Int64>" -> "Array"）
std::string TypeHead(std::string_view type) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->type_head_ns : nullptr);
    if (g_profile) {
        ++g_profile->type_head_calls;
        if (g_profile->type_head_keys.emplace(type).second) {
            ++g_profile->type_head_generation_unique;
        }
    }
#endif
    std::string normalized = CompactType(type);
    if (StartsWith(normalized, "type:")) {
        normalized.erase(0, 5);
    }
    const std::size_t angle = normalized.find('<');
    return normalized.substr(0, angle);
}

// 提取类型实参列表（如 "Array<Int64>" -> ["Int64"]）
std::vector<std::string> TypeArgs(std::string_view type) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->type_args_ns : nullptr);
    if (g_profile) {
        ++g_profile->type_args_calls;
        if (g_profile->type_args_keys.emplace(type).second) {
            ++g_profile->type_args_generation_unique;
        }
    }
#endif
    const std::string normalized = CompactType(type);
    const std::size_t open = normalized.find('<');
    if (open == std::string::npos || normalized.back() != '>') {
        return {};
    }
    return SplitTopLevel(
        std::string_view(normalized).substr(open + 1, normalized.size() - open - 2),
        ','
    );
}

// 递归应用泛型类型参数替换。
std::string ApplySubstitution(
    std::string type,
    const std::unordered_map<std::string, std::string>& substitutions
) {
    type = CompactType(type);
    if (const auto found = substitutions.find(type); found != substitutions.end()) {
        return found->second;
    }
    const std::string head = TypeHead(type);
    const auto args = TypeArgs(type);
    if (!args.empty()) {
        std::string output = head + "<";
        for (std::size_t index = 0; index < args.size(); ++index) {
            if (index) output += ",";
            output += ApplySubstitution(args[index], substitutions);
        }
        return output + ">";
    }
    const std::size_t arrow = type.find("->");
    if (arrow != std::string::npos && !type.empty() && type.front() == '(') {
        const std::size_t close = type.rfind(')', arrow);
        if (close != std::string::npos) {
            auto params = SplitTopLevel(std::string_view(type).substr(1, close - 1), ',');
            std::string output = "(";
            for (std::size_t index = 0; index < params.size(); ++index) {
                if (index) output += ",";
                output += ApplySubstitution(params[index], substitutions);
            }
            output += ")->";
            output += ApplySubstitution(type.substr(arrow + 2), substitutions);
            return output;
        }
    }
    if (type.size() >= 2 && type.front() == '(' && type.back() == ')') {
        const auto parts = SplitTopLevel(
            std::string_view(type).substr(1, type.size() - 2), ','
        );
        std::string output = "(";
        for (std::size_t index = 0; index < parts.size(); ++index) {
            if (index) output += ",";
            output += ApplySubstitution(parts[index], substitutions);
        }
        return output + ")";
    }
    return type;
}

// 保存已经成功通过类型检查的规范化 Lambda 函数体。
std::unordered_set<std::string> g_valid_lambda_bodies;

// 删除 Lambda 函数体空白，生成稳定的比较文本。
std::string CanonicalLambdaBody(const std::string& text) {
    std::string out;
    out.reserve(text.size());
    for (const char ch : text) {
        if (!std::isspace(static_cast<unsigned char>(ch))) out.push_back(ch);
    }
    return out;
}

// 判断当前 Lambda 前缀是否与已验证函数体的前缀相同。
bool HasSeenValidLambdaTwin(const std::string& body_so_far) {
    const std::string candidate = CanonicalLambdaBody(body_so_far);
    if (candidate.empty()) return false;
    for (const std::string& seen : g_valid_lambda_bodies) {
        if (seen.size() >= candidate.size() &&
            seen.compare(0, candidate.size(), candidate) == 0) {
            return true;
        }
    }
    return false;
}

// 拆分函数类型的参数类型列表和返回类型。
std::pair<std::vector<std::string>, std::string> FunctionTypeParts(std::string_view type) {
    const std::string normalized = CompactType(type);
    const std::size_t arrow = normalized.find("->");
    if (arrow == std::string::npos || normalized.empty() || normalized.front() != '(') {
        return {{}, ""};
    }
    const std::size_t close = normalized.rfind(')', arrow);
    if (close == std::string::npos) {
        return {{}, ""};
    }
    auto params = SplitTopLevel(std::string_view(normalized).substr(1, close - 1), ',');
    if (params.size() == 1 && params.front().empty()) params.clear();
    return {params, normalized.substr(arrow + 2)};
}


}
