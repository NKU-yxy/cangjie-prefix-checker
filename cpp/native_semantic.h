#pragma once

#include <cstddef>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace cangjie {

enum class TokenKind {
    Identifier,
    Integer,
    Floating,
    String,
    Rune,
    Symbol,
    Newline,
};

struct TokenEvent {
    TokenKind kind = TokenKind::Symbol;
    std::string text;
    bool complete = true;
};

struct PartialLexeme {
    std::string text;
    std::vector<TokenKind> candidates;
};

struct CheckStatus {
    bool ok = true;
    std::string message;
};

struct Checkpoint {
    std::size_t accepted_tokens = 0;
    std::size_t source_bytes = 0;
};

class IncrementalLexer {
 public:
    struct Result {
        std::vector<TokenEvent> stable;
        PartialLexeme partial;
    };

    Result Feed(std::string_view bytes);

 private:
    std::string pending_;
};

class IncrementalSemanticEngine {
 public:
    explicit IncrementalSemanticEngine(std::string context_path = {});
    ~IncrementalSemanticEngine();

    IncrementalSemanticEngine(const IncrementalSemanticEngine&) = delete;
    IncrementalSemanticEngine& operator=(const IncrementalSemanticEngine&) = delete;

    CheckStatus Accept(const TokenEvent& event);
    CheckStatus Probe(const PartialLexeme& partial, std::string_view source);
    Checkpoint Save() const;
    void Rollback(const Checkpoint& checkpoint);

 private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

class NativeSemanticChecker {
 public:
    explicit NativeSemanticChecker(std::string context_path = {});
    CheckStatus Check(std::string_view bytes);

 private:
    IncrementalLexer lexer_;
    IncrementalSemanticEngine engine_;
    std::string source_;
    bool failed_ = false;
    std::string failure_message_;
};

}  // namespace cangjie
