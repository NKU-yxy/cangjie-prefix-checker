#include "native_semantic.h"

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

#ifdef CANGJIE_ENABLE_PROFILE
class ProfileScopeTimer {
 public:
    explicit ProfileScopeTimer(std::uint64_t* target)
        : target_(target), started_(std::chrono::steady_clock::now()) {}

    ~ProfileScopeTimer() {
        if (!target_) return;
        *target_ += static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - started_
            ).count()
        );
    }

 private:
    std::uint64_t* target_;
    std::chrono::steady_clock::time_point started_;
};

struct ProfileCounters {
    bool enabled = std::getenv("CANGJIE_PROFILE") != nullptr;
    std::uint64_t accepted_events = 0;
    std::uint64_t probe_calls = 0;
    std::uint64_t indentation_fast_paths = 0;
    std::uint64_t brace_scan_bytes = 0;
    std::uint64_t model_rebuilds = 0;
    std::uint64_t model_rebuild_source_bytes = 0;
    std::uint64_t declaration_snapshot_rebuilds = 0;
    std::uint64_t declaration_snapshot_source_bytes = 0;
    std::uint64_t declaration_snapshot_records = 0;
    std::uint64_t context_rebuilds = 0;
    std::uint64_t context_rebuild_source_bytes = 0;
    std::uint64_t analyze_calls = 0;
    std::uint64_t context_copy_payload_bytes = 0;
    std::uint64_t duplicate_parameter_checks = 0;
    std::uint64_t declared_type_checks = 0;
    std::uint64_t interface_checks = 0;
    std::uint64_t constructor_checks = 0;
    std::uint64_t range_checks = 0;
    std::uint64_t branch_join_checks = 0;
    std::uint64_t malformed_generic_checks = 0;
    std::uint64_t generic_prefix_checks = 0;
    std::uint64_t unclosed_string_scan_bytes = 0;
    std::uint64_t analyze_total_ns = 0;
    std::uint64_t duplicate_parameter_ns = 0;
    std::uint64_t declared_type_ns = 0;
    std::uint64_t interface_ns = 0;
    std::uint64_t constructor_ns = 0;
    std::uint64_t range_ns = 0;
    std::uint64_t branch_join_ns = 0;
    std::uint64_t malformed_generic_ns = 0;
    std::uint64_t generic_prefix_ns = 0;
    std::uint64_t brace_scan_ns = 0;
    std::uint64_t model_rebuild_ns = 0;
    std::uint64_t declaration_snapshot_build_ns = 0;
    std::uint64_t model_reset_ns = 0;
    std::uint64_t collect_imports_ns = 0;
    std::uint64_t collect_functions_ns = 0;
    std::uint64_t collect_nominals_ns = 0;
    std::uint64_t context_rebuild_ns = 0;
    std::uint64_t context_current_function_ns = 0;
    std::uint64_t context_local_variables_ns = 0;
    std::uint64_t context_class_fields_ns = 0;
    std::uint64_t context_inferred_variables_ns = 0;
    std::uint64_t context_lambda_variables_ns = 0;
    std::uint64_t context_for_binding_ns = 0;
    std::uint64_t type_generations = 0;
    std::uint64_t compact_type_calls = 0;
    std::uint64_t compact_type_ns = 0;
    std::uint64_t compact_type_generation_unique = 0;
    std::uint64_t type_head_calls = 0;
    std::uint64_t type_head_ns = 0;
    std::uint64_t type_head_generation_unique = 0;
    std::uint64_t type_args_calls = 0;
    std::uint64_t type_args_ns = 0;
    std::uint64_t type_args_generation_unique = 0;
    std::uint64_t compatible_calls = 0;
    std::uint64_t compatible_ns = 0;
    std::uint64_t compatible_generation_unique = 0;
    std::uint64_t nominal_subtype_calls = 0;
    std::uint64_t nominal_subtype_ns = 0;
    std::uint64_t nominal_subtype_generation_unique = 0;
    std::unordered_set<std::string> compact_type_keys;
    std::unordered_set<std::string> type_head_keys;
    std::unordered_set<std::string> type_args_keys;
    std::unordered_set<std::string> compatible_keys;
    std::unordered_set<std::string> nominal_subtype_keys;

    void BeginTypeGeneration() {
        ++type_generations;
        compact_type_keys.clear();
        type_head_keys.clear();
        type_args_keys.clear();
        compatible_keys.clear();
        nominal_subtype_keys.clear();
    }

    void Print() const {
        if (!enabled) return;
        std::cerr
            << "CANGJIE_PROFILE {"
            << "\"accepted_events\":" << accepted_events
            << ",\"probe_calls\":" << probe_calls
            << ",\"indentation_fast_paths\":" << indentation_fast_paths
            << ",\"brace_scan_bytes\":" << brace_scan_bytes
            << ",\"model_rebuilds\":" << model_rebuilds
            << ",\"model_rebuild_source_bytes\":" << model_rebuild_source_bytes
            << ",\"declaration_snapshot_rebuilds\":"
            << declaration_snapshot_rebuilds
            << ",\"declaration_snapshot_source_bytes\":"
            << declaration_snapshot_source_bytes
            << ",\"declaration_snapshot_records\":"
            << declaration_snapshot_records
            << ",\"context_rebuilds\":" << context_rebuilds
            << ",\"context_rebuild_source_bytes\":" << context_rebuild_source_bytes
            << ",\"analyze_calls\":" << analyze_calls
            << ",\"context_copy_payload_bytes\":" << context_copy_payload_bytes
            << ",\"duplicate_parameter_checks\":" << duplicate_parameter_checks
            << ",\"declared_type_checks\":" << declared_type_checks
            << ",\"interface_checks\":" << interface_checks
            << ",\"constructor_checks\":" << constructor_checks
            << ",\"range_checks\":" << range_checks
            << ",\"branch_join_checks\":" << branch_join_checks
            << ",\"malformed_generic_checks\":" << malformed_generic_checks
            << ",\"generic_prefix_checks\":" << generic_prefix_checks
            << ",\"unclosed_string_scan_bytes\":" << unclosed_string_scan_bytes
            << ",\"analyze_total_ns\":" << analyze_total_ns
            << ",\"duplicate_parameter_ns\":" << duplicate_parameter_ns
            << ",\"declared_type_ns\":" << declared_type_ns
            << ",\"interface_ns\":" << interface_ns
            << ",\"constructor_ns\":" << constructor_ns
            << ",\"range_ns\":" << range_ns
            << ",\"branch_join_ns\":" << branch_join_ns
            << ",\"malformed_generic_ns\":" << malformed_generic_ns
            << ",\"generic_prefix_ns\":" << generic_prefix_ns
            << ",\"brace_scan_ns\":" << brace_scan_ns
            << ",\"model_rebuild_ns\":" << model_rebuild_ns
            << ",\"declaration_snapshot_build_ns\":"
            << declaration_snapshot_build_ns
            << ",\"model_reset_ns\":" << model_reset_ns
            << ",\"collect_imports_ns\":" << collect_imports_ns
            << ",\"collect_functions_ns\":" << collect_functions_ns
            << ",\"collect_nominals_ns\":" << collect_nominals_ns
            << ",\"context_rebuild_ns\":" << context_rebuild_ns
            << ",\"context_current_function_ns\":" << context_current_function_ns
            << ",\"context_local_variables_ns\":" << context_local_variables_ns
            << ",\"context_class_fields_ns\":" << context_class_fields_ns
            << ",\"context_inferred_variables_ns\":" << context_inferred_variables_ns
            << ",\"context_lambda_variables_ns\":" << context_lambda_variables_ns
            << ",\"context_for_binding_ns\":" << context_for_binding_ns
            << ",\"type_generations\":" << type_generations
            << ",\"compact_type_calls\":" << compact_type_calls
            << ",\"compact_type_ns\":" << compact_type_ns
            << ",\"compact_type_generation_unique\":" << compact_type_generation_unique
            << ",\"type_head_calls\":" << type_head_calls
            << ",\"type_head_ns\":" << type_head_ns
            << ",\"type_head_generation_unique\":" << type_head_generation_unique
            << ",\"type_args_calls\":" << type_args_calls
            << ",\"type_args_ns\":" << type_args_ns
            << ",\"type_args_generation_unique\":" << type_args_generation_unique
            << ",\"compatible_calls\":" << compatible_calls
            << ",\"compatible_ns\":" << compatible_ns
            << ",\"compatible_generation_unique\":" << compatible_generation_unique
            << ",\"nominal_subtype_calls\":" << nominal_subtype_calls
            << ",\"nominal_subtype_ns\":" << nominal_subtype_ns
            << ",\"nominal_subtype_generation_unique\":"
            << nominal_subtype_generation_unique
            << "}\n";
    }
};

ProfileCounters* g_profile = nullptr;

std::string ProfilePairKey(std::string_view left, std::string_view right) {
    std::string key;
    key.reserve(left.size() + right.size() + 1);
    key.append(left.data(), left.size());
    key.push_back('\0');
    key.append(right.data(), right.size());
    return key;
}
#endif

bool IsIdentStart(unsigned char ch) {
    return std::isalpha(ch) || ch == '_';
}

bool IsIdentContinue(unsigned char ch) {
    return std::isalnum(ch) || ch == '_';
}

bool IsIdentifierText(std::string_view text) {
    if (text.empty() || !IsIdentStart(static_cast<unsigned char>(text.front()))) return false;
    return std::all_of(text.begin() + 1, text.end(), [](unsigned char ch) {
        return IsIdentContinue(ch);
    });
}

bool IsDecimalIntegerText(std::string_view text) {
    return !text.empty() && std::all_of(text.begin(), text.end(), [](unsigned char ch) {
        return std::isdigit(ch);
    });
}

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

bool StartsWith(std::string_view text, std::string_view prefix) {
    return text.size() >= prefix.size() && text.substr(0, prefix.size()) == prefix;
}

bool StartsWithKeyword(std::string_view text, std::string_view keyword) {
    return StartsWith(text, keyword) &&
        (text.size() == keyword.size() ||
         !IsIdentContinue(static_cast<unsigned char>(text[keyword.size()])));
}

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

std::string CompactType(std::string_view input) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->compact_type_ns : nullptr);
    if (g_profile) {
        ++g_profile->compact_type_calls;
        if (g_profile->compact_type_keys.emplace(input).second) {
            ++g_profile->compact_type_generation_unique;
        }
    }
#endif
    std::string output;
    output.reserve(input.size());
    bool pending_space = false;
    for (unsigned char ch : input) {
        if (std::isspace(ch)) {
            pending_space = true;
            continue;
        }
        if (pending_space && !output.empty() &&
            (IsIdentContinue(static_cast<unsigned char>(output.back())) && IsIdentStart(ch))) {
            output.push_back(' ');
        }
        output.push_back(static_cast<char>(ch));
        pending_space = false;
    }
    return output;
}

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
            if (escaped) {
                escaped = false;
            } else if (ch == '\\') {
                escaped = true;
            } else if (ch == '"') {
                in_string = false;
            }
            continue;
        }
        if (ch == '"') {
            in_string = true;
        } else if (ch == '(') {
            ++paren;
        } else if (ch == ')') {
            --paren;
        } else if (ch == '[') {
            ++bracket;
        } else if (ch == ']') {
            --bracket;
        } else if (ch == '{') {
            ++brace;
        } else if (ch == '}') {
            --brace;
        } else if (ch == '<') {
            ++angle;
        } else if (ch == '>' && angle > 0) {
            --angle;
        } else if (ch == separator && paren == 0 && bracket == 0 && brace == 0 && angle == 0) {
            parts.emplace_back(Trim(input.substr(start, index - start)));
            start = index + 1;
        }
    }
    parts.emplace_back(Trim(input.substr(start)));
    return parts;
}

