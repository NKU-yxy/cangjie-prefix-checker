/*
 * Team-authored competition entry.
 *
 * External dependencies:
 * - XGrammar C++ core v0.2.1, Apache License 2.0
 *
 * This file calls public APIs from the dependencies above and does not
 * contain copied implementation source from that project. The final package
 * includes the disclosed, unmodified XGrammar C++ core source so its build
 * does not depend on package indexes, Python bindings, or TVM FFI.
 * Files under third_party/xgrammar_core are third-party code and are not
 * claimed as team-authored implementation.
 * See THIRD_PARTY_NOTICES.md for details.
 *
 * Token decoding, syntax transitions, incremental lexing, and semantic
 * checking all run in this native process.
 */

#include <algorithm>
#include <cassert>
#include <charconv>
#ifdef CANGJIE_ENABLE_PROFILE
#include <chrono>
#endif
#include <cstdint>
#include <cstdlib>
#include <cstring>
#ifdef CANGJIE_ENABLE_GRAMMAR_SHADOW
#include <exception>
#endif
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#ifdef CANGJIE_ENABLE_GRAMMAR_SHADOW
#include <typeinfo>
#endif
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
            << ",\"shutdown_object_destroy_ns\":" << shutdown_object_destroy_ns
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
    std::uint64_t shutdown_object_destroy_ns = 0;

 private:
    bool enabled_ = false;
};

class ShutdownObjectProfiler {
 public:
    explicit ShutdownObjectProfiler(std::uint64_t* target) : target_(target) {}

    ~ShutdownObjectProfiler() {
        if (target_ && armed_) *target_ += PhaseProfiler::Elapsed(started_);
    }

    void Arm() {
        if (!target_) return;
        started_ = PhaseProfiler::Clock::now();
        armed_ = true;
    }

 private:
    std::uint64_t* target_ = nullptr;
    PhaseProfiler::Clock::time_point started_{};
    bool armed_ = false;
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

bool is_ascii_identifier_start(char ch) {
    return (ch >= 'a' && ch <= 'z') ||
           (ch >= 'A' && ch <= 'Z') || ch == '_';
}

bool is_ascii_identifier_continue(char ch) {
    return is_ascii_identifier_start(ch) || (ch >= '0' && ch <= '9');
}

bool is_identifier_literal(std::string_view value) {
    if (value.empty() || !is_ascii_identifier_start(value.front())) return false;
    return std::all_of(value.begin() + 1, value.end(), is_ascii_identifier_continue);
}

bool starts_with(std::string_view value, std::string_view prefix) {
    return value.size() >= prefix.size() && value.substr(0, prefix.size()) == prefix;
}

std::vector<std::string> grammar_identifier_literals(std::string_view grammar_source) {
    std::vector<std::string> result;
    std::size_t cursor = 0;
    while (cursor < grammar_source.size()) {
        if (grammar_source[cursor] == '#') {
            const std::size_t newline = grammar_source.find('\n', cursor + 1);
            cursor = newline == std::string_view::npos ? grammar_source.size() : newline + 1;
            continue;
        }
        if (grammar_source[cursor] == '[') {
            bool escaped = false;
            for (++cursor; cursor < grammar_source.size(); ++cursor) {
                const char ch = grammar_source[cursor];
                if (escaped) {
                    escaped = false;
                } else if (ch == '\\') {
                    escaped = true;
                } else if (ch == ']') {
                    ++cursor;
                    break;
                }
            }
            continue;
        }
        if (grammar_source[cursor] != '"') {
            ++cursor;
            continue;
        }
        ++cursor;
        std::string literal;
        bool escaped = false;
        bool has_escape = false;
        while (cursor < grammar_source.size()) {
            const char ch = grammar_source[cursor++];
            if (escaped) {
                literal.push_back(ch);
                escaped = false;
                has_escape = true;
            } else if (ch == '\\') {
                escaped = true;
                has_escape = true;
            } else if (ch == '"') {
                break;
            } else {
                literal.push_back(ch);
            }
        }
        if (!has_escape && is_identifier_literal(literal)) {
            result.push_back(std::move(literal));
        }
    }
    std::sort(result.begin(), result.end());
    result.erase(std::unique(result.begin(), result.end()), result.end());
    return result;
}

std::string choose_canonical_identifier(const std::vector<std::string>& literals) {
    static constexpr std::string_view kCandidates =
        "zqjxvkbywghdpcnmfosaeutrilABCDEFGHIJKLMNOPQRSTUVWXYZ_";
    for (const char candidate : kCandidates) {
        const bool overlaps_literal = std::any_of(
            literals.begin(), literals.end(), [&](const std::string& literal) {
                return literal.find(candidate) != std::string::npos;
            }
        );
        if (!overlaps_literal) return std::string(1, candidate);
    }
    throw std::runtime_error("grammar has no safe canonical identifier representative");
}

std::size_t max_identifier_literal_length(const std::vector<std::string>& literals) {
    std::size_t result = 1;
    for (const std::string& literal : literals) result = std::max(result, literal.size());
    return result;
}

class NativeSyntaxChecker {
 public:
    struct InMemoryGrammar {};
#ifdef CANGJIE_ENABLE_PROFILE
    struct ProfileSnapshot {
        std::uint64_t stable_bytes = 0;
        std::uint64_t trailing_whitespace_scan_bytes = 0;
        std::uint64_t stable_over_15_bytes_calls = 0;
        std::uint64_t pending_capacity_growths = 0;
    };
#endif

