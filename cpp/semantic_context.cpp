#include "semantic_context.h"

#include "semantic_profile.h"
#include "semantic_text.h"
#include "semantic_types.h"

#include <algorithm>
#include <cctype>
#include <deque>
#include <iostream>
#include <regex>
#include <set>
#include <unordered_map>
#include <unordered_set>
#include <utility>

namespace cangjie {



// 把字符串/字符字面量与注释内容掩码为空白，只保留代码结构
std::string MaskQuotedAndComments(std::string_view line) {
    std::string out(line);
    const std::size_t n = out.size();
    bool in_string = false;
    bool in_line_comment = false;
    bool in_block_comment = false;
    for (std::size_t i = 0; i < n; ++i) {
        const char ch = out[i];
        if (in_line_comment) {
            out[i] = ' ';
            continue;
        }
        if (in_block_comment) {
            out[i] = ' ';
            if (ch == '*' && i + 1 < n && out[i + 1] == '/') {
                out[i + 1] = ' ';
                ++i;
                in_block_comment = false;
            }
            continue;
        }
        if (in_string) {
            out[i] = ' ';
            if (ch == '\\') {
                if (i + 1 < n) out[i + 1] = ' ';
                ++i;
            } else if (ch == '"') {
                in_string = false;
            }
            continue;
        }
        if (ch == '"') {
            in_string = true;
            out[i] = ' ';
        } else if (ch == '/' && i + 1 < n && out[i + 1] == '/') {
            in_line_comment = true;
            out[i] = out[i + 1] = ' ';
            ++i;
        } else if (ch == '/' && i + 1 < n && out[i + 1] == '*') {
            in_block_comment = true;
            out[i] = out[i + 1] = ' ';
            ++i;
        }
    }
    return out;
}

struct FrontierScan {
    std::size_t start = std::string_view::npos;
    std::size_t end = std::string_view::npos;
    std::size_t tail_start = std::string_view::npos;
};

// 跳过类型实参列表（"<...>"，含嵌套），返回列表结束位置
std::size_t SkipTypeArgumentList(std::string_view line, std::size_t open) {
    int depth = 0;
    for (std::size_t i = open; i < line.size(); ++i) {
        if (line[i] == '<') ++depth;
        else if (line[i] == '>') {
            if (--depth == 0) return i + 1;
        }
    }
    return std::string_view::npos;
}

// 查找当前语句中最后一个可作为失败前沿的标识符。
FrontierScan FindFrontierIdentifier(std::string_view line) {
    FrontierScan scan;
    std::size_t i = line.size();
    while (i > 0) {
        while (i > 0 && !IsIdentContinue(static_cast<unsigned char>(line[i - 1]))) --i;
        if (i == 0) break;
        const std::size_t end = i;
        while (i > 0 && IsIdentContinue(static_cast<unsigned char>(line[i - 1]))) --i;
        if (!IsIdentStart(static_cast<unsigned char>(line[i]))) continue;
        std::size_t name_end = end;
        std::size_t type_args_tail = std::string_view::npos;
        while (i > 0 && line[i - 1] == '<') {
            const std::size_t outer_end = i - 1;
            std::size_t j = outer_end;
            while (j > 0 && IsIdentContinue(static_cast<unsigned char>(line[j - 1]))) --j;
            if (j == outer_end || !IsIdentStart(static_cast<unsigned char>(line[j]))) break;
            type_args_tail = SkipTypeArgumentList(line, outer_end);
            if (type_args_tail == std::string_view::npos) break;
            i = j;
            name_end = outer_end;
        }
        scan = {i, name_end, type_args_tail == std::string_view::npos ? end : type_args_tail};
        break;
    }
    return scan;
}

// 根据标识符后的 token 分类调用、成员或普通值尾部。
TailKind ClassifyTail(std::string_view line, std::size_t tail_start) {
    std::size_t i = tail_start;
    while (i < line.size() && (line[i] == ' ' || line[i] == '\t')) ++i;
    if (i >= line.size()) return TailKind::Value;
    if (line[i] == '(') return TailKind::Call;
    if (line[i] == '.') return TailKind::Member;
    if (line[i] == '<') {
        const std::size_t after = SkipTypeArgumentList(line, i);
        if (after == std::string_view::npos) return TailKind::Value;
        i = after;
        while (i < line.size() && (line[i] == ' ' || line[i] == '\t')) ++i;
        if (i < line.size() && line[i] == '(') return TailKind::Call;
        if (i < line.size() && line[i] == '.') return TailKind::Member;
    }
    return TailKind::Value;
}

// 判断文本是否以完整单词结束。
bool EndsWithWord(std::string_view text, std::string_view word) {
    if (text.size() < word.size()) return false;
    const std::size_t cut = text.size() - word.size();
    if (text.substr(cut) != word) return false;
    return cut == 0 || !IsIdentContinue(static_cast<unsigned char>(text[cut - 1]));
}

// 根据前沿位置判断所属语句边界类型。
BoundaryKind ClassifyBoundary(
    std::string_view prefix,
    bool member_selection,
    bool type_position
) {
    if (member_selection) return BoundaryKind::MemberSel;
    if (type_position) return BoundaryKind::Decl;
    std::size_t end = prefix.size();
    while (end > 0 && (prefix[end - 1] == ' ' || prefix[end - 1] == '\t')) --end;
    if (end > 0 && prefix[end - 1] == '=') return BoundaryKind::AssignRhs;
    if (EndsWithWord(prefix.substr(0, end), "return")) return BoundaryKind::Return;
    if (EndsWithWord(prefix.substr(0, end), "if")) return BoundaryKind::Condition;
    if (EndsWithWord(prefix.substr(0, end), "while")) return BoundaryKind::Condition;
    if (EndsWithWord(prefix.substr(0, end), "for")) return BoundaryKind::LoopHead;
    int depth = 0;
    std::size_t last_open = std::string_view::npos;
    for (std::size_t i = 0; i < end; ++i) {
        if (prefix[i] == '(') {
            ++depth;
            last_open = i;
        } else if (prefix[i] == ')' && depth > 0) {
            --depth;
        }
    }
    if (depth > 0) {
        const std::string_view head = prefix.substr(0, last_open);
        std::size_t head_end = head.size();
        while (head_end > 0 && (head[head_end - 1] == ' ' || head[head_end - 1] == '\t')) --head_end;
        if (EndsWithWord(head.substr(0, head_end), "if") ||
            EndsWithWord(head.substr(0, head_end), "while")) {
            return BoundaryKind::Condition;
        }
        if (EndsWithWord(head.substr(0, head_end), "for")) return BoundaryKind::LoopHead;
        return BoundaryKind::CallArg;
    }
    return BoundaryKind::Statement;
}

// 判断名称是否为内建原始类型。
bool IsPrimitiveTypeName(std::string_view name) {
    static const std::unordered_set<std::string> primitives = {
        "Int8", "Int16", "Int32", "Int64",
        "UInt8", "UInt16", "UInt32", "UInt64",
        "Float32", "Float64", "Bool", "Rune", "Unit",
    };
    return primitives.count(std::string(name)) != 0;
}

// 解析无接收者标识符对应的符号种类。
SymbolKind ResolveBareSymbol(
    std::string_view name,
    const Model& model,
    const FunctionContext& context
) {
    if (context.variables.count(std::string(name)) != 0) return SymbolKind::Local;
    if (model.functions.count(std::string(name)) != 0) return SymbolKind::Function;
    if (model.globals.count(std::string(name)) != 0) return SymbolKind::Global;
    if (model.nominals.count(std::string(name)) != 0) return SymbolKind::Type;
    if (IsPrimitiveTypeName(name)) return SymbolKind::Primitive;
    return SymbolKind::Unknown;
}

// 解析成员访问对应的字段或方法种类。
SymbolKind ResolveMemberKind(
    std::string_view receiver_text,
    std::string_view member,
    const Model& model,
    const FunctionContext& context,
    std::string* receiver_head,
    std::string* receiver_full = nullptr
) {
    const std::string recv(Trim(receiver_text));
    std::string recv_type;
    const auto local = context.variables.find(recv);
    if (local != context.variables.end()) {
        recv_type = local->second;
    } else if (model.globals.count(recv) != 0) {
        recv_type = model.globals.at(recv);
    } else if (model.nominals.count(recv) != 0) {
        *receiver_head = recv;
        if (receiver_full) *receiver_full = recv;
        const auto& info = model.nominals.at(recv);
        const std::string key(member);
        if (info.fields.count(key) || info.methods.count(key)) {
            return SymbolKind::StaticMember;
        }
        if (info.static_fields.count(key) || info.static_methods.count(key)) {
            return SymbolKind::StaticMember;
        }
        return SymbolKind::Unknown;
    } else {
        *receiver_head = recv;
        if (receiver_full) *receiver_full = recv;
        return SymbolKind::Unknown;
    }
    *receiver_head = TypeHead(recv_type);
    if (receiver_full) *receiver_full = recv_type;
    const auto info_it = model.nominals.find(*receiver_head);
    if (info_it == model.nominals.end()) return SymbolKind::Unknown;
    const NominalInfo& info = info_it->second;
    const std::string key(member);
    if (info.fields.count(key) != 0) return SymbolKind::Field;
    if (info.methods.count(key) != 0) return SymbolKind::Method;
    if (info.static_fields.count(key) != 0 || info.static_methods.count(key) != 0) {
        return SymbolKind::StaticMember;
    }
    return SymbolKind::Unknown;
}

// 判断成员名称是否存在合法的完整或前缀匹配。
FrontierVerdict MemberVerdict(
    SymbolKind kind,
    TailKind tail,
    const Model& model,
    const std::string& receiver_head,
    const std::string& member
) {
    if (kind == SymbolKind::Unknown || kind == SymbolKind::StaticMember) {
        return FrontierVerdict::Unknown;
    }
    if (tail == TailKind::Call) {
        return kind == SymbolKind::Field ? FrontierVerdict::Dead : FrontierVerdict::Alive;
    }
    if (kind == SymbolKind::Field) return FrontierVerdict::Alive;
    const auto info = model.nominals.find(receiver_head);
    if (info == model.nominals.end()) return FrontierVerdict::Unknown;
    const auto methods = info->second.methods.find(member);
    if (methods == info->second.methods.end()) return FrontierVerdict::Unknown;
    for (const FunctionSig& sig : methods->second) {
        if (sig.param_types.empty()) return FrontierVerdict::Alive;
    }
    return FrontierVerdict::Dead;
}

// 分类失败点（frontier）：定位语句末尾的标识符，判断其符号种类、尾部与边界
FrontierInfo ClassifyFrontier(
    std::string_view source,
    const Model& model,
    const FunctionContext& context
) {
    FrontierInfo info;
    std::size_t line_start = source.rfind('\n');
    if (line_start != std::string_view::npos) ++line_start;
    for (;;) {
        if (line_start == std::string_view::npos) return info;
        const std::string trimmed = Trim(MaskQuotedAndComments(source.substr(line_start)));
        if (!trimmed.empty() && trimmed != "}" && trimmed != "{") break;
        if (line_start == 0) return info;
        const std::size_t prev = source.rfind('\n', line_start - 2);
        line_start = prev == std::string_view::npos ? 0 : prev + 1;
    }
    const std::string masked = MaskQuotedAndComments(source.substr(line_start));
    const std::string trimmed = Trim(masked);
    if (trimmed.empty()) return info;
    info.line = std::string(source.substr(line_start));
    const FrontierScan scan = FindFrontierIdentifier(trimmed);
    if (scan.start == std::string_view::npos) return info;

    const std::size_t lead = masked.find_first_not_of(" \t\r\n");
    info.frontier_start = line_start + lead + scan.start;
    info.frontier_end = line_start + lead + scan.end;

    info.symbol = std::string(trimmed.substr(scan.start, scan.end - scan.start));
    const std::string_view prefix = std::string_view(trimmed).substr(0, scan.start);
    const bool member_selection =
        !prefix.empty() && prefix.back() == '.';
    const bool type_position =
        !prefix.empty() &&
        (prefix.back() == ':' || prefix.back() == ',' || prefix.back() == '<');
    info.tail_kind = ClassifyTail(trimmed, scan.tail_start);
    if (type_position && info.tail_kind == TailKind::Value) {
        info.tail_kind = TailKind::Type;
    }
    info.boundary_kind = ClassifyBoundary(prefix, member_selection, type_position);

    if (member_selection) {
        std::size_t recv_end = prefix.size() - 1;
        while (recv_end > 0 && !IsIdentContinue(static_cast<unsigned char>(prefix[recv_end - 1]))) --recv_end;
        std::size_t recv_start = recv_end;
        while (recv_start > 0 && IsIdentContinue(static_cast<unsigned char>(prefix[recv_start - 1]))) --recv_start;
        const std::string_view receiver_text = prefix.substr(recv_start, recv_end - recv_start);
        info.symbol_kind = ResolveMemberKind(
            receiver_text, info.symbol, model, context, &info.receiver, &info.receiver_type
        );
        info.verdict = MemberVerdict(info.symbol_kind, info.tail_kind, model, info.receiver, info.symbol);
        return info;
    }

    const std::string base = info.symbol;
    info.symbol_kind = ResolveBareSymbol(base, model, context);
    if (info.tail_kind == TailKind::Call) {
        info.verdict =
            info.symbol_kind == SymbolKind::Unknown || info.symbol_kind == SymbolKind::Primitive
                ? FrontierVerdict::Unknown : FrontierVerdict::Alive;
        return info;
    }
    if (info.tail_kind == TailKind::Type) {
        info.verdict = FrontierVerdict::Unknown;
        return info;
    }
    info.verdict =
        info.symbol_kind == SymbolKind::Local || info.symbol_kind == SymbolKind::Global ||
        info.symbol_kind == SymbolKind::Function
            ? FrontierVerdict::Alive : FrontierVerdict::Unknown;
    return info;
}


// 从声明快照记录定位当前所在函数（含参数变量与返回类型）
FunctionContext CurrentFunctionContextFromRecords(
    std::string_view source,
    const std::vector<DeclarationRecord>& single_line_records,
    const std::vector<DeclarationRecord>& multiline_only_records,
    const std::vector<DeclarationRecord>& broad_class_records
) {
    const std::string owned(source);
    FunctionContext best;
    std::size_t best_open = std::string::npos;
    std::optional<std::size_t> best_close;
    auto inspect = [&](const std::vector<DeclarationRecord>& records) {
        for (const DeclarationRecord& record : records) {
            const std::size_t open = record.open;
            if (best_open != std::string::npos && open < best_open) continue;
            best_open = open;
            best_close = record.close;
            best.in_function = true;
            best.is_main = StartsWith(Trim(SnapshotCaptureAt(record, 0).text), "main");
            const SnapshotCapture& result_capture = SnapshotCaptureAt(record, 2);
            best.result = CompactType(result_capture.matched ? result_capture.text : "Unit");
            best.variables.clear();
            best.immutable.clear();
            const FunctionSig params = ParseFunctionSignature(
                "", {}, SnapshotCaptureAt(record, 1).text, best.result
            );
            for (std::size_t index = 0; index < params.param_names.size(); ++index) {
                best.variables[params.param_names[index]] = params.param_types[index];
                best.immutable.insert(params.param_names[index]);
            }
        }
    };
    inspect(single_line_records);
    inspect(multiline_only_records);
    best.entry_variables = best.variables;
    best.entry_immutable = best.immutable;
    if (best_open == std::string::npos) {
        best.body = owned;
        return best;
    }
    best.body_start = best_open + 1;
    best.body_end = best_close.value_or(std::string::npos);
    best.body = best_close
        ? owned.substr(best_open + 1, *best_close - best_open - 1)
        : owned.substr(best_open + 1);

    for (const DeclarationRecord& record : broad_class_records) {
        if (record.open < best_open && (!record.close || *record.close > best_open)) {
            best.class_name = SnapshotCaptureAt(record, 1).text;
        }
    }
    return best;
}

// 获取当前源码位置所在的函数上下文（入口，基于声明快照）
FunctionContext CurrentFunctionContext(
    std::string_view source,
    const DeclarationSnapshot& snapshot
) {
    return CurrentFunctionContextFromRecords(
        source,
        snapshot.current_functions_single_line,
        snapshot.current_functions_multiline_only,
        snapshot.broad_classes
    );
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 使用正则旧实现定位当前函数上下文。
FunctionContext CurrentFunctionContextRegex(std::string_view source) {
    static const std::regex single_line_pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()\n]*>)?|\bmain|\binit)\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{)"
    );
    static const std::regex multiline_pattern(
        R"((?:\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>{}()]*>)?|\bmain|\binit)\s*\(([^{};]*?)\)\s*(?::\s*([^{}]+?))?\s*\{)"
    );
    const std::string owned(source);
    const std::string code_mask = MaskNonCodeText(source);
    FunctionContext best;
    std::size_t best_open = std::string::npos;
    std::optional<std::size_t> best_close;
    auto inspect = [&](const std::regex& pattern, bool multiline_only) {
        for (std::sregex_iterator it(owned.begin(), owned.end(), pattern), end;
             it != end; ++it) {
            if (multiline_only && (*it)[0].str().find_first_of("\n\r") == std::string::npos) {
                continue;
            }
            const std::size_t match_offset = static_cast<std::size_t>((*it).position());
            if (StartsWith(std::string_view(owned).substr(match_offset), "init") &&
                (match_offset >= code_mask.size() ||
                 !IsIdentStart(static_cast<unsigned char>(code_mask[match_offset])))) {
                continue;
            }
            const std::size_t open = static_cast<std::size_t>(
                match_offset + (*it).length() - 1
            );
            if (best_open != std::string::npos && open < best_open) continue;
            best_open = open;
            best_close = MatchingDelimiter(owned, open, '{', '}');
            best.in_function = true;
            best.is_main = StartsWith(Trim((*it)[0].str()), "main");
            best.result = CompactType((*it)[2].matched ? (*it)[2].str() : "Unit");
            best.variables.clear();
            best.immutable.clear();
            const FunctionSig params = ParseFunctionSignature(
                "", {}, (*it)[1].str(), best.result
            );
            for (std::size_t index = 0; index < params.param_names.size(); ++index) {
                best.variables[params.param_names[index]] = params.param_types[index];
                best.immutable.insert(params.param_names[index]);
            }
        }
    };
    inspect(single_line_pattern, false);
    if (HasMultilineFunctionHeader(source)) inspect(multiline_pattern, true);
    best.entry_variables = best.variables;
    best.entry_immutable = best.immutable;
    if (best_open == std::string::npos) {
        best.body = owned;
        return best;
    }
    best.body_start = best_open + 1;
    best.body_end = best_close.value_or(std::string::npos);
    best.body = best_close
        ? owned.substr(best_open + 1, *best_close - best_open - 1)
        : owned.substr(best_open + 1);

    static const std::regex nominal_pattern(
        R"(\bclass\s+([A-Za-z_][A-Za-z0-9_]*)[^{}]*\{)"
    );
    for (std::sregex_iterator it(owned.begin(), owned.end(), nominal_pattern), end;
         it != end; ++it) {
        const std::size_t open = static_cast<std::size_t>(
            (*it).position() + (*it).length() - 1
        );
        const auto close = MatchingDelimiter(owned, open, '{', '}');
        if (open < best_open && (!close || *close > best_open)) {
            best.class_name = (*it)[1].str();
        }
    }
    return best;
}
#endif

