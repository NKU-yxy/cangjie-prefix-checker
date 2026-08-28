#include "semantic_control_flow.h"

#include "semantic_expression.h"
#include "semantic_text.h"
#include "semantic_types.h"

#include <algorithm>
#include <cctype>
#include <iostream>
#include <optional>
#include <regex>
#include <set>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace cangjie {

// 解析任意变量声明行（var/let 带类型或不带类型），返回声明信息
std::optional<AnyVariableDeclaration> ParseAnyVariableDeclaration(std::string_view line) {
    const std::string owned = Trim(line);
    std::size_t cursor = 0;
    if (StartsWith(owned, "let") && owned.size() > 3 &&
        std::isspace(static_cast<unsigned char>(owned[3]))) {
        cursor = 3;
    } else if (StartsWith(owned, "var") && owned.size() > 3 &&
               std::isspace(static_cast<unsigned char>(owned[3]))) {
        cursor = 3;
    } else {
        return std::nullopt;
    }
    while (cursor < owned.size() &&
           std::isspace(static_cast<unsigned char>(owned[cursor]))) ++cursor;
    const std::size_t name_start = cursor;
    if (cursor >= owned.size() || !IsIdentStart(static_cast<unsigned char>(owned[cursor]))) {
        return std::nullopt;
    }
    while (cursor < owned.size() &&
           IsIdentContinue(static_cast<unsigned char>(owned[cursor]))) ++cursor;
    const std::string name = owned.substr(name_start, cursor - name_start);
    while (cursor < owned.size() &&
           std::isspace(static_cast<unsigned char>(owned[cursor]))) ++cursor;

    std::string annotated_type;
    std::size_t assignment = std::string::npos;
    if (cursor < owned.size() && owned[cursor] == '=') {
        assignment = cursor;
    } else if (cursor < owned.size() && owned[cursor] == ':') {
        const std::size_t type_start = ++cursor;
        int paren = 0;
        int bracket = 0;
        int angle = 0;
        for (; cursor < owned.size(); ++cursor) {
            const char ch = owned[cursor];
            if (ch == '(') ++paren;
            else if (ch == ')' && paren > 0) --paren;
            else if (ch == '[') ++bracket;
            else if (ch == ']' && bracket > 0) --bracket;
            else if (ch == '<') ++angle;
            else if (ch == '>' && angle > 0) --angle;
            else if (ch == '=' && paren == 0 && bracket == 0 && angle == 0) {
                assignment = cursor;
                break;
            }
        }
        if (assignment == std::string::npos) return std::nullopt;
        annotated_type = CompactType(std::string_view(owned).substr(
            type_start, assignment - type_start
        ));
    } else {
        return std::nullopt;
    }
    return AnyVariableDeclaration{
        name,
        std::move(annotated_type),
        Trim(std::string_view(owned).substr(assignment + 1)),
    };
}

// 解析 "var 名字 = 值" 形式的变量声明，返回名字与初始化表达式
std::optional<std::pair<std::string, std::string>> ParseVariableDeclaration(
    std::string_view line
) {
    const auto declaration = ParseAnyVariableDeclaration(line);
    if (!declaration || declaration->annotated_type.empty()) return std::nullopt;
    return std::make_pair(declaration->annotated_type, declaration->expression);
}

// 解析赋值语句（目标 = 值），返回目标与右值表达式
std::optional<std::pair<std::string, std::string>> ParseReassignment(std::string_view line) {
    static const std::regex pattern(
        R"(^\s*(?:this\s*\.\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)\s*(.*)$)"
    );
    std::smatch match;
    const std::string owned(line);
    if (!std::regex_match(owned, match, pattern)) return std::nullopt;
    return std::make_pair(match[1].str(), Trim(match[2].str()));
}

// 判断一行是否以显式的 this 接收者开头（this.member 形式）
bool HasExplicitThisReceiver(std::string_view line) {
    static const std::regex pattern(R"(^\s*this\s*\.)");
    return std::regex_search(line.begin(), line.end(), pattern);
}

// 判断某类型上是否存在以 prefix 开头的成员名（未完成成员访问的续写试探）
bool HasMemberPrefix(const Model& model, const std::string& type, const std::string& prefix) {
    if (prefix.empty()) return true;
    const bool type_receiver = StartsWith(type, "type:");
    const std::string head = TypeHead(type);
    const auto found = model.nominals.find(head);
    if (found == model.nominals.end()) {
        if ((head == "Int64" || head == "Float64" || head == "Bool") &&
            StartsWith("toString", prefix)) {
            return true;
        }
        return false;
    }
    const NominalInfo& info = found->second;
    if (type_receiver) {
        for (const auto& field : info.static_fields) {
            if (StartsWith(field.first, prefix)) return true;
        }
        for (const auto& method : info.static_methods) {
            if (StartsWith(method.first, prefix)) return true;
        }
        return false;
    }
    for (const auto& field : info.fields) {
        if (StartsWith(field.first, prefix)) return true;
    }
    for (const auto& method : info.methods) {
        if (StartsWith(method.first, prefix)) return true;
    }
    return false;
}

// 检查赋值语句的目标是否为不可赋值的表达式（如字面量/函数调用）
bool HasInvalidAssignmentTarget(std::string_view line) {
    const std::string owned = Trim(MaskNonCodeText(line));
    if (StartsWith(owned, "let ") || StartsWith(owned, "var ")) return false;
    int paren = 0;
    int bracket = 0;
    int brace = 0;
    bool in_string = false;
    bool escaped = false;
    for (std::size_t index = 0; index < owned.size(); ++index) {
        const char ch = owned[index];
        if (in_string) {
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '"') in_string = true;
        else if (ch == '(') ++paren;
        else if (ch == ')' && paren > 0) --paren;
        else if (ch == '[') ++bracket;
        else if (ch == ']' && bracket > 0) --bracket;
        else if (ch == '{') ++brace;
        else if (ch == '}' && brace > 0) --brace;
        else if (ch == '=' && paren == 0 && bracket == 0 && brace == 0) {
            const char previous = index > 0 ? owned[index - 1] : '\0';
            const char next = index + 1 < owned.size() ? owned[index + 1] : '\0';
            if (next == '=' || next == '>' || previous == '=' || previous == '!' ||
                previous == '<' || previous == '>') {
                continue;
            }
            const std::string lhs = Trim(std::string_view(owned).substr(0, index));
            const std::string rhs = Trim(std::string_view(owned).substr(index + 1));
            if (rhs.empty()) return false;
            static const std::regex assignable(
                R"((?:this\.)?[A-Za-z_][A-Za-z0-9_]*(?:(?:\.[A-Za-z_][A-Za-z0-9_]*)|(?:\[[^\]]+\]))*)"
            );
            return !std::regex_match(lhs, assignable);
        }
    }
    return false;
}