    explicit NativeSyntaxChecker(const fs::path& grammar_path)
        : NativeSyntaxChecker(InMemoryGrammar{}, read_text_file(grammar_path)) {}

    NativeSyntaxChecker(InMemoryGrammar, const std::string& grammar_source)
        : identifier_literals_(grammar_identifier_literals(grammar_source)),
          canonical_identifier_(choose_canonical_identifier(identifier_literals_)),
          max_identifier_literal_length_(
              max_identifier_literal_length(identifier_literals_)
          ),
          tokenizer_(std::vector<std::string>{"x"}, xgrammar::VocabType::RAW),
          compiler_(tokenizer_, 1, false),
          compiled_(compiler_.CompileGrammar(grammar_source)),
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
        return accept_stable(stable);
    }

#ifdef CANGJIE_ENABLE_PROFILE
    ProfileSnapshot profile() const { return profile_; }
#endif

 private:
    enum class LexicalMode {
        Normal,
        Identifier,
        ExactIdentifier,
        RawIdentifier,
        QuoteRun,
        String,
        OpaqueAfterTripleQuote,
        Rune,
        Slash,
        LineComment,
        BlockComment,
    };

    struct IdentifierGap {
        // A gap contains only uncovered bytes older than the literal window.
        // It stays uncommitted until a covered byte or the identifier boundary
        // closes it, so a rolling-buffer flush does not change the live probe.
        bool active = false;
        bool starts_with_digit = false;
        bool ends_with_digit = false;
        std::uint8_t non_digit_length_cap = 0;
    };

    static bool is_ascii_digit(char ch) {
        return ch >= '0' && ch <= '9';
    }

    static void add_identifier_gap_char(IdentifierGap* gap, char ch) {
        const bool is_digit = is_ascii_digit(ch);
        if (!gap->active) {
            gap->active = true;
            gap->starts_with_digit = is_digit;
        }
        gap->ends_with_digit = is_digit;
        if (!is_digit &&
            gap->non_digit_length_cap < kGenericGapRepresentativeLength) {
            ++gap->non_digit_length_cap;
        }
    }

    void append_identifier_gap(
        const IdentifierGap& gap,
        std::string* output
    ) const {
        if (!gap.active) return;
        if (gap.non_digit_length_cap == 0) {
            output->push_back('1');
            return;
        }
        if (gap.starts_with_digit) output->push_back('1');
        for (std::uint8_t index = 0;
             index < gap.non_digit_length_cap;
             ++index) {
            output->append(canonical_identifier_);
        }
        if (gap.ends_with_digit) output->push_back('1');
    }

    void close_identifier_gap(IdentifierGap* gap, std::string* output) const {
        append_identifier_gap(*gap, output);
        *gap = IdentifierGap{};
    }

    void fold_finalized_identifier_char(
        char ch,
        bool covered,
        std::string* output
    ) {
        if (covered) {
            close_identifier_gap(&identifier_open_gap_, output);
            output->push_back(ch);
        } else {
            add_identifier_gap_char(&identifier_open_gap_, ch);
        }
    }