// 从函数体内收集 var/let 局部变量及其类型
void CollectLocalVariables(FunctionContext* context) {
    static const std::regex declaration_pattern(
        R"(\b(let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^=;{}\n]+)\s*=)"
    );
    for (std::sregex_iterator it(context->body.begin(), context->body.end(), declaration_pattern), end;
         it != end; ++it) {
        context->variables[(*it)[2].str()] = CompactType((*it)[3].str());
        if ((*it)[1].str() == "let") context->immutable.insert((*it)[2].str());
    }
}

// 收集当前仍处于打开状态的 lambda 的形参变量（含类型推断结果）
void CollectActiveLambdaVariables(FunctionContext* context) {
    struct BraceFrame {
        std::size_t open = 0;
        bool lambda = false;
        std::string parameters;
    };
    std::vector<BraceFrame> stack;
    bool in_string = false;
    bool escaped = false;
    bool line_comment = false;
    int block_comment_depth = 0;
    for (std::size_t index = 0; index < context->body.size(); ++index) {
        const char ch = context->body[index];
        const char next = index + 1 < context->body.size() ? context->body[index + 1] : '\0';
        if (line_comment) {
            if (ch == '\n' || ch == '\r') line_comment = false;
            continue;
        }
        if (block_comment_depth > 0) {
            if (ch == '/' && next == '*') {
                ++block_comment_depth;
                ++index;
            } else if (ch == '*' && next == '/') {
                --block_comment_depth;
                ++index;
            }
            continue;
        }
        if (in_string) {
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '/' && next == '/') {
            line_comment = true;
            ++index;
        } else if (ch == '/' && next == '*') {
            block_comment_depth = 1;
            ++index;
        } else if (ch == '"') {
            in_string = true;
        } else if (ch == '{') {
            stack.push_back({index, false, {}});
        } else if (ch == '=' && next == '>' && !stack.empty()) {
            BraceFrame& frame = stack.back();
            frame.lambda = true;
            frame.parameters = Trim(std::string_view(context->body).substr(
                frame.open + 1, index - frame.open - 1
            ));
            ++index;
        } else if (ch == '}' && !stack.empty()) {
            stack.pop_back();
        }
    }
    for (const BraceFrame& frame : stack) {
        if (!frame.lambda) continue;
        for (const std::string& raw_parameter : SplitTopLevel(frame.parameters, ',')) {
            const std::size_t colon = FindTopLevel(raw_parameter, ":");
            std::string name = Trim(std::string_view(raw_parameter).substr(0, colon));
            if (!IsIdentifierText(name)) continue;
            const std::string type = colon == std::string::npos
                ? "?" : CompactType(std::string_view(raw_parameter).substr(colon + 1));
            context->variables[name] = type.empty() ? "?" : type;
            context->immutable.insert(name);
            context->entry_variables[name] = type.empty() ? "?" : type;
            context->entry_immutable.insert(name);
        }
    }
}

