#include "semantic_expression.h"

#include "semantic_text.h"
#include "semantic_types.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <iostream>
#include <regex>
#include <tuple>
#include <unordered_set>
#include <utility>

namespace cangjie {

// 把可扩展后缀（如未写完的成员访问/调用）标记进表达式推断结果
ExprResult WithExtendablePostfix(ExprResult result) {
    if (result.known && !result.error) result.suffix_may_change_type = true;
    return result;
}

// 绑定本次推断使用的模型、函数作用域和完整源码。
ExpressionTyper::ExpressionTyper(
    const Model& model,
    const FunctionContext& context,
    std::string_view full_source
) : model_(model), context_(context), full_source_(full_source) {}

// 推断表达式类型，并可使用期望类型约束重载和 Lambda。
ExprResult ExpressionTyper::Infer(std::string expression, std::string expected) {
    return InferImpl(Trim(expression), CompactType(expected), 0);
}

// 去掉表达式最外层的成对括号（仅当整体被括号包裹时）
std::string StripOuterParens(std::string expression) {
    expression = Trim(expression);
    while (expression.size() >= 2 && expression.front() == '(') {
        const auto close = MatchingDelimiter(expression, 0, '(', ')');
        if (!close || *close != expression.size() - 1) break;
        expression = Trim(std::string_view(expression).substr(1, expression.size() - 2));
    }
    return expression;
}

// 按运算符优先级拆分表达式最外层的二元运算。
std::optional<std::tuple<std::string, std::string, std::string>> TailBinary(
    std::string_view expression
) {
    static const std::vector<std::vector<std::string>> precedences = {
        {"||"}, {"&&"}, {"==", "!="}, {"<=", ">=", "<", ">"},
        {"..=", ".."}, {"+", "-"}, {"*", "/", "%"}
    };
    std::vector<unsigned char> ignored(expression.size(), 0);
    bool in_string = false;
    bool triple_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    for (std::size_t index = 0; index < expression.size(); ++index) {
        const char ch = expression[index];
        const char next = index + 1 < expression.size()
            ? expression[index + 1] : '\0';
        if (line_comment) {
            ignored[index] = 1;
            if (ch == '\n' || ch == '\r') line_comment = false;
            continue;
        }
        if (block_comment_depth > 0) {
            ignored[index] = 1;
            if (ch == '/' && next == '*') {
                ignored[index + 1] = 1;
                ++block_comment_depth;
                ++index;
            } else if (ch == '*' && next == '/') {
                ignored[index + 1] = 1;
                --block_comment_depth;
                ++index;
            }
            continue;
        }
        if (in_string) {
            ignored[index] = 1;
            if (triple_string) {
                if (index + 2 < expression.size() &&
                    expression.substr(index, 3) == "\"\"\"") {
                    ignored[index + 1] = 1;
                    ignored[index + 2] = 1;
                    in_string = false;
                    triple_string = false;
                    index += 2;
                }
            } else if (escaped) {
                escaped = false;
            } else if (ch == '\\') {
                escaped = true;
            } else if (ch == '"') {
                in_string = false;
            }
            continue;
        }
        if (ch == '/' && next == '/') {
            ignored[index] = ignored[index + 1] = 1;
            line_comment = true;
            ++index;
            continue;
        }
        if (ch == '/' && next == '*') {
            ignored[index] = ignored[index + 1] = 1;
            block_comment_depth = 1;
            ++index;
            continue;
        }
        if (ch == '"') {
            ignored[index] = 1;
            triple_string = index + 2 < expression.size() &&
                expression.substr(index, 3) == "\"\"\"";
            in_string = true;
            if (triple_string) {
                ignored[index + 1] = ignored[index + 2] = 1;
                index += 2;
            }
        }
    }
    for (const auto& operators : precedences) {
        int paren = 0;
        int bracket = 0;
        int brace = 0;
        for (std::size_t index = expression.size(); index-- > 0;) {
            if (ignored[index]) continue;
            const char ch = expression[index];
            if (ch == ')') ++paren;
            else if (ch == '(') --paren;
            else if (ch == ']') ++bracket;
            else if (ch == '[') --bracket;
            else if (ch == '}') ++brace;
            else if (ch == '{') --brace;
            if (paren || bracket || brace) continue;
            for (const std::string& op : operators) {
                if (index + op.size() <= expression.size() && expression.substr(index, op.size()) == op) {
                    if ((op == "+" || op == "-") && index == 0) continue;
                    if (op == "<" && index + 1 < expression.size() && expression[index + 1] == ':') continue;
                    if (op == ">" && index > 0 && expression[index - 1] == '=') continue;
                    return std::make_tuple(
                        Trim(expression.substr(0, index)), op,
                        Trim(expression.substr(index + op.size()))
                    );
                }
            }
        }
    }
    return std::nullopt;
}

// 在表达式尾部找到最近的函数调用 '('（含泛型实参前缀），判断其是否已闭合
std::optional<std::size_t> FindCallOpen(std::string_view expression, bool* closed) {
    int total_parens = 0;
    bool scan_string = false;
    bool scan_escaped = false;
    for (const char ch : expression) {
        if (scan_string) {
            if (scan_escaped) scan_escaped = false;
            else if (ch == '\\') scan_escaped = true;
            else if (ch == '"') scan_string = false;
            continue;
        }
        if (ch == '"') scan_string = true;
        else if (ch == '(') ++total_parens;
        else if (ch == ')' && total_parens > 0) --total_parens;
    }
    *closed = total_parens == 0 && !expression.empty() && expression.back() == ')';
    if (*closed) {
        int depth = 0;
        bool in_string = false;
        bool escaped = false;
        for (std::size_t index = expression.size(); index-- > 0;) {
            const char ch = expression[index];
            if (in_string) {
                if (escaped) escaped = false;
                else if (ch == '\\') escaped = true;
                else if (ch == '"') in_string = false;
                continue;
            }
            if (ch == '"') in_string = true;
            else if (ch == ')') ++depth;
            else if (ch == '(' && --depth == 0) return index;
        }
        return std::nullopt;
    }
    int paren = 0;
    int bracket = 0;
    int brace = 0;
    bool in_string = false;
    bool escaped = false;
    std::optional<std::size_t> candidate;
    for (std::size_t index = 0; index < expression.size(); ++index) {
        const char ch = expression[index];
        if (in_string) {
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '"') in_string = true;
        else if (ch == '(') {
            if (paren == 0 && bracket == 0 && brace == 0) candidate = index;
            ++paren;
        } else if (ch == ')' && paren > 0) --paren;
        else if (ch == '[') ++bracket;
        else if (ch == ']' && bracket > 0) --bracket;
        else if (ch == '{') ++brace;
        else if (ch == '}' && brace > 0) --brace;
    }
    return paren > 0 ? candidate : std::nullopt;
}

// 解析显式调用目标：拆分 callee 名字与显式类型实参列表
std::pair<std::string, std::vector<std::string>> ParseExplicitTypes(std::string callee) {
    callee = Trim(callee);
    if (callee.empty() || callee.back() != '>') return {callee, {}};
    int depth = 0;
    for (std::size_t index = callee.size(); index-- > 0;) {
        if (callee[index] == '>') ++depth;
        else if (callee[index] == '<' && --depth == 0) {
            auto args = SplitTopLevel(
                std::string_view(callee).substr(index + 1, callee.size() - index - 2), ','
            );
            return {Trim(std::string_view(callee).substr(0, index)), args};
        }
    }
    return {callee, {}};
}

// 判断前缀是否以运算符/特殊符号开头（表达式可能仍是这些符号的一部分）
bool ExpressionTyper::HasSymbolPrefix(std::string_view prefix) const {
    for (const auto& [name, _] : context_.variables) if (StartsWith(name, prefix)) return true;
    for (const auto& [name, _] : model_.globals) if (StartsWith(name, prefix)) return true;
    for (const auto& [name, _] : model_.functions) if (StartsWith(name, prefix)) return true;
    for (const auto& [name, _] : model_.nominals) if (StartsWith(name, prefix)) return true;
    return false;
}

// 判断尾部标识符是否还能继续扩展（如未写完的成员名或关键字）
bool ExpressionTyper::MayExtendTrailingIdentifier(std::string_view identifier) const {
    if (!IsIdentifierText(identifier) || full_source_.empty()) return false;
    std::size_t end = full_source_.size();
    if (std::isspace(static_cast<unsigned char>(full_source_[end - 1]))) return false;
    std::size_t start = end;
    while (start > 0 && IsIdentContinue(
               static_cast<unsigned char>(full_source_[start - 1]))) --start;
    return full_source_.substr(start, end - start) == identifier;
}

// 解析成员访问表达式（接收者类型 + 成员名），处理泛型实例与链式访问
std::optional<std::pair<std::string, std::string>> ExpressionTyper::ParseMember(
    std::string_view expression
) const {
    int paren = 0;
    int bracket = 0;
    int brace = 0;
    bool in_string = false;
    for (std::size_t index = expression.size(); index-- > 0;) {
        const char ch = expression[index];
        if (ch == '"') in_string = !in_string;
        if (in_string) continue;
        if (ch == ')') ++paren;
        else if (ch == '(') --paren;
        else if (ch == ']') ++bracket;
        else if (ch == '[') --bracket;
        else if (ch == '}') ++brace;
        else if (ch == '{') --brace;
        else if (ch == '.' && paren == 0 && bracket == 0 && brace == 0) {
            return std::make_pair(
                Trim(expression.substr(0, index)), Trim(expression.substr(index + 1))
            );
        }
    }
    return std::nullopt;
}

// 根据实参类型递归绑定签名中的泛型类型变量。
void BindTypeVariables(
    const std::string& pattern,
    const std::string& actual,
    const std::unordered_set<std::string>& type_params,
    std::unordered_map<std::string, std::string>* substitutions
) {
    if (type_params.count(pattern)) {
        substitutions->emplace(pattern, actual);
        return;
    }
    if (IsFunctionType(pattern) && IsFunctionType(actual)) {
        const auto pattern_fn = FunctionTypeParts(pattern);
        const auto actual_fn = FunctionTypeParts(actual);
        for (std::size_t index = 0;
             index < pattern_fn.first.size() && index < actual_fn.first.size(); ++index) {
            BindTypeVariables(pattern_fn.first[index], actual_fn.first[index], type_params, substitutions);
        }
        BindTypeVariables(pattern_fn.second, actual_fn.second, type_params, substitutions);
    } else if (pattern.size() >= 2 && pattern.front() == '(' && pattern.back() == ')' &&
               actual.size() >= 2 && actual.front() == '(' && actual.back() == ')') {
        const auto pattern_parts = SplitTopLevel(
            std::string_view(pattern).substr(1, pattern.size() - 2), ','
        );
        const auto actual_parts = SplitTopLevel(
            std::string_view(actual).substr(1, actual.size() - 2), ','
        );
        for (std::size_t index = 0;
             index < pattern_parts.size() && index < actual_parts.size(); ++index) {
            BindTypeVariables(pattern_parts[index], actual_parts[index], type_params, substitutions);
        }
    } else {
        if (TypeHead(pattern) != TypeHead(actual)) return;
        const auto pattern_args = TypeArgs(pattern);
        const auto actual_args = TypeArgs(actual);
        for (std::size_t index = 0;
             index < pattern_args.size() && index < actual_args.size(); ++index) {
            BindTypeVariables(
                pattern_args[index], actual_args[index], type_params, substitutions
            );
        }
    }
}

// 按函数签名集合检查一个调用：逐一匹配重载，核对实参个数与类型
ExprResult ExpressionTyper::CheckSignatures(
    const std::vector<FunctionSig>& signatures,
    const std::vector<std::string>& explicit_types,
    const std::vector<std::string>& arguments,
    bool closed,
    const std::string& expected,
    int depth,
    const std::unordered_map<std::string, std::string>& receiver_substitutions
) {
    std::string first_error;
    bool over_arity_fallback = false;
    for (const FunctionSig& sig : signatures) {
        if (!explicit_types.empty() && explicit_types.size() != sig.type_params.size()) {
            if (first_error.empty()) first_error = "wrong generic arity";
            continue;
        }
        if (arguments.size() > sig.param_types.size() ||
            (closed && (arguments.size() < sig.required || arguments.size() > sig.param_types.size()))) {
            if (!closed && arguments.size() > sig.param_types.size()) {
                over_arity_fallback = true;
            } else if (first_error.empty()) {
                first_error = "wrong argument arity";
            }
            continue;
        }
        std::unordered_map<std::string, std::string> substitutions = receiver_substitutions;
        for (std::size_t index = 0; index < explicit_types.size() && index < sig.type_params.size(); ++index) {
            substitutions[sig.type_params[index]] = CompactType(explicit_types[index]);
        }
        std::unordered_set<std::string> type_params(sig.type_params.begin(), sig.type_params.end());
        if (!expected.empty()) BindTypeVariables(sig.result, expected, type_params, &substitutions);
        bool rejected = false;
        std::size_t positional = 0;
        std::unordered_set<std::size_t> used;
        for (std::size_t argument_number = 0; argument_number < arguments.size(); ++argument_number) {
            const std::string& raw_argument = arguments[argument_number];
            if (raw_argument.empty()) continue;
            const std::string trimmed_argument = Trim(raw_argument);
            if (!closed && HasUnclosedString(trimmed_argument)) continue;
            std::size_t parameter_index = positional;
            std::string argument = raw_argument;
            const std::size_t colon = FindTopLevel(argument, ":");
            if (colon != std::string::npos &&
                IsIdentifierText(Trim(std::string_view(argument).substr(0, colon)))) {
                const std::string named = Trim(std::string_view(argument).substr(0, colon));
                const auto found = std::find(sig.param_names.begin(), sig.param_names.end(), named);
                if (found == sig.param_names.end()) {
                    rejected = true;
                    if (first_error.empty()) first_error = "unknown named argument";
                    break;
                }
                parameter_index = static_cast<std::size_t>(found - sig.param_names.begin());
                argument = Trim(std::string_view(argument).substr(colon + 1));
            } else {
                const std::string possible_name = Trim(raw_argument);
                if (!closed && MayExtendTrailingIdentifier(possible_name) &&
                    IsIdentifierText(possible_name) &&
                    std::any_of(
                        sig.param_names.begin(), sig.param_names.end(),
                        [&](const std::string& item) { return StartsWith(item, possible_name); }
                    )) {
                    continue;
                }
                while (used.count(parameter_index)) ++parameter_index;
                positional = parameter_index + 1;
            }
            if (parameter_index >= sig.param_types.size() || !used.insert(parameter_index).second) {
                rejected = true;
                if (first_error.empty()) first_error = "invalid argument";
                break;
            }
            const std::string pattern = ApplySubstitution(sig.param_types[parameter_index], substitutions);
            ExprResult actual = InferImpl(argument, pattern, depth + 1);
            if (actual.error) {
                rejected = true;
                if (first_error.empty()) first_error = actual.message;
                break;
            }
            if (!closed && MayExtendTrailingIdentifier(trimmed_argument) &&
                IsIdentifierText(trimmed_argument) &&
                HasSymbolPrefix(trimmed_argument) &&
                argument_number + 1 == arguments.size()) {
                continue;
            }
            if (actual.known) {
                BindTypeVariables(sig.param_types[parameter_index], actual.type, type_params, &substitutions);
                const std::string want = ApplySubstitution(sig.param_types[parameter_index], substitutions);
                if (!Compatible(actual.type, want, model_)) {
                    if (!closed && actual.suffix_may_change_type &&
                        argument_number + 1 == arguments.size()) {
                        continue;
                    }
                    if (!closed && MayExtendTrailingIdentifier(trimmed_argument) &&
                        argument_number + 1 == arguments.size()) continue;
                    if (IsInteger(actual.type) && IsInteger(want) &&
                        IsDecimalIntegerText(Trim(argument))) {
                        continue;
                    }
                    rejected = true;
                    if (first_error.empty()) first_error = "argument type mismatch";
                    break;
                }
            }
        }
        if (!rejected) {
            ExprResult result;
            result.type = ApplySubstitution(sig.result, substitutions);
            result.known = result.type.find_first_of("?") == std::string::npos;
            return result;
        }
    }
    if (!first_error.empty()) return {"?", false, true, first_error};
    if (over_arity_fallback) return {"?", false, true, "wrong argument arity"};
    return {};
}

// 推断一次函数调用：解析目标与实参，按签名检查并做泛型实参替换
ExprResult ExpressionTyper::InferCall(
    std::string base,
    std::string name,
    std::vector<std::string> explicit_types,
    std::string arguments,
    bool closed,
    const std::string& expected,
    int depth
) {
    std::vector<std::string> args = SplitTopLevel(arguments, ',');
    if (args.size() == 1 && args.front().empty()) args.clear();
    if (base.empty()) {
        std::vector<FunctionSig> candidates;
        if (const auto function = model_.functions.find(name); function != model_.functions.end()) {
            candidates.insert(candidates.end(), function->second.begin(), function->second.end());
        }
        if (const auto nominal = model_.nominals.find(name); nominal != model_.nominals.end() && !nominal->second.is_interface) {
            candidates.insert(candidates.end(), nominal->second.constructors.begin(), nominal->second.constructors.end());
        }
        if (candidates.empty() && !name.empty() && name.front() == '{') {
            ExprResult callee = InferImpl(name, {}, depth + 1);
            if (callee.error) return callee;
            if (callee.known && IsFunctionType(callee.type)) {
                const auto parts = FunctionTypeParts(callee.type);
                FunctionSig sig;
                sig.name = "<lambda>";
                sig.param_types = parts.first;
                sig.param_names.resize(parts.first.size());
                sig.required = parts.first.size();
                sig.result = parts.second;
                candidates.push_back(std::move(sig));
            }
        }
        if (candidates.empty()) return {};
        return WithExtendablePostfix(
            CheckSignatures(candidates, explicit_types, args, closed, expected, depth)
        );
    }

    if (name.find_first_of("+-*/%<>=&|") != std::string::npos) return {};

    ExprResult receiver = InferImpl(base, {}, depth + 1);
    if (receiver.error || !receiver.known) return receiver;
    const bool type_receiver = StartsWith(receiver.type, "type:");
    const std::string receiver_type = type_receiver ? receiver.type.substr(5) : receiver.type;
    if (StartsWith(receiver_type, "namespace:")) {
        if (name == "println" || name == "print" || name == "eprintln" || name == "eprint") {
            return {"Unit", true, false, {}, true};
        }
        return {};
    }
    const auto nominal = model_.nominals.find(TypeHead(receiver_type));
    if (name == "toString") return {"String", true, false, {}, true};
    if (nominal == model_.nominals.end()) {
        if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
            std::cerr << "member on non-nominal type '" << receiver_type
                      << "', base '" << base << "'\n";
        }
        return {"?", false, true, "member on non-nominal"};
    }
    if (!type_receiver) {
        const auto& fields = nominal->second.fields;
        if (fields.find(name) != fields.end()) {
            return {"?", false, true, "field is not callable"};
        }
    }
    const auto& methods = type_receiver ? nominal->second.static_methods : nominal->second.methods;
    const auto method = methods.find(name);
    if (method == methods.end()) {
        const bool partial = MayExtendTrailingIdentifier(name);
        if (partial) {
            for (const auto& [candidate, _] : methods) if (StartsWith(candidate, name)) return {};
        }
        if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
            std::cerr << "unknown method '" << name << "' on " << receiver_type
                      << " in " << base << '\n';
        }
        return {"?", false, true, "unknown member"};
    }
    std::unordered_map<std::string, std::string> substitutions;
    const auto receiver_args = TypeArgs(receiver_type);
    for (std::size_t index = 0;
         index < receiver_args.size() && index < nominal->second.type_params.size(); ++index) {
        substitutions[nominal->second.type_params[index]] = receiver_args[index];
    }
    return WithExtendablePostfix(CheckSignatures(
        method->second, explicit_types, args, closed, expected, depth, substitutions
    ));
}

