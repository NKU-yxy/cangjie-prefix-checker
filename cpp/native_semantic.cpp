#include "native_semantic.h"

#include "call_frontier.h"
#include "semantic_context.h"
#include "semantic_constructor.h"
#include "semantic_control_flow.h"
#include "semantic_checks.h"
#include "semantic_declarations.h"
#include "semantic_expression.h"
#include "semantic_model.h"
#include "semantic_profile.h"
#include "semantic_text.h"
#include "semantic_types.h"

#include <algorithm>
#include <cctype>
#ifdef CANGJIE_ENABLE_PROFILE
#include <chrono>
#endif
#include <cstdint>
#ifdef CANGJIE_ENABLE_PROFILE
#include <cstdlib>
#endif
#include <fstream>
#include <iostream>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>

namespace cangjie {
namespace {



}

namespace {

struct NominalDeclaration {
    std::size_t open = 0;
    std::optional<std::size_t> close;
    std::vector<std::string> type_parameters;
    std::string super_header;
};

// 从声明快照构建名义类型声明列表。
std::vector<NominalDeclaration> CollectNominalDeclarations(
    const DeclarationSnapshot& snapshot
) {
    std::vector<NominalDeclaration> declarations;
    declarations.reserve(snapshot.strict_nominals.size());
    for (const DeclarationRecord& record : snapshot.strict_nominals) {
        NominalDeclaration declaration;
        declaration.open = record.open;
        declaration.close = record.close;
        declaration.type_parameters = ParseTypeParameters(SnapshotCaptureAt(record, 3).text);
        declaration.super_header = SnapshotCaptureAt(record, 4).text;
        declarations.push_back(std::move(declaration));
    }
    return declarations;
}

// 查找包含指定源码位置的名义类型参数。
std::unordered_set<std::string> EnclosingNominalTypeParameters(
    const std::vector<NominalDeclaration>& declarations,
    std::size_t position
) {
    std::size_t nearest_open = std::string::npos;
    const std::vector<std::string>* nearest = nullptr;
    for (const NominalDeclaration& declaration : declarations) {
        if (declaration.open >= position) continue;
        if (declaration.close && *declaration.close < position) continue;
        if (nearest_open == std::string::npos || declaration.open > nearest_open) {
            nearest_open = declaration.open;
            nearest = &declaration.type_parameters;
        }
    }
    if (!nearest) return {};
    return std::unordered_set<std::string>(nearest->begin(), nearest->end());
}

// 检查所有显式声明的函数/变量类型：类型参数冲突、已知性、类型兼容性
CheckStatus CheckDeclaredTypesFromRecords(
    std::string_view source,
    const Model& model,
    const std::vector<DeclarationRecord>& single_line_records,
    const std::vector<DeclarationRecord>& multiline_only_records,
    const std::vector<NominalDeclaration>& nominal_declarations
) {
#ifndef CANGJIE_ENABLE_REGEX_SHADOW
    (void)source;
#endif
    static const std::unordered_set<std::string> primitives = {
        "Int64", "Float64", "Bool", "Rune", "Unit"
    };
    auto check_functions = [&](const std::vector<DeclarationRecord>& records) -> CheckStatus {
        for (const DeclarationRecord& record : records) {
            const auto params = ParseTypeParameters(SnapshotCaptureAt(record, 2).text);
            const std::size_t function_position = record.offset;
            std::unordered_set<std::string> allowed = EnclosingNominalTypeParameters(
                nominal_declarations, function_position
            );
#ifdef CANGJIE_ENABLE_REGEX_SHADOW
            if (allowed != EnclosingNominalTypeParametersRegex(source, function_position)) {
                throw std::logic_error(
                    "nominal declaration index diverged from regex shadow"
                );
            }
#endif
            allowed.insert(params.begin(), params.end());
            for (const std::string& parameter : params) {
                if (primitives.count(parameter)) {
                    return {false, "type parameter conflicts with primitive"};
                }
            }
            FunctionSig sig = ParseFunctionSignature(
                SnapshotCaptureAt(record, 1).text,
                SnapshotCaptureAt(record, 2).text,
                SnapshotCaptureAt(record, 3).text,
                SnapshotCaptureAt(record, 4).matched
                    ? SnapshotCaptureAt(record, 4).text : "Unit"
            );
            for (const std::string& type : sig.param_types) {
                if (!KnownDeclaredType(type, model, allowed)) {
                    return {false, "unknown parameter type"};
                }
            }
            if (!KnownDeclaredType(sig.result, model, allowed)) {
                return {false, "unknown return type"};
            }
        }
        return {};
    };
    if (CheckStatus status = check_functions(single_line_records); !status.ok) {
        return status;
    }
    if (CheckStatus status = check_functions(multiline_only_records); !status.ok) {
        return status;
    }
    for (const NominalDeclaration& declaration : nominal_declarations) {
        for (const std::string& parameter : declaration.type_parameters) {
            if (primitives.count(parameter)) return {false, "type parameter conflicts with primitive"};
        }
        const std::unordered_set<std::string> allowed(
            declaration.type_parameters.begin(), declaration.type_parameters.end()
        );
        for (const std::string& super : ParseSupers(declaration.super_header)) {
            if (!KnownDeclaredType(super, model, allowed)) return {false, "unknown supertype"};
        }
    }
    return {};
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 使用正则旧实现收集名义类型声明。
std::vector<NominalDeclaration> CollectNominalDeclarationsRegex(
    std::string_view source
) {
    static const std::regex nominal_pattern(
        R"(\b(class|interface)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^:>{}()]*>)?([^{}]*)\{)"
    );
    const std::string owned(source);
    std::vector<NominalDeclaration> declarations;
    for (std::sregex_iterator it(owned.begin(), owned.end(), nominal_pattern), end;
         it != end; ++it) {
        NominalDeclaration declaration;
        declaration.open = static_cast<std::size_t>(
            (*it).position() + (*it).length() - 1
        );
        declaration.close = MatchingDelimiter(owned, declaration.open, '{', '}');
        declaration.type_parameters = ParseTypeParameters((*it)[3].str());
        declaration.super_header = (*it)[4].str();
        declarations.push_back(std::move(declaration));
    }
    return declarations;
}

// 使用正则旧实现检查声明中的类型。
CheckStatus CheckDeclaredTypesRegex(std::string_view source, const Model& model) {
    static const std::regex single_line_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    static const std::regex multiline_pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    static const std::unordered_set<std::string> primitives = {
        "Int8", "Int16", "Int32", "Int64", "Float32", "Float64",
        "Bool", "Rune", "String", "Unit"
    };
    const std::string owned(source);
    const std::vector<NominalDeclaration> nominal_declarations =
        CollectNominalDeclarationsRegex(source);
    auto check_functions = [&](const std::regex& pattern,
                               bool multiline_only) -> CheckStatus {
        for (std::sregex_iterator it(owned.begin(), owned.end(), pattern), end;
             it != end; ++it) {
            if (multiline_only && (*it)[0].str().find_first_of("\n\r") == std::string::npos) {
                continue;
            }
            const auto params = ParseTypeParameters((*it)[2].str());
            const std::size_t function_position = static_cast<std::size_t>((*it).position());
            std::unordered_set<std::string> allowed = EnclosingNominalTypeParameters(
                nominal_declarations, function_position
            );
            if (allowed != EnclosingNominalTypeParametersRegex(owned, function_position)) {
                throw std::logic_error(
                    "legacy nominal declaration index diverged from direct regex shadow"
                );
            }
            allowed.insert(params.begin(), params.end());
            for (const std::string& parameter : params) {
                if (primitives.count(parameter)) {
                    return {false, "type parameter conflicts with primitive"};
                }
            }
            FunctionSig sig = ParseFunctionSignature(
                (*it)[1].str(), (*it)[2].str(), (*it)[3].str(),
                (*it)[4].matched ? (*it)[4].str() : "Unit"
            );
            for (const std::string& type : sig.param_types) {
                if (!KnownDeclaredType(type, model, allowed)) {
                    return {false, "unknown parameter type"};
                }
            }
            if (!KnownDeclaredType(sig.result, model, allowed)) {
                return {false, "unknown return type"};
            }
        }
        return {};
    };
    if (CheckStatus status = check_functions(single_line_pattern, false); !status.ok) {
        return status;
    }
    if (HasMultilineFunctionHeader(source)) {
        if (CheckStatus status = check_functions(multiline_pattern, true); !status.ok) {
            return status;
        }
    }
    for (const NominalDeclaration& declaration : nominal_declarations) {
        for (const std::string& parameter : declaration.type_parameters) {
            if (primitives.count(parameter)) {
                return {false, "type parameter conflicts with primitive"};
            }
        }
        const std::unordered_set<std::string> allowed(
            declaration.type_parameters.begin(), declaration.type_parameters.end()
        );
        for (const std::string& super : ParseSupers(declaration.super_header)) {
            if (!KnownDeclaredType(super, model, allowed)) {
                return {false, "unknown supertype"};
            }
        }
    }
    return {};
}
#endif

// 检查显式声明类型是否合法（入口，基于声明快照）
CheckStatus CheckDeclaredTypes(
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot
) {
    const std::vector<NominalDeclaration> nominal_declarations =
        CollectNominalDeclarations(snapshot);
    const CheckStatus result = CheckDeclaredTypesFromRecords(
        source, model,
        snapshot.explicit_functions_single_line,
        snapshot.explicit_functions_multiline_only,
        nominal_declarations
    );
#ifdef CANGJIE_ENABLE_REGEX_SHADOW
    RegexShadowProfileGuard profile_guard;
    const CheckStatus reference = CheckDeclaredTypesRegex(source, model);
    if (result.ok != reference.ok || result.message != reference.message) {
        throw std::logic_error("declaration snapshot declared-type check diverged from regex shadow");
    }
#endif
    return result;
}

class ActiveStatementCache {
 public:
    enum class Boundary {
        None,
        Newline,
        Semicolon,
        FunctionClose,
    };

    struct Result {
        std::string text;
        Boundary boundary = Boundary::None;
        std::string pending_text;
    };

    // 清空增量语句扫描状态。
    void Reset() {
        body_start_ = std::string_view::npos;
        cursor_ = 0;
        statement_start_ = 0;
        last_start_ = std::string_view::npos;
        last_end_ = 0;
        last_boundary_ = Boundary::None;
        paren_ = 0;
        bracket_ = 0;
        brace_ = 0;
        in_string_ = false;
        escaped_ = false;
        line_comment_ = false;
        block_comment_depth_ = 0;
        pending_newline_ = false;
    }

    // 扫描新增源码并返回当前活动语句。
    Result Update(
        std::string_view source,
        std::size_t body_start,
        std::size_t body_end
    ) {
        body_end = std::min(body_end, source.size());
        if (body_start_ != body_start || cursor_ > body_end) Initialize(body_start);
        bool started_after_newline = false;
        while (cursor_ < body_end) {
            const std::size_t index = cursor_;
            const char ch = source[index];
            const bool has_next = index + 1 < body_end;
            const char next = has_next ? source[index + 1] : '\0';
            if (pending_newline_ && index >= statement_start_ &&
                !std::isspace(static_cast<unsigned char>(ch))) {
                started_after_newline = true;
                pending_newline_ = false;
            }
            if (line_comment_) {
                ++cursor_;
                if (ch == '\n' || ch == '\r') {
                    line_comment_ = false;
                    CommitAtNewline(source, index);
                }
                continue;
            }
            if (block_comment_depth_ > 0) {
                if ((ch == '/' || ch == '*') && !has_next) break;
                if (ch == '/' && next == '*') {
                    ++block_comment_depth_;
                    cursor_ += 2;
                } else if (ch == '*' && next == '/') {
                    --block_comment_depth_;
                    cursor_ += 2;
                } else {
                    ++cursor_;
                }
                continue;
            }
            if (in_string_) {
                ++cursor_;
                if (escaped_) escaped_ = false;
                else if (ch == '\\') escaped_ = true;
                else if (ch == '"') in_string_ = false;
                continue;
            }
            if (ch == '/' && !has_next) break;
            if (ch == '/' && next == '/') {
                line_comment_ = true;
                cursor_ += 2;
            } else if (ch == '/' && next == '*') {
                block_comment_depth_ = 1;
                cursor_ += 2;
            } else if (ch == '"') {
                in_string_ = true;
                ++cursor_;
            } else if (ch == '(') {
                ++paren_;
                ++cursor_;
            } else if (ch == ')' && paren_ > 0) {
                --paren_;
                ++cursor_;
            } else if (ch == '[') {
                ++bracket_;
                ++cursor_;
            } else if (ch == ']' && bracket_ > 0) {
                --bracket_;
                ++cursor_;
            } else if (ch == '{') {
                ++brace_;
                ++cursor_;
            } else if (ch == '}' && brace_ > 0) {
                --brace_;
                ++cursor_;
            } else if (ch == ';' && AtTopLevel()) {
                Commit(source, index, Boundary::Semicolon);
                statement_start_ = index + 1;
                ++cursor_;
            } else if ((ch == '\n' || ch == '\r') && AtTopLevel()) {
                CommitAtNewline(source, index);
                ++cursor_;
            } else {
                ++cursor_;
            }
        }

        std::size_t visible_end = body_end;
        while (visible_end > statement_start_ &&
               std::isspace(static_cast<unsigned char>(source[visible_end - 1]))) {
            --visible_end;
        }
        if (visible_end > statement_start_ && source[visible_end - 1] == ';') {
            --visible_end;
            while (visible_end > statement_start_ &&
                   std::isspace(static_cast<unsigned char>(source[visible_end - 1]))) {
                --visible_end;
            }
        }
        const bool function_closed = body_end < source.size() && source[body_end] == '}';
        const std::string active = Trim(source.substr(
            statement_start_, visible_end - statement_start_
        ));
        if (started_after_newline && last_start_ != std::string_view::npos &&
            !active.empty()) {
            return {
                active,
                function_closed ? Boundary::FunctionClose : Boundary::None,
                Trim(source.substr(last_start_, last_end_ - last_start_)),
            };
        }
        if (!active.empty()) {
            return {
                active,
                function_closed ? Boundary::FunctionClose : Boundary::None,
            };
        }
        if (last_start_ != std::string_view::npos) {
            return {
                Trim(source.substr(last_start_, last_end_ - last_start_)),
                function_closed ? Boundary::FunctionClose : last_boundary_,
            };
        }
        return {};
    }

 private:
    // 从新的函数体起点初始化扫描游标。
    void Initialize(std::size_t body_start) {
        Reset();
        body_start_ = body_start;
        cursor_ = body_start;
        statement_start_ = body_start;
    }

    // 判断当前游标是否位于所有嵌套结构之外。
    bool AtTopLevel() const {
        return paren_ == 0 && bracket_ == 0 && brace_ == 0;
    }

    // 保存一条已经确定边界的非空语句。
    void Commit(std::string_view source, std::size_t end, Boundary boundary) {
        if (!Trim(source.substr(statement_start_, end - statement_start_)).empty()) {
            last_start_ = statement_start_;
            last_end_ = end;
            last_boundary_ = boundary;
        }
    }

    // 在无需续行时提交换行前的语句。
    void CommitAtNewline(std::string_view source, std::size_t index) {
        if (!ContinuesAfterNewline(source.substr(
                statement_start_, index - statement_start_
            ))) {
            const bool nonempty = !Trim(source.substr(
                statement_start_, index - statement_start_
            )).empty();
            Commit(source, index, Boundary::Newline);
            statement_start_ = index + 1;
            if (nonempty) pending_newline_ = true;
        }
    }

    std::size_t body_start_ = std::string_view::npos;  // 当前函数体起点。
    std::size_t cursor_ = 0;  // 下一个待扫描字节位置。
    std::size_t statement_start_ = 0;  // 当前活动语句起点。
    std::size_t last_start_ = std::string_view::npos;  // 最近完整语句起点。
    std::size_t last_end_ = 0;  // 最近完整语句终点。
    Boundary last_boundary_ = Boundary::None;  // 最近完整语句的结束方式。
    int paren_ = 0;  // 未闭合圆括号层数。
    int bracket_ = 0;  // 未闭合方括号层数。
    int brace_ = 0;  // 未闭合花括号层数。
    bool in_string_ = false;  // 当前是否位于字符串内。
    bool escaped_ = false;  // 字符串前一字符是否为转义符。
    bool line_comment_ = false;  // 当前是否位于行注释内。
    int block_comment_depth_ = 0;  // 块注释嵌套层数。
    bool pending_newline_ = false;  // 是否刚提交了一条换行语句。
};

// 填充函数上下文中的局部变量、字段和循环绑定。
FunctionContext PopulateFunctionContext(
    FunctionContext context,
    std::string_view source,
    const Model& model
) {
    if (!context.in_function) return context;
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(g_profile ? &g_profile->context_local_variables_ns : nullptr);
#endif
        CollectLocalVariables(&context);
    }
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(g_profile ? &g_profile->context_class_fields_ns : nullptr);
#endif
        if (!context.class_name.empty()) {
            if (const auto cls = model.nominals.find(context.class_name);
                cls != model.nominals.end()) {
                for (const auto& [name, type] : cls->second.fields) {
                    context.variables.emplace(name, type);
                    context.entry_variables.emplace(name, type);
                }
                context.variables["this"] = context.class_name;
                context.entry_variables["this"] = context.class_name;
            }
        }
    }
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(
            g_profile ? &g_profile->context_inferred_variables_ns : nullptr
        );
#endif
        CollectInferredLocalVariables(&context, model, source);
    }
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(g_profile ? &g_profile->context_lambda_variables_ns : nullptr);
#endif
        CollectActiveLambdaVariables(&context);
    }
    static const std::regex for_binding(
        R"(\bfor\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s+in\s+([^(){}\n]+)\)\s*\{)"
    );
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(g_profile ? &g_profile->context_for_binding_ns : nullptr);
#endif
        for (std::sregex_iterator it(context.body.begin(), context.body.end(), for_binding), end;
             it != end; ++it) {
            const std::size_t open = static_cast<std::size_t>(
                (*it).position() + (*it).length() - 1
            );
            if (MatchingDelimiter(context.body, open, '{', '}')) continue;
            ExpressionTyper typer(model, context, source);
            ExprResult iterable = typer.Infer((*it)[2].str());
            if (!iterable.known) continue;
            if (TypeHead(iterable.type) == "HashMap") {
                const auto args = TypeArgs(iterable.type);
                context.variables[(*it)[1].str()] = args.size() >= 2
                    ? "(" + args[0] + "," + args[1] + ")" : "?";
            } else {
                context.variables[(*it)[1].str()] = IterableElement(iterable.type);
            }
            context.entry_variables[(*it)[1].str()] =
                context.variables[(*it)[1].str()];
            context.entry_immutable.insert((*it)[1].str());
        }
    }
    return context;
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 比较两个函数上下文是否一致（shadow 差分校验用）
bool SameFunctionContext(const FunctionContext& left, const FunctionContext& right) {
    return left.in_function == right.in_function &&
        left.is_main == right.is_main &&
        left.result == right.result &&
        left.body == right.body &&
        left.body_start == right.body_start &&
        left.body_end == right.body_end &&
        left.variables == right.variables &&
        left.immutable == right.immutable &&
        left.entry_variables == right.entry_variables &&
        left.entry_immutable == right.entry_immutable &&
        left.class_name == right.class_name;
}
#endif

