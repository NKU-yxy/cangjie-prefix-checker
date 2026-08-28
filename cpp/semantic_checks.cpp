#include "semantic_checks.h"

#include "semantic_constructor.h"
#include "semantic_control_flow.h"
#include "semantic_expression.h"
#include "semantic_profile.h"
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

// 检查类字段声明前缀规则（字段不能与参数/方法重名等）
CheckStatus CheckClassFieldPrefixRules(std::string_view source) {
    static const std::regex class_pattern(
        R"(\bclass\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>{}()]*>)?[^{}]*\{)"
    );
    static const std::regex member_pattern(
        R"((?:^|[\n\r])\s*(?:(?:public|private)\s+)?(?:static\s+)?(init|func\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>{}()]*>)?)\s*\([^{};]*\)\s*(?::\s*[^{}\n\r]+)?\s*\{)"
    );
    const std::string owned = MaskNonCodeText(source);
    for (std::sregex_iterator cls(owned.begin(), owned.end(), class_pattern), end;
         cls != end; ++cls) {
        const std::size_t class_open = static_cast<std::size_t>(
            (*cls).position() + (*cls).length() - 1
        );
        const auto class_close = MatchingDelimiter(owned, class_open, '{', '}');
        const std::string body = owned.substr(
            class_open + 1,
            class_close ? *class_close - class_open - 1 : owned.size() - class_open - 1
        );
        const auto fields = ScanTopLevelSourceFieldsMasked(body);
        if (class_close) {
            for (const auto& [_, field] : fields) {
                if (field.is_static && !field.has_initializer) {
                    return {false, "static field requires an initializer"};
                }
            }
            continue;
        }

        std::size_t active_open = std::string::npos;
        bool active_constructor = false;
        for (std::sregex_iterator member(body.begin(), body.end(), member_pattern), member_end;
             member != member_end; ++member) {
            const std::size_t position = static_cast<std::size_t>((*member).position());
            if (BraceDepthBefore(body, position) != 0) continue;
            const std::size_t open = position + static_cast<std::size_t>((*member).length()) - 1;
            if (!MatchingDelimiter(body, open, '{', '}')) {
                active_open = open;
                active_constructor = (*member)[1].str() == "init";
            }
        }
        if (active_open == std::string::npos) continue;
        const std::string member_body = body.substr(active_open + 1);

        static const std::regex assignment_tail(
            R"((?:^|[\n\r])\s*(?:this\s*\.\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^\n\r]+)$)"
        );
        std::smatch assignment;
        if (!active_constructor && std::regex_search(member_body, assignment, assignment_tail)) {
            const auto field = fields.find(assignment[1].str());
            if (field != fields.end() && !field->second.mutable_field &&
                !Trim(assignment[2].str()).empty()) {
                return {false, "assignment to immutable field"};
            }
        }

    }
    return CheckConstructorFieldInitialization(source);
}

// 检查函数声明前缀的初始化器（默认参数等）是否合法
CheckStatus CheckFunctionInitializerPrefix(
    std::string_view source,
    const Model& model
) {
    if (source.empty() || !IsIdentContinue(static_cast<unsigned char>(source.back()))) {
        return {};
    }
    static const std::regex declaration_tail(
        R"((?:^|[\n\r])\s*(?:let|var)\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*([^=\n\r{}]+)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)$)"
    );
    const std::string owned(source);
    std::smatch match;
    if (!std::regex_search(owned, match, declaration_tail)) return {};
    const std::string expected = CompactType(match[1].str());
    const std::string name = match[2].str();
    for (const auto& [candidate, _] : model.functions) {
        if (candidate != name && StartsWith(candidate, name)) return {};
    }
    const auto signatures = model.functions.find(name);
    if (signatures == model.functions.end()) return {};
    for (const FunctionSig& signature : signatures->second) {
        if (signature.required != 0 || !signature.type_params.empty()) return {};
    }
    for (const FunctionSig& signature : signatures->second) {
        if (Compatible(signature.result, expected, model)) return {};
        std::string function_type = "(";
        for (std::size_t index = 0; index < signature.param_types.size(); ++index) {
            if (index) function_type += ",";
            function_type += signature.param_types[index];
        }
        function_type += ")->" + signature.result;
        if (Compatible(function_type, expected, model)) return {};
    }
    return {false, "function initializer cannot match annotated type"};
}

