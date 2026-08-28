#include "semantic_declarations.h"

#include "semantic_profile.h"
#include "semantic_text.h"
#include "semantic_types.h"

#include <algorithm>
#include <regex>
#include <stdexcept>
#include <unordered_set>
#include <utility>

namespace cangjie {

// 解析泛型参数列表文本（"<T, U>" 形式，忽略 <: 上界）
std::vector<std::string> ParseTypeParameters(std::string_view text) {
    std::string trimmed = Trim(text);
    if (!trimmed.empty() && trimmed.front() == '<') trimmed.erase(trimmed.begin());
    if (!trimmed.empty() && trimmed.back() == '>') trimmed.pop_back();
    std::vector<std::string> result;
    for (std::string item : SplitTopLevel(trimmed, ',')) {
        const std::size_t bound = item.find("<:");
        if (bound != std::string::npos) item.resize(bound);
        item = Trim(item);
        if (!item.empty()) result.push_back(item);
    }
    return result;
}

// 解析函数签名（泛型、参数列表、返回类型），生成 FunctionSig 记录
FunctionSig ParseFunctionSignature(
    std::string name,
    std::string_view generic_text,
    std::string_view param_text,
    std::string_view result_text
) {
    FunctionSig sig;
    sig.name = std::move(name);
    sig.type_params = ParseTypeParameters(generic_text);
    sig.result = CompactType(result_text);
    for (const std::string& raw : SplitTopLevel(param_text, ',')) {
        if (raw.empty()) continue;
        const std::size_t colon = FindTopLevel(raw, ":");
        if (colon == std::string::npos) continue;
        std::string name_part = Trim(std::string_view(raw).substr(0, colon));
        if (!name_part.empty() && name_part.back() == '!') name_part.pop_back();
        std::string type_part = Trim(std::string_view(raw).substr(colon + 1));
        const std::size_t equal = FindTopLevel(type_part, "=");
        const bool has_default = equal != std::string::npos;
        if (has_default) type_part.resize(equal);
        sig.param_names.push_back(Trim(name_part));
        sig.param_types.push_back(CompactType(type_part));
        if (!has_default) ++sig.required;
    }
    return sig;
}

// 解析类型头部中的 "<:" 父类型/接口列表（以 & 分隔）
std::vector<std::string> ParseSupers(std::string_view header) {
    const std::size_t marker = header.find("<:");
    if (marker == std::string::npos) return {};
    std::vector<std::string> output;
    for (std::string item : SplitTopLevel(header.substr(marker + 2), '&')) {
        item = CompactType(item);
        if (!item.empty()) output.push_back(item);
    }
    return output;
}

// 判断源码中是否存在跨行的函数/init/main 头部
bool HasMultilineFunctionHeader(std::string_view source) {
    std::size_t search_from = 0;
    while (search_from < source.size()) {
        const std::size_t func = source.find("func ", search_from);
        const std::size_t main = source.find("main", search_from);
        const std::size_t init = source.find("init", search_from);
        const std::size_t start = std::min({func, main, init});
        if (start == std::string_view::npos) return false;
        const std::size_t brace = source.find('{', start);
        const std::size_t newline = source.find_first_of("\n\r", start);
        if (newline != std::string_view::npos &&
            (brace == std::string_view::npos || newline < brace)) {
            return true;
        }
        search_from = start + 1;
    }
    return false;
}

// 返回严格类或接口声明的复用正则。
const std::regex& StrictNominalPattern() {
    static const std::regex pattern(
        R"(\b(class|interface)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^:>{}()]*>)?([^{}]*)\{)"
    );
    return pattern;
}

// 返回宽松类声明的复用正则。
const std::regex& BroadClassPattern() {
    static const std::regex pattern(
        R"(\bclass\s+([A-Za-z_][A-Za-z0-9_]*)[^{}]*\{)"
    );
    return pattern;
}

// 返回单行显式返回类型函数的复用正则。
const std::regex& ExplicitFunctionSingleLinePattern() {
    static const std::regex pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([^{}\n]+?)\s*\{)"
    );
    return pattern;
}

// 返回多行显式返回类型函数的复用正则。
const std::regex& ExplicitFunctionMultilinePattern() {
    static const std::regex pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*:\s*([^{}]+?)\s*\{)"
    );
    return pattern;
}

