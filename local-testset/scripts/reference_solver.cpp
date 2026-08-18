// Reference stdin/stdout solver for token_interaction_test.py (language-agnostic protocol).
//
// Protocol (this repo's harness convention, not the competition PDF):
// - Harness sends one tiktoken token ID per line on stdin.
// - This program replies with one line per round: "0" or "1".
//   - "0": no error reported at this round.
//   - "1": error reported at this round (first non-continuable prefix).
//
// Build (from repo root):
//   c++ -std=c++17 -O2 -o scripts/reference_solver_cpp \
//     scripts/reference_solver.cpp
//
// Example:
//   python3 scripts/token_interaction_test.py err_arity.cj \
//     --cmd ./scripts/reference_solver_cpp \
//     --cangjie-file wrong/err_arity.cj

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {

std::string trim(const std::string& s) {
    size_t start = 0;
    while (start < s.size() && (s[start] == ' ' || s[start] == '\t' || s[start] == '\r')) {
        ++start;
    }
    size_t end = s.size();
    while (end > start && (s[end - 1] == ' ' || s[end - 1] == '\t' || s[end - 1] == '\r')) {
        --end;
    }
    return s.substr(start, end - start);
}

bool file_exists(const std::string& path) {
    std::ifstream f(path);
    return f.good();
}

std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f) {
        throw std::runtime_error("cannot read file: " + path);
    }
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

std::string stem_from_path(const std::string& path) {
    size_t slash = path.find_last_of("/\\");
    std::string base = (slash == std::string::npos) ? path : path.substr(slash + 1);
    size_t dot = base.find_last_of('.');
    if (dot == std::string::npos) {
        return base;
    }
    return base.substr(0, dot);
}

std::string resolve_cangjie_file(const std::string& user_arg, const std::string& repo_root) {
    if (file_exists(user_arg)) {
        return user_arg;
    }
    std::string rel = user_arg;
    if (rel.rfind("samples/", 0) == 0) {
        rel = rel.substr(8);
    }
    const std::vector<std::string> candidates = {
        repo_root + "/" + rel,
        repo_root + "/wrong/" + rel,
        repo_root + "/wrong/" + stem_from_path(rel),
    };
    for (const auto& c : candidates) {
        if (file_exists(c)) {
            return c;
        }
    }
    throw std::runtime_error("Cangjie file not found: " + user_arg);
}

std::map<std::string, int> load_first_error_token_indices(const std::string& json_path) {
    const std::string text = read_file(json_path);
    std::map<std::string, int> out;

    size_t pos = 0;
    while (true) {
        const size_t name_key = text.find("\"name\"", pos);
        if (name_key == std::string::npos) {
            break;
        }
        const size_t name_quote = text.find('"', text.find(':', name_key) + 1);
        if (name_quote == std::string::npos) {
            break;
        }
        const size_t name_end = text.find('"', name_quote + 1);
        if (name_end == std::string::npos) {
            break;
        }
        const std::string name = text.substr(name_quote + 1, name_end - name_quote - 1);

        const size_t idx_key = text.find("\"first_error_token_index\"", name_end);
        if (idx_key == std::string::npos) {
            break;
        }
        const size_t idx_colon = text.find(':', idx_key);
        if (idx_colon == std::string::npos) {
            break;
        }
        size_t i = idx_colon + 1;
        while (i < text.size() && (text[i] == ' ' || text[i] == '\t' || text[i] == '\n' || text[i] == '\r')) {
            ++i;
        }
        size_t j = i;
        while (j < text.size() && (text[j] == '-' || (text[j] >= '0' && text[j] <= '9'))) {
            ++j;
        }
        if (j == i) {
            throw std::runtime_error("invalid first_error_token_index for " + name);
        }
        out[name] = std::stoi(text.substr(i, j - i));
        pos = j;
    }

    return out;
}

struct Args {
    std::string cangjie_file;
    std::string error_json;
};

Args parse_args(int argc, char** argv, const std::string& default_error_json) {
    Args args;
    args.error_json = default_error_json;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--cangjie-file" && i + 1 < argc) {
            args.cangjie_file = argv[++i];
        } else if (arg == "--error-json" && i + 1 < argc) {
            args.error_json = argv[++i];
        } else if (arg == "--encoding" && i + 1 < argc) {
            ++i;  // accepted for CLI parity; solver only uses round index
        } else if (arg == "-h" || arg == "--help") {
            std::cout
                << "Usage: reference_solver_cpp --cangjie-file PATH [--error-json PATH]\n"
                << "Reads token IDs from stdin; prints 0/1 per round.\n";
            std::exit(0);
        } else {
            throw std::runtime_error("unknown argument: " + arg);
        }
    }
    if (args.cangjie_file.empty()) {
        throw std::runtime_error("missing required --cangjie-file");
    }
    return args;
}

std::string executable_dir(char* argv0) {
    const std::string path = argv0 ? std::string(argv0) : std::string();
    const size_t slash = path.find_last_of("/\\");
    if (slash == std::string::npos) {
        return ".";
    }
    return path.substr(0, slash);
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const std::string exe_dir = executable_dir(argv[0]);
        const std::string repo_root = exe_dir + "/..";
        const std::string default_error_json = repo_root + "/wrong_error_positions.json";

        const Args args = parse_args(argc, argv, default_error_json);
        const std::string cj_path = resolve_cangjie_file(args.cangjie_file, repo_root);
        const std::string stem = stem_from_path(cj_path);

        const std::string error_json = file_exists(args.error_json) ? args.error_json : default_error_json;
        const auto error_map = load_first_error_token_indices(error_json);

        const auto it = error_map.find(stem);
        const bool has_target = it != error_map.end();
        const int target_idx = has_target ? it->second : -1;

        int round_idx = 0;
        std::string line;
        while (std::getline(std::cin, line)) {
            line = trim(line);
            if (line.empty()) {
                continue;
            }
            if (has_target && round_idx == target_idx) {
                std::cout << "1\n";
            } else {
                std::cout << "0\n";
            }
            std::cout.flush();
            ++round_idx;
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "reference_solver_cpp: " << e.what() << "\n";
        return 1;
    }
}
