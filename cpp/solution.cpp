// Native competition protocol and cl100k decoder.
//
// Syntax transitions run through XGrammar's native C++ API. Semantic checking
// stays in the lightweight Python worker so the C++ optimization preserves
// the already differential-tested type rules while removing tiktoken and
// XGrammar Python cold imports from the timed process.

#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <utility>
#include <vector>

#include <xgrammar/xgrammar.h>

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

std::uint32_t read_u32(std::istream& stream) {
    unsigned char bytes[4]{};
    stream.read(reinterpret_cast<char*>(bytes), sizeof(bytes));
    if (!stream) {
        throw std::runtime_error("truncated cl100k table");
    }
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
        char magic[8]{};
        stream.read(magic, sizeof(magic));
        if (!stream || std::memcmp(magic, kTableMagic, sizeof(magic)) != 0) {
            throw std::runtime_error("invalid cl100k table header");
        }
        const std::uint32_t count = read_u32(stream);
        const std::uint32_t blob_size = read_u32(stream);
        entries_.reserve(count);
        for (std::uint32_t index = 0; index < count; ++index) {
            entries_.emplace_back(read_u32(stream), read_u32(stream));
        }
        blob_.resize(blob_size);
        stream.read(blob_.data(), static_cast<std::streamsize>(blob_.size()));
        if (!stream) {
            throw std::runtime_error("truncated cl100k table payload");
        }
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

void close_fd(int fd) {
    if (fd >= 0) {
        while (::close(fd) < 0 && errno == EINTR) {
        }
    }
}

class SemanticWorker {
 public:
    SemanticWorker(const fs::path& root, const std::string& context_path) {
        int parent_to_child[2] = {-1, -1};
        int child_to_parent[2] = {-1, -1};
        if (::pipe(parent_to_child) != 0 || ::pipe(child_to_parent) != 0) {
            throw std::runtime_error("cannot create semantic worker pipes");
        }
        pid_ = ::fork();
        if (pid_ < 0) {
            close_fd(parent_to_child[0]);
            close_fd(parent_to_child[1]);
            close_fd(child_to_parent[0]);
            close_fd(child_to_parent[1]);
            throw std::runtime_error("cannot fork semantic worker");
        }
        if (pid_ == 0) {
            ::dup2(parent_to_child[0], STDIN_FILENO);
            ::dup2(child_to_parent[1], STDOUT_FILENO);
            close_fd(parent_to_child[0]);
            close_fd(parent_to_child[1]);
            close_fd(child_to_parent[0]);
            close_fd(child_to_parent[1]);
            const std::string script = (root / "src" / "native_semantic_worker.py").string();
            if (context_path.empty()) {
                ::execlp("python3", "python3", script.c_str(), static_cast<char*>(nullptr));
            } else {
                ::execlp(
                    "python3", "python3", script.c_str(), "--context", context_path.c_str(),
                    static_cast<char*>(nullptr)
                );
            }
            std::cerr << "cannot exec native semantic worker: " << std::strerror(errno) << '\n';
            _exit(127);
        }
        close_fd(parent_to_child[0]);
        close_fd(child_to_parent[1]);
        write_fd_ = parent_to_child[1];
        read_fd_ = child_to_parent[0];
    }

    SemanticWorker(const SemanticWorker&) = delete;
    SemanticWorker& operator=(const SemanticWorker&) = delete;

    ~SemanticWorker() {
        close_fd(write_fd_);
        close_fd(read_fd_);
        if (pid_ > 0) {
            int status = 0;
            while (::waitpid(pid_, &status, 0) < 0 && errno == EINTR) {
            }
        }
    }

    bool check(std::string_view fragment) {
        static constexpr char kHex[] = "0123456789abcdef";
        std::string message;
        message.reserve(fragment.size() * 2 + 1);
        for (unsigned char byte : fragment) {
            message.push_back(kHex[byte >> 4u]);
            message.push_back(kHex[byte & 0x0fu]);
        }
        message.push_back('\n');
        write_all(message);
        char answer = '\0';
        read_exact(&answer, 1);
        char newline = '\0';
        read_exact(&newline, 1);
        if ((answer != '0' && answer != '1') || newline != '\n') {
            throw std::runtime_error("invalid response from semantic worker");
        }
        return answer == '0';
    }

 private:
    void write_all(std::string_view data) {
        std::size_t offset = 0;
        while (offset < data.size()) {
            const ssize_t count = ::write(write_fd_, data.data() + offset, data.size() - offset);
            if (count < 0 && errno == EINTR) {
                continue;
            }
            if (count <= 0) {
                throw std::runtime_error("semantic worker pipe write failed");
            }
            offset += static_cast<std::size_t>(count);
        }
    }

    void read_exact(char* output, std::size_t size) {
        std::size_t offset = 0;
        while (offset < size) {
            const ssize_t count = ::read(read_fd_, output + offset, size - offset);
            if (count < 0 && errno == EINTR) {
                continue;
            }
            if (count <= 0) {
                throw std::runtime_error("semantic worker pipe read failed");
            }
            offset += static_cast<std::size_t>(count);
        }
    }

    pid_t pid_ = -1;
    int write_fd_ = -1;
    int read_fd_ = -1;
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
    std::size_t last = line.find_last_not_of(" \t\r");
    const std::string trimmed = line.substr(first, last - first + 1);
    std::size_t consumed = 0;
    try {
        const long long value = std::stoll(trimmed, &consumed, 10);
        if (consumed != trimmed.size()) {
            return false;
        }
        *output = static_cast<std::int64_t>(value);
        return true;
    } catch (const std::exception&) {
        return false;
    }
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
        const Args args = parse_args(argc, argv);
        const fs::path root = executable_root(argv[0]);
        const TokenTable token_table(root / "generated" / "cl100k_base.bin");
        NativeSyntaxChecker syntax(root / "grammar" / "cangjie.gbnf");
        SemanticWorker semantic(root, args.context_path);

        std::string line;
        while (std::getline(std::cin, line)) {
            std::int64_t token_id = -1;
            std::string_view fragment;
            if (!parse_token_id(line, &token_id) || !token_table.decode(token_id, &fragment)) {
                emit(false, args.competition_output);
                return 0;
            }
            const bool syntax_ok = syntax.check(fragment);
            const bool ok = syntax_ok && semantic.check(fragment);
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
