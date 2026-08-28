#include "native_semantic.h"

#include <cctype>
#include <string>
#include <unordered_set>
#include <vector>

namespace cangjie {
namespace {

// 判断字符能否作为标识符首字符。
bool IsIdentifierStart(unsigned char ch) {
    return std::isalpha(ch) || ch == '_';
}

// 判断字符能否作为标识符后续字符。
bool IsIdentifierContinue(unsigned char ch) {
    return std::isalnum(ch) || ch == '_';
}

}

// 把新字节切成稳定 token，并保留尚未完成的词素。
IncrementalLexer::Result IncrementalLexer::Feed(std::string_view bytes) {
    pending_.append(bytes.data(), bytes.size());
    Result result;
    std::size_t pos = 0;
    // 将已确定边界的词素加入稳定 token 列表。
    auto emit = [&](TokenKind kind, std::size_t start, std::size_t end) {
        result.stable.push_back(TokenEvent{kind, pending_.substr(start, end - start), true});
    };
    // 末尾仍可能扩展的运算符前缀集合。
    static const std::unordered_set<std::string> operator_prefixes = {
        ".", "..", "...", "=", "!", "<", ">", "&", "&&", "|", "||",
        "?", "~", "*", "**", "+", "-", "/", "%", "^"
    };
    while (pos < pending_.size()) {
        const std::size_t start = pos;
        const unsigned char ch = pending_[pos];
        if (ch == ' ' || ch == '\t' || ch == '\r') {
            while (pos < pending_.size() &&
                   (pending_[pos] == ' ' || pending_[pos] == '\t' || pending_[pos] == '\r')) {
                ++pos;
            }
            continue;
        }
        if (ch == '\n') {
            emit(TokenKind::Newline, pos, pos + 1);
            ++pos;
            continue;
        }
        if (pos + 1 < pending_.size() && pending_.substr(pos, 2) == "//") {
            const std::size_t end = pending_.find('\n', pos + 2);
            if (end == std::string::npos) break;
            pos = end;
            continue;
        }
        if (pos + 1 < pending_.size() && pending_.substr(pos, 2) == "/*") {
            int depth = 1;
            pos += 2;
            while (pos + 1 < pending_.size() && depth > 0) {
                if (pending_.substr(pos, 2) == "/*") {
                    ++depth;
                    pos += 2;
                } else if (pending_.substr(pos, 2) == "*/") {
                    --depth;
                    pos += 2;
                } else {
                    ++pos;
                }
            }
            if (depth > 0) {
                pos = start;
                break;
            }
            continue;
        }
        if (ch == '"') {
            ++pos;
            bool escaped = false;
            while (pos < pending_.size()) {
                const char current = pending_[pos++];
                if (escaped) escaped = false;
                else if (current == '\\') escaped = true;
                else if (current == '"') break;
            }
            if (pos == pending_.size() && pending_[pos - 1] != '"') {
                pos = start;
                break;
            }
            emit(TokenKind::String, start, pos);
            continue;
        }
        if (ch == '`') {
            const std::size_t end = pending_.find('`', pos + 1);
            if (end == std::string::npos) break;
            pos = end + 1;
            emit(TokenKind::Identifier, start, pos);
            continue;
        }
        if (IsIdentifierStart(ch)) {
            ++pos;
            while (pos < pending_.size() &&
                   IsIdentifierContinue(static_cast<unsigned char>(pending_[pos]))) {
                ++pos;
            }
            if (pos == pending_.size()) {
                pos = start;
                break;
            }
            emit(TokenKind::Identifier, start, pos);
            continue;
        }
        if (std::isdigit(ch)) {
            bool floating = false;
            ++pos;
            while (pos < pending_.size() &&
                   (std::isalnum(static_cast<unsigned char>(pending_[pos])) || pending_[pos] == '.')) {
                floating = floating || pending_[pos] == '.' || pending_[pos] == 'e' ||
                    pending_[pos] == 'E' || pending_[pos] == 'f';
                ++pos;
            }
            if (pos == pending_.size()) {
                pos = start;
                break;
            }
            emit(floating ? TokenKind::Floating : TokenKind::Integer, start, pos);
            continue;
        }
        // 按最长优先顺序识别多字符运算符。
        static const std::vector<std::string> operators = {
            "&&=", "||=", "<<=", ">>=", "**=", "..=", "==", "!=", "<:",
            "<=", ">=", "&&", "||", "??", "|>", "~>", "=>", "->", "<<", ">>",
            "**", "+=", "-=", "*=", "/=", "%=", "&=", "^=", "|=", "++", "--", ".."
        };
        std::string matched;
        for (const std::string& op : operators) {
            if (pending_.substr(pos, op.size()) == op) {
                matched = op;
                break;
            }
        }
        if (!matched.empty()) {
            pos += matched.size();
            if (pos == pending_.size() && operator_prefixes.count(matched)) {
                pos = start;
                break;
            }
            emit(TokenKind::Symbol, start, pos);
            continue;
        }
        const std::string one(1, static_cast<char>(ch));
        if (pos + 1 == pending_.size() && operator_prefixes.count(one)) break;
        emit(TokenKind::Symbol, pos, pos + 1);
        ++pos;
    }
    if (pos > 0) pending_.erase(0, pos);
    result.partial.text = pending_;
    if (!pending_.empty()) {
        const unsigned char ch = pending_.front();
        if (ch == '"') result.partial.candidates.push_back(TokenKind::String);
        else if (IsIdentifierStart(ch) || ch == '`') {
            result.partial.candidates.push_back(TokenKind::Identifier);
        } else if (std::isdigit(ch)) {
            result.partial.candidates.push_back(TokenKind::Integer);
            result.partial.candidates.push_back(TokenKind::Floating);
        } else {
            result.partial.candidates.push_back(TokenKind::Symbol);
        }
    }
    return result;
}

}