// 返回单行可选返回类型函数的复用正则。
const std::regex& OptionalFunctionSingleLinePattern() {
    static const std::regex pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    return pattern;
}

// 返回多行可选返回类型函数的复用正则。
const std::regex& OptionalFunctionMultilinePattern() {
    static const std::regex pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    return pattern;
}

// 返回当前单行函数头的复用正则。
const std::regex& CurrentFunctionSingleLinePattern() {
    static const std::regex pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()\n]*>)?|\bmain|\binit)\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    return pattern;
}

// 返回当前多行函数头的复用正则。
const std::regex& CurrentFunctionMultilinePattern() {
    static const std::regex pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()]*>)?|\bmain|\binit)\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    return pattern;
}

// 返回声明快照中缓存的记录总数。
std::size_t DeclarationSnapshot::RecordCount() const {
    return strict_nominals.size() + broad_classes.size() +
        explicit_functions_single_line.size() +
        explicit_functions_multiline_only.size() +
        optional_functions_single_line.size() +
        optional_functions_multiline_only.size() +
        current_functions_single_line.size() +
        current_functions_multiline_only.size();
}

using DelimiterCloseCache =
    std::unordered_map<std::size_t, std::optional<std::size_t>>;

// 从缓存读取或计算声明花括号的闭合位置。
std::optional<std::size_t> CachedDelimiterClose(
    std::string_view source,
    std::size_t open,
    DelimiterCloseCache* cache
) {
    const auto found = cache->find(open);
    if (found != cache->end()) {
#ifdef CANGJIE_ENABLE_PROFILE
        if (g_profile) ++g_profile->declaration_snapshot_delimiter_hits;
#endif
        return found->second;
    }
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer timer(
        g_profile ? &g_profile->declaration_snapshot_delimiter_ns : nullptr
    );
    if (g_profile) ++g_profile->declaration_snapshot_delimiter_misses;
#endif
    const std::optional<std::size_t> close = MatchingDelimiter(source, open, '{', '}');
    cache->emplace(open, close);
    return close;
}

// 使用指定正则扫描一类声明并保存捕获信息。
std::vector<DeclarationRecord> ScanDeclarationFamily(
    const std::string& source,
    const std::regex& pattern,
    bool multiline_only,
    DelimiterCloseCache* close_cache,
    const std::string* code_mask = nullptr
) {
    std::vector<DeclarationRecord> records;
    for (std::sregex_iterator it(source.begin(), source.end(), pattern), end;
         it != end; ++it) {
        if (multiline_only && (*it)[0].str().find_first_of("\n\r") == std::string::npos) {
            continue;
        }
        const std::size_t match_offset = static_cast<std::size_t>((*it).position());
        if (code_mask && StartsWith(source.substr(match_offset), "init") &&
            (match_offset >= code_mask->size() ||
            !IsIdentStart(static_cast<unsigned char>((*code_mask)[match_offset])))) {
            continue;
        }
        DeclarationRecord record;
        record.offset = match_offset;
        record.length = static_cast<std::size_t>((*it).length());
        record.open = record.offset + record.length - 1;
        record.close = CachedDelimiterClose(source, record.open, close_cache);
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(
                g_profile ? &g_profile->declaration_snapshot_capture_copy_ns : nullptr
            );
#endif
            record.captures.reserve(it->size());
            for (std::size_t index = 0; index < it->size(); ++index) {
                SnapshotCapture capture;
                capture.matched = (*it)[index].matched;
                capture.length = static_cast<std::size_t>((*it).length(index));
                if (capture.matched) {
                    capture.offset = static_cast<std::size_t>((*it).position(index));
                    capture.text = (*it)[index].str();
                }
                record.captures.push_back(std::move(capture));
            }
        }
        records.push_back(std::move(record));
    }
    return records;
}

