#include "semantic_constructor.h"

#include "semantic_declarations.h"
#include "semantic_text.h"
#include "semantic_types.h"

#include <algorithm>
#include <cctype>
#include <optional>
#include <regex>
#include <set>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace cangjie {

struct FieldFlowToken {
    enum class Kind { Identifier, Symbol, Newline, Opaque };
    Kind kind = Kind::Symbol;
    std::string text;
};

// 把构造器体内的语句流切分为"字段访问 + 赋值"token 序列（用于字段初始化分析）
std::vector<FieldFlowToken> TokenizeFieldFlow(std::string_view source) {
    std::vector<FieldFlowToken> tokens;
    std::size_t index = 0;
    while (index < source.size()) {
        const unsigned char ch = static_cast<unsigned char>(source[index]);
        if (source[index] == '\n' || source[index] == '\r') {
            if (source[index] == '\r' && index + 1 < source.size() &&
                source[index + 1] == '\n') {
                ++index;
            }
            tokens.push_back({FieldFlowToken::Kind::Newline, "\n"});
            ++index;
            continue;
        }
        if (std::isspace(ch)) {
            ++index;
            continue;
        }
        if (index + 1 < source.size() && source.substr(index, 2) == "//") {
            index += 2;
            while (index < source.size() && source[index] != '\n' &&
                   source[index] != '\r') {
                ++index;
            }
            continue;
        }
        if (index + 1 < source.size() && source.substr(index, 2) == "/*") {
            int depth = 1;
            index += 2;
            while (index < source.size() && depth > 0) {
                if (index + 1 < source.size() && source.substr(index, 2) == "/*") {
                    ++depth;
                    index += 2;
                } else if (index + 1 < source.size() && source.substr(index, 2) == "*/") {
                    --depth;
                    index += 2;
                } else {
                    ++index;
                }
            }
            continue;
        }
        if (index + 3 <= source.size() && source.substr(index, 3) == "\"\"\"") {
            index += 3;
            bool escaped = false;
            while (index < source.size()) {
                if (!escaped && index + 3 <= source.size() &&
                    source.substr(index, 3) == "\"\"\"") {
                    index += 3;
                    break;
                }
                if (escaped) escaped = false;
                else if (source[index] == '\\') escaped = true;
                ++index;
            }
            tokens.push_back({FieldFlowToken::Kind::Opaque, "literal"});
            continue;
        }
        if (source[index] == '`') {
            const std::size_t close = source.find('`', index + 1);
            if (close != std::string_view::npos) {
                const std::string name(source.substr(index + 1, close - index - 1));
                if (IsIdentifierText(name)) {
                    tokens.push_back({FieldFlowToken::Kind::Identifier, name});
                    index = close + 1;
                    continue;
                }
            }
        }
        if (source[index] == 'r' && index + 1 < source.size() &&
            source[index + 1] == '\'') {
            index += 2;
            bool escaped = false;
            while (index < source.size()) {
                const char current = source[index++];
                if (escaped) escaped = false;
                else if (current == '\\') escaped = true;
                else if (current == '\'') break;
            }
            tokens.push_back({FieldFlowToken::Kind::Opaque, "literal"});
            continue;
        }
        if (source[index] == '"' || source[index] == '\'') {
            const char quote = source[index++];
            bool escaped = false;
            while (index < source.size()) {
                const char current = source[index++];
                if (escaped) escaped = false;
                else if (current == '\\') escaped = true;
                else if (current == quote) break;
            }
            tokens.push_back({FieldFlowToken::Kind::Opaque, "literal"});
            continue;
        }
        if (std::isdigit(ch)) {
            const std::size_t start = index;
            if (source[index] == '0' && index + 1 < source.size() &&
                (source[index + 1] == 'x' || source[index + 1] == 'X')) {
                index += 2;
                while (index < source.size() && std::isxdigit(
                           static_cast<unsigned char>(source[index]))) ++index;
            } else if (source[index] == '0' && index + 1 < source.size() &&
                       (source[index + 1] == 'o' || source[index + 1] == 'O' ||
                        source[index + 1] == 'b' || source[index + 1] == 'B')) {
                index += 2;
                while (index < source.size() && std::isdigit(
                           static_cast<unsigned char>(source[index]))) ++index;
            } else {
                while (index < source.size() && std::isdigit(
                           static_cast<unsigned char>(source[index]))) ++index;
                if (index < source.size() && source[index] == '.' &&
                    (index + 1 >= source.size() || source[index + 1] != '.')) {
                    ++index;
                    while (index < source.size() && std::isdigit(
                               static_cast<unsigned char>(source[index]))) ++index;
                }
                if (index < source.size() &&
                    (source[index] == 'e' || source[index] == 'E')) {
                    ++index;
                    if (index < source.size() &&
                        (source[index] == '+' || source[index] == '-')) ++index;
                    while (index < source.size() && std::isdigit(
                               static_cast<unsigned char>(source[index]))) ++index;
                }
            }
            if (index < source.size() &&
                (source[index] == 'i' || source[index] == 'u' ||
                 source[index] == 'f')) {
                ++index;
                while (index < source.size() && std::isdigit(
                           static_cast<unsigned char>(source[index]))) ++index;
            }
            tokens.push_back({
                FieldFlowToken::Kind::Opaque,
                std::string(source.substr(start, index - start)),
            });
            continue;
        }
        if (IsIdentStart(ch)) {
            const std::size_t start = index++;
            while (index < source.size() && IsIdentContinue(
                       static_cast<unsigned char>(source[index]))) {
                ++index;
            }
            tokens.push_back({
                FieldFlowToken::Kind::Identifier,
                std::string(source.substr(start, index - start)),
            });
            continue;
        }
        static const std::unordered_set<std::string> three_character_operators = {
            "<<=", ">>=", "**=", "&&=", "||=",
        };
        static const std::unordered_set<std::string> two_character_operators = {
            "==", "!=", "<=", ">=", "=>", "+=", "-=", "*=", "/=", "%=",
            "&=", "|=", "^=", "&&", "||", "**", "<<", ">>", "..",
        };
        if (index + 3 <= source.size()) {
            const std::string candidate(source.substr(index, 3));
            if (three_character_operators.count(candidate)) {
                tokens.push_back({FieldFlowToken::Kind::Symbol, candidate});
                index += 3;
                continue;
            }
        }
        if (index + 2 <= source.size()) {
            const std::string candidate(source.substr(index, 2));
            if (two_character_operators.count(candidate)) {
                tokens.push_back({FieldFlowToken::Kind::Symbol, candidate});
                index += 2;
                continue;
            }
        }
        tokens.push_back({
            FieldFlowToken::Kind::Symbol,
            std::string(1, source[index++]),
        });
    }
    return tokens;
}

