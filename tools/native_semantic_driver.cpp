#include <cctype>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

#include "native_semantic.h"

namespace {

int hex_value(char ch) {
    if (ch >= '0' && ch <= '9') return ch - '0';
    ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    return -1;
}

std::string decode_hex(const std::string& line) {
    if (line.size() % 2 != 0) throw std::runtime_error("odd hex fragment");
    std::string output;
    output.reserve(line.size() / 2);
    for (std::size_t index = 0; index < line.size(); index += 2) {
        const int high = hex_value(line[index]);
        const int low = hex_value(line[index + 1]);
        if (high < 0 || low < 0) throw std::runtime_error("invalid hex fragment");
        output.push_back(static_cast<char>((high << 4) | low));
    }
    return output;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: native_semantic_driver CONTEXT_BIN");
        cangjie::NativeSemanticChecker checker(argv[1]);
        std::string line;
        while (std::getline(std::cin, line)) {
            const cangjie::CheckStatus status = checker.Check(decode_hex(line));
            std::cout << (status.ok ? 0 : 1) << '\n';
            if (!status.ok) {
                if (std::getenv("CANGJIE_DEBUG_SEMANTIC")) {
                    std::cerr << status.message << '\n';
                }
                break;
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