// 提取源码中最后一个 if/while 的条件表达式
std::optional<std::string> LastCondition(std::string_view source, std::string_view keyword) {
    const std::string marker = std::string(keyword) + " (";
    std::size_t position = source.rfind(marker);
    if (position == std::string::npos) {
        position = source.rfind(std::string(keyword) + "(");
        if (position == std::string::npos) return std::nullopt;
    }
    const std::size_t open = source.find('(', position + keyword.size());
    if (open == std::string::npos) return std::nullopt;
    const auto close = MatchingDelimiter(source, open, '(', ')');
    if (close) return Trim(source.substr(open + 1, *close - open - 1));
    return std::nullopt;
}

// 判断当前是否位于循环体内（break/continue 上下文检查用）
bool InsideLoop(std::string_view body) {
    static const std::regex loop_pattern(R"(\b(?:for|while)\s*\([^{}]*\)\s*\{)");
    const std::string owned(body);
    for (std::sregex_iterator it(owned.begin(), owned.end(), loop_pattern), end; it != end; ++it) {
        const std::size_t open = static_cast<std::size_t>((*it).position() + (*it).length() - 1);
        if (!MatchingDelimiter(owned, open, '{', '}')) return true;
    }
    return false;
}

// 判断一个类型是否可迭代（for-in 源）
bool IsIterable(std::string_view type) {
    const std::string head = TypeHead(type);
    return head == "Array" || head == "ArrayList" || head == "HashSet" ||
           head == "ArrayStack" || head == "ArrayDeque" ||
           head == "KeysView" || head == "ValuesView" || head == "Range" ||
           type == "String";
}

// 提取可迭代类型的元素类型（Array<T> -> T）
std::string IterableElement(std::string_view type) {
    if (type == "String") return "Rune";
    const auto args = TypeArgs(type);
    return args.empty() ? "?" : args.front();
}

struct CompletedLoop {
    bool is_for = false;
    std::size_t keyword_start = 0;
    std::size_t condition_open = 0;
    std::size_t condition_close = 0;
    std::size_t body_open = 0;
    std::size_t body_close = 0;
};

// 跳过循环源码中的空白和行注释。
std::size_t SkipLoopLineTrivia(std::string_view source, std::size_t cursor) {
    while (cursor < source.size()) {
        while (cursor < source.size() &&
               std::isspace(static_cast<unsigned char>(source[cursor]))) {
            ++cursor;
        }
        if (cursor + 1 >= source.size()) break;
        if (source.substr(cursor, 2) == "/*") {
            int depth = 1;
            cursor += 2;
            while (cursor < source.size() && depth > 0) {
                if (cursor + 1 < source.size() &&
                    source.substr(cursor, 2) == "/*") {
                    ++depth;
                    cursor += 2;
                } else if (cursor + 1 < source.size() &&
                           source.substr(cursor, 2) == "*/") {
                    --depth;
                    cursor += 2;
                } else {
                    ++cursor;
                }
            }
            continue;
        }
        if (source.substr(cursor, 2) != "//") break;
        cursor += 2;
        while (cursor < source.size() && source[cursor] != '\n' &&
               source[cursor] != '\r') {
            ++cursor;
        }
    }
    return cursor;
}

// 找出源码中所有已闭合的 for 循环（含头、体与边界）
std::vector<CompletedLoop> FindCompletedLoops(std::string_view source) {
    std::vector<CompletedLoop> loops;
    bool in_string = false;
    bool triple_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    for (std::size_t index = 0; index < source.size(); ++index) {
        const char ch = source[index];
        const char next = index + 1 < source.size() ? source[index + 1] : '\0';
        if (line_comment) {
            if (ch == '\n' || ch == '\r') line_comment = false;
            continue;
        }
        if (block_comment_depth > 0) {
            if (ch == '/' && next == '*') {
                ++block_comment_depth;
                ++index;
            } else if (ch == '*' && next == '/') {
                --block_comment_depth;
                ++index;
            }
            continue;
        }
        if (in_string) {
            if (triple_string) {
                if (index + 2 < source.size() &&
                    source.substr(index, 3) == "\"\"\"") {
                    in_string = false;
                    triple_string = false;
                    index += 2;
                }
            } else if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '/' && next == '/') {
            line_comment = true;
            ++index;
            continue;
        }
        if (ch == '/' && next == '*') {
            block_comment_depth = 1;
            ++index;
            continue;
        }
        if (ch == '"') {
            triple_string = index + 2 < source.size() &&
                source.substr(index, 3) == "\"\"\"";
            in_string = true;
            if (triple_string) index += 2;
            continue;
        }
        if (!IsIdentStart(static_cast<unsigned char>(ch))) continue;
        std::size_t word_end = index + 1;
        while (word_end < source.size() &&
               IsIdentContinue(static_cast<unsigned char>(source[word_end]))) {
            ++word_end;
        }
        const std::string_view keyword = source.substr(index, word_end - index);
        if (keyword != "for" && keyword != "while") {
            index = word_end - 1;
            continue;
        }
        const std::size_t condition_open = SkipLoopLineTrivia(source, word_end);
        if (condition_open >= source.size() || source[condition_open] != '(') {
            index = word_end - 1;
            continue;
        }
        const auto condition_close = MatchingDelimiter(source, condition_open, '(', ')');
        if (!condition_close) continue;
        const std::size_t body_open = SkipLoopLineTrivia(source, *condition_close + 1);
        if (body_open >= source.size() || source[body_open] != '{') continue;
        const auto body_close = MatchingDelimiter(source, body_open, '{', '}');
        if (!body_close) continue;
        loops.push_back(CompletedLoop{
            keyword == "for", index, condition_open, *condition_close,
            body_open, *body_close
        });
        index = word_end - 1;
    }
    return loops;
}