// 构建当前函数上下文：定位当前函数，填充局部变量/lambda 变量/类字段
FunctionContext BuildFunctionContext(
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot
) {
    FunctionContext current;
    {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer timer(g_profile ? &g_profile->context_current_function_ns : nullptr);
#endif
        current = CurrentFunctionContext(source, snapshot);
    }
    FunctionContext context = PopulateFunctionContext(std::move(current), source, model);
#ifdef CANGJIE_ENABLE_REGEX_SHADOW
    RegexShadowProfileGuard profile_guard;
    FunctionContext reference = PopulateFunctionContext(
        CurrentFunctionContextRegex(source), source, model
    );
    if (!SameFunctionContext(context, reference)) {
        throw std::logic_error("declaration snapshot function context diverged from regex shadow");
    }
#endif
    return context;
}

#ifdef CANGJIE_ENABLE_PROFILE
template <typename Callable>
// 执行检查并把耗时累加到指定性能计数器。
auto ProfileTimed(std::uint64_t* target, Callable&& callable) {
    ProfileScopeTimer timer(target);
    return callable();
}

// 估算复制函数上下文所需的字符串字节数。
std::size_t EstimateContextPayloadBytes(const FunctionContext& context) {
    std::size_t result = context.result.size() + context.body.size() + context.class_name.size();
    for (const auto& [name, type] : context.variables) {
        result += name.size() + type.size();
    }
    for (const std::string& name : context.immutable) result += name.size();
    for (const auto& [name, type] : context.entry_variables) {
        result += name.size() + type.size();
    }
    for (const std::string& name : context.entry_immutable) result += name.size();
    return result;
}
#endif

