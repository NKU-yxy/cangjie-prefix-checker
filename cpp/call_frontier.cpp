#include "call_frontier.h"

#include <cctype>
#include <sstream>

namespace cangjie {

namespace {

// An unbound generic parameter in a parameter type ("T" or "Array<T>") means
// the argument cannot be judged Dead by type mismatch (plan §8.2 rule 6:
// symbolic type variables are neither alive-by-anything nor dead).
// 判断参数类型中是否出现未绑定的泛型参数（出现则不能凭类型失配判死）
bool HasUnboundTypeParam(std::string_view type, const std::vector<std::string>& tparams) {
    if (tparams.empty()) return false;
    const std::string text(type);
    for (const std::string& tp : tparams) {
        if (text == tp) return true;
        // "Array<T>" contains the bare parameter as a whole word.
        const std::size_t pos = text.find(tp);
        if (pos != std::string::npos) {
            const bool left_ok = pos == 0 || !(std::isalnum(
                static_cast<unsigned char>(text[pos - 1])) || text[pos - 1] == '_');
            const std::size_t after = pos + tp.size();
            const bool right_ok = after >= text.size() || !(std::isalnum(
                static_cast<unsigned char>(text[after])) || text[after] == '_');
            if (left_ok && right_ok) return true;
        }
    }
    return false;
}

}  // namespace

// 分类调用点：对每个重载候选独立判断存活/等待/淘汰状态，给出淘汰原因
CallFrontierResult CallFrontierClassifier::Classify(
    const std::string& callee,
    const std::vector<OverloadView>& overloads,
    const std::vector<std::string>& typed_args,
    const std::string& expected_type,
    bool call_closed,
    CompatPredicate compat) const {
    CallFrontierResult result;
    result.callee = callee;
    result.resolved = !overloads.empty();
    result.overload_count = overloads.size();
    result.call_closed = call_closed;
    result.candidates.reserve(overloads.size());

    for (std::size_t oi = 0; oi < overloads.size(); ++oi) {
        const OverloadView& ov = overloads[oi];
        CallCandidate cand;
        cand.overload_index = oi;
        const std::size_t effective_required =
            ov.required > 0 ? ov.required : ov.param_types.size();

        // Rule 1/2/3: walk the already-typed arguments.  Arity counts every
        // present argument; compatibility eliminates the overload only when a
        // typed argument is incompatible with a non-symbolic parameter (no
        // legal suffix can repair it) — an unknown argument type never vetoes.
        bool dead = false;
        std::size_t matched = 0;
        for (std::size_t ai = 0; ai < typed_args.size(); ++ai) {
            const std::string& arg = typed_args[ai];
            matched = ai + 1;  // the argument exists regardless of its type
            if (ai >= ov.param_types.size()) {
                // More arguments typed than this overload accepts.
                dead = true;
                cand.reason = EliminationReason::ArityExceeded;
                break;
            }
            if (arg.empty()) continue;  // unknown type — never vetoes
            const std::string& want = ov.param_types[ai];
            if (!HasUnboundTypeParam(want, ov.type_params) &&
                !compat(arg, want)) {
                dead = true;
                cand.reason = EliminationReason::ArgTypeMismatch;
                break;
            }
        }
        cand.next_param = matched < ov.param_types.size() ? matched
                                                          : ov.param_types.size();
        cand.accepts_more = !call_closed && matched < ov.param_types.size();
        if (!dead) {
            // Rule 4: ')' performs the final arity/default check.
            if (call_closed && matched < effective_required) {
                dead = true;
                cand.reason = EliminationReason::ArityShortAtClose;
            } else {
                cand.can_close_now = matched >= effective_required;
                cand.state = cand.can_close_now
                                 ? CandidateState::Alive
                                 : CandidateState::WaitingForMoreInput;
            }
        }
        if (dead) {
            cand.state = CandidateState::Dead;
        }
        // Rule 5: expected-return mismatch never eliminates; record it only
        // for reporting (the recovery-witness machinery answers the "can the
        // result still reach the expected type" question).
        if (cand.state != CandidateState::Dead && !expected_type.empty() &&
            !HasUnboundTypeParam(ov.result_type, ov.type_params) &&
            !compat(ov.result_type, expected_type)) {
            cand.reason = EliminationReason::ExpectedReturnOnly;
        }
        if (cand.state != CandidateState::Dead) {
            ++result.alive_count;
        }
        result.candidates.push_back(cand);

        std::ostringstream line;
        line << "#" << oi << " " << ov.name << "(";
        for (std::size_t pi = 0; pi < ov.param_types.size(); ++pi) {
            if (pi) line << ", ";
            line << ov.param_types[pi];
        }
        line << ")";
        if (!ov.result_type.empty()) {
            line << " -> " << ov.result_type;
        }
        switch (cand.state) {
            case CandidateState::Dead:
                line << " DEAD";
                break;
            case CandidateState::Alive:
                line << " alive";
                break;
            case CandidateState::WaitingForMoreInput:
                line << " waiting(next=" << cand.next_param << ")";
                break;
        }
        if (cand.reason != EliminationReason::None) {
            switch (cand.reason) {
                case EliminationReason::ArityExceeded:
                    line << " [reason=arity-exceeded]";
                    break;
                case EliminationReason::ArgTypeMismatch:
                    line << " [reason=arg-mismatch]";
                    break;
                case EliminationReason::ArityShortAtClose:
                    line << " [reason=arity-short-at-close]";
                    break;
                case EliminationReason::ExpectedReturnOnly:
                    line << " [reason=expected-return]";
                    break;
                case EliminationReason::None:
                    break;
            }
        }
        result.reasons.push_back(line.str());
    }
    return result;
}

}  // namespace cangjie