// 检查声明前缀：函数初始化器、类字段规则、重复参数与未定义类型
CheckStatus CheckDeclarationPrefixes(std::string_view source, const Model& model) {
    const std::string owned(source);
    static const std::regex forbidden_func_main(
        R"((?:^|[\n\r])\s*(?:(?:public|private)\s+)?(?:static\s+)?func\s+main\s*\()"
    );
    if (std::regex_search(owned, forbidden_func_main)) {
        return {false, "func main is forbidden"};
    }

    static const std::regex closed_type_parameters(
        R"(\b(?:func\s+[A-Za-z_][A-Za-z0-9_]*|class\s+[A-Za-z_][A-Za-z0-9_]*|interface\s+[A-Za-z_][A-Za-z0-9_]*)\s*<([^>{}()\n\r]*)>)"
    );
    static const std::unordered_set<std::string> reserved = {
        "Int64", "Float64", "Bool", "Rune", "Unit"
    };
    std::unordered_set<std::string> type_parameters;
    for (std::sregex_iterator it(owned.begin(), owned.end(), closed_type_parameters), end;
         it != end; ++it) {
        std::unordered_set<std::string> seen;
        for (const std::string& item : SplitTopLevel((*it)[1].str(), ',')) {
            const std::string name = Trim(item);
            if (!IsIdentifierText(name)) continue;
            if (reserved.count(name)) return {false, "type parameter conflicts with primitive"};
            if (!seen.insert(name).second) return {false, "duplicate type parameter"};
            type_parameters.insert(name);
        }
    }

    if (!source.empty() && IsIdentContinue(static_cast<unsigned char>(source.back()))) {
        static const std::regex local_type_tail(
            R"((?:^|[\n\r])\s*(?:let|var)\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*([^=\n\r{}]*)$)"
        );
        std::smatch local_type;
        if (std::regex_search(owned, local_type, local_type_tail)) {
            const std::string type_text = local_type[1].str();
            std::size_t start = type_text.size();
            while (start > 0 && IsIdentContinue(
                       static_cast<unsigned char>(type_text[start - 1]))) --start;
            const std::string prefix = type_text.substr(start);
            if (!prefix.empty() && !HasKnownTypePrefix(prefix, model, type_parameters)) {
                return {false, "unknown local type"};
            }
        }

        static const std::regex super_tail(
            R"((?:^|[\n\r])\s*(?:class|interface)\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>{}()]*>)?\s*<:\s*([^{}\n\r]*)$)"
        );
        std::smatch super_header;
        if (std::regex_search(owned, super_header, super_tail)) {
            const std::string supers = super_header[1].str();
            const std::size_t ampersand = supers.rfind('&');
            const std::string current = Trim(std::string_view(supers).substr(
                ampersand == std::string::npos ? 0 : ampersand + 1
            ));
            if (IsIdentifierText(current) &&
                !HasKnownTypePrefix(current, model, type_parameters)) {
                return {false, "unknown supertype prefix"};
            }
        }
    }

    if (CheckStatus status = CheckFunctionInitializerPrefix(source, model); !status.ok) {
        return status;
    }
    if (CheckStatus status = CheckClassFieldPrefixRules(source); !status.ok) {
        return status;
    }
    return CheckClassMemberNameCollisions(source);
}

// 检查函数体内局部变量是否存在重复声明
CheckStatus CheckDuplicateLocalDeclarations(const FunctionContext& context) {
    if (!context.in_function || context.body.empty()) return {};
    std::vector<std::unordered_set<std::string>> scopes(1);
    bool in_string = false;
    bool triple_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    for (std::size_t index = 0; index < context.body.size(); ++index) {
        const char ch = context.body[index];
        const char next = index + 1 < context.body.size()
            ? context.body[index + 1] : '\0';
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
                if (index + 2 < context.body.size() &&
                    std::string_view(context.body).substr(index, 3) == "\"\"\"") {
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
            triple_string = index + 2 < context.body.size() &&
                std::string_view(context.body).substr(index, 3) == "\"\"\"";
            in_string = true;
            if (triple_string) index += 2;
            continue;
        }
        if (ch == '{') {
            scopes.emplace_back();
            continue;
        }
        if (ch == '}') {
            if (scopes.size() > 1) scopes.pop_back();
            continue;
        }
        if (!IsIdentStart(static_cast<unsigned char>(ch))) continue;
        std::size_t word_end = index + 1;
        while (word_end < context.body.size() &&
               IsIdentContinue(static_cast<unsigned char>(context.body[word_end]))) {
            ++word_end;
        }
        const std::string_view keyword = std::string_view(context.body).substr(
            index, word_end - index
        );
        if (keyword != "let" && keyword != "var") {
            index = word_end - 1;
            continue;
        }
        std::size_t name_start = word_end;
        while (name_start < context.body.size() &&
               std::isspace(static_cast<unsigned char>(context.body[name_start]))) {
            ++name_start;
        }
        if (name_start >= context.body.size() ||
            !IsIdentStart(static_cast<unsigned char>(context.body[name_start]))) {
            index = word_end - 1;
            continue;
        }
        std::size_t name_end = name_start + 1;
        while (name_end < context.body.size() &&
               IsIdentContinue(static_cast<unsigned char>(context.body[name_end]))) {
            ++name_end;
        }
        const std::string name = context.body.substr(
            name_start, name_end - name_start
        );
        const std::size_t declaration_operator = SkipLoopLineTrivia(
            context.body, name_end
        );
        if (declaration_operator >= context.body.size() ||
            (context.body[declaration_operator] != ':' &&
             context.body[declaration_operator] != '=')) {
            index = name_end - 1;
            continue;
        }
        if (!scopes.back().insert(name).second) {
            return {false, "duplicate local declaration"};
        }
        index = name_end - 1;
    }
    return {};
}