// 删除循环文本中的注释并保留字符串内容。
std::string RemoveLoopComments(std::string_view text) {
    std::string result;
    result.reserve(text.size());
    bool in_string = false;
    bool triple_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    for (std::size_t index = 0; index < text.size(); ++index) {
        const char ch = text[index];
        const char next = index + 1 < text.size() ? text[index + 1] : '\0';
        if (line_comment) {
            if (ch == '\n' || ch == '\r') {
                line_comment = false;
                result.push_back(ch);
            }
            continue;
        }
        if (block_comment_depth > 0) {
            if (ch == '/' && next == '*') {
                ++block_comment_depth;
                ++index;
            } else if (ch == '*' && next == '/') {
                --block_comment_depth;
                ++index;
                if (block_comment_depth == 0) result.push_back(' ');
            }
            continue;
        }
        if (in_string) {
            result.push_back(ch);
            if (triple_string) {
                if (index + 2 < text.size() &&
                    text.substr(index, 3) == "\"\"\"") {
                    result.append("\"\"");
                    in_string = false;
                    triple_string = false;
                    index += 2;
                }
            } else if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '/' && next == '/') {
            line_comment = true;
            ++index;
            continue;
        }
        if (ch == '/' && next == '*') {
            block_comment_depth = 1;
            ++index;
            continue;
        }
        result.push_back(ch);
        if (ch == '"') {
            triple_string = index + 2 < text.size() &&
                text.substr(index, 3) == "\"\"\"";
            in_string = true;
            if (triple_string) {
                result.append("\"\"");
                index += 2;
            }
        }
    }
    return result;
}

// 判断当前位置后是否紧跟 else 分支。
bool FollowedByElse(std::string_view body, std::size_t cursor) {
    cursor = SkipLoopLineTrivia(body, cursor);
    return cursor < body.size() && StartsWithKeyword(body.substr(cursor), "else");
}

// 判断当前位置后是否紧跟循环后置条件。
bool FollowedByLoopPostfix(std::string_view body, std::size_t cursor) {
    cursor = SkipLoopLineTrivia(body, cursor);
    return cursor < body.size() && body[cursor] == '.';
}

// 判断闭合花括号后是否仍属于同一循环结构。
bool FollowedByLoopBraceContinuation(std::string_view body, std::size_t cursor) {
    cursor = SkipLoopLineTrivia(body, cursor);
    if (cursor >= body.size()) return false;
    const char ch = body[cursor];
    if (std::string_view(".([,+-*/%<>=&|?").find(ch) != std::string_view::npos) {
        return true;
    }
    return StartsWithKeyword(body.substr(cursor), "else") ||
        StartsWithKeyword(body.substr(cursor), "catch") ||
        StartsWithKeyword(body.substr(cursor), "finally");
}

// 按边界切分循环体中的顶层语句。
std::vector<std::string> TopLevelLoopStatements(std::string_view body) {
    std::size_t start = 0;
    std::vector<std::string> statements;
    int paren = 0;
    int bracket = 0;
    int brace = 0;
    bool in_string = false;
    bool triple_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    auto commit = [&](std::size_t end) {
        const std::string candidate = Trim(RemoveLoopComments(
            body.substr(start, end - start)
        ));
        if (!candidate.empty()) statements.push_back(candidate);
        start = end + 1;
    };
    auto commit_through = [&](std::size_t end_inclusive) {
        const std::string candidate = Trim(RemoveLoopComments(
            body.substr(start, end_inclusive - start + 1)
        ));
        if (!candidate.empty()) statements.push_back(candidate);
        start = end_inclusive + 1;
    };
    for (std::size_t index = 0; index < body.size(); ++index) {
        const char ch = body[index];
        const char next = index + 1 < body.size() ? body[index + 1] : '\0';
        if (line_comment) {
            if (ch == '\n' || ch == '\r') {
                line_comment = false;
                if (paren == 0 && bracket == 0 && brace == 0 &&
                    !FollowedByElse(body, index + 1) &&
                    !FollowedByLoopPostfix(body, index + 1)) {
                    commit(index);
                }
            }
            continue;
        }
        if (block_comment_depth > 0) {
            if (ch == '/' && next == '*') {
                ++block_comment_depth;
                ++index;
            } else if (ch == '*' && next == '/') {
                --block_comment_depth;
                ++index;
            }
            continue;
        }
        if (in_string) {
            if (triple_string) {
                if (index + 2 < body.size() &&
                    body.substr(index, 3) == "\"\"\"") {
                    in_string = false;
                    triple_string = false;
                    index += 2;
                }
            } else if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '/' && next == '/') {
            line_comment = true;
            ++index;
            continue;
        }
        if (ch == '/' && next == '*') {
            block_comment_depth = 1;
            ++index;
            continue;
        }
        if (ch == '"') {
            triple_string = index + 2 < body.size() &&
                body.substr(index, 3) == "\"\"\"";
            in_string = true;
            if (triple_string) index += 2;
        }
        else if (ch == '(') ++paren;
        else if (ch == ')' && paren > 0) --paren;
        else if (ch == '[') ++bracket;
        else if (ch == ']' && bracket > 0) --bracket;
        else if (ch == '{') ++brace;
        else if (ch == '}' && brace > 0) {
            --brace;
            const std::size_t next_statement = SkipLoopLineTrivia(body, index + 1);
            if (brace == 0 && paren == 0 && bracket == 0 &&
                next_statement < body.size() && body[next_statement] != '}' &&
                !FollowedByLoopBraceContinuation(body, index + 1)) {
                commit_through(index);
            }
        }
        else if (ch == ';' && paren == 0 && bracket == 0 && brace == 0) commit(index);
        else if ((ch == '\n' || ch == '\r') && paren == 0 && bracket == 0 &&
                 brace == 0 && !FollowedByElse(body, index + 1) &&
                 !FollowedByLoopPostfix(body, index + 1) &&
                 !ContinuesAfterNewline(body.substr(start, index - start))) {
            commit(index);
        }
    }
    const std::string tail = Trim(RemoveLoopComments(body.substr(start)));
    if (!tail.empty()) statements.push_back(tail);
    return statements;
}