std::optional<std::size_t> MatchingDelimiter(
    std::string_view text,
    std::size_t open,
    char opening,
    char closing
) {
    if (open >= text.size() || text[open] != opening) {
        return std::nullopt;
    }
    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment = 0;
    for (std::size_t index = open; index < text.size(); ++index) {
        const char ch = text[index];
        const char next = index + 1 < text.size() ? text[index + 1] : '\0';
        if (line_comment) {
            if (ch == '\n' || ch == '\r') {
                line_comment = false;
            }
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
            if (escaped) {
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
            block_comment = 1;
            ++index;
            continue;
        }
        if (ch == '"') {
            in_string = true;
        } else if (ch == opening) {
            ++depth;
        } else if (ch == closing && --depth == 0) {
            return index;
        }
    }
    return std::nullopt;
}

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
            if (escaped) {
                escaped = false;
            } else if (ch == '\\') {
                escaped = true;
            } else if (ch == '"') {
                in_string = false;
            }
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

std::string TypeHead(std::string_view type) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->type_head_ns : nullptr);
    if (g_profile) {
        ++g_profile->type_head_calls;
        if (g_profile->type_head_keys.emplace(type).second) {
            ++g_profile->type_head_generation_unique;
        }
    }
#endif
    std::string normalized = CompactType(type);
    if (StartsWith(normalized, "type:")) {
        normalized.erase(0, 5);
    }
    const std::size_t angle = normalized.find('<');
    return normalized.substr(0, angle);
}

std::vector<std::string> TypeArgs(std::string_view type) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->type_args_ns : nullptr);
    if (g_profile) {
        ++g_profile->type_args_calls;
        if (g_profile->type_args_keys.emplace(type).second) {
            ++g_profile->type_args_generation_unique;
        }
    }
#endif
    const std::string normalized = CompactType(type);
    const std::size_t open = normalized.find('<');
    if (open == std::string::npos || normalized.back() != '>') {
        return {};
    }
    return SplitTopLevel(
        std::string_view(normalized).substr(open + 1, normalized.size() - open - 2),
        ','
    );
}

std::string ApplySubstitution(
    std::string type,
    const std::unordered_map<std::string, std::string>& substitutions
) {
    type = CompactType(type);
    if (const auto found = substitutions.find(type); found != substitutions.end()) {
        return found->second;
    }
    const std::string head = TypeHead(type);
    const auto args = TypeArgs(type);
    if (!args.empty()) {
        std::string output = head + "<";
        for (std::size_t index = 0; index < args.size(); ++index) {
            if (index) output += ",";
            output += ApplySubstitution(args[index], substitutions);
        }
        return output + ">";
    }
    const std::size_t arrow = type.find("->");
    if (arrow != std::string::npos && !type.empty() && type.front() == '(') {
        const std::size_t close = type.rfind(')', arrow);
        if (close != std::string::npos) {
            auto params = SplitTopLevel(std::string_view(type).substr(1, close - 1), ',');
            std::string output = "(";
            for (std::size_t index = 0; index < params.size(); ++index) {
                if (index) output += ",";
                output += ApplySubstitution(params[index], substitutions);
            }
            output += ")->";
            output += ApplySubstitution(type.substr(arrow + 2), substitutions);
            return output;
        }
    }
    if (type.size() >= 2 && type.front() == '(' && type.back() == ')') {
        const auto parts = SplitTopLevel(
            std::string_view(type).substr(1, type.size() - 2), ','
        );
        std::string output = "(";
        for (std::size_t index = 0; index < parts.size(); ++index) {
            if (index) output += ",";
            output += ApplySubstitution(parts[index], substitutions);
        }
        return output + ")";
    }
    return type;
}

struct FunctionSig {
    std::string name;
    std::vector<std::string> type_params;
    std::vector<std::string> param_names;
    std::vector<std::string> param_types;
    std::string result = "Unit";
    std::size_t required = 0;
    bool is_static = false;
};

struct NominalInfo {
    std::string name;
    bool is_interface = false;
    std::vector<std::string> type_params;
    std::vector<std::string> supers;
    std::unordered_map<std::string, std::string> fields;
    std::unordered_map<std::string, std::string> static_fields;
    std::unordered_map<std::string, std::vector<FunctionSig>> methods;
    std::unordered_map<std::string, std::vector<FunctionSig>> static_methods;
    std::vector<FunctionSig> constructors;
};

struct Model {
    std::unordered_map<std::string, std::vector<FunctionSig>> functions;
    std::unordered_map<std::string, NominalInfo> nominals;
    std::unordered_map<std::string, std::string> globals;
};

bool IsInteger(std::string_view type) {
    static const std::unordered_set<std::string> values = {
        "Int8", "Int16", "Int32", "Int64"
    };
    return values.count(std::string(type)) != 0;
}

bool IsFloat(std::string_view type) {
    return type == "Float32" || type == "Float64";
}

bool IsNumeric(std::string_view type) {
    return IsInteger(type) || IsFloat(type) || type == "Rune";
}

bool SameNumericFamily(std::string_view left, std::string_view right) {
    return left == right;
}

bool IsFunctionType(std::string_view type) {
    return !type.empty() && type.front() == '(' && type.find("->") != std::string_view::npos;
}

std::pair<std::vector<std::string>, std::string> FunctionTypeParts(std::string_view type) {
    const std::string normalized = CompactType(type);
    const std::size_t arrow = normalized.find("->");
    if (arrow == std::string::npos || normalized.empty() || normalized.front() != '(') {
        return {{}, ""};
    }
    const std::size_t close = normalized.rfind(')', arrow);
    if (close == std::string::npos) {
        return {{}, ""};
    }
    auto params = SplitTopLevel(std::string_view(normalized).substr(1, close - 1), ',');
    if (params.size() == 1 && params.front().empty()) params.clear();
    return {params, normalized.substr(arrow + 2)};
}

void AddBuiltinModel(Model* model) {
    auto add_function = [&](std::string name, std::string param, std::string result) {
        FunctionSig sig;
        sig.name = name;
        sig.param_names = {"value"};
        sig.param_types = {std::move(param)};
        sig.result = std::move(result);
        sig.required = 1;
        model->functions[name].push_back(std::move(sig));
    };
    for (const std::string& name : {"println", "print", "eprintln", "eprint"}) {
        add_function(name, "String", "Unit");
        add_function(name, "Int64", "Unit");
        add_function(name, "Float64", "Unit");
    }

    auto add_nominal = [&](std::string name, std::vector<std::string> params) -> NominalInfo& {
        NominalInfo info;
        info.name = name;
        info.type_params = std::move(params);
        return model->nominals.emplace(name, std::move(info)).first->second;
    };
    auto add_method = [](
        NominalInfo* info,
        std::string name,
        std::vector<std::string> params,
        std::string result,
        std::vector<std::string> param_names = {}
    ) {
        FunctionSig sig;
        sig.name = name;
        sig.param_types = std::move(params);
        sig.param_names = std::move(param_names);
        while (sig.param_names.size() < sig.param_types.size()) {
            sig.param_names.push_back("arg" + std::to_string(sig.param_names.size()));
        }
        sig.result = std::move(result);
        sig.required = sig.param_types.size();
        info->methods[name].push_back(std::move(sig));
    };
    auto add_ctor = [](
        NominalInfo* info,
        std::vector<std::string> params,
        std::vector<std::string> names = {}
    ) {
        FunctionSig sig;
        sig.name = info->name;
        sig.type_params = info->type_params;
        sig.param_types = std::move(params);
        sig.param_names = std::move(names);
        while (sig.param_names.size() < sig.param_types.size()) {
            sig.param_names.push_back("arg" + std::to_string(sig.param_names.size()));
        }
        sig.required = sig.param_types.size();
        sig.result = info->name;
        if (!info->type_params.empty()) {
            sig.result += "<";
            for (std::size_t i = 0; i < info->type_params.size(); ++i) {
                if (i) sig.result += ",";
                sig.result += info->type_params[i];
            }
            sig.result += ">";
        }
        info->constructors.push_back(std::move(sig));
    };

    NominalInfo& array = add_nominal("Array", {"T"});
    array.fields["size"] = "Int64";
    add_ctor(&array, {"Int64", "T"}, {"size", "repeat"});
    add_ctor(&array, {"Array<T>"});
    add_ctor(&array, {"Int64"}, {"size"});
    add_method(&array, "fill", {"T"}, "Unit", {"value"});
    add_method(&array, "get", {"Int64"}, "Optional<T>");
    add_method(&array, "first", {}, "Optional<T>");
    add_method(&array, "last", {}, "Optional<T>");
    add_method(&array, "toString", {}, "String");

    NominalInfo& list = add_nominal("ArrayList", {"T"});
    list.fields["size"] = "Int64";
    list.fields["capacity"] = "Int64";
    add_ctor(&list, {});
    add_ctor(&list, {"Array<T>"});
    add_ctor(&list, {"Int64"});
    add_method(&list, "add", {"T"}, "Unit", {"value"});
    add_method(&list, "add", {"ArrayList<T>"}, "Unit");
    add_method(&list, "toArray", {}, "Array<T>");
    add_method(&list, "isEmpty", {}, "Bool");
    add_method(&list, "toString", {}, "String");

    NominalInfo& map = add_nominal("HashMap", {"K", "V"});
    map.fields["size"] = "Int64";
    map.fields["capacity"] = "Int64";
    add_ctor(&map, {});
    add_ctor(&map, {"Int64"});
    add_ctor(&map, {"Array<(K,V)>"});
    add_ctor(&map, {"HashMap<K,V>"});
    add_method(&map, "add", {"K", "V"}, "Unit", {"key", "value"});
    add_method(&map, "get", {"K"}, "Optional<V>", {"key"});
    add_method(&map, "keys", {}, "KeysView<K>");
    add_method(&map, "values", {}, "ValuesView<V>");
    add_method(&map, "toString", {}, "String");

    NominalInfo& set = add_nominal("HashSet", {"T"});
    set.fields["size"] = "Int64";
    add_ctor(&set, {});
    add_ctor(&set, {"Int64"});
    add_ctor(&set, {"Array<T>"});
    add_method(&set, "add", {"T"}, "Bool", {"value"});
    add_method(&set, "contains", {"T"}, "Bool");
    add_method(&set, "toArray", {}, "Array<T>");
    add_method(&set, "toString", {}, "String");

    NominalInfo& string = add_nominal("String", {});
    string.fields["size"] = "Int64";
    for (const std::string& name : {"contains", "startsWith", "endsWith"}) {
        add_method(&string, name, {"String"}, "Bool", {"value"});
    }
    add_method(&string, "isEmpty", {}, "Bool");
    add_method(&string, "get", {"Int64"}, "Optional<Rune>");
    add_method(&string, "compare", {"String"}, "Int64");
    add_method(&string, "toString", {}, "String");

    NominalInfo& optional = add_nominal("Optional", {"T"});
    add_method(&optional, "getOrThrow", {}, "T");
    NominalInfo& keys = add_nominal("KeysView", {"K"});
    keys.fields["size"] = "Int64";
    NominalInfo& values = add_nominal("ValuesView", {"V"});
    values.fields["size"] = "Int64";
    NominalInfo& range = add_nominal("Range", {"T"});
    range.fields["size"] = "Int64";
}