// 找到表达式中第一个字符串字面量的结束位置（用于掩码处理）
std::optional<std::size_t> FirstStringLiteralEnd(std::string_view expression) {
    if (expression.empty() || expression.front() != '"') return std::nullopt;
    if (StartsWith(expression, "\"\"\"")) {
        for (std::size_t index = 3; index + 2 < expression.size(); ++index) {
            if (expression.substr(index, 3) == "\"\"\"") return index + 2;
        }
        return std::nullopt;
    }
    bool escaped = false;
    for (std::size_t index = 1; index < expression.size(); ++index) {
        const char ch = expression[index];
        if (escaped) {
            escaped = false;
        } else if (ch == '\\') {
            escaped = true;
        } else if (ch == '"') {
            return index;
        }
    }
    return std::nullopt;
}

// 表达式类型推断核心：递归处理字面量/标识符/调用/成员访问/运算符/数组/lambda
ExprResult ExpressionTyper::InferImpl(std::string expression, const std::string& expected, int depth) {
    if (depth > 64) return {};
    expression = Trim(expression);
    if (expression.empty()) return {};
    if (expression.front() == '(') {
        const auto outer_close = MatchingDelimiter(expression, 0, '(', ')');
        if (outer_close && *outer_close == expression.size() - 1) {
            const std::string inner = expression.substr(1, expression.size() - 2);
            const auto tuple_parts = SplitTopLevel(inner, ',');
            if (tuple_parts.size() > 1) {
                std::vector<std::string> expected_parts;
                if (expected.size() >= 2 && expected.front() == '(' &&
                    expected.back() == ')') {
                    expected_parts = SplitTopLevel(
                        std::string_view(expected).substr(1, expected.size() - 2), ','
                    );
                }
                std::string tuple = "(";
                bool known = true;
                for (std::size_t index = 0; index < tuple_parts.size(); ++index) {
                    const std::string item_expected = index < expected_parts.size()
                        ? expected_parts[index] : std::string{};
                    ExprResult item = InferImpl(
                        tuple_parts[index], item_expected, depth + 1
                    );
                    if (item.error) return item;
                    if (!item_expected.empty() &&
                        KnownType(TypeHead(item_expected), model_) && item.known &&
                        !Compatible(item.type, item_expected, model_)) {
                        return {"?", false, true, "tuple element type mismatch"};
                    }
                    if (index) tuple += ",";
                    tuple += item.type;
                    known = known && item.known;
                }
                return {tuple + ")", known, false, {}};
            }
        }
    }
    expression = StripOuterParens(expression);
    if (expression.empty()) return {};
    if ((StartsWithKeyword(expression, "if") || StartsWithKeyword(expression, "while") ||
         StartsWithKeyword(expression, "for")) && expression.find('{') == std::string::npos) {
        return {};
    }
    const std::size_t unmatched_angle = expression.find('<');
    if (unmatched_angle != std::string::npos && expression.find('>', unmatched_angle + 1) == std::string::npos &&
        expression.find("<:", unmatched_angle) != unmatched_angle) {
        const std::string head = Trim(std::string_view(expression).substr(0, unmatched_angle));
        if (model_.nominals.count(head) || model_.functions.count(head) || head.find('.') != std::string::npos) return {};
    }

    if (expression.front() == '{') {
        const auto lambda_end = MatchingDelimiter(expression, 0, '{', '}');
        if (lambda_end && *lambda_end + 1 < expression.size()) {
            const std::string suffix = Trim(
                std::string_view(expression).substr(*lambda_end + 1)
            );
            if (!suffix.empty() && suffix.front() == '(' && suffix.back() == ')') {
                return InferCall(
                    {}, expression.substr(0, *lambda_end + 1), {},
                    suffix.substr(1, suffix.size() - 2), true, expected, depth + 1
                );
            }
        }
    }

    if (expression.front() == '{') {
        const std::size_t arrow = expression.find("=>");
        if (arrow == std::string::npos) {
            const auto close = MatchingDelimiter(expression, 0, '{', '}');
            if (close && *close == expression.size() - 1) {
                std::string body = Trim(std::string_view(expression).substr(1, expression.size() - 2));
                const std::size_t separator = body.find_last_of(";\n\r");
                if (separator != std::string::npos) body = Trim(std::string_view(body).substr(separator + 1));
                return InferImpl(body, expected, depth + 1);
            }
        }
        std::string header = Trim(std::string_view(expression).substr(
            1, arrow == std::string::npos ? expression.size() - 1 : arrow - 1
        ));
        auto expected_fn = FunctionTypeParts(expected);
        if (arrow == std::string::npos && !expected_fn.second.empty()) {
            const auto partial_params = SplitTopLevel(header, ',');
            for (std::size_t index = 0;
                 index < partial_params.size() && index < expected_fn.first.size(); ++index) {
                const std::size_t colon = FindTopLevel(partial_params[index], ":");
                if (colon == std::string::npos) continue;
                const std::string annotated = CompactType(
                    std::string_view(partial_params[index]).substr(colon + 1)
                );
                if (KnownType(annotated, model_) &&
                    !Compatible(annotated, expected_fn.first[index], model_) &&
                    !Compatible(expected_fn.first[index], annotated, model_)) {
                    if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
                        std::cerr << "lambda partial parameter mismatch: " << annotated
                                  << " vs " << expected_fn.first[index] << '\n';
                    }
                    return {"?", false, true, "lambda parameter type mismatch"};
                }
            }
            return {};
        }
        if (arrow == std::string::npos) return {};
        std::string body = Trim(std::string_view(expression).substr(arrow + 2));
        const auto lambda_close = MatchingDelimiter(expression, 0, '{', '}');
        const bool lambda_closed = lambda_close && *lambda_close == expression.size() - 1;
        if (lambda_closed && !body.empty() && body.back() == '}') body.pop_back();
        auto params = SplitTopLevel(header, ',');
        if (params.size() == 1 && params.front().empty()) params.clear();
        if (!expected_fn.second.empty() && params.size() != expected_fn.first.size()) {
            return {"?", false, true, "lambda parameter arity mismatch"};
        }
        if (expected_fn.second.empty()) {
            for (const std::string& parameter : params) {
                if (FindTopLevel(parameter, ":") == std::string::npos) {
                    return {"?", false, true,
                            "lambda synthesis requires parameter annotations"};
                }
            }
        }
        FunctionContext lambda_context = context_;
        std::vector<std::string> param_types;
        for (std::size_t index = 0; index < params.size(); ++index) {
            const std::size_t colon = FindTopLevel(params[index], ":");
            const std::string name = Trim(std::string_view(params[index]).substr(0, colon));
            std::string type = colon == std::string::npos
                ? (index < expected_fn.first.size() ? expected_fn.first[index] : "?")
                : CompactType(std::string_view(params[index]).substr(colon + 1));
            if (index < expected_fn.first.size() && type != "?" &&
                !Compatible(type, expected_fn.first[index], model_) &&
                !Compatible(expected_fn.first[index], type, model_)) {
                if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
                    std::cerr << "lambda parameter mismatch: " << type
                              << " vs " << expected_fn.first[index] << '\n';
                }
                return {"?", false, true, "lambda parameter type mismatch"};
            }
            lambda_context.variables[name] = type;
            param_types.push_back(type);
        }
        ExpressionTyper lambda_typer(model_, lambda_context, full_source_);
        ExprResult result_body = lambda_typer.Infer(body, expected_fn.second);
        if (result_body.error) {
            if (!lambda_closed && result_body.message == "argument type mismatch") {
                return {};
            }
            return result_body;
        }
        if (!expected_fn.second.empty() && result_body.known &&
            !Compatible(result_body.type, expected_fn.second, model_)) {
            if (!lambda_closed) {
                if (TailBinary(body) && HasSeenValidLambdaTwin(body)) {
                    return {"?", false, true, "lambda return type mismatch"};
                }
                return {};
            }
            return {"?", false, true, "lambda return type mismatch"};
        }
        std::string type = "(";
        for (std::size_t index = 0; index < param_types.size(); ++index) {
            if (index) type += ",";
            type += param_types[index];
        }
        type += ")->" + (result_body.known ? result_body.type : expected_fn.second);
        if (lambda_closed && result_body.known) {
            g_valid_lambda_bodies.insert(CanonicalLambdaBody(body));
        }
        return {type, lambda_closed && result_body.known, false, {}, true};
    }

    const bool multiline_string = StartsWith(expression, "\"\"\"");
    const auto string_literal_end = FirstStringLiteralEnd(expression);
    if (multiline_string && !string_literal_end) {
        return {};
    }
    if (expression.front() == '"' &&
        (!string_literal_end || *string_literal_end == expression.size() - 1)) {
        if (!multiline_string && expected == "Rune" && string_literal_end &&
            expression.size() >= 3) {
            const std::string_view content(expression.data() + 1, expression.size() - 2);
            std::size_t scalars = 0;
            for (std::size_t index = 0; index < content.size();) {
                if (content[index] == '\\' && index + 1 < content.size()) index += 2;
                else {
                    const unsigned char lead = static_cast<unsigned char>(content[index]);
                    index += lead < 0x80 ? 1 : lead < 0xE0 ? 2 : lead < 0xF0 ? 3 : 4;
                }
                ++scalars;
            }
            if (scalars == 1) return {"Rune", true, false, {}};
        }
        return {"String", true, false, {}};
    }
    if (expression == "true" || expression == "false") return {"Bool", true, false, {}};
    static const std::regex integer_pattern(
        R"((?:[0-9]+|0[xX][0-9a-fA-F]+|0[oO][0-7]+|0[bB][01]+)(?:i(?:8|16|32|64))?)"
    );
    static const std::regex floating_pattern(R"([0-9]+\.[0-9]*(?:f(?:32|64))?)");
    if (std::regex_match(expression, floating_pattern)) {
        return {expression.find("f32") != std::string::npos ? "Float32" : "Float64", true, false, {}};
    }
    if (std::regex_match(expression, integer_pattern)) {
        if (expression.find("i8") != std::string::npos) return {"Int8", true, false, {}};
        if (expression.find("i16") != std::string::npos) return {"Int16", true, false, {}};
        if (expression.find("i32") != std::string::npos) return {"Int32", true, false, {}};
        return {"Int64", true, false, {}};
    }
    if (expression.front() == '!' || expression.front() == '-') {
        ExprResult operand = InferImpl(Trim(std::string_view(expression).substr(1)), {}, depth + 1);
        if (operand.error || !operand.known) return operand;
        if (expression.front() == '!' && operand.type != "Bool") {
            return {"?", false, true, "logical not requires Bool"};
        }
        if (expression.front() == '-' && !(IsInteger(operand.type) || IsFloat(operand.type))) {
            return {"?", false, true, "unary minus requires numeric"};
        }
        return operand;
    }

    bool call_closed = false;
    if (const auto call_open = FindCallOpen(expression, &call_closed)) {
        std::string callee = Trim(std::string_view(expression).substr(0, *call_open));
        const auto parsed_callee = ParseExplicitTypes(callee);
        const bool call_crosses_binary = TailBinary(parsed_callee.first).has_value();
        if (!callee.empty() && !call_crosses_binary) {
            std::string arguments = expression.substr(
                *call_open + 1,
                expression.size() - *call_open - 1 - (call_closed ? 1 : 0)
            );
            std::string base;
            std::string name = callee;
            if (const auto member = ParseMember(callee)) {
                base = member->first;
                name = member->second;
            }
            auto explicit_pair = ParseExplicitTypes(name);
            name = explicit_pair.first;
            return InferCall(base, name, explicit_pair.second, arguments, call_closed, expected, depth + 1);
        }
    }
    if (const auto binary = TailBinary(expression)) {
        const auto& [left_text, op, right_text] = *binary;
        const bool range_operator = op == ".." || op == "..=";
        const std::size_t range_step_colon = range_operator
            ? FindTopLevel(right_text, ":") : std::string::npos;
        const std::string range_endpoint_text = range_step_colon == std::string::npos
            ? right_text
            : Trim(std::string_view(right_text).substr(0, range_step_colon));
        ExprResult left = InferImpl(left_text, {}, depth + 1);
        ExprResult right = InferImpl(range_endpoint_text, {}, depth + 1);
        if (left.error) return left;
        if (right.error) return right;
        const bool partial_right_identifier =
            range_step_colon == std::string::npos &&
            MayExtendTrailingIdentifier(range_endpoint_text) &&
            IsIdentifierText(range_endpoint_text) &&
            range_endpoint_text != "true" && range_endpoint_text != "false";
        if (op == "&&" || op == "||") {
            if (left.known && left.type != "Bool") {
                return {"?", false, true, "logical operands require Bool"};
            }
            if (right.known && right.type != "Bool" && !partial_right_identifier)
                return {"?", false, true, "logical operands require Bool"};
            return {"Bool", left.known || right.known, false, {}};
        }
        if (op == "==" || op == "!=") {
            if (left.known && right.known && !Compatible(left.type, right.type, model_) &&
                !Compatible(right.type, left.type, model_)) {
                return {"?", false, true, "incomparable operands"};
            }
            return {"Bool", left.known || right.known, false, {}};
        }
        if (op == "<" || op == ">" || op == "<=" || op == ">=") {
            if (left.known && !IsNumeric(left.type)) {
                return {"?", false, true, "relational operands must be numeric"};
            }
            if (right.known && !IsNumeric(right.type) && !partial_right_identifier)
                return {"?", false, true, "relational operands must be numeric"};
            if (left.known && right.known && !SameNumericFamily(left.type, right.type)) {
                return {"?", false, true, "mixed numeric relation"};
            }
            return {"Bool", left.known || right.known, false, {}};
        }
        if (op == ".." || op == "..=") {
            if ((left.known && !(IsInteger(left.type) || left.type == "Rune")) ||
                (right.known && !(IsInteger(right.type) || right.type == "Rune") &&
                 !partial_right_identifier)) {
                return {"?", false, true, "range endpoints must be integral"};
            }
            if (left.known && right.known && left.type != right.type &&
                !partial_right_identifier) {
                return {"?", false, true, "range endpoints must share type"};
            }
            const std::string element = left.known ? left.type : (right.known ? right.type : "Int64");
            if (range_step_colon != std::string::npos) {
                const std::string step_text = Trim(
                    std::string_view(right_text).substr(range_step_colon + 1)
                );
                if (!step_text.empty()) {
                    ExprResult step = InferImpl(step_text, element, depth + 1);
                    if (step.error) return step;
                    const bool partial_step_identifier =
                        MayExtendTrailingIdentifier(step_text) &&
                        IsIdentifierText(step_text) &&
                        step_text != "true" && step_text != "false";
                    if (step.known &&
                        !(IsInteger(step.type) || step.type == "Rune") &&
                        !partial_step_identifier) {
                        return {"?", false, true,
                                "range step must be integral"};
                    }
                    if ((left.known || right.known) && step.known &&
                        step.type != element && !partial_step_identifier) {
                        return {"?", false, true,
                                "range step must share endpoint type"};
                    }
                }
            }
            return {"Range<" + element + ">", left.known || right.known, false, {}};
        }
        if (op == "%") {
            if ((left.known && !IsInteger(left.type)) ||
                (right.known && !IsInteger(right.type) && !partial_right_identifier)) {
                return {"?", false, true, "modulo operands must be integral"};
            }
            return left.known ? left : right;
        }
        if (op == "+" || op == "-" || op == "*" || op == "/") {
            const bool string_plus = op == "+" && left.known && left.type == "String";
            if (left.known && !IsNumeric(left.type) && !string_plus) {
                return {"?", false, true, "arithmetic operands must be numeric"};
            }
            if (right.known && string_plus && right.type != "String" && !partial_right_identifier) {
                return {"?", false, true, "string concatenation requires String"};
            }
            if (right.known && !string_plus && !IsNumeric(right.type) && !partial_right_identifier) {
                return {"?", false, true, "arithmetic operands must be numeric"};
            }
            const bool integer_pair = left.known && right.known &&
                IsInteger(left.type) && IsInteger(right.type);
            if (left.known && right.known && !string_plus && !partial_right_identifier &&
                !SameNumericFamily(left.type, right.type) && !integer_pair) {
                return {"?", false, true, "mixed numeric arithmetic"};
            }
            if (integer_pair) {
                if (left.type == "Int64" || right.type == "Int64") return {"Int64", true, false, {}};
                return left;
            }
            return left.known ? left : right;
        }
    }

    if (expression.front() == '[') {
        const bool array_closed = expression.back() == ']';
        std::string inner = expression.substr(1);
        if (array_closed && !inner.empty()) inner.pop_back();
        const auto expected_args = TypeHead(expected) == "Array"
            ? TypeArgs(expected) : std::vector<std::string>{};
        const bool concrete_expected_element = expected_args.size() == 1 &&
            KnownType(TypeHead(expected_args.front()), model_);
        if (Trim(inner).empty()) {
            if (array_closed && !concrete_expected_element) {
                return {"?", false, true, "empty array requires a concrete expected type"};
            }
            if (concrete_expected_element) return {expected, true, false, {}, true};
            return {};
        }
        const auto elements = SplitTopLevel(inner, ',');
        std::string element_type;
        for (std::size_t index = 0; index < elements.size(); ++index) {
            const std::string& item = elements[index];
            ExprResult element = InferImpl(
                item,
                concrete_expected_element ? expected_args.front() : std::string{},
                depth + 1
            );
            if (element.error) return element;
            const bool last_open = !array_closed && index + 1 == elements.size();
            if (concrete_expected_element && element.known &&
                !Compatible(element.type, expected_args.front(), model_) &&
                (!last_open ||
                 (!MemberRecoversType(model_, element.type, expected_args.front()) &&
                  !OperatorRecoversType(model_, element.type, expected_args.front())))) {
                return {"?", false, true, "array element type mismatch"};
            }
            if (!element.known) continue;
            if (element_type.empty()) element_type = element.type;
            else if (!Compatible(element.type, element_type, model_) &&
                     !(index + 1 == elements.size() &&
                       MayExtendTrailingIdentifier(Trim(item)))) {
                return {"?", false, true, "array element type mismatch"};
            }
        }
        return {"Array<" + (element_type.empty() ? std::string("?") : element_type) + ">",
                !element_type.empty(), false, {}, true};
    }

    if (!expression.empty() && expression.back() == ']') {
        int depth_counter = 0;
        for (std::size_t index = expression.size(); index-- > 0;) {
            if (expression[index] == ']') ++depth_counter;
            else if (expression[index] == '[' && --depth_counter == 0) {
                ExprResult base = InferImpl(expression.substr(0, index), {}, depth + 1);
                ExprResult subscript = InferImpl(
                    expression.substr(index + 1, expression.size() - index - 2), {}, depth + 1
                );
                if (base.error) return base;
                if (subscript.error) return subscript;
                if (base.known && TypeHead(base.type) != "Array" && TypeHead(base.type) != "ArrayList" && base.type != "String") {
                    return {"?", false, true, "cannot index non-array"};
                }
                if (subscript.known && subscript.type != "Int64") {
                    return {"?", false, true, "array index must be Int64"};
                }
                if (base.type == "String") return {"Rune", true, false, {}, true};
                const auto args = TypeArgs(base.type);
                return args.empty()
                    ? ExprResult{}
                    : ExprResult{args.front(), true, false, {}, true};
            }
        }
    }
    const std::size_t open_index = expression.rfind('[');
    if (open_index != std::string::npos && expression.find(']', open_index) == std::string::npos) {
        ExprResult base = InferImpl(expression.substr(0, open_index), {}, depth + 1);
        ExprResult subscript = InferImpl(expression.substr(open_index + 1), {}, depth + 1);
        if (base.error) return base;
        if (subscript.error) return subscript;
        if (base.known && TypeHead(base.type) != "Array" && TypeHead(base.type) != "ArrayList" && base.type != "String") {
            return {"?", false, true, "cannot index non-array"};
        }
        const std::string subscript_text = Trim(
            std::string_view(expression).substr(open_index + 1)
        );
        const bool partial_subscript = MayExtendTrailingIdentifier(subscript_text) &&
            IsIdentifierText(subscript_text) &&
            subscript_text != "true" && subscript_text != "false";
        if (subscript.known && subscript.type != "Int64" && !partial_subscript) {
            return {"?", false, true, "array index must be Int64"};
        }
        return {};
    }

    if (const auto member = ParseMember(expression)) {
        if (member->second.empty()) {
            ExprResult base = InferImpl(member->first, {}, depth + 1);
            return base.error ? base : ExprResult{};
        }
        ExprResult base = InferImpl(member->first, {}, depth + 1);
        if (base.error || !base.known) return base;
        const bool type_receiver = StartsWith(base.type, "type:");
        const std::string receiver_type = type_receiver ? base.type.substr(5) : base.type;
        if (!type_receiver && StartsWith("toString", member->second)) {
            if (MayExtendTrailingIdentifier(member->second)) return {};
            if (member->second == "toString") return {"method", true, false, {}, true};
        }
        const auto nominal = model_.nominals.find(TypeHead(receiver_type));
        if (nominal == model_.nominals.end()) return {"?", false, true, "unknown receiver type"};
        const auto& fields = type_receiver ? nominal->second.static_fields : nominal->second.fields;
        if (const auto field = fields.find(member->second); field != fields.end()) {
            std::unordered_map<std::string, std::string> substitutions;
            const auto args = TypeArgs(receiver_type);
            for (std::size_t index = 0;
                 index < args.size() && index < nominal->second.type_params.size(); ++index) {
                substitutions[nominal->second.type_params[index]] = args[index];
            }
            return {
                ApplySubstitution(field->second, substitutions), true, false, {}, true
            };
        }
        const auto& methods = type_receiver ? nominal->second.static_methods : nominal->second.methods;
        if (const auto method = methods.find(member->second); method != methods.end()) {
            if (MayExtendTrailingIdentifier(member->second)) return {};
            if (method->second.size() > 1) {
                return {"?", false, true, "ambiguous overloaded member reference"};
            }
            std::unordered_map<std::string, std::string> substitutions;
            const auto receiver_args = TypeArgs(receiver_type);
            for (std::size_t index = 0;
                 index < receiver_args.size() && index < nominal->second.type_params.size(); ++index) {
                substitutions[nominal->second.type_params[index]] = receiver_args[index];
            }
            std::vector<std::string> candidates;
            for (const FunctionSig& signature : method->second) {
                std::string function_type = "(";
                for (std::size_t index = 0; index < signature.param_types.size(); ++index) {
                    if (index) function_type += ",";
                    function_type += ApplySubstitution(
                        signature.param_types[index], substitutions
                    );
                }
                function_type += ")->";
                function_type += ApplySubstitution(signature.result, substitutions);
                if (expected.empty() || Compatible(function_type, expected, model_)) {
                    candidates.push_back(std::move(function_type));
                }
            }
            if (candidates.size() == 1) {
                return {candidates.front(), true, false, {}, true};
            }
            return {"?", false, true, "ambiguous overloaded member reference"};
        }
        const bool partial = MayExtendTrailingIdentifier(member->second);
        if (partial) {
            for (const auto& [name, _] : fields) if (StartsWith(name, member->second)) return {};
            for (const auto& [name, _] : methods) if (StartsWith(name, member->second)) return {};
        }
        if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
            std::cerr << "unknown field/member '" << member->second << "' on "
                      << receiver_type << " in " << expression << '\n';
        }
        return {"?", false, true, "unknown member"};
    }

    static const std::regex identifier_pattern(R"([A-Za-z_][A-Za-z0-9_]*)");
    if (std::regex_match(expression, identifier_pattern)) {
        if (const auto variable = context_.variables.find(expression); variable != context_.variables.end()) {
            return {variable->second, variable->second != "?", false, {}};
        }
        if (const auto global = model_.globals.find(expression); global != model_.globals.end()) {
            return {global->second, true, false, {}};
        }
        if (const auto functions = model_.functions.find(expression);
            functions != model_.functions.end()) {
            if (MayExtendTrailingIdentifier(expression)) return {};
            std::vector<std::string> candidates;
            for (const FunctionSig& signature : functions->second) {
                std::string pattern = "(";
                for (std::size_t index = 0; index < signature.param_types.size(); ++index) {
                    if (index) pattern += ",";
                    pattern += signature.param_types[index];
                }
                pattern += ")->" + signature.result;
                std::unordered_set<std::string> type_parameters(
                    signature.type_params.begin(), signature.type_params.end()
                );
                std::unordered_map<std::string, std::string> substitutions;
                if (!expected.empty()) {
                    BindTypeVariables(
                        pattern, expected, type_parameters, &substitutions
                    );
                }
                const std::string function_type = ApplySubstitution(
                    pattern, substitutions
                );
                if (expected.empty() || Compatible(function_type, expected, model_)) {
                    candidates.push_back(function_type);
                }
            }
            if (candidates.size() == 1) {
                return {candidates.front(), true, false, {}, true};
            }
            return {"?", false, true, "ambiguous function reference"};
        }
        if (const auto nominal = model_.nominals.find(expression); nominal != model_.nominals.end()) {
            if (nominal->second.is_interface) return {"?", false, true, "interface used as value"};
            if (MayExtendTrailingIdentifier(expression)) return {};
            return {"type:" + expression, true, false, {}};
        }
        if (MayExtendTrailingIdentifier(expression) &&
            (StartsWith("true", expression) || StartsWith("false", expression))) {
            return {};
        }
        if (MayExtendTrailingIdentifier(expression) && HasSymbolPrefix(expression)) return {};
        if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
            std::cerr << "undefined expression identifier '" << expression << "'\n";
        }
        return {"?", false, true, "undefined identifier"};
    }
    return {};
}