// 判断语句是否以显式代码块结构开头。
bool IsExplicitBlockStatement(std::string_view statement) {
    const std::string owned = Trim(statement);
    if (owned.empty() || owned.front() != '{') return false;
    const auto close = MatchingDelimiter(owned, 0, '{', '}');
    if (!close || *close != owned.size() - 1) return false;
    const std::string_view inner(owned.data() + 1, owned.size() - 2);
    return FindTopLevel(inner, "=>") == std::string::npos;
}

// 收集指定位置前已经生效的顶层局部声明。
void CollectTopLevelDeclarationsBefore(
    std::string_view region,
    std::size_t end,
    const Model& model,
    FunctionContext* context,
    std::string_view full_source
) {
    end = std::min(end, region.size());
    for (const std::string& statement :
         TopLevelLoopStatements(region.substr(0, end))) {
        const auto declaration = ParseAnyVariableDeclaration(statement);
        if (!declaration) continue;
        ExpressionTyper typer(model, *context, full_source);
        ExprResult actual = typer.Infer(
            declaration->expression, declaration->annotated_type
        );
        if (!declaration->annotated_type.empty()) {
            context->variables[declaration->name] = declaration->annotated_type;
        } else if (actual.known && !actual.error) {
            context->variables[declaration->name] = actual.type;
        }
        if (StartsWithKeyword(statement, "let")) {
            context->immutable.insert(declaration->name);
        }
    }
}

// 返回嵌套结构之外所有空白位置。
std::vector<std::size_t> TopLevelSpacePositions(std::string_view text) {
    std::vector<std::size_t> positions;
    int paren = 0;
    int bracket = 0;
    int brace = 0;
    bool in_string = false;
    bool triple_string = false;
    bool escaped = false;
    for (std::size_t index = 0; index < text.size(); ++index) {
        const char ch = text[index];
        if (in_string) {
            if (triple_string) {
                if (index + 2 < text.size() &&
                    text.substr(index, 3) == "\"\"\"") {
                    in_string = false;
                    triple_string = false;
                    index += 2;
                }
            } else if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '"') {
            triple_string = index + 2 < text.size() &&
                text.substr(index, 3) == "\"\"\"";
            in_string = true;
            if (triple_string) index += 2;
        } else if (ch == '(') ++paren;
        else if (ch == ')' && paren > 0) --paren;
        else if (ch == '[') ++bracket;
        else if (ch == ']' && bracket > 0) --bracket;
        else if (ch == '{') ++brace;
        else if (ch == '}' && brace > 0) --brace;
        else if (std::isspace(static_cast<unsigned char>(ch)) &&
                 paren == 0 && bracket == 0 && brace == 0) {
            if (positions.empty() || positions.back() + 1 != index) {
                positions.push_back(index);
            }
        }
    }
    return positions;
}

// 判断文本是否为不可再拆分的原子表达式。
bool IsAtomExpression(std::string_view tail) {
    if (tail.empty()) return false;
    if (tail.front() == '"') {
        if (tail.size() >= 6 && tail.substr(0, 3) == "\"\"\"" &&
            tail.substr(tail.size() - 3) == "\"\"\"") {
            return true;
        }
        if (tail.size() >= 2 && tail.back() == '"') {
            bool escaped = false;
            for (std::size_t index = 1; index + 1 < tail.size(); ++index) {
                if (escaped) escaped = false;
                else if (tail[index] == '\\') escaped = true;
                else if (tail[index] == '"') return false;
            }
            return !escaped;
        }
        return false;
    }
    static const std::regex atom_pattern(
        R"(([A-Za-z_][A-Za-z0-9_]*)|(true|false)|(0[xXoObB][0-9A-Fa-f]+[A-Za-z0-9_]*)|([0-9]+(\.[0-9]+)?[A-Za-z0-9_]*))"
    );
    return std::regex_match(std::string(tail), atom_pattern);
}

// 判断文本是否以可继续扩展的 token 结束。
bool EndsWithIncompleteToken(std::string_view text) {
    static const std::vector<std::string> operators = {
        "+", "-", "*", "/", "%", "&&", "||", "==", "!=", "<", ">", "<=", ">=",
        "..", "..=", "=>", "=", "(", ".", "?", "??", "&", "|", "^", "<<", ">>"
    };
    const std::string trimmed = Trim(text);
    if (trimmed.empty()) return true;
    for (const std::string& op : operators) {
        if (trimmed.size() >= op.size() &&
            trimmed.compare(
                trimmed.size() - op.size(), op.size(), op
            ) == 0) {
            const std::size_t before = trimmed.size() - op.size();
            if (before == 0 || !IsIdentContinue(
                    static_cast<unsigned char>(trimmed[before - 1]))) {
                return true;
            }
        }
    }
    return false;
}

// 按顶层空白展开相邻的尾部原子表达式。
std::vector<std::string> ExpandTrailingAtoms(
    const std::string& statement,
    const Model& model,
    const FunctionContext& context,
    std::string_view full_source
) {
    std::vector<std::string> result = {statement};
    const std::vector<std::size_t> spaces = TopLevelSpacePositions(statement);
    if (spaces.empty()) return result;
    ExpressionTyper probe(model, context, full_source);
    for (auto it = spaces.rbegin(); it != spaces.rend(); ++it) {
        const std::string tail = Trim(
            std::string_view(statement).substr(*it + 1)
        );
        if (tail.empty() || tail.front() == '(' || tail.front() == '[') continue;
        if (!IsAtomExpression(tail)) continue;
        const std::string head = Trim(
            std::string_view(statement).substr(0, *it)
        );
        if (head.empty() || EndsWithIncompleteToken(head)) continue;
        bool head_ok = false;
        if (const auto assignment = ParseReassignment(head)) {
            const ExprResult rhs_result = probe.Infer(assignment->second);
            head_ok = rhs_result.known;
        } else {
            const ExprResult head_result = probe.Infer(head);
            head_ok = head_result.error || head_result.known;
        }
        if (head_ok) {
            if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
                std::cerr << "[ExpandTrailingAtoms] split '" << statement
                          << "' -> '" << head << "' | '" << tail << "'\n";
            }
            return {head, tail};
        }
    }
    return result;
}