class ContextTableReader {
 public:
    explicit ContextTableReader(std::string data) : data_(std::move(data)) {
        static constexpr char magic[8] = {'C', 'J', 'C', 'T', 1, 0, 0, 0};
        if (data_.size() < sizeof(magic) ||
            !std::equal(std::begin(magic), std::end(magic), data_.begin())) {
            throw std::runtime_error("invalid native context table");
        }
        cursor_ = sizeof(magic);
    }

    std::uint32_t U32() {
        if (cursor_ > data_.size() || data_.size() - cursor_ < 4) {
            throw std::runtime_error("truncated native context table");
        }
        const auto* bytes = reinterpret_cast<const unsigned char*>(data_.data() + cursor_);
        cursor_ += 4;
        return static_cast<std::uint32_t>(bytes[0]) |
            (static_cast<std::uint32_t>(bytes[1]) << 8u) |
            (static_cast<std::uint32_t>(bytes[2]) << 16u) |
            (static_cast<std::uint32_t>(bytes[3]) << 24u);
    }

    std::string Text() {
        const std::uint32_t size = U32();
        if (size > data_.size() - cursor_) {
            throw std::runtime_error("truncated native context string");
        }
        std::string result = data_.substr(cursor_, size);
        cursor_ += size;
        return result;
    }

    std::vector<std::string> Texts() {
        std::vector<std::string> result;
        const std::uint32_t count = U32();
        result.reserve(count);
        for (std::uint32_t index = 0; index < count; ++index) result.push_back(Text());
        return result;
    }

    std::unordered_map<std::string, std::string> Fields() {
        std::unordered_map<std::string, std::string> result;
        const std::uint32_t count = U32();
        for (std::uint32_t index = 0; index < count; ++index) {
            std::string name = Text();
            result.emplace(std::move(name), Text());
        }
        return result;
    }

    FunctionSig Signature() {
        FunctionSig sig;
        sig.name = Text();
        sig.result = Text();
        sig.type_params = Texts();
        sig.param_names = Texts();
        sig.param_types = Texts();
        sig.required = U32();
        return sig;
    }

    std::vector<FunctionSig> Signatures() {
        std::vector<FunctionSig> result;
        const std::uint32_t count = U32();
        result.reserve(count);
        for (std::uint32_t index = 0; index < count; ++index) result.push_back(Signature());
        return result;
    }

 private:
    std::string data_;
    std::size_t cursor_ = 0;
};

void LoadContextTable(const std::string& path, Model* model) {
    if (path.empty()) return;
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("cannot open native context table: " + path);
    ContextTableReader reader(std::string{
        std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()
    });
    const std::uint32_t variable_count = reader.U32();
    for (std::uint32_t index = 0; index < variable_count; ++index) {
        const std::string name = reader.Text();
        model->globals[name] = reader.Text();
        (void)reader.U32();  // mutability is tracked once the variable is assigned.
    }
    for (FunctionSig& sig : reader.Signatures()) {
        model->functions[sig.name].push_back(std::move(sig));
    }
    const std::uint32_t nominal_count = reader.U32();
    for (std::uint32_t index = 0; index < nominal_count; ++index) {
        NominalInfo info;
        info.name = reader.Text();
        info.is_interface = reader.U32() != 0;
        info.type_params = reader.Texts();
        info.supers = reader.Texts();
        info.fields = reader.Fields();
        info.static_fields = reader.Fields();
        for (FunctionSig& sig : reader.Signatures()) {
            info.methods[sig.name].push_back(std::move(sig));
        }
        for (FunctionSig& sig : reader.Signatures()) {
            sig.is_static = true;
            info.static_methods[sig.name].push_back(std::move(sig));
        }
        info.constructors = reader.Signatures();
        model->nominals[info.name] = std::move(info);
    }
}

}  // namespace

IncrementalLexer::Result IncrementalLexer::Feed(std::string_view bytes) {
    pending_.append(bytes.data(), bytes.size());
    Result result;
    std::size_t pos = 0;
    auto emit = [&](TokenKind kind, std::size_t start, std::size_t end) {
        result.stable.push_back(TokenEvent{kind, pending_.substr(start, end - start), true});
    };
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
        if (IsIdentStart(ch)) {
            ++pos;
            while (pos < pending_.size() && IsIdentContinue(static_cast<unsigned char>(pending_[pos]))) ++pos;
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
                floating = floating || pending_[pos] == '.' || pending_[pos] == 'e' || pending_[pos] == 'E' || pending_[pos] == 'f';
                ++pos;
            }
            if (pos == pending_.size()) {
                pos = start;
                break;
            }
            emit(floating ? TokenKind::Floating : TokenKind::Integer, start, pos);
            continue;
        }
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
        else if (IsIdentStart(ch) || ch == '`') result.partial.candidates.push_back(TokenKind::Identifier);
        else if (std::isdigit(ch)) {
            result.partial.candidates.push_back(TokenKind::Integer);
            result.partial.candidates.push_back(TokenKind::Floating);
        } else result.partial.candidates.push_back(TokenKind::Symbol);
    }
    return result;
}

namespace {

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

bool HasMultilineFunctionHeader(std::string_view source) {
    std::size_t search_from = 0;
    while (search_from < source.size()) {
        const std::size_t func = source.find("func ", search_from);
        const std::size_t main = source.find("main", search_from);
        std::size_t start = std::min(func, main);
        if (start == std::string_view::npos) start = std::max(func, main);
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

const std::regex& StrictNominalPattern() {
    static const std::regex pattern(
        R"(\b(class|interface)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^:>{}()]*>)?([^{}]*)\{)"
    );
    return pattern;
}

const std::regex& BroadClassPattern() {
    static const std::regex pattern(
        R"(\bclass\s+([A-Za-z_][A-Za-z0-9_]*)[^{}]*\{)"
    );
    return pattern;
}

const std::regex& ExplicitFunctionSingleLinePattern() {
    static const std::regex pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([^{}\n]+?)\s*\{)"
    );
    return pattern;
}

const std::regex& ExplicitFunctionMultilinePattern() {
    static const std::regex pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*:\s*([^{}]+?)\s*\{)"
    );
    return pattern;
}

const std::regex& OptionalFunctionSingleLinePattern() {
    static const std::regex pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    return pattern;
}

const std::regex& OptionalFunctionMultilinePattern() {
    static const std::regex pattern(
        R"(\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}()]*>)?\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    return pattern;
}

const std::regex& CurrentFunctionSingleLinePattern() {
    static const std::regex pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()\n]*>)?|\bmain)\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    return pattern;
}

const std::regex& CurrentFunctionMultilinePattern() {
    static const std::regex pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()]*>)?|\bmain)\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    return pattern;
}

struct SnapshotCapture {
    bool matched = false;
    std::size_t offset = std::string::npos;
    std::size_t length = 0;
    std::string text;
};

struct DeclarationRecord {
    std::size_t offset = 0;
    std::size_t length = 0;
    std::size_t open = 0;
    std::optional<std::size_t> close;
    std::vector<SnapshotCapture> captures;
};

struct DeclarationSnapshot {
    std::vector<DeclarationRecord> strict_nominals;
    std::vector<DeclarationRecord> broad_classes;
    std::vector<DeclarationRecord> explicit_functions_single_line;
    std::vector<DeclarationRecord> explicit_functions_multiline_only;
    std::vector<DeclarationRecord> optional_functions_single_line;
    std::vector<DeclarationRecord> optional_functions_multiline_only;
    std::vector<DeclarationRecord> current_functions_single_line;
    std::vector<DeclarationRecord> current_functions_multiline_only;

    std::size_t RecordCount() const {
        return strict_nominals.size() + broad_classes.size() +
            explicit_functions_single_line.size() +
            explicit_functions_multiline_only.size() +
            optional_functions_single_line.size() +
            optional_functions_multiline_only.size() +
            current_functions_single_line.size() +
            current_functions_multiline_only.size();
    }
};

using DelimiterCloseCache =
    std::unordered_map<std::size_t, std::optional<std::size_t>>;

std::optional<std::size_t> CachedDelimiterClose(
    std::string_view source,
    std::size_t open,
    DelimiterCloseCache* cache
) {
    const auto found = cache->find(open);
    if (found != cache->end()) return found->second;
    const std::optional<std::size_t> close = MatchingDelimiter(source, open, '{', '}');
    cache->emplace(open, close);
    return close;
}

std::vector<DeclarationRecord> ScanDeclarationFamily(
    const std::string& source,
    const std::regex& pattern,
    bool multiline_only,
    DelimiterCloseCache* close_cache
) {
    std::vector<DeclarationRecord> records;
    for (std::sregex_iterator it(source.begin(), source.end(), pattern), end;
         it != end; ++it) {
        if (multiline_only && (*it)[0].str().find_first_of("\n\r") == std::string::npos) {
            continue;
        }
        DeclarationRecord record;
        record.offset = static_cast<std::size_t>((*it).position());
        record.length = static_cast<std::size_t>((*it).length());
        record.open = record.offset + record.length - 1;
        record.close = CachedDelimiterClose(source, record.open, close_cache);
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
        records.push_back(std::move(record));
    }
    return records;
}

DeclarationSnapshot BuildDeclarationSnapshot(std::string_view source) {
    const std::string owned(source);
    DelimiterCloseCache close_cache;
    DeclarationSnapshot snapshot;
    snapshot.strict_nominals = ScanDeclarationFamily(
        owned, StrictNominalPattern(), false, &close_cache
    );
    snapshot.broad_classes = ScanDeclarationFamily(
        owned, BroadClassPattern(), false, &close_cache
    );
    snapshot.current_functions_single_line = ScanDeclarationFamily(
        owned, CurrentFunctionSingleLinePattern(), false, &close_cache
    );
    snapshot.explicit_functions_single_line = ScanDeclarationFamily(
        owned, ExplicitFunctionSingleLinePattern(), false, &close_cache
    );
    snapshot.optional_functions_single_line = ScanDeclarationFamily(
        owned, OptionalFunctionSingleLinePattern(), false, &close_cache
    );
    if (HasMultilineFunctionHeader(source)) {
        snapshot.current_functions_multiline_only = ScanDeclarationFamily(
            owned, CurrentFunctionMultilinePattern(), true, &close_cache
        );
        snapshot.explicit_functions_multiline_only = ScanDeclarationFamily(
            owned, ExplicitFunctionMultilinePattern(), true, &close_cache
        );
        snapshot.optional_functions_multiline_only = ScanDeclarationFamily(
            owned, OptionalFunctionMultilinePattern(), true, &close_cache
        );
    }
    return snapshot;
}

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
class RegexShadowProfileGuard {
 public:
    RegexShadowProfileGuard() {
#ifdef CANGJIE_ENABLE_PROFILE
        saved_ = g_profile;
        g_profile = nullptr;
#endif
    }