// 递归判断名义类型是否为目标类型的子类型。
bool NominalSubtype(
    std::string_view got,
    std::string_view want,
    const Model& model,
    std::unordered_set<std::string>* visited
) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->nominal_subtype_ns : nullptr);
    if (g_profile) {
        ++g_profile->nominal_subtype_calls;
        if (g_profile->nominal_subtype_keys.emplace(ProfilePairKey(got, want)).second) {
            ++g_profile->nominal_subtype_generation_unique;
        }
    }
#endif
    const std::string got_head = TypeHead(got);
    const std::string want_head = TypeHead(want);
    if (got_head == want_head) return CompactType(got) == CompactType(want);
    if (!visited->insert(got_head).second) return false;
    const auto nominal = model.nominals.find(got_head);
    if (nominal == model.nominals.end()) return false;
    std::unordered_map<std::string, std::string> substitutions;
    const auto got_args = TypeArgs(got);
    for (std::size_t index = 0;
         index < nominal->second.type_params.size() && index < got_args.size(); ++index) {
        substitutions[nominal->second.type_params[index]] = got_args[index];
    }
    for (const std::string& raw_super : nominal->second.supers) {
        const std::string super = ApplySubstitution(raw_super, substitutions);
        if (CompactType(super) == CompactType(want) || NominalSubtype(super, want, model, visited)) {
            return true;
        }
    }
    return false;
}

