// V15 Patch 1: Proof-Carrying Continuation — name helpers.
#include "continuation.h"

namespace cangjie {

// 续写状态枚举到字符串的名称映射
const char* ContinuationStateName(ContinuationState state) {
    switch (state) {
        case ContinuationState::Alive: return "alive";
        case ContinuationState::Dead: return "dead";
        case ContinuationState::Unknown: return "unknown";
    }
    return "unknown";
}

// 证明类型枚举到字符串的名称映射
const char* ProofKindName(ProofKind kind) {
    switch (kind) {
        case ProofKind::None: return "none";
        case ProofKind::ValidSuffix: return "valid_suffix";
        case ProofKind::OfficialAudit: return "official_audit";
        case ProofKind::ClosedWorldExhaustive: return "closed_world_exhaustive";
    }
    return "none";
}

}  // namespace cangjie