// 扫描源码构建声明快照：收集函数、类/接口、类型参数与成员记录
DeclarationSnapshot BuildDeclarationSnapshot(std::string_view source) {
#ifdef CANGJIE_ENABLE_PROFILE
    {
        ProfileScopeTimer timer(
            g_profile ? &g_profile->declaration_snapshot_pattern_init_ns : nullptr
        );
        (void)StrictNominalPattern();
        (void)BroadClassPattern();
        (void)CurrentFunctionSingleLinePattern();
        (void)ExplicitFunctionSingleLinePattern();
        (void)OptionalFunctionSingleLinePattern();
        (void)CurrentFunctionMultilinePattern();
        (void)ExplicitFunctionMultilinePattern();
        (void)OptionalFunctionMultilinePattern();
    }
    std::string owned;
    {
        ProfileScopeTimer timer(
            g_profile ? &g_profile->declaration_snapshot_source_copy_ns : nullptr
        );
        owned.assign(source.data(), source.size());
    }
#else
    const std::string owned(source);
#endif
    DelimiterCloseCache close_cache;
    DeclarationSnapshot snapshot;
    std::string current_callable_mask;
    const std::string* current_callable_mask_ptr;
    if (owned.find("init") != std::string::npos) {
        current_callable_mask = MaskNonCodeText(owned);
        current_callable_mask_ptr = &current_callable_mask;
    }
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(
            g_profile ? &g_profile->declaration_snapshot_strict_nominal_ns : nullptr
        );
#endif
        snapshot.strict_nominals = ScanDeclarationFamily(
            owned, StrictNominalPattern(), false, &close_cache
        );
    }
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(
            g_profile ? &g_profile->declaration_snapshot_broad_class_ns : nullptr
        );
#endif
        snapshot.broad_classes = ScanDeclarationFamily(
            owned, BroadClassPattern(), false, &close_cache
        );
    }
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(
            g_profile ? &g_profile->declaration_snapshot_current_single_ns : nullptr
        );
#endif
        snapshot.current_functions_single_line = ScanDeclarationFamily(
            owned, CurrentFunctionSingleLinePattern(), false, &close_cache,
            current_callable_mask_ptr
        );
    }
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(
            g_profile ? &g_profile->declaration_snapshot_explicit_single_ns : nullptr
        );
#endif
        snapshot.explicit_functions_single_line = ScanDeclarationFamily(
            owned, ExplicitFunctionSingleLinePattern(), false, &close_cache
        );
    }
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(
            g_profile ? &g_profile->declaration_snapshot_optional_single_ns : nullptr
        );
#endif
        snapshot.optional_functions_single_line = ScanDeclarationFamily(
            owned, OptionalFunctionSingleLinePattern(), false, &close_cache
        );
    }
    bool has_multiline = false;
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(
            g_profile ? &g_profile->declaration_snapshot_multiline_probe_ns : nullptr
        );
#endif
        has_multiline = HasMultilineFunctionHeader(source);
    }
    if (has_multiline) {
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(
                g_profile ? &g_profile->declaration_snapshot_current_multiline_ns : nullptr
            );
#endif
            snapshot.current_functions_multiline_only = ScanDeclarationFamily(
                owned, CurrentFunctionMultilinePattern(), true, &close_cache,
                current_callable_mask_ptr
            );
        }
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(
                g_profile ? &g_profile->declaration_snapshot_explicit_multiline_ns : nullptr
            );
#endif
            snapshot.explicit_functions_multiline_only = ScanDeclarationFamily(
                owned, ExplicitFunctionMultilinePattern(), true, &close_cache
            );
        }
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(
                g_profile ? &g_profile->declaration_snapshot_optional_multiline_ns : nullptr
            );
#endif
            snapshot.optional_functions_multiline_only = ScanDeclarationFamily(
                owned, OptionalFunctionMultilinePattern(), true, &close_cache
            );
        }
    }
    return snapshot;
}

