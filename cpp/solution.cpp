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

#include <charconv>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
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

constexpr char kTableMagic[8] = {'C', 'J', 'T', 'K', 1, 0, 0, 0};
constexpr std::uint32_t kMissing = 0xFFFFFFFFu;

std::uint32_t read_u32_unchecked(const char* data) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(data);
    return static_cast<std::uint32_t>(bytes[0]) |
           (static_cast<std::uint32_t>(bytes[1]) << 8u) |
           (static_cast<std::uint32_t>(bytes[2]) << 16u) |
           (static_cast<std::uint32_t>(bytes[3]) << 24u);
}

std::uint32_t read_u32(std::string_view data, std::size_t* cursor) {
    if (*cursor > data.size() || data.size() - *cursor < 4) {
        throw std::runtime_error("truncated cl100k table");
    }
    const std::uint32_t value = read_u32_unchecked(data.data() + *cursor);
    *cursor += 4;
    return value;
}

class TokenTable {
 public:
    explicit TokenTable(const fs::path& path) {
        std::ifstream stream(path, std::ios::binary);
        if (!stream) {
            throw std::runtime_error("cannot open token table: " + path.string());
        }
        data_ = std::string{
            std::istreambuf_iterator<char>(stream),
            std::istreambuf_iterator<char>()
        };
        if (data_.size() < sizeof(kTableMagic) ||
            std::memcmp(data_.data(), kTableMagic, sizeof(kTableMagic)) != 0) {
            throw std::runtime_error("invalid cl100k table header");
        }
        std::size_t cursor = sizeof(kTableMagic);
        entry_count_ = read_u32(data_, &cursor);
        blob_size_ = read_u32(data_, &cursor);
        entries_offset_ = cursor;
        if (entry_count_ > (data_.size() - cursor) / 8) {
            throw std::runtime_error("truncated cl100k table entries");
        }
        blob_offset_ = cursor + static_cast<std::size_t>(entry_count_) * 8;
        if (blob_size_ > data_.size() - blob_offset_) {
            throw std::runtime_error("truncated cl100k table payload");
        }
        for (std::uint32_t index = 0; index < entry_count_; ++index) {
            std::size_t entry_cursor = entries_offset_ + static_cast<std::size_t>(index) * 8;
            const std::uint32_t offset = read_u32(data_, &entry_cursor);
            const std::uint32_t length = read_u32(data_, &entry_cursor);
            if (offset != kMissing &&
                (offset > blob_size_ || length > blob_size_ - offset)) {
                throw std::runtime_error("invalid cl100k table entry");
            }
        }
    }

    bool decode(std::int64_t token_id, std::string_view* decoded) const {
        if (token_id < 0 || static_cast<std::uint64_t>(token_id) >= entry_count_) {
            return false;
        }
        const char* entry = data_.data() + entries_offset_ +
            static_cast<std::size_t>(token_id) * 8;
        const std::uint32_t offset = read_u32_unchecked(entry);
        const std::uint32_t length = read_u32_unchecked(entry + 4);
        if (offset == kMissing) {
            return false;
        }
        *decoded = std::string_view(data_.data() + blob_offset_ + offset, length);
        return true;
    }

 private:
    std::string data_;
    std::size_t entries_offset_ = 0;
    std::size_t blob_offset_ = 0;
    std::uint32_t entry_count_ = 0;
    std::uint32_t blob_size_ = 0;
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
    explicit NativeSyntaxChecker(const fs::path& grammar_path)
        : tokenizer_(std::vector<std::string>{"x"}, xgrammar::VocabType::RAW),
          compiler_(tokenizer_, 1, false),
          compiled_(compiler_.CompileGrammar(read_text_file(grammar_path))),
          matcher_(compiled_) {}

    bool check(std::string_view fragment) {
        pending_.append(fragment.data(), fragment.size());
        std::size_t stable_size = pending_.size();
        while (stable_size > 0) {
            const char ch = pending_[stable_size - 1];
            if (ch != ' ' && ch != '\t' && ch != '\n' && ch != '\r') {
                break;
            }
            --stable_size;
        }
        if (stable_size == 0) {
            return true;
        }
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
        std::ios::sync_with_stdio(false);
        std::cin.tie(nullptr);
        const Args args = parse_args(argc, argv);
        const fs::path root = executable_root(argv[0]);
        fs::path native_context = root / "generated" / "context.bin";
        if (!args.context_path.empty() && fs::path(args.context_path).extension() == ".bin") {
            native_context = args.context_path;
        }
        cangjie::NativeSemanticChecker native_semantic(native_context.string());
        const TokenTable token_table(root / "generated" / "cl100k_base.bin");
        NativeSyntaxChecker syntax(root / "grammar" / "cangjie.gbnf");

        std::string line;
        while (std::getline(std::cin, line)) {
            std::int64_t token_id = -1;
            std::string_view fragment;
            if (!parse_token_id(line, &token_id) || !token_table.decode(token_id, &fragment)) {
                emit(false, args.competition_output);
                return 0;
            }
            const bool syntax_ok = syntax.check(fragment);
            const cangjie::CheckStatus semantic_status = native_semantic.Check(fragment);
            const bool semantic_ok = semantic_status.ok;
            if (!semantic_status.ok && std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
                std::cerr << "native semantic rejection: " << semantic_status.message << '\n';
            }
            const bool ok = syntax_ok && semantic_ok;
            emit(ok, args.competition_output);
            if (!ok) {
                return 0;
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "native solution error: " << error.what() << '\n';
        return 1;
    }
}