// 递归检查已闭合的 for 循环：迭代源、绑定模式、break/continue 与 if 分支
CheckStatus CheckCompletedLoopsRecursive(
    std::string_view region,
    const Model& model,
    const FunctionContext& inherited_context,
    std::string_view full_source
);

// 检查循环体内的语句序列（类型推断与连续性）
CheckStatus CheckLoopStatementSequence(
    std::string_view body,
    const Model& model,
    FunctionContext loop_context,
    std::string_view full_source,
    bool require_unit_tail,
    ExprResult* tail_result
);

// 合并循环体内 if-else 两个分支的类型（分支合流推断）
ExprResult JoinLoopIfBranchTypes(
    const ExprResult& left,
    const ExprResult& right,
    const Model& model
) {
    if (!left.known || !right.known) return {};
    if (Compatible(left.type, right.type, model)) return right;
    if (Compatible(right.type, left.type, model)) return left;
    for (const auto& [name, nominal] : model.nominals) {
        if (!nominal.is_interface) continue;
        if (Compatible(left.type, name, model) &&
            Compatible(right.type, name, model)) {
            return {name, true, false, {}};
        }
    }
    return {"?", false, true, "if branch types cannot be joined"};
}

// 检查循环内 if 表达式（条件与分支类型）
CheckStatus CheckLoopIfExpression(
    std::string_view statement,
    const Model& model,
    const FunctionContext& context,
    std::string_view full_source,
    bool require_unit,
    ExprResult* expression_result
) {
    const std::string owned = Trim(statement);
    if (!StartsWithKeyword(owned, "if")) return {};
    std::size_t condition_open = owned.find('(', 2);
    if (condition_open == std::string::npos) return {};
    const auto condition_close = MatchingDelimiter(owned, condition_open, '(', ')');
    if (!condition_close) return {};
    ExpressionTyper condition_typer(model, context, full_source);
    ExprResult condition = condition_typer.Infer(
        std::string(std::string_view(owned).substr(
            condition_open + 1, *condition_close - condition_open - 1
        )),
        "Bool"
    );
    if (condition.error) return {false, condition.message};
    if (condition.known && !Compatible(condition.type, "Bool", model)) {
        return {false, "if condition must be Bool"};
    }

    const std::size_t then_open = SkipLoopLineTrivia(owned, *condition_close + 1);
    if (then_open >= owned.size() || owned[then_open] != '{') return {};
    const auto then_close = MatchingDelimiter(owned, then_open, '{', '}');
    if (!then_close) return {};
    ExprResult then_result;
    CheckStatus status = CheckLoopStatementSequence(
        std::string_view(owned).substr(
            then_open + 1, *then_close - then_open - 1
        ),
        model, context, full_source, require_unit, &then_result
    );
    if (!status.ok) return status;

    std::size_t cursor = SkipLoopLineTrivia(owned, *then_close + 1);
    if (cursor >= owned.size() ||
        !StartsWithKeyword(std::string_view(owned).substr(cursor), "else")) {
        if (expression_result) {
            *expression_result = {"Unit", true, false, {}};
        }
        return {};
    }
    cursor += 4;
    cursor = SkipLoopLineTrivia(owned, cursor);
    ExprResult else_result;
    if (cursor < owned.size() &&
        StartsWithKeyword(std::string_view(owned).substr(cursor), "if")) {
        status = CheckLoopIfExpression(
            std::string_view(owned).substr(cursor), model, context, full_source,
            require_unit, &else_result
        );
        if (!status.ok) return status;
    } else {
        if (cursor >= owned.size() || owned[cursor] != '{') return {};
        const auto else_close = MatchingDelimiter(owned, cursor, '{', '}');
        if (!else_close) return {};
        status = CheckLoopStatementSequence(
            std::string_view(owned).substr(cursor + 1, *else_close - cursor - 1),
            model, context, full_source, require_unit, &else_result
        );
        if (!status.ok) return status;
    }
    if (require_unit) {
        if (expression_result) {
            *expression_result = {"Unit", true, false, {}};
        }
        return {};
    }
    ExprResult joined = JoinLoopIfBranchTypes(then_result, else_result, model);
    if (joined.error) return {false, joined.message};
    if (expression_result) *expression_result = std::move(joined);
    return {};
}