    ~RegexShadowProfileGuard() {
#ifdef CANGJIE_ENABLE_PROFILE
        g_profile = saved_;
#endif
    }

    RegexShadowProfileGuard(const RegexShadowProfileGuard&) = delete;
    RegexShadowProfileGuard& operator=(const RegexShadowProfileGuard&) = delete;

 private:
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileCounters* saved_ = nullptr;
#endif
};

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

std::vector<LegacyDeclarationRecord> LegacyScanDeclarationFamily(
    std::string_view source,
    const std::regex& pattern,
    bool multiline_only
) {
    const std::string owned(source);
    std::vector<LegacyDeclarationRecord> records;
    for (std::sregex_iterator it(owned.begin(), owned.end(), pattern), end;
         it != end; ++it) {
        if (multiline_only && (*it)[0].str().find_first_of("\n\r") == std::string::npos) {
            continue;
        }
        LegacyDeclarationRecord record;
        record.offset = static_cast<std::size_t>((*it).position());
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
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()\n]*>)?|\bmain)\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    static const std::regex current_multiline_pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()]*>)?|\bmain)\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    auto verify = [&](const std::vector<DeclarationRecord>& actual,
                      const std::regex& pattern,
                      bool multiline_only,
                      const char* family) {
        const std::vector<LegacyDeclarationRecord> expected = LegacyScanDeclarationFamily(
            source, pattern, multiline_only
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
        current_single_line_pattern, false, "current function single-line"
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
            current_multiline_pattern, true, "current function multiline-only"
        );
    } else if (!snapshot.explicit_functions_multiline_only.empty() ||
               !snapshot.optional_functions_multiline_only.empty() ||
               !snapshot.current_functions_multiline_only.empty()) {
        throw std::logic_error("declaration snapshot contains unexpected multiline records");
    }
}
#endif

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
    static const std::regex field_pattern(
        R"(\b(?:let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^={}\n]+))"
    );
    static const std::regex bare_field_pattern(
        R"(\b([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>{}()\n]+>)?))"
    );
    static const std::regex init_pattern(R"(\binit\s*\(([^{};\n]*)\))");
    static const std::regex let_or_var_prefix(R"(\b(?:let|var)\s*$)");
    const std::string owned(source);
    for (const DeclarationRecord& record : records) {
        const std::size_t open = record.open;
        const std::optional<std::size_t>& close = record.close;
        const std::size_t body_end = close.value_or(owned.size());
        const std::string body = owned.substr(open + 1, body_end - open - 1);
        NominalInfo info;
        info.is_interface = SnapshotCaptureAt(record, 1).text == "interface";
        info.name = SnapshotCaptureAt(record, 2).text;
        info.type_params = ParseTypeParameters(SnapshotCaptureAt(record, 3).text);
        info.supers = ParseSupers(SnapshotCaptureAt(record, 4).text);

        auto collect_methods = [&](const std::regex& pattern, bool multiline_only) {
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
                const std::size_t prefix_start = body.rfind('\n', method_pos);
                const std::string prefix = body.substr(
                    prefix_start == std::string::npos ? 0 : prefix_start + 1,
                    method_pos - (prefix_start == std::string::npos ? 0 : prefix_start + 1)
                );
                sig.is_static = prefix.find("static") != std::string::npos;
                auto& methods = sig.is_static ? info.static_methods : info.methods;
                methods[sig.name].push_back(std::move(sig));
            }
        };
        collect_methods(single_line_method_pattern, false);
        if (HasMultilineFunctionHeader(body)) {
            collect_methods(multiline_method_pattern, true);
        }
        for (std::sregex_iterator field(body.begin(), body.end(), field_pattern), field_end;
             field != field_end; ++field) {
            const std::size_t field_pos = static_cast<std::size_t>((*field).position());
            const std::size_t line_start = body.rfind('\n', field_pos);
            const std::string prefix = body.substr(
                line_start == std::string::npos ? 0 : line_start + 1,
                field_pos - (line_start == std::string::npos ? 0 : line_start + 1)
            );
            auto& fields = prefix.find("static") != std::string::npos
                ? info.static_fields : info.fields;
            fields[(*field)[1].str()] = CompactType((*field)[2].str());
        }
        for (std::sregex_iterator field(body.begin(), body.end(), bare_field_pattern), field_end;
             field != field_end; ++field) {
            const std::size_t position = static_cast<std::size_t>((*field).position());
            int paren_depth = 0;
            int brace_depth = 0;
            for (std::size_t index = 0; index < position; ++index) {
                if (body[index] == '(') ++paren_depth;
                else if (body[index] == ')' && paren_depth > 0) --paren_depth;
                else if (body[index] == '{') ++brace_depth;
                else if (body[index] == '}' && brace_depth > 0) --brace_depth;
            }
            if (paren_depth == 0 && brace_depth == 0) {
                const std::size_t line_start = body.find_last_of("\n;{}", position);
                const std::string prefix = body.substr(
                    line_start == std::string::npos ? 0 : line_start + 1,
                    position - (line_start == std::string::npos ? 0 : line_start + 1)
                );
                if (!std::regex_search(prefix, let_or_var_prefix)) {
                    info.fields.emplace((*field)[1].str(), CompactType((*field)[2].str()));
                }
            }
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

void CollectNominals(
    std::string_view source,
    const DeclarationSnapshot& snapshot,
    Model* model
) {
    CollectNominalsFromRecords(source, snapshot.strict_nominals, model);
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
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
    static const std::regex field_pattern(
        R"(\b(?:let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^={}\n]+))"
    );
    static const std::regex bare_field_pattern(
        R"(\b([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>{}()\n]+>)?))"
    );
    static const std::regex init_pattern(R"(\binit\s*\(([^{};\n]*)\))");
    static const std::regex let_or_var_prefix(R"(\b(?:let|var)\s*$)");
    const std::string owned(source);
    for (std::sregex_iterator it(owned.begin(), owned.end(), nominal_pattern), end;
         it != end; ++it) {
        const std::size_t open = static_cast<std::size_t>(
            (*it).position() + (*it).length() - 1
        );
        const auto close = MatchingDelimiter(owned, open, '{', '}');
        const std::size_t body_end = close.value_or(owned.size());
        const std::string body = owned.substr(open + 1, body_end - open - 1);
        NominalInfo info;
        info.is_interface = (*it)[1].str() == "interface";
        info.name = (*it)[2].str();
        info.type_params = ParseTypeParameters((*it)[3].str());
        info.supers = ParseSupers((*it)[4].str());

        auto collect_methods = [&](const std::regex& pattern, bool multiline_only) {
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
                const std::size_t prefix_start = body.rfind('\n', method_pos);
                const std::string prefix = body.substr(
                    prefix_start == std::string::npos ? 0 : prefix_start + 1,
                    method_pos - (prefix_start == std::string::npos ? 0 : prefix_start + 1)
                );
                sig.is_static = prefix.find("static") != std::string::npos;
                auto& methods = sig.is_static ? info.static_methods : info.methods;
                methods[sig.name].push_back(std::move(sig));
            }
        };
        collect_methods(single_line_method_pattern, false);
        if (HasMultilineFunctionHeader(body)) {
            collect_methods(multiline_method_pattern, true);
        }
        for (std::sregex_iterator field(body.begin(), body.end(), field_pattern), field_end;
             field != field_end; ++field) {
            const std::size_t field_pos = static_cast<std::size_t>((*field).position());
            const std::size_t line_start = body.rfind('\n', field_pos);
            const std::string prefix = body.substr(
                line_start == std::string::npos ? 0 : line_start + 1,
                field_pos - (line_start == std::string::npos ? 0 : line_start + 1)
            );
            auto& fields = prefix.find("static") != std::string::npos
                ? info.static_fields : info.fields;
            fields[(*field)[1].str()] = CompactType((*field)[2].str());
        }
        for (std::sregex_iterator field(body.begin(), body.end(), bare_field_pattern), field_end;
             field != field_end; ++field) {
            const std::size_t position = static_cast<std::size_t>((*field).position());
            int paren_depth = 0;
            int brace_depth = 0;
            for (std::size_t index = 0; index < position; ++index) {
                if (body[index] == '(') ++paren_depth;
                else if (body[index] == ')' && paren_depth > 0) --paren_depth;
                else if (body[index] == '{') ++brace_depth;
                else if (body[index] == '}' && brace_depth > 0) --brace_depth;
            }
            if (paren_depth == 0 && brace_depth == 0) {
                const std::size_t line_start = body.find_last_of("\n;{}", position);
                const std::string prefix = body.substr(
                    line_start == std::string::npos ? 0 : line_start + 1,
                    position - (line_start == std::string::npos ? 0 : line_start + 1)
                );
                if (!std::regex_search(prefix, let_or_var_prefix)) {
                    info.fields.emplace(
                        (*field)[1].str(), CompactType((*field)[2].str())
                    );
                }
            }
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

bool SameFunctionSignature(const FunctionSig& left, const FunctionSig& right) {
    return left.name == right.name &&
        left.type_params == right.type_params &&
        left.param_names == right.param_names &&
        left.param_types == right.param_types &&
        left.result == right.result &&
        left.required == right.required &&
        left.is_static == right.is_static;
}

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

struct FunctionContext {
    bool in_function = false;
    bool is_main = false;
    std::string result = "Unit";
    std::string body;
    std::size_t body_start = 0;
    std::size_t body_end = std::string::npos;
    std::unordered_map<std::string, std::string> variables;
    std::unordered_set<std::string> immutable;
    std::string class_name;
};

FunctionContext CurrentFunctionContextFromRecords(
    std::string_view source,
    const std::vector<DeclarationRecord>& single_line_records,
    const std::vector<DeclarationRecord>& multiline_only_records,
    const std::vector<DeclarationRecord>& broad_class_records
) {
    const std::string owned(source);
    FunctionContext best;
    std::size_t best_open = std::string::npos;
    std::optional<std::size_t> best_close;
    auto inspect = [&](const std::vector<DeclarationRecord>& records) {
        for (const DeclarationRecord& record : records) {
            const std::size_t open = record.open;
            if (best_open != std::string::npos && open < best_open) continue;
            best_open = open;
            best_close = record.close;
            best.in_function = true;
            best.is_main = StartsWith(Trim(SnapshotCaptureAt(record, 0).text), "main");
            const SnapshotCapture& result_capture = SnapshotCaptureAt(record, 2);
            best.result = CompactType(result_capture.matched ? result_capture.text : "Unit");
            best.variables.clear();
            best.immutable.clear();
            const FunctionSig params = ParseFunctionSignature(
                "", {}, SnapshotCaptureAt(record, 1).text, best.result
            );
            for (std::size_t index = 0; index < params.param_names.size(); ++index) {
                best.variables[params.param_names[index]] = params.param_types[index];
                best.immutable.insert(params.param_names[index]);
            }
        }
    };
    inspect(single_line_records);
    inspect(multiline_only_records);
    if (best_open == std::string::npos) {
        best.body = owned;
        return best;
    }
    best.body_start = best_open + 1;
    best.body_end = best_close.value_or(std::string::npos);
    best.body = best_close
        ? owned.substr(best_open + 1, *best_close - best_open - 1)
        : owned.substr(best_open + 1);

    for (const DeclarationRecord& record : broad_class_records) {
        if (record.open < best_open && (!record.close || *record.close > best_open)) {
            best.class_name = SnapshotCaptureAt(record, 1).text;
        }
    }
    return best;
}

FunctionContext CurrentFunctionContext(
    std::string_view source,
    const DeclarationSnapshot& snapshot
) {
    return CurrentFunctionContextFromRecords(
        source,
        snapshot.current_functions_single_line,
        snapshot.current_functions_multiline_only,
        snapshot.broad_classes
    );
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
FunctionContext CurrentFunctionContextRegex(std::string_view source) {
    static const std::regex single_line_pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()\n]*>)?|\bmain)\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    static const std::regex multiline_pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()]*>)?|\bmain)\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    const std::string owned(source);
    FunctionContext best;
    std::size_t best_open = std::string::npos;
    std::optional<std::size_t> best_close;
    auto inspect = [&](const std::regex& pattern, bool multiline_only) {
        for (std::sregex_iterator it(owned.begin(), owned.end(), pattern), end;
             it != end; ++it) {
            if (multiline_only && (*it)[0].str().find_first_of("\n\r") == std::string::npos) {
                continue;
            }
            const std::size_t open = static_cast<std::size_t>(
                (*it).position() + (*it).length() - 1
            );
            if (best_open != std::string::npos && open < best_open) continue;
            best_open = open;
            best_close = MatchingDelimiter(owned, open, '{', '}');
            best.in_function = true;
            best.is_main = StartsWith(Trim((*it)[0].str()), "main");
            best.result = CompactType((*it)[2].matched ? (*it)[2].str() : "Unit");
            best.variables.clear();
            best.immutable.clear();
            const FunctionSig params = ParseFunctionSignature(
                "", {}, (*it)[1].str(), best.result
            );
            for (std::size_t index = 0; index < params.param_names.size(); ++index) {
                best.variables[params.param_names[index]] = params.param_types[index];
                best.immutable.insert(params.param_names[index]);
            }
        }
    };
    inspect(single_line_pattern, false);
    if (HasMultilineFunctionHeader(source)) inspect(multiline_pattern, true);
    if (best_open == std::string::npos) {
        best.body = owned;
        return best;
    }
    best.body_start = best_open + 1;
    best.body_end = best_close.value_or(std::string::npos);
    best.body = best_close
        ? owned.substr(best_open + 1, *best_close - best_open - 1)
        : owned.substr(best_open + 1);

    static const std::regex nominal_pattern(
        R"(\bclass\s+([A-Za-z_][A-Za-z0-9_]*)[^{}]*\{)"
    );
    for (std::sregex_iterator it(owned.begin(), owned.end(), nominal_pattern), end;
         it != end; ++it) {
        const std::size_t open = static_cast<std::size_t>(
            (*it).position() + (*it).length() - 1
        );
        const auto close = MatchingDelimiter(owned, open, '{', '}');
        if (open < best_open && (!close || *close > best_open)) {
            best.class_name = (*it)[1].str();
        }
    }
    return best;
}
#endif

