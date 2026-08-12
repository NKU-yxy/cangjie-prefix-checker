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
#include <condition_variable>
#ifdef CANGJIE_ENABLE_PROFILE
#include <chrono>
#endif
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <mutex>
#include <new>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <thread>
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
            << ",\"syntax_semantic_actual_overlap_ns\":"
            << syntax_semantic_actual_overlap_ns
            << ",\"parallel_round_wall_ns\":" << parallel_round_wall_ns
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

    static std::uint64_t Timestamp() {
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                Clock::now().time_since_epoch()
            ).count()
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
    std::uint64_t syntax_semantic_actual_overlap_ns = 0;
    std::uint64_t parallel_round_wall_ns = 0;
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

struct SyntaxOutcome {
    bool ok = false;
    std::exception_ptr error;
#ifdef CANGJIE_ENABLE_PROFILE
    std::uint64_t started_ns = 0;
    std::uint64_t finished_ns = 0;
#endif
};

#ifdef CANGJIE_ENABLE_CONCURRENCY_TESTS
void ConcurrencyYieldPoint() {
    if (std::getenv("CANGJIE_TEST_FORCE_YIELD")) std::this_thread::yield();
}
#else
void ConcurrencyYieldPoint() {}
#endif

class SyntaxExecutor {
 public:
    static std::unique_ptr<SyntaxExecutor> Create(const fs::path& grammar_path) {
        auto result = std::unique_ptr<SyntaxExecutor>(
            new SyntaxExecutor(grammar_path)
        );
        bool launched = false;
        try {
#ifdef CANGJIE_ENABLE_CONCURRENCY_TESTS
            if (std::getenv("CANGJIE_TEST_FORCE_THREAD_LAUNCH_FAILURE")) {
                throw std::system_error(std::make_error_code(
                    std::errc::resource_unavailable_try_again
                ));
            }
#endif
            result->worker_ = std::thread(&SyntaxExecutor::WorkerMain, result.get());
            launched = true;
        } catch (const std::system_error&) {
            // This try block contains only std::thread construction.  Standard
            // libraries may report thread-resource exhaustion through
            // different error_code categories, so every launch failure falls
            // back to the original serial syntax path.
        } catch (const std::bad_alloc&) {
            // A failed thread shared-state allocation may still leave enough
            // memory for the original serial syntax path.
        }
        if (!launched) {
#ifdef CANGJIE_ENABLE_PROFILE
            const auto started = PhaseProfiler::Clock::now();
#endif
            result->serial_ = std::make_unique<NativeSyntaxChecker>(grammar_path);
#ifdef CANGJIE_ENABLE_PROFILE
            result->grammar_init_ns_ = PhaseProfiler::Elapsed(started);
#endif
            return result;
        }

        std::exception_ptr initialization_error;
        {
            std::unique_lock<std::mutex> lock(result->mutex_);
            result->ready_cv_.wait(lock, [&] { return result->ready_; });
            initialization_error = result->initialization_error_;
        }
        if (initialization_error) {
            result->StopAndJoin();
            std::rethrow_exception(initialization_error);
        }
        return result;
    }

    SyntaxExecutor(const SyntaxExecutor&) = delete;
    SyntaxExecutor& operator=(const SyntaxExecutor&) = delete;
    SyntaxExecutor(SyntaxExecutor&&) = delete;
    SyntaxExecutor& operator=(SyntaxExecutor&&) = delete;

    ~SyntaxExecutor() { StopAndJoin(); }

    void Submit(std::string_view fragment) {
        if (serial_) {
            serial_outcome_ = CheckSerial(fragment);
            serial_pending_ = true;
            return;
        }
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (state_ != State::Idle || stop_requested_) {
                throw std::logic_error("syntax worker received an invalid submit");
            }
            ConcurrencyYieldPoint();
            fragment_ = fragment;
            outcome_ = {};
            state_ = State::Pending;
            ConcurrencyYieldPoint();
        }
        task_cv_.notify_one();
    }

    SyntaxOutcome Wait() {
        if (serial_) {
            if (!serial_pending_) {
                throw std::logic_error("serial syntax path has no pending task");
            }
            serial_pending_ = false;
            return serial_outcome_;
        }
        std::unique_lock<std::mutex> lock(mutex_);
        done_cv_.wait(lock, [&] { return state_ == State::Done; });
        ConcurrencyYieldPoint();
        SyntaxOutcome result = outcome_;
        state_ = State::Idle;
        ConcurrencyYieldPoint();
        return result;
    }

