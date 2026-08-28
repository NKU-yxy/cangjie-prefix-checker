#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_set>

#ifdef CANGJIE_ENABLE_PROFILE
#include <chrono>
#include <cstdlib>
#include <iostream>
#endif

namespace cangjie {

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
    std::uint64_t range_source_copy_ns = 0;
    std::uint64_t range_regex_ns = 0;
    std::uint64_t range_infer_ns = 0;
    std::uint64_t branch_source_copy_ns = 0;
    std::uint64_t branch_regex_ns = 0;
    std::uint64_t branch_infer_ns = 0;
    std::uint64_t branch_compatible_ns = 0;
    std::uint64_t malformed_generic_ns = 0;
    std::uint64_t generic_prefix_ns = 0;
    std::uint64_t brace_scan_ns = 0;
    std::uint64_t model_rebuild_ns = 0;
    std::uint64_t declaration_snapshot_build_ns = 0;
    std::uint64_t declaration_snapshot_pattern_init_ns = 0;
    std::uint64_t declaration_snapshot_source_copy_ns = 0;
    std::uint64_t declaration_snapshot_multiline_probe_ns = 0;
    std::uint64_t declaration_snapshot_strict_nominal_ns = 0;
    std::uint64_t declaration_snapshot_broad_class_ns = 0;
    std::uint64_t declaration_snapshot_current_single_ns = 0;
    std::uint64_t declaration_snapshot_explicit_single_ns = 0;
    std::uint64_t declaration_snapshot_optional_single_ns = 0;
    std::uint64_t declaration_snapshot_current_multiline_ns = 0;
    std::uint64_t declaration_snapshot_explicit_multiline_ns = 0;
    std::uint64_t declaration_snapshot_optional_multiline_ns = 0;
    std::uint64_t declaration_snapshot_capture_copy_ns = 0;
    std::uint64_t declaration_snapshot_delimiter_ns = 0;
    std::uint64_t declaration_snapshot_delimiter_hits = 0;
    std::uint64_t declaration_snapshot_delimiter_misses = 0;
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
            << ",\"range_source_copy_ns\":" << range_source_copy_ns
            << ",\"range_regex_ns\":" << range_regex_ns
            << ",\"range_infer_ns\":" << range_infer_ns
            << ",\"branch_source_copy_ns\":" << branch_source_copy_ns
            << ",\"branch_regex_ns\":" << branch_regex_ns
            << ",\"branch_infer_ns\":" << branch_infer_ns
            << ",\"branch_compatible_ns\":" << branch_compatible_ns
            << ",\"malformed_generic_ns\":" << malformed_generic_ns
            << ",\"generic_prefix_ns\":" << generic_prefix_ns
            << ",\"brace_scan_ns\":" << brace_scan_ns
            << ",\"model_rebuild_ns\":" << model_rebuild_ns
            << ",\"declaration_snapshot_build_ns\":"
            << declaration_snapshot_build_ns
            << ",\"declaration_snapshot_pattern_init_ns\":"
            << declaration_snapshot_pattern_init_ns
            << ",\"declaration_snapshot_source_copy_ns\":"
            << declaration_snapshot_source_copy_ns
            << ",\"declaration_snapshot_multiline_probe_ns\":"
            << declaration_snapshot_multiline_probe_ns
            << ",\"declaration_snapshot_strict_nominal_ns\":"
            << declaration_snapshot_strict_nominal_ns
            << ",\"declaration_snapshot_broad_class_ns\":"
            << declaration_snapshot_broad_class_ns
            << ",\"declaration_snapshot_current_single_ns\":"
            << declaration_snapshot_current_single_ns
            << ",\"declaration_snapshot_explicit_single_ns\":"
            << declaration_snapshot_explicit_single_ns
            << ",\"declaration_snapshot_optional_single_ns\":"
            << declaration_snapshot_optional_single_ns
            << ",\"declaration_snapshot_current_multiline_ns\":"
            << declaration_snapshot_current_multiline_ns
            << ",\"declaration_snapshot_explicit_multiline_ns\":"
            << declaration_snapshot_explicit_multiline_ns
            << ",\"declaration_snapshot_optional_multiline_ns\":"
            << declaration_snapshot_optional_multiline_ns
            << ",\"declaration_snapshot_capture_copy_ns\":"
            << declaration_snapshot_capture_copy_ns
            << ",\"declaration_snapshot_delimiter_ns\":"
            << declaration_snapshot_delimiter_ns
            << ",\"declaration_snapshot_delimiter_hits\":"
            << declaration_snapshot_delimiter_hits
            << ",\"declaration_snapshot_delimiter_misses\":"
            << declaration_snapshot_delimiter_misses
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

inline ProfileCounters* g_profile = nullptr;  // 当前检查任务使用的性能计数器。

// 构造缓存键（左右字符串用 '\0' 分隔）
inline std::string ProfilePairKey(std::string_view left, std::string_view right) {
    std::string key;
    key.reserve(left.size() + right.size() + 1);
    key.append(left.data(), left.size());
    key.push_back('\0');
    key.append(right.data(), right.size());
    return key;
}
#endif

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 在正则影子校验期间暂停性能统计，避免重复计数。
class RegexShadowProfileGuard {
 public:
    // 保存当前计数器并临时关闭统计。
    RegexShadowProfileGuard() {
#ifdef CANGJIE_ENABLE_PROFILE
        saved_ = g_profile;
        g_profile = nullptr;
#endif
    }

    // 恢复进入影子校验前使用的计数器。
    ~RegexShadowProfileGuard() {
#ifdef CANGJIE_ENABLE_PROFILE
        g_profile = saved_;
#endif
    }

    RegexShadowProfileGuard(const RegexShadowProfileGuard&) = delete;
    RegexShadowProfileGuard& operator=(const RegexShadowProfileGuard&) = delete;

 private:
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileCounters* saved_ = nullptr;  // 影子校验前使用的计数器。
#endif
};
#endif

}  // namespace cangjie