// 按脏标记执行声明、接口、构造器、控制流和表达式等语义检查。
CheckStatus AnalyzeSource(
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot,
    bool model_dirty,
    bool commit_dirty,
    const FunctionContext& cached_context,
    ActiveStatementCache::Result active_statement
#ifdef CANGJIE_ENABLE_PROFILE
    , ProfileCounters* profile
#endif
) {
    if (Trim(source).empty()) return {};

    const CheckStatus declaration_prefixes = CheckDeclarationPrefixes(source, model);
    if (!declaration_prefixes.ok) return declaration_prefixes;

#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer analyze_timer(profile ? &profile->analyze_total_ns : nullptr);
    if (profile) ++profile->duplicate_parameter_checks;
    const CheckStatus duplicate = ProfileTimed(
        profile ? &profile->duplicate_parameter_ns : nullptr,
        [&] { return CheckDuplicateParameter(source); }
    );
#else
    const CheckStatus duplicate = CheckDuplicateParameter(source);
#endif
    if (!duplicate.ok) return duplicate;
    if (model_dirty) {
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile) ++profile->declared_type_checks;
        const CheckStatus declared = ProfileTimed(
            profile ? &profile->declared_type_ns : nullptr,
            [&] { return CheckDeclaredTypes(source, model, snapshot); }
        );
#else
        const CheckStatus declared = CheckDeclaredTypes(source, model, snapshot);
#endif
        if (!declared.ok) return declared;
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile) ++profile->interface_checks;
        const CheckStatus interface = ProfileTimed(
            profile ? &profile->interface_ns : nullptr,
            [&] { return CheckInterfaces(source, model, snapshot); }
        );
#else
        const CheckStatus interface = CheckInterfaces(source, model, snapshot);
#endif
        if (!interface.ok) return interface;
    }
    if (commit_dirty) {
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile) ++profile->constructor_checks;
        const CheckStatus constructors = ProfileTimed(
            profile ? &profile->constructor_ns : nullptr,
            [&] { return CheckConstructors(source, model, snapshot); }
        );
