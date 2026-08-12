/*
 * Team-authored competition entry.
 *
 * External dependencies:
 * - XGrammar v0.2.1, Apache License 2.0
 * - Apache TVM FFI, Apache License 2.0
 *
 * This file calls public APIs from the dependencies above and does not
 * contain copied implementation source from those projects.
 * See THIRD_PARTY_NOTICES.md for details.
 *
 * Token decoding, syntax transitions, incremental lexing, and semantic
 * checking all run in this native process.
 */

#include <algorithm>
#include <charconv>
#ifdef CANGJIE_ENABLE_PROFILE
#include <chrono>
#endif
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#include <xgrammar/xgrammar.h>

#include "native_semantic.h"

// xgrammar 0.2.1 aarch64 wheels are built with a newer GCC than the official
// Ubuntu 22.04 image.  Their shared library references the new, unversioned
// iostream initialization hook while GCC 11's libstdc++ does not export it.
// This executable already initializes the standard streams through <iostream>,
// so the compatibility hook is intentionally empty.  Newer libstdc++ and
// libc++ builds use their own implementation and do not compile this shim.
#if defined(__GLIBCXX__) && defined(__GNUC__) && __GNUC__ < 12
namespace std {
void ios_base_library_init() {}
}  // namespace std
#endif

namespace fs = std::filesystem;

namespace {

#ifdef CANGJIE_ENABLE_PROFILE
class PhaseProfiler {
 public:
    using Clock = std::chrono::steady_clock;

    PhaseProfiler() : enabled_(std::getenv("CANGJIE_PROFILE") != nullptr) {}

    ~PhaseProfiler() {
        if (!enabled_) return;
        std::cerr
            << "CANGJIE_PHASE_PROFILE {"
            << "\"semantic_init_ns\":" << semantic_init_ns
            << ",\"token_table_init_ns\":" << token_table_init_ns
            << ",\"grammar_init_ns\":" << grammar_init_ns
            << ",\"startup_wall_ns\":" << startup_wall_ns
            << ",\"syntax_check_ns\":" << syntax_check_ns
            << ",\"semantic_check_ns\":" << semantic_check_ns
            << ",\"syntax_semantic_overlap_upper_bound_ns\":"
            << syntax_semantic_overlap_upper_bound_ns
            << ",\"syntax_stable_bytes\":" << syntax_stable_bytes
            << ",\"syntax_trailing_whitespace_scan_bytes\":"
            << syntax_trailing_whitespace_scan_bytes
            << ",\"syntax_stable_over_15_bytes_calls\":"
            << syntax_stable_over_15_bytes_calls
            << ",\"syntax_pending_capacity_growths\":"
            << syntax_pending_capacity_growths
            << ",\"tokens_checked\":" << tokens_checked
            << "}\n";
    }

    static std::uint64_t Elapsed(Clock::time_point start) {
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count()
        );
    }

    bool enabled() const { return enabled_; }

    std::uint64_t semantic_init_ns = 0;
    std::uint64_t token_table_init_ns = 0;
    std::uint64_t grammar_init_ns = 0;
    std::uint64_t startup_wall_ns = 0;
    std::uint64_t syntax_check_ns = 0;
    std::uint64_t semantic_check_ns = 0;
    std::uint64_t syntax_semantic_overlap_upper_bound_ns = 0;
    std::uint64_t syntax_stable_bytes = 0;
    std::uint64_t syntax_trailing_whitespace_scan_bytes = 0;
    std::uint64_t syntax_stable_over_15_bytes_calls = 0;
    std::uint64_t syntax_pending_capacity_growths = 0;
    std::uint64_t tokens_checked = 0;

 private:
    bool enabled_ = false;
};
#endif

constexpr char kTableMagic[8] = {'C', 'J', 'T', 'K', 1, 0, 0, 0};
constexpr std::uint32_t kMissing = 0xFFFFFFFFu;

std::uint32_t read_u32(std::string_view data, std::size_t* cursor) {
    if (*cursor > data.size() || data.size() - *cursor < 4) {
        throw std::runtime_error("truncated cl100k table");
    }
    const auto* bytes = reinterpret_cast<const unsigned char*>(data.data() + *cursor);
    *cursor += 4;
    return static_cast<std::uint32_t>(bytes[0]) |
           (static_cast<std::uint32_t>(bytes[1]) << 8u) |
           (static_cast<std::uint32_t>(bytes[2]) << 16u) |
           (static_cast<std::uint32_t>(bytes[3]) << 24u);
}

