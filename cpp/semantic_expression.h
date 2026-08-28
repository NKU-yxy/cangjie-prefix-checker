#pragma once

#include "semantic_context.h"
#include "semantic_model.h"

#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace cangjie {

// 保存表达式推断出的类型、错误和后缀可扩展状态。
struct ExprResult {
    std::string type = "?";
    bool known = false;
    bool error = false;
    std::string message;
    bool suffix_may_change_type = false;
};

// 根据模型和当前函数作用域推断表达式类型。
class ExpressionTyper {
 public:
    // 绑定本次推断使用的模型、函数作用域和完整源码。
    ExpressionTyper(
        const Model& model,
        const FunctionContext& context,
        std::string_view full_source
    );

    // 推断表达式类型，并可使用期望类型约束重载和 Lambda。
    ExprResult Infer(std::string expression, std::string expected = {});

 private:
    // 递归推断规范化表达式，深度参数用于限制异常嵌套。
    ExprResult InferImpl(std::string expression, const std::string& expected, int depth);
    // 推断普通函数、构造器或成员方法调用。
    ExprResult InferCall(
        std::string base,
        std::string name,
        std::vector<std::string> explicit_types,
        std::string arguments,
        bool closed,
        const std::string& expected,
        int depth
    );
    // 检查一组重载签名并汇总可行候选的返回类型。
    ExprResult CheckSignatures(
        const std::vector<FunctionSig>& signatures,
        const std::vector<std::string>& explicit_types,
        const std::vector<std::string>& arguments,
        bool closed,
        const std::string& expected,
        int depth,
        const std::unordered_map<std::string, std::string>& receiver_substitutions = {}
    );
    // 判断当前作用域是否存在指定前缀的可见符号。
    bool HasSymbolPrefix(std::string_view prefix) const;
    // 判断末尾标识符是否仍可能扩展为另一个符号。
    bool MayExtendTrailingIdentifier(std::string_view identifier) const;
    // 把成员访问拆成接收者和成员名称。
    std::optional<std::pair<std::string, std::string>> ParseMember(
        std::string_view expression
    ) const;

    const Model& model_;
    const FunctionContext& context_;
    std::string_view full_source_;
};

// 标记表达式结果仍可通过后缀改变类型。
ExprResult WithExtendablePostfix(ExprResult result);
// 收集没有显式类型标注的局部变量。
void CollectInferredLocalVariables(
    FunctionContext* context,
    const Model& model,
    std::string_view full_source
);
// 判断单个成员后缀能否把值恢复为目标类型。
bool MemberRecoversType(
    const Model& model,
    const std::string& type,
    const std::string& target,
    int depth = 0
);
// 判断单个运算符后缀能否得到目标类型。
bool OperatorRecoversType(
    const Model& model,
    const std::string& type,
    const std::string& target
);

}
