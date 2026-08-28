#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace cangjie {

bool IsIdentStart(unsigned char ch);
bool IsIdentContinue(unsigned char ch);
bool IsIdentifierText(std::string_view text);
bool HasBareVarLetKeyword(std::string_view text);
bool HasDeclNameAfterKeyword(std::string_view text);
bool IsDecimalIntegerText(std::string_view text);
bool IsDecimalNumberText(std::string_view text);
bool IsBasedIntegerText(std::string_view text);
bool StartsWith(std::string_view text, std::string_view prefix);
bool StartsWithKeyword(std::string_view text, std::string_view keyword);
std::string Trim(std::string_view input);
std::vector<std::string> SplitTopLevel(std::string_view input, char separator);
std::optional<std::size_t> MatchingDelimiter(
    std::string_view text,
    std::size_t open,
    char opening,
    char closing
);
std::size_t FindTopLevel(std::string_view input, std::string_view needle);
std::string MaskNonCodeText(std::string_view text);

}  // namespace cangjie