// 安全读取声明记录中的指定捕获组。
const SnapshotCapture& SnapshotCaptureAt(
    const DeclarationRecord& record,
    std::size_t index
) {
    if (index >= record.captures.size()) {
        throw std::logic_error("declaration snapshot capture index out of range");
    }
    return record.captures[index];
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
struct LegacyCapture {
    bool matched = false;
    std::size_t offset = std::string::npos;
    std::size_t length = 0;
    std::string text;
};

struct LegacyDeclarationRecord {
    std::size_t offset = 0;
    std::size_t length = 0;
    std::size_t open = 0;
    std::optional<std::size_t> close;
    std::vector<LegacyCapture> captures;
};

// 使用旧实现扫描一类声明以供差分校验。
std::vector<LegacyDeclarationRecord> LegacyScanDeclarationFamily(
    std::string_view source,
    const std::regex& pattern,
    bool multiline_only,
    const std::string* code_mask
) {
    const std::string owned(source);
    std::vector<LegacyDeclarationRecord> records;
    for (std::sregex_iterator it(owned.begin(), owned.end(), pattern), end;
         it != end; ++it) {
        if (multiline_only && (*it)[0].str().find_first_of("\n\r") == std::string::npos) {
            continue;
        }
        const std::size_t match_offset = static_cast<std::size_t>((*it).position());
        if (code_mask && StartsWith(source.substr(match_offset), "init") &&
            (match_offset >= code_mask->size() ||
            !IsIdentStart(static_cast<unsigned char>((*code_mask)[match_offset])))) {
            continue;
        }
        LegacyDeclarationRecord record;
        record.offset = match_offset;
        record.length = static_cast<std::size_t>((*it).length());
        record.open = record.offset + record.length - 1;
        record.close = MatchingDelimiter(owned, record.open, '{', '}');
        record.captures.reserve(it->size());
        for (std::size_t index = 0; index < it->size(); ++index) {
            LegacyCapture capture;
            capture.matched = (*it)[index].matched;
            capture.length = static_cast<std::size_t>((*it).length(index));
            if (capture.matched) {
                capture.offset = static_cast<std::size_t>((*it).position(index));
                capture.text = (*it)[index].str();
            }
            record.captures.push_back(std::move(capture));
        }
        records.push_back(std::move(record));
    }
    return records;
}

// 判断新旧扫描器生成的单条声明记录是否一致。
bool SameDeclarationRecord(
    const DeclarationRecord& left,
    const LegacyDeclarationRecord& right
) {
    if (left.offset != right.offset || left.length != right.length ||
        left.open != right.open || left.close != right.close ||
        left.captures.size() != right.captures.size()) {
        return false;
    }
    for (std::size_t index = 0; index < left.captures.size(); ++index) {
        const SnapshotCapture& left_capture = left.captures[index];
        const LegacyCapture& right_capture = right.captures[index];
        if (left_capture.matched != right_capture.matched ||
            left_capture.offset != right_capture.offset ||
            left_capture.length != right_capture.length ||
            left_capture.text != right_capture.text) {
            return false;
        }
    }
    return true;
}

// 判断新旧扫描器生成的声明记录列表是否一致。
bool SameDeclarationRecords(
    const std::vector<DeclarationRecord>& left,
    const std::vector<LegacyDeclarationRecord>& right
) {
    if (left.size() != right.size()) return false;
    for (std::size_t index = 0; index < left.size(); ++index) {
        if (!SameDeclarationRecord(left[index], right[index])) return false;
    }
    return true;
}

// 验证声明快照与旧正则实现完全一致。
void VerifyDeclarationSnapshot(
    std::string_view source,
    const DeclarationSnapshot& snapshot
) {
    static const std::regex strict_nominal_pattern(
        R"(\b(class|interface)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^:>{}()]*>)?([^{}]*)\{)"
    );
    static const std::regex broad_class_pattern(
        R"(\bclass\s+([A-Za-z_][A-Za-z0-9_]*)[^{}]*\{)"
    );
    static const std::regex explicit_single_line_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([^{}\n]+?)\s*\{)"
    );
    static const std::regex explicit_multiline_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*:\s*([^{}]+?)\s*\{)"
    );
    static const std::regex optional_single_line_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    static const std::regex optional_multiline_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    static const std::regex current_single_line_pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()\n]*>)?|\bmain|\binit)\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    static const std::regex current_multiline_pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()]*>)?|\bmain|\binit)\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    const std::string code_mask = MaskNonCodeText(source);
    auto verify = [&](const std::vector<DeclarationRecord>& actual,
                      const std::regex& pattern,
                      bool multiline_only,
                      const char* family,
                      const std::string* match_mask = nullptr) {
        const std::vector<LegacyDeclarationRecord> expected = LegacyScanDeclarationFamily(
            source, pattern, multiline_only, match_mask
        );
        if (!SameDeclarationRecords(actual, expected)) {
            throw std::logic_error(
                std::string("declaration snapshot record family diverged: ") + family
            );
        }
    };
    verify(snapshot.strict_nominals, strict_nominal_pattern, false, "strict nominal");
    verify(snapshot.broad_classes, broad_class_pattern, false, "broad class");
    verify(
        snapshot.explicit_functions_single_line,
        explicit_single_line_pattern, false, "explicit function single-line"
    );
    verify(
        snapshot.optional_functions_single_line,
        optional_single_line_pattern, false, "optional function single-line"
    );
    verify(
        snapshot.current_functions_single_line,
        current_single_line_pattern, false, "current function single-line", &code_mask
    );
    if (HasMultilineFunctionHeader(source)) {
        verify(
            snapshot.explicit_functions_multiline_only,
            explicit_multiline_pattern, true, "explicit function multiline-only"
        );
        verify(
            snapshot.optional_functions_multiline_only,
            optional_multiline_pattern, true, "optional function multiline-only"
        );
        verify(
            snapshot.current_functions_multiline_only,
            current_multiline_pattern, true, "current function multiline-only", &code_mask
        );
    } else if (!snapshot.explicit_functions_multiline_only.empty() ||
               !snapshot.optional_functions_multiline_only.empty() ||
               !snapshot.current_functions_multiline_only.empty()) {
        throw std::logic_error("declaration snapshot contains unexpected multiline records");
    }
}
#endif

