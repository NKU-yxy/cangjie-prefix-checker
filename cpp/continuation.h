// V15 Patch 1: Proof-Carrying Continuation types (V15_Plan §五).
//
// The v15 decision contract (plan §四/§五):
//   - open expressions are only ever Alive or Unknown; a missing legal
//     continuation is Unknown, never Dead;
//   - Dead is allowed only at hard commit boundaries (`)`, `]`, lambda/block
//     `}`, committed argument separators, type-committing operators, first
//     token of the next statement);
//   - baseline = v12-F1-L decision; the proof layer may only override it when
//     proof_kind != None.
#pragma once

#include <string>
#include <vector>

namespace cangjie {

enum class ContinuationState {
    Alive,   // a legal continuation exists
    Dead,    // all continuations are provably eliminated
    Unknown, // not proven either way
};

enum class ProofKind {
    None,                  // no proof: baseline decides
    ValidSuffix,           // a complete, compilable suffix was found
    OfficialAudit,         // official public audit supports the decision
    ClosedWorldExhaustive, // transition set complete and all candidates dead
};

struct ContinuationProof {
    ContinuationState state = ContinuationState::Unknown;
    ProofKind proof = ProofKind::None;

    std::string rule_id;
    std::string printable_suffix;

    bool transition_set_complete = false;
    std::vector<std::string> eliminated_candidates;
};

// Decision context captured at a fire/defer decision site.  This is the
// input to ComputeProof; `site` is the message-derived decision family
// (let_initializer / assignment_rhs / return / call_close / ...).
struct DecisionContext {
    std::string site;        // decision family (message-derived)
    std::string prefix;      // fire-time source up to and including this token
    bool baseline_reject;    // v12-F1-L baseline decision: true = reject/fire
    std::string symbol_kind; // shadow frontier symbol kind ("" = n/a)
    std::string tail_kind;   // shadow frontier tail kind
    std::string boundary;    // shadow frontier boundary kind
    std::string expected_type; // "" = none known
    std::string actual_type;   // "" = none known
    int candidate_count = -1;  // call_frontier overloads (-1 = n/a)
    bool call_closed = false;  // call frontier saw the closing ')'
    // Patch 4: array-literal element fires.  The engine checks element types
    // while the literal is still open (before ']' is committed); V15 allows
    // Alive there because the baseline re-checks the closed literal at ']'
    // (a hard commit boundary), so a genuinely incompatible element still
    // fires at the commit point.
    bool element_open = false;       // fire sits inside an unclosed '['
    std::string element_expected;    // element type of the enclosing literal
};

// One ledger entry (V15_Plan Patch 1 schema).
struct DecisionLedgerEntry {
    std::string decision_id;
    std::string site;
    std::string prefix;
    std::string baseline;   // "alive" (defer) | "dead" (reject)
    std::string frontier;   // ContinuationState name
    std::string proof_kind; // ProofKind name
    std::string symbol_kind;
    std::string tail_kind;
    std::string boundary;
    int candidate_count = -1;
    std::string expected_type;
    std::string actual_type;
    std::string rule_id;       // proof rule (e.g. "v15-p4-array-element")
    std::string printable_suffix; // suffix the proof asserts ("" = none)
    bool overridden = false; // proof changed the baseline outcome
};

const char* ContinuationStateName(ContinuationState state);
const char* ProofKindName(ProofKind kind);

}  // namespace cangjie