// 判断 got 类型是否与期望的 want 类型兼容（含数值族转换与泛型/继承关系）
bool Compatible(std::string_view got, std::string_view want, const Model& model) {
#ifdef CANGJIE_ENABLE_PROFILE
    ProfileScopeTimer profile_timer(g_profile ? &g_profile->compatible_ns : nullptr);
    if (g_profile) {
        ++g_profile->compatible_calls;
        if (g_profile->compatible_keys.emplace(ProfilePairKey(got, want)).second) {
            ++g_profile->compatible_generation_unique;
        }
    }
#endif
    const std::string left = CompactType(got);
    const std::string right = CompactType(want);
    if (left.empty() || left == "?" || right.empty() || right == "?") return true;
    if (left == right) return true;
    if (IsFunctionType(left) && IsFunctionType(right)) {
        const auto got_function = FunctionTypeParts(left);
        const auto want_function = FunctionTypeParts(right);
        if (got_function.first.size() != want_function.first.size()) return false;
        for (std::size_t index = 0; index < got_function.first.size(); ++index) {
            if (!Compatible(want_function.first[index], got_function.first[index], model)) {
                return false;
            }
        }
        return Compatible(got_function.second, want_function.second, model);
    }
    if (TypeHead(left) == TypeHead(right) && TypeArgs(right).empty()) return true;
    std::unordered_set<std::string> visited;
    return NominalSubtype(left, right, model, &visited);
}

// 判断一个类型是否为模型已知的类型（原始类型、命名类型或泛型实例）
bool KnownType(std::string_view type, const Model& model) {
    const std::string normalized = CompactType(type);
    static const std::unordered_set<std::string> primitives = {
        "Int64", "Float64", "Bool", "Rune", "Unit"
    };
    if (primitives.count(normalized)) return true;
    if (IsFunctionType(normalized)) return true;
    return model.nominals.count(TypeHead(normalized)) != 0;
}



// 按名义类型实参替换成员签名中的类型参数。
std::string SubstituteTypeArgs(
    std::string_view type,
    const std::vector<std::string>& params,
    const std::vector<std::string>& args
) {
    if (params.empty()) return std::string(type);
    std::string out;
    out.reserve(type.size() + 16);
    std::size_t index = 0;
    while (index < type.size()) {
        const char ch = type[index];
        if (ch != '_' && !std::isalpha(static_cast<unsigned char>(ch))) {
            out.push_back(ch);
            ++index;
            continue;
        }
        std::size_t end = index;
        while (end < type.size() && (type[end] == '_' ||
               std::isalnum(static_cast<unsigned char>(type[end])))) ++end;
        const std::string_view word = type.substr(index, end - index);
        bool replaced = false;
        for (std::size_t p = 0; p < params.size() && p < args.size(); ++p) {
            if (word == params[p]) {
                out += args[p];
                replaced = true;
                break;
            }
        }
        if (!replaced) out.append(word.data(), word.size());
        index = end;
    }
    return out;
}

// 把函数签名转换为统一的函数类型文本。
std::string PostfixGraph::FunctionTypeOf(const FunctionSig& sig) {
    std::string output = "(";
    for (std::size_t index = 0; index < sig.param_types.size(); ++index) {
        if (index) output += ",";
        output += sig.param_types[index];
    }
    output += ")->" + sig.result;
    return output;
}

// 从完整模型预计算所有可用后缀边。
PostfixGraph PostfixGraph::Build(const Model& model) {
    PostfixGraph graph;
    for (const auto& entry : model.nominals) {
        const NominalInfo& info = entry.second;
        NominalNode& node = graph.nodes[info.name];
        node.type_params = info.type_params;
        for (const auto& field : info.fields) node.fields[field.first] = field.second;
        for (const auto& member : info.methods) {
            for (const FunctionSig& sig : member.second) {
                node.calls[member.first].push_back({sig.param_types, sig.result});
                if (sig.param_types.empty()) {
                    node.method_values[member.first] = FunctionTypeOf(sig);
                    if (member.first == "first" || member.first == "last") {
                        node.fields[member.first] = sig.result;
                    }
                }
            }
        }
    }
    // 原始类型不在上下文名义类型表中，这里补充固定的 toString 边。
    static const char* kToStringPrimitives[] = {"Int64", "Float64", "Bool"};
    for (const char* primitive : kToStringPrimitives) {
        NominalNode& node = graph.nodes[primitive];
        node.calls["toString"].push_back({{}, "String"});
        node.method_values["toString"] = "()->String";
    }
    return graph;
}

// 为指定类型构造一个可用的最小实参文本。
std::string ConstructibleArg(
    std::string_view type,
    const FunctionContext& context,
    const Model& model
) {
    const std::string normalized = CompactType(type);
    if (normalized == "Bool") return "true";
    if (normalized == "Int64") return "0";
    if (normalized == "Float64") return "0.0";
    if (normalized == "String") return "\"\"";
    if (normalized == "Unit") return "";
    if (IsFunctionType(normalized)) return "";
    const std::string head = TypeHead(normalized);
    if (head == "Array") return "[]";
    if (head == "Rune") return "";
    const auto nominal = model.nominals.find(head);
    if (nominal != model.nominals.end()) {
        for (const FunctionSig& ctor : nominal->second.constructors) {
            if (ctor.param_types.empty()) {
                return normalized + "()";
            }
        }
    }
    for (const auto& local : context.variables) {
        if (Compatible(local.second, normalized, model)) return local.first;
    }
    return "";
}