class ConstructorFieldFlowAnalyzer {
 public:
    struct State {
        std::unordered_set<std::string> assigned;
        std::unordered_set<std::string> locals;
        bool reachable = true;
        bool uncertain_control_flow = false;
    };

    // 构造字段流分析器并记录待初始化字段和参数。
    ConstructorFieldFlowAnalyzer(
        std::string_view body,
        std::unordered_set<std::string> uninitialized,
        std::unordered_set<std::string> parameters
    ) : tokens_(TokenizeFieldFlow(body)), uninitialized_(std::move(uninitialized)) {
        initial_.locals = std::move(parameters);
    }

    // 分析整个构造器并返回最终字段状态。
    CheckStatus Analyze(bool constructor_closed, State* result) const {
        State state = initial_;
        CheckStatus status = AnalyzeBlock(
            0, tokens_.size(), constructor_closed, &state
        );
        if (status.ok && result) *result = std::move(state);
        return status;
    }

 private:
    // 跳过换行并返回下一个有效 token。
    std::size_t Next(std::size_t index, std::size_t end) const {
        while (index < end && tokens_[index].kind == FieldFlowToken::Kind::Newline) {
            ++index;
        }
        return index;
    }

    // 向前查找上一个非换行 token。
    std::size_t Previous(std::size_t index, std::size_t begin) const {
        while (index > begin) {
            --index;
            if (tokens_[index].kind != FieldFlowToken::Kind::Newline) return index;
        }
        return std::string::npos;
    }

    // 查找成对符号对应的闭合 token。
    std::optional<std::size_t> MatchingToken(
        std::size_t open,
        std::size_t end,
        std::string_view opening,
        std::string_view closing
    ) const {
        if (open >= end || tokens_[open].text != opening) return std::nullopt;
        int depth = 0;
        for (std::size_t index = open; index < end; ++index) {
            if (tokens_[index].text == opening) ++depth;
            else if (tokens_[index].text == closing && --depth == 0) return index;
        }
        return std::nullopt;
    }

    // 查找当前简单语句的结束 token。
    std::size_t StatementEnd(std::size_t begin, std::size_t end) const {
        static const std::unordered_set<std::string> trailing_continuations = {
            "=", "+", "-", "*", "/", "%", "&&", "||", "&", "|", "^",
            "==", "!=", "<", ">", "<=", ">=", "=>", ".", ",", ":",
        };
        static const std::unordered_set<std::string> leading_continuations = {
            "=", "+", "-", "*", "/", "%", "&&", "||", "&", "|", "^",
            "==", "!=", "<", ">", "<=", ">=", ".", ",",
        };
        int paren = 0;
        int bracket = 0;
        int brace = 0;
        bool saw_assignment = false;
        bool saw_assignment_value = false;
        for (std::size_t index = begin; index < end; ++index) {
            const std::string& token = tokens_[index].text;
            if (paren == 0 && bracket == 0 && brace == 0 &&
                saw_assignment && saw_assignment_value &&
                IsAssignmentStart(index, end)) {
                return index;
            }
            if (token == "(") ++paren;
            else if (token == ")" && paren > 0) --paren;
            else if (token == "[") ++bracket;
            else if (token == "]" && bracket > 0) --bracket;
            else if (token == "{") ++brace;
            else if (token == "}" && brace > 0) --brace;
            else if (token == "=" && paren == 0 && bracket == 0 && brace == 0 &&
                     !saw_assignment) {
                saw_assignment = true;
                saw_assignment_value = false;
            }
            else if ((tokens_[index].kind == FieldFlowToken::Kind::Newline ||
                      token == ";") && paren == 0 && bracket == 0 && brace == 0) {
                if (tokens_[index].kind == FieldFlowToken::Kind::Newline) {
                    const std::size_t previous = Previous(index, begin);
                    const std::size_t next = Next(index + 1, end);
                    if ((previous != std::string::npos &&
                         trailing_continuations.count(tokens_[previous].text)) ||
                        (next < end && leading_continuations.count(tokens_[next].text))) {
                        continue;
                    }
                }
                return index;
            }
            if (saw_assignment && token != "=" && token != ";" &&
                tokens_[index].kind != FieldFlowToken::Kind::Newline) {
                saw_assignment_value = true;
            }
        }
        return end;
    }