    std::string identifier_probe_text() const {
        // Build the quotient for the still-buffered suffix.  Keep source bytes
        // verbatim whenever they can still grow into a multi-character grammar
        // literal; the speculative matcher step is reconciled separately.
        assert(identifier_buffer_.size() == identifier_covered_.size());
        std::vector<bool> covered = identifier_covered_;
        for (std::size_t start = 0; start < identifier_buffer_.size(); ++start) {
            const std::string_view suffix(identifier_buffer_.data() + start,
                                          identifier_buffer_.size() - start);
            const bool can_complete_literal = std::any_of(
                identifier_literals_.begin(), identifier_literals_.end(),
                [&](const std::string& literal) {
                    // All one-character identifier-shaped terminals in the
                    // locked grammar are already covered by any_identifier in
                    // normal code.  Rune/string uses are handled by their
                    // lexical modes, so retaining _, r, or u here only creates
                    // a redundant speculative state.
                    return literal.size() > 1 && starts_with(literal, suffix);
                }
            );
            if (can_complete_literal) {
                std::fill(covered.begin() + static_cast<std::ptrdiff_t>(start),
                          covered.end(), true);
            }
        }
        std::string representative;
        IdentifierGap gap = identifier_open_gap_;
        for (std::size_t index = 0; index < identifier_buffer_.size(); ++index) {
            if (covered[index]) {
                close_identifier_gap(&gap, &representative);
                representative.push_back(identifier_buffer_[index]);
            } else {
                add_identifier_gap_char(&gap, identifier_buffer_[index]);
            }
        }
        append_identifier_gap(gap, &representative);
        return representative;
    }

    bool accept_normalized_and_probe(
        std::string normalized,
        bool has_probe,
        const std::string& probe_text,
        bool can_defer_identifier_extension
    ) {
        if (speculative_probe_active_) {
            if (normalized.empty() && has_probe &&
                probe_text == speculative_probe_text_) {
                return true;
            }
            if (normalized.empty() && has_probe &&
                can_defer_identifier_extension &&
                speculative_probe_text_.size() >= canonical_identifier_.size() &&
                speculative_probe_text_.compare(
                    speculative_probe_text_.size() - canonical_identifier_.size(),
                    canonical_identifier_.size(), canonical_identifier_
                ) == 0 &&
                starts_with(probe_text, speculative_probe_text_)) {
                // The live suffix ends inside the generic identifier branch:
                // the canonical byte occurs in no identifier-shaped literal.
                // A longer quotient prefix can therefore keep that branch
                // alive without touching the matcher.  Reconcile the one
                // outstanding speculative step when output is next emitted
                // or the identifier boundary is reached.
                return true;
            }
            if (normalized.size() >= speculative_probe_text_.size() &&
                normalized.compare(
                    0, speculative_probe_text_.size(), speculative_probe_text_
                ) == 0) {
                normalized.erase(0, speculative_probe_text_.size());
            } else {
                matcher_.Rollback(1);
            }
            speculative_probe_active_ = false;
            speculative_probe_text_.clear();
        }

        if (!normalized.empty() && !matcher_.AcceptString(normalized)) return false;
        if (!has_probe) return true;

        // A successful AcceptString call is exactly one rollback step in
        // XGrammar 0.2.1.  Keep it live until the next fragment either commits
        // the same quotient or proves that the unfinished suffix changed.
        if (!matcher_.AcceptString(probe_text)) return false;
        speculative_probe_active_ = true;
        speculative_probe_text_ = probe_text;
        return true;
    }

    void mark_completed_identifier_literals() {
        // Preserve every character participating in an identifier-shaped
        // grammar terminal.  The canonical character occurs in no such
        // terminal, so collapsing each remaining non-empty gap cannot create
        // a new terminal or erase an existing one.
        for (const std::string& literal : identifier_literals_) {
            if (literal.size() <= 1 || identifier_buffer_.size() < literal.size()) continue;
            const std::size_t start = identifier_buffer_.size() - literal.size();
            if (identifier_buffer_.compare(start, literal.size(), literal) == 0) {
                std::fill(
                    identifier_covered_.begin() + static_cast<std::ptrdiff_t>(start),
                    identifier_covered_.end(), true
                );
            }
        }
    }

    void flush_identifier_prefix(std::size_t count, std::string* output) {
        assert(identifier_buffer_.size() == identifier_covered_.size());
        assert(count <= identifier_buffer_.size());
        for (std::size_t index = 0; index < count; ++index) {
            fold_finalized_identifier_char(
                identifier_buffer_[index], identifier_covered_[index], output
            );
        }
        identifier_buffer_.erase(0, count);
        identifier_covered_.erase(
            identifier_covered_.begin(),
            identifier_covered_.begin() + static_cast<std::ptrdiff_t>(count)
        );
    }