// 从失败语句推断前沿表达式的期望类型。
std::string ExpectedFromLine(
    std::string_view line,
    const FunctionContext& context,
    const Model& model
) {
    const std::string trimmed = Trim(line);
    {
        int depth = 0;
        std::size_t open = std::string_view::npos;
        for (std::size_t i = line.size(); i-- > 0;) {
            const char ch = line[i];
            if (ch == ')') {
                ++depth;
            } else if (ch == '(') {
                if (depth == 0) {
                    open = i;
                    break;
                }
                --depth;
            }
        }
        if (open != std::string_view::npos) {
            std::size_t callee_end = open;
            while (callee_end > 0 && !IsIdentContinue(
                       static_cast<unsigned char>(line[callee_end - 1]))) --callee_end;
            std::size_t callee_start = callee_end;
            while (callee_start > 0 && IsIdentContinue(
                       static_cast<unsigned char>(line[callee_start - 1]))) --callee_start;
            std::size_t arg_index = 0;
            for (std::size_t i = open + 1; i < line.size(); ++i) {
                if (line[i] == ',') ++arg_index;
            }
            const std::string callee(
                line.substr(callee_start, callee_end - callee_start)
            );
            if (callee == "if" || callee == "while") return "Bool";
            const std::size_t dot = callee.rfind('.');
            if (dot != std::string_view::npos) {
                const std::string recv = Trim(line.substr(0, callee_start + dot));
                std::string head;
                std::string full;
                if (ResolveMemberKind(recv, callee.substr(dot + 1), model, context,
                                      &head, &full) == SymbolKind::Method) {
                    const auto nominal = model.nominals.find(head);
                    if (nominal != model.nominals.end()) {
                        const auto methods = nominal->second.methods.find(callee.substr(dot + 1));
                        if (methods != nominal->second.methods.end()) {
                            for (const FunctionSig& sig : methods->second) {
                                if (arg_index < sig.param_types.size()) {
                                    return SubstituteTypeArgs(
                                        sig.param_types[arg_index],
                                        nominal->second.type_params,
                                        TypeArgs(full)
                                    );
                                }
                            }
                        }
                    }
                }
            } else {
                const auto functions = model.functions.find(callee);
                if (functions != model.functions.end()) {
                    for (const FunctionSig& sig : functions->second) {
                        if (arg_index < sig.param_types.size()) {
                            return sig.param_types[arg_index];
                        }
                    }
                }
            }
        }
        if (!trimmed.empty() && trimmed[trimmed.size() - 1] == ')') {
            int depth = 0;
            for (std::size_t i = trimmed.size(); i-- > 0;) {
                const char ch = trimmed[i];
                if (ch == ')') {
                    ++depth;
                } else if (ch == '(') {
                    if (--depth == 0) {
                        std::size_t ce = i;
                        while (ce > 0 && !IsIdentContinue(
                                   static_cast<unsigned char>(trimmed[ce - 1]))) --ce;
                        std::size_t cs = ce;
                        while (cs > 0 && IsIdentContinue(
                                   static_cast<unsigned char>(trimmed[cs - 1]))) --cs;
                        const std::string group(trimmed.substr(cs, ce - cs));
                        if (group == "if" || group == "while") return "Bool";
                        break;
                    }
                }
            }
        }
    }
    static const std::regex decl_pattern(
        R"(\b(let|var)\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*([^=\n;]+?)\s*=)"
    );
    {
        std::string owned(line);
        std::smatch match;
        if (std::regex_search(owned, match, decl_pattern)) {
            return CompactType(match[2].str());
        }
    }
    if (StartsWith(trimmed, "return") &&
        (trimmed.size() == 6 || std::isspace(static_cast<unsigned char>(trimmed[6])))) {
        return context.result.empty() ? "" : context.result;
    }
    if (StartsWith(trimmed, "if (") || StartsWith(trimmed, "while (")) {
        return "Bool";
    }
    return "";
}

// 提取尚未闭合调用中已经输入的参数文本。
std::vector<std::string> OpenCallTypedArgs(
    std::string_view line, std::size_t callee_end
) {
    std::vector<std::string> out;
    std::size_t open = std::string_view::npos;
    int depth = 0;
    for (std::size_t i = callee_end; i < line.size(); ++i) {
        if (line[i] == '(') {
            if (depth == 0 && open == std::string_view::npos) open = i;
            ++depth;
        } else if (line[i] == ')' && depth > 0) {
            --depth;
        }
    }
    if (open == std::string_view::npos) return out;
    std::size_t scan_end = line.size();
    depth = 0;
    for (std::size_t i = open + 1; i < line.size(); ++i) {
        if (line[i] == '(' || line[i] == '[') {
            ++depth;
        } else if (line[i] == ')' || line[i] == ']') {
            if (depth > 0) {
                --depth;
            } else if (line[i] == ')') {
                scan_end = i;
                break;
            }
        }
    }
    std::size_t piece_start = open + 1;
    depth = 0;
    for (std::size_t i = open + 1; i < scan_end; ++i) {
        if (line[i] == '(' || line[i] == '[') {
            ++depth;
        } else if (line[i] == ')' || line[i] == ']') {
            if (depth > 0) --depth;
        } else if (line[i] == ',' && depth == 0) {
            out.push_back(Trim(line.substr(piece_start, i - piece_start)));
            piece_start = i + 1;
        }
    }
    const std::string last = Trim(line.substr(piece_start, scan_end - piece_start));
    if (!last.empty()) out.push_back(last);
    return out;
}

// 统计开放调用中已经开始的参数数量。
int OpenCallArgCount(std::string_view line, std::size_t callee_end) {
    return static_cast<int>(OpenCallTypedArgs(line, callee_end).size());
}

// 判断调用左括号是否仍未闭合。
bool CallStillOpen(std::string_view line, std::size_t callee_end) {
    int depth = 0;
    for (std::size_t i = callee_end; i < line.size(); ++i) {
        if (line[i] == '(') {
            ++depth;
        } else if (line[i] == ')' && depth > 0) {
            --depth;
        }
    }
    return depth > 0;
}