// 从声明快照收集所有函数（含方法、构造器）到模型，按名字分组
void CollectFunctions(const DeclarationSnapshot& snapshot, Model* model) {
    auto collect = [&](const std::vector<DeclarationRecord>& records) {
        for (const DeclarationRecord& record : records) {
            FunctionSig sig = ParseFunctionSignature(
                SnapshotCaptureAt(record, 1).text,
                SnapshotCaptureAt(record, 2).text,
                SnapshotCaptureAt(record, 3).text,
                SnapshotCaptureAt(record, 4).text
            );
            model->functions[sig.name].push_back(std::move(sig));
        }
    };
    collect(snapshot.explicit_functions_single_line);
    collect(snapshot.explicit_functions_multiline_only);
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 使用正则旧实现收集函数声明。
void CollectFunctionsRegex(std::string_view source, Model* model) {
    static const std::regex single_line_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([^{}\n]+?)\s*\{)"
    );
    static const std::regex multiline_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*:\s*([^{}]+?)\s*\{)"
    );
    const std::string owned(source);
    auto collect = [&](const std::regex& pattern, bool multiline_only) {
        for (std::sregex_iterator it(owned.begin(), owned.end(), pattern), end;
             it != end; ++it) {
            if (multiline_only && (*it)[0].str().find_first_of("\n\r") == std::string::npos) {
                continue;
            }
            FunctionSig sig = ParseFunctionSignature(
                (*it)[1].str(), (*it)[2].str(), (*it)[3].str(), (*it)[4].str()
            );
            model->functions[sig.name].push_back(std::move(sig));
        }
    };
    collect(single_line_pattern, false);
    if (HasMultilineFunctionHeader(source)) {
        collect(multiline_pattern, true);
    }
}
#endif

// 收集 import 语句暴露到当前作用域的符号名（全局/函数别名）
void CollectImports(std::string_view source, Model* model) {
    static const std::regex import_pattern(
        R"(\bimport\s+(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*))"
    );
    const std::string owned(source);
    for (std::sregex_iterator it(owned.begin(), owned.end(), import_pattern), end; it != end; ++it) {
        const std::string alias = (*it)[1].str();
        model->globals[alias] = "namespace:" + alias;
    }
}