    void finish_identifier(char following, std::string* output) {
        if (following == '\'' && !identifier_buffer_.empty() &&
            identifier_buffer_.back() == 'r') {
            identifier_covered_.back() = true;
        }
        flush_identifier_prefix(identifier_buffer_.size(), output);
        close_identifier_gap(&identifier_open_gap_, output);
    }

    void note_source_char(char ch) {
        previous_source_char_2_ = previous_source_char_;
        has_previous_source_char_2_ = has_previous_source_char_;
        previous_source_char_ = ch;
        has_previous_source_char_ = true;
    }

    bool follows_number_like_prefix() const {
        if (!has_previous_source_char_) return false;
        if (previous_source_char_ >= '0' && previous_source_char_ <= '9') return true;
        return previous_source_char_ == '.' && has_previous_source_char_2_ &&
            previous_source_char_2_ >= '0' && previous_source_char_2_ <= '9';
    }

    void append_raw_identifier(std::string* output) {
        if (raw_identifier_valid_ && raw_identifier_content_size_ > 0) {
            output->push_back('`');
            output->append(canonical_identifier_);
            output->push_back('`');
        } else {
            output->append(raw_identifier_buffer_);
        }
        raw_identifier_buffer_.clear();
        raw_identifier_content_size_ = 0;
        raw_identifier_valid_ = true;
    }