// 检查泛型前缀：泛型实参个数、类型已知性与替换后的类型兼容性
CheckStatus CheckGenericPrefix(std::string_view source, const Model& model) {
    std::size_t end = source.size();
    while (end > 0 && std::isspace(static_cast<unsigned char>(source[end - 1]))) --end;
    const std::size_t open = source.rfind('<', end == 0 ? 0 : end - 1);
    if (open == std::string::npos) return {};
    if (open + 1 < source.size() && source[open + 1] == ':') return {};
    const std::size_t close = source.find('>', open);
    if (close != std::string::npos && close < end) return {};
    std::size_t name_end = open;
    while (name_end > 0 && std::isspace(static_cast<unsigned char>(source[name_end - 1]))) --name_end;
    std::size_t name_start = name_end;
    while (name_start > 0 && IsIdentContinue(static_cast<unsigned char>(source[name_start - 1]))) --name_start;
    const std::string name(source.substr(name_start, name_end - name_start));
    std::size_t arity = 0;
    if (const auto function = model.functions.find(name); function != model.functions.end() && !function->second.empty()) {
        arity = function->second.front().type_params.size();
    } else if (const auto nominal = model.nominals.find(name); nominal != model.nominals.end()) {
        arity = nominal->second.type_params.size();
    } else {
        return {};
    }
    const std::string inside(source.substr(open + 1, end - open - 1));
    const auto args = SplitTopLevel(inside, ',');
    const std::size_t supplied = args.size();
    if (supplied > arity || (arity == 0 && !inside.empty())) return {false, "wrong generic arity"};
    return {};
}

// 按类型参数映射替换函数签名中的类型。
FunctionSig SubstituteSignature(
    const FunctionSig& input,
    const std::unordered_map<std::string, std::string>& substitutions
) {
    FunctionSig output = input;
    for (std::string& type : output.param_types) {
        type = ApplySubstitution(type, substitutions);
    }
    output.result = ApplySubstitution(output.result, substitutions);
    return output;
}

// 判断接口实现方法签名是否满足接口要求（参数与返回类型匹配）
bool SameInterfaceSignature(const FunctionSig& implementation, const FunctionSig& requirement) {
    if (implementation.type_params.size() != requirement.type_params.size() ||
        implementation.param_types.size() != requirement.param_types.size()) {
        return false;
    }
    std::unordered_map<std::string, std::string> method_parameters;
    for (std::size_t index = 0; index < requirement.type_params.size(); ++index) {
        method_parameters[requirement.type_params[index]] = implementation.type_params[index];
    }
    const FunctionSig normalized_requirement = SubstituteSignature(requirement, method_parameters);
    for (std::size_t index = 0; index < implementation.param_types.size(); ++index) {
        if (CompactType(implementation.param_types[index]) !=
            CompactType(normalized_requirement.param_types[index])) {
            return false;
        }
    }
    return CompactType(implementation.result) == CompactType(normalized_requirement.result);
}

// 判断签名中的参数和返回类型是否全部已知。
bool SignatureTypesAreKnown(
    const FunctionSig& signature,
    const NominalInfo& owner,
    const Model& model
) {
    std::unordered_set<std::string> allowed(
        owner.type_params.begin(), owner.type_params.end()
    );
    allowed.insert(signature.type_params.begin(), signature.type_params.end());
    if (!KnownDeclaredType(signature.result, model, allowed)) return false;
    return std::all_of(
        signature.param_types.begin(), signature.param_types.end(),
        [&](const std::string& type) {
            return KnownDeclaredType(type, model, allowed);
        }
    );
}