void CollectLocalVariables(FunctionContext* context) {
    static const std::regex declaration_pattern(
        R"(\b(let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^=;{}\n]+)\s*=)"
    );
    for (std::sregex_iterator it(context->body.begin(), context->body.end(), declaration_pattern), end;
         it != end; ++it) {
        context->variables[(*it)[2].str()] = CompactType((*it)[3].str());
        if ((*it)[1].str() == "let") context->immutable.insert((*it)[2].str());
    }
}

void CollectActiveLambdaVariables(FunctionContext* context) {
    struct BraceFrame {
        std::size_t open = 0;
        bool lambda = false;
        std::string parameters;
    };
    std::vector<BraceFrame> stack;
    bool in_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    for (std::size_t index = 0; index < context->body.size(); ++index) {
        const char ch = context->body[index];
        const char next = index + 1 < context->body.size() ? context->body[index + 1] : '\0';
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
            stack.push_back({index, false, {}});
        } else if (ch == '=' && next == '>' && !stack.empty()) {
            BraceFrame& frame = stack.back();
            frame.lambda = true;
            frame.parameters = Trim(std::string_view(context->body).substr(
                frame.open + 1, index - frame.open - 1
            ));
            ++index;
        } else if (ch == '}' && !stack.empty()) {
            stack.pop_back();
        }
    }
    for (const BraceFrame& frame : stack) {
        if (!frame.lambda) continue;
        for (const std::string& raw_parameter : SplitTopLevel(frame.parameters, ',')) {
            const std::size_t colon = FindTopLevel(raw_parameter, ":");
            std::string name = Trim(std::string_view(raw_parameter).substr(0, colon));
            if (!IsIdentifierText(name)) continue;
            const std::string type = colon == std::string::npos
                ? "?" : CompactType(std::string_view(raw_parameter).substr(colon + 1));
            context->variables[name] = type.empty() ? "?" : type;
            context->immutable.insert(name);
        }
    }
}

bool NominalSubtype(
    std::string_view got,
    std::string_view want,
    const Model& model,
    std::unordered_set<std::string>* visited
) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->nominal_subtype_ns : nullptr);
    if (g_profile) {
        ++g_profile->nominal_subtype_calls;
        if (g_profile->nominal_subtype_keys.emplace(ProfilePairKey(got, want)).second) {
            ++g_profile->nominal_subtype_generation_unique;
        }
    }
#endif
    const std::string got_head = TypeHead(got);
    const std::string want_head = TypeHead(want);
    if (got_head == want_head) return CompactType(got) == CompactType(want);
    if (!visited->insert(got_head).second) return false;
    const auto nominal = model.nominals.find(got_head);
    if (nominal == model.nominals.end()) return false;
    std::unordered_map<std::string, std::string> substitutions;
    const auto got_args = TypeArgs(got);
    for (std::size_t index = 0;
         index < nominal->second.type_params.size() && index < got_args.size(); ++index) {
        substitutions[nominal->second.type_params[index]] = got_args[index];
    }
    for (const std::string& raw_super : nominal->second.supers) {
        const std::string super = ApplySubstitution(raw_super, substitutions);
        if (CompactType(super) == CompactType(want) || NominalSubtype(super, want, model, visited)) {
            return true;
        }
    }
    return false;
}

bool Compatible(std::string_view got, std::string_view want, const Model& model) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->compatible_ns : nullptr);
    if (g_profile) {
        ++g_profile->compatible_calls;
        if (g_profile->compatible_keys.emplace(ProfilePairKey(got, want)).second) {
            ++g_profile->compatible_generation_unique;
        }
    }
#endif
    const std::string left = CompactType(got);
    const std::string right = CompactType(want);
    if (left.empty() || left == "?" || right.empty() || right == "?") return true;
    if (left == right) return true;
    if (IsFunctionType(left) && IsFunctionType(right)) {
        const auto got_function = FunctionTypeParts(left);
        const auto want_function = FunctionTypeParts(right);
        if (got_function.first.size() != want_function.first.size()) return false;
        for (std::size_t index = 0; index < got_function.first.size(); ++index) {
            if (!Compatible(want_function.first[index], got_function.first[index], model)) {
                return false;
            }
        }
        return Compatible(got_function.second, want_function.second, model);
    }
    if (TypeHead(left) == TypeHead(right) && TypeArgs(right).empty()) return true;
    std::unordered_set<std::string> visited;
    return NominalSubtype(left, right, model, &visited);
}

bool KnownType(std::string_view type, const Model& model) {
    const std::string normalized = CompactType(type);
    static const std::unordered_set<std::string> primitives = {
        "Int8", "Int16", "Int32", "Int64", "Float32", "Float64",
        "Bool", "Rune", "String", "Unit"
    };
    if (primitives.count(normalized)) return true;
    if (IsFunctionType(normalized)) return true;
    return model.nominals.count(TypeHead(normalized)) != 0;
}

bool KnownDeclaredType(
    std::string_view type,
    const Model& model,
    const std::unordered_set<std::string>& type_params
) {
    const std::string normalized = CompactType(type);
    if (normalized.empty() || normalized == "Unit") return true;
    if (type_params.count(normalized)) return true;
    if (IsFunctionType(normalized)) {
        const auto parts = FunctionTypeParts(normalized);
        for (const std::string& parameter : parts.first) {
            if (!KnownDeclaredType(parameter, model, type_params)) return false;
        }
        return KnownDeclaredType(parts.second, model, type_params);
    }
    if (normalized.size() >= 2 && normalized.front() == '(' && normalized.back() == ')') {
        for (const std::string& item : SplitTopLevel(
                 std::string_view(normalized).substr(1, normalized.size() - 2), ',')) {
            if (!KnownDeclaredType(item, model, type_params)) return false;
        }
        return true;
    }
    if (!KnownType(TypeHead(normalized), model)) return false;
    for (const std::string& argument : TypeArgs(normalized)) {
        if (!KnownDeclaredType(argument, model, type_params)) return false;
    }
    return true;
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
std::unordered_set<std::string> EnclosingNominalTypeParametersRegex(
    std::string_view source,
    std::size_t position
) {
    static const std::regex nominal_pattern(
        R"(\b(?:class|interface)\s+[A-Za-z_][A-Za-z0-9_]*\s*(<[^:>{}()]*>)?[^{}]*\{)"
    );
    const std::string owned(source);
    std::size_t nearest_open = std::string::npos;
    std::vector<std::string> nearest;
    for (std::sregex_iterator it(owned.begin(), owned.end(), nominal_pattern), end; it != end; ++it) {
        const std::size_t open = static_cast<std::size_t>((*it).position() + (*it).length() - 1);
        if (open >= position) continue;
        const auto close = MatchingDelimiter(owned, open, '{', '}');
        if (close && *close < position) continue;
        if (nearest_open == std::string::npos || open > nearest_open) {
            nearest_open = open;
            nearest = ParseTypeParameters((*it)[1].str());
        }
    }
    return std::unordered_set<std::string>(nearest.begin(), nearest.end());
}
#endif

struct NominalDeclaration {
    std::size_t open = 0;
    std::optional<std::size_t> close;
    std::vector<std::string> type_parameters;
    std::string super_header;
};

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
        "Int8", "Int16", "Int32", "Int64", "Float32", "Float64",
        "Bool", "Rune", "String", "Unit"
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

CheckStatus CheckDeclaredTypes(
    std::string_view source,
    const Model& model,
    const DeclarationSnapshot& snapshot
) {
    const std::vector<NominalDeclaration> nominal_declarations =
        CollectNominalDeclarations(snapshot);
    const CheckStatus result = CheckDeclaredTypesFromRecords(
        source, model,
        snapshot.optional_functions_single_line,
        snapshot.optional_functions_multiline_only,
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
    };

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
    }

    Result Update(
        std::string_view source,
        std::size_t body_start,
        std::size_t body_end
    ) {
        body_end = std::min(body_end, source.size());
        if (body_start_ != body_start || cursor_ > body_end) Initialize(body_start);
        while (cursor_ < body_end) {
            const std::size_t index = cursor_;
            const char ch = source[index];
            const bool has_next = index + 1 < body_end;
            const char next = has_next ? source[index + 1] : '\0';
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
        const std::string active = Trim(source.substr(
            statement_start_, visible_end - statement_start_
        ));
        if (!active.empty()) {
            const bool function_closed = body_end < source.size() &&
                source[body_end] == '}';
            return {
                active,
                function_closed ? Boundary::FunctionClose : Boundary::None,
            };
        }
        if (last_start_ != std::string_view::npos) {
            return {
                Trim(source.substr(last_start_, last_end_ - last_start_)),
                last_boundary_,
            };
        }
        return {};
    }

 private:
    void Initialize(std::size_t body_start) {
        Reset();
        body_start_ = body_start;
        cursor_ = body_start;
        statement_start_ = body_start;
    }

    bool AtTopLevel() const {
        return paren_ == 0 && bracket_ == 0 && brace_ == 0;
    }

    void Commit(std::string_view source, std::size_t end, Boundary boundary) {
        if (!Trim(source.substr(statement_start_, end - statement_start_)).empty()) {
            last_start_ = statement_start_;
            last_end_ = end;
            last_boundary_ = boundary;
        }
    }

    void CommitAtNewline(std::string_view source, std::size_t index) {
        if (!ContinuesAfterNewline(source.substr(
                statement_start_, index - statement_start_
            ))) {
            Commit(source, index, Boundary::Newline);
            statement_start_ = index + 1;
        }
    }

    std::size_t body_start_ = std::string_view::npos;
    std::size_t cursor_ = 0;
    std::size_t statement_start_ = 0;
    std::size_t last_start_ = std::string_view::npos;
    std::size_t last_end_ = 0;
    Boundary last_boundary_ = Boundary::None;
    int paren_ = 0;
    int bracket_ = 0;
    int brace_ = 0;
    bool in_string_ = false;
    bool escaped_ = false;
    bool line_comment_ = false;
    int block_comment_depth_ = 0;
};

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

bool HasCompleteTrailingIdentifier(std::string_view source) {
    if (source.empty()) return false;
    const unsigned char last = static_cast<unsigned char>(source.back());
    return !IsIdentContinue(last);
}

bool HasUnclosedString(std::string_view source) {
    bool in_string = false;
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
        }
    }
    return in_string;
}