    bool accept_stable(std::string_view input) {
        std::string normalized;
        normalized.reserve(input.size());
        std::size_t cursor = 0;
        while (cursor < input.size()) {
            const char ch = input[cursor];
            const auto consume = [&]() {
                ++cursor;
                note_source_char(ch);
            };
            switch (lexical_mode_) {
                case LexicalMode::Identifier:
                    if (is_ascii_identifier_continue(ch)) {
                        identifier_buffer_.push_back(ch);
                        identifier_covered_.push_back(false);
                        consume();
                        mark_completed_identifier_literals();
                        // Retaining one maximum-literal window is sufficient:
                        // no future byte can make an older position part of a
                        // newly completed grammar terminal.
                        if (identifier_buffer_.size() > max_identifier_literal_length_) {
                            flush_identifier_prefix(
                                identifier_buffer_.size() - max_identifier_literal_length_,
                                &normalized
                            );
                        }
                        assert(
                            identifier_buffer_.size() <= max_identifier_literal_length_
                        );
                    } else {
                        finish_identifier(ch, &normalized);
                        lexical_mode_ = LexicalMode::Normal;
                    }
                    break;

                case LexicalMode::ExactIdentifier:
                    if (is_ascii_identifier_continue(ch)) {
                        normalized.push_back(ch);
                        consume();
                    } else {
                        lexical_mode_ = LexicalMode::Normal;
                    }
                    break;

                case LexicalMode::RawIdentifier:
                    raw_identifier_buffer_.push_back(ch);
                    consume();
                    if (ch == '`') {
                        append_raw_identifier(&normalized);
                        lexical_mode_ = LexicalMode::Normal;
                    } else {
                        const bool valid = raw_identifier_content_size_ == 0
                            ? is_ascii_identifier_start(ch)
                            : is_ascii_identifier_continue(ch);
                        raw_identifier_valid_ = raw_identifier_valid_ && valid;
                        ++raw_identifier_content_size_;
                        if (!valid) {
                            normalized.append(raw_identifier_buffer_);
                            raw_identifier_buffer_.clear();
                            raw_identifier_content_size_ = 0;
                            raw_identifier_valid_ = true;
                            lexical_mode_ = LexicalMode::Normal;
                        }
                    }
                    break;

                case LexicalMode::QuoteRun:
                    if (ch == '"') {
                        normalized.push_back(ch);
                        consume();
                        if (++quote_run_size_ == 3) {
                            quote_run_size_ = 0;
                            // The GBNF multiline body can also consume quote
                            // triples, so the first triple is not a unique close.
                            // Preserve the remainder rather than choosing one
                            // lexical branch and changing prefix semantics.
                            lexical_mode_ = LexicalMode::OpaqueAfterTripleQuote;
                        }
                    } else if (quote_run_size_ == 1) {
                        quote_run_size_ = 0;
                        lexical_mode_ = LexicalMode::String;
                        escaped_ = false;
                    } else {
                        quote_run_size_ = 0;
                        lexical_mode_ = LexicalMode::Normal;
                    }
                    break;

                case LexicalMode::String:
                    normalized.push_back(ch);
                    consume();
                    if (escaped_) {
                        escaped_ = false;
                    } else if (ch == '\\') {
                        escaped_ = true;
                    } else if (ch == '"') {
                        lexical_mode_ = LexicalMode::Normal;
                    }
                    break;

                case LexicalMode::OpaqueAfterTripleQuote:
                    normalized.push_back(ch);
                    consume();
                    break;

                case LexicalMode::Rune:
                    normalized.push_back(ch);
                    consume();
                    if (escaped_) {
                        escaped_ = false;
                    } else if (ch == '\\') {
                        escaped_ = true;
                    } else if (ch == '\'') {
                        lexical_mode_ = LexicalMode::Normal;
                    }
                    break;

                case LexicalMode::Slash:
                    if (ch == '/') {
                        normalized.push_back(ch);
                        consume();
                        lexical_mode_ = LexicalMode::LineComment;
                    } else if (ch == '*') {
                        normalized.push_back(ch);
                        consume();
                        lexical_mode_ = LexicalMode::BlockComment;
                        block_comment_depth_ = 1;
                        block_comment_boundary_ = '\0';
                    } else {
                        lexical_mode_ = LexicalMode::Normal;
                    }
                    break;

                case LexicalMode::LineComment:
                    normalized.push_back(ch);
                    consume();
                    if (ch == '\n' || ch == '\r') {
                        lexical_mode_ = LexicalMode::Normal;
                    }
                    break;

                case LexicalMode::BlockComment:
                    normalized.push_back(ch);
                    consume();
                    if (block_comment_boundary_ == '/' && ch == '*') {
                        ++block_comment_depth_;
                        block_comment_boundary_ = '\0';
                    } else if (block_comment_boundary_ == '*' && ch == '/') {
                        --block_comment_depth_;
                        block_comment_boundary_ = '\0';
                        if (block_comment_depth_ == 0) {
                            lexical_mode_ = LexicalMode::Normal;
                        }
                    } else if (ch == '/' || ch == '*') {
                        block_comment_boundary_ = ch;
                    } else {
                        block_comment_boundary_ = '\0';
                    }
                    break;

                case LexicalMode::Normal:
                    if (is_ascii_identifier_start(ch)) {
                        if (follows_number_like_prefix()) {
                            // x/o/b/e and suffix letters are part of numeric
                            // literals, not standalone identifiers.
                            normalized.push_back(ch);
                            lexical_mode_ = LexicalMode::ExactIdentifier;
                        } else {
                            assert(!identifier_open_gap_.active);
                            identifier_open_gap_ = IdentifierGap{};
                            identifier_buffer_.assign(1, ch);
                            identifier_covered_.assign(1, false);
                            lexical_mode_ = LexicalMode::Identifier;
                        }
                        consume();
                    } else if (ch == '`') {
                        raw_identifier_buffer_.assign(1, ch);
                        raw_identifier_content_size_ = 0;
                        raw_identifier_valid_ = true;
                        lexical_mode_ = LexicalMode::RawIdentifier;
                        consume();
                    } else {
                        normalized.push_back(ch);
                        consume();
                        if (ch == '"') {
                            lexical_mode_ = LexicalMode::QuoteRun;
                            quote_run_size_ = 1;
                        } else if (ch == '\'') {
                            lexical_mode_ = LexicalMode::Rune;
                            escaped_ = false;
                        } else if (ch == '/') {
                            lexical_mode_ = LexicalMode::Slash;
                        }
                    }
                    break;
            }
        }

        if (lexical_mode_ == LexicalMode::Identifier) {
            std::string probe_text = identifier_probe_text();
            return accept_normalized_and_probe(
                std::move(normalized), !probe_text.empty(), probe_text, true
            );
        }
        if (lexical_mode_ == LexicalMode::RawIdentifier) {
            if (!raw_identifier_valid_) return false;
            const std::string probe_text = "`" + canonical_identifier_ + "`";
            return accept_normalized_and_probe(
                std::move(normalized), true, probe_text, false
            );
        }
        return accept_normalized_and_probe(
            std::move(normalized), false, {}, false
        );
    }

