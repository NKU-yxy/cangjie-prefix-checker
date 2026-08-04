"""Lightweight prefix semantic checks for monotonic local errors.

This layer intentionally does not know about public sample names, files, or
answer positions. It derives a small symbol table from the currently decoded
source prefix and reports only errors that later input cannot repair.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_PRIMS = {"Int64", "Float64", "Bool", "Rune", "String", "Unit"}
_KEYWORD_PREFIXES = {
    "if", "else", "for", "while", "break", "continue", "return", "func",
    "class", "interface", "let", "var", "public", "private", "static",
}
_NUMERIC = {"Int64", "Float64", "Rune"}
_SIGNED_NUMERIC = {"Int64", "Float64"}
_BUILTIN_NOMINALS = {"Array", "ArrayList", "HashMap", "HashSet", "Range", "String"}
_ITERABLE_HEADS = {"Range", "Array", "ArrayList", "HashSet", "KeysView", "ValuesView"}
_KNOWN_STRING_MEMBERS = {"size", "isEmpty", "contains", "startsWith", "endsWith", "toString", "get", "compare"}
_KNOWN_ARRAY_MEMBERS = {"size", "add", "addIfAbsent", "remove", "contains", "toArray", "first", "last", "fill"}
_KNOWN_HASHMAP_MEMBERS = {"size", "add", "addIfAbsent", "contains", "remove", "keys", "values", "get"}


@dataclass(frozen=True)
class PrefixSemanticResult:
    ok: bool
    message: str = ""


@dataclass
class FunctionSig:
    name: str
    type_params: tuple[str, ...]
    param_names: tuple[str | None, ...]
    param_types: tuple[str, ...]
    ret: str


@dataclass
class InterfaceInfo:
    name: str
    methods: dict[str, FunctionSig] = field(default_factory=dict)


@dataclass
class ClassInfo:
    name: str
    supers: tuple[str, ...] = ()
    methods: dict[str, FunctionSig] = field(default_factory=dict)


@dataclass
class _Context:
    funcs: dict[str, list[FunctionSig]]
    interfaces: dict[str, InterfaceInfo]
    classes: dict[str, ClassInfo]
    vars: dict[str, str]
    params: set[str]
    current_ret: str | None
    current_chunk: str


class PrefixSemanticChecker:
    """Report semantic errors at the earliest stable prefix boundary."""

    def validate(self, source: str) -> PrefixSemanticResult:
        if not source.strip():
            return PrefixSemanticResult(ok=True)

        ctx = self._build_context(source)
        for check in (
            self._check_duplicate_param,
            self._check_interface_method_prefix,
            self._check_break_continue,
            self._check_condition_prefix,
            self._check_for_prefix,
            self._check_generic_arity_prefix,
            self._check_call_prefix,
            self._check_member_and_index_prefix,
            self._check_var_assignment_prefix,
            self._check_return_prefix,
        ):
            result = check(source, ctx)
            if not result.ok:
                return result
        return PrefixSemanticResult(ok=True)

    def _build_context(self, source: str) -> _Context:
        funcs = self._collect_functions(source)
        interfaces = self._collect_interfaces(source)
        classes = self._collect_classes(source, interfaces)
        current_ret, current_chunk, params = self._current_function_context(source)
        vars_ = dict(params)
        vars_.update(self._collect_local_vars(current_chunk))
        return _Context(funcs, interfaces, classes, vars_, set(params), current_ret, current_chunk)

    def _collect_functions(self, source: str) -> dict[str, list[FunctionSig]]:
        funcs: dict[str, list[FunctionSig]] = {}
        pattern = re.compile(
            r"(?:^|\n)\s*(?:public\s+|private\s+)?(?:static\s+)?func\s+"
            r"([A-Za-z_]\w*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([A-Za-z_]\w*(?:\s*<[^>{}\n]*>)?|\([^{}\n]*\)\s*->\s*[A-Za-z_]\w*)\s*\{",
            re.M,
        )
        for m in pattern.finditer(source):
            name = m.group(1)
            tparams = _parse_type_params(m.group(2) or "")
            pnames, ptypes = _parse_params(m.group(3))
            sig = FunctionSig(name, tparams, tuple(pnames), tuple(ptypes), _norm_type(m.group(4)))
            funcs.setdefault(name, []).append(sig)
        main = re.search(r"(?:^|\n)\s*main\s*\(\s*\)\s*:\s*([A-Za-z_]\w*)\s*\{", source)
        if main:
            funcs.setdefault("main", []).append(FunctionSig("main", (), (), (), _norm_type(main.group(1))))
        return funcs

    def _collect_interfaces(self, source: str) -> dict[str, InterfaceInfo]:
        out: dict[str, InterfaceInfo] = {}
        for name, _header, body in _iter_blocks(source, "interface"):
            info = InterfaceInfo(name)
            for mm in re.finditer(
                r"func\s+([A-Za-z_]\w*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([A-Za-z_]\w*(?:\s*<[^>{}\n]*>)?|\([^{}\n]*\)\s*->\s*[A-Za-z_]\w*)",
                body,
            ):
                mname = mm.group(1)
                tparams = _parse_type_params(mm.group(2) or "")
                pnames, ptypes = _parse_params(mm.group(3))
                info.methods[mname] = FunctionSig(mname, tparams, tuple(pnames), tuple(ptypes), _norm_type(mm.group(4)))
            out[name] = info
        return out

    def _collect_classes(self, source: str, interfaces: dict[str, InterfaceInfo]) -> dict[str, ClassInfo]:
        out: dict[str, ClassInfo] = {}
        for name, header, body in _iter_blocks(source, "class"):
            supers = _parse_supers(header)
            info = ClassInfo(name, supers)
            for mm in re.finditer(
                r"(?:public\s+|private\s+)?(?:static\s+)?func\s+([A-Za-z_]\w*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([A-Za-z_]\w*(?:\s*<[^>{}\n]*>)?|\([^{}\n]*\)\s*->\s*[A-Za-z_]\w*)",
                body,
            ):
                mname = mm.group(1)
                tparams = _parse_type_params(mm.group(2) or "")
                pnames, ptypes = _parse_params(mm.group(3))
                info.methods[mname] = FunctionSig(mname, tparams, tuple(pnames), tuple(ptypes), _norm_type(mm.group(4)))
            out[name] = info
        return out

    def _current_function_context(self, source: str) -> tuple[str | None, str, dict[str, str]]:
        best: tuple[int, str | None, str, dict[str, str]] | None = None
        pattern = re.compile(
            r"((?:public\s+|private\s+)?(?:static\s+)?func\s+[A-Za-z_]\w*\s*(?:<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([^{}\n]+?)\s*\{|main\s*\(\s*\)\s*:\s*([A-Za-z_]\w*)\s*\{)",
            re.M,
        )
        for m in pattern.finditer(source):
            brace = source.find("{", m.start(), m.end())
            if brace < 0:
                continue
            if _brace_balance(source[brace:]) <= 0:
                continue
            ret = _norm_type(m.group(3) or m.group(4) or "Unit")
            pnames, ptypes = _parse_params(m.group(2) or "")
            params = {n: t for n, t in zip(pnames, ptypes) if n}
            best = (brace, ret, source[brace + 1 :], params)
        if best is None:
            return None, source, {}
        return best[1], best[2], best[3]

    def _collect_local_vars(self, chunk: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for m in re.finditer(r"\b(?:let|var)\s+([A-Za-z_]\w*)\s*:\s*([^=\n]+?)\s*=", chunk):
            out[m.group(1)] = _norm_type(m.group(2))
        return out

    def _check_duplicate_param(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        tail = _after_last(source, "func ")
        if "{" in tail or "(" not in tail:
            return PrefixSemanticResult(ok=True)
        inside = tail[tail.find("(") + 1 :]
        parts = _split_top_level(inside, ",")
        if len(parts) < 2:
            return PrefixSemanticResult(ok=True)
        seen: set[str] = set()
        for part in parts[:-1]:
            name = _leading_ident(part.strip())
            if name:
                seen.add(name)
        if ":" not in parts[-1]:
            return PrefixSemanticResult(ok=True)
        cur = _leading_ident(parts[-1].strip())
        if cur and cur in seen:
            return PrefixSemanticResult(False, f"duplicate parameter {cur}")
        return PrefixSemanticResult(ok=True)

    def _check_interface_method_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        class_match = _last_open_class(source)
        if not class_match:
            return PrefixSemanticResult(ok=True)
        _cname, supers, body = class_match
        mm = re.search(
            r"(?:public\s+|private\s+)?(?:static\s+)?func\s+([A-Za-z_]\w*)\s*(?:<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([A-Za-z_]\w*(?:\s*<[^>{}\n]*>)?)\s*$",
            body,
        )
        if not mm:
            return PrefixSemanticResult(ok=True)
        mname = mm.group(1)
        got_ret = _norm_type(mm.group(3))
        if not _is_complete_type_name(got_ret, ctx):
            return PrefixSemanticResult(ok=True)
        for sup in supers:
            iface = ctx.interfaces.get(_type_head(sup))
            if not iface or mname not in iface.methods:
                continue
            want = iface.methods[mname]
            _pnames, ptypes = _parse_params(mm.group(2))
            if tuple(ptypes) != want.param_types or not _same_type(got_ret, want.ret):
                return PrefixSemanticResult(False, f"method {mname} does not match interface {sup}")
        return PrefixSemanticResult(ok=True)

    def _check_break_continue(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        stripped = source.rstrip()
        if not (re.search(r"\bbreak$", stripped) or re.search(r"\bcontinue$", stripped)):
            return PrefixSemanticResult(ok=True)
        if not _inside_loop(ctx.current_chunk):
            return PrefixSemanticResult(False, "break/continue outside loop")
        return PrefixSemanticResult(ok=True)

    def _check_condition_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        m = re.search(r"\b(if|while)\s*\(([^()\n{}]*)\)\s*$", source.rstrip())
        if not m:
            return PrefixSemanticResult(ok=True)
        ty = self._expr_type(m.group(2), ctx)
        if ty and ty != "Bool":
            return PrefixSemanticResult(False, f"{m.group(1)} condition must be Bool")
        return PrefixSemanticResult(ok=True)

    def _check_for_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        m = re.search(r"\bfor\s*\(\s*([A-Za-z_]\w*)\s+in\s+([^()\n{}]*)$", source.rstrip())
        if m:
            expr = m.group(2).strip()
            range_result = self._check_for_range_prefix(expr, ctx)
            if not range_result.ok:
                return range_result
            ty = self._expr_type(expr, ctx)
            if ty and _type_head(ty) != "HashMap" and not _is_iterable(ty) and _for_operand_committed(expr, ctx):
                return PrefixSemanticResult(False, f"not iterable: {ty}")
        return PrefixSemanticResult(ok=True)

    def _check_for_range_prefix(self, expr: str, ctx: _Context) -> PrefixSemanticResult:
        if ".." not in expr:
            return PrefixSemanticResult(ok=True)
        left = expr.split("..", 1)[0].strip()
        left_ty = self._expr_type(left, ctx) if left else None
        if left_ty and left_ty not in {"Int64", "Rune"}:
            return PrefixSemanticResult(False, "range endpoint must be integral")
        return PrefixSemanticResult(ok=True)

    def _check_generic_arity_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        m = re.search(r"\b([A-Za-z_]\w*)\s*<([^<>(){}\n]*)$", source.rstrip())
        if not m or not m.group(2).rstrip().endswith(","):
            return PrefixSemanticResult(ok=True)
        name = m.group(1)
        sigs = ctx.funcs.get(name, [])
        if not sigs:
            return PrefixSemanticResult(ok=True)
        provided = len([p for p in _split_top_level(m.group(2), ",") if p.strip()])
        required = len(sigs[0].type_params)
        if provided >= required:
            return PrefixSemanticResult(False, f"{name} expects {required} type argument(s)")
        return PrefixSemanticResult(ok=True)

    def _check_call_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        stripped = source.rstrip()
        named = re.search(r"([A-Za-z_]\w*(?:\s*<[^>(){}\n]*>)?)\s*\(([^()\n{}]*)\s+([A-Za-z_]\w*)$", stripped)
        if named and "," in named.group(2):
            sig = self._call_sig(named.group(1), ctx)
            if sig:
                allowed = {n for n in sig.param_names if n}
                cur = named.group(3)
                if cur not in ctx.vars and allowed and not any(n.startswith(cur) for n in allowed):
                    return PrefixSemanticResult(False, f"unknown named argument {cur}")

        call = _last_call_prefix(stripped)
        if not call:
            return PrefixSemanticResult(ok=True)
        callee, explicit_args, arg_text = call
        sig = self._call_sig(callee, ctx, explicit_args)
        if not sig:
            return PrefixSemanticResult(ok=True)
        args = [a.strip() for a in _split_top_level(arg_text, ",")]
        complete_args = args[:-1]
        if len(complete_args) > len(sig.param_types):
            return PrefixSemanticResult(False, "too many arguments")
        subst = _subst_from_explicit(sig, explicit_args)
        inferred: dict[str, str] = {}
        for idx, arg in enumerate(complete_args):
            if not arg or ":" in arg:
                continue
            aty = self._expr_type(arg, ctx)
            if not aty or idx >= len(sig.param_types):
                continue
            if aty.startswith("unknown:"):
                continue
            want = _apply_subst(sig.param_types[idx], subst | inferred)
            if _is_tparam(want):
                prev = inferred.get(want)
                if prev and not _same_type(prev, aty):
                    return PrefixSemanticResult(False, "conflicting generic inference")
                inferred[want] = aty
                continue
            if not _compatible(aty, want):
                return PrefixSemanticResult(False, f"expected {want}, got {aty}")
        return PrefixSemanticResult(ok=True)

    def _check_member_and_index_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        stripped = source.rstrip()
        if _inside_string_tail(source):
            return PrefixSemanticResult(ok=True)
        idx = re.search(r"(.+)\[([^\]\n{}]*)$", stripped)
        if idx:
            base = _last_expr(idx.group(1))
            if not base:
                return PrefixSemanticResult(ok=True)
            base_ty = self._expr_type(base, ctx)
            if base_ty and not _is_indexable(base_ty):
                return PrefixSemanticResult(False, f"cannot index {base_ty}")
            inner = idx.group(2).strip()
            inner_ty = self._expr_type(inner, ctx) if inner else None
            if inner_ty and _safe_index_mismatch(inner, inner_ty):
                return PrefixSemanticResult(False, "index must be Int64")

        if stripped.endswith("."):
            base = _member_base_before_trailing_dot(stripped)
            if base in _hashmap_single_for_bound_names(source, ctx):
                return PrefixSemanticResult(False, "HashMap for pattern requires key/value binding")

        mem = re.search(r"(.+)\.([A-Za-z_]\w*)$", stripped)
        if mem:
            base = _last_expr(mem.group(1))
            base_ty = self._expr_type(base, ctx)
            member = mem.group(2)
            if base_ty and not _member_prefix_valid(base_ty, member):
                return PrefixSemanticResult(False, f"no member {member} on {base_ty}")
        return PrefixSemanticResult(ok=True)

    def _check_var_assignment_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        line = source[source.rfind("\n") + 1 :].strip()
        m = re.match(r"(?:let|var)\s+([A-Za-z_]\w*)\s*:\s*([^=]+?)\s*=\s*(.+)$", line)
        if not m:
            return PrefixSemanticResult(ok=True)
        want = _norm_type(m.group(2))
        expr = m.group(3).strip()
        result = self._check_expr_against(expr, want, ctx)
        if not result.ok:
            return result
        got = self._expr_type(expr, ctx)
        if got and _defer_var_rhs_mismatch(expr, got, want, source.endswith(("\n", "\r", ";"))):
            return PrefixSemanticResult(ok=True)
        if got and not _compatible(got, want):
            return PrefixSemanticResult(False, f"expected {want}, got {got}")
        return PrefixSemanticResult(ok=True)

    def _check_return_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        if not ctx.current_ret or ctx.current_ret == "Unit":
            return PrefixSemanticResult(ok=True)
        line = source[source.rfind("\n") + 1 :].strip()
        if not line or line.startswith(("let ", "var ", "if ", "for ", "while ", "println")):
            return PrefixSemanticResult(ok=True)
        if line.startswith("return "):
            expr = line[len("return ") :].strip()
        else:
            expr = line
            if not source.endswith(("\n", "\r", ";")) and not _is_atomic_literal_prefix(expr):
                return PrefixSemanticResult(ok=True)
        got = self._expr_type(expr, ctx)
        ended = source.endswith(("\n", "\r", ";"))
        if got and _safe_final_expr_mismatch(expr, got, ctx.current_ret, ended) and not _compatible(got, ctx.current_ret):
            return PrefixSemanticResult(False, f"expected {ctx.current_ret}, got {got}")
        return PrefixSemanticResult(ok=True)

    def _check_expr_against(self, expr: str, want: str, ctx: _Context) -> PrefixSemanticResult:
        if _looks_like_generic_construct_prefix(expr):
            return PrefixSemanticResult(ok=True)

        lambda_result = self._check_lambdas_in_call(expr, ctx)
        if not lambda_result.ok:
            return lambda_result

        member_call = _completed_member_call(expr)
        if member_call:
            base, member, arg_text = member_call
            base_ty = self._expr_type(base, ctx)
            sig = _member_call_sig(base_ty, member) if base_ty else None
            if sig:
                args = [a.strip() for a in _split_top_level(arg_text, ",") if a.strip()]
                if len(args) > len(sig.param_types):
                    return PrefixSemanticResult(False, "too many arguments")
                for idx, arg in enumerate(args):
                    aty = self._expr_type(arg, ctx)
                    if not aty or aty.startswith("unknown:") or idx >= len(sig.param_types):
                        continue
                    if not _compatible(aty, sig.param_types[idx]):
                        return PrefixSemanticResult(False, f"expected {sig.param_types[idx]}, got {aty}")

        if re.search(r"^-\s*", expr):
            inner = re.sub(r"^-\s*", "", expr).strip()
            ty = self._expr_type(inner, ctx)
            if ty and ty not in _SIGNED_NUMERIC:
                return PrefixSemanticResult(False, f"unary '-' requires numeric operand, got {ty}")
        if re.search(r"^!\s*", expr):
            inner = re.sub(r"^!\s*", "", expr).strip()
            ty = self._expr_type(inner, ctx)
            if ty and ty != "Bool":
                return PrefixSemanticResult(False, f"'!' requires Bool operand, got {ty}")

        binop = _find_tail_binary(expr)
        if binop:
            left, op, right = binop
            lt = self._expr_type(left, ctx)
            rt = self._expr_type(right, ctx) if right.strip() else None
            if op in {"%", "+", "-", "*", "/"}:
                if lt and op == "%" and lt != "Int64":
                    return PrefixSemanticResult(False, f"'%' requires Int64 operands, got {lt}")
                if lt and op in {"+", "-", "*", "/"} and lt not in _SIGNED_NUMERIC:
                    return PrefixSemanticResult(False, f"arithmetic operator requires numeric operands, got {lt}")
                if rt:
                    if op == "%" and rt != "Int64":
                        return PrefixSemanticResult(False, f"'%' requires Int64 operands, got {rt}")
                    if op in {"+", "-", "*", "/"} and rt not in _SIGNED_NUMERIC:
                        return PrefixSemanticResult(False, f"arithmetic operator requires numeric operands, got {rt}")
            if op in {"<", ">", "<=", ">="}:
                if lt and rt and (lt not in _NUMERIC or rt not in _NUMERIC):
                    return PrefixSemanticResult(False, "relational operator requires numeric operands")
                if lt and rt and not _same_type(lt, rt):
                    return PrefixSemanticResult(False, "relational operands must share numeric family")
                if lt and not right.strip() and lt not in _NUMERIC:
                    return PrefixSemanticResult(False, "relational operator requires numeric operands")
            if op in {"==", "!="} and lt and rt and not _same_type(lt, rt):
                if not _string_literal_unclosed(right):
                    return PrefixSemanticResult(False, "operands not comparable")
            if op in {"..", "..="}:
                if lt and lt not in {"Int64", "Rune"}:
                    return PrefixSemanticResult(False, "range endpoint must be integral")
                if rt and rt not in {"Int64", "Rune"}:
                    return PrefixSemanticResult(False, "range endpoint must be integral")

        got = self._expr_type(expr, ctx)
        if got and _type_head(got) == "interface-type":
            return PrefixSemanticResult(False, "interface cannot be used as a value")
        return PrefixSemanticResult(ok=True)

    def _check_lambdas_in_call(self, expr: str, ctx: _Context) -> PrefixSemanticResult:
        call = _call_expr_prefix(expr)
        if not call:
            return PrefixSemanticResult(ok=True)
        callee, explicit_args, arg_text = call
        sig = self._call_sig(callee, ctx, explicit_args)
        if not sig:
            return PrefixSemanticResult(ok=True)
        subst = _subst_from_explicit(sig, explicit_args)
        args = [a.strip() for a in _split_top_level(arg_text, ",")]
        for idx, arg in enumerate(args):
            if idx >= len(sig.param_types):
                continue
            want = _apply_subst(sig.param_types[idx], subst)
            if not _function_type_parts(want):
                continue
            if explicit_args and idx == 0 and "=>" not in arg:
                result = self._check_explicit_hof_lambda_header(arg, want, ctx)
                if not result.ok:
                    return result
                continue
            if "=>" not in arg:
                continue
            result = self._check_lambda_against(arg, want, ctx)
            if not result.ok:
                return result
        return PrefixSemanticResult(ok=True)

    def _check_explicit_hof_lambda_header(self, expr: str, want: str, ctx: _Context) -> PrefixSemanticResult:
        parts = _function_type_parts(want)
        if not parts or len(parts[0]) != 1:
            return PrefixSemanticResult(ok=True)
        header = _lambda_header_prefix(expr)
        if header is None:
            return PrefixSemanticResult(ok=True)
        if ":" not in header:
            return PrefixSemanticResult(ok=True)
        _name, got_ty = header.split(":", 1)
        got_ty = _norm_type(got_ty)
        if _is_complete_type_name(got_ty, ctx) and not _same_type(got_ty, parts[0][0]):
            return PrefixSemanticResult(False, f"expected {parts[0][0]}, got {got_ty}")
        return PrefixSemanticResult(ok=True)

    def _check_lambda_against(self, expr: str, want: str, ctx: _Context) -> PrefixSemanticResult:
        parts = _function_type_parts(want)
        if not parts:
            return PrefixSemanticResult(ok=True)
        want_params, want_ret = parts
        parsed = _parse_lambda_expr(expr)
        if not parsed:
            return PrefixSemanticResult(ok=True)
        lambda_params, body = parsed
        if len(lambda_params) != len(want_params):
            return PrefixSemanticResult(False, "lambda arity mismatch")
        for (_name, got_ty), want_ty in zip(lambda_params, want_params):
            if got_ty and not _same_type(got_ty, want_ty):
                return PrefixSemanticResult(False, f"expected {want_ty}, got {got_ty}")
        local_ctx = _ctx_with_lambda_params(ctx, lambda_params, want_params)
        lambda_closed = _matching_brace(expr.strip(), 0) is not None
        ret_parts = _function_type_parts(want_ret)
        if ret_parts:
            nested = _first_lambda_in_body(body)
            if nested:
                return self._check_lambda_against(nested, want_ret, local_ctx)
            return PrefixSemanticResult(ok=True)
        if not lambda_closed:
            return self._check_lambda_body_prefix(body, want_ret, local_ctx)
        body_expr = _strip_lambda_body_expr(body)
        got = self._expr_type(body_expr, local_ctx)
        if got and _safe_lambda_body_mismatch(body_expr, got, want_ret):
            return PrefixSemanticResult(False, f"expected {want_ret}, got {got}")
        return PrefixSemanticResult(ok=True)

    def _check_lambda_body_prefix(self, body: str, want_ret: str, ctx: _Context) -> PrefixSemanticResult:
        body_expr = _strip_lambda_body_expr(body)
        binop = _find_tail_binary(body_expr)
        if not binop:
            return PrefixSemanticResult(ok=True)
        left, op, right = binop
        if right.strip():
            return PrefixSemanticResult(ok=True)
        left_ty = self._expr_type(left, ctx)
        if op in {"+", "-", "*", "/", "%"} and left_ty and left_ty not in _SIGNED_NUMERIC:
            return PrefixSemanticResult(False, f"arithmetic operator requires numeric operands, got {left_ty}")
        if op in {"+", "-", "*", "/", "%"} and left_ty in _SIGNED_NUMERIC and want_ret not in _SIGNED_NUMERIC:
            return PrefixSemanticResult(False, f"expected {want_ret}, got {left_ty}")
        return PrefixSemanticResult(ok=True)

    def _expr_type(self, expr: str, ctx: _Context) -> str | None:
        expr = _strip_outer(expr.strip())
        if not expr:
            return None
        if re.fullmatch(r"true|false", expr):
            return "Bool"
        if re.fullmatch(r"\d[\d_]*", expr):
            return "Int64"
        if re.fullmatch(r"\d[\d_]*\.\d*", expr):
            return "Float64"
        if expr.startswith('"'):
            return "String"
        if re.fullmatch(r"r?'.*'?", expr):
            return "Rune"
        if expr in ctx.vars:
            return ctx.vars[expr]
        if expr in ctx.interfaces:
            return "interface-type:" + expr
        if expr in ctx.classes or expr in _PRIMS or expr in _BUILTIN_NOMINALS:
            return "type:" + expr
        if re.fullmatch(r"[A-Za-z_]\w*", expr):
            if expr in _KEYWORD_PREFIXES:
                return None
            if expr and expr[0].isupper():
                return None
            if not _identifier_has_possible_completion(expr, ctx):
                return "unknown:" + expr
            return None
        call = re.match(r"([A-Za-z_]\w*)\s*(?:<([^>(){}\n]*)>)?\s*\((.*)\)$", expr, re.S)
        if call:
            name = call.group(1)
            if name in ctx.classes:
                return name
            sig = self._call_sig(name, ctx, _parse_type_arg_list(call.group(2) or ""))
            if sig:
                subst = _subst_from_explicit(sig, _parse_type_arg_list(call.group(2) or ""))
                return _apply_subst(sig.ret, subst)
        member_call = re.match(r"(.+)\.([A-Za-z_]\w*)\s*\((.*)\)$", expr, re.S)
        if member_call:
            base_ty = self._expr_type(member_call.group(1), ctx)
            member = member_call.group(2)
            sig = _member_call_sig(base_ty, member) if base_ty else None
            if sig:
                return sig.ret
            if member == "toString":
                return "String"
            if member == "toArray" and base_ty and _type_head(base_ty) == "ArrayList":
                args = _type_args(base_ty)
                return f"Array<{args[0]}>" if args else "Array"
        member = re.match(r"(.+)\.([A-Za-z_]\w*)$", expr, re.S)
        if member:
            base_ty = self._expr_type(member.group(1), ctx)
            field = member.group(2)
            if field == "size" and base_ty and _type_head(base_ty) in {"Array", "ArrayList", "HashMap", "String"}:
                return "Int64"
            if field == "size" and base_ty and _type_head(base_ty) == "HashSet":
                return "Int64"
            if field == "get" and base_ty == "String":
                return "Rune"
        index = re.match(r"(.+)\[([^\]]*)\]$", expr, re.S)
        if index:
            base_ty = self._expr_type(index.group(1), ctx)
            if base_ty and _type_args(base_ty):
                return _type_args(base_ty)[0]
            if base_ty == "String":
                return "Rune"
        return None

    def _call_sig(self, callee: str, ctx: _Context, explicit_args: list[str] | None = None) -> FunctionSig | None:
        explicit_args = explicit_args or []
        callee = callee.strip()
        generic = re.match(r"([A-Za-z_]\w*)\s*<([^>]*)>$", callee)
        if generic:
            callee = generic.group(1)
            explicit_args = _parse_type_arg_list(generic.group(2))
        if callee.startswith("Array<") or callee == "Array":
            elem = _type_args(callee)[0] if _type_args(callee) else "T"
            return FunctionSig("Array", ("T",), (None, "repeat"), ("Int64", elem), f"Array<{elem}>")
        if callee.startswith("HashMap<"):
            args = _type_args(callee)
            k = args[0] if args else "K"
            v = args[1] if len(args) > 1 else "V"
            return FunctionSig("HashMap", ("K", "V"), (None,), (f"Array<({k}, {v})>",), f"HashMap<{k}, {v}>")
        if callee in ctx.funcs and ctx.funcs[callee]:
            return ctx.funcs[callee][0]
        return None


def _norm_type(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).replace(" ,", ",")


def _type_head(ty: str) -> str:
    return ty.split(":", 1)[0] if ty.startswith(("type:", "interface-type:", "unknown:")) else re.split(r"[<(]", ty, 1)[0]


def _type_args(ty: str) -> list[str]:
    start = ty.find("<")
    end = ty.rfind(">")
    if start < 0 or end < start:
        return []
    return [_norm_type(x) for x in _split_top_level(ty[start + 1 : end], ",") if x.strip()]


def _same_type(a: str, b: str) -> bool:
    return _norm_type(a) == _norm_type(b)


def _is_complete_type_name(ty: str, ctx: _Context) -> bool:
    head = _type_head(ty)
    return (
        ty in _PRIMS
        or head in _BUILTIN_NOMINALS
        or head in ctx.classes
        or head in ctx.interfaces
        or ">" in ty
        or "->" in ty
    )


def _compatible(got: str, want: str) -> bool:
    if got.startswith("unknown:"):
        return False
    if got.startswith("type:") or got.startswith("interface-type:"):
        return False
    return _same_type(got, want)


def _is_tparam(ty: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]\w*", ty)) and ty not in _PRIMS


def _apply_subst(ty: str, subst: dict[str, str]) -> str:
    out = ty
    for name, val in subst.items():
        out = re.sub(rf"\b{re.escape(name)}\b", val, out)
    return out


def _subst_from_explicit(sig: FunctionSig, explicit_args: list[str]) -> dict[str, str]:
    if len(explicit_args) != len(sig.type_params):
        return {}
    return {name: val for name, val in zip(sig.type_params, explicit_args)}


def _function_type_parts(ty: str) -> tuple[list[str], str] | None:
    ty = _norm_type(ty)
    if not ty.startswith("("):
        return None
    close = _matching_paren(ty, 0)
    if close is None:
        return None
    rest = ty[close + 1 :].strip()
    if not rest.startswith("->"):
        return None
    params = [_norm_type(x) for x in _split_top_level(ty[1:close], ",") if x.strip()]
    return params, _norm_type(rest[2:])


def _function_type_mentions(ty: str, tparam: str) -> bool:
    parts = _function_type_parts(ty)
    if not parts:
        return False
    params, ret = parts
    return any(re.search(rf"\b{re.escape(tparam)}\b", p) for p in params) or bool(
        re.search(rf"\b{re.escape(tparam)}\b", ret)
    )


def _ctx_with_lambda_params(ctx: _Context, params: list[tuple[str | None, str | None]], expected: list[str]) -> _Context:
    vars_ = dict(ctx.vars)
    param_names = set(ctx.params)
    for idx, (name, got_ty) in enumerate(params):
        if not name:
            continue
        ty = got_ty or (expected[idx] if idx < len(expected) else None)
        if ty:
            vars_[name] = ty
            param_names.add(name)
    return _Context(ctx.funcs, ctx.interfaces, ctx.classes, vars_, param_names, ctx.current_ret, ctx.current_chunk)


def _parse_type_params(text: str) -> tuple[str, ...]:
    text = text.strip()
    if text.startswith("<") and text.endswith(">"):
        return tuple(x.strip() for x in _split_top_level(text[1:-1], ",") if x.strip())
    return ()


def _parse_type_arg_list(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [_norm_type(x) for x in _split_top_level(text, ",") if x.strip()]


def _parse_lambda_expr(expr: str) -> tuple[list[tuple[str | None, str | None]], str] | None:
    expr = expr.strip()
    if not expr.startswith("{"):
        return None
    arrow = _find_top_level_fat_arrow(expr)
    if arrow < 0:
        return None
    header = expr[1:arrow].strip()
    params: list[tuple[str | None, str | None]] = []
    if header:
        for part in _split_top_level(header, ","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                name, ty = part.split(":", 1)
                params.append((_leading_ident(name.strip()), _norm_type(ty)))
            else:
                params.append((_leading_ident(part), None))
    return params, expr[arrow + 2 :].strip()


def _lambda_header_prefix(expr: str) -> str | None:
    expr = expr.strip()
    if not expr.startswith("{") or "=>" in expr:
        return None
    header = expr[1:].strip()
    if not header or "," in header:
        return None
    return header


def _find_top_level_fat_arrow(expr: str) -> int:
    paren = bracket = brace = angle = 0
    in_str = False
    esc = False
    for i, ch in enumerate(expr):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(0, brace - 1)
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)
        elif ch == "<":
            angle += 1
        elif ch == ">" and angle:
            angle -= 1
        if brace == 1 and not (paren or bracket or angle) and expr.startswith("=>", i):
            return i
    return -1


def _parse_params(text: str) -> tuple[list[str | None], list[str]]:
    names: list[str | None] = []
    types: list[str] = []
    for part in _split_top_level(text, ","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            continue
        name, ty = part.split(":", 1)
        name = name.strip().rstrip("!")
        ty = ty.split("=", 1)[0].strip()
        names.append(name or None)
        types.append(_norm_type(ty))
    return names, types


def _split_top_level(text: str, sep: str) -> list[str]:
    parts: list[str] = []
    start = 0
    angle = paren = bracket = brace = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "<":
            angle += 1
        elif ch == ">" and angle:
            angle -= 1
        elif ch == "(":
            paren += 1
        elif ch == ")" and paren:
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]" and bracket:
            bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}" and brace:
            brace -= 1
        elif ch == sep and not (angle or paren or bracket or brace):
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _brace_balance(text: str) -> int:
    return text.count("{") - text.count("}")


def _iter_blocks(source: str, keyword: str):
    pat = re.compile(rf"\b{keyword}\s+([A-Za-z_]\w*)([^\n{{}}]*)\{{")
    for m in pat.finditer(source):
        open_idx = source.find("{", m.start(), m.end())
        close_idx = _matching_brace(source, open_idx)
        if close_idx is None:
            continue
        yield m.group(1), m.group(2), source[open_idx + 1 : close_idx]


def _matching_brace(source: str, open_idx: int) -> int | None:
    depth = 0
    for i in range(open_idx, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _parse_supers(header: str) -> tuple[str, ...]:
    if "<:" not in header:
        return ()
    raw = header.split("<:", 1)[1]
    return tuple(_norm_type(x) for x in _split_top_level(raw, "&") if x.strip())


def _last_open_class(source: str) -> tuple[str, tuple[str, ...], str] | None:
    pat = re.compile(r"\bclass\s+([A-Za-z_]\w*)([^\n{}]*)\{")
    out = None
    for m in pat.finditer(source):
        open_idx = source.find("{", m.start(), m.end())
        if _brace_balance(source[open_idx:]) > 0:
            out = (m.group(1), _parse_supers(m.group(2)), source[open_idx + 1 :])
    return out


def _inside_loop(chunk: str) -> bool:
    loop_depths: list[int] = []
    depth = 0
    token_re = re.compile(r"\b(?:for|while)\b|[{}]")
    for m in token_re.finditer(chunk):
        tok = m.group(0)
        if tok in {"for", "while"}:
            brace = chunk.find("{", m.end())
            if brace >= 0:
                loop_depths.append(depth + 1)
        elif tok == "{":
            depth += 1
        elif tok == "}":
            depth = max(0, depth - 1)
            loop_depths = [d for d in loop_depths if d <= depth]
    return bool(loop_depths)


def _after_last(source: str, marker: str) -> str:
    idx = source.rfind(marker)
    return source[idx + len(marker) :] if idx >= 0 else ""


def _leading_ident(text: str) -> str | None:
    m = re.match(r"([A-Za-z_]\w*)", text)
    return m.group(1) if m else None


def _strip_outer(expr: str) -> str:
    while expr.startswith("(") and expr.endswith(")") and _matching_paren(expr, 0) == len(expr) - 1:
        expr = expr[1:-1].strip()
    return expr


def _matching_paren(text: str, open_idx: int) -> int | None:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


def _find_tail_binary(expr: str) -> tuple[str, str, str] | None:
    for op in ("==", "!=", "<=", ">=", "..=", "..", "%", "+", "-", "*", "/", "<", ">"):
        idx = _find_top_level_op(expr, op)
        if idx >= 0:
            return expr[:idx].strip(), op, expr[idx + len(op) :].strip()
    return None


def _find_top_level_op(expr: str, op: str) -> int:
    angle = paren = bracket = brace = 0
    in_str = False
    esc = False
    i = len(expr) - len(op)
    while i >= 0:
        ch = expr[i]
        if in_str:
            if ch == '"' and not esc:
                in_str = False
            esc = ch == "\\" and not esc
            i -= 1
            continue
        if ch == '"':
            in_str = True
        elif ch == ">":
            angle += 1
        elif ch == "<" and angle:
            angle -= 1
        elif ch == ")":
            paren += 1
        elif ch == "(" and paren:
            paren -= 1
        elif ch == "]":
            bracket += 1
        elif ch == "[" and bracket:
            bracket -= 1
        elif ch == "}":
            brace += 1
        elif ch == "{" and brace:
            brace -= 1
        if not (angle or paren or bracket or brace) and expr.startswith(op, i):
            if op in {"+", "-"} and i == 0:
                i -= 1
                continue
            return i
        i -= 1
    return -1


def _identifier_has_possible_completion(name: str, ctx: _Context) -> bool:
    symbols = set(ctx.vars) | set(ctx.funcs) | set(ctx.classes) | set(ctx.interfaces) | _PRIMS
    return any(sym.startswith(name) for sym in symbols)


def _is_atomic_literal_prefix(expr: str) -> bool:
    expr = expr.strip()
    return bool(
        re.fullmatch(r"true|false", expr)
        or re.fullmatch(r"\d[\d_]*", expr)
        or re.fullmatch(r"\d[\d_]*\.\d*", expr)
        or expr.startswith('"')
        or expr.startswith("'")
    )


def _inside_string_tail(source: str) -> bool:
    line = source[source.rfind("\n") + 1 :]
    escaped = False
    in_str = False
    for ch in line:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
    return in_str


def _safe_final_expr_mismatch(expr: str, got: str, want: str, ended: bool) -> bool:
    if ended:
        return True
    expr = expr.strip()
    if got == "Bool":
        return True
    if got == "String" and expr.startswith('"'):
        return True
    if got == "Rune" and expr.startswith("'"):
        return True
    if got in {"Int64", "Float64"} and want not in {"Int64", "Float64"}:
        return True
    return False


def _safe_index_mismatch(expr: str, got: str) -> bool:
    if got.startswith("unknown:") or got == "Int64":
        return False
    expr = expr.strip()
    return bool(
        re.fullmatch(r"true|false", expr)
        or expr.startswith('"')
        or expr.startswith("'")
    )


def _defer_var_rhs_mismatch(expr: str, got: str, want: str, ended: bool) -> bool:
    if ended:
        return False
    if got.startswith("unknown:"):
        return False
    expr = expr.strip()
    if re.fullmatch(r"true|false", expr):
        return False
    if re.fullmatch(r"[A-Za-z_]\w*", expr):
        return True
    if re.fullmatch(r"\d[\d_]*", expr):
        return True
    if re.fullmatch(r"\d[\d_]*\.\d*", expr):
        return True
    if expr.startswith('"') or expr.startswith("'"):
        return True
    return False


def _looks_like_generic_construct_prefix(expr: str) -> bool:
    return re.search(r"\b[A-Z][A-Za-z_0-9]*\s*<[^>\n{}()]*$", expr.strip()) is not None


def _string_literal_unclosed(expr: str) -> bool:
    expr = expr.strip()
    if not expr.startswith('"'):
        return False
    escaped = False
    closed = False
    for ch in expr[1:]:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            closed = True
            break
    return not closed


def _last_expr(prefix: str) -> str:
    text = prefix.rstrip()
    for sep in ("\n", "=", "(", ",", "{", "return "):
        idx = text.rfind(sep)
        if idx >= 0:
            return text[idx + len(sep) :].strip()
    return text


def _last_call_prefix(source: str) -> tuple[str, list[str], str] | None:
    m = re.search(r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\s*<([^>(){}\n]*)>)?)\s*\(([^()\n{}]*)$", source)
    if not m:
        return None
    return m.group(1), _parse_type_arg_list(m.group(2) or ""), m.group(3)


def _call_expr_prefix(expr: str) -> tuple[str, list[str], str] | None:
    expr = expr.strip()
    m = re.match(r"([A-Za-z_]\w*(?:\s*<([^>(){}\n]*)>)?)\s*\(", expr, re.S)
    if not m:
        return None
    open_idx = expr.find("(", m.start())
    if open_idx < 0:
        return None
    close_idx = _matching_paren(expr, open_idx)
    end = close_idx if close_idx is not None else len(expr)
    return m.group(1), _parse_type_arg_list(m.group(2) or ""), expr[open_idx + 1 : end]


def _completed_member_call(expr: str) -> tuple[str, str, str] | None:
    m = re.match(r"(.+)\.([A-Za-z_]\w*)\s*\((.*)\)$", expr.strip(), re.S)
    if not m:
        return None
    return m.group(1).strip(), m.group(2), m.group(3)


def _member_base_before_trailing_dot(source: str) -> str:
    base = source[:-1].rstrip()
    paren = re.search(r"\(([A-Za-z_]\w*)\)$", base)
    if paren:
        return paren.group(1)
    return _strip_outer(_last_expr(base))


def _hashmap_single_for_bound_names(source: str, ctx: _Context) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"\bfor\s*\(\s*([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)\s*\)", source):
        iter_name = m.group(2)
        if _type_head(ctx.vars.get(iter_name, "")) == "HashMap":
            names.add(m.group(1))
    return names


def _first_lambda_in_body(body: str) -> str | None:
    idx = body.find("{")
    if idx < 0:
        return None
    return body[idx:].strip()


def _strip_lambda_body_expr(body: str) -> str:
    body = body.strip()
    while body.endswith("}"):
        candidate = body[:-1].rstrip()
        if candidate.count("{") <= candidate.count("}"):
            body = candidate
        else:
            break
    return body.strip()


def _safe_lambda_body_mismatch(expr: str, got: str, want: str) -> bool:
    if _compatible(got, want):
        return False
    expr = expr.strip()
    return bool(
        re.fullmatch(r"true|false", expr)
        or re.fullmatch(r"\d[\d_]*", expr)
        or re.fullmatch(r"\d[\d_]*\.\d*", expr)
        or expr.startswith('"')
        or expr.startswith("'")
    )


def _is_iterable(ty: str) -> bool:
    return _type_head(ty) in _ITERABLE_HEADS


def _for_operand_committed(expr: str, ctx: _Context) -> bool:
    expr = expr.strip()
    if re.fullmatch(r"\d[\d_]*", expr):
        return False
    if re.fullmatch(r"\d[\d_]*\.\d*", expr):
        return False
    if re.fullmatch(r"[A-Za-z_]\w*", expr):
        return expr in ctx.vars and expr not in ctx.params
    return True


def _is_indexable(ty: str) -> bool:
    return _type_head(ty) in {"Array", "ArrayList", "String"}


def _member_prefix_valid(ty: str, member: str) -> bool:
    head = _type_head(ty)
    if head in {"Int64", "Float64", "Bool", "Rune", "String"} and "toString".startswith(member):
        return True
    members: set[str]
    if head == "String":
        members = _KNOWN_STRING_MEMBERS
    elif head in {"Array", "ArrayList", "HashSet"}:
        members = _KNOWN_ARRAY_MEMBERS
    elif head == "HashMap":
        members = _KNOWN_HASHMAP_MEMBERS
    else:
        return True
    return any(m.startswith(member) for m in members)


def _member_call_sig(base_ty: str | None, member: str) -> FunctionSig | None:
    if not base_ty:
        return None
    head = _type_head(base_ty)
    args = _type_args(base_ty)
    if head == "String":
        if member in {"contains", "startsWith", "endsWith"}:
            return FunctionSig(member, (), (None,), ("String",), "Bool")
        if member == "get":
            return FunctionSig(member, (), (None,), ("Int64",), "Rune")
        if member == "compare":
            return FunctionSig(member, (), (None,), ("String",), "Int64")
    if head in {"Array", "ArrayList"}:
        elem = args[0] if args else "T"
        if member in {"contains", "add", "addIfAbsent", "remove", "fill"}:
            ret = "Bool" if member in {"contains", "addIfAbsent", "remove"} else "Unit"
            return FunctionSig(member, (), (None,), (elem,), ret)
        if member in {"first", "last"}:
            return FunctionSig(member, (), (), (), elem)
    if head == "HashMap":
        key = args[0] if args else "K"
        val = args[1] if len(args) > 1 else "V"
        if member in {"contains", "remove", "get"}:
            ret = val if member == "get" else "Bool"
            return FunctionSig(member, (), (None,), (key,), ret)
    return None