// 扫描已遮蔽源码中的顶层字段，并按需记录字段和方法顺序。
std::unordered_map<std::string, SourceFieldInfo> ScanTopLevelSourceFieldsMasked(
    std::string_view masked_body,
    std::vector<std::string>* ordered_field_names,
    std::vector<std::string>* ordered_method_names
) {
    static const std::regex member_pattern(
        R"((?:^|[\s;])\s*(?:(?:public|private)\s+)?(static\s+)?(?:(?:(let|var)\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*:|init\s*\(|func\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*<[^>{}()]*>)?\s*\())"
    );
    struct MemberHeader {
        std::size_t position = 0;
        std::size_t end = 0;
        bool is_static = false;
        std::string mutability;
        std::string field_name;
        std::string method_name;
    };

    const std::string owned(masked_body);
    std::vector<MemberHeader> members;
    std::size_t scan = 0;
    int brace_depth = 0;
    int paren_depth = 0;
    int bracket_depth = 0;
    for (std::sregex_iterator it(owned.begin(), owned.end(), member_pattern), end;
         it != end; ++it) {
        const std::size_t position = static_cast<std::size_t>((*it).position());
        while (scan < position) {
            const char ch = owned[scan++];
            if (ch == '{') ++brace_depth;
            else if (ch == '}' && brace_depth > 0) --brace_depth;
            else if (ch == '(') ++paren_depth;
            else if (ch == ')' && paren_depth > 0) --paren_depth;
            else if (ch == '[') ++bracket_depth;
            else if (ch == ']' && bracket_depth > 0) --bracket_depth;
        }
        if (brace_depth != 0 || paren_depth != 0 || bracket_depth != 0) continue;
        members.push_back(MemberHeader{
            position,
            position + static_cast<std::size_t>((*it).length()),
            (*it)[1].matched,
            (*it)[2].str(),
            (*it)[3].str(),
            (*it)[4].str(),
        });
    }

    std::unordered_map<std::string, SourceFieldInfo> result;
    for (std::size_t index = 0; index < members.size(); ++index) {
        const MemberHeader& member = members[index];
        if (!member.field_name.empty() && ordered_field_names) {
            ordered_field_names->push_back(member.field_name);
        }
        if (!member.method_name.empty() && ordered_method_names) {
            ordered_method_names->push_back(member.method_name);
        }
        if (member.field_name.empty()) continue;
        const std::size_t boundary = index + 1 < members.size()
            ? members[index + 1].position : owned.size();
        if (member.end > boundary) continue;
        const std::string_view tail = std::string_view(owned).substr(
            member.end, boundary - member.end
        );
        const std::size_t initializer = FindTopLevel(tail, "=");
        const std::size_t semicolon = FindTopLevel(tail, ";");
        std::size_t type_end = tail.size();
        if (initializer != std::string::npos) type_end = initializer;
        if (semicolon != std::string::npos) type_end = std::min(type_end, semicolon);
        result[member.field_name] = SourceFieldInfo{
            member.mutability != "let",
            member.is_static,
            initializer != std::string::npos &&
                (semicolon == std::string::npos || initializer < semicolon),
            CompactType(tail.substr(0, type_end)),
        };
    }
    return result;
}

// 遮蔽注释和字符串后扫描源码中的顶层字段。
std::unordered_map<std::string, SourceFieldInfo> ScanTopLevelSourceFields(
    std::string_view body
) {
    return ScanTopLevelSourceFieldsMasked(MaskNonCodeText(body));
}

