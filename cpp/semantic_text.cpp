#include "semantic_text.h"

#include <algorithm>
#include <cctype>

namespace cangjie {

// 判断字符能否作为标识符首字符。
bool IsIdentStart(unsigned char ch) {
    return std::isalpha(ch) || ch == '_';
}

// 判断字符能否作为标识符后续字符。
bool IsIdentContinue(unsigned char ch) {
    return std::isalnum(ch) || ch == '_';
}

// 判断文本是否为普通标识符。
bool IsIdentifierText(std::string_view text) {
    if (text.empty() || !IsIdentStart(static_cast<unsigned char>(text.front()))) return false;
    return std::all_of(text.begin() + 1, text.end(), [](unsigned char ch) {
        return IsIdentContinue(ch);
    });
}

// 判断文本是否包含独立的 var 或 let 关键字。
bool HasBareVarLetKeyword(std::string_view text) {
    for (std::size_t index = 0; index + 3 <= text.size(); ++index) {
        const bool is_var = text[index] == 'v' && text[index + 1] == 'a' && text[index + 2] == 'r';
        const bool is_let = text[index] == 'l' && text[index + 1] == 'e' && text[index + 2] == 't';
        if (!is_var && !is_let) continue;
        if (index > 0 && IsIdentContinue(static_cast<unsigned char>(text[index - 1]))) continue;
        if (index + 3 < text.size() &&
            IsIdentContinue(static_cast<unsigned char>(text[index + 3]))) {
            continue;
        }
        return true;
    }
    return false;
}

// 判断 var 或 let 关键字后是否已出现声明名称。
bool HasDeclNameAfterKeyword(std::string_view text) {
    for (std::size_t index = 0; index + 3 <= text.size(); ++index) {
        const bool is_var = text[index] == 'v' && text[index + 1] == 'a' && text[index + 2] == 'r';
        const bool is_let = text[index] == 'l' && text[index + 1] == 'e' && text[index + 2] == 't';
        if (!is_var && !is_let) continue;
        if (index > 0 && IsIdentContinue(static_cast<unsigned char>(text[index - 1]))) continue;
        if (index + 3 < text.size() &&
            IsIdentContinue(static_cast<unsigned char>(text[index + 3]))) {
            continue;
        }
        std::size_t cursor = index + 3;
        while (cursor < text.size() &&
               (text[cursor] == ' ' || text[cursor] == '\t')) {
            ++cursor;
        }
        if (cursor < text.size()) {
            return IsIdentStart(static_cast<unsigned char>(text[cursor]));
        }
        return false;
    }
    return false;
}

// 判断文本是否只包含十进制数字。
bool IsDecimalIntegerText(std::string_view text) {
    return !text.empty() && std::all_of(text.begin(), text.end(), [](unsigned char ch) {
        return std::isdigit(ch);
    });
}

// 判断文本是否为简单十进制整数或小数。
bool IsDecimalNumberText(std::string_view text) {
    if (text.empty()) return false;
    bool saw_digit = false;
    bool saw_dot = false;
    for (unsigned char ch : text) {
        if (std::isdigit(ch)) {
            saw_digit = true;
        } else if (ch == '.' && !saw_dot) {
            saw_dot = true;
        } else {
            return false;
        }
    }
    return saw_digit && text.front() != '.';
}

// 判断文本是否为带可选整数后缀的二、八或十六进制整数。
bool IsBasedIntegerText(std::string_view text) {
    if (text.size() < 3 || text.front() != '0') return false;
    const char marker = text[1];
    // 按进制前缀判断单个数字是否合法。
    auto valid_digit = [marker](unsigned char ch) {
        if (marker == 'x' || marker == 'X') return std::isxdigit(ch) != 0;
        if (marker == 'o' || marker == 'O') return ch >= '0' && ch <= '7';
        if (marker == 'b' || marker == 'B') return ch == '0' || ch == '1';
        return false;
    };
    if (marker != 'x' && marker != 'X' && marker != 'o' && marker != 'O' &&
        marker != 'b' && marker != 'B') {
        return false;
    }
    std::size_t end = text.size();
    // 仓颉整数类型后缀不会参与进制数字校验。
    static const std::vector<std::string_view> suffixes = {
        "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"
    };
    for (const std::string_view suffix : suffixes) {
        if (text.size() > suffix.size() &&
            text.substr(text.size() - suffix.size()) == suffix) {
            end -= suffix.size();
            break;
        }
    }
    return end > 2 && std::all_of(
        text.begin() + 2, text.begin() + static_cast<std::ptrdiff_t>(end),
        valid_digit
    );
}

// 判断文本是否以指定前缀开头。
bool StartsWith(std::string_view text, std::string_view prefix) {
    return text.size() >= prefix.size() && text.substr(0, prefix.size()) == prefix;
}

// 判断文本是否以完整关键字开头。
bool StartsWithKeyword(std::string_view text, std::string_view keyword) {
    return StartsWith(text, keyword) &&
        (text.size() == keyword.size() ||
         !IsIdentContinue(static_cast<unsigned char>(text[keyword.size()])));
}

// 去掉文本首尾的空白字符。
std::string Trim(std::string_view input) {
    std::size_t first = 0;
    while (first < input.size() && std::isspace(static_cast<unsigned char>(input[first]))) {
        ++first;
    }
    std::size_t last = input.size();
    while (last > first && std::isspace(static_cast<unsigned char>(input[last - 1]))) {
        --last;
    }
    return std::string(input.substr(first, last - first));
}

// 按分隔符切分顶层文本，不切开括号、尖括号或字符串内部内容。
std::vector<std::string> SplitTopLevel(std::string_view input, char separator) {
    std::vector<std::string> parts;
    std::size_t start = 0;
    int paren = 0;
    int bracket = 0;
    int brace = 0;
    int angle = 0;
    bool in_string = false;
    bool escaped = false;
    for (std::size_t index = 0; index < input.size(); ++index) {
        const char ch = input[index];
        if (in_string) {
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '"') in_string = true;
        else if (ch == '(') ++paren;
        else if (ch == ')') --paren;
        else if (ch == '[') ++bracket;
        else if (ch == ']') --bracket;
        else if (ch == '{') ++brace;
        else if (ch == '}') --brace;
        else if (ch == '<') ++angle;
        else if (ch == '>' && angle > 0) --angle;
        else if (ch == separator && paren == 0 && bracket == 0 && brace == 0 && angle == 0) {
            parts.emplace_back(Trim(input.substr(start, index - start)));
            start = index + 1;
        }
    }
    parts.emplace_back(Trim(input.substr(start)));
    return parts;
}

// 查找与给定开放定界符匹配的闭合位置。
std::optional<std::size_t> MatchingDelimiter(
    std::string_view text,
    std::size_t open,
    char opening,
    char closing
) {
    if (open >= text.size() || text[open] != opening) return std::nullopt;
    int depth = 0;
    bool in_string = false;
    bool triple_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment = 0;
    for (std::size_t index = open; index < text.size(); ++index) {
        const char ch = text[index];
        const char next = index + 1 < text.size() ? text[index + 1] : '\0';
        if (line_comment) {
            if (ch == '\n' || ch == '\r') line_comment = false;
            continue;
        }
        if (block_comment > 0) {
            if (ch == '/' && next == '*') {
                ++block_comment;
                ++index;
            } else if (ch == '*' && next == '/') {
                --block_comment;
                ++index;
            }
            continue;
        }
        if (in_string) {
            if (triple_string) {
                if (index + 2 < text.size() && text.substr(index, 3) == "\"\"\"") {
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
            block_comment = 1;
            ++index;
            continue;
        }
        if (ch == '"') {
            triple_string = index + 2 < text.size() && text.substr(index, 3) == "\"\"\"";
            in_string = true;
            if (triple_string) index += 2;
        } else if (ch == opening) {
            ++depth;
        } else if (ch == closing && --depth == 0) {
            return index;
        }
    }
    return std::nullopt;
}

// 在括号、尖括号和字符串之外查找指定子串。
std::size_t FindTopLevel(std::string_view input, std::string_view needle) {
    int paren = 0;
    int bracket = 0;
    int brace = 0;
    int angle = 0;
    bool in_string = false;
    bool escaped = false;
    for (std::size_t index = 0; index + needle.size() <= input.size(); ++index) {
        const char ch = input[index];
        if (in_string) {
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '"') {
            in_string = true;
            continue;
        }
        if (ch == '(') ++paren;
        else if (ch == ')') --paren;
        else if (ch == '[') ++bracket;
        else if (ch == ']') --bracket;
        else if (ch == '{') ++brace;
        else if (ch == '}') --brace;
        else if (ch == '<') ++angle;
        else if (ch == '>' && angle > 0) --angle;
        if (paren == 0 && bracket == 0 && brace == 0 && angle == 0 &&
            input.substr(index, needle.size()) == needle) {
            return index;
        }
    }
    return std::string_view::npos;
}

// 用空格遮蔽字符串和注释，同时保留换行及字节位置。
std::string MaskNonCodeText(std::string_view text) {
    std::string masked(text);
    bool in_string = false;
    bool in_multi_line_string = false;
    char quote = '\0';
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    for (std::size_t index = 0; index < masked.size(); ++index) {
        const char ch = text[index];
        const char next = index + 1 < text.size() ? text[index + 1] : '\0';
        if (line_comment) {
            if (ch == '\n' || ch == '\r') {
                line_comment = false;
            } else {
                masked[index] = ' ';
            }
            continue;
        }
        if (block_comment_depth > 0) {
            if (ch == '/' && next == '*') {
                masked[index] = masked[index + 1] = ' ';
                ++block_comment_depth;
                ++index;
            } else if (ch == '*' && next == '/') {
                masked[index] = masked[index + 1] = ' ';
                --block_comment_depth;
                ++index;
            } else if (ch != '\n' && ch != '\r') {
                masked[index] = ' ';
            }
            continue;
        }
        if (in_string) {
            if (in_multi_line_string) {
                if (ch != '\n' && ch != '\r') masked[index] = ' ';
                if (escaped) {
                    escaped = false;
                } else if (ch == '\\') {
                    escaped = true;
                } else if (ch == '"' && next == '"' &&
                           index + 2 < text.size() && text[index + 2] == '"') {
                    masked[index] = masked[index + 1] = masked[index + 2] = ' ';
                    index += 2;
                    in_string = false;
                    in_multi_line_string = false;
                }
                continue;
            }
            if (ch != '\n' && ch != '\r') masked[index] = ' ';
            if (escaped) {
                escaped = false;
            } else if (ch == '\\') {
                escaped = true;
            } else if (ch == quote) {
                in_string = false;
            }
            continue;
        }
        if (ch == '/' && next == '/') {
            masked[index] = masked[index + 1] = ' ';
            line_comment = true;
            ++index;
        } else if (ch == '/' && next == '*') {
            masked[index] = masked[index + 1] = ' ';
            block_comment_depth = 1;
            ++index;
        } else if (ch == '"' && next == '"' && index + 2 < text.size() &&
                   text[index + 2] == '"') {
            masked[index] = masked[index + 1] = masked[index + 2] = ' ';
            index += 2;
            in_string = true;
            in_multi_line_string = true;
            quote = '"';
            escaped = false;
        } else if (ch == '"' || ch == '\'') {
            masked[index] = ' ';
            in_string = true;
            in_multi_line_string = false;
            quote = ch;
            escaped = false;
        }
    }
    return masked;
}


// 判断源码中是否存在未闭合的字符串字面量（此时前缀仍可续写）
bool HasUnclosedString(std::string_view source) {
    bool in_string = false;
    bool triple_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    for (std::size_t index = 0; index < source.size(); ++index) {
        const char ch = source[index];
        const char next = index + 1 < source.size() ? source[index + 1] : '\0';
        if (line_comment) {
            if (ch == '\n') line_comment = false;
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
        } else if (ch == '/' && next == '*') {
            block_comment_depth = 1;
            ++index;
        } else if (ch == '"') {
            triple_string = index + 2 < source.size() &&
                source.substr(index, 3) == "\"\"\"";
            in_string = true;
            if (triple_string) index += 2;
        }
    }
    return in_string;
}


// 统计指定位置之前尚未闭合的花括号深度。
int BraceDepthBefore(std::string_view text, std::size_t end) {
    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    end = std::min(end, text.size());
    for (std::size_t index = 0; index < end; ++index) {
        const char ch = text[index];
        const char next = index + 1 < end ? text[index + 1] : '\0';
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
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '/' && next == '/') {
            line_comment = true;
            ++index;
        } else if (ch == '/' && next == '*') {
            block_comment_depth = 1;
            ++index;
        } else if (ch == '"') {
            in_string = true;
        } else if (ch == '{') {
            ++depth;
        } else if (ch == '}' && depth > 0) {
            --depth;
        }
    }
    return depth;
}


}