#else
        const CheckStatus constructors = CheckConstructors(source, model, snapshot);
#endif
        if (!constructors.ok) return constructors;
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile) ++profile->range_checks;
        const CheckStatus ranges = ProfileTimed(
            profile ? &profile->range_ns : nullptr,
            [&] { return CheckRangeSteps(source, model); }
        );
#else
        const CheckStatus ranges = CheckRangeSteps(source, model);
#endif
        if (!ranges.ok) return ranges;
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile) ++profile->branch_join_checks;
        const CheckStatus joins = ProfileTimed(
            profile ? &profile->branch_join_ns : nullptr,
            [&] { return CheckIfBranchJoins(source, model); }
        );
#else
        const CheckStatus joins = CheckIfBranchJoins(source, model);
#endif
        if (!joins.ok) return joins;
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile) ++profile->malformed_generic_checks;
        const CheckStatus malformed = ProfileTimed(
            profile ? &profile->malformed_generic_ns : nullptr,
            [&] { return CheckMalformedGenericConstruct(source); }
        );
#else
        const CheckStatus malformed = CheckMalformedGenericConstruct(source);
#endif
        if (!malformed.ok) return malformed;
    }
#ifdef CANGJIE_ENABLE_PROFILE
    if (profile) ++profile->generic_prefix_checks;
    const CheckStatus generic = ProfileTimed(
        profile ? &profile->generic_prefix_ns : nullptr,
        [&] { return CheckGenericPrefix(source, model); }
    );
#else
    const CheckStatus generic = CheckGenericPrefix(source, model);
#endif
    if (!generic.ok) return generic;

#ifdef CANGJIE_ENABLE_PROFILE
    if (profile) profile->context_copy_payload_bytes += EstimateContextPayloadBytes(cached_context);
#endif
    FunctionContext context = cached_context;
    if (!context.in_function) return {};
    auto correct_explicit_result = [&](const std::vector<DeclarationRecord>& records) {
        for (const DeclarationRecord& record : records) {
            if (record.open + 1 == context.body_start) {
                context.result = CompactType(SnapshotCaptureAt(record, 4).text);
                return true;
            }
        }
        return false;
    };
    if (!correct_explicit_result(snapshot.explicit_functions_single_line)) {
        correct_explicit_result(snapshot.explicit_functions_multiline_only);
    }
    if (context.body_start <= source.size()) {
        const std::size_t end = context.body_end == std::string::npos
            ? source.size() : std::min(context.body_end, source.size());
        context.body = std::string(source.substr(context.body_start, end - context.body_start));
    }

    const CheckStatus duplicate_locals = CheckDuplicateLocalDeclarations(context);
    if (!duplicate_locals.ok) return duplicate_locals;

    ExpressionTyper typer(model, context, source);
    const bool trailing_numeric_prefix = !source.empty() &&
        std::isdigit(static_cast<unsigned char>(source.back()));
    const bool soft_newline =
        active_statement.boundary == ActiveStatementCache::Boundary::Newline;
    const bool committed =
        active_statement.boundary == ActiveStatementCache::Boundary::Semicolon ||
        active_statement.boundary == ActiveStatementCache::Boundary::FunctionClose;
#ifdef CANGJIE_ENABLE_PROFILE
    if (profile) profile->unclosed_string_scan_bytes += source.size();