// 推断前沿符号在当前上下文中的类型。
std::string FrontierTypeFor(
    const FrontierInfo& frontier,
    const FunctionContext& context,
    const Model& model
) {
    switch (frontier.symbol_kind) {
        case SymbolKind::Local:
        case SymbolKind::Global: {
            const auto local = context.variables.find(frontier.symbol);
            if (local != context.variables.end()) return local->second;
            const auto global = model.globals.find(frontier.symbol);
            if (global != model.globals.end()) return global->second;
            return "";
        }
        case SymbolKind::Method:
        case SymbolKind::Field: {
            const auto nominal = model.nominals.find(frontier.receiver);
            if (nominal == model.nominals.end()) return "";
            const std::vector<std::string> receiver_args = TypeArgs(frontier.receiver_type);
            if (frontier.symbol_kind == SymbolKind::Field) {
                const auto field = nominal->second.fields.find(frontier.symbol);
                if (field != nominal->second.fields.end()) {
                    return SubstituteTypeArgs(
                        field->second, nominal->second.type_params, receiver_args
                    );
                }
                return "";
            }
            const auto methods = nominal->second.methods.find(frontier.symbol);
            if (methods == nominal->second.methods.end()) return "";
            if (frontier.tail_kind == TailKind::Call) {
                if (frontier.line.find(frontier.symbol) == std::string::npos) return "";
                const std::size_t symbol_end =
                    frontier.line.find(frontier.symbol) + frontier.symbol.size();
                const int args = OpenCallArgCount(frontier.line, symbol_end);
                if (args >= 0) {
                    for (const FunctionSig& sig : methods->second) {
                        if (static_cast<std::size_t>(args) == sig.param_types.size()) {
                            return SubstituteTypeArgs(
                                sig.result, nominal->second.type_params, receiver_args
                            );
                        }
                    }
                }
                return SubstituteTypeArgs(
                    methods->second.front().result, nominal->second.type_params, receiver_args
                );
            }
            const FunctionSig& front = methods->second.front();
            std::vector<std::string> params(front.param_types);
            for (std::string& param : params) {
                param = SubstituteTypeArgs(param, nominal->second.type_params, receiver_args);
            }
            FunctionSig substituted = front;
            substituted.param_types = std::move(params);
            substituted.result = SubstituteTypeArgs(
                front.result, nominal->second.type_params, receiver_args
            );
            return PostfixGraph::FunctionTypeOf(substituted);
        }
        case SymbolKind::Function: {
            const auto functions = model.functions.find(frontier.symbol);
            if (functions == model.functions.end()) return "";
            if (frontier.tail_kind == TailKind::Call) {
                if (frontier.line.find(frontier.symbol) == std::string::npos) return "";
                const std::size_t symbol_end =
                    frontier.line.find(frontier.symbol) + frontier.symbol.size();
                const int args = OpenCallArgCount(frontier.line, symbol_end);
                if (args >= 0) {
                    for (const FunctionSig& sig : functions->second) {
                        if (static_cast<std::size_t>(args) == sig.param_types.size()) {
                            return sig.result;
                        }
                    }
                }
                return functions->second.front().result;
            }
            return PostfixGraph::FunctionTypeOf(functions->second.front());
        }
        default:
            return "";
    }
}

// 对调用参数文本执行轻量类型推断。
std::string ArgTextType(
    std::string_view text,
    const Model& model,
    const FunctionContext& context
) {
    const std::string owned(Trim(text));
    if (owned.empty()) return "";
    if (owned == "true" || owned == "false") return "Bool";
    if (owned.front() == '"') return "String";
    if (owned.front() == '[' || owned.front() == '{') return "";
    bool numeric = true;
    bool integral = true;
    for (std::size_t index = 0; index < owned.size(); ++index) {
        const char ch = owned[index];
        if (index == 0 && (ch == '-' || ch == '+')) continue;
        if (ch >= '0' && ch <= '9') continue;
        if (ch == '.' && integral) {
            integral = false;
            continue;
        }
        numeric = false;
        break;
    }
    if (numeric) return integral ? "Int64" : "Float64";
    const auto local = context.variables.find(owned);
    if (local != context.variables.end()) return local->second;
    const auto global = model.globals.find(owned);
    if (global != model.globals.end()) return global->second;
    const auto function = model.functions.find(owned);
    if (function != model.functions.end()) {
        return PostfixGraph::FunctionTypeOf(function->second.front());
    }
    return "";
}

// 为尚未闭合的函数调用构造可行后缀见证。
bool OpenCallWitness(
    const FrontierInfo& frontier,
    const Model& model,
    const FunctionContext& context,
    RecoveryWitness* witness
) {
    const std::size_t symbol_end = frontier.line.find(frontier.symbol);
    if (symbol_end == std::string::npos) return false;
    const std::size_t callee_end = symbol_end + frontier.symbol.size();
    if (!CallStillOpen(frontier.line, callee_end)) return false;
    const std::vector<std::string> typed = OpenCallTypedArgs(
        frontier.line, callee_end
    );
    const std::vector<FunctionSig>* overloads = nullptr;
    if (frontier.symbol_kind == SymbolKind::Function) {
        const auto functions = model.functions.find(frontier.symbol);
        if (functions != model.functions.end()) overloads = &functions->second;
    } else if (frontier.symbol_kind == SymbolKind::Method) {
        const auto nominal = model.nominals.find(frontier.receiver);
        if (nominal != model.nominals.end()) {
            const auto methods = nominal->second.methods.find(frontier.symbol);
            if (methods != nominal->second.methods.end()) overloads = &methods->second;
        }
    }
    if (overloads == nullptr) return false;
    for (const FunctionSig& sig : *overloads) {
        if (typed.size() > sig.param_types.size()) continue;
        bool typed_ok = true;
        for (std::size_t index = 0; index < typed.size(); ++index) {
            const std::string arg_type = ArgTextType(
                typed[index], model, context
            );
            if (!arg_type.empty() &&
                !Compatible(arg_type, sig.param_types[index], model)) {
                typed_ok = false;
                break;
            }
        }
        if (!typed_ok) continue;
        std::string suffix;
        bool concrete = true;
        for (std::size_t index = typed.size();
             index < sig.param_types.size(); ++index) {
            const std::string arg = ConstructibleArg(
                sig.param_types[index], context, model
            );
            if (arg.empty() && sig.param_types[index] != "Unit") {
                concrete = false;
                break;
            }
            suffix += ", ";
            suffix += arg;
        }
        witness->found = true;
        witness->source = frontier.symbol;
        witness->target = sig.result;
        if (concrete) {
            witness->printable_suffix = suffix + ")";
        } else {
            witness->printable_suffix = "…)";
        }
        return true;
    }
    return false;
}

// 为未完成标识符搜索名称补全见证。
bool CompletionWitness(
    const FrontierInfo& frontier,
    std::string_view expected,
    const FunctionContext& context,
    const Model& model,
    RecoveryWitness* witness
) {
    if (frontier.symbol.empty()) return false;
    if (frontier.line.empty() || frontier.line.back() == '\n' ||
        !IsIdentContinue(static_cast<unsigned char>(frontier.line.back()))) {
        return false;
    }
    auto is_completion_candidate = [&](const std::string& candidate) {
        if (candidate.size() <= frontier.symbol.size()) return false;
        return candidate.compare(0, frontier.symbol.size(), frontier.symbol) == 0;
    };
    auto accept = [&](const std::string& type) {
        if (!expected.empty() && !Compatible(type, expected, model)) return false;
        return true;
    };
    if (frontier.boundary_kind == BoundaryKind::MemberSel) {
        if (frontier.receiver.empty()) return false;
        const auto nominal = model.nominals.find(frontier.receiver);
        if (nominal == model.nominals.end()) return false;
        for (const auto& field : nominal->second.fields) {
            if (!is_completion_candidate(field.first)) continue;
            if (!accept(field.second)) continue;
            witness->found = true;
            witness->source = field.second;
            witness->target = std::string(expected);
            witness->printable_suffix = field.first.substr(frontier.symbol.size());
            return true;
        }
        for (const auto& method : nominal->second.methods) {
            if (!is_completion_candidate(method.first)) continue;
            const std::string type = PostfixGraph::FunctionTypeOf(method.second.front());
            if (!accept(type)) continue;
            witness->found = true;
            witness->source = type;
            witness->target = std::string(expected);
            witness->printable_suffix = method.first.substr(frontier.symbol.size());
            return true;
        }
        return false;
    }
    if (frontier.symbol_kind != SymbolKind::Unknown) return false;
    std::vector<std::string> candidates;
    for (const auto& local : context.variables) {
        candidates.push_back(local.first);
    }
    for (const auto& global : model.globals) {
        candidates.push_back(global.first);
    }
    for (const auto& function : model.functions) {
        candidates.push_back(function.first);
    }
    for (const auto& nominal : model.nominals) {
        candidates.push_back(nominal.first);
    }
    for (const std::string& candidate : candidates) {
        if (!is_completion_candidate(candidate)) continue;
        std::string type;
        const auto local = context.variables.find(candidate);
        if (local != context.variables.end()) {
            type = local->second;
        } else {
            const auto global = model.globals.find(candidate);
            if (global != model.globals.end()) {
                type = global->second;
            } else if (model.functions.count(candidate) != 0) {
                type = PostfixGraph::FunctionTypeOf(model.functions.at(candidate).front());
            } else {
                type = "type:" + candidate;
            }
        }
        if (!accept(type)) continue;
        witness->found = true;
        witness->source = type;
        witness->target = std::string(expected);
        witness->printable_suffix = candidate.substr(frontier.symbol.size());
        return true;
    }
    return false;
}