class TokenTable {
 public:
    explicit TokenTable(const fs::path& path) {
        std::ifstream stream(path, std::ios::binary);
        if (!stream) {
            throw std::runtime_error("cannot open token table: " + path.string());
        }
        const std::string data{
            std::istreambuf_iterator<char>(stream),
            std::istreambuf_iterator<char>()
        };
        if (data.size() < sizeof(kTableMagic) ||
            std::memcmp(data.data(), kTableMagic, sizeof(kTableMagic)) != 0) {
            throw std::runtime_error("invalid cl100k table header");
        }
        std::size_t cursor = sizeof(kTableMagic);
        const std::uint32_t count = read_u32(data, &cursor);
        const std::uint32_t blob_size = read_u32(data, &cursor);
        if (count > (data.size() - cursor) / 8) {
            throw std::runtime_error("truncated cl100k table entries");
        }
        entries_.reserve(count);
        for (std::uint32_t index = 0; index < count; ++index) {
            const std::uint32_t offset = read_u32(data, &cursor);
            const std::uint32_t length = read_u32(data, &cursor);
            entries_.emplace_back(offset, length);
        }
        if (blob_size > data.size() - cursor) {
            throw std::runtime_error("truncated cl100k table payload");
        }
        blob_.assign(data.data() + cursor, blob_size);
        for (const auto& [offset, length] : entries_) {
            if (offset != kMissing &&
                (offset > blob_.size() || length > blob_.size() - offset)) {
                throw std::runtime_error("invalid cl100k table entry");
            }
        }
    }

    bool decode(std::int64_t token_id, std::string_view* decoded) const {
        if (token_id < 0 || static_cast<std::uint64_t>(token_id) >= entries_.size()) {
            return false;
        }
        const auto [offset, length] = entries_[static_cast<std::size_t>(token_id)];
        if (offset == kMissing) {
            return false;
        }
        *decoded = std::string_view(blob_.data() + offset, length);
        return true;
    }

 private:
    std::vector<std::pair<std::uint32_t, std::uint32_t>> entries_;
    std::string blob_;
};

std::string read_text_file(const fs::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        throw std::runtime_error("cannot open grammar: " + path.string());
    }
    return std::string(
        std::istreambuf_iterator<char>(stream),
        std::istreambuf_iterator<char>()
    );
}

class NativeSyntaxChecker {
 public:
#ifdef CANGJIE_ENABLE_PROFILE
    struct ProfileSnapshot {
        std::uint64_t stable_bytes = 0;
        std::uint64_t trailing_whitespace_scan_bytes = 0;
        std::uint64_t stable_over_15_bytes_calls = 0;
        std::uint64_t pending_capacity_growths = 0;
    };
#endif

    explicit NativeSyntaxChecker(const fs::path& grammar_path)
        : tokenizer_(std::vector<std::string>{"x"}, xgrammar::VocabType::RAW),
          compiler_(tokenizer_, 1, false),
          compiled_(compiler_.CompileGrammar(read_text_file(grammar_path))),
          matcher_(compiled_) {}

    bool check(std::string_view fragment) {
#ifdef CANGJIE_ENABLE_PROFILE
        const std::size_t prior_capacity = pending_.capacity();
#endif
        pending_.append(fragment.data(), fragment.size());
#ifdef CANGJIE_ENABLE_PROFILE
        if (pending_.capacity() != prior_capacity) ++profile_.pending_capacity_growths;
#endif
        std::size_t stable_size = pending_.size();
        while (stable_size > 0) {
            const char ch = pending_[stable_size - 1];
            if (ch != ' ' && ch != '\t' && ch != '\n' && ch != '\r') {
                break;
            }
            --stable_size;
        }
        if (stable_size == 0) {
#ifdef CANGJIE_ENABLE_PROFILE
            profile_.trailing_whitespace_scan_bytes += pending_.size();
#endif
            return true;
        }
#ifdef CANGJIE_ENABLE_PROFILE
        profile_.stable_bytes += stable_size;
        profile_.trailing_whitespace_scan_bytes += pending_.size() - stable_size;
        if (stable_size > 15) ++profile_.stable_over_15_bytes_calls;
#endif
        std::string stable = pending_.substr(0, stable_size);
        pending_.erase(0, stable_size);
        return matcher_.AcceptString(stable);
    }

#ifdef CANGJIE_ENABLE_PROFILE
    ProfileSnapshot profile() const { return profile_; }
#endif

 private:
    xgrammar::TokenizerInfo tokenizer_;
    xgrammar::GrammarCompiler compiler_;
    xgrammar::CompiledGrammar compiled_;
    xgrammar::GrammarMatcher matcher_;
    std::string pending_;
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileSnapshot profile_;
#endif
};

