#pragma once

#include <cstddef>
#include <memory>
#include <ostream>
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

// V14 Patch 2: shadow frontier classification, recorded per fire and never
// consulted by the decision path (shadow-only until Patch 5 activation).
enum class SymbolKind {
    None,         // no identifier at the frontier (non-identifier fire)
    Local,        // local variable / parameter
    Global,       // global variable
    Function,     // global or user function (callee or value position)
    Method,       // instance method
    Field,        // instance field
    StaticMember, // static method or static field
    Type,         // nominal type name
    Primitive,    // primitive type name
    Unknown,      // not resolvable
};

enum class TailKind {
    None,
    Call,         // '(' follows (possibly after type arguments)
    Member,       // '.' follows
    Type,         // in type position (after ':' / inside type arguments)
    Value,        // plain value position
};

enum class BoundaryKind {
    None,
    Statement,    // expression statement
    AssignRhs,    // right of '='
    Return,       // after 'return'
    Condition,    // if/while condition
    LoopHead,     // for header
    CallArg,      // argument of an enclosing call
    MemberSel,    // after '.'
    Decl,         // var/let name or type annotation
};

// Shadow-only verdict; Unknown symbols are never adjudicated Dead (Patch 2
// completion standard: no UnknownSymbol directly judged Dead).
enum class FrontierVerdict { None, Alive, Dead, Unknown };

struct FrontierInfo {
    std::string symbol;    // frontier identifier text ("" for non-identifier fires)
    SymbolKind symbol_kind = SymbolKind::None;
    TailKind tail_kind = TailKind::None;
    BoundaryKind boundary_kind = BoundaryKind::None;
    std::string receiver;  // TypeHead of the member receiver, if member selection
    FrontierVerdict verdict = FrontierVerdict::None;
};

const char* SymbolKindName(SymbolKind kind);
const char* TailKindName(TailKind kind);
const char* BoundaryKindName(BoundaryKind kind);
const char* FrontierVerdictName(FrontierVerdict verdict);

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

    // Dump the preloaded context model as canonical Context IR JSON
    // (context-ir-v1, same schema as tools/export_official_context_ir.py).
    void DumpContextIrJson(std::ostream& os) const;

    // Shadow frontier classification of the last failed Probe (Patch 2).
    // Empty FrontierInfo when the last Probe succeeded or had no identifier.
    const FrontierInfo& LastFrontier() const;

 private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

class NativeSemanticChecker {
 public:
    explicit NativeSemanticChecker(std::string context_path = {});
    CheckStatus Check(std::string_view bytes);
    void DumpContextIrJson(std::ostream& os) const { engine_.DumpContextIrJson(os); }
    const FrontierInfo& LastFrontier() const { return engine_.LastFrontier(); }

 private:
    IncrementalLexer lexer_;
    IncrementalSemanticEngine engine_;
    std::string source_;
    bool failed_ = false;
    std::string failure_message_;
};

}  // namespace cangjie
