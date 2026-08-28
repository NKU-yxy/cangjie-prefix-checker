#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace cangjie {

// 判断字符能否作为标识符首字符。
bool IsIdentStart(unsigned char ch);
// 判断字符能否作为标识符后续字符。
bool IsIdentContinue(unsigned char ch);
// 判断文本是否为普通标识符。
bool IsIdentifierText(std::string_view text);
// 判断文本是否包含独立的 var 或 let 关键字。
bool HasBareVarLetKeyword(std::string_view text);
// 判断声明关键字后是否已出现名称。
bool HasDeclNameAfterKeyword(std::string_view text);
// 判断文本是否只包含十进制数字。
bool IsDecimalIntegerText(std::string_view text);
// 判断文本是否为简单十进制数。
bool IsDecimalNumberText(std::string_view text);
// 判断文本是否为带前缀的进制整数。
bool IsBasedIntegerText(std::string_view text);
// 判断文本是否以指定前缀开头。
bool StartsWith(std::string_view text, std::string_view prefix);
// 判断文本是否以完整关键字开头。
bool StartsWithKeyword(std::string_view text, std::string_view keyword);
// 去掉文本首尾空白。
std::string Trim(std::string_view input);
// 按分隔符切分顶层文本。
std::vector<std::string> SplitTopLevel(std::string_view input, char separator);
// 查找匹配的闭合定界符。
std::optional<std::size_t> MatchingDelimiter(
    std::string_view text,
    std::size_t open,
    char opening,
    char closing
);
// 在嵌套结构之外查找子串。
std::size_t FindTopLevel(std::string_view input, std::string_view needle);
// 遮蔽字符串和注释并保留源码位置。
std::string MaskNonCodeText(std::string_view text);
// 判断源码是否含有未闭合字符串。
bool HasUnclosedString(std::string_view source);
// 统计指定位置前未闭合的花括号深度。
int BraceDepthBefore(std::string_view text, std::size_t end);

}
