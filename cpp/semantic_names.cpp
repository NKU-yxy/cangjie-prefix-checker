#include "native_semantic.h"

namespace cangjie {

// 返回符号种类对应的稳定文本名称。
const char* SymbolKindName(SymbolKind kind) {
    switch (kind) {
        case SymbolKind::None: return "none";
        case SymbolKind::Local: return "local";
        case SymbolKind::Global: return "global";
        case SymbolKind::Function: return "function";
        case SymbolKind::Method: return "method";
        case SymbolKind::Field: return "field";
        case SymbolKind::StaticMember: return "static";
        case SymbolKind::Type: return "type";
        case SymbolKind::Primitive: return "primitive";
        case SymbolKind::Unknown: return "unknown";
    }
    return "none";
}

// 返回尾部结构种类对应的稳定文本名称。
const char* TailKindName(TailKind kind) {
    switch (kind) {
        case TailKind::None: return "none";
        case TailKind::Call: return "call";
        case TailKind::Member: return "member";
        case TailKind::Type: return "type";
        case TailKind::Value: return "value";
    }
    return "none";
}

// 返回语句边界种类对应的稳定文本名称。
const char* BoundaryKindName(BoundaryKind kind) {
    switch (kind) {
        case BoundaryKind::None: return "none";
        case BoundaryKind::Statement: return "statement";
        case BoundaryKind::AssignRhs: return "assign_rhs";
        case BoundaryKind::Return: return "return";
        case BoundaryKind::Condition: return "condition";
        case BoundaryKind::LoopHead: return "loop_head";
        case BoundaryKind::CallArg: return "call_arg";
        case BoundaryKind::MemberSel: return "member_sel";
        case BoundaryKind::Decl: return "decl";
    }
    return "none";
}

// 返回前沿判定结果对应的稳定文本名称。
const char* FrontierVerdictName(FrontierVerdict verdict) {
    switch (verdict) {
        case FrontierVerdict::None: return "none";
        case FrontierVerdict::Alive: return "Alive";
        case FrontierVerdict::Dead: return "Dead";
        case FrontierVerdict::Unknown: return "Unknown";
    }
    return "none";
}

}