    // 判断当前位置是否开始一个简单赋值。
    bool IsAssignmentStart(std::size_t index, std::size_t end) const {
        if (index >= end ||
            tokens_[index].kind != FieldFlowToken::Kind::Identifier) {
            return false;
        }
        std::size_t cursor = Next(index + 1, end);
        if (tokens_[index].text == "this" && cursor < end &&
            tokens_[cursor].text == ".") {
            cursor = Next(cursor + 1, end);
            if (cursor >= end ||
                tokens_[cursor].kind != FieldFlowToken::Kind::Identifier) {
                return false;
            }
            cursor = Next(cursor + 1, end);
        }
        return cursor < end && tokens_[cursor].text == "=";
    }

    // 判断当前位置是否消费了语句边界。
    bool ConsumesStatementBoundary(std::size_t index, std::size_t end) const {
        return index < end &&
            (tokens_[index].kind == FieldFlowToken::Kind::Newline ||
             tokens_[index].text == ";");
    }

    // 判断字段读取是否发生在首次赋值之前。
    bool IsUninitializedRead(
        const std::string& name,
        const State& state,
        bool explicit_this
    ) const {
        if (!uninitialized_.count(name) || state.assigned.count(name)) return false;
        return explicit_this || !state.locals.count(name);
    }

    // 检查表达式中的字段读取和嵌套 Lambda。
    CheckStatus AnalyzeExpression(
        std::size_t begin,
        std::size_t end,
        bool statement_complete,
        State* state
    ) const {
        const std::size_t first = Next(begin, end);
        for (std::size_t index = first; index < end; ++index) {
            if (tokens_[index].text == "{") {
                const auto close = MatchingToken(index, end, "{", "}");
                const std::size_t lambda_end = close.value_or(end);
                const std::size_t before_brace = Previous(index, begin);
                const bool may_be_lambda = index == first ||
                    (before_brace != std::string::npos &&
                     (tokens_[before_brace].text == "=" ||
                      tokens_[before_brace].text == "(" ||
                      tokens_[before_brace].text == "[" ||
                      tokens_[before_brace].text == ","));
                int brace_depth = 0;
                std::size_t arrow = lambda_end;
                for (std::size_t cursor = index + 1;
                     may_be_lambda && cursor < lambda_end; ++cursor) {
                    if (tokens_[cursor].text == "{") ++brace_depth;
                    else if (tokens_[cursor].text == "}" && brace_depth > 0) --brace_depth;
                    else if (tokens_[cursor].text == "=>" && brace_depth == 0) {
                        arrow = cursor;
                        break;
                    }
                }
                if (arrow < lambda_end) {
                    State lambda_state = *state;
                    const std::size_t first_parameter = Next(index + 1, arrow);
                    for (std::size_t cursor = first_parameter; cursor < arrow; ++cursor) {
                        if (tokens_[cursor].kind != FieldFlowToken::Kind::Identifier) continue;
                        const std::size_t previous = Previous(cursor, index + 1);
                        const std::size_t next = Next(cursor + 1, arrow);
                        const bool parameter_start = cursor == first_parameter ||
                            (previous != std::string::npos && tokens_[previous].text == ",");
                        const bool parameter_end = next == arrow ||
                            tokens_[next].text == ":" || tokens_[next].text == ",";
                        if (parameter_start && parameter_end) {
                            lambda_state.locals.insert(tokens_[cursor].text);
                        }
                    }
                    CheckStatus lambda = AnalyzeBlock(
                        arrow + 1, lambda_end, close.has_value(), &lambda_state
                    );
                    if (!lambda.ok) return lambda;
                    if (!close) return {};
                    index = *close;
                    continue;
                }
                if (!close) return {};
                index = *close;
                continue;
            }
            if (tokens_[index].kind != FieldFlowToken::Kind::Identifier) continue;
            const std::string& name = tokens_[index].text;
            const std::size_t next = Next(index + 1, end);
            const std::size_t previous = Previous(index, begin);
            const bool explicit_this = previous != std::string::npos &&
                tokens_[previous].text == "." &&
                Previous(previous, begin) != std::string::npos &&
                tokens_[Previous(previous, begin)].text == "this";
            if (previous != std::string::npos && tokens_[previous].text == "." &&
                !explicit_this) {
                continue;
            }
            if (next < end && tokens_[next].text == ":") continue;
            if (next < end && tokens_[next].text == "=") {
                CheckStatus rhs = AnalyzeExpression(next + 1, end, statement_complete, state);
                if (!rhs.ok) return rhs;
                if (IsUninitializedRead(name, *state, explicit_this)) {
                    state->assigned.insert(name);
                }
                return {};
            }
            if (!IsUninitializedRead(name, *state, explicit_this)) continue;

            if (next == end && !statement_complete) {
                const std::size_t target_start = explicit_this
                    ? Previous(previous, begin) : index;
                const std::size_t before_target = target_start == std::string::npos
                    ? std::string::npos : Previous(target_start, begin);
                if (before_target != std::string::npos &&
                    (tokens_[before_target].kind == FieldFlowToken::Kind::Identifier ||
                     tokens_[before_target].kind == FieldFlowToken::Kind::Opaque ||
                     tokens_[before_target].text == ")" ||
                     tokens_[before_target].text == "]" ||
                     tokens_[before_target].text == "}")) {
                    continue;
                }
            }
            bool ambiguous_assignment_lhs = index == first;
            if (explicit_this) {
                const std::size_t dot = previous;
                const std::size_t receiver = Previous(dot, begin);
                ambiguous_assignment_lhs = receiver == first;
            }
            if (ambiguous_assignment_lhs && next == end && !statement_complete) {
                continue;
            }
            if (next == end && !statement_complete) {
                if (!explicit_this && name == "r") continue;
                const auto may_extend = [&](const std::string& candidate) {
                    return candidate.size() > name.size() && StartsWith(candidate, name);
                };
                if ((!explicit_this && std::any_of(
                         state->locals.begin(), state->locals.end(), may_extend)) ||
                    std::any_of(
                        uninitialized_.begin(), uninitialized_.end(), may_extend)) {
                    continue;
                }
            }
            return {false, "field read before initialization"};
        }
        return {};
    }