// 递归收集接口及其父接口的方法要求。
void CollectInterfaceRequirements(
    std::string interface_type,
    const Model& model,
    std::unordered_map<std::string, std::vector<FunctionSig>>* requirements,
    std::unordered_set<std::string>* visited,
    bool static_methods
) {
    interface_type = CompactType(interface_type);
    if (!visited->insert(interface_type).second) return;
    const auto interface = model.nominals.find(TypeHead(interface_type));
    if (interface == model.nominals.end() || !interface->second.is_interface) return;
    std::unordered_map<std::string, std::string> substitutions;
    const auto arguments = TypeArgs(interface_type);
    for (std::size_t index = 0;
         index < arguments.size() && index < interface->second.type_params.size(); ++index) {
        substitutions[interface->second.type_params[index]] = arguments[index];
    }
    const auto& methods = static_methods
        ? interface->second.static_methods : interface->second.methods;
    for (const auto& [method_name, signatures] : methods) {
        auto& target = (*requirements)[method_name];
        for (const FunctionSig& signature : signatures) {
            target.push_back(SubstituteSignature(signature, substitutions));
        }
    }
    for (const std::string& super : interface->second.supers) {
        CollectInterfaceRequirements(
            ApplySubstitution(super, substitutions), model, requirements, visited,
            static_methods
        );
    }
}

// 检查类方法是否满足一组接口方法要求。
CheckStatus CheckInterfaceRequirementSet(
    const std::string& class_name,
    const NominalInfo& cls,
    const Model& model,
    const std::unordered_map<std::string, std::vector<FunctionSig>>& requirements,
    const std::unordered_map<std::string, std::vector<FunctionSig>>& implementations,
    bool class_closed,
    bool reject_mismatch_while_open
) {
    for (const auto& [method_name, required_signatures] : requirements) {
        const auto implementation = implementations.find(method_name);
        if (implementation == implementations.end()) continue;
        for (const FunctionSig& requirement : required_signatures) {
            bool has_complete_candidate = false;
            bool matched = false;
            for (const FunctionSig& candidate : implementation->second) {
                if (!SignatureTypesAreKnown(candidate, cls, model)) continue;
                has_complete_candidate = true;
                if (SameInterfaceSignature(candidate, requirement)) {
                    matched = true;
                    break;
                }
            }
            if (has_complete_candidate && !matched &&
                (class_closed || reject_mismatch_while_open)) {
                if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
                    std::cerr << "interface mismatch " << class_name << "." << method_name
                              << ", required=" << requirement.result << '\n';
                }
                return {false, "interface method signature mismatch"};
            }
        }
    }
    if (!class_closed) return {};
    for (const auto& [method_name, _] : requirements) {
        if (!implementations.count(method_name)) {
            return {false, "interface method not implemented"};
        }
    }
    return {};
}