struct ExprResult {
    std::string type = "?";
    bool known = false;
    bool error = false;
    std::string message;
    bool suffix_may_change_type = false;
};

class ExpressionTyper {
 public:
    ExpressionTyper(
        const Model& model,
        const FunctionContext& context,
        std::string_view full_source
    ) : model_(model), context_(context), full_source_(full_source) {}

    ExprResult Infer(std::string expression, std::string expected = {}) {
        return InferImpl(Trim(expression), CompactType(expected), 0);
    }

 private:
    ExprResult InferImpl(std::string expression, const std::string& expected, int depth);
    ExprResult InferCall(
        std::string base,
        std::string name,
        std::vector<std::string> explicit_types,
        std::string arguments,
        bool closed,
        const std::string& expected,
        int depth
    );
    ExprResult CheckSignatures(
        const std::vector<FunctionSig>& signatures,
        const std::vector<std::string>& explicit_types,
        const std::vector<std::string>& arguments,
        bool closed,
        const std::string& expected,
        int depth,
        const std::unordered_map<std::string, std::string>& receiver_substitutions = {}
    );
    bool HasSymbolPrefix(std::string_view prefix) const;
    std::optional<std::pair<std::string, std::string>> ParseMember(std::string_view expression) const;

    const Model& model_;
    const FunctionContext& context_;
    std::string_view full_source_;
};

std::string StripOuterParens(std::string expression) {
    expression = Trim(expression);
    while (expression.size() >= 2 && expression.front() == '(') {
        const auto close = MatchingDelimiter(expression, 0, '(', ')');
        if (!close || *close != expression.size() - 1) break;
        expression = Trim(std::string_view(expression).substr(1, expression.size() - 2));
    }
    return expression;
}