    // 合并条件两条分支上的字段赋值状态。
    State MergeConditionalStates(
        const State& before,
        const State& left,
        const State& right
    ) const {
        State result = before;
        result.reachable = left.reachable || right.reachable;
        result.uncertain_control_flow = before.uncertain_control_flow ||
            (left.reachable && left.uncertain_control_flow) ||
            (right.reachable && right.uncertain_control_flow);
        if (left.reachable && right.reachable) {
            result.assigned.clear();
            for (const std::string& field : left.assigned) {
                if (right.assigned.count(field)) result.assigned.insert(field);
            }
        } else if (left.reachable) {
            result.assigned = left.assigned;
        } else if (right.reachable) {
            result.assigned = right.assigned;
        }
        return result;
    }

    // 分析 if 条件和各分支的字段流。
    CheckStatus AnalyzeIf(
        std::size_t start,
        std::size_t end,
        bool enclosing_closed,
        const State& before,
        State* after,
        std::size_t* next_index
    ) const {
        std::size_t cursor = Next(start + 1, end);
        std::size_t condition_end = cursor;
        if (cursor < end && tokens_[cursor].text == "(") {
            const auto close = MatchingToken(cursor, end, "(", ")");
            condition_end = close.value_or(end);
            State condition_state = before;
            CheckStatus condition = AnalyzeExpression(
                cursor + 1, condition_end, close.has_value(), &condition_state
            );
            if (!condition.ok) return condition;
            if (!close) {
                *after = before;
                *next_index = end;
                return {};
            }
            cursor = Next(*close + 1, end);
        } else {
            while (condition_end < end && tokens_[condition_end].text != "{") {
                ++condition_end;
            }
            State condition_state = before;
            CheckStatus condition = AnalyzeExpression(
                cursor, condition_end, condition_end < end, &condition_state
            );
            if (!condition.ok) return condition;
            cursor = condition_end;
        }
        if (cursor >= end || tokens_[cursor].text != "{") {
            *after = before;
            *next_index = end;
            return {};
        }
        const auto then_close = MatchingToken(cursor, end, "{", "}");
        State then_state = before;
        CheckStatus then_status = AnalyzeBlock(
            cursor + 1, then_close.value_or(end), then_close.has_value(), &then_state
        );
        if (!then_status.ok) return then_status;
        if (!then_close) {
            *after = before;
            *next_index = end;
            return {};
        }

        cursor = Next(*then_close + 1, end);
        if (cursor >= end || tokens_[cursor].text != "else") {
            *after = MergeConditionalStates(before, then_state, before);
            *next_index = cursor;
            return {};
        }
        cursor = Next(cursor + 1, end);
        State else_state = before;
        std::size_t else_end = cursor;
        if (cursor < end && tokens_[cursor].text == "if") {
            CheckStatus nested = AnalyzeIf(
                cursor, end, enclosing_closed, before, &else_state, &else_end
            );
            if (!nested.ok) return nested;
        } else if (cursor < end && tokens_[cursor].text == "{") {
            const auto else_close = MatchingToken(cursor, end, "{", "}");
            CheckStatus else_status = AnalyzeBlock(
                cursor + 1, else_close.value_or(end), else_close.has_value(), &else_state
            );
            if (!else_status.ok) return else_status;
            if (!else_close) {
                *after = before;
                *next_index = end;
                return {};
            }
            else_end = *else_close + 1;
        } else {
            *after = before;
            *next_index = end;
            return {};
        }
        *after = MergeConditionalStates(before, then_state, else_state);
        *next_index = else_end;
        return {};
    }