#endif
    const bool unclosed_string = HasUnclosedString(source);
    const bool trailing_open_paren = !source.empty() && source.back() == '(';
    const std::size_t source_last_nonspace = source.find_last_not_of(" \t\r\n");
    const bool trailing_continuation = source_last_nonspace != std::string::npos && (
        std::string_view("+-*/%<>=!&|.,").find(source[source_last_nonspace]) !=
            std::string_view::npos ||
        source[source_last_nonspace] == '('
    );
    const bool defer_expression_error = trailing_numeric_prefix || unclosed_string ||
        trailing_open_paren || (!context.is_main && !committed && !soft_newline);
    auto should_defer_expression_error = [&](const ExprResult& result) {
        if (result.message == "wrong argument arity" && !trailing_open_paren)
            return false;
        return defer_expression_error ||
            (!committed && trailing_continuation &&
             result.message == "array index must be Int64") ||
            (!committed &&
             (result.message == "mixed numeric arithmetic" ||
              result.message == "logical operands require Bool" ||
              result.message == "incomparable operands" ||
              result.message == "mixed numeric relation")) ||
            (!committed && !soft_newline && !source.empty() &&
             std::isspace(static_cast<unsigned char>(source.back())) &&
             result.message == "string concatenation requires String");
    };
    auto defer_mixed_mismatch = [&](const std::string& actual_type,
                                    const std::string& target_type) {
        return !committed && trailing_continuation &&
            (actual_type == "Int64" || actual_type == "Float64") &&
            (target_type == "Int64" || target_type == "Float64") &&
            actual_type != target_type;
    };
    const std::string line = Trim(RemoveLoopComments(active_statement.text));
    if (!active_statement.pending_text.empty()) {
        const std::string pending = Trim(RemoveLoopComments(
            active_statement.pending_text
        ));
        if (const auto declaration = ParseAnyVariableDeclaration(pending)) {
            ExprResult actual = typer.Infer(
                declaration->expression, declaration->annotated_type
            );
            if (actual.error &&
                actual.message == "string concatenation requires String" &&
                StartsWith(Trim(line), ".")) {
                actual = typer.Infer(
                    declaration->expression + Trim(line), declaration->annotated_type
                );
            }
            if (actual.error) return {false, actual.message};
            if (!declaration->annotated_type.empty() && actual.known &&
                !Compatible(actual.type, declaration->annotated_type, model)) {
                return {false, "variable initializer type mismatch"};
            }
        } else if (const auto assignment = ParseReassignment(pending)) {
            if (!HasExplicitThisReceiver(pending) &&
                context.immutable.count(assignment->first)) {
                return {false, "assignment to let"};
            }
            std::string expected_type;
            if (HasExplicitThisReceiver(pending) && !context.class_name.empty()) {
                expected_type = TopLevelSourceFieldType(
                    source, snapshot, context.class_name, assignment->first
                );
            } else if (const auto expected = context.variables.find(assignment->first);
                       expected != context.variables.end()) {
                expected_type = expected->second;
            }
            if (!expected_type.empty()) {
                ExprResult actual = typer.Infer(assignment->second, expected_type);
                if (actual.error &&
                    actual.message == "string concatenation requires String" &&
                    StartsWith(Trim(line), ".")) {
                    actual = typer.Infer(
                        assignment->second + Trim(line), expected_type
                    );
                }
                if (actual.error) return {false, actual.message};
                if (actual.known && !Compatible(actual.type, expected_type, model)) {
                    return {false, "assignment type mismatch"};
                }
            }
        } else if (!pending.empty() && !IsStatementPrefix(pending)) {
            ExprResult expression = typer.Infer(pending, context.result);
            if (expression.error) return {false, expression.message};
            if (active_statement.boundary ==
                    ActiveStatementCache::Boundary::FunctionClose &&
                expression.known && context.result != "Unit" &&
                KnownDeclaredType(context.result, model, {}) &&
                !Compatible(expression.type, context.result, model)) {
                return {false, "implicit return type mismatch"};
            }
        }
    }
    const std::string trimmed_source = Trim(source);
    if (commit_dirty && !trimmed_source.empty() && trimmed_source.back() == '}') {
        const CheckStatus loop_bodies = CheckCompletedLoopBodies(
            context.body, model, context, source
        );
        if (!loop_bodies.ok) return loop_bodies;
    }
    if (active_statement.boundary == ActiveStatementCache::Boundary::FunctionClose) {
        const CheckStatus adjacent_assignments =
            CheckCompletedSimpleAssignmentSequence(
                line, source, model, snapshot, context
            );
        if (!adjacent_assignments.ok) return adjacent_assignments;
    }
    const bool condition_closed_now = !trimmed_source.empty() && trimmed_source.back() == ')';
    if (condition_closed_now) {
        for (const std::string keyword : {"if", "while"}) {
            if (line.find(keyword + " (") == std::string::npos &&
                line.find(keyword + "(") == std::string::npos) continue;
            const auto condition = LastCondition(context.body, keyword);
            if (!condition || condition->empty()) continue;
            ExprResult result = typer.Infer(*condition);
            if (result.error && !should_defer_expression_error(result)) {
                return {false, result.message};
            }
            if (result.known && result.type != "Bool") return {false, keyword + " condition must be Bool"};
        }
    }

    const std::size_t for_position = line.find("for (") != std::string::npos
        ? context.body.rfind("for (") : std::string::npos;
    if (for_position != std::string::npos) {
        const std::size_t in_position = context.body.find(" in ", for_position);
        if (in_position != std::string::npos) {
            const std::size_t close = context.body.find(')', in_position + 4);
            const std::size_t end = close == std::string::npos ? context.body.size() : close;
            std::string iterable_text = Trim(
                std::string_view(context.body).substr(in_position + 4, end - in_position - 4)
            );
            if (!iterable_text.empty()) {
                ExprResult iterable = typer.Infer(iterable_text);
                const bool incomplete_range_step = close == std::string::npos &&
                    (iterable.message == "range step must be integral" ||
                     iterable.message == "range step must share endpoint type");
                if (iterable.error && !incomplete_range_step &&
                    !should_defer_expression_error(iterable)) {
                    return {false, iterable.message};
                }
                const bool numeric_literal = IsDecimalNumberText(iterable_text) ||
                    IsBasedIntegerText(iterable_text);
                const bool may_be_range = close == std::string::npos &&
                    (numeric_literal || (!iterable_text.empty() && iterable_text.back() == '.') ||
                     ((!context.is_main || iterable_text.find('.') != std::string::npos) &&
                      (IsInteger(iterable.type) || iterable.type == "Rune")));
                if (iterable.known && !may_be_range && !IsIterable(iterable.type) &&
                    TypeHead(iterable.type) != "HashMap") {
                    return {false, "for operand is not iterable"};
                }
            }
        }
    }

    if ((line == "break" || line == "continue") && !InsideLoop(context.body)) {
        return {false, line + " outside loop"};
    }
    if (HasInvalidAssignmentTarget(line)) {
        return {false, "invalid assignment target"};
    }
    if (const auto declaration = ParseVariableDeclaration(line)) {
        ExprResult actual = typer.Infer(declaration->second, declaration->first);
        if (actual.error && !should_defer_expression_error(actual)) {
            return {false, actual.message};
        }
        static const std::regex incomplete_float(R"([0-9]+\.[0-9]*)");
        const bool recoverable = actual.known &&
            (MemberRecoversType(model, actual.type, declaration->first) ||
             OperatorRecoversType(model, actual.type, declaration->first));
        const bool trailing_open_bracket =
            std::count(declaration->second.begin(), declaration->second.end(), '[') >
            std::count(declaration->second.begin(), declaration->second.end(), ']');
        const bool defer_atom = !committed && !soft_newline && (
            ((IsIdentifierText(declaration->second) ||
              (!declaration->second.empty() && declaration->second.front() == '"')) &&
             recoverable) ||
            trailing_numeric_prefix ||
            unclosed_string || trailing_open_paren || trailing_open_bracket ||
            std::regex_match(declaration->second, incomplete_float)
        ) && declaration->second != "true" && declaration->second != "false";
        const bool defer_suffix = !committed && actual.suffix_may_change_type &&
            !IsFunctionType(actual.type) && recoverable;
        const std::string rhs_text = Trim(declaration->second);
        const bool rhs_closed_lambda =
            rhs_text.size() >= 4 && rhs_text.front() == '{' &&
            rhs_text.back() == '}' &&
            rhs_text.find("=>") != std::string::npos;
        if (actual.known && !Compatible(actual.type, declaration->first, model) &&
            !defer_atom && !defer_suffix &&
            !(soft_newline && recoverable && !rhs_closed_lambda) &&
            !defer_mixed_mismatch(actual.type, declaration->first)) {
            return {false, "variable initializer type mismatch"};
        }
        if (!actual.error) {
            const std::size_t dot = declaration->second.rfind('.');
            if (dot != std::string::npos) {
                const std::string member =
                    Trim(std::string_view(declaration->second).substr(dot + 1));
                if (!member.empty() && IsIdentifierText(member)) {
                    const std::string receiver =
                        Trim(std::string_view(declaration->second).substr(0, dot));
                    const bool simple_receiver = !receiver.empty() &&
                        receiver.find_first_of("[({") == std::string::npos;
                    if (simple_receiver) {
                        ExprResult recv = typer.Infer(receiver, {});
                        if (recv.known && !recv.error) {
                            const std::string head = TypeHead(recv.type);
                            const bool tostring_primitive =
                                (head == "Int64" || head == "Float64" || head == "Bool");
                            if (!tostring_primitive &&
                                !HasMemberPrefix(model, recv.type, member)) {
                                return {false, "unknown member"};
                            }
                        }
                    }
                }
            }
        }
    } else if (const auto declaration = ParseAnyVariableDeclaration(line)) {
        ExprResult actual = typer.Infer(declaration->expression, declaration->annotated_type);
        if (actual.error && !should_defer_expression_error(actual)) {
            return {false, actual.message};
        }
        const bool stable_initializer = committed || (soft_newline &&
            (!actual.suffix_may_change_type || IsFunctionType(actual.type)));
        if (!declaration->annotated_type.empty() && actual.known && stable_initializer &&
            !defer_mixed_mismatch(actual.type, declaration->annotated_type) &&
            !Compatible(actual.type, declaration->annotated_type, model)) {
            return {false, "variable initializer type mismatch"};
        }
    } else if (const auto assignment = ParseReassignment(line)) {
        const bool explicit_this = HasExplicitThisReceiver(line);
        std::string expected_type;
        if (explicit_this && !context.class_name.empty()) {
            expected_type = TopLevelSourceFieldType(
                source, snapshot, context.class_name, assignment->first
            );
        } else if (const auto expected = context.variables.find(assignment->first);
                   expected != context.variables.end()) {
            expected_type = expected->second;
        }
        ExprResult actual;
        if (!expected_type.empty()) {
            actual = typer.Infer(assignment->second, expected_type);
            if (actual.error && !should_defer_expression_error(actual)) {
                return {false, actual.message};
            }
        }
        const bool rhs_extendable = actual.known &&
            (actual.suffix_may_change_type ||
             !(actual.type == "Bool" || actual.type == "Unit" ||
               IsFunctionType(actual.type)));
        if (!explicit_this && context.immutable.count(assignment->first) &&
            (committed || (soft_newline && !rhs_extendable))) {
            return {false, "assignment to let"};
        }
        if (committed && actual.known && !Compatible(actual.type, expected_type, model)) {
            return {false, "assignment type mismatch"};
        }
    } else if (line == "return") {
        if (active_statement.boundary == ActiveStatementCache::Boundary::FunctionClose &&
            context.result != "Unit") {
            return {false, "return value required"};
        }
    } else if (StartsWith(line, "return ")) {
        ExprResult actual = typer.Infer(Trim(std::string_view(line).substr(7)), context.result);
        if (actual.error && !should_defer_expression_error(actual)) {
            return {false, actual.message};
        }
        if (committed && actual.known && context.result != "Unit" && !Compatible(actual.type, context.result, model)) {
            return {false, "return type mismatch"};
        }
    } else if (!line.empty() && !IsStatementPrefix(line) &&
               !IsExplicitBlockStatement(line) &&
               !StartsWith(line, "func ") && !StartsWith(line, "class ") &&
               !StartsWith(line, "interface ") && !StartsWith(line, "if ") &&
               !StartsWith(line, "while ") && !StartsWith(line, "for ") &&
               !StartsWith(line, "//") && !StartsWith(line, "/*")) {
        ExprResult expression = typer.Infer(line, context.result);
        if (expression.error && !should_defer_expression_error(expression)) {
            return {false, expression.message};
        }
        const std::unordered_set<std::string> no_type_parameters;
        const bool implicit_result_stable =
            active_statement.boundary == ActiveStatementCache::Boundary::FunctionClose;
        const bool concrete_result = KnownDeclaredType(
            context.result, model, no_type_parameters
        );
        if (implicit_result_stable && concrete_result && context.result != "Unit" &&
            expression.known &&
            !trailing_numeric_prefix &&
            !Compatible(expression.type, context.result, model)) {
            return {false, "implicit return type mismatch"};
        }
    }

    if (!line.empty() && line.back() == '.') {
        static const std::regex single_map_loop(
            R"(for\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\s*\))"
        );
        std::smatch loop;
        if (std::regex_search(context.body, loop, single_map_loop)) {
            const auto variable = context.variables.find(loop[2].str());
            if (variable != context.variables.end() && TypeHead(variable->second) == "HashMap" &&
                line.find(loop[1].str()) != std::string::npos) {
                return {false, "HashMap loop requires key/value pattern"};
            }
        }
    }
    return {};
}

}