// 检查循环体内的语句序列（类型推断与连续性）
CheckStatus CheckLoopStatementSequence(
    std::string_view body,
    const Model& model,
    FunctionContext loop_context,
    std::string_view full_source,
    bool require_unit_tail,
    ExprResult* tail_result
) {
    std::vector<std::string> statements;
    for (const std::string& statement : TopLevelLoopStatements(body)) {
        std::vector<std::string> expanded = ExpandTrailingAtoms(
            statement, model, loop_context, full_source
        );
        statements.insert(statements.end(), expanded.begin(), expanded.end());
    }
    ExprResult synthesized_tail{"Unit", true, false, {}};
    for (std::size_t index = 0; index < statements.size(); ++index) {
        const std::string& statement = statements[index];
        const bool is_last = index + 1 == statements.size();
        ExpressionTyper typer(model, loop_context, full_source);
        if (const auto declaration = ParseAnyVariableDeclaration(statement)) {
            ExprResult actual = typer.Infer(
                declaration->expression, declaration->annotated_type
            );
            if (actual.error) return {false, actual.message};
            if (!declaration->annotated_type.empty() && actual.known &&
                !Compatible(actual.type, declaration->annotated_type, model)) {
                return {false, "loop local initializer type mismatch"};
            }
            if (!declaration->annotated_type.empty()) {
                loop_context.variables[declaration->name] = declaration->annotated_type;
            } else if (actual.known) {
                loop_context.variables[declaration->name] = actual.type;
            }
            if (StartsWithKeyword(statement, "let")) {
                loop_context.immutable.insert(declaration->name);
            }
            synthesized_tail = {"Unit", true, false, {}};
            continue;
        }
        if (const auto assignment = ParseReassignment(statement)) {
            const auto expected = loop_context.variables.find(assignment->first);
            if (expected != loop_context.variables.end()) {
                ExprResult actual = typer.Infer(assignment->second, expected->second);
                if (actual.error) return {false, actual.message};
                if (actual.known && !Compatible(actual.type, expected->second, model)) {
                    return {false, "loop assignment type mismatch"};
                }
            }
            synthesized_tail = {"Unit", true, false, {}};
            continue;
        }

        if (StartsWithKeyword(statement, "if")) {
            CheckStatus branch = CheckLoopIfExpression(
                statement, model, loop_context, full_source,
                require_unit_tail && is_last, &synthesized_tail
            );
            if (!branch.ok) return branch;
            continue;
        }
        if (IsExplicitBlockStatement(statement)) {
            const std::string owned = Trim(statement);
            ExprResult block_result;
            CheckStatus block = CheckLoopStatementSequence(
                std::string_view(owned).substr(1, owned.size() - 2),
                model, loop_context, full_source,
                require_unit_tail && is_last, &block_result
            );
            if (!block.ok) return block;
            synthesized_tail = std::move(block_result);
            continue;
        }
        if (StartsWithKeyword(statement, "while") ||
            StartsWithKeyword(statement, "for")) {
            CheckStatus nested = CheckCompletedLoopsRecursive(
                statement, model, loop_context, full_source
            );
            if (!nested.ok) return nested;
            synthesized_tail = {"Unit", true, false, {}};
            continue;
        }
        if (statement == "break" || statement == "continue" ||
            statement == "return" || StartsWith(statement, "return ") ||
            IsUnfinishedKeywordPrefix(statement)) {
            synthesized_tail = {"Unit", true, false, {}};
            continue;
        }

        CheckStatus nested = CheckCompletedLoopsRecursive(
            statement, model, loop_context, full_source
        );
        if (!nested.ok) return nested;
        const std::string expected = require_unit_tail && is_last
            ? "Unit" : std::string{};
        ExprResult result = typer.Infer(statement, expected);
        if (result.error) return {false, result.message};
        if (require_unit_tail && is_last && result.known &&
            !Compatible(result.type, "Unit", model)) {
            return {false, "loop body must end with Unit"};
        }
        synthesized_tail = std::move(result);
    }
    if (tail_result) *tail_result = std::move(synthesized_tail);
    return {};
}