    // 分析 for 或 while 循环中的字段流。
    CheckStatus AnalyzeLoop(
        std::size_t start,
        std::size_t end,
        const State& before,
        std::size_t* next_index
    ) const {
        std::size_t cursor = Next(start + 1, end);
        std::size_t body_open = cursor;
        int paren = 0;
        while (body_open < end) {
            if (tokens_[body_open].text == "(") ++paren;
            else if (tokens_[body_open].text == ")" && paren > 0) --paren;
            else if (tokens_[body_open].text == "{" && paren == 0) break;
            ++body_open;
        }
        std::unordered_set<std::string> loop_locals;
        std::size_t expression_begin = cursor;
        if (tokens_[start].text == "for") {
            std::size_t in_token = cursor;
            for (; in_token < body_open; ++in_token) {
                if (tokens_[in_token].text == "in") break;
            }
            if (in_token >= body_open) {
                *next_index = end;
                return {};
            }
            for (std::size_t index = cursor; index < in_token; ++index) {
                if (tokens_[index].kind == FieldFlowToken::Kind::Identifier) {
                    loop_locals.insert(tokens_[index].text);
                }
            }
            expression_begin = in_token + 1;
        }
        State condition_state = before;
        CheckStatus condition = AnalyzeExpression(
            expression_begin, body_open, body_open < end, &condition_state
        );
        if (!condition.ok) return condition;
        if (body_open >= end) {
            *next_index = end;
            return {};
        }
        const auto body_close = MatchingToken(body_open, end, "{", "}");
        State body_state = before;
        body_state.locals.insert(loop_locals.begin(), loop_locals.end());
        CheckStatus body_status = AnalyzeBlock(
            body_open + 1, body_close.value_or(end), body_close.has_value(), &body_state
        );
        if (!body_status.ok) return body_status;
        *next_index = body_close ? *body_close + 1 : end;
        return {};
    }

    // 分析 do-while 循环中的字段流。
    CheckStatus AnalyzeDoLoop(
        std::size_t start,
        std::size_t end,
        const State& before,
        State* after,
        std::size_t* next_index
    ) const {
        const std::size_t body_open = Next(start + 1, end);
        if (body_open >= end || tokens_[body_open].text != "{") {
            *after = before;
            *next_index = end;
            return {};
        }
        const auto body_close = MatchingToken(body_open, end, "{", "}");
        State body_state = before;
        CheckStatus body_status = AnalyzeBlock(
            body_open + 1, body_close.value_or(end), body_close.has_value(),
            &body_state
        );
        if (!body_status.ok) return body_status;
        if (!body_close) {
            *after = before;
            *next_index = end;
            return {};
        }
        if (!body_state.reachable) {
            *after = body_state;
            *next_index = *body_close + 1;
            return {};
        }

        std::size_t cursor = Next(*body_close + 1, end);
        if (cursor >= end || tokens_[cursor].text != "while") {
            *after = before;
            *next_index = cursor;
            return {};
        }
        const std::size_t condition_begin = Next(cursor + 1, end);
        const std::size_t statement_end = StatementEnd(condition_begin, end);
        CheckStatus condition;
        if (condition_begin < statement_end &&
            tokens_[condition_begin].text == "(") {
            const auto condition_close = MatchingToken(
                condition_begin, statement_end, "(", ")"
            );
            condition = AnalyzeExpression(
                condition_begin + 1, condition_close.value_or(statement_end),
                condition_close.has_value(), &body_state
            );
        } else {
            condition = AnalyzeExpression(
                condition_begin, statement_end,
                statement_end < end, &body_state
            );
        }
        if (!condition.ok) return condition;
        *after = before;
        after->assigned = std::move(body_state.assigned);
        after->reachable = body_state.reachable;
        after->uncertain_control_flow = body_state.uncertain_control_flow;
        *next_index = statement_end < end
            ? statement_end + (ConsumesStatementBoundary(statement_end, end) ? 1 : 0)
            : end;
        return {};
    }