#ifdef CANGJIE_ENABLE_PROFILE
    std::uint64_t grammar_init_ns() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return grammar_init_ns_;
    }

    NativeSyntaxChecker::ProfileSnapshot profile() const {
        if (serial_) return serial_->profile();
        std::lock_guard<std::mutex> lock(mutex_);
        return profile_;
    }
#endif

 private:
    enum class State { Idle, Pending, Done };

    explicit SyntaxExecutor(fs::path grammar_path)
        : grammar_path_(std::move(grammar_path)) {}

    static SyntaxOutcome Check(NativeSyntaxChecker* checker, std::string_view fragment) {
        SyntaxOutcome result;
#ifdef CANGJIE_ENABLE_PROFILE
        result.started_ns = PhaseProfiler::Timestamp();
#endif
        try {
#ifdef CANGJIE_ENABLE_CONCURRENCY_TESTS
            if (std::getenv("CANGJIE_TEST_FORCE_SYNTAX_EXCEPTION")) {
                throw std::runtime_error("forced syntax exception");
            }
#endif
            result.ok = checker->check(fragment);
        } catch (...) {
            result.error = std::current_exception();
        }
#ifdef CANGJIE_ENABLE_PROFILE
        result.finished_ns = PhaseProfiler::Timestamp();
#endif
        return result;
    }

    SyntaxOutcome CheckSerial(std::string_view fragment) {
        return Check(serial_.get(), fragment);
    }

    void WorkerMain() noexcept {
        std::unique_ptr<NativeSyntaxChecker> checker;
        std::exception_ptr initialization_error;
#ifdef CANGJIE_ENABLE_PROFILE
        const auto grammar_started = PhaseProfiler::Clock::now();
#endif
        try {
            checker = std::make_unique<NativeSyntaxChecker>(grammar_path_);
        } catch (...) {
            initialization_error = std::current_exception();
        }
#ifdef CANGJIE_ENABLE_PROFILE
        const std::uint64_t grammar_elapsed = PhaseProfiler::Elapsed(grammar_started);
#endif
        {
            std::lock_guard<std::mutex> lock(mutex_);
            initialization_error_ = initialization_error;
#ifdef CANGJIE_ENABLE_PROFILE
            grammar_init_ns_ = grammar_elapsed;
#endif
            ready_ = true;
        }
        ready_cv_.notify_one();
        if (initialization_error) return;

        while (true) {
            std::string_view fragment;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                task_cv_.wait(lock, [&] {
                    return stop_requested_ || state_ == State::Pending;
                });
                if (stop_requested_ && state_ != State::Pending) return;
                ConcurrencyYieldPoint();
                fragment = fragment_;
                ConcurrencyYieldPoint();
            }

            SyntaxOutcome result = Check(checker.get(), fragment);
            bool should_stop = false;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                outcome_ = result;
#ifdef CANGJIE_ENABLE_PROFILE
                profile_ = checker->profile();
#endif
                state_ = State::Done;
                should_stop = stop_requested_;
            }
            done_cv_.notify_one();
            if (should_stop) return;
        }
    }

    void StopAndJoin() noexcept {
        if (!worker_.joinable()) return;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stop_requested_ = true;
        }
        task_cv_.notify_one();
        done_cv_.notify_all();
        worker_.join();
    }

    fs::path grammar_path_;
    std::unique_ptr<NativeSyntaxChecker> serial_;
    SyntaxOutcome serial_outcome_;
    bool serial_pending_ = false;
    mutable std::mutex mutex_;
    std::condition_variable ready_cv_;
    std::condition_variable task_cv_;
    std::condition_variable done_cv_;
    std::thread worker_;
    State state_ = State::Idle;
    bool ready_ = false;
    bool stop_requested_ = false;
    std::string_view fragment_;
    SyntaxOutcome outcome_;
    std::exception_ptr initialization_error_;
#ifdef CANGJIE_ENABLE_PROFILE
    std::uint64_t grammar_init_ns_ = 0;
    NativeSyntaxChecker::ProfileSnapshot profile_;
#endif
};

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
        auto phase_started = PhaseProfiler::Clock::now();
#endif
        cangjie::NativeSemanticChecker native_semantic(native_context.string());
#ifdef CANGJIE_ENABLE_PROFILE
        if (phase_profile.enabled()) {
            phase_profile.semantic_init_ns += PhaseProfiler::Elapsed(phase_started);
            phase_started = PhaseProfiler::Clock::now();
        }
        const auto startup_started = PhaseProfiler::Clock::now();