// 查找条件最外层的 in 关键字及其边界。
std::optional<std::pair<std::size_t, std::size_t>> FindTopLevelInKeyword(
    std::string_view condition
) {
    int paren = 0;
    int bracket = 0;
    int brace = 0;
    int angle = 0;
    bool in_string = false;
    bool triple_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    for (std::size_t index = 0; index < condition.size(); ++index) {
        const char ch = condition[index];
        const char next = index + 1 < condition.size() ? condition[index + 1] : '\0';
        if (line_comment) {
            if (ch == '\n' || ch == '\r') line_comment = false;
            continue;
        }
        if (block_comment_depth > 0) {
            if (ch == '/' && next == '*') {
                ++block_comment_depth;
                ++index;
            } else if (ch == '*' && next == '/') {
                --block_comment_depth;
                ++index;
            }
            continue;
        }
        if (in_string) {
            if (triple_string) {
                if (index + 2 < condition.size() &&
                    condition.substr(index, 3) == "\"\"\"") {
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
            line_comment = true;
            ++index;
            continue;
        }
        if (ch == '/' && next == '*') {
            block_comment_depth = 1;
            ++index;
            continue;
        }
        if (ch == '"') {
            triple_string = index + 2 < condition.size() &&
                condition.substr(index, 3) == "\"\"\"";
            in_string = true;
            if (triple_string) index += 2;
            continue;
        }
        if (ch == '(') ++paren;
        else if (ch == ')' && paren > 0) --paren;
        else if (ch == '[') ++bracket;
        else if (ch == ']' && bracket > 0) --bracket;
        else if (ch == '{') ++brace;
        else if (ch == '}' && brace > 0) --brace;
        else if (ch == '<') ++angle;
        else if (ch == '>' && angle > 0) --angle;
        if (paren != 0 || bracket != 0 || brace != 0 || angle != 0 ||
            !IsIdentStart(static_cast<unsigned char>(ch))) {
            continue;
        }
        std::size_t word_end = index + 1;
        while (word_end < condition.size() &&
               IsIdentContinue(static_cast<unsigned char>(condition[word_end]))) {
            ++word_end;
        }
        if (condition.substr(index, word_end - index) == "in") {
            return std::make_pair(index, word_end);
        }
        index = word_end - 1;
    }
    return std::nullopt;
}

// 递归检查已闭合的 for 循环：迭代源、绑定模式、break/continue 与 if 分支
CheckStatus CheckCompletedLoopsRecursive(
    std::string_view region,
    const Model& model,
    const FunctionContext& inherited_context,
    std::string_view full_source
) {
    const std::vector<CompletedLoop> loops = FindCompletedLoops(region);
    for (std::size_t index = 0; index < loops.size(); ++index) {
        const CompletedLoop& loop = loops[index];
        bool nested_in_another_loop = false;
        for (std::size_t outer_index = 0; outer_index < loops.size(); ++outer_index) {
            if (outer_index == index) continue;
            const CompletedLoop& outer = loops[outer_index];
            if (outer.body_open < loop.condition_open &&
                loop.body_close < outer.body_close) {
                nested_in_another_loop = true;
                break;
            }
        }
        if (nested_in_another_loop) continue;

        FunctionContext loop_context = inherited_context;
        CollectTopLevelDeclarationsBefore(
            region, loop.keyword_start, model, &loop_context, full_source
        );
        if (loop.is_for) {
            const std::string condition = std::string(region.substr(
                loop.condition_open + 1,
                loop.condition_close - loop.condition_open - 1
            ));
            const auto in_keyword = FindTopLevelInKeyword(condition);
            if (in_keyword) {
                const std::string binding = Trim(RemoveLoopComments(
                    std::string_view(condition).substr(0, in_keyword->first)
                ));
                const std::string iterable_text = Trim(RemoveLoopComments(
                    std::string_view(condition).substr(in_keyword->second)
                ));
                ExpressionTyper outer_typer(model, loop_context, full_source);
                ExprResult iterable = outer_typer.Infer(iterable_text);
                if (iterable.error) return {false, iterable.message};
                if (IsIdentifierText(binding)) {
                    if (iterable.known && TypeHead(iterable.type) == "HashMap") {
                        const auto args = TypeArgs(iterable.type);
                        loop_context.variables[binding] = args.size() >= 2
                            ? "(" + args[0] + "," + args[1] + ")" : "?";
                    } else if (iterable.known) {
                        loop_context.variables[binding] = IterableElement(iterable.type);
                    } else {
                        loop_context.variables[binding] = "?";
                    }
                    loop_context.immutable.insert(binding);
                }
            }
        }
        const std::string_view loop_body = region.substr(
            loop.body_open + 1, loop.body_close - loop.body_open - 1
        );
        CheckStatus status = CheckLoopStatementSequence(
            loop_body, model, std::move(loop_context), full_source, true, nullptr
        );
        if (!status.ok) return status;
    }
    return {};
}

// 逐个递归检查函数体中所有已闭合循环。
CheckStatus CheckCompletedLoopBodies(
    std::string_view function_body,
    const Model& model,
    const FunctionContext& function_context,
    std::string_view full_source
) {
    FunctionContext lexical_context = function_context;
    lexical_context.variables = function_context.entry_variables;
    lexical_context.immutable = function_context.entry_immutable;
    return CheckCompletedLoopsRecursive(
        function_body, model, lexical_context, full_source
    );
}

// 检查函数参数是否存在重名
CheckStatus CheckDuplicateParameter(std::string_view source) {
    const std::size_t func = source.rfind("func ");
    if (func == std::string::npos) return {};
    const std::size_t last_open = source.rfind('{');
    const std::size_t last_close = source.rfind('}');
    const std::size_t last_body_boundary = last_open == std::string::npos
        ? last_close : last_close == std::string::npos ? last_open : std::max(last_open, last_close);
    if (last_body_boundary != std::string::npos && func < last_body_boundary) return {};
    const std::size_t open = source.find('(', func);
    if (open == std::string::npos) return {};
    const auto close = MatchingDelimiter(source, open, '(', ')');
    const std::size_t end = close.value_or(source.size());
    const std::string params = std::string(source.substr(open + 1, end - open - (close ? 1 : 0)));
    std::unordered_set<std::string> seen;
    for (const std::string& param : SplitTopLevel(params, ',')) {
        const std::size_t colon = param.find(':');
        if (colon == std::string::npos) continue;
        std::string name = Trim(std::string_view(param).substr(0, colon));
        if (!name.empty() && name.back() == '!') name.pop_back();
        if (!name.empty() && !seen.insert(name).second) {
            return {false, "duplicate parameter"};
        }
    }
    return {};
}

// 判断文本能否扩展为已知类型或类型参数。
bool HasKnownTypePrefix(
    std::string_view prefix,
    const Model& model,
    const std::unordered_set<std::string>& type_parameters
) {
    static const std::vector<std::string> primitive_types = {
        "Int8", "Int16", "Int32", "Int64", "Float32", "Float64",
        "Bool", "Rune", "Unit"
    };
    if (prefix.empty()) return true;
    for (const std::string& name : primitive_types) {
        if (StartsWith(name, prefix)) return true;
    }
    for (const std::string& name : type_parameters) {
        if (StartsWith(name, prefix)) return true;
    }
    for (const auto& [name, _] : model.nominals) {
        if (StartsWith(name, prefix)) return true;
    }
    return false;
}

// 检查类/接口成员（字段、方法、构造器）是否存在重名
CheckStatus CheckClassMemberNameCollisions(std::string_view source) {
    static const std::regex class_pattern(
        R"(\bclass\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>{}()]*>)?[^{}]*\{)"
    );
    const std::string owned = MaskNonCodeText(source);
    for (std::sregex_iterator cls(owned.begin(), owned.end(), class_pattern), end;
         cls != end; ++cls) {
        const std::size_t open = static_cast<std::size_t>(
            (*cls).position() + (*cls).length() - 1
        );
        const auto close = MatchingDelimiter(owned, open, '{', '}');
        const std::string body = owned.substr(
            open + 1,
            close ? *close - open - 1 : owned.size() - open - 1
        );
        std::vector<std::string> ordered_fields;
        std::vector<std::string> ordered_methods;
        (void)ScanTopLevelSourceFieldsMasked(
            body, &ordered_fields, &ordered_methods
        );
        std::unordered_set<std::string> fields;
        for (const std::string& field : ordered_fields) {
            if (!fields.insert(field).second) {
                return {false, "duplicate class field"};
            }
        }
        for (const std::string& method : ordered_methods) {
            if (fields.count(method)) {
                return {false, "class member name collision"};
            }
        }
    }
    return {};
}

// 查找源码类中指定顶层字段的类型。
std::string TopLevelSourceFieldType(
    std::string_view source,
    const DeclarationSnapshot& snapshot,
    std::string_view class_name,
    std::string_view field_name
) {
    for (const DeclarationRecord& cls : snapshot.broad_classes) {
        if (SnapshotCaptureAt(cls, 1).text != class_name) continue;
        const std::size_t class_end = cls.close.value_or(source.size());
        if (cls.open >= class_end || class_end > source.size()) continue;
        const std::string body = std::string(source.substr(
            cls.open + 1, class_end - cls.open - 1
        ));
        const auto fields = ScanTopLevelSourceFields(body);
        const auto field = fields.find(std::string(field_name));
        if (field != fields.end() && !field->second.is_static) {
            return field->second.type;
        }
    }
    return {};
}

// 切分仅以空白相邻的多条简单赋值。
std::vector<std::string> SplitAdjacentSimpleAssignments(
    std::string_view statement
) {
    const std::string masked = MaskNonCodeText(statement);
    std::vector<std::size_t> starts;
    int paren = 0;
    int bracket = 0;
    int brace = 0;
    for (std::size_t index = 0; index < masked.size(); ++index) {
        const char ch = masked[index];
        if (paren == 0 && bracket == 0 && brace == 0 &&
            IsIdentStart(static_cast<unsigned char>(ch)) &&
            (index == 0 || !IsIdentContinue(
                static_cast<unsigned char>(masked[index - 1])))) {
            std::size_t word_end = index + 1;
            while (word_end < masked.size() && IsIdentContinue(
                    static_cast<unsigned char>(masked[word_end]))) {
                ++word_end;
            }
            std::size_t previous = index;
            while (previous > 0 && std::isspace(
                    static_cast<unsigned char>(masked[previous - 1]))) {
                --previous;
            }
            const bool member_suffix = previous > 0 && masked[previous - 1] == '.';
            std::size_t cursor = word_end;
            if (!member_suffix && masked.substr(index, word_end - index) == "this") {
                while (cursor < masked.size() &&
                       std::isspace(static_cast<unsigned char>(masked[cursor]))) {
                    ++cursor;
                }
                if (cursor < masked.size() && masked[cursor] == '.') {
                    ++cursor;
                    while (cursor < masked.size() && std::isspace(
                            static_cast<unsigned char>(masked[cursor]))) {
                        ++cursor;
                    }
                    if (cursor < masked.size() && IsIdentStart(
                            static_cast<unsigned char>(masked[cursor]))) {
                        ++cursor;
                        while (cursor < masked.size() && IsIdentContinue(
                                static_cast<unsigned char>(masked[cursor]))) {
                            ++cursor;
                        }
                    }
                }
            }
            while (cursor < masked.size() && std::isspace(
                    static_cast<unsigned char>(masked[cursor]))) {
                ++cursor;
            }
            if (!member_suffix && cursor < masked.size() && masked[cursor] == '=' &&
                (cursor + 1 == masked.size() ||
                 (masked[cursor + 1] != '=' && masked[cursor + 1] != '>'))) {
                starts.push_back(index);
            }
        }
        if (ch == '(') ++paren;
        else if (ch == ')' && paren > 0) --paren;
        else if (ch == '[') ++bracket;
        else if (ch == ']' && bracket > 0) --bracket;
        else if (ch == '{') ++brace;
        else if (ch == '}' && brace > 0) --brace;
    }
    if (starts.size() < 2 || !Trim(std::string_view(masked).substr(
            0, starts.front())).empty()) {
        return {};
    }
    std::vector<std::string> assignments;
    assignments.reserve(starts.size());
    for (std::size_t index = 0; index < starts.size(); ++index) {
        const std::size_t end = index + 1 < starts.size()
            ? starts[index + 1] : statement.size();
        assignments.push_back(Trim(statement.substr(starts[index], end - starts[index])));
    }
    return assignments;
}

// 检查一段连续的简单赋值语句序列（目标合法性与类型一致性）
CheckStatus CheckCompletedSimpleAssignmentSequence(
    std::string_view statement,
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot,
    const FunctionContext& context
) {
    if (context.class_name.empty()) return {};
    const std::vector<std::string> assignments =
        SplitAdjacentSimpleAssignments(statement);
    if (assignments.empty()) return {};
    ExpressionTyper typer(model, context, source);
    for (const std::string& text : assignments) {
        const auto assignment = ParseReassignment(text);
        if (!assignment) continue;
        const bool explicit_this = HasExplicitThisReceiver(text);
        if (!explicit_this && context.immutable.count(assignment->first)) {
            return {false, "assignment to let"};
        }
        std::string expected;
        if (explicit_this) {
            expected = TopLevelSourceFieldType(
                source, snapshot, context.class_name, assignment->first
            );
        } else if (const auto found = context.variables.find(assignment->first);
                   found != context.variables.end()) {
            expected = found->second;
        }
        if (expected.empty()) continue;
        ExprResult actual = typer.Infer(assignment->second, expected);
        if (actual.error) return {false, actual.message};
        if (actual.known && !Compatible(actual.type, expected, model)) {
            return {false, "assignment type mismatch"};
        }
    }
    return {};
}


// 判断语句是否以需要续行的操作符结尾（=、=>、+ 等）
bool ContinuesAfterNewline(std::string_view statement) {
    const std::string trimmed = Trim(statement);
    if (trimmed.empty()) return false;
    static const std::vector<std::string> suffixes = {
        "=", "=>", "+", "-", "*", "/", "%", "==", "!=", "<", ">",
        "<=", ">=", "&&", "||", "..", "..=", ",", ":", ".", "<:"
    };
    return std::any_of(suffixes.begin(), suffixes.end(), [&](const std::string& suffix) {
        return trimmed.size() >= suffix.size() &&
            trimmed.compare(trimmed.size() - suffix.size(), suffix.size(), suffix) == 0;
    });
}


// 判断一行文本能否作为一条语句的开头（保守试探）
bool IsStatementPrefix(std::string_view line) {
    static const std::vector<std::string> keywords = {
        "if", "else", "while", "for", "return", "let", "var", "break",
        "continue", "func", "class", "interface", "public", "private",
        "static", "init", "import", "package"
    };
    const std::string trimmed = Trim(line);
    if (trimmed.empty() || trimmed == "{" || trimmed == "}") return true;
    for (const std::string& keyword : {"let", "var", "func", "class", "interface",
                                      "public", "private", "static", "init", "import",
                                      "package", "else"}) {
        if (StartsWith(trimmed, keyword + " ") || StartsWith(trimmed, keyword + "(")) return true;
    }
    for (const std::string& keyword : keywords) {
        if (StartsWith(keyword, trimmed)) return true;
    }
    return false;
}

// 判断一行是否为未写完的关键字前缀（如 "ret" 可能是 "return"）
bool IsUnfinishedKeywordPrefix(std::string_view line) {
    static const std::vector<std::string> keywords = {
        "if", "else", "while", "for", "return", "let", "var", "break",
        "continue", "func", "class", "interface", "public", "private",
        "static", "init", "import", "package"
    };
    const std::string trimmed = Trim(line);
    if (trimmed.empty() || trimmed == "{" || trimmed == "}") return true;
    const bool whole_word = IsIdentifierText(trimmed);
    for (const std::string& keyword : keywords) {
        if (StartsWith(keyword, trimmed)) {
            if (whole_word && trimmed != keyword) continue;
            return true;
        }
    }
    return false;
}



}
