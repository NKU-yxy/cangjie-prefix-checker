#pragma once

#include "call_frontier.h"
#include "continuation.h"

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
    TokenKind kind = TokenKind::Symbol; // token 类别。
    std::string text;                   // token 原始文本。
    bool complete = true;               // token 是否已确定边界。
};

struct PartialLexeme {
    std::string text;                       // 尚未稳定的词素文本。
    std::vector<TokenKind> candidates;      // 词素可能形成的 token 类别。
};

struct CheckStatus {
    bool ok = true;       // 当前前缀是否仍可接受。
    std::string message;  // 拒绝原因。
};

struct Checkpoint {
    std::size_t accepted_tokens = 0;
    std::size_t source_bytes = 0;
};

enum class SymbolKind {
    None,
    Local,
    Global,
    Function,
    Method,
    Field,
    StaticMember,
    Type,
    Primitive,
    Unknown,
};

enum class TailKind {
    None,
    Call,
    Member,
    Type,
    Value,
};

enum class BoundaryKind {
    None,
    Statement,
    AssignRhs,
    Return,
    Condition,
    LoopHead,
    CallArg,
    MemberSel,
    Decl,
};

enum class FrontierVerdict { None, Alive, Dead, Unknown };

enum class EdgeKind {
    Field,
    MethodValue,
    MethodCall,
    FunctionCall,
    Index,
};

struct SuffixStep {
    EdgeKind kind = EdgeKind::Field;
    std::string member;
    std::string result;
};

struct RecoveryWitness {
    bool found = false;
    std::string source;
    std::string target;
    std::vector<SuffixStep> steps;
    std::string printable_suffix;
};

struct WitnessStats {
    std::size_t queries = 0;
    std::size_t cache_hits = 0;
    std::size_t witness_found = 0;
};

struct FrontierInfo {
    std::string symbol;
    SymbolKind symbol_kind = SymbolKind::None;
    TailKind tail_kind = TailKind::None;
    BoundaryKind boundary_kind = BoundaryKind::None;
    std::string receiver;
    std::string receiver_type;
    std::string line;
    std::size_t frontier_start = 0;
    std::size_t frontier_end = 0;
    FrontierVerdict verdict = FrontierVerdict::None;
};

// 返回符号种类的稳定文本名称。
const char* SymbolKindName(SymbolKind kind);
// 返回尾部结构种类的稳定文本名称。
const char* TailKindName(TailKind kind);
// 返回语句边界种类的稳定文本名称。
const char* BoundaryKindName(BoundaryKind kind);
// 返回前沿判定结果的稳定文本名称。
const char* FrontierVerdictName(FrontierVerdict verdict);

class IncrementalLexer {
 public:
    struct Result {
        std::vector<TokenEvent> stable;
        PartialLexeme partial;
    };

    // 增量词法分析：输入新字节，返回已稳定的 token 序列与未完成词素
    Result Feed(std::string_view bytes);

 private:
    std::string pending_;
};

class IncrementalSemanticEngine {
 public:
    // 创建增量语义引擎并加载指定上下文表。
    explicit IncrementalSemanticEngine(std::string context_path = {});
    // 释放语义引擎持有的模型和缓存。
    ~IncrementalSemanticEngine();

    IncrementalSemanticEngine(const IncrementalSemanticEngine&) = delete;
    IncrementalSemanticEngine& operator=(const IncrementalSemanticEngine&) = delete;

    // 接受一个已稳定的 token（通常不报错，仅记录）
    CheckStatus Accept(const TokenEvent& event);
    // 对当前源码前缀做一次完整语义检查（含未完成词素的保守判断）
    CheckStatus Probe(const PartialLexeme& partial, std::string_view source);
    // 保存当前检查进度（已接受 token 数与源码字节数），供回滚使用
    Checkpoint Save() const;
    // 回滚到之前保存的检查进度
    void Rollback(const Checkpoint& checkpoint);

    // 把预加载模型输出为 Context IR JSON。
    void DumpContextIrJson(std::ostream& os) const;

    // 返回最近一次失败的前沿分类。
    const FrontierInfo& LastFrontier() const;

    // 返回最近一次失败的恢复见证。
    const RecoveryWitness& LastWitness() const;
    // 返回恢复见证查询统计。
    const WitnessStats& WitnessStatistics() const;

    // 返回最近一次调用的重载前沿。
    const CallFrontierResult& LastCallFrontier() const;

    // 返回最近一次续写证明。
    const ContinuationProof& LastProof() const;
    // 返回全部前缀决策账本记录。
    const std::vector<DecisionLedgerEntry>& DecisionLedger() const;

 private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

class NativeSemanticChecker {
 public:
    // 构造语义检查器并预加载上下文表
    explicit NativeSemanticChecker(std::string context_path = {});
    // 检查一段新输入的字节：先增量词法，再对整体前缀做语义检查
    CheckStatus Check(std::string_view bytes);
    // 把预加载模型输出为 Context IR JSON。
    void DumpContextIrJson(std::ostream& os) const { engine_.DumpContextIrJson(os); }
    // 返回最近一次失败的前沿分类。
    const FrontierInfo& LastFrontier() const { return engine_.LastFrontier(); }
    // 返回最近一次失败的恢复见证。
    const RecoveryWitness& LastWitness() const { return engine_.LastWitness(); }
    // 返回恢复见证查询统计。
    const WitnessStats& WitnessStatistics() const { return engine_.WitnessStatistics(); }
    // 返回最近一次调用的重载前沿。
    const CallFrontierResult& LastCallFrontier() const { return engine_.LastCallFrontier(); }
    // 返回最近一次续写证明。
    const ContinuationProof& LastProof() const { return engine_.LastProof(); }
    // 返回全部前缀决策账本记录。
    const std::vector<DecisionLedgerEntry>& DecisionLedger() const { return engine_.DecisionLedger(); }

 private:
    IncrementalLexer lexer_;
    IncrementalSemanticEngine engine_;
    std::string source_;          // 已接收的完整源码前缀。
    bool failed_ = false;         // 检查器是否已进入不可恢复失败状态。
    std::string failure_message_; // 首次失败原因。
};

}
