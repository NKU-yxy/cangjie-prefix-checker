#pragma once

// V14 Patch 4 (shadow): per-overload call candidate frontier (plan §8).
//
// For a fire at a call site, every overload of the callee gets an independent
// candidate state: which arguments are already typed and compatible, how many
// parameters remain, whether the call can close now, and — when a candidate is
// eliminated — the concrete reason.  Nothing here consults the decision path;
// the trace prints alive counts and elimination reasons (completion standard:
// "所有调用可打印 alive candidate 数量；所有淘汰有 reason").
//
// The classifier is deliberately narrow: type compatibility is supplied by the
// caller (a Model-aware predicate), so this TU stays self-contained.
//
// §8.2 rules implemented: (1) per-overload independent state; (2) a typed
// argument eliminates a candidate only when no legal suffix can make it
// compatible (unknown arg types never veto); (3) the ',' commits arguments
// without a premature arity verdict (matched only counts closed pieces);
// (4) ')' performs the final arity/default check (ArityShortAtClose); (5) the
// expected return type is recorded (ExpectedReturnOnly) but never eliminates;
// (6) unbound type variables stay symbolic (never eliminate by mismatch, never
// declared dead by arity either).

#include <cstddef>
#include <functional>
#include <string>
#include <string_view>
#include <vector>

namespace cangjie {

enum class CandidateState {
    Alive,               // still viable; may be waiting for more input
    WaitingForMoreInput, // viable but cannot close before more args arrive
    Dead,                // eliminated (reason set)
};

enum class EliminationReason {
    None,
    ArityExceeded,     // more args typed than the overload accepts
    ArgTypeMismatch,   // a typed argument can never be compatible (non-symbolic)
    ArityShortAtClose, // call closed with fewer args than required params
    ExpectedReturnOnly,// result incompatible with expected type (deferred —
                       // never eliminates by itself; recorded for reporting)
};

struct CallCandidate {
    std::size_t overload_index = 0;
    std::size_t next_param = 0;      // first not-yet-matched parameter index
    bool accepts_more = false;       // another argument could still arrive
    bool can_close_now = false;      // ")" at this point satisfies arity
    CandidateState state = CandidateState::Alive;
    EliminationReason reason = EliminationReason::None;
};

struct CallFrontierResult {
    std::string callee;
    bool resolved = false;           // callee resolved to >= 1 overload
    std::size_t overload_count = 0;
    std::size_t alive_count = 0;     // candidates not eliminated
    bool call_closed = false;        // the call group is balanced at line end
    std::vector<CallCandidate> candidates;
    std::vector<std::string> reasons;  // printable per-candidate reason lines
};

// One overload signature, already substituted for the receiver.
struct OverloadView {
    std::string name;
    std::vector<std::string> param_types;
    std::string result_type;
    std::vector<std::string> type_params;  // still-unbound generic parameters
    std::size_t required = 0;              // mandatory parameter count (0 = all)
};

// Caller-supplied predicate (Model-aware): "can a value of type got be passed
// where want is expected?"  Captures allowed (the caller binds its Model).
using CompatPredicate = std::function<bool(std::string_view got, std::string_view want)>;

class CallFrontierClassifier {
 public:
    // typed_args: complete arguments typed so far at the call site (top-level
    // comma split, trailing incomplete argument dropped), already reduced to
    // their best-effort types ("" = unknown, never vetoes).
    CallFrontierResult Classify(
        const std::string& callee,
        const std::vector<OverloadView>& overloads,
        const std::vector<std::string>& typed_args,
        const std::string& expected_type,
        bool call_closed,
        CompatPredicate compat) const;
};

}  // namespace cangjie