class IncrementalSemanticEngine::Impl {
 public:
    // 构造引擎：加载上下文表作为预置模型，并构建后缀图（postfix graph）
    explicit Impl(std::string context_path) : context_path_(std::move(context_path)) {
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile_.enabled) {
            g_profile = &profile_;
            profile_.BeginTypeGeneration();
        }
#endif
        LoadContextTable(context_path_, &preload_);
        active_model_ = preload_;
        postfix_graph_ = PostfixGraph::Build(preload_);
    }

#ifdef CANGJIE_ENABLE_PROFILE
    // 输出性能统计并解除当前计数器绑定。
    ~Impl() {
        profile_.Print();
        if (g_profile == &profile_) g_profile = nullptr;
    }
#endif

    void DumpContextIrJson(std::ostream& os) const;

    // 返回最近一次失败的前沿分类。
    const FrontierInfo& LastFrontier() const { return last_frontier_; }
    // 更新最近一次失败的前沿分类。
    void SetLastFrontier(const FrontierInfo& info) { last_frontier_ = info; }

    // 返回最近一次失败的恢复见证。
    const RecoveryWitness& LastWitness() const { return last_witness_; }
    // 更新最近一次失败的恢复见证。
    void SetLastWitness(const RecoveryWitness& witness) { last_witness_ = witness; }
    // 返回恢复见证查询统计。
    const WitnessStats& WitnessStatistics() const { return witness_stats_; }

    // 返回最近一次调用的重载前沿。
    const CallFrontierResult& LastCallFrontier() const { return last_call_frontier_; }
    // 更新最近一次调用的重载前沿。
    void SetLastCallFrontier(const CallFrontierResult& result) {
        last_call_frontier_ = result;
    }

    // 返回最近一次续写证明。
    const ContinuationProof& LastProof() const { return last_proof_; }
    // 返回全部决策账本记录。
    const std::vector<DecisionLedgerEntry>& DecisionLedger() const { return ledger_; }

    std::string context_path_;  // 预置上下文表路径。
    PostfixGraph postfix_graph_;  // 用于搜索可恢复后缀的类型图。
    FrontierInfo last_frontier_;  // 最近一次拒绝位置的分类结果。
    RecoveryWitness last_witness_;  // 最近一次可恢复性见证。
    WitnessStats witness_stats_;  // 恢复见证查询统计。
    CallFrontierResult last_call_frontier_;  // 最近一次调用重载分析结果。
    ContinuationProof last_proof_;  // 最近一次前缀续写证明。
    std::vector<DecisionLedgerEntry> ledger_;  // 全部前缀决策记录。
    std::unordered_map<std::string, RecoveryWitness> witness_cache_;  // 见证缓存。
    Model preload_;  // 从上下文表加载的只读基础模型。
    Model active_model_;  // 合并当前源码声明后的模型。
    DeclarationSnapshot declaration_snapshot_;  // 当前源码的声明扫描快照。
    FunctionContext active_context_;  // 当前所在函数的局部语义上下文。
    std::vector<TokenEvent> accepted_;  // 已接受的稳定词法单元。
    std::size_t source_bytes_ = 0;  // 上次完成检查的源码长度。
    std::size_t model_source_bytes_ = 0;  // 当前模型对应的源码长度。
    std::size_t context_source_bytes_ = 0;  // 当前函数上下文对应的源码长度。
    bool context_decl_pending_ = false;  // 是否存在尚未闭合的声明头。
    std::string last_partial_;  // 上次检查时未完成的词素。
    ActiveStatementCache statement_cache_;  // 当前活动语句的增量扫描缓存。
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileCounters profile_;  // 本引擎实例的性能计数器。
#endif
};