struct TokenTableStartup {
    std::unique_ptr<TokenTable> table;
#ifdef CANGJIE_ENABLE_PROFILE
    std::uint64_t elapsed_ns = 0;
#endif
};

TokenTableStartup build_token_table(const fs::path& path) {
    TokenTableStartup result;
#ifdef CANGJIE_ENABLE_PROFILE
    const auto started = PhaseProfiler::Clock::now();
#endif
    result.table = std::make_unique<TokenTable>(path);
#ifdef CANGJIE_ENABLE_PROFILE
    result.elapsed_ns = PhaseProfiler::Elapsed(started);
#endif
    return result;
}

bool is_async_resource_failure(const std::system_error& error) {
    return error.code() == std::make_error_code(
        std::errc::resource_unavailable_try_again
    );
}

struct Args {
    std::string context_path;
    bool competition_output = false;
};

Args parse_args(int argc, char** argv) {
    Args result;
    for (int index = 1; index < argc; ++index) {
        const std::string arg = argv[index];
        if (arg == "--context" && index + 1 < argc) {
            result.context_path = argv[++index];
        } else if (arg == "--competition-output") {
            result.competition_output = true;
        } else if (arg == "--pure-cpp-semantic") {
            // Accepted as a no-op for experimental-package compatibility.
        } else if ((arg == "--grammar" || arg == "--semantic-mode" ||
                    arg == "--cangjie-file") && index + 1 < argc) {
            ++index;  // accepted for compatibility with the existing entry
        } else if (arg == "-h" || arg == "--help") {
            std::cout << "Usage: solution_cpp [--context PATH] [--competition-output]\n";
            std::exit(0);
        }
    }
    return result;
}

bool parse_token_id(const std::string& line, std::int64_t* output) {
    std::size_t first = line.find_first_not_of(" \t\r");
    if (first == std::string::npos) {
        return false;
    }
    const std::size_t last = line.find_last_not_of(" \t\r");
    const char* begin = line.data() + first;
    const char* end = line.data() + last + 1;
    bool explicit_positive = begin != end && *begin == '+';
    if (explicit_positive && ++begin == end) {
        return false;
    }
    std::int64_t value = 0;
    const auto parsed = std::from_chars(begin, end, value, 10);
    if (parsed.ec != std::errc{} || parsed.ptr != end) {
        return false;
    }
    *output = value;
    return true;
}

fs::path executable_root(const char* argv0) {
    std::error_code error;
    fs::path path = fs::absolute(argv0 ? argv0 : "solution_cpp", error);
    if (error) {
        return fs::current_path();
    }
    path = fs::weakly_canonical(path, error);
    return path.parent_path();
}

void emit(bool ok, bool competition_output) {
    const int value = competition_output ? (ok ? 1 : 0) : (ok ? 0 : 1);
    std::cout << value << '\n' << std::flush;
}

}  // namespace