std::optional<std::tuple<std::string, std::string, std::string>> TailBinary(
    std::string_view expression
) {
    static const std::vector<std::vector<std::string>> precedences = {
        {"||"}, {"&&"}, {"==", "!="}, {"<=", ">=", "<", ">"},
        {"..=", ".."}, {"+", "-"}, {"*", "/", "%"}
    };
    for (const auto& operators : precedences) {
        int paren = 0;
        int bracket = 0;
        int brace = 0;
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
            if (ch == '"') {
                in_string = true;
                continue;
            }
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

bool ExpressionTyper::HasSymbolPrefix(std::string_view prefix) const {
    for (const auto& [name, _] : context_.variables) if (StartsWith(name, prefix)) return true;
    for (const auto& [name, _] : model_.globals) if (StartsWith(name, prefix)) return true;
    for (const auto& [name, _] : model_.functions) if (StartsWith(name, prefix)) return true;
    for (const auto& [name, _] : model_.nominals) if (StartsWith(name, prefix)) return true;
    return false;
}

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
    if (TypeHead(pattern) != TypeHead(actual)) return;
    const auto pattern_args = TypeArgs(pattern);
    const auto actual_args = TypeArgs(actual);
    for (std::size_t index = 0; index < pattern_args.size() && index < actual_args.size(); ++index) {
        BindTypeVariables(pattern_args[index], actual_args[index], type_params, substitutions);
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
    }
}

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
    for (const FunctionSig& sig : signatures) {
        if (!explicit_types.empty() && explicit_types.size() != sig.type_params.size()) {
            if (first_error.empty()) first_error = "wrong generic arity";
            continue;
        }
        if (arguments.size() > sig.param_types.size() ||
            (closed && (arguments.size() < sig.required || arguments.size() > sig.param_types.size()))) {
            if (first_error.empty()) first_error = "wrong argument arity";
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
                if (!HasCompleteTrailingIdentifier(full_source_) &&
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
            if (!HasCompleteTrailingIdentifier(full_source_) &&
                IsIdentifierText(trimmed_argument) &&
                HasSymbolPrefix(trimmed_argument) &&
                argument_number + 1 == arguments.size()) {
                // A resolved name can still acquire a call/member/index suffix.
                continue;
            }
            if (actual.known) {
                BindTypeVariables(sig.param_types[parameter_index], actual.type, type_params, &substitutions);
                const std::string want = ApplySubstitution(sig.param_types[parameter_index], substitutions);
                if (!Compatible(actual.type, want, model_)) {
                    if (!closed && !HasCompleteTrailingIdentifier(full_source_) &&
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
    return {};
}

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
    if (!closed && !args.empty() && args.back().empty()) args.pop_back();
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
        return CheckSignatures(candidates, explicit_types, args, closed, expected, depth);
    }

    // If call discovery reached across a binary expression, the apparent
    // member name contains the operator tail.  The expression is still
    // syntactically extendable; leave it unknown instead of inventing a member
    // error.  TailBinary handles the stable forms on subsequent probes.
    if (name.find_first_of("+-*/%<>=&|") != std::string::npos) return {};

    ExprResult receiver = InferImpl(base, {}, depth + 1);
    if (receiver.error || !receiver.known) return receiver;
    const bool type_receiver = StartsWith(receiver.type, "type:");
    const std::string receiver_type = type_receiver ? receiver.type.substr(5) : receiver.type;
    if (StartsWith(receiver_type, "namespace:")) {
        if (name == "println" || name == "print" || name == "eprintln" || name == "eprint") {
            return {"Unit", true, false, {}};
        }
        return {};
    }
    const auto nominal = model_.nominals.find(TypeHead(receiver_type));
    if (name == "toString") return {"String", true, false, {}};
    if (nominal == model_.nominals.end()) {
        if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
            std::cerr << "member on non-nominal type '" << receiver_type
                      << "', base '" << base << "'\n";
        }
        return {"?", false, true, "member on non-nominal"};
    }
    const auto& methods = type_receiver ? nominal->second.static_methods : nominal->second.methods;
    const auto method = methods.find(name);
    if (method == methods.end()) {
        const bool partial = !HasCompleteTrailingIdentifier(full_source_);
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
    return CheckSignatures(
        method->second, explicit_types, args, closed, expected, depth, substitutions
    );
}

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
                std::string tuple = "(";
                bool known = true;
                for (std::size_t index = 0; index < tuple_parts.size(); ++index) {
                    ExprResult item = InferImpl(tuple_parts[index], {}, depth + 1);
                    if (item.error) return item;
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
        // Explicit annotations become stable as soon as a complete known type
        // is present, even while the rest of the lambda header is unfinished.
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
        if (result_body.error) return result_body;
        if (!expected_fn.second.empty() && result_body.known &&
            !Compatible(result_body.type, expected_fn.second, model_)) {
            if (!lambda_closed) {
                const auto body_binary = TailBinary(body);
                if (!body_binary || !std::get<2>(*body_binary).empty()) return {};
            }
            return {"?", false, true, "lambda return type mismatch"};
        }
        std::string type = "(";
        for (std::size_t index = 0; index < param_types.size(); ++index) {
            if (index) type += ",";
            type += param_types[index];
        }
        type += ")->" + (result_body.known ? result_body.type : expected_fn.second);
        return {type, !type.empty() && type.back() != '>', false, {}, true};
    }

    if (expression.front() == '"') {
        if (expected == "Rune" && expression.size() >= 3 && expression.back() == '"') {
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
    static const std::regex integer_pattern(R"([0-9]+(?:i(?:8|16|32|64))?)");
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
        if (!callee.empty()) {
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
        ExprResult left = InferImpl(left_text, {}, depth + 1);
        ExprResult right = InferImpl(right_text, {}, depth + 1);
        if (left.error) return left;
        if (right.error) return right;
        const bool partial_right_identifier = !HasCompleteTrailingIdentifier(full_source_) &&
            IsIdentifierText(right_text) &&
            right_text != "true" && right_text != "false";
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
            const std::string element = left.known ? left.type : (right.known ? right.type : "Int64");
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
        std::string inner = expression.substr(1);
        if (!inner.empty() && inner.back() == ']') inner.pop_back();
        const auto elements = SplitTopLevel(inner, ',');
        std::string element_type;
        for (std::size_t index = 0; index < elements.size(); ++index) {
            const std::string& item = elements[index];
            ExprResult element = InferImpl(item, {}, depth + 1);
            if (element.error) return element;
            if (!element.known) continue;
            if (element_type.empty()) element_type = element.type;
            else if (!Compatible(element.type, element_type, model_) &&
                     !(index + 1 == elements.size() && !HasCompleteTrailingIdentifier(full_source_))) {
                return {"?", false, true, "array element type mismatch"};
            }
        }
        return {"Array<" + (element_type.empty() ? std::string("?") : element_type) + ">",
                !element_type.empty(), false, {}};
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
                if (base.type == "String") return {"Rune", true, false, {}};
                const auto args = TypeArgs(base.type);
                return args.empty() ? ExprResult{} : ExprResult{args.front(), true, false, {}};
            }
        }
    }
    const std::size_t open_index = expression.rfind('[');
    if (open_index != std::string::npos && expression.find(']', open_index) == std::string::npos) {
        ExprResult base = InferImpl(expression.substr(0, open_index), {}, depth + 1);
        ExprResult subscript = InferImpl(expression.substr(open_index + 1), {}, depth + 1);
        if (base.known && TypeHead(base.type) != "Array" && TypeHead(base.type) != "ArrayList" && base.type != "String") {
            return {"?", false, true, "cannot index non-array"};
        }
        const std::string subscript_text = Trim(
            std::string_view(expression).substr(open_index + 1)
        );
        const bool partial_subscript = !HasCompleteTrailingIdentifier(full_source_) &&
            IsIdentifierText(subscript_text) &&
            subscript_text != "true" && subscript_text != "false";
        if (subscript.known && subscript.type != "Int64" && !partial_subscript) {
            return {"?", false, true, "array index must be Int64"};
        }
        return {};
    }

    if (const auto member = ParseMember(expression)) {
        if (member->second.empty()) return {};
        ExprResult base = InferImpl(member->first, {}, depth + 1);
        if (base.error || !base.known) return base;
        const bool type_receiver = StartsWith(base.type, "type:");
        const std::string receiver_type = type_receiver ? base.type.substr(5) : base.type;
        if (!type_receiver && StartsWith("toString", member->second)) {
            if (!HasCompleteTrailingIdentifier(full_source_)) return {};
            if (member->second == "toString") return {"method", true, false, {}};
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
            return {ApplySubstitution(field->second, substitutions), true, false, {}};
        }
        const auto& methods = type_receiver ? nominal->second.static_methods : nominal->second.methods;
        if (const auto method = methods.find(member->second); method != methods.end()) {
            if (!HasCompleteTrailingIdentifier(full_source_)) return {};
            if (method->second.size() != 1) {
                return {"?", false, true, "ambiguous overloaded member reference"};
            }
            const FunctionSig& signature = method->second.front();
            std::unordered_map<std::string, std::string> substitutions;
            const auto receiver_args = TypeArgs(receiver_type);
            for (std::size_t index = 0;
                 index < receiver_args.size() && index < nominal->second.type_params.size(); ++index) {
                substitutions[nominal->second.type_params[index]] = receiver_args[index];
            }
            std::string function_type = "(";
            for (std::size_t index = 0; index < signature.param_types.size(); ++index) {
                if (index) function_type += ",";
                function_type += ApplySubstitution(signature.param_types[index], substitutions);
            }
            function_type += ")->";
            function_type += ApplySubstitution(signature.result, substitutions);
            return {function_type, true, false, {}};
        }
        const bool complete = HasCompleteTrailingIdentifier(full_source_);
        if (!complete) {
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
        if (const auto nominal = model_.nominals.find(expression); nominal != model_.nominals.end()) {
            if (nominal->second.is_interface) return {"?", false, true, "interface used as value"};
            if (!HasCompleteTrailingIdentifier(full_source_)) return {};
            return {"type:" + expression, true, false, {}};
        }
        if (!HasCompleteTrailingIdentifier(full_source_) &&
            (StartsWith("true", expression) || StartsWith("false", expression))) {
            return {};
        }
        if (!HasCompleteTrailingIdentifier(full_source_) && HasSymbolPrefix(expression)) return {};
        if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
            std::cerr << "undefined expression identifier '" << expression << "'\n";
        }
        return {"?", false, true, "undefined identifier"};
    }
    return {};
}

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

struct AnyVariableDeclaration {
    std::string name;
    std::string annotated_type;
    std::string expression;
};

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

std::optional<std::pair<std::string, std::string>> ParseVariableDeclaration(
    std::string_view line
) {
    const auto declaration = ParseAnyVariableDeclaration(line);
    if (!declaration || declaration->annotated_type.empty()) return std::nullopt;
    return std::make_pair(declaration->annotated_type, declaration->expression);
}

std::optional<std::pair<std::string, std::string>> ParseReassignment(std::string_view line) {
    static const std::regex pattern(
        R"(^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)\s*(.*)$)"
    );
    std::smatch match;
    const std::string owned(line);
    if (!std::regex_match(owned, match, pattern)) return std::nullopt;
    return std::make_pair(match[1].str(), Trim(match[2].str()));
}

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

bool InsideLoop(std::string_view body) {
    static const std::regex loop_pattern(R"(\b(?:for|while)\s*\([^{}]*\)\s*\{)");
    const std::string owned(body);
    for (std::sregex_iterator it(owned.begin(), owned.end(), loop_pattern), end; it != end; ++it) {
        const std::size_t open = static_cast<std::size_t>((*it).position() + (*it).length() - 1);
        if (!MatchingDelimiter(owned, open, '{', '}')) return true;
    }
    return false;
}

bool IsIterable(std::string_view type) {
    const std::string head = TypeHead(type);
    return head == "Array" || head == "ArrayList" || head == "HashSet" ||
           head == "KeysView" || head == "ValuesView" || head == "Range" ||
           type == "String";
}

std::string IterableElement(std::string_view type) {
    if (type == "String") return "Rune";
    const auto args = TypeArgs(type);
    return args.empty() ? "?" : args.front();
}

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

void CollectInterfaceRequirements(
    std::string interface_type,
    const Model& model,
    std::unordered_map<std::string, std::vector<FunctionSig>>* requirements,
    std::unordered_set<std::string>* visited
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
    for (const auto& [method_name, signatures] : interface->second.methods) {
        auto& target = (*requirements)[method_name];
        for (const FunctionSig& signature : signatures) {
            target.push_back(SubstituteSignature(signature, substitutions));
        }
    }
    for (const std::string& super : interface->second.supers) {
        CollectInterfaceRequirements(
            ApplySubstitution(super, substitutions), model, requirements, visited
        );
    }
}

CheckStatus CheckInterfacesFromRecords(
    const std::vector<DeclarationRecord>& class_records,
    const Model& model
) {
    for (const DeclarationRecord& record : class_records) {
        const std::string& name = SnapshotCaptureAt(record, 1).text;
        const auto cls = model.nominals.find(name);
        if (cls == model.nominals.end()) continue;
        std::unordered_map<std::string, std::vector<FunctionSig>> requirements;
        std::unordered_set<std::string> visited_interfaces;
        for (const std::string& super_type : cls->second.supers) {
            CollectInterfaceRequirements(
                super_type, model, &requirements, &visited_interfaces
            );
        }
        for (const auto& [method_name, required_signatures] : requirements) {
            const auto implementation = cls->second.methods.find(method_name);
            if (implementation == cls->second.methods.end()) continue;
            for (const FunctionSig& requirement : required_signatures) {
                bool has_complete_candidate = false;
                bool matched = false;
                for (const FunctionSig& candidate : implementation->second) {
                    if (!SignatureTypesAreKnown(candidate, cls->second, model)) continue;
                    has_complete_candidate = true;
                    if (SameInterfaceSignature(candidate, requirement)) {
                        matched = true;
                        break;
                    }
                }
                if (has_complete_candidate && !matched) {
                    if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
                        std::cerr << "interface mismatch " << name << "." << method_name
                                  << ", required=" << requirement.result << ", candidates=";
                        for (const FunctionSig& candidate : implementation->second) {
                            std::cerr << candidate.result << " ";
                        }
                        std::cerr << '\n';
                    }
                    return {false, "interface method signature mismatch"};
                }
            }
        }
        if (!record.close) continue;
        for (const auto& [method_name, _] : requirements) {
            if (!cls->second.methods.count(method_name)) {
                return {false, "interface method not implemented"};
            }
        }
    }
    return {};
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
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
        std::unordered_map<std::string, std::vector<FunctionSig>> requirements;
        std::unordered_set<std::string> visited_interfaces;
        for (const std::string& super_type : cls->second.supers) {
            CollectInterfaceRequirements(
                super_type, model, &requirements, &visited_interfaces
            );
        }
        for (const auto& [method_name, required_signatures] : requirements) {
            const auto implementation = cls->second.methods.find(method_name);
            if (implementation == cls->second.methods.end()) continue;
            for (const FunctionSig& requirement : required_signatures) {
                bool has_complete_candidate = false;
                bool matched = false;
                for (const FunctionSig& candidate : implementation->second) {
                    if (!SignatureTypesAreKnown(candidate, cls->second, model)) continue;
                    has_complete_candidate = true;
                    if (SameInterfaceSignature(candidate, requirement)) {
                        matched = true;
                        break;
                    }
                }
                if (has_complete_candidate && !matched) {
                    if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
                        std::cerr << "interface mismatch " << name << "." << method_name
                                  << ", required=" << requirement.result << ", candidates=";
                        for (const FunctionSig& candidate : implementation->second) {
                            std::cerr << candidate.result << " ";
                        }
                        std::cerr << '\n';
                    }
                    return {false, "interface method signature mismatch"};
                }
            }
        }
        const std::size_t open = static_cast<std::size_t>(
            (*it).position() + (*it).length() - 1
        );
        if (!MatchingDelimiter(owned, open, '{', '}')) continue;
        for (const auto& [method_name, _] : requirements) {
            if (!cls->second.methods.count(method_name)) {
                return {false, "interface method not implemented"};
            }
        }
    }
    return {};
}
#endif

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