namespace {

// 判断失败点是否位于未闭合的数组字面量内部（"[" 尚未闭合）
bool ArrayLiteralOpenAt(std::string_view line, std::size_t frontier_end) {
    (void)frontier_end;
    int balance = 0;
    for (const char ch : line) {
        if (ch == '[') ++balance;
        else if (ch == ']') --balance;
    }
    return balance > 0;
}

// 从变量声明行提取数组元素的期望类型。
std::string ArrayElementExpectedFromLine(
    std::string_view line, std::size_t frontier_end
) {
    const std::size_t limit = std::min(frontier_end, line.size());
    std::size_t open = std::string_view::npos;
    {
        int balance = 0;
        for (std::size_t i = limit; i-- > 0;) {
            if (line[i] == ']') ++balance;
            else if (line[i] == '[') {
                if (balance == 0) {
                    open = i;
                    break;
                }
                --balance;
            }
        }
    }
    if (open == std::string_view::npos) return "";
    std::size_t eq = open;
    while (eq > 0 && line[eq] != '=') --eq;
    if (eq == 0 || line[eq] != '=') return "";
    std::size_t colon = eq;
    while (colon > 0 && line[colon] != ':') --colon;
    if (colon == 0 || line[colon] != ':') return "";
    const std::string type = CompactType(Trim(
        std::string_view(line.data() + colon + 1, eq - colon - 1)
    ));
    const auto args = TypeArgs(type);
    if (args.empty()) return "";
    return args.front();
}

// 从拒绝消息的关键词推断决策现场类别（array_element / let_initializer / ...）
std::string SiteFromMessage(const std::string& message) {
    if (message.find("array element") != std::string::npos) return "array_element";
    if (message.find("initializer") != std::string::npos) return "let_initializer";
    if (message.find("assignment") != std::string::npos) return "assignment_rhs";
    if (message.find("condition") != std::string::npos) return "condition";
    if (message.find("lambda") != std::string::npos) return "lambda";
    if (message.find("return") != std::string::npos) return "return";
    if (message.find("iterable") != std::string::npos) return "for_in_source";
    if (message.find("argument") != std::string::npos ||
        message.find("parameter") != std::string::npos) return "call_arg";
    if (message.find("candidate") != std::string::npos ||
        message.find("overload") != std::string::npos) return "call_close";
    if (message.find("member") != std::string::npos) return "member_selection";
    if (message.find("callable") != std::string::npos) return "callable";
    if (message.find("type") != std::string::npos) return "type_check";
    return "generic";
}

// 从失败信息与 shadow 结果构造决策上下文（供证明层与账本使用）
DecisionContext MakeDecisionContext(
    const std::string& message,
    std::string_view source,
    const FrontierInfo& frontier,
    const RecoveryWitness& witness,
    const CallFrontierResult& call_frontier
) {
    DecisionContext ctx;
    ctx.site = SiteFromMessage(message);
    ctx.prefix = std::string(source);
    ctx.baseline_reject = true;
    ctx.symbol_kind = SymbolKindName(frontier.symbol_kind);
    ctx.tail_kind = TailKindName(frontier.tail_kind);
    ctx.boundary = BoundaryKindName(frontier.boundary_kind);
    ctx.expected_type = witness.target;
    ctx.actual_type = witness.source;
    if (call_frontier.resolved) {
        ctx.candidate_count = static_cast<int>(call_frontier.overload_count);
        ctx.call_closed = call_frontier.call_closed;
        ctx.alive_count = static_cast<int>(call_frontier.alive_count);
        ctx.eliminated_reasons = call_frontier.reasons;
    }
    if (ctx.site == "array_element") {
        ctx.element_open = ArrayLiteralOpenAt(frontier.line, frontier.frontier_end);
        if (ctx.element_open) {
            ctx.element_expected = ArrayElementExpectedFromLine(
                frontier.line, frontier.frontier_end
            );
            if (!ctx.element_expected.empty()) {
                ctx.expected_type = ctx.element_expected;
            }
        }
    }
    return ctx;
}

// 根据开放数组和已闭合调用的重载状态计算前缀续写证明。
ContinuationProof ComputeProof(const DecisionContext& ctx) {
    ContinuationProof proof;
    if (ctx.site == "array_element" && ctx.element_open) {
        proof.state = ContinuationState::Alive;
        proof.proof = ProofKind::ValidSuffix;
        proof.rule_id = "v15-p4-array-element";
        proof.printable_suffix = "]";
        return proof;
    }
    // 调用已经闭合且所有重载均被淘汰时，前缀无法再通过续写恢复。
    if (ctx.site == "call_close" && ctx.call_closed &&
        ctx.candidate_count > 0 && ctx.alive_count == 0) {
        proof.state = ContinuationState::Dead;
        proof.proof = ProofKind::ClosedWorldExhaustive;
        proof.rule_id = "v15-p5-call-close";
        proof.transition_set_complete = true;
        proof.eliminated_candidates = ctx.eliminated_reasons;
        return proof;
    }
    proof.rule_id = "v15-stub";
    return proof;
}

// 仅在续写证明有效时覆盖基线结果，并生成决策账本条目。
CheckStatus DecideWithProof(
    const CheckStatus& baseline,
    const DecisionContext& ctx,
    ContinuationProof* proof_out,
    DecisionLedgerEntry* entry_out
) {
    static std::size_t serial = 0;
    ContinuationProof proof = ComputeProof(ctx);
    if (proof_out) *proof_out = proof;

    DecisionLedgerEntry entry;
    entry.decision_id = ctx.site + "_" + std::to_string(++serial);
    entry.site = ctx.site;
    entry.prefix = ctx.prefix;
    entry.baseline = ctx.baseline_reject ? "dead" : "alive";
    entry.frontier = ContinuationStateName(proof.state);
    entry.proof_kind = ProofKindName(proof.proof);
    entry.symbol_kind = ctx.symbol_kind;
    entry.tail_kind = ctx.tail_kind;
    entry.boundary = ctx.boundary;
    entry.candidate_count = ctx.candidate_count;
    entry.expected_type = ctx.expected_type;
    entry.actual_type = ctx.actual_type;
    entry.rule_id = proof.rule_id;
    entry.printable_suffix = proof.printable_suffix;

    if (proof.state == ContinuationState::Alive &&
        proof.proof == ProofKind::ValidSuffix) {
        entry.overridden = true;
        if (entry_out) *entry_out = std::move(entry);
        return {};
    }
    if (proof.state == ContinuationState::Dead &&
        (proof.proof == ProofKind::OfficialAudit ||
         proof.proof == ProofKind::ClosedWorldExhaustive)) {
        entry.overridden = true;
        if (entry_out) *entry_out = std::move(entry);
        return baseline;
    }
    if (entry_out) *entry_out = std::move(entry);
    return baseline;
}

}

// 把预加载的上下文模型序列化为 Context IR JSON（供外部工具对比）
void IncrementalSemanticEngine::Impl::DumpContextIrJson(std::ostream& os) const {
    DumpModelJson(os, preload_);
}

// 创建增量语义引擎并初始化内部状态。
IncrementalSemanticEngine::IncrementalSemanticEngine(std::string context_path)
    : impl_(std::make_unique<Impl>(std::move(context_path))) {}

// 释放增量语义引擎内部实现。
IncrementalSemanticEngine::~IncrementalSemanticEngine() = default;

// 接受一个稳定 token（记录到已接受列表，语义检查留待 Probe 阶段）
CheckStatus IncrementalSemanticEngine::Accept(const TokenEvent& event) {
    impl_->accepted_.push_back(event);
#ifdef CANGJIE_ENABLE_PROFILE
    if (impl_->profile_.enabled) ++impl_->profile_.accepted_events;
#endif
    return {};
}

// 按需重建模型和上下文，分析整体前缀并使用恢复证明复核失败结果。
CheckStatus IncrementalSemanticEngine::Probe(
    const PartialLexeme& partial,
    std::string_view source
) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileCounters* profile = impl_->profile_.enabled ? &impl_->profile_ : nullptr;
    if (profile) ++profile->probe_calls;
#endif
    const std::string_view delta = source.substr(
        std::min(impl_->source_bytes_, source.size())
    );
    const bool indentation_only = !delta.empty() &&
        delta.find_first_not_of(" \t") == std::string_view::npos && impl_->last_partial_.empty();
    if (indentation_only) {
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile) ++profile->indentation_fast_paths;
#endif
        impl_->source_bytes_ = source.size();
        impl_->last_partial_ = partial.text;
        return {};
    }
    int brace_depth = 0;
    std::size_t outer_open = std::string_view::npos;
    {
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile) profile->brace_scan_bytes += source.size();
        ProfileScopeTimer brace_timer(profile ? &profile->brace_scan_ns : nullptr);
#endif
        for (std::size_t index = 0; index < source.size(); ++index) {
            if (source[index] == '{') {
                if (brace_depth++ == 0) outer_open = index;
            } else if (source[index] == '}' && brace_depth > 0) {
                --brace_depth;
                if (brace_depth == 0) outer_open = std::string_view::npos;
            }
        }
    }
    bool open_nominal_header = false;
    if (outer_open != std::string_view::npos && brace_depth == 1) {
        const std::size_t prior_close = source.rfind('}', outer_open);
        const std::string header(source.substr(
            prior_close == std::string_view::npos ? 0 : prior_close + 1,
            outer_open - (prior_close == std::string_view::npos ? 0 : prior_close + 1)
        ));
        open_nominal_header = header.find("class ") != std::string::npos ||
            header.find("interface ") != std::string::npos;
    }
    const bool model_dirty = impl_->model_source_bytes_ == 0 ||
        delta.find_first_of("{}") != std::string_view::npos || open_nominal_header;
    const bool commit_dirty = model_dirty ||
        delta.find_first_of(")\n\r;}") != std::string_view::npos;
    if (model_dirty) {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer model_timer(profile ? &profile->model_rebuild_ns : nullptr);
        if (profile) {
            ++profile->model_rebuilds;
            profile->model_rebuild_source_bytes += source.size();
            profile->BeginTypeGeneration();
        }
#endif
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(
                profile ? &profile->declaration_snapshot_build_ns : nullptr
            );
            if (profile) {
                ++profile->declaration_snapshot_rebuilds;
                profile->declaration_snapshot_source_bytes += source.size();
            }
#endif
            impl_->declaration_snapshot_ = BuildDeclarationSnapshot(source);
#ifdef CANGJIE_ENABLE_REGEX_SHADOW
            VerifyDeclarationSnapshot(source, impl_->declaration_snapshot_);
#endif
#ifdef CANGJIE_ENABLE_PROFILE
            if (profile) {
                profile->declaration_snapshot_records +=
                    impl_->declaration_snapshot_.RecordCount();
            }
#endif
        }
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(profile ? &profile->model_reset_ns : nullptr);
#endif
            impl_->active_model_ = impl_->preload_;
        }
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(profile ? &profile->collect_imports_ns : nullptr);
#endif
            CollectImports(source, &impl_->active_model_);
        }
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(profile ? &profile->collect_functions_ns : nullptr);
#endif
            CollectFunctions(impl_->declaration_snapshot_, &impl_->active_model_);
        }
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(profile ? &profile->collect_nominals_ns : nullptr);
#endif
            CollectNominals(
                source, impl_->declaration_snapshot_, &impl_->active_model_
            );
        }