    std::vector<std::string> identifier_literals_;
    std::string canonical_identifier_;
    std::size_t max_identifier_literal_length_;
    xgrammar::TokenizerInfo tokenizer_;
    xgrammar::GrammarCompiler compiler_;
    xgrammar::CompiledGrammar compiled_;
    xgrammar::GrammarMatcher matcher_;
    bool speculative_probe_active_ = false;
    std::string speculative_probe_text_;
    std::string pending_;
    LexicalMode lexical_mode_ = LexicalMode::Normal;
    std::string identifier_buffer_;
    std::vector<bool> identifier_covered_;
    IdentifierGap identifier_open_gap_;
    std::string raw_identifier_buffer_;
    std::size_t raw_identifier_content_size_ = 0;
    bool raw_identifier_valid_ = true;
    bool escaped_ = false;
    int quote_run_size_ = 0;
    std::size_t block_comment_depth_ = 0;
    char block_comment_boundary_ = '\0';
    char previous_source_char_ = '\0';
    char previous_source_char_2_ = '\0';
    bool has_previous_source_char_ = false;
    bool has_previous_source_char_2_ = false;
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileSnapshot profile_;
#endif

    // The locked grammar needs at most two non-pumpable adjacent generic
    // identifiers across a nullable boundary (neighboring field declarations).
    // Preserve that exact bound; a larger representative measurably recreates
    // the Earley-state growth this quotient is intended to avoid.
    static constexpr std::size_t kGenericGapRepresentativeLength = 2;
};

#ifdef CANGJIE_ENABLE_GRAMMAR_SHADOW
class LegacySyntaxChecker {
 public:
    explicit LegacySyntaxChecker(const std::string& grammar_source)
        : tokenizer_(std::vector<std::string>{"x"}, xgrammar::VocabType::RAW),
          compiler_(tokenizer_, 1, false),
          compiled_(compiler_.CompileGrammar(grammar_source)),
          matcher_(compiled_) {}

    bool check(std::string_view fragment) {
        pending_.append(fragment.data(), fragment.size());
        std::size_t stable_size = pending_.size();
        while (stable_size > 0) {
            const char ch = pending_[stable_size - 1];
            if (ch != ' ' && ch != '\t' && ch != '\n' && ch != '\r') break;
            --stable_size;
        }
        if (stable_size == 0) return true;
        std::string stable = pending_.substr(0, stable_size);
        pending_.erase(0, stable_size);
        return matcher_.AcceptString(stable);
    }

 private:
    xgrammar::TokenizerInfo tokenizer_;
    xgrammar::GrammarCompiler compiler_;
    xgrammar::CompiledGrammar compiled_;
    xgrammar::GrammarMatcher matcher_;
    std::string pending_;
};

struct CapturedException {
    std::exception_ptr pointer;
    std::string type;
    std::string message;
};

CapturedException describe_exception(std::exception_ptr pointer) {
    if (!pointer) return {};
    try {
        std::rethrow_exception(pointer);
    } catch (const std::exception& error) {
        return {pointer, typeid(error).name(), error.what()};
    } catch (...) {
        return {pointer, "non-std-exception", ""};
    }
}

bool same_exception(const CapturedException& lhs, const CapturedException& rhs) {
    return static_cast<bool>(lhs.pointer) == static_cast<bool>(rhs.pointer) &&
           lhs.type == rhs.type && lhs.message == rhs.message;
}

std::string exception_summary(const CapturedException& error) {
    if (!error.pointer) return "none";
    return error.type + ": " + error.message;
}

class GrammarShadowSyntaxChecker {
 public:
    explicit GrammarShadowSyntaxChecker(const fs::path& grammar_path) {
        const std::string grammar_source = read_text_file(grammar_path);
        CandidateCreation candidate = create_candidate(grammar_source);
        ControlCreation control = create_control(grammar_source);
        ensure_matching_exceptions("matcher initialization", candidate.error, control.error);
        if (candidate.error.pointer) std::rethrow_exception(candidate.error.pointer);
        candidate_ = std::move(candidate.checker);
        control_ = std::move(control.checker);
    }