// 从声明快照记录收集类/接口（含字段、方法、构造器、父类型）
void CollectNominalsFromRecords(
    std::string_view source,
    const std::vector<DeclarationRecord>& records,
    Model* model
) {
    static const std::regex single_line_method_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([^{};\n]*[^\s{};\n]))"
    );
    static const std::regex multiline_method_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*:\s*([^{};\n]*[^\s{};\n]))"
    );
    static const std::regex init_pattern(R"(\binit\s*\(([^{};]*?)\))");
    const std::string owned(source);
    for (const DeclarationRecord& record : records) {
        const std::size_t open = record.open;
        const std::optional<std::size_t>& close = record.close;
        const std::size_t body_end = close.value_or(owned.size());
        const std::string body = owned.substr(open + 1, body_end - open - 1);
        const std::string masked_body = MaskNonCodeText(body);
        NominalInfo info;
        info.is_interface = SnapshotCaptureAt(record, 1).text == "interface";
        info.name = SnapshotCaptureAt(record, 2).text;
        info.type_params = ParseTypeParameters(SnapshotCaptureAt(record, 3).text);
        info.supers = ParseSupers(SnapshotCaptureAt(record, 4).text);

        auto collect_methods = [&](const std::regex& pattern, bool multiline_only) {
            static const std::regex static_modifier_suffix(
                R"((?:^|[;{}\n\r])\s*(?:(?:public|private)\s+)?static\s*$)"
            );
            for (std::sregex_iterator method(body.begin(), body.end(), pattern), method_end;
                 method != method_end; ++method) {
                if (multiline_only &&
                    (*method)[0].str().find_first_of("\n\r") == std::string::npos) {
                    continue;
                }
                FunctionSig sig = ParseFunctionSignature(
                    (*method)[1].str(), (*method)[2].str(), (*method)[3].str(), (*method)[4].str()
                );
                const std::size_t method_pos = static_cast<std::size_t>((*method).position());
                sig.is_static = std::regex_search(
                    masked_body.substr(0, method_pos), static_modifier_suffix
                );
                auto& methods = sig.is_static ? info.static_methods : info.methods;
                methods[sig.name].push_back(std::move(sig));
            }
        };
        collect_methods(single_line_method_pattern, false);
        if (HasMultilineFunctionHeader(body)) {
            collect_methods(multiline_method_pattern, true);
        }
        for (const auto& [name, field] : ScanTopLevelSourceFieldsMasked(masked_body)) {
            auto& fields = field.is_static ? info.static_fields : info.fields;
            fields[name] = field.type;
        }
        for (std::sregex_iterator init(body.begin(), body.end(), init_pattern), init_end;
             init != init_end; ++init) {
            FunctionSig sig = ParseFunctionSignature(info.name, {}, (*init)[1].str(), info.name);
            sig.type_params = info.type_params;
            if (!info.type_params.empty()) {
                sig.result = info.name + "<";
                for (std::size_t index = 0; index < info.type_params.size(); ++index) {
                    if (index) sig.result += ",";
                    sig.result += info.type_params[index];
                }
                sig.result += ">";
            }
            info.constructors.push_back(std::move(sig));
        }
        if (!info.is_interface && info.constructors.empty()) {
            FunctionSig ctor;
            ctor.name = info.name;
            ctor.type_params = info.type_params;
            ctor.result = info.name;
            if (!info.type_params.empty()) {
                ctor.result += "<";
                for (std::size_t index = 0; index < info.type_params.size(); ++index) {
                    if (index) ctor.result += ",";
                    ctor.result += info.type_params[index];
                }
                ctor.result += ">";
            }
            info.constructors.push_back(std::move(ctor));
        }
        model->nominals[info.name] = std::move(info);
    }
}

// 收集全部类/接口声明到模型（入口函数）
void CollectNominals(
    std::string_view source,
    const DeclarationSnapshot& snapshot,
    Model* model
) {
    CollectNominalsFromRecords(source, snapshot.strict_nominals, model);
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 使用正则旧实现收集类和接口声明。
void CollectNominalsRegex(std::string_view source, Model* model) {
    static const std::regex nominal_pattern(
        R"(\b(class|interface)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^:>{}()]*>)?([^{}]*)\{)"
    );
    static const std::regex single_line_method_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([^{};\n]*[^\s{};\n]))"
    );
    static const std::regex multiline_method_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*:\s*([^{};\n]*[^\s{};\n]))"
    );
    static const std::regex init_pattern(R"(\binit\s*\(([^{};]*?)\))");
    const std::string owned(source);
    for (std::sregex_iterator it(owned.begin(), owned.end(), nominal_pattern), end;
         it != end; ++it) {
        const std::size_t open = static_cast<std::size_t>(
            (*it).position() + (*it).length() - 1
        );
        const auto close = MatchingDelimiter(owned, open, '{', '}');
        const std::size_t body_end = close.value_or(owned.size());
        const std::string body = owned.substr(open + 1, body_end - open - 1);
        const std::string masked_body = MaskNonCodeText(body);
        NominalInfo info;
        info.is_interface = (*it)[1].str() == "interface";
        info.name = (*it)[2].str();
        info.type_params = ParseTypeParameters((*it)[3].str());
        info.supers = ParseSupers((*it)[4].str());

        auto collect_methods = [&](const std::regex& pattern, bool multiline_only) {
            static const std::regex static_modifier_suffix(
                R"((?:^|[;{}\n\r])\s*(?:(?:public|private)\s+)?static\s*$)"
            );
            for (std::sregex_iterator method(body.begin(), body.end(), pattern), method_end;
                 method != method_end; ++method) {
                if (multiline_only &&
                    (*method)[0].str().find_first_of("\n\r") == std::string::npos) {
                    continue;
                }
                FunctionSig sig = ParseFunctionSignature(
                    (*method)[1].str(), (*method)[2].str(),
                    (*method)[3].str(), (*method)[4].str()
                );
                const std::size_t method_pos = static_cast<std::size_t>((*method).position());
                sig.is_static = std::regex_search(
                    masked_body.substr(0, method_pos), static_modifier_suffix
                );
                auto& methods = sig.is_static ? info.static_methods : info.methods;
                methods[sig.name].push_back(std::move(sig));
            }
        };
        collect_methods(single_line_method_pattern, false);
        if (HasMultilineFunctionHeader(body)) {
            collect_methods(multiline_method_pattern, true);
        }
        for (const auto& [name, field] : ScanTopLevelSourceFieldsMasked(masked_body)) {
            auto& fields = field.is_static ? info.static_fields : info.fields;
            fields[name] = field.type;
        }
        for (std::sregex_iterator init(body.begin(), body.end(), init_pattern), init_end;
             init != init_end; ++init) {
            FunctionSig sig = ParseFunctionSignature(
                info.name, {}, (*init)[1].str(), info.name
            );
            sig.type_params = info.type_params;
            if (!info.type_params.empty()) {
                sig.result = info.name + "<";
                for (std::size_t index = 0; index < info.type_params.size(); ++index) {
                    if (index) sig.result += ",";
                    sig.result += info.type_params[index];
                }
                sig.result += ">";
            }
            info.constructors.push_back(std::move(sig));
        }
        if (!info.is_interface && info.constructors.empty()) {
            FunctionSig ctor;
            ctor.name = info.name;
            ctor.type_params = info.type_params;
            ctor.result = info.name;
            if (!info.type_params.empty()) {
                ctor.result += "<";
                for (std::size_t index = 0; index < info.type_params.size(); ++index) {
                    if (index) ctor.result += ",";
                    ctor.result += info.type_params[index];
                }
                ctor.result += ">";
            }
            info.constructors.push_back(std::move(ctor));
        }
        model->nominals[info.name] = std::move(info);
    }
}