// 收集可从初始化表达式推断出类型的局部变量（var x = expr 形式）
void CollectInferredLocalVariables(
    FunctionContext* context,
    const Model& model,
    std::string_view full_source
) {
    static const std::regex declaration_pattern(
        R"(\b(let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*([^=;\n]+?))?\s*=\s*([^;\n]+))"
    );
    for (std::sregex_iterator it(context->body.begin(), context->body.end(), declaration_pattern), end;
         it != end; ++it) {
        const std::string name = (*it)[2].str();
        if ((*it)[3].matched) {
            context->variables[name] = CompactType((*it)[3].str());
        } else {
            ExpressionTyper typer(model, *context, full_source);
            ExprResult inferred = typer.Infer((*it)[4].str());
            if (inferred.known && !inferred.error) context->variables[name] = inferred.type;
        }
        if ((*it)[1].str() == "let") context->immutable.insert(name);
    }
}


// 判断单个成员、调用或下标后缀能否恢复目标类型。
bool MemberRecoversType(
    const Model& model,
    const std::string& type,
    const std::string& target,
    int depth
) {
    if (type.empty() || target.empty() || depth > 3) return false;
    if (IsFunctionType(type)) {
        const auto parts = FunctionTypeParts(type);
        return Compatible(parts.second, target, model);
    }
    const bool type_receiver = StartsWith(type, "type:");
    const std::string nominal_text = type_receiver ? type.substr(5) : type;
    const std::string head = TypeHead(nominal_text);
    if (head == "Array" || head == "ArrayList") {
        const std::vector<std::string> args = TypeArgs(nominal_text);
        if (!args.empty() && Compatible(args.front(), target, model)) return true;
    }
    if (head == "String" && Compatible("Rune", target, model)) return true;
    const auto found = model.nominals.find(head);
    if (found == model.nominals.end()) {
        if ((head == "Int64" || head == "Float64" || head == "Bool") &&
            target == "String") {
            return true;
        }
        return false;
    }
    const NominalInfo& info = found->second;
    const std::vector<std::string> args = TypeArgs(nominal_text);
    auto subst = [&](std::string text) {
        if (args.empty()) return text;
        std::unordered_map<std::string, std::string> subs;
        for (std::size_t i = 0; i < info.type_params.size() && i < args.size(); ++i) {
            subs[info.type_params[i]] = args[i];
        }
        return ApplySubstitution(std::move(text), subs);
    };
    auto sig_recovers = [&](const FunctionSig& sig) {
        FunctionSig substituted = sig;
        for (std::string& param : substituted.param_types) {
            param = subst(param);
        }
        substituted.result = subst(sig.result);
        if (IsFunctionType(target) &&
            Compatible(PostfixGraph::FunctionTypeOf(substituted), target, model)) {
            return true;
        }
        if (!KnownType(TypeHead(substituted.result), model)) return true;
        return Compatible(substituted.result, target, model);
    };
    if (type_receiver) {
        for (const auto& field : info.static_fields) {
            if (Compatible(subst(field.second), target, model)) return true;
        }
        for (const auto& method : info.static_methods) {
            for (const FunctionSig& sig : method.second) {
                if (sig_recovers(sig)) return true;
            }
        }
        return false;
    }
    for (const auto& field : info.fields) {
        if (Compatible(subst(field.second), target, model)) return true;
    }
    for (const auto& method : info.methods) {
        for (const FunctionSig& sig : method.second) {
            if (sig_recovers(sig)) return true;
        }
    }
    for (const std::string& super : info.supers) {
        if (MemberRecoversType(model, subst(super), target, depth + 1)) return true;
    }
    return false;
}

// 判断运算符结果类型能否通过后续运算恢复为期望类型
bool OperatorRecoversType(const Model& model, const std::string& type, const std::string& target) {
    if (type.empty() || target.empty()) return false;
    if (target != "Bool") return false;
    if (IsFunctionType(type)) return false;
    return KnownType(TypeHead(type), model);
}


}