    // 保守分析 match 主体和代码块。
    CheckStatus AnalyzeOpaqueMatch(
        std::size_t start,
        std::size_t end,
        State* state,
        std::size_t* next_index
    ) const {
        std::size_t body_open = Next(start + 1, end);
        int paren = 0;
        int bracket = 0;
        while (body_open < end) {
            if (tokens_[body_open].text == "(") ++paren;
            else if (tokens_[body_open].text == ")" && paren > 0) --paren;
            else if (tokens_[body_open].text == "[") ++bracket;
            else if (tokens_[body_open].text == "]" && bracket > 0) --bracket;
            else if (tokens_[body_open].text == "{" && paren == 0 && bracket == 0) break;
            ++body_open;
        }
        CheckStatus subject = AnalyzeExpression(
            start + 1, body_open, body_open < end, state
        );
        if (!subject.ok) return subject;
        state->uncertain_control_flow = true;
        if (body_open >= end) {
            *next_index = end;
            return {};
        }
        const auto body_close = MatchingToken(body_open, end, "{", "}");
        *next_index = body_close ? *body_close + 1 : end;
        return {};
    }

    // 保守分析 try、catch 和 finally 代码块。
    CheckStatus AnalyzeOpaqueTry(
        std::size_t start,
        std::size_t end,
        State* state,
        std::size_t* next_index
    ) const {
        state->uncertain_control_flow = true;
        std::size_t cursor = Next(start + 1, end);
        if (cursor >= end || tokens_[cursor].text != "{") {
            *next_index = end;
            return {};
        }
        auto close = MatchingToken(cursor, end, "{", "}");
        if (!close) {
            *next_index = end;
            return {};
        }
        cursor = Next(*close + 1, end);
        while (cursor < end &&
               (tokens_[cursor].text == "catch" || tokens_[cursor].text == "finally")) {
            const bool is_catch = tokens_[cursor].text == "catch";
            cursor = Next(cursor + 1, end);
            if (is_catch && cursor < end && tokens_[cursor].text == "(") {
                const auto parameters_close = MatchingToken(cursor, end, "(", ")");
                if (!parameters_close) {
                    *next_index = end;
                    return {};
                }
                cursor = Next(*parameters_close + 1, end);
            }
            if (cursor >= end || tokens_[cursor].text != "{") break;
            close = MatchingToken(cursor, end, "{", "}");
            if (!close) {
                *next_index = end;
                return {};
            }
            cursor = Next(*close + 1, end);
        }
        *next_index = cursor;
        return {};
    }

    // 分析一条语句对字段状态的影响。
    CheckStatus AnalyzeStatement(
        std::size_t begin,
        std::size_t end,
        bool statement_complete,
        State* state
    ) const {
        const std::size_t first = Next(begin, end);
        if (first >= end) return {};
        if (tokens_[first].text == "return" || tokens_[first].text == "throw") {
            CheckStatus value = AnalyzeExpression(
                first + 1, end, statement_complete, state
            );
            if (!value.ok) return value;
            if (!statement_complete) return {};
            if (tokens_[first].text == "return") {
                for (const std::string& field : uninitialized_) {
                    if (!state->assigned.count(field)) {
                        return {false, "constructor returns before initializing field"};
                    }
                }
            }
            state->reachable = false;
            return {};
        }
        if (tokens_[first].text == "let" || tokens_[first].text == "var") {
            const std::size_t name_index = Next(first + 1, end);
            if (name_index >= end ||
                tokens_[name_index].kind != FieldFlowToken::Kind::Identifier) {
                return {};
            }
            std::size_t equal = name_index + 1;
            int paren = 0;
            int bracket = 0;
            for (; equal < end; ++equal) {
                if (tokens_[equal].text == "(") ++paren;
                else if (tokens_[equal].text == ")" && paren > 0) --paren;
                else if (tokens_[equal].text == "[") ++bracket;
                else if (tokens_[equal].text == "]" && bracket > 0) --bracket;
                else if (tokens_[equal].text == "=" && paren == 0 && bracket == 0) break;
            }
            if (equal < end) {
                CheckStatus initializer = AnalyzeExpression(
                    equal + 1, end, true, state
                );
                if (!initializer.ok) return initializer;
            }
            state->locals.insert(tokens_[name_index].text);
            return {};
        }

        const std::size_t delegation_open = Next(first + 1, end);
        if (tokens_[first].text == "this" && delegation_open < end &&
            tokens_[delegation_open].text == "(") {
            const auto delegation_close = MatchingToken(
                delegation_open, end, "(", ")"
            );
            CheckStatus arguments = AnalyzeExpression(
                delegation_open + 1, delegation_close.value_or(end),
                delegation_close.has_value(), state
            );
            if (!arguments.ok) return arguments;
            if (delegation_close) {
                state->assigned.insert(
                    uninitialized_.begin(), uninitialized_.end()
                );
            }
            return {};
        }

        std::size_t field_index = first;
        bool explicit_this = false;
        std::size_t equal = Next(field_index + 1, end);
        if (tokens_[field_index].text == "this" && equal < end &&
            tokens_[equal].text == ".") {
            field_index = Next(equal + 1, end);
            equal = field_index < end ? Next(field_index + 1, end) : end;
            explicit_this = true;
        }
        if (field_index < end &&
            tokens_[field_index].kind == FieldFlowToken::Kind::Identifier &&
            equal < end && tokens_[equal].text == "=" &&
            IsUninitializedRead(tokens_[field_index].text, *state, explicit_this)) {
            CheckStatus rhs = AnalyzeExpression(equal + 1, end, statement_complete, state);
            if (!rhs.ok) return rhs;
            if (Next(equal + 1, end) < end) {
                state->assigned.insert(tokens_[field_index].text);
            }
            return {};
        }
        return AnalyzeExpression(begin, end, statement_complete, state);
    }

