#include "native_semantic.h"

#include <utility>

namespace cangjie {

// 创建检查器并把上下文路径交给增量语义引擎。
NativeSemanticChecker::NativeSemanticChecker(std::string context_path)
    : engine_(std::move(context_path)) {}

// 接收新字节并依次执行增量词法、稳定 token 接受和完整前缀探测。
CheckStatus NativeSemanticChecker::Check(std::string_view bytes) {
    if (failed_) return {false, failure_message_};
    source_.append(bytes.data(), bytes.size());
    IncrementalLexer::Result result = lexer_.Feed(bytes);
    for (const TokenEvent& event : result.stable) {
        CheckStatus status = engine_.Accept(event);
        if (!status.ok) {
            failed_ = true;
            failure_message_ = status.message;
            return status;
        }
    }
    CheckStatus status = engine_.Probe(result.partial, source_);
    if (!status.ok) {
        failed_ = true;
        failure_message_ = status.message;
    }
    return status;
}

}