CheckStatus CheckRangeSteps(std::string_view source, const Model& model) {
    static const std::regex loop_pattern(R"(\bfor\s*\([^)]*\bin\s+([^)]*)\))");
    const std::string owned(source);
    FunctionContext context;
    ExpressionTyper typer(model, context, source);
    for (std::sregex_iterator it(owned.begin(), owned.end(), loop_pattern), end; it != end; ++it) {
        const std::string range = (*it)[1].str();
        const std::size_t dots = range.find("..");
        if (dots == std::string::npos) continue;
        const std::string left_text = Trim(std::string_view(range).substr(0, dots));
        std::string remainder = Trim(std::string_view(range).substr(dots + 2));
        if (!remainder.empty() && remainder.front() == '=') remainder.erase(remainder.begin());
        const std::size_t colon = FindTopLevel(remainder, ":");
        const std::string right_text = Trim(std::string_view(remainder).substr(0, colon));
        const std::string step_text = colon == std::string::npos
            ? "" : Trim(std::string_view(remainder).substr(colon + 1));
        ExprResult left = typer.Infer(left_text);
        ExprResult right = typer.Infer(right_text);
        ExprResult step = typer.Infer(step_text);
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

CheckStatus CheckIfBranchJoins(std::string_view source, const Model& model) {
    static const std::regex if_pattern(
        R"(\bif\s*\([^{}]*\)\s*\{\s*([^{};]+?)\s*\}\s*else\s*\{\s*([^{};]+?)\s*\})"
    );
    const std::string owned(source);
    FunctionContext context;
    ExpressionTyper typer(model, context, source);
    for (std::sregex_iterator it(owned.begin(), owned.end(), if_pattern), end; it != end; ++it) {
        ExprResult left = typer.Infer((*it)[1].str());
        ExprResult right = typer.Infer((*it)[2].str());
        if (!left.known || !right.known || left.error || right.error) continue;
        bool joined = Compatible(left.type, right.type, model) ||
            Compatible(right.type, left.type, model);
        if (!joined) {
            for (const auto& [name, nominal] : model.nominals) {
                if (!nominal.is_interface) continue;
                if (Compatible(left.type, name, model) && Compatible(right.type, name, model)) {
                    joined = true;
                    break;
                }
            }
        }
        if (!joined) return {false, "if branch types cannot be joined"};
    }
    return {};
}

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
        for (std::sregex_iterator init_it(body.begin(), body.end(), init_pattern), init_end;
             init_it != init_end; ++init_it) {
            const std::size_t init_open = static_cast<std::size_t>(
                (*init_it).position() + (*init_it).length() - 1
            );
            const auto init_close = MatchingDelimiter(body, init_open, '{', '}');
            const std::string init_body = body.substr(
                init_open + 1,
                init_close ? *init_close - init_open - 1 : body.size() - init_open - 1
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
        for (std::sregex_iterator init_it(body.begin(), body.end(), init_pattern), init_end;
             init_it != init_end; ++init_it) {
            const std::size_t init_open = static_cast<std::size_t>(
                (*init_it).position() + (*init_it).length() - 1
            );
            const auto init_close = MatchingDelimiter(body, init_open, '{', '}');
            const std::string init_body = body.substr(
                init_open + 1,
                init_close ? *init_close - init_open - 1 : body.size() - init_open - 1
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

bool IsRegexIdentifierStart(char ch) {
    return (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || ch == '_';
}

bool IsRegexIdentifierContinue(char ch) {
    return IsRegexIdentifierStart(ch) || (ch >= '0' && ch <= '9');
}

std::size_t SkipRegexWhitespace(std::string_view source, std::size_t cursor) {
    while (cursor < source.size() &&
           std::isspace(static_cast<unsigned char>(source[cursor]))) {
        ++cursor;
    }
    return cursor;
}

std::size_t ParseRegexIdentifier(std::string_view source, std::size_t cursor) {
    if (cursor >= source.size() || !IsRegexIdentifierStart(source[cursor])) {
        return std::string_view::npos;
    }
    do {
        ++cursor;
    } while (cursor < source.size() && IsRegexIdentifierContinue(source[cursor]));
    return cursor;
}

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
                }
                context.variables["this"] = context.class_name;
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
        }
    }
    return context;
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
bool SameFunctionContext(const FunctionContext& left, const FunctionContext& right) {
    return left.in_function == right.in_function &&
        left.is_main == right.is_main &&
        left.result == right.result &&
        left.body == right.body &&
        left.body_start == right.body_start &&
        left.body_end == right.body_end &&
        left.variables == right.variables &&
        left.immutable == right.immutable &&
        left.class_name == right.class_name;
}
#endif

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
auto ProfileTimed(std::uint64_t* target, Callable&& callable) {
    ProfileScopeTimer timer(target);
    return callable();
}

std::size_t EstimateContextPayloadBytes(const FunctionContext& context) {
    std::size_t result = context.result.size() + context.body.size() + context.class_name.size();
    for (const auto& [name, type] : context.variables) {
        result += name.size() + type.size();
    }
    for (const std::string& name : context.immutable) result += name.size();
    return result;
}
#endif

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
    if (context.body_start <= source.size()) {
        const std::size_t end = context.body_end == std::string::npos
            ? source.size() : std::min(context.body_end, source.size());
        context.body = std::string(source.substr(context.body_start, end - context.body_start));
    }

    ExpressionTyper typer(model, context, source);
    const bool trailing_numeric_prefix = !source.empty() &&
        std::isdigit(static_cast<unsigned char>(source.back()));
    const bool committed =
        active_statement.boundary != ActiveStatementCache::Boundary::None;
#ifdef CANGJIE_ENABLE_PROFILE
    if (profile) profile->unclosed_string_scan_bytes += source.size();
#endif
    const bool unclosed_string = HasUnclosedString(source);
    const bool trailing_open_paren = !source.empty() && source.back() == '(';
    const bool defer_expression_error = trailing_numeric_prefix || unclosed_string ||
        trailing_open_paren || (!context.is_main && !committed);
    const std::string line = std::move(active_statement.text);
    const std::string trimmed_source = Trim(source);
    const bool condition_closed_now = !trimmed_source.empty() && trimmed_source.back() == ')';
    if (condition_closed_now) {
        for (const std::string keyword : {"if", "while"}) {
            if (line.find(keyword + " (") == std::string::npos &&
                line.find(keyword + "(") == std::string::npos) continue;
            const auto condition = LastCondition(context.body, keyword);
            if (!condition || condition->empty()) continue;
            ExprResult result = typer.Infer(*condition);
            if (result.error && !defer_expression_error) return {false, result.message};
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
                if (iterable.error && !defer_expression_error) return {false, iterable.message};
                const bool numeric_literal = IsDecimalNumberText(iterable_text);
                const bool may_be_range = close == std::string::npos &&
                    (numeric_literal || (!iterable_text.empty() && iterable_text.back() == '.') ||
                     (!context.is_main && (IsInteger(iterable.type) || iterable.type == "Rune")));
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
    if (const auto declaration = ParseVariableDeclaration(line)) {
        ExprResult actual = typer.Infer(declaration->second, declaration->first);
        if (actual.error && !defer_expression_error) return {false, actual.message};
        static const std::regex incomplete_float(R"([0-9]+\.[0-9]*)");
        const bool defer_atom = !committed && (
            IsIdentifierText(declaration->second) ||
            (!declaration->second.empty() && declaration->second.front() == '"') ||
            trailing_numeric_prefix || unclosed_string ||
            trailing_open_paren ||
            std::regex_match(declaration->second, incomplete_float)
        ) && declaration->second != "true" && declaration->second != "false";
        const bool defer_suffix = !committed && actual.suffix_may_change_type;
        if (actual.known && !Compatible(actual.type, declaration->first, model) &&
            !defer_atom && !defer_suffix) {
            return {false, "variable initializer type mismatch"};
        }
    } else if (const auto declaration = ParseAnyVariableDeclaration(line)) {
        ExprResult actual = typer.Infer(declaration->expression, declaration->annotated_type);
        if (actual.error && !defer_expression_error) return {false, actual.message};
        if (!declaration->annotated_type.empty() && actual.known && committed &&
            !Compatible(actual.type, declaration->annotated_type, model)) {
            return {false, "variable initializer type mismatch"};
        }
    } else if (const auto assignment = ParseReassignment(line)) {
        if (committed && context.immutable.count(assignment->first)) return {false, "assignment to let"};
        const auto expected = context.variables.find(assignment->first);
        if (expected != context.variables.end()) {
            ExprResult actual = typer.Infer(assignment->second, expected->second);
            if (actual.error && !defer_expression_error) return {false, actual.message};
            if (committed && actual.known && !Compatible(actual.type, expected->second, model)) {
                return {false, "assignment type mismatch"};
            }
        }
    } else if (StartsWith(line, "return ")) {
        ExprResult actual = typer.Infer(Trim(std::string_view(line).substr(7)), context.result);
        if (actual.error && !defer_expression_error) return {false, actual.message};
        if (committed && actual.known && context.result != "Unit" && !Compatible(actual.type, context.result, model)) {
            return {false, "return type mismatch"};
        }
    } else if (!line.empty() && !IsStatementPrefix(line) &&
               !StartsWith(line, "func ") && !StartsWith(line, "class ") &&
               !StartsWith(line, "interface ") && !StartsWith(line, "if ") &&
               !StartsWith(line, "while ") && !StartsWith(line, "for ") &&
               !StartsWith(line, "//") && !StartsWith(line, "/*")) {
        ExprResult expression = typer.Infer(line, context.result);
        if (expression.error && !defer_expression_error) return {false, expression.message};
        const bool atomic = line == "true" || line == "false" ||
            (!line.empty() && (line.front() == '"' || std::isdigit(static_cast<unsigned char>(line.front()))));
        if (atomic && context.result != "Unit" && expression.known &&
            !trailing_numeric_prefix &&
            !Compatible(expression.type, context.result, model)) {
            return {false, "implicit return type mismatch"};
        }
    }

    // A single HashMap binding denotes a tuple.  Accessing it as a nominal
    // value becomes irrecoverable at the member dot, matching prefix rules.
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

}  // namespace

class IncrementalSemanticEngine::Impl {
 public:
    explicit Impl(std::string context_path) : context_path_(std::move(context_path)) {
#ifdef CANGJIE_ENABLE_PROFILE
        if (profile_.enabled) {
            g_profile = &profile_;
            profile_.BeginTypeGeneration();
        }
#endif
        AddBuiltinModel(&preload_);
        LoadContextTable(context_path_, &preload_);
        active_model_ = preload_;
    }

#ifdef CANGJIE_ENABLE_PROFILE
    ~Impl() {
        profile_.Print();
        if (g_profile == &profile_) g_profile = nullptr;
    }
#endif

    std::string context_path_;
    Model preload_;
    Model active_model_;
    DeclarationSnapshot declaration_snapshot_;
    FunctionContext active_context_;
    std::vector<TokenEvent> accepted_;
    std::size_t source_bytes_ = 0;
    std::size_t model_source_bytes_ = 0;
    std::size_t context_source_bytes_ = 0;
    std::string last_partial_;
    ActiveStatementCache statement_cache_;
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileCounters profile_;
#endif
};

IncrementalSemanticEngine::IncrementalSemanticEngine(std::string context_path)
    : impl_(std::make_unique<Impl>(std::move(context_path))) {}

IncrementalSemanticEngine::~IncrementalSemanticEngine() = default;

CheckStatus IncrementalSemanticEngine::Accept(const TokenEvent& event) {
    impl_->accepted_.push_back(event);
#ifdef CANGJIE_ENABLE_PROFILE
    if (impl_->profile_.enabled) ++impl_->profile_.accepted_events;
#endif
    return {};
}

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
    const bool context_dirty = impl_->context_source_bytes_ == 0 ||
        delta.find_first_of("{}\n\r;") != std::string_view::npos;
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
    return AnalyzeSource(
        source, impl_->active_model_, impl_->declaration_snapshot_, model_dirty, commit_dirty,
        impl_->active_context_, std::move(active_statement)
#ifdef CANGJIE_ENABLE_PROFILE
        , profile
#endif
    );
}

Checkpoint IncrementalSemanticEngine::Save() const {
    return {impl_->accepted_.size(), impl_->source_bytes_};
}

void IncrementalSemanticEngine::Rollback(const Checkpoint& checkpoint) {
    if (checkpoint.accepted_tokens < impl_->accepted_.size()) {
        impl_->accepted_.resize(checkpoint.accepted_tokens);
    }
    impl_->source_bytes_ = checkpoint.source_bytes;
    impl_->statement_cache_.Reset();
}

NativeSemanticChecker::NativeSemanticChecker(std::string context_path)
    : engine_(std::move(context_path)) {}

CheckStatus NativeSemanticChecker::Check(std::string_view bytes) {
    if (failed_) return {false, failure_message_};
    source_.append(bytes.data(), bytes.size());
    IncrementalLexer::Result result = lexer_.Feed(bytes);
    for (const TokenEvent& event : result.stable) {
        CheckStatus status = engine_.Accept(event);
        if (!status.ok) {
            failed_ = true;
            failure_message_ = status.message;
            return status;
        }
    }
    CheckStatus status = engine_.Probe(result.partial, source_);
    if (!status.ok) {
        failed_ = true;
        failure_message_ = status.message;
    }
    return status;
}

}  // namespace cangjie