// 比较两个函数签名是否完全一致（用于模型差分校验）
bool SameFunctionSignature(const FunctionSig& left, const FunctionSig& right) {
    return left.name == right.name &&
        left.type_params == right.type_params &&
        left.param_names == right.param_names &&
        left.param_types == right.param_types &&
        left.result == right.result &&
        left.required == right.required &&
        left.is_static == right.is_static;
}

// 判断两个函数签名列表是否逐项一致。
bool SameSignatureVector(
    const std::vector<FunctionSig>& left,
    const std::vector<FunctionSig>& right
) {
    if (left.size() != right.size()) return false;
    for (std::size_t index = 0; index < left.size(); ++index) {
        if (!SameFunctionSignature(left[index], right[index])) return false;
    }
    return true;
}

// 判断两个重载签名映射是否完全一致。
bool SameSignatureMap(
    const std::unordered_map<std::string, std::vector<FunctionSig>>& left,
    const std::unordered_map<std::string, std::vector<FunctionSig>>& right
) {
    if (left.size() != right.size()) return false;
    for (const auto& [name, signatures] : left) {
        const auto found = right.find(name);
        if (found == right.end() || !SameSignatureVector(signatures, found->second)) {
            return false;
        }
    }
    return true;
}

// 比较两个类型（类/接口）信息是否完全一致
bool SameNominalInfo(const NominalInfo& left, const NominalInfo& right) {
    return left.name == right.name &&
        left.is_interface == right.is_interface &&
        left.type_params == right.type_params &&
        left.supers == right.supers &&
        left.fields == right.fields &&
        left.static_fields == right.static_fields &&
        SameSignatureMap(left.methods, right.methods) &&
        SameSignatureMap(left.static_methods, right.static_methods) &&
        SameSignatureVector(left.constructors, right.constructors);
}

// 比较两个模型（全局/函数/类型表）是否完全一致
bool SameModel(const Model& left, const Model& right) {
    if (left.globals != right.globals ||
        !SameSignatureMap(left.functions, right.functions) ||
        left.nominals.size() != right.nominals.size()) {
        return false;
    }
    for (const auto& [name, nominal] : left.nominals) {
        const auto found = right.nominals.find(name);
        if (found == right.nominals.end() || !SameNominalInfo(nominal, found->second)) {
            return false;
        }
    }
    return true;
}
#endif


}