    bool check(std::string_view fragment) {
        CheckResult candidate = run_check(candidate_.get(), fragment);
        CheckResult control = run_check(control_.get(), fragment);
        ensure_matching_exceptions("AcceptString", candidate.error, control.error);
        if (candidate.error.pointer) std::rethrow_exception(candidate.error.pointer);

        candidate_transcript_.push_back(candidate.value);
        control_transcript_.push_back(control.value);
        const std::size_t index = candidate_transcript_.size() - 1;
        if (!candidate.value && candidate_first_reject_ == kNoReject) {
            candidate_first_reject_ = index;
        }
        if (!control.value && control_first_reject_ == kNoReject) {
            control_first_reject_ = index;
        }
        if (candidate.value != control.value ||
            candidate_first_reject_ != control_first_reject_ ||
            candidate_transcript_.size() != control_transcript_.size()) {
            throw std::runtime_error(
                "grammar shadow mismatch at fragment " + std::to_string(index)
            );
        }
        return candidate.value;
    }

#ifdef CANGJIE_ENABLE_PROFILE
    NativeSyntaxChecker::ProfileSnapshot profile() const {
        return candidate_->profile();
    }
#endif

 private:
    struct CandidateCreation {
        std::unique_ptr<NativeSyntaxChecker> checker;
        CapturedException error;
    };

    struct ControlCreation {
        std::unique_ptr<LegacySyntaxChecker> checker;
        CapturedException error;
    };

    struct CheckResult {
        bool value = false;
        CapturedException error;
    };

    static CandidateCreation create_candidate(const std::string& source) {
        try {
            return {
                std::make_unique<NativeSyntaxChecker>(
                    NativeSyntaxChecker::InMemoryGrammar{}, source
                ),
                {}
            };
        } catch (...) {
            return {nullptr, describe_exception(std::current_exception())};
        }
    }

    static ControlCreation create_control(const std::string& source) {
        try {
            return {std::make_unique<LegacySyntaxChecker>(source), {}};
        } catch (...) {
            return {nullptr, describe_exception(std::current_exception())};
        }
    }

    template <typename Checker>
    static CheckResult run_check(Checker* checker, std::string_view fragment) {
        try {
            return {checker->check(fragment), {}};
        } catch (...) {
            return {false, describe_exception(std::current_exception())};
        }
    }

    static void ensure_matching_exceptions(
        std::string_view operation,
        const CapturedException& candidate,
        const CapturedException& control
    ) {
        if (same_exception(candidate, control)) return;
        throw std::runtime_error(
            "grammar shadow exception mismatch during " + std::string(operation) +
            "; candidate=" + exception_summary(candidate) +
            "; control=" + exception_summary(control)
        );
    }

    static constexpr std::size_t kNoReject = static_cast<std::size_t>(-1);
    std::unique_ptr<NativeSyntaxChecker> candidate_;
    std::unique_ptr<LegacySyntaxChecker> control_;
    std::vector<bool> candidate_transcript_;
    std::vector<bool> control_transcript_;
    std::size_t candidate_first_reject_ = kNoReject;
    std::size_t control_first_reject_ = kNoReject;
};

int hex_digit_value(char digit) {
    if (digit >= '0' && digit <= '9') return digit - '0';
    if (digit >= 'a' && digit <= 'f') return digit - 'a' + 10;
    if (digit >= 'A' && digit <= 'F') return digit - 'A' + 10;
    return -1;
}

std::string decode_hex_fragment(std::string_view line) {
    if (line.size() % 2 != 0) {
        throw std::runtime_error("grammar shadow fragment has odd-length hex input");
    }
    std::string fragment;
    fragment.reserve(line.size() / 2);
    for (std::size_t index = 0; index < line.size(); index += 2) {
        const int high = hex_digit_value(line[index]);
        const int low = hex_digit_value(line[index + 1]);
        if (high < 0 || low < 0) {
            throw std::runtime_error("grammar shadow fragment has invalid hex input");
        }
        fragment.push_back(static_cast<char>((high << 4) | low));
    }
    return fragment;
}
#endif