#ifdef CANGJIE_ENABLE_REGEX_SHADOW
        RegexShadowProfileGuard profile_guard;
        Model reference_model = impl_->preload_;
        CollectImports(source, &reference_model);
        CollectFunctionsRegex(source, &reference_model);
        CollectNominalsRegex(source, &reference_model);
        if (!SameModel(impl_->active_model_, reference_model)) {
            throw std::logic_error(
                "declaration snapshot model diverged from regex shadow"
            );
        }
#endif
        impl_->model_source_bytes_ = source.size();
    }
    const bool has_var_let = HasBareVarLetKeyword(delta);
    const bool name_in_delta = has_var_let && HasDeclNameAfterKeyword(delta);
    const bool decl_completed =
        impl_->context_decl_pending_ &&
        delta.find('=') != std::string_view::npos;
    const bool context_dirty = impl_->context_source_bytes_ == 0 ||
        delta.find_first_of("{}\n\r;") != std::string_view::npos ||
        decl_completed || name_in_delta;
    if (context_dirty) {
#ifdef CANGJIE_ENABLE_PROFILE
        ProfileScopeTimer context_timer(profile ? &profile->context_rebuild_ns : nullptr);
        if (profile) {
            ++profile->context_rebuilds;
            profile->context_rebuild_source_bytes += source.size();
        }
#endif
        impl_->active_context_ = BuildFunctionContext(
            source, impl_->active_model_, impl_->declaration_snapshot_
        );
        impl_->context_source_bytes_ = source.size();
        impl_->context_decl_pending_ = has_var_let && !name_in_delta;
    } else if (has_var_let) {
        impl_->context_decl_pending_ = true;
    }
    impl_->source_bytes_ = source.size();
    impl_->last_partial_ = partial.text;
    ActiveStatementCache::Result active_statement;
    if (impl_->active_context_.in_function &&
        impl_->active_context_.body_start <= source.size()) {
        const std::size_t body_end = impl_->active_context_.body_end == std::string::npos
            ? source.size() : std::min(impl_->active_context_.body_end, source.size());
        active_statement = impl_->statement_cache_.Update(
            source, impl_->active_context_.body_start, body_end
        );
    } else {
        impl_->statement_cache_.Reset();
    }
#ifdef CANGJIE_ENABLE_PROFILE
    if (profile) ++profile->analyze_calls;
#endif
    CheckStatus status = AnalyzeSource(
        source, impl_->active_model_, impl_->declaration_snapshot_, model_dirty, commit_dirty,
        impl_->active_context_, std::move(active_statement)
#ifdef CANGJIE_ENABLE_PROFILE
        , profile
#endif
    );
    if (!status.ok) {
        impl_->SetLastFrontier(
            ClassifyFrontier(source, impl_->active_model_, impl_->active_context_)
        );
        impl_->SetLastWitness(
            ComputeShadowWitness(impl_->LastFrontier(), impl_->active_model_,
                                 impl_->active_context_, impl_->postfix_graph_,
                                 &impl_->witness_cache_, &impl_->witness_stats_)
        );
        impl_->SetLastCallFrontier(
            ComputeCallFrontier(impl_->LastFrontier(), impl_->active_model_,
                                impl_->active_context_)
        );
    } else {
        impl_->SetLastFrontier(FrontierInfo());
        impl_->SetLastWitness(RecoveryWitness());
        impl_->SetLastCallFrontier(CallFrontierResult());
        // 对已闭合调用补做重载穷尽检查，避免接受无法恢复的调用前缀。
        const std::string trimmed_source = Trim(source);
        if (!trimmed_source.empty() && trimmed_source.back() == ')') {
            const FrontierInfo cf = ClassifyFrontier(
                source, impl_->active_model_, impl_->active_context_);
            if (cf.tail_kind == TailKind::Call) {
                const CallFrontierResult call = ComputeCallFrontier(
                    cf, impl_->active_model_, impl_->active_context_);
                if (call.resolved && call.call_closed &&
                    call.overload_count > 0 && call.alive_count == 0) {
                    status.ok = false;
                    status.message =
                        "call close: all overload candidates eliminated";
                    impl_->SetLastFrontier(cf);
                    impl_->SetLastCallFrontier(call);
                }
            }
        }
    }
    // 使用续写证明复核拒绝结果，并记录可追踪的决策条目。
    if (!status.ok) {
        DecisionContext ctx = MakeDecisionContext(
            status.message, source, impl_->LastFrontier(), impl_->LastWitness(),
            impl_->LastCallFrontier()
        );
        DecisionLedgerEntry entry;
        status = DecideWithProof(status, ctx, &impl_->last_proof_, &entry);
        impl_->ledger_.push_back(std::move(entry));
    } else {
        impl_->last_proof_ = ContinuationProof();
    }
    return status;
}

// 保存检查进度（已接受 token 数与源码字节数）
Checkpoint IncrementalSemanticEngine::Save() const {
    return {impl_->accepted_.size(), impl_->source_bytes_};
}

// 回滚到指定检查进度（截断已接受 token，并重置语句缓存）
void IncrementalSemanticEngine::Rollback(const Checkpoint& checkpoint) {
    if (checkpoint.accepted_tokens < impl_->accepted_.size()) {
        impl_->accepted_.resize(checkpoint.accepted_tokens);
    }
    impl_->source_bytes_ = checkpoint.source_bytes;
    impl_->statement_cache_.Reset();
}

// 把预加载模型输出为 Context IR JSON。
void IncrementalSemanticEngine::DumpContextIrJson(std::ostream& os) const {
    impl_->DumpContextIrJson(os);
}

// 返回最近一次失败的前沿分类。
const FrontierInfo& IncrementalSemanticEngine::LastFrontier() const {
    return impl_->LastFrontier();
}

// 返回最近一次失败的恢复见证。
const RecoveryWitness& IncrementalSemanticEngine::LastWitness() const {
    return impl_->LastWitness();
}

// 返回恢复见证查询统计。
const WitnessStats& IncrementalSemanticEngine::WitnessStatistics() const {
    return impl_->WitnessStatistics();
}

// 返回最近一次调用的重载前沿。
const CallFrontierResult& IncrementalSemanticEngine::LastCallFrontier() const {
    return impl_->LastCallFrontier();
}

// 返回最近一次续写证明。
const ContinuationProof& IncrementalSemanticEngine::LastProof() const {
    return impl_->LastProof();
}

// 返回全部前缀决策账本记录。
const std::vector<DecisionLedgerEntry>& IncrementalSemanticEngine::DecisionLedger() const {
    return impl_->DecisionLedger();
}

}