    // 递归分析指定 token 范围内的代码块。
    CheckStatus AnalyzeBlock(
        std::size_t begin,
        std::size_t end,
        bool block_closed,
        State* state
    ) const {
        const auto outer_locals = state->locals;
        std::size_t cursor = begin;
        while ((cursor = Next(cursor, end)) < end) {
            if (!state->reachable) break;
            if (tokens_[cursor].text == ";") {
                ++cursor;
                continue;
            }
            if (tokens_[cursor].text == "if") {
                State after;
                std::size_t next = cursor + 1;
                CheckStatus status = AnalyzeIf(
                    cursor, end, block_closed, *state, &after, &next
                );
                if (!status.ok) return status;
                *state = std::move(after);
                cursor = std::max(next, cursor + 1);
                continue;
            }
            if (tokens_[cursor].text == "while" || tokens_[cursor].text == "for") {
                std::size_t next = cursor + 1;
                CheckStatus status = AnalyzeLoop(cursor, end, *state, &next);
                if (!status.ok) return status;
                cursor = std::max(next, cursor + 1);
                continue;
            }
            if (tokens_[cursor].text == "do") {
                State after;
                std::size_t next = cursor + 1;
                CheckStatus status = AnalyzeDoLoop(
                    cursor, end, *state, &after, &next
                );
                if (!status.ok) return status;
                *state = std::move(after);
                cursor = std::max(next, cursor + 1);
                continue;
            }
            if (tokens_[cursor].text == "match") {
                std::size_t next = cursor + 1;
                CheckStatus status = AnalyzeOpaqueMatch(
                    cursor, end, state, &next
                );
                if (!status.ok) return status;
                cursor = std::max(next, cursor + 1);
                continue;
            }
            if (tokens_[cursor].text == "try") {
                std::size_t next = cursor + 1;
                CheckStatus status = AnalyzeOpaqueTry(
                    cursor, end, state, &next
                );
                if (!status.ok) return status;
                cursor = std::max(next, cursor + 1);
                continue;
            }
            if (tokens_[cursor].text == "{") {
                const auto close = MatchingToken(cursor, end, "{", "}");
                State nested = *state;
                CheckStatus status = AnalyzeBlock(
                    cursor + 1, close.value_or(end), close.has_value(), &nested
                );
                if (!status.ok) return status;
                state->assigned = std::move(nested.assigned);
                state->reachable = nested.reachable;
                state->uncertain_control_flow = nested.uncertain_control_flow;
                cursor = close ? *close + 1 : end;
                continue;
            }
            const std::size_t statement_end = StatementEnd(cursor, end);
            const bool statement_complete = statement_end < end || block_closed;
            CheckStatus status = AnalyzeStatement(
                cursor, statement_end, statement_complete, state
            );
            if (!status.ok) return status;
            cursor = statement_end < end
                ? statement_end +
                    (ConsumesStatementBoundary(statement_end, end) ? 1 : 0)
                : end;
        }
        state->locals = outer_locals;
        return {};
    }

    std::vector<FieldFlowToken> tokens_;
    std::unordered_set<std::string> uninitialized_;
    State initial_;
};

// 提取构造器参数的名字集合（用于区分参数与字段）
std::unordered_set<std::string> ConstructorParameterNames(std::string_view parameters) {
    std::unordered_set<std::string> result;
    for (const std::string& raw : SplitTopLevel(parameters, ',')) {
        const std::size_t colon = FindTopLevel(raw, ":");
        const std::string name = Trim(std::string_view(raw).substr(0, colon));
        if (IsIdentifierText(name)) {
            result.insert(name);
        } else if (name.size() >= 3 && name.front() == '`' && name.back() == '`') {
            const std::string unquoted = name.substr(1, name.size() - 2);
            if (IsIdentifierText(unquoted)) result.insert(unquoted);
        }
    }
    return result;
}