// 在后缀图中搜索到目标类型的最短恢复路径。
RecoveryWitness FindRecoveryWitness(
    std::string_view source_type,
    std::string_view expected,
    const PostfixGraph& graph,
    const FunctionContext& context,
    const Model& model
) {
    RecoveryWitness result;
    result.source = std::string(source_type);
    result.target = std::string(expected);
    const bool debug = std::getenv("CANGJIE_TRACE_WITNESS") != nullptr;
    if (debug) std::cerr << "[witness] search " << source_type << " -> " << expected << "\n";
    if (source_type.empty() || !KnownType(source_type, model)) return result;

    struct State {
        std::string type;
        std::size_t cost = 0;
        std::vector<SuffixStep> steps;
    };
    std::vector<State> frontier_states;
    frontier_states.push_back({std::string(source_type), 0, {}});
    std::size_t visited = 0;
    while (!frontier_states.empty() && visited < 32) {
        std::size_t best = 0;
        for (std::size_t index = 1; index < frontier_states.size(); ++index) {
            if (frontier_states[index].cost < frontier_states[best].cost) best = index;
        }
        State state = frontier_states[best];
        frontier_states.erase(frontier_states.begin() + best);
        ++visited;
        if (debug) {
            std::cerr << "[witness]   pop type=" << state.type
                      << " cost=" << state.cost << " steps=" << state.steps.size() << "\n";
        }
        if (!state.steps.empty()) {
            const bool goal = expected.empty()
                ? KnownType(state.type, model)
                : Compatible(state.type, expected, model);
            if (goal) {
                result.steps = state.steps;
                result.found = true;
                std::string suffix;
                for (const SuffixStep& step : state.steps) {
                    switch (step.kind) {
                        case EdgeKind::Field:
                        case EdgeKind::MethodValue:
                        case EdgeKind::MethodCall:
                        case EdgeKind::Index:
                            suffix += "." + step.member;
                            break;
                        case EdgeKind::FunctionCall:
                            suffix += step.member;
                            break;
                    }
                }
                result.printable_suffix = suffix;
                if (debug) {
                    std::cerr << "[witness]   goal found: " << suffix
                              << "  (cost " << state.cost << ")\n";
                }
                return result;
            }
        }
        if (state.steps.size() >= 3) continue;
        const std::string head = TypeHead(state.type);
        const PostfixGraph::NominalNode* node = nullptr;
        const auto node_it = graph.nodes.find(head);
        if (node_it != graph.nodes.end()) node = &node_it->second;
        auto push = [&](const SuffixStep& step, std::size_t step_cost) {
            if (state.steps.size() + 1 > 3) return;
            State next;
            next.type = step.result;
            next.cost = state.cost + step_cost;
            next.steps = state.steps;
            next.steps.push_back(step);
            frontier_states.push_back(std::move(next));
        };
        const std::vector<std::string> inst_args = TypeArgs(state.type);
        auto subst = [&](const std::string& type) {
            return node != nullptr
                ? SubstituteTypeArgs(type, node->type_params, inst_args)
                : type;
        };
        std::size_t overload_checked = 0;
        if (node != nullptr) {
            for (const auto& field : node->fields) {
                SuffixStep step;
                step.kind = EdgeKind::Field;
                step.member = field.first;
                step.result = subst(field.second);
                push(step, 1);
            }
            for (const auto& value : node->method_values) {
                SuffixStep step;
                step.kind = EdgeKind::MethodValue;
                step.member = value.first;
                step.result = subst(value.second);
                push(step, 1);
            }
            for (const auto& calls : node->calls) {
                for (const auto& overload : calls.second) {
                    if (++overload_checked > 32) break;
                    bool constructible = true;
                    std::string args;
                    for (const std::string& param : overload.first) {
                        const std::string param_type = subst(param);
                        const std::string arg = ConstructibleArg(param_type, context, model);
                        if (arg.empty() && !param_type.empty() && param_type != "Unit") {
                            constructible = false;
                            break;
                        }
                        if (!args.empty()) args += ", ";
                        args += arg;
                    }
                    if (!constructible) continue;
                    SuffixStep step;
                    step.kind = EdgeKind::MethodCall;
                    step.member = calls.first + "(" + args + ")";
                    step.result = subst(overload.second);
                    push(step, overload.first.empty() ? 1 : 2);
                }
            }
        }
        if (IsFunctionType(state.type)) {
            const auto parts = FunctionTypeParts(state.type);
            bool constructible = true;
            std::string args;
            for (const std::string& param : parts.first) {
                const std::string arg = ConstructibleArg(param, context, model);
                if (arg.empty() && !param.empty() && param != "Unit") {
                    constructible = false;
                    break;
                }
                if (!args.empty()) args += ", ";
                args += arg;
            }
            if (constructible) {
                SuffixStep step;
                step.kind = EdgeKind::FunctionCall;
                step.member = "(" + args + ")";
                step.result = parts.second;
                push(step, 1);
            }
        }
        const auto args = TypeArgs(state.type);
        if (head == "Array" || head == "ArrayList" || head == "ArrayDeque" ||
            head == "Range") {
            if (!args.empty()) {
                SuffixStep step;
                step.kind = EdgeKind::Index;
                step.member = "[0]";
                step.result = args.front();
                push(step, 2);
            }
        } else if (head == "String") {
            SuffixStep step;
            step.kind = EdgeKind::Index;
            step.member = "[0]";
            step.result = "Rune";
            push(step, 2);
        } else if (head == "HashMap" && args.size() >= 2) {
            SuffixStep step;
            step.kind = EdgeKind::Index;
            step.member = "[\"x\"]";
            step.result = args[1];
            push(step, 2);
        }
    }
    return result;
}