int main(int argc, char** argv) {
    try {
#ifdef CANGJIE_ENABLE_PROFILE
        PhaseProfiler phase_profile;
#endif
        std::ios::sync_with_stdio(false);
        std::cin.tie(nullptr);
        const Args args = parse_args(argc, argv);
        const fs::path root = executable_root(argv[0]);
        fs::path native_context = root / "generated" / "context.bin";
        if (!args.context_path.empty() && fs::path(args.context_path).extension() == ".bin") {
            native_context = args.context_path;
        }
#ifdef CANGJIE_ENABLE_PROFILE
        const auto semantic_started = PhaseProfiler::Clock::now();
#endif
        cangjie::NativeSemanticChecker native_semantic(native_context.string());
#ifdef CANGJIE_ENABLE_PROFILE
        if (phase_profile.enabled()) {
            phase_profile.semantic_init_ns += PhaseProfiler::Elapsed(semantic_started);
        }
        const auto startup_started = PhaseProfiler::Clock::now();
#endif
        const fs::path token_table_path = root / "generated" / "cl100k_base.bin";
        const fs::path grammar_path = root / "grammar" / "cangjie.gbnf";
        std::unique_ptr<TokenTable> token_table;
        std::unique_ptr<NativeSyntaxChecker> syntax;
        std::future<TokenTableStartup> token_future;
        bool async_started = false;
        try {
#ifdef CANGJIE_ENABLE_CONCURRENCY_TESTS
            if (std::getenv("CANGJIE_TEST_FORCE_ASYNC_LAUNCH_FAILURE")) {
                throw std::system_error(std::make_error_code(
                    std::errc::resource_unavailable_try_again
                ));
            }
#endif
            token_future = std::async(
                std::launch::async,
                [token_table_path] { return build_token_table(token_table_path); }
            );
            async_started = true;
        } catch (const std::system_error& error) {
            if (!is_async_resource_failure(error)) throw;
        } catch (const std::bad_alloc&) {
            // A shared-state allocation failure may still leave enough memory
            // for the original serial startup path.
        }

        if (!async_started) {
            TokenTableStartup token_result = build_token_table(token_table_path);
            token_table = std::move(token_result.table);
#ifdef CANGJIE_ENABLE_PROFILE
            phase_profile.token_table_init_ns += token_result.elapsed_ns;
            const auto grammar_started = PhaseProfiler::Clock::now();
#endif
            syntax = std::make_unique<NativeSyntaxChecker>(grammar_path);
#ifdef CANGJIE_ENABLE_PROFILE
            phase_profile.grammar_init_ns += PhaseProfiler::Elapsed(grammar_started);
#endif
        } else {
            std::exception_ptr grammar_error;
            std::exception_ptr token_error;
#ifdef CANGJIE_ENABLE_PROFILE
            const auto grammar_started = PhaseProfiler::Clock::now();
#endif
            try {
                syntax = std::make_unique<NativeSyntaxChecker>(grammar_path);
            } catch (...) {
                grammar_error = std::current_exception();
            }
#ifdef CANGJIE_ENABLE_PROFILE
            phase_profile.grammar_init_ns += PhaseProfiler::Elapsed(grammar_started);
#endif
            try {
                TokenTableStartup token_result = token_future.get();
                token_table = std::move(token_result.table);
#ifdef CANGJIE_ENABLE_PROFILE
                phase_profile.token_table_init_ns += token_result.elapsed_ns;
#endif
            } catch (...) {
                token_error = std::current_exception();
            }
            if (token_error) std::rethrow_exception(token_error);
            if (grammar_error) std::rethrow_exception(grammar_error);
        }
#ifdef CANGJIE_ENABLE_PROFILE
        if (phase_profile.enabled()) {
            phase_profile.startup_wall_ns += PhaseProfiler::Elapsed(startup_started);
        }
#endif

        std::string line;
        while (std::getline(std::cin, line)) {
            std::int64_t token_id = -1;
            std::string_view fragment;
            if (!parse_token_id(line, &token_id) || !token_table->decode(token_id, &fragment)) {
                emit(false, args.competition_output);
                return 0;
            }
#ifdef CANGJIE_ENABLE_PROFILE
            const auto syntax_started = PhaseProfiler::Clock::now();
#endif
            const bool syntax_ok = syntax->check(fragment);
#ifdef CANGJIE_ENABLE_PROFILE
            std::uint64_t syntax_elapsed = 0;
            if (phase_profile.enabled()) {
                syntax_elapsed = PhaseProfiler::Elapsed(syntax_started);
                phase_profile.syntax_check_ns += syntax_elapsed;
            }
            const auto semantic_check_started = PhaseProfiler::Clock::now();
#endif
            const cangjie::CheckStatus semantic_status = native_semantic.Check(fragment);
#ifdef CANGJIE_ENABLE_PROFILE
            if (phase_profile.enabled()) {
                const std::uint64_t semantic_elapsed =
                    PhaseProfiler::Elapsed(semantic_check_started);
                phase_profile.semantic_check_ns += semantic_elapsed;
                phase_profile.syntax_semantic_overlap_upper_bound_ns +=
                    std::min(syntax_elapsed, semantic_elapsed);
                ++phase_profile.tokens_checked;
            }
#endif
            const bool semantic_ok = semantic_status.ok;
            if (!semantic_status.ok && std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
                std::cerr << "native semantic rejection: " << semantic_status.message << '\n';
            }
            const bool ok = syntax_ok && semantic_ok;
            emit(ok, args.competition_output);
            if (!ok) break;
        }
#ifdef CANGJIE_ENABLE_PROFILE
        if (phase_profile.enabled()) {
            const NativeSyntaxChecker::ProfileSnapshot snapshot = syntax->profile();
            phase_profile.syntax_stable_bytes = snapshot.stable_bytes;
            phase_profile.syntax_trailing_whitespace_scan_bytes =
                snapshot.trailing_whitespace_scan_bytes;
            phase_profile.syntax_stable_over_15_bytes_calls =
                snapshot.stable_over_15_bytes_calls;
            phase_profile.syntax_pending_capacity_growths =
                snapshot.pending_capacity_growths;
        }
#endif
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "native solution error: " << error.what() << '\n';
        return 1;
    }
}