// 检查构造器是否初始化了全部非默认字段（字段初始化完整性分析）
CheckStatus CheckConstructorFieldInitialization(std::string_view source) {
    static const std::regex class_pattern(
        R"(\bclass\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>{}()]*>)?[^{}]*\{)"
    );
    static const std::regex init_pattern(
        R"(\binit\s*\(([^{};]*?)\)\s*\{)"
    );
    static const std::regex delegated_pattern(R"(\bthis\s*\(([^()]*)\))" );
    if (source.find("class") == std::string_view::npos) return {};
    const std::string owned(source);
    const std::string masked = MaskNonCodeText(source);
    for (std::sregex_iterator cls(masked.begin(), masked.end(), class_pattern), end;
         cls != end; ++cls) {
        const std::size_t class_open = static_cast<std::size_t>(
            (*cls).position() + (*cls).length() - 1
        );
        const auto class_close = MatchingDelimiter(masked, class_open, '{', '}');
        const std::string body = owned.substr(
            class_open + 1,
            class_close ? *class_close - class_open - 1 : owned.size() - class_open - 1
        );
        const std::string masked_body = masked.substr(
            class_open + 1,
            class_close ? *class_close - class_open - 1 : masked.size() - class_open - 1
        );
        const auto fields = ScanTopLevelSourceFieldsMasked(masked_body);
        std::unordered_set<std::string> uninitialized;
        for (const auto& [name, field] : fields) {
            if (!field.is_static && !field.has_initializer) {
                uninitialized.insert(name);
            }
        }
        if (uninitialized.empty()) continue;

        struct ConstructorSummary {
            std::size_t required = 0;
            std::size_t maximum = 0;
            bool delegates = false;
            std::optional<std::size_t> delegated_argument_count;
        };
        bool saw_constructor = false;
        std::vector<ConstructorSummary> constructor_summaries;
        for (std::sregex_iterator init(masked_body.begin(), masked_body.end(), init_pattern), init_end;
             init != init_end; ++init) {
            const std::size_t position = static_cast<std::size_t>((*init).position());
            if (BraceDepthBefore(masked_body, position) != 0) continue;
            saw_constructor = true;
            const std::size_t init_open = position +
                static_cast<std::size_t>((*init).length()) - 1;
            const auto init_close = MatchingDelimiter(masked_body, init_open, '{', '}');
            const std::string init_body = body.substr(
                init_open + 1,
                init_close ? *init_close - init_open - 1 : body.size() - init_open - 1
            );
            ConstructorFieldFlowAnalyzer analyzer(
                init_body, uninitialized,
                ConstructorParameterNames((*init)[1].str())
            );
            ConstructorFieldFlowAnalyzer::State state;
            CheckStatus status = analyzer.Analyze(init_close.has_value(), &state);
            if (!status.ok) return status;
            if (!init_close) continue;
            const std::string masked_init_body = MaskNonCodeText(init_body);
            std::smatch delegation;
            const bool delegates = std::regex_search(
                masked_init_body, delegation, delegated_pattern
            );
            for (const std::string& field : uninitialized) {
                if (state.reachable && !state.uncertain_control_flow &&
                    !state.assigned.count(field)) {
                    return {false, "constructor does not initialize field"};
                }
            }
            ConstructorSummary summary;
            const std::vector<std::string> parameters = SplitTopLevel(
                (*init)[1].str(), ','
            );
            if (!(parameters.size() == 1 && parameters.front().empty())) {
                summary.maximum = parameters.size();
                for (const std::string& parameter : parameters) {
                    if (FindTopLevel(parameter, "=") == std::string::npos) {
                        ++summary.required;
                    }
                }
            }
            summary.delegates = delegates;
            if (delegates) {
                const std::vector<std::string> arguments = SplitTopLevel(
                    delegation[1].str(), ','
                );
                summary.delegated_argument_count =
                    arguments.size() == 1 && arguments.front().empty()
                        ? 0 : arguments.size();
            }
            constructor_summaries.push_back(std::move(summary));
        }
        if (class_close && !constructor_summaries.empty()) {
            std::vector<bool> reaches_direct(constructor_summaries.size(), false);
            bool has_direct = false;
            for (std::size_t index = 0; index < constructor_summaries.size(); ++index) {
                if (!constructor_summaries[index].delegates) {
                    reaches_direct[index] = true;
                    has_direct = true;
                }
            }
            bool changed = true;
            while (changed) {
                changed = false;
                for (std::size_t index = 0; index < constructor_summaries.size(); ++index) {
                    const ConstructorSummary& current = constructor_summaries[index];
                    if (!current.delegates || reaches_direct[index]) continue;
                    if (!current.delegated_argument_count) {
                        if (has_direct) {
                            reaches_direct[index] = true;
                            changed = true;
                        }
                        continue;
                    }
                    for (std::size_t target = 0;
                         target < constructor_summaries.size(); ++target) {
                        if (!reaches_direct[target]) continue;
                        const ConstructorSummary& candidate = constructor_summaries[target];
                        if (*current.delegated_argument_count >= candidate.required &&
                            *current.delegated_argument_count <= candidate.maximum) {
                            reaches_direct[index] = true;
                            changed = true;
                            break;
                        }
                    }
                }
            }
            for (std::size_t index = 0; index < constructor_summaries.size(); ++index) {
                if (constructor_summaries[index].delegates && !reaches_direct[index]) {
                    return {false, "constructor delegation has no initializing target"};
                }
            }
        }
        if (class_close && !saw_constructor) {
            return {false, "class field is never initialized"};
        }
    }
    return {};
}


}