#endif
        const TokenTable token_table(root / "generated" / "cl100k_base.bin");
#ifdef CANGJIE_ENABLE_PROFILE
        if (phase_profile.enabled()) {
            phase_profile.token_table_init_ns += PhaseProfiler::Elapsed(phase_started);
        }
#endif
        std::unique_ptr<SyntaxExecutor> syntax = SyntaxExecutor::Create(
            root / "grammar" / "cangjie.gbnf"
        );
#ifdef CANGJIE_ENABLE_PROFILE
        if (phase_profile.enabled()) {
            phase_profile.grammar_init_ns += syntax->grammar_init_ns();
            phase_profile.startup_wall_ns += PhaseProfiler::Elapsed(startup_started);
        }
#endif
#ifdef CANGJIE_ENABLE_PARALLEL_SHADOW
        NativeSyntaxChecker syntax_shadow(root / "grammar" / "cangjie.gbnf");
#endif

        std::string line;
        while (std::getline(std::cin, line)) {
            std::int64_t token_id = -1;
            std::string_view fragment;
            if (!parse_token_id(line, &token_id) || !token_table.decode(token_id, &fragment)) {
                emit(false, args.competition_output);
                break;
            }
#ifdef CANGJIE_ENABLE_PROFILE
            const auto parallel_round_started = PhaseProfiler::Clock::now();
#endif
            syntax->Submit(fragment);
            cangjie::CheckStatus semantic_status;
            std::exception_ptr semantic_error;
#ifdef CANGJIE_ENABLE_PROFILE
            const std::uint64_t semantic_started_ns = PhaseProfiler::Timestamp();
#endif
            try {
#ifdef CANGJIE_ENABLE_CONCURRENCY_TESTS
                if (std::getenv("CANGJIE_TEST_FORCE_SEMANTIC_EXCEPTION")) {
                    throw std::runtime_error("forced semantic exception");
                }
#endif
                semantic_status = native_semantic.Check(fragment);
            } catch (...) {
                semantic_error = std::current_exception();
            }
#ifdef CANGJIE_ENABLE_PROFILE
            const std::uint64_t semantic_finished_ns = PhaseProfiler::Timestamp();
#endif
            const SyntaxOutcome syntax_outcome = syntax->Wait();
#ifdef CANGJIE_ENABLE_PROFILE
            if (phase_profile.enabled()) {
                const std::uint64_t syntax_elapsed =
                    syntax_outcome.finished_ns - syntax_outcome.started_ns;
                const std::uint64_t semantic_elapsed =
                    semantic_finished_ns - semantic_started_ns;
                const std::uint64_t overlap_start = std::max(
                    syntax_outcome.started_ns, semantic_started_ns
                );
                const std::uint64_t overlap_end = std::min(
                    syntax_outcome.finished_ns, semantic_finished_ns
                );
                phase_profile.syntax_check_ns += syntax_elapsed;
                phase_profile.semantic_check_ns += semantic_elapsed;
                phase_profile.syntax_semantic_overlap_upper_bound_ns +=
                    std::min(syntax_elapsed, semantic_elapsed);
                if (overlap_end > overlap_start) {
                    phase_profile.syntax_semantic_actual_overlap_ns +=
                        overlap_end - overlap_start;
                }
                phase_profile.parallel_round_wall_ns +=
                    PhaseProfiler::Elapsed(parallel_round_started);
                ++phase_profile.tokens_checked;
            }
#endif
#ifdef CANGJIE_ENABLE_PARALLEL_SHADOW
            bool shadow_ok = false;
            std::exception_ptr shadow_error;
            try {
                shadow_ok = syntax_shadow.check(fragment);
            } catch (...) {
                shadow_error = std::current_exception();
            }
            if (static_cast<bool>(shadow_error) !=
                static_cast<bool>(syntax_outcome.error)) {
                throw std::logic_error("parallel syntax exception diverged from serial shadow");
            }
            if (!shadow_error && shadow_ok != syntax_outcome.ok) {
                throw std::logic_error("parallel syntax result diverged from serial shadow");
            }
#endif
            if (syntax_outcome.error) std::rethrow_exception(syntax_outcome.error);
            if (semantic_error) std::rethrow_exception(semantic_error);
            const bool syntax_ok = syntax_outcome.ok;
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