struct Args {
    std::string context_path;
    bool competition_output = false;
#ifdef CANGJIE_ENABLE_GRAMMAR_SHADOW
    bool grammar_shadow_fragments = false;
#endif
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
#ifdef CANGJIE_ENABLE_GRAMMAR_SHADOW
        } else if (arg == "--grammar-shadow-fragments") {
            result.grammar_shadow_fragments = true;
#endif
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

std::string json_escape(const std::string& raw) {
    std::string out;
    out.reserve(raw.size() + 8);
    for (const char ch : raw) {
        switch (ch) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (static_cast<unsigned char>(ch) < 0x20) {
                    constexpr char kHex[] = "0123456789abcdef";
                    out += "\\u00";
                    out += kHex[(ch >> 4) & 0xF];
                    out += kHex[ch & 0xF];
                } else {
                    out += ch;
                }
        }
    }
    return out;
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
        ShutdownObjectProfiler shutdown_profiler(
            phase_profile.enabled() ? &phase_profile.shutdown_object_destroy_ns : nullptr
        );
#endif
        std::ios::sync_with_stdio(false);
        std::cin.tie(nullptr);
        const Args args = parse_args(argc, argv);
        const fs::path root = executable_root(argv[0]);
#ifdef CANGJIE_ENABLE_GRAMMAR_SHADOW
        if (args.grammar_shadow_fragments) {
            GrammarShadowSyntaxChecker syntax(root / "grammar" / "cangjie.gbnf");
            std::string encoded_fragment;
            while (std::getline(std::cin, encoded_fragment)) {
                const std::string fragment = decode_hex_fragment(encoded_fragment);
                const bool ok = syntax.check(fragment);
                emit(ok, args.competition_output);
                if (!ok) break;
            }
            return 0;
        }
#endif
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
            phase_started = PhaseProfiler::Clock::now();
        }
#endif
#ifdef CANGJIE_ENABLE_GRAMMAR_SHADOW
        GrammarShadowSyntaxChecker syntax(root / "grammar" / "cangjie.gbnf");
#else
        NativeSyntaxChecker syntax(root / "grammar" / "cangjie.gbnf");
#endif
#ifdef CANGJIE_ENABLE_PROFILE
        if (phase_profile.enabled()) {
            phase_profile.grammar_init_ns += PhaseProfiler::Elapsed(phase_started);
            phase_profile.startup_wall_ns += PhaseProfiler::Elapsed(startup_started);
        }
#endif

        std::string line;
        std::size_t tokens_seen = 0;
        while (std::getline(std::cin, line)) {
            std::int64_t token_id = -1;
            std::string_view fragment;
            if (!parse_token_id(line, &token_id) || !token_table.decode(token_id, &fragment)) {
                emit(false, args.competition_output);
                return 0;
            }
#ifdef CANGJIE_ENABLE_PROFILE
            phase_started = PhaseProfiler::Clock::now();
#endif
            const bool syntax_ok = syntax.check(fragment);
#ifdef CANGJIE_ENABLE_PROFILE
            std::uint64_t syntax_elapsed = 0;
            if (phase_profile.enabled()) {
                syntax_elapsed = PhaseProfiler::Elapsed(phase_started);
                phase_profile.syntax_check_ns += syntax_elapsed;
                phase_started = PhaseProfiler::Clock::now();
            }
#endif
            const cangjie::CheckStatus semantic_status = native_semantic.Check(fragment);
#ifdef CANGJIE_ENABLE_PROFILE
            if (phase_profile.enabled()) {
                const std::uint64_t semantic_elapsed = PhaseProfiler::Elapsed(phase_started);
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
            if (!ok && std::getenv("CANGJIE_TRACE_FIRE")) {
                std::cerr << "{\"event\":\"fire\",\"token\":" << tokens_seen
                          << ",\"syntax_ok\":" << (syntax_ok ? "true" : "false")
                          << ",\"message\":\"" << json_escape(semantic_status.message) << "\"}\n";
            }
            emit(ok, args.competition_output);
            if (!ok) break;
            ++tokens_seen;
        }
#ifdef CANGJIE_ENABLE_PROFILE
        if (phase_profile.enabled()) {
            const NativeSyntaxChecker::ProfileSnapshot snapshot = syntax.profile();
            phase_profile.syntax_stable_bytes = snapshot.stable_bytes;
            phase_profile.syntax_trailing_whitespace_scan_bytes =
                snapshot.trailing_whitespace_scan_bytes;
            phase_profile.syntax_stable_over_15_bytes_calls =
                snapshot.stable_over_15_bytes_calls;
            phase_profile.syntax_pending_capacity_growths =
                snapshot.pending_capacity_growths;
        }
        shutdown_profiler.Arm();
#endif
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "native solution error: " << error.what() << '\n';
        return 1;
    }
}