// 结合期望类型、开放调用和后缀搜索计算带缓存的前缀恢复见证。
RecoveryWitness ComputeShadowWitness(
    const FrontierInfo& frontier,
    const Model& model,
    const FunctionContext& context,
    const PostfixGraph& graph,
    std::unordered_map<std::string, RecoveryWitness>* cache,
    WitnessStats* stats
) {
    RecoveryWitness witness;
    if (frontier.symbol_kind == SymbolKind::None) return witness;
    const std::string expected = ExpectedFromLine(
        frontier.line, context, model
    );
    const std::string cache_key = frontier.symbol + "|" + SymbolKindName(frontier.symbol_kind) +
        "|" + expected + "|" + std::to_string(static_cast<int>(frontier.tail_kind)) +
        "|" + std::to_string(static_cast<int>(frontier.boundary_kind));
    const auto cached = cache->find(cache_key);
    ++stats->queries;
    if (cached != cache->end()) {
        ++stats->cache_hits;
        return cached->second;
    }
    if (CompletionWitness(frontier, expected, context, model, &witness)) {
        ++stats->witness_found;
        (*cache)[cache_key] = witness;
        return witness;
    }
    if ((frontier.symbol_kind == SymbolKind::Function ||
         frontier.symbol_kind == SymbolKind::Method) &&
        frontier.tail_kind == TailKind::Call &&
        OpenCallWitness(frontier, model, context, &witness)) {
        ++stats->witness_found;
        (*cache)[cache_key] = witness;
        return witness;
    }
    const std::string frontier_type = FrontierTypeFor(frontier, context, model);
    if (!frontier_type.empty()) {
        witness = FindRecoveryWitness(
            frontier_type, expected, graph, context, model
        );
        if (witness.found) ++stats->witness_found;
    }
    (*cache)[cache_key] = witness;
    return witness;
}

// 对失败点（frontier）为调用位置的场景，逐一分析被调函数各重载的候选存活状态
CallFrontierResult ComputeCallFrontier(
    const FrontierInfo& frontier,
    const Model& model,
    const FunctionContext& context
) {
    CallFrontierResult result;
    if (frontier.tail_kind != TailKind::Call) return result;
    const std::size_t symbol_end = frontier.line.find(frontier.symbol);
    if (symbol_end == std::string::npos) return result;
    const std::size_t callee_end = symbol_end + frontier.symbol.size();

    std::vector<OverloadView> views;
    const auto add_views = [&views](const std::string& name,
                                    const std::vector<FunctionSig>& sigs,
                                    const std::vector<std::string>& type_params,
                                    const std::vector<std::string>& subst_args) {
        for (const FunctionSig& sig : sigs) {
            OverloadView view;
            view.name = name;
            view.type_params = sig.type_params;
            view.required = sig.required;
            for (const std::string& param : sig.param_types) {
                view.param_types.push_back(SubstituteTypeArgs(
                    param, type_params, subst_args
                ));
            }
            view.result_type = SubstituteTypeArgs(
                sig.result, type_params, subst_args
            );
            views.push_back(std::move(view));
        }
    };
    if (frontier.symbol_kind == SymbolKind::Method ||
        frontier.symbol_kind == SymbolKind::StaticMember) {
        const auto nominal = model.nominals.find(frontier.receiver);
        if (nominal != model.nominals.end()) {
            const std::vector<std::string> receiver_args = TypeArgs(frontier.receiver_type);
            const auto methods = nominal->second.methods.find(frontier.symbol);
            if (methods != nominal->second.methods.end()) {
                add_views(frontier.symbol, methods->second,
                          nominal->second.type_params, receiver_args);
            } else {
                const auto statics = nominal->second.static_methods.find(frontier.symbol);
                if (statics != nominal->second.static_methods.end()) {
                    add_views(frontier.symbol, statics->second,
                              nominal->second.type_params, receiver_args);
                }
            }
        }
    } else if (frontier.symbol_kind == SymbolKind::Function) {
        const auto functions = model.functions.find(frontier.symbol);
        if (functions != model.functions.end()) {
            add_views(frontier.symbol, functions->second, {}, {});
        }
    } else if (frontier.symbol_kind == SymbolKind::Type) {
        const auto nominal = model.nominals.find(frontier.symbol);
        if (nominal != model.nominals.end()) {
            add_views(frontier.symbol, nominal->second.constructors,
                      nominal->second.type_params, TypeArgs(frontier.receiver_type));
        }
    } else if (frontier.symbol_kind == SymbolKind::Local ||
               frontier.symbol_kind == SymbolKind::Global) {
        const auto local = context.variables.find(frontier.symbol);
        std::string var_type = local != context.variables.end()
            ? local->second : "";
        if (var_type.empty()) {
            const auto global = model.globals.find(frontier.symbol);
            if (global != model.globals.end()) var_type = global->second;
        }
        if (!var_type.empty() && IsFunctionType(var_type)) {
            const auto parts = FunctionTypeParts(var_type);
            OverloadView view;
            view.name = frontier.symbol;
            view.required = parts.first.size();
            view.param_types = parts.first;
            view.result_type = parts.second;
            views.push_back(std::move(view));
        }
    }
    if (views.empty()) return result;

    std::vector<std::string> typed;
    for (const std::string& arg : OpenCallTypedArgs(frontier.line, callee_end)) {
        typed.push_back(ArgTextType(arg, model, context));
    }
    const std::string expected = ExpectedFromLine(frontier.line, context, model);
    const bool call_closed = !CallStillOpen(frontier.line, callee_end);

    return CallFrontierClassifier().Classify(
        frontier.symbol, views, typed, expected, call_closed,
        [&model](std::string_view got, std::string_view want) {
            return Compatible(got, want, model);
        }
    );
}


// 判断声明类型及其嵌套参数是否全部已知。
bool KnownDeclaredType(
    std::string_view type,
    const Model& model,
    const std::unordered_set<std::string>& type_params
) {
    const std::string normalized = CompactType(type);
    if (normalized.empty() || normalized == "Unit") return true;
    if (type_params.count(normalized)) return true;
    if (IsFunctionType(normalized)) {
        const auto parts = FunctionTypeParts(normalized);
        for (const std::string& parameter : parts.first) {
            if (!KnownDeclaredType(parameter, model, type_params)) return false;
        }
        return KnownDeclaredType(parts.second, model, type_params);
    }
    if (normalized.size() >= 2 && normalized.front() == '(' && normalized.back() == ')') {
        for (const std::string& item : SplitTopLevel(
                 std::string_view(normalized).substr(1, normalized.size() - 2), ',')) {
            if (!KnownDeclaredType(item, model, type_params)) return false;
        }
        return true;
    }
    if (!KnownType(TypeHead(normalized), model)) return false;
    for (const std::string& argument : TypeArgs(normalized)) {
        if (!KnownDeclaredType(argument, model, type_params)) return false;
    }
    return true;
}

#ifdef CANGJIE_ENABLE_REGEX_SHADOW
// 使用正则旧实现查找外围名义类型参数。
std::unordered_set<std::string> EnclosingNominalTypeParametersRegex(
    std::string_view source,
    std::size_t position
) {
    static const std::regex nominal_pattern(
        R"(\b(?:class|interface)\s+[A-Za-z_][A-Za-z0-9_]*\s*(<[^:>{}()]*>)?[^{}]*\{)"
    );
    const std::string owned(source);
    std::size_t nearest_open = std::string::npos;
    std::vector<std::string> nearest;
    for (std::sregex_iterator it(owned.begin(), owned.end(), nominal_pattern), end; it != end; ++it) {
        const std::size_t open = static_cast<std::size_t>((*it).position() + (*it).length() - 1);
        if (open >= position) continue;
        const auto close = MatchingDelimiter(owned, open, '{', '}');
        if (close && *close < position) continue;
        if (nearest_open == std::string::npos || open > nearest_open) {
            nearest_open = open;
            nearest = ParseTypeParameters((*it)[1].str());
        }
    }
    return std::unordered_set<std::string>(nearest.begin(), nearest.end());
}
#endif


}