// 从声明快照记录检查接口实现：每个接口方法要求都有匹配的实现
CheckStatus CheckInterfacesFromRecords(
    const std::vector<DeclarationRecord>& class_records,
    const Model& model
) {
    for (const DeclarationRecord& record : class_records) {
        const std::string& name = SnapshotCaptureAt(record, 1).text;
        const auto cls = model.nominals.find(name);
        if (cls == model.nominals.end()) continue;
        std::unordered_map<std::string, std::vector<FunctionSig>> instance_requirements;
        std::unordered_map<std::string, std::vector<FunctionSig>> static_requirements;
        std::unordered_set<std::string> visited_instance_interfaces;
        std::unordered_set<std::string> visited_static_interfaces;
        for (const std::string& super_type : cls->second.supers) {
            CollectInterfaceRequirements(
                super_type, model, &instance_requirements,
                &visited_instance_interfaces, false
            );
            CollectInterfaceRequirements(
                super_type, model, &static_requirements,
                &visited_static_interfaces, true
            );
        }
        CheckStatus status = CheckInterfaceRequirementSet(
            name, cls->second, model, instance_requirements,
            cls->second.methods, record.close.has_value(), true
        );
        if (!status.ok) return status;
        status = CheckInterfaceRequirementSet(
            name, cls->second, model, static_requirements,
            cls->second.static_methods, record.close.has_value(), false
        );
        if (!status.ok) return status;
    }
    return {};
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 使用正则旧实现检查接口实现完整性。
CheckStatus CheckInterfacesRegex(std::string_view source, const Model& model) {
    static const std::regex class_pattern(
        R"(\bclass\s+([A-Za-z_][A-Za-z0-9_]*)[^{}]*\{)"
    );
    const std::string owned(source);
    for (std::sregex_iterator it(owned.begin(), owned.end(), class_pattern), end;
         it != end; ++it) {
        const std::string name = (*it)[1].str();
        const auto cls = model.nominals.find(name);
        if (cls == model.nominals.end()) continue;
        std::unordered_map<std::string, std::vector<FunctionSig>> instance_requirements;
        std::unordered_map<std::string, std::vector<FunctionSig>> static_requirements;
        std::unordered_set<std::string> visited_instance_interfaces;
        std::unordered_set<std::string> visited_static_interfaces;
        for (const std::string& super_type : cls->second.supers) {
            CollectInterfaceRequirements(
                super_type, model, &instance_requirements,
                &visited_instance_interfaces, false
            );
            CollectInterfaceRequirements(
                super_type, model, &static_requirements,
                &visited_static_interfaces, true
            );
        }
        const std::size_t open = static_cast<std::size_t>(
            (*it).position() + (*it).length() - 1
        );
        const bool class_closed = MatchingDelimiter(owned, open, '{', '}').has_value();
        CheckStatus status = CheckInterfaceRequirementSet(
            name, cls->second, model, instance_requirements,
            cls->second.methods, class_closed, true
        );
        if (!status.ok) return status;
        status = CheckInterfaceRequirementSet(
            name, cls->second, model, static_requirements,
            cls->second.static_methods, class_closed, false
        );
        if (!status.ok) return status;
    }
    return {};
}
#endif

// 检查接口实现完整性（入口，基于声明快照）
CheckStatus CheckInterfaces(
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot
) {
    const CheckStatus result = CheckInterfacesFromRecords(snapshot.broad_classes, model);
#ifdef CANGJIE_ENABLE_REGEX_SHADOW
    RegexShadowProfileGuard profile_guard;
    const CheckStatus reference = CheckInterfacesRegex(source, model);
    if (result.ok != reference.ok || result.message != reference.message) {
        throw std::logic_error("declaration snapshot interface check diverged from regex shadow");
    }
#else
    (void)source;
#endif
    return result;
}

// 检查 for 循环 range（起点..终点:步长）的类型：必须为整数且端点同型
CheckStatus CheckRangeSteps(std::string_view source, const Model& model) {
    static const std::regex loop_pattern(R"(\bfor\s*\([^)]*\bin\s+([^)]*)\))");
#ifdef CANGJIE_ENABLE_PROFILE
    std::string owned;
    {
        ProfileScopeTimer timer(g_profile ? &g_profile->range_source_copy_ns : nullptr);
        owned.assign(source.data(), source.size());
    }
#else
    const std::string owned(source);
#endif
    FunctionContext context;
    ExpressionTyper typer(model, context, source);
#ifdef CANGJIE_ENABLE_PROFILE
    std::sregex_iterator it;
    {
        ProfileScopeTimer timer(g_profile ? &g_profile->range_regex_ns : nullptr);
        it = std::sregex_iterator(owned.begin(), owned.end(), loop_pattern);
    }
    const std::sregex_iterator end;
    for (; it != end;) {
#else
    for (std::sregex_iterator it(owned.begin(), owned.end(), loop_pattern), end;
         it != end; ++it) {
#endif
#ifdef CANGJIE_ENABLE_PROFILE
        const std::smatch match = *it;
        {
            ProfileScopeTimer timer(g_profile ? &g_profile->range_regex_ns : nullptr);
            ++it;
        }
#else
        const std::smatch& match = *it;
#endif
        const std::string range = match[1].str();
        const std::size_t dots = range.find("..");
        if (dots == std::string::npos) continue;
        const std::string left_text = Trim(std::string_view(range).substr(0, dots));
        std::string remainder = Trim(std::string_view(range).substr(dots + 2));
        if (!remainder.empty() && remainder.front() == '=') remainder.erase(remainder.begin());
        const std::size_t colon = FindTopLevel(remainder, ":");
        const std::string right_text = Trim(std::string_view(remainder).substr(0, colon));
        const std::string step_text = colon == std::string::npos
            ? "" : Trim(std::string_view(remainder).substr(colon + 1));
        ExprResult left;
        ExprResult right;
        ExprResult step;
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(g_profile ? &g_profile->range_infer_ns : nullptr);
#endif
            left = typer.Infer(left_text);
            right = typer.Infer(right_text);
            step = typer.Infer(step_text);
        }
        auto integral = [](const ExprResult& value) {
            return !value.known || IsInteger(value.type) || value.type == "Rune";
        };
        if (!integral(left) || !integral(right) || !integral(step)) {
            return {false, "range components must be integral"};
        }
        if (left.known && right.known && left.type != right.type) {
            return {false, "range endpoints must share type"};
        }
        if (left.known && step.known && left.type != step.type) {
            return {false, "range step must share type"};
        }
    }
    return {};
}

// 检查 if-else 两个分支的表达式类型能否合流为同一类型
CheckStatus CheckIfBranchJoins(std::string_view source, const Model& model) {
    static const std::regex if_pattern(
        R"(\bif\s*\([^{}]*\)\s*\{\s*([^{};]+?)\s*\}\s*else\s*\{\s*([^{};]+?)\s*\})"
    );
#ifdef CANGJIE_ENABLE_PROFILE
    std::string owned;
    {
        ProfileScopeTimer timer(g_profile ? &g_profile->branch_source_copy_ns : nullptr);
        owned.assign(source.data(), source.size());
    }
#else
    const std::string owned(source);
#endif
    FunctionContext context;
    ExpressionTyper typer(model, context, source);
#ifdef CANGJIE_ENABLE_PROFILE
    std::sregex_iterator it;
    {
        ProfileScopeTimer timer(g_profile ? &g_profile->branch_regex_ns : nullptr);
        it = std::sregex_iterator(owned.begin(), owned.end(), if_pattern);
    }
    const std::sregex_iterator end;
    for (; it != end;) {
#else
    for (std::sregex_iterator it(owned.begin(), owned.end(), if_pattern), end;
         it != end; ++it) {
#endif
#ifdef CANGJIE_ENABLE_PROFILE
        const std::smatch match = *it;
        {
            ProfileScopeTimer timer(g_profile ? &g_profile->branch_regex_ns : nullptr);
            ++it;
        }
#else
        const std::smatch& match = *it;
#endif
        ExprResult left;
        ExprResult right;
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(g_profile ? &g_profile->branch_infer_ns : nullptr);
#endif
            left = typer.Infer(match[1].str());
            right = typer.Infer(match[2].str());
        }
        if (!left.known || !right.known || left.error || right.error) continue;
        bool joined = false;
        {
#ifdef CANGJIE_ENABLE_PROFILE
            ProfileScopeTimer timer(g_profile ? &g_profile->branch_compatible_ns : nullptr);
#endif
            joined = Compatible(left.type, right.type, model) ||
                Compatible(right.type, left.type, model);
            if (!joined) {
                for (const auto& [name, nominal] : model.nominals) {
                    if (!nominal.is_interface) continue;
                    if (Compatible(left.type, name, model) &&
                        Compatible(right.type, name, model)) {
                        joined = true;
                        break;
                    }
                }
            }
        }
        if (!joined) return {false, "if branch types cannot be joined"};
    }
    return {};
}

// 从声明快照记录检查构造器：参数个数、类型与字段初始化
CheckStatus CheckConstructorsFromRecords(
    std::string_view source,
    const Model& model,
    const std::vector<DeclarationRecord>& class_records
) {
    static const std::regex init_pattern(R"(\binit\s*\([^{};\n]*\)\s*\{)");
    static const std::regex return_value(R"(\breturn\s+([^;{}\n]+))");
    static const std::regex delegated(R"(\bthis\s*\(([^()]*)\))");
    static const std::regex this_member(R"(\bthis\s*\.\s*([A-Za-z_][A-Za-z0-9_]*))");
    const std::string owned(source);
    for (const DeclarationRecord& record : class_records) {
        const std::string& class_name = SnapshotCaptureAt(record, 1).text;
        const auto info = model.nominals.find(class_name);
        if (info == model.nominals.end()) continue;
        const std::size_t class_open = record.open;
        const std::optional<std::size_t>& class_close = record.close;
        const std::string body = owned.substr(
            class_open + 1,
            class_close ? *class_close - class_open - 1 : owned.size() - class_open - 1
        );
        const std::string masked_body = MaskNonCodeText(body);
        for (std::sregex_iterator init_it(masked_body.begin(), masked_body.end(), init_pattern), init_end;
             init_it != init_end; ++init_it) {
            const std::size_t init_open = static_cast<std::size_t>(
                (*init_it).position() + (*init_it).length() - 1
            );
            const auto init_close = MatchingDelimiter(masked_body, init_open, '{', '}');
            const std::string init_body = masked_body.substr(
                init_open + 1,
                init_close ? *init_close - init_open - 1 : masked_body.size() - init_open - 1
            );
            if (std::regex_search(init_body, return_value)) {
                return {false, "constructor cannot return a value"};
            }
            std::smatch delegation;
            if (std::regex_search(init_body, delegation, delegated)) {
                FunctionContext context;
                ExpressionTyper typer(model, context, source);
                ExprResult call = typer.Infer(class_name + "(" + delegation[1].str() + ")");
                if (call.error) return {false, "delegated constructor mismatch"};
            }
            for (std::sregex_iterator member(init_body.begin(), init_body.end(), this_member), member_end;
                 member != member_end; ++member) {
                const std::string name = (*member)[1].str();
                if (!info->second.fields.count(name) && !info->second.methods.count(name)) {
                    return {false, "unknown this member"};
                }
            }
        }
    }
    return {};
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 使用正则旧实现检查构造器调用。
CheckStatus CheckConstructorsRegex(std::string_view source, const Model& model) {
    static const std::regex class_pattern(
        R"(\bclass\s+([A-Za-z_][A-Za-z0-9_]*)[^{}]*\{)"
    );
    static const std::regex init_pattern(R"(\binit\s*\([^{};\n]*\)\s*\{)");
    static const std::regex return_value(R"(\breturn\s+([^;{}\n]+))");
    static const std::regex delegated(R"(\bthis\s*\(([^()]*)\))");
    static const std::regex this_member(
        R"(\bthis\s*\.\s*([A-Za-z_][A-Za-z0-9_]*))"
    );
    const std::string owned(source);
    for (std::sregex_iterator cls_it(owned.begin(), owned.end(), class_pattern), end;
         cls_it != end; ++cls_it) {
        const std::string class_name = (*cls_it)[1].str();
        const auto info = model.nominals.find(class_name);
        if (info == model.nominals.end()) continue;
        const std::size_t class_open = static_cast<std::size_t>(
            (*cls_it).position() + (*cls_it).length() - 1
        );
        const auto class_close = MatchingDelimiter(owned, class_open, '{', '}');
        const std::string body = owned.substr(
            class_open + 1,
            class_close ? *class_close - class_open - 1 : owned.size() - class_open - 1
        );
        const std::string masked_body = MaskNonCodeText(body);
        for (std::sregex_iterator init_it(masked_body.begin(), masked_body.end(), init_pattern), init_end;
             init_it != init_end; ++init_it) {
            const std::size_t init_open = static_cast<std::size_t>(
                (*init_it).position() + (*init_it).length() - 1
            );
            const auto init_close = MatchingDelimiter(masked_body, init_open, '{', '}');
            const std::string init_body = masked_body.substr(
                init_open + 1,
                init_close ? *init_close - init_open - 1 : masked_body.size() - init_open - 1
            );
            if (std::regex_search(init_body, return_value)) {
                return {false, "constructor cannot return a value"};
            }
            std::smatch delegation;
            if (std::regex_search(init_body, delegation, delegated)) {
                FunctionContext context;
                ExpressionTyper typer(model, context, source);
                ExprResult call = typer.Infer(
                    class_name + "(" + delegation[1].str() + ")"
                );
                if (call.error) return {false, "delegated constructor mismatch"};
            }
            for (std::sregex_iterator member(
                     init_body.begin(), init_body.end(), this_member), member_end;
                 member != member_end; ++member) {
                const std::string name = (*member)[1].str();
                if (!info->second.fields.count(name) &&
                    !info->second.methods.count(name)) {
                    return {false, "unknown this member"};
                }
            }
        }
    }
    return {};
}
#endif

// 检查所有构造器声明（入口，基于声明快照）
CheckStatus CheckConstructors(
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot
) {
    const CheckStatus result = CheckConstructorsFromRecords(
        source, model, snapshot.broad_classes
    );
#ifdef CANGJIE_ENABLE_REGEX_SHADOW
    RegexShadowProfileGuard profile_guard;
    const CheckStatus reference = CheckConstructorsRegex(source, model);
    if (result.ok != reference.ok || result.message != reference.message) {
        throw std::logic_error("declaration snapshot constructor check diverged from regex shadow");
    }
#endif
    return result;
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 使用正则旧实现检查畸形泛型构造。
CheckStatus CheckMalformedGenericConstructRegex(std::string_view source) {
    static const std::regex malformed(
        R"(\b(?:let|var)\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*:[^=;{}\n]+)?\s*=\s*[A-Z][A-Za-z0-9_]*<[^>;{}\n]*\([^;{}\n]*\)\s*;)"
    );
    static const std::regex malformed_binding(
        R"(\b(?:let|var)\s+[A-Za-z_][A-Za-z0-9_]*\s+[+\-*/%]\s*[A-Za-z_][A-Za-z0-9_]*\s*=)"
    );
    const std::string owned(source);
    if (std::regex_search(owned, malformed)) return {false, "malformed generic construction"};
    if (std::regex_search(owned, malformed_binding)) return {false, "malformed variable declaration"};
    return {};
}
#endif

// 判断字符能否作为线性扫描中的标识符首字符。
bool IsRegexIdentifierStart(char ch) {
    return (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || ch == '_';
}

// 判断字符能否作为线性扫描中的标识符后续字符。
bool IsRegexIdentifierContinue(char ch) {
    return IsRegexIdentifierStart(ch) || (ch >= '0' && ch <= '9');
}

// 跳过线性声明扫描中的空白字符。
std::size_t SkipRegexWhitespace(std::string_view source, std::size_t cursor) {
    while (cursor < source.size() &&
           std::isspace(static_cast<unsigned char>(source[cursor]))) {
        ++cursor;
    }
    return cursor;
}

// 返回线性扫描中标识符结束位置。
std::size_t ParseRegexIdentifier(std::string_view source, std::size_t cursor) {
    if (cursor >= source.size() || !IsRegexIdentifierStart(source[cursor])) {
        return std::string_view::npos;
    }
    do {
        ++cursor;
    } while (cursor < source.size() && IsRegexIdentifierContinue(source[cursor]));
    return cursor;
}

// 判断当前位置是否开始了畸形泛型构造。
bool MalformedGenericAt(std::string_view source, std::size_t cursor) {
    const std::size_t whitespace = cursor;
    cursor = SkipRegexWhitespace(source, cursor);
    if (cursor == whitespace) return false;
    cursor = ParseRegexIdentifier(source, cursor);
    if (cursor == std::string_view::npos) return false;

    cursor = SkipRegexWhitespace(source, cursor);
    if (cursor < source.size() && source[cursor] == ':') {
        const std::size_t type_start = ++cursor;
        while (cursor < source.size() && source[cursor] != '=' &&
               source[cursor] != ';' && source[cursor] != '{' &&
               source[cursor] != '}' && source[cursor] != '\n') {
            ++cursor;
        }
        if (cursor == type_start) return false;
    }
    cursor = SkipRegexWhitespace(source, cursor);
    if (cursor >= source.size() || source[cursor++] != '=') return false;
    cursor = SkipRegexWhitespace(source, cursor);
    if (cursor >= source.size() || source[cursor] < 'A' || source[cursor] > 'Z') {
        return false;
    }
    do {
        ++cursor;
    } while (cursor < source.size() && IsRegexIdentifierContinue(source[cursor]));
    if (cursor >= source.size() || source[cursor++] != '<') return false;

    while (cursor < source.size() && source[cursor] != '(') {
        const char ch = source[cursor++];
        if (ch == '>' || ch == ';' || ch == '{' || ch == '}' || ch == '\n') {
            return false;
        }
    }
    if (cursor >= source.size()) return false;
    ++cursor;
    while (cursor < source.size() && source[cursor] != ';') {
        const char ch = source[cursor++];
        if (ch == '{' || ch == '}' || ch == '\n') return false;
    }
    if (cursor >= source.size()) return false;
    std::size_t before_semicolon = cursor;
    while (before_semicolon > 0 &&
           std::isspace(static_cast<unsigned char>(source[before_semicolon - 1]))) {
        --before_semicolon;
    }
    return before_semicolon > 0 && source[before_semicolon - 1] == ')';
}

// 判断当前位置是否开始了畸形变量绑定。
bool MalformedBindingAt(std::string_view source, std::size_t cursor) {
    const std::size_t first_whitespace = cursor;
    cursor = SkipRegexWhitespace(source, cursor);
    if (cursor == first_whitespace) return false;
    cursor = ParseRegexIdentifier(source, cursor);
    if (cursor == std::string_view::npos) return false;
    const std::size_t operator_whitespace = cursor;
    cursor = SkipRegexWhitespace(source, cursor);
    if (cursor == operator_whitespace || cursor >= source.size() ||
        std::string_view("+-*/%").find(source[cursor]) == std::string_view::npos) {
        return false;
    }
    ++cursor;
    const std::size_t name_whitespace = cursor;
    cursor = SkipRegexWhitespace(source, cursor);
    if (cursor == name_whitespace) return false;
    cursor = ParseRegexIdentifier(source, cursor);
    if (cursor == std::string_view::npos) return false;
    cursor = SkipRegexWhitespace(source, cursor);
    return cursor < source.size() && source[cursor] == '=';
}

// 使用线性扫描检查畸形泛型构造和绑定。
CheckStatus CheckMalformedGenericConstructLinear(std::string_view source) {
    for (std::size_t cursor = 0; cursor < source.size(); ++cursor) {
        if (cursor > 0 && IsRegexIdentifierContinue(source[cursor - 1])) continue;
        std::size_t after_keyword = std::string_view::npos;
        if (source.substr(cursor, 3) == "let") {
            after_keyword = cursor + 3;
        } else if (source.substr(cursor, 3) == "var") {
            after_keyword = cursor + 3;
        }
        if (after_keyword == std::string_view::npos ||
            after_keyword >= source.size() ||
            !std::isspace(static_cast<unsigned char>(source[after_keyword]))) {
            continue;
        }
        if (MalformedGenericAt(source, after_keyword)) {
            return {false, "malformed generic construction"};
        }
        if (MalformedBindingAt(source, after_keyword)) {
            return {false, "malformed variable declaration"};
        }
    }
    return {};
}

// 检查畸形泛型构造（如 Box<Int64(1) 缺少 ">" 或绑定不完整）
CheckStatus CheckMalformedGenericConstruct(std::string_view source) {
    const CheckStatus result = CheckMalformedGenericConstructLinear(source);
#ifdef CANGJIE_ENABLE_REGEX_SHADOW
    const CheckStatus reference = CheckMalformedGenericConstructRegex(source);
    if (result.ok != reference.ok || result.message != reference.message) {
        throw std::logic_error("linear malformed-generic check diverged from regex shadow");
    }
#endif
    return result;
}


}
