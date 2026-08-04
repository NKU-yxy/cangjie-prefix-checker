"""Lightweight prefix semantic checks for monotonic local errors.

This layer intentionally does not know about public sample names, files, or
answer positions. It derives a small symbol table from the currently decoded
source prefix and reports only errors that later input cannot repair.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_INTEGER_TYPES = {"Int8", "Int16", "Int32", "Int64"}
_FLOAT_TYPES = {"Float32", "Float64"}
_PRIMS = _INTEGER_TYPES | _FLOAT_TYPES | {"Bool", "Rune", "String", "Unit"}
_KEYWORD_PREFIXES = {
    "if", "else", "for", "while", "break", "continue", "return", "func",
    "class", "interface", "let", "var", "public", "private", "static",
}
_NUMERIC = _INTEGER_TYPES | _FLOAT_TYPES | {"Rune"}
_SIGNED_NUMERIC = _INTEGER_TYPES | _FLOAT_TYPES
_BUILTIN_NOMINALS = {"Array", "ArrayList", "HashMap", "HashSet", "Range", "String"}
_ITERABLE_HEADS = {"Range", "Array", "ArrayList", "HashSet", "KeysView", "ValuesView"}
_KNOWN_STRING_MEMBERS = {"size", "isEmpty", "contains", "startsWith", "endsWith", "toString", "get", "compare"}
_KNOWN_ARRAY_MEMBERS = {"size", "add", "addIfAbsent", "remove", "contains", "toArray", "first", "last", "fill"}
_KNOWN_HASHMAP_MEMBERS = {"size", "add", "addIfAbsent", "contains", "remove", "keys", "values", "get"}
_COMMIT_SUFFIXES = ("\n", "\r", ";", ",", "}")


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
    required_params: int | None = None


@dataclass
class InterfaceInfo:
    name: str
    methods: dict[str, FunctionSig] = field(default_factory=dict)
    type_params: tuple[str, ...] = ()
    supers: tuple[str, ...] = ()


@dataclass
class ClassInfo:
    name: str
    supers: tuple[str, ...] = ()
    methods: dict[str, FunctionSig] = field(default_factory=dict)
    type_params: tuple[str, ...] = ()
    fields: dict[str, str] = field(default_factory=dict)
    constructors: tuple[tuple[str, ...], ...] = ()
    method_overloads: dict[str, tuple[FunctionSig, ...]] = field(default_factory=dict)
    constructor_sigs: tuple[FunctionSig, ...] = ()
    static_fields: dict[str, str] = field(default_factory=dict)
    static_methods: dict[str, FunctionSig] = field(default_factory=dict)
    static_method_overloads: dict[str, tuple[FunctionSig, ...]] = field(default_factory=dict)


@dataclass
class _Context:
    funcs: dict[str, list[FunctionSig]]
    interfaces: dict[str, InterfaceInfo]
    classes: dict[str, ClassInfo]
    vars: dict[str, str]
    params: set[str]
    current_ret: str | None
    current_chunk: str
    immutable_vars: set[str] = field(default_factory=set)


class PrefixSemanticChecker:
    """Report semantic errors at the earliest stable prefix boundary."""

    def __init__(self, preload_context: dict | None = None) -> None:
        self._preload_funcs: dict[str, list[FunctionSig]] = {}
        self._preload_interfaces: dict[str, InterfaceInfo] = {}
        self._preload_classes: dict[str, ClassInfo] = {}
        self._preload_vars: dict[str, str] = {}
        self._preload_immutable: set[str] = set()
        self._cache_source = ""
        self._cached_source_funcs: dict[str, list[FunctionSig]] = {}
        self._cached_source_interfaces: dict[str, InterfaceInfo] = {}
        self._cached_source_classes: dict[str, ClassInfo] = {}
        self._cached_function_meta: tuple[str | None, int, dict[str, str]] = (
            None,
            0,
            {},
        )
        self._active_line_source = ""
        self._active_line_value = ""
        if preload_context:
            self._load_predefined_context(preload_context)

    def _load_predefined_context(self, context: dict) -> None:
        for variable in context.get("variables", []):
            if not isinstance(variable, dict):
                continue
            name = variable.get("name")
            declared_type = variable.get("type")
            if name and declared_type:
                self._preload_vars[str(name)] = _norm_type(str(declared_type))
                if not variable.get("mutable", False):
                    self._preload_immutable.add(str(name))

        for function in context.get("functions", []):
            sig = _function_sig_from_context(function)
            if sig:
                self._preload_funcs.setdefault(sig.name, []).append(sig)

        for interface in context.get("interfaces", []):
            if not isinstance(interface, dict) or not interface.get("name"):
                continue
            name = str(interface["name"])
            info = InterfaceInfo(
                name,
                type_params=tuple(
                    str(item) for item in interface.get("type_params", []) if item
                ),
                supers=tuple(
                    str(item) for item in interface.get("supers", []) if item
                ),
            )
            for method in interface.get("methods", []):
                sig = _function_sig_from_context(method)
                if sig and sig.name not in info.methods:
                    info.methods[sig.name] = sig
            self._preload_interfaces[name] = info

        for class_entry in context.get("classes", []):
            if not isinstance(class_entry, dict) or not class_entry.get("name"):
                continue
            name = str(class_entry["name"])
            methods: dict[str, FunctionSig] = {}
            method_overloads: dict[str, list[FunctionSig]] = {}
            for method in class_entry.get("methods", []):
                sig = _function_sig_from_context(method)
                if sig:
                    methods.setdefault(sig.name, sig)
                    method_overloads.setdefault(sig.name, []).append(sig)
            static_methods: dict[str, FunctionSig] = {}
            static_method_overloads: dict[str, list[FunctionSig]] = {}
            for method in class_entry.get("static_methods", []):
                sig = _function_sig_from_context(method)
                if sig:
                    static_methods.setdefault(sig.name, sig)
                    static_method_overloads.setdefault(sig.name, []).append(sig)
            fields = {
                str(field_name): _norm_type(str(field_type))
                for field_name, field_type in class_entry.get("fields", {}).items()
                if field_type
            }
            static_fields = {
                str(field_name): _norm_type(str(field_type))
                for field_name, field_type in class_entry.get("static_fields", {}).items()
                if field_type
            }
            constructors = tuple(
                tuple(_norm_type(str(param)) for param in ctor if param)
                for ctor in class_entry.get("constructors", [])
                if isinstance(ctor, list)
            )
            constructor_sigs = tuple(
                sig
                for item in class_entry.get("constructor_signatures", [])
                if (sig := _function_sig_from_context(item)) is not None
            )
            self._preload_classes[name] = ClassInfo(
                name=name,
                supers=tuple(str(item) for item in class_entry.get("supers", []) if item),
                methods=methods,
                type_params=tuple(str(item) for item in class_entry.get("type_params", []) if item),
                fields=fields,
                constructors=constructors,
                method_overloads={
                    method_name: tuple(sigs)
                    for method_name, sigs in method_overloads.items()
                },
                constructor_sigs=constructor_sigs,
                static_fields=static_fields,
                static_methods=static_methods,
                static_method_overloads={
                    method_name: tuple(sigs)
                    for method_name, sigs in static_method_overloads.items()
                },
            )

    def validate(self, source: str) -> PrefixSemanticResult:
        if not source.strip():
            return PrefixSemanticResult(ok=True)

        ctx = self._build_context(source)
        for check in (
            self._check_duplicate_param,
            self._check_declared_type_prefix,
            self._check_interface_method_prefix,
            self._check_interface_completion_prefix,
            self._check_init_prefix,
            self._check_this_member_prefix,
            self._check_break_continue,
            self._check_condition_prefix,
            self._check_if_join_prefix,
            self._check_for_prefix,
            self._check_generic_arity_prefix,
            self._check_call_prefix,
            self._check_member_and_index_prefix,
            self._check_var_assignment_prefix,
            self._check_reassignment_prefix,
            self._check_committed_call_prefix,
            self._check_return_prefix,
        ):
            result = check(source, ctx)
            if not result.ok:
                return result
        return PrefixSemanticResult(ok=True)

    def _check_declared_type_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        """Reject stable unknown types in declaration headers."""

        known = set(ctx.classes) | set(ctx.interfaces) | _PRIMS | _BUILTIN_NOMINALS
        tail = _physical_line_tail(source)
        function = re.search(
            r"\bfunc\s+[A-Za-z_]\w*\s*(<[^>]*>)?\s*\(([^{};\n]*)\)"
            r"\s*(?::\s*([^{}\n]+?))?\s*(?:\{|$)",
            tail,
        )
        if function:
            type_params = set(_parse_type_params(function.group(1) or ""))
            conflict = type_params & _PRIMS
            if conflict:
                return PrefixSemanticResult(
                    False,
                    f"type parameter conflicts with primitive {sorted(conflict)[0]}",
                )
            _names, parameter_types = _parse_params(function.group(2))
            declared = parameter_types
            if function.group(3):
                declared.append(_norm_type(function.group(3)))
            unknown = _first_unknown_type(declared, known | type_params)
            if unknown:
                return PrefixSemanticResult(False, f"unknown type {unknown}")

        class_header = re.search(
            r"\b(?:class|interface)\s+[A-Za-z_]\w*\s*(<[^>]*>)?"
            r"\s*(?:<:\s*([^{}]+?))?\s*(?:\{|$)",
            tail,
        )
        if class_header:
            type_params = set(_parse_type_params(class_header.group(1) or ""))
            conflict = type_params & _PRIMS
            if conflict:
                return PrefixSemanticResult(
                    False,
                    f"type parameter conflicts with primitive {sorted(conflict)[0]}",
                )
            if class_header.group(2):
                supers = [
                    item.strip()
                    for item in _split_top_level(class_header.group(2), "&")
                    if item.strip()
                ]
                unknown = _first_unknown_type(supers, known | type_params)
                if unknown:
                    return PrefixSemanticResult(False, f"unknown supertype {unknown}")
        return PrefixSemanticResult(ok=True)

    def _build_context(self, source: str) -> _Context:
        extending = source.startswith(self._cache_source)
        delta = source[len(self._cache_source) :] if extending else source
        reset = not extending or not self._cache_source
        if reset or "{" in delta:
            self._cached_source_funcs = self._collect_functions(source)
        if reset or "}" in delta:
            self._cached_source_interfaces = self._collect_interfaces(source)
            self._cached_source_classes = self._collect_classes(
                source,
                {**self._preload_interfaces, **self._cached_source_interfaces},
            )
        if reset or "{" in delta or "}" in delta:
            current_ret, current_chunk, params = self._current_function_context(source)
            self._cached_function_meta = (
                current_ret,
                len(source) - len(current_chunk),
                params,
            )
        self._cache_source = source

        funcs = {name: list(sigs) for name, sigs in self._preload_funcs.items()}
        for name, sigs in self._cached_source_funcs.items():
            funcs.setdefault(name, []).extend(sigs)
        interfaces = dict(self._preload_interfaces)
        interfaces.update(self._cached_source_interfaces)
        classes = dict(self._preload_classes)
        classes.update(self._cached_source_classes)
        current_ret, chunk_start, params = self._cached_function_meta
        current_chunk = source[chunk_start:]
        vars_ = dict(self._preload_vars)
        vars_.update(params)
        vars_.update(self._collect_local_vars(current_chunk))
        vars_.update(_collect_open_for_bindings(current_chunk, vars_))
        immutable = set(self._preload_immutable) | set(params)
        if current_ret is not None:
            immutable.update(self._collect_immutable_vars(current_chunk))
        return _Context(
            funcs,
            interfaces,
            classes,
            vars_,
            set(params),
            current_ret,
            current_chunk,
            immutable,
        )

    def _active_line(self, source: str) -> str:
        if source != self._active_line_source:
            self._active_line_source = source
            self._active_line_value = _active_or_committed_line(source)
        return self._active_line_value

    def _collect_functions(self, source: str) -> dict[str, list[FunctionSig]]:
        funcs: dict[str, list[FunctionSig]] = {}
        pattern = re.compile(
            r"(?:^|[\n}])\s*(?:public\s+|private\s+)?(?:static\s+)?func\s+"
            r"([A-Za-z_]\w*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([A-Za-z_]\w*(?:\s*<[^>{}\n]*>)?|\([^{}\n]*\)\s*->\s*[A-Za-z_]\w*)\s*\{",
            re.M,
        )
        for m in pattern.finditer(source):
            name = m.group(1)
            tparams = _parse_type_params(m.group(2) or "")
            pnames, ptypes = _parse_params(m.group(3))
            sig = FunctionSig(name, tparams, tuple(pnames), tuple(ptypes), _norm_type(m.group(4)))
            funcs.setdefault(name, []).append(sig)
        main = re.search(r"(?:^|[\n}])\s*(?:func\s+)?main\s*\(\s*\)\s*(?::\s*([A-Za-z_]\w*))?\s*\{", source)
        if main:
            funcs.setdefault("main", []).append(FunctionSig("main", (), (), (), _norm_type(main.group(1) or "Unit")))
        return funcs

    def _collect_interfaces(self, source: str) -> dict[str, InterfaceInfo]:
        out: dict[str, InterfaceInfo] = {}
        for name, header, body in _iter_blocks(source, "interface"):
            type_param_match = re.search(r"<([^:>{}]*)>", header.split("<:", 1)[0])
            type_params = tuple(
                part.strip()
                for part in _split_top_level(type_param_match.group(1), ",")
                if part.strip()
            ) if type_param_match else ()
            info = InterfaceInfo(
                name,
                type_params=type_params,
                supers=_parse_supers(header),
            )
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
            type_param_match = re.search(r"<([^:>{}]*)>", header.split("<:", 1)[0])
            type_params = tuple(
                part.strip()
                for part in _split_top_level(type_param_match.group(1), ",")
                if part.strip()
            ) if type_param_match else ()
            fields: dict[str, str] = {}
            static_fields: dict[str, str] = {}
            for field_match in re.finditer(
                r"\b(?:(static)\s+)?(?:let|var)\s+([A-Za-z_]\w*)\s*:\s*([^=\n{}]+)",
                body,
            ):
                target = static_fields if field_match.group(1) else fields
                target[field_match.group(2)] = _norm_type(field_match.group(3))
            constructor_sigs: list[FunctionSig] = []
            for init_match in re.finditer(r"\binit\s*\(([^{};\n]*)\)", body):
                param_names, param_types = _parse_params(init_match.group(1))
                constructor_sigs.append(
                    FunctionSig(
                        name,
                        type_params,
                        tuple(param_names),
                        tuple(param_types),
                        (
                            f"{name}<{', '.join(type_params)}>"
                            if type_params
                            else name
                        ),
                    )
                )
            info = ClassInfo(
                name,
                supers,
                type_params=type_params,
                fields=fields,
                constructor_sigs=tuple(constructor_sigs),
                static_fields=static_fields,
            )
            for mm in re.finditer(
                r"(?:public\s+|private\s+)?(?:(static)\s+)?func\s+([A-Za-z_]\w*)\s*(<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*:\s*([A-Za-z_]\w*(?:\s*<[^>{}\n]*>)?|\([^{}\n]*\)\s*->\s*[A-Za-z_]\w*)",
                body,
            ):
                is_static = bool(mm.group(1))
                mname = mm.group(2)
                tparams = _parse_type_params(mm.group(3) or "")
                pnames, ptypes = _parse_params(mm.group(4))
                sig = FunctionSig(mname, tparams, tuple(pnames), tuple(ptypes), _norm_type(mm.group(5)))
                methods = info.static_methods if is_static else info.methods
                overloads = info.static_method_overloads if is_static else info.method_overloads
                methods[mname] = sig
                existing = list(overloads.get(mname, ()))
                existing.append(sig)
                overloads[mname] = tuple(existing)
            out[name] = info
        return out

    def _current_function_context(self, source: str) -> tuple[str | None, str, dict[str, str]]:
        best: tuple[int, str | None, str, dict[str, str]] | None = None
        pattern = re.compile(
            r"((?:public\s+|private\s+)?(?:static\s+)?func\s+[A-Za-z_]\w*\s*(?:<[^>{}()\n]*>)?\s*\(([^{};\n]*)\)\s*(?::\s*([^{}\n]+?))?\s*\{|main\s*\(\s*\)\s*(?::\s*([A-Za-z_]\w*))?\s*\{)",
            re.M,
        )
        for m in pattern.finditer(source):
            brace = source.find("{", m.start(), m.end())
            if brace < 0:
                continue
            if _matching_brace(source, brace) is not None:
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
        for m in re.finditer(r"\b(?:let|var)\s+([A-Za-z_]\w*)\s*=", chunk):
            out.setdefault(m.group(1), "?")
        return out

    @staticmethod
    def _collect_immutable_vars(chunk: str) -> set[str]:
        return {
            match.group(1)
            for match in re.finditer(r"\blet\s+([A-Za-z_]\w*)\s*:", chunk)
        }

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
        if "class" not in source:
            return PrefixSemanticResult(ok=True)
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

    def _check_interface_completion_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        if not source.endswith(("}", "\n", "\r")):
            return PrefixSemanticResult(ok=True)
        completed = list(_iter_blocks(source, "class"))
        if not completed:
            return PrefixSemanticResult(ok=True)
        name, header, body = completed[-1]
        supers = _parse_supers(header)
        # A concrete superclass may provide the implementation.  Defer that
        # case to the complete typechecker rather than risking an early error.
        if any(_type_head(sup) in ctx.classes for sup in supers):
            return PrefixSemanticResult(ok=True)
        implemented = {
            match.group(1)
            for match in re.finditer(
                r"(?:public\s+|private\s+)?(?:static\s+)?func\s+([A-Za-z_]\w*)\s*(?:<[^>{}()\n]*>)?\s*\(",
                body,
            )
        }
        for super_type in supers:
            interface = ctx.interfaces.get(_type_head(super_type))
            if not interface:
                continue
            missing = set(interface.methods) - implemented
            if missing:
                method = sorted(missing)[0]
                return PrefixSemanticResult(False, f"class {name} does not implement {method}")
        return PrefixSemanticResult(ok=True)

    def _check_break_continue(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        stripped = _physical_line_tail(source)
        if not (re.search(r"\bbreak$", stripped) or re.search(r"\bcontinue$", stripped)):
            return PrefixSemanticResult(ok=True)
        if not _inside_loop(ctx.current_chunk):
            return PrefixSemanticResult(False, "break/continue outside loop")
        return PrefixSemanticResult(ok=True)

    def _check_init_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        """Check constructor-only rules while the constructor is still open."""

        if "init" not in source:
            return PrefixSemanticResult(ok=True)
        init_body = _last_open_init_body(source)
        if init_body is None:
            return PrefixSemanticResult(ok=True)

        # Constructors have Unit result and therefore only permit a bare
        # return.  Once a non-whitespace character follows ``return`` this
        # cannot be repaired by extending the current lexeme.
        returned = re.search(r"(?:^|[;{}\n])\s*return\s+([^;{}\n]+)$", init_body.rstrip())
        if returned and returned.group(1).strip():
            return PrefixSemanticResult(False, "init cannot return a value")

        delegated = re.search(r"(?:^|[;{}\n])\s*this\s*\((.*)\)\s*;?\s*$", init_body, re.S)
        if not delegated:
            return PrefixSemanticResult(ok=True)
        open_class = _last_open_class_details(source)
        if not open_class:
            return PrefixSemanticResult(ok=True)
        class_name, type_params, _supers, class_body = open_class
        signatures = _constructor_signatures_from_body(class_name, type_params, class_body)
        if not signatures:
            return PrefixSemanticResult(ok=True)
        args = [part.strip() for part in _split_top_level(delegated.group(1), ",")]
        if len(args) == 1 and not args[0]:
            args = []
        failures: list[str] = []
        for sig in signatures:
            matched, message = self._signature_accepts(sig, args, [], None, ctx)
            if matched:
                return PrefixSemanticResult(ok=True)
            failures.append(message)
        return PrefixSemanticResult(False, failures[0] if failures else "no matching delegated constructor")

    def _check_this_member_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        if "init" not in source or "this" not in source:
            return PrefixSemanticResult(ok=True)
        init_body = _last_open_init_body(source)
        open_class = _last_open_class_details(source)
        if init_body is None or not open_class:
            return PrefixSemanticResult(ok=True)
        _name, _type_params, _supers, class_body = open_class
        match = re.search(r"\bthis\s*\.\s*([A-Za-z_]\w*)$", init_body.rstrip())
        if not match:
            return PrefixSemanticResult(ok=True)
        prefix = match.group(1)
        members = {
            member_name
            for item in re.finditer(
                r"\b(?:let|var)\s+([A-Za-z_]\w*)\s*:\s*|\bfunc\s+([A-Za-z_]\w*)\s*\(",
                class_body,
            )
            for member_name in item.groups()
            if member_name
        }
        if members and any(name.startswith(prefix) for name in members):
            return PrefixSemanticResult(ok=True)
        return PrefixSemanticResult(False, f"no member {prefix} on this")

    def _check_condition_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        m = re.search(r"\b(if|while)\s*\(([^()\n{}]*)\)\s*$", _physical_line_tail(source))
        if not m:
            return PrefixSemanticResult(ok=True)
        ty = self._expr_type(m.group(2), ctx)
        if ty and ty != "Bool":
            return PrefixSemanticResult(False, f"{m.group(1)} condition must be Bool")
        return PrefixSemanticResult(ok=True)

    def _check_if_join_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        if "else" not in source or not source.rstrip().endswith("}"):
            return PrefixSemanticResult(ok=True)
        matches = list(re.finditer(
            r"\bif\s*\([^{}]*\)\s*\{\s*([^{}]*?)\s*\}"
            r"\s*else\s*\{\s*([^{}]*?)\s*\}",
            source,
            re.S,
        ))
        if not matches:
            return PrefixSemanticResult(ok=True)
        match = matches[-1]
        left_expr = _last_block_value(match.group(1))
        right_expr = _last_block_value(match.group(2))
        if not left_expr or not right_expr:
            return PrefixSemanticResult(ok=True)
        left_type = self._expr_type(left_expr, ctx)
        right_type = self._expr_type(right_expr, ctx)
        if (
            left_type
            and right_type
            and not left_type.startswith("unknown:")
            and not right_type.startswith("unknown:")
            and left_type != "?"
            and right_type != "?"
            and not _types_have_join(left_type, right_type, ctx)
        ):
            return PrefixSemanticResult(
                False,
                f"if branch types cannot be joined: {left_type}, {right_type}",
            )
        return PrefixSemanticResult(ok=True)

    def _check_for_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        m = re.search(r"\bfor\s*\(\s*([A-Za-z_]\w*)\s+in\s+([^()\n{}]*)$", _physical_line_tail(source))
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
        left, remainder = expr.split("..", 1)
        left = left.strip()
        remainder = remainder.lstrip("=").strip()
        endpoint, separator, step = remainder.partition(":")
        left_ty = self._expr_type(left, ctx) if left else None
        if left_ty and left_ty not in (_INTEGER_TYPES | {"Rune"}):
            return PrefixSemanticResult(False, "range endpoint must be integral")
        right_ty = self._expr_type(endpoint.strip(), ctx) if endpoint.strip() else None
        right_committed = _range_part_committed(endpoint.strip(), right_ty, ctx)
        if right_ty and right_ty not in (_INTEGER_TYPES | {"Rune"}) and right_committed:
            return PrefixSemanticResult(False, "range endpoint must be integral")
        if left_ty and right_ty and right_committed and not _same_type(left_ty, right_ty):
            return PrefixSemanticResult(False, "range endpoints must share integral family")
        step_ty = self._expr_type(step.strip(), ctx) if separator and step.strip() else None
        step_committed = _range_part_committed(step.strip(), step_ty, ctx)
        if step_ty and step_ty not in (_INTEGER_TYPES | {"Rune"}) and step_committed:
            return PrefixSemanticResult(False, "range step must be integral")
        if step_ty and left_ty and step_committed and not _same_type(step_ty, left_ty):
            return PrefixSemanticResult(False, "range step must share integral family")
        return PrefixSemanticResult(ok=True)

    def _check_generic_arity_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        m = re.search(r"\b([A-Za-z_]\w*)\s*<([^<>(){}\n]*)$", _physical_line_tail(source))
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
        stripped = _physical_line_tail(source)
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
        if "." in callee:
            base, member = callee.rsplit(".", 1)
            sig = _member_call_sig(
                self._expr_type(base, ctx),
                member.split("<", 1)[0].strip(),
                ctx,
            )
        else:
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
            if _is_tparam(want, ctx):
                prev = inferred.get(want)
                if prev and not _same_type(prev, aty):
                    return PrefixSemanticResult(False, "conflicting generic inference")
                inferred[want] = aty
                continue
            if not _compatible(aty, want, ctx):
                return PrefixSemanticResult(False, f"expected {want}, got {aty}")
        return PrefixSemanticResult(ok=True)

    def _check_member_and_index_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        stripped = _physical_line_tail(source)
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
            class_info = ctx.classes.get(_nominal_name(base_ty) or "")
            if class_info and class_info.name not in _BUILTIN_NOMINALS:
                is_type_receiver = bool(base_ty and base_ty.startswith("type:"))
                allowed = (
                    set(class_info.static_fields) | set(class_info.static_methods)
                    if is_type_receiver
                    else set(class_info.fields) | set(class_info.methods)
                )
                if not any(name.startswith(member) for name in allowed):
                    return PrefixSemanticResult(False, f"no member {member} on {base_ty}")
            if base_ty and not _member_prefix_valid(base_ty, member):
                return PrefixSemanticResult(False, f"no member {member} on {base_ty}")
        return PrefixSemanticResult(ok=True)

    def _check_var_assignment_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        line = self._active_line(source)
        generic = re.match(
            r"(?:let|var)\s+([A-Za-z_]\w*)(?:\s*:\s*([^=]+?))?\s*=\s*(.+)$",
            line,
            re.S,
        )
        if not generic:
            declaration = _active_variable_declaration(ctx.current_chunk)
            if declaration:
                line = declaration
                generic = re.match(
                    r"(?:let|var)\s+([A-Za-z_]\w*)(?:\s*:\s*([^=]+?))?\s*=\s*(.+)$",
                    line,
                    re.S,
                )
        if not generic:
            return PrefixSemanticResult(ok=True)
        undefined = _first_undefined_value_name(generic.group(3).strip(), ctx)
        if undefined:
            return PrefixSemanticResult(False, f"undefined identifier {undefined}")
        if generic.group(2) is None:
            return PrefixSemanticResult(ok=True)
        m = generic
        want = _norm_type(m.group(2))
        expr = m.group(3).strip()
        if source.endswith(("\n", "\r", ";", "}")) and _function_type_parts(want):
            member_ref = re.fullmatch(r"(.+)\.([A-Za-z_]\w*)", expr, re.S)
            if member_ref:
                base_ty = self._expr_type(member_ref.group(1), ctx)
                class_info = ctx.classes.get(_nominal_name(base_ty) or "")
                if class_info:
                    overloads = (
                        class_info.static_method_overloads
                        if base_ty and base_ty.startswith("type:")
                        else class_info.method_overloads
                    )
                    if len(overloads.get(member_ref.group(2), ())) > 1:
                        return PrefixSemanticResult(
                            False,
                            f"ambiguous overloaded member reference {member_ref.group(2)}",
                        )
        result = self._check_expr_against(expr, want, ctx)
        if not result.ok:
            return result
        got = self._expr_type(expr, ctx)
        if got and got.startswith("unknown:"):
            return PrefixSemanticResult(False, f"undefined identifier {got.split(':', 1)[1]}")
        if got == "?":
            return PrefixSemanticResult(ok=True)
        if got and _defer_var_rhs_mismatch(expr, got, want, source.endswith(("\n", "\r", ";"))):
            return PrefixSemanticResult(ok=True)
        if got and _parse_completed_call(expr) and _is_tparam(got, ctx):
            return PrefixSemanticResult(ok=True)
        if got and not _expr_compatible(got, want, expr, ctx):
            return PrefixSemanticResult(False, f"expected {want}, got {got}")
        return PrefixSemanticResult(ok=True)

    def _check_reassignment_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        if not source.endswith(_COMMIT_SUFFIXES):
            return PrefixSemanticResult(ok=True)
        line = self._active_line(source)
        match = re.match(r"([A-Za-z_]\w*)\s*=(?!=)\s*(.+)$", line)
        if not match:
            return PrefixSemanticResult(ok=True)
        name, expr = match.group(1), match.group(2).strip()
        if name in ctx.immutable_vars:
            return PrefixSemanticResult(False, f"cannot assign to immutable variable {name}")
        want = ctx.vars.get(name)
        if want:
            result = self._check_expr_against(expr, want, ctx)
            if not result.ok:
                return result
            got = self._expr_type(expr, ctx)
            if got and got.startswith("unknown:"):
                return PrefixSemanticResult(False, f"undefined identifier {got.split(':', 1)[1]}")
            if got == "?":
                return PrefixSemanticResult(ok=True)
            if got and not _compatible(got, want, ctx):
                return PrefixSemanticResult(False, f"expected {want}, got {got}")
        return PrefixSemanticResult(ok=True)

    def _check_committed_call_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        if not source.endswith(_COMMIT_SUFFIXES):
            return PrefixSemanticResult(ok=True)
        line = self._active_line(source)
        if not line:
            return PrefixSemanticResult(ok=True)
        declaration = re.match(
            r"(?:let|var)\s+[A-Za-z_]\w*(?:\s*:\s*([^=]+?))?\s*=\s*(.+)$",
            line,
            re.S,
        )
        if declaration:
            expected = _norm_type(declaration.group(1)) if declaration.group(1) else None
            return self._check_completed_call(
                declaration.group(2).strip(),
                ctx,
                expected_return=expected,
            )
        if line.startswith(("return ", "func ", "class ", "interface ")):
            return PrefixSemanticResult(ok=True)
        return self._check_completed_call(line, ctx)

    def _check_return_prefix(self, source: str, ctx: _Context) -> PrefixSemanticResult:
        if not ctx.current_ret or ctx.current_ret == "Unit":
            return PrefixSemanticResult(ok=True)
        line = self._active_line(source)
        if not line or line.startswith(("let ", "var ", "if ", "for ", "while ", "println")):
            return PrefixSemanticResult(ok=True)
        if line.startswith("return "):
            expr = line[len("return ") :].strip()
        else:
            expr = line
            # A completed non-final expression may legally be followed by the
            # function's actual result expression.  Only probe an implicit
            # return while the current atomic expression itself is being
            # formed; closing-brace validation remains the batch/fallback
            # layer's responsibility.
            if source.endswith(("\n", "\r", ";")) or not _is_atomic_literal_prefix(expr):
                return PrefixSemanticResult(ok=True)
        got = self._expr_type(expr, ctx)
        if got and got.startswith("unknown:"):
            return PrefixSemanticResult(False, f"undefined identifier {got.split(':', 1)[1]}")
        if got == "?":
            return PrefixSemanticResult(ok=True)
        ended = source.endswith(("\n", "\r", ";"))
        if got and _safe_final_expr_mismatch(expr, got, ctx.current_ret, ended) and not _compatible(got, ctx.current_ret, ctx):
            return PrefixSemanticResult(False, f"expected {ctx.current_ret}, got {got}")
        return PrefixSemanticResult(ok=True)

    def _check_expr_against(self, expr: str, want: str, ctx: _Context) -> PrefixSemanticResult:
        stripped_outer = _strip_outer(expr.strip())
        if stripped_outer != expr.strip():
            expr = stripped_outer
        if _looks_like_generic_construct_prefix(expr):
            return PrefixSemanticResult(ok=True)

        array_result = self._check_array_literal_against(expr, want, ctx)
        if not array_result.ok:
            return array_result

        undefined = _first_undefined_value_name(expr, ctx)
        if undefined:
            return PrefixSemanticResult(False, f"undefined identifier {undefined}")

        call_result = self._check_completed_call(expr, ctx, expected_return=want)
        if not call_result.ok:
            return call_result

        lambda_result = self._check_lambdas_in_call(expr, ctx)
        if not lambda_result.ok:
            return lambda_result

        member_call = _completed_member_call(expr)
        if member_call:
            base, member, arg_text = member_call
            base_ty = self._expr_type(base, ctx)
            sig = _member_call_sig(base_ty, member, ctx) if base_ty else None
            if sig:
                args = [a.strip() for a in _split_top_level(arg_text, ",") if a.strip()]
                if len(args) > len(sig.param_types):
                    return PrefixSemanticResult(False, "too many arguments")
                for idx, arg in enumerate(args):
                    aty = self._expr_type(arg, ctx)
                    if not aty or aty.startswith("unknown:") or idx >= len(sig.param_types):
                        continue
                    if not _compatible(aty, sig.param_types[idx], ctx):
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
            if lt and lt.startswith("unknown:"):
                lt = None
            if rt and rt.startswith("unknown:"):
                rt = None
            if op in {"%", "+", "-", "*", "/"}:
                string_concat = op == "+" and lt == "String"
                if lt and op == "%" and lt not in _INTEGER_TYPES:
                    return PrefixSemanticResult(False, f"'%' requires integral operands, got {lt}")
                if lt and op in {"+", "-", "*", "/"} and lt not in _SIGNED_NUMERIC and not string_concat:
                    return PrefixSemanticResult(False, f"arithmetic operator requires numeric operands, got {lt}")
                if rt:
                    if op == "%" and rt not in _INTEGER_TYPES:
                        return PrefixSemanticResult(False, f"'%' requires integral operands, got {rt}")
                    if string_concat and rt != "String":
                        return PrefixSemanticResult(False, "string concatenation requires String operands")
                    if op in {"+", "-", "*", "/"} and rt not in _SIGNED_NUMERIC and not string_concat:
                        return PrefixSemanticResult(False, f"arithmetic operator requires numeric operands, got {rt}")
                    if lt in _SIGNED_NUMERIC and rt in _SIGNED_NUMERIC and not _same_type(lt, rt):
                        return PrefixSemanticResult(False, "arithmetic operands must share numeric family")
            if op in {"&&", "||"}:
                if lt and lt != "Bool":
                    return PrefixSemanticResult(False, "logical operator requires Bool operands")
                if rt and rt != "Bool":
                    return PrefixSemanticResult(False, "logical operator requires Bool operands")
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
                if lt and lt not in (_INTEGER_TYPES | {"Rune"}):
                    return PrefixSemanticResult(False, "range endpoint must be integral")
                if rt and rt not in (_INTEGER_TYPES | {"Rune"}):
                    return PrefixSemanticResult(False, "range endpoint must be integral")

        got = self._expr_type(expr, ctx)
        if got and _type_head(got) == "interface-type":
            return PrefixSemanticResult(False, "interface cannot be used as a value")
        return PrefixSemanticResult(ok=True)

    def _check_array_literal_against(
        self,
        expr: str,
        want: str,
        ctx: _Context,
    ) -> PrefixSemanticResult:
        stripped = expr.strip()
        want_args = _type_args(want)
        if not stripped.startswith("[") or _type_head(want) != "Array" or not want_args:
            return PrefixSemanticResult(ok=True)
        inner = stripped[1:]
        if inner.endswith("]"):
            inner = inner[:-1]
        expected_element = want_args[0]
        elements = _split_top_level(inner, ",")
        for index, element in enumerate(elements):
            element = element.strip()
            if not element:
                continue
            actual = self._expr_type(element, ctx)
            if not actual or actual.startswith("unknown:"):
                continue
            committed = index < len(elements) - 1 or stripped.endswith("]")
            if not committed and _defer_var_rhs_mismatch(
                element,
                actual,
                expected_element,
                False,
            ):
                continue
            if not _expr_compatible(actual, expected_element, element, ctx):
                return PrefixSemanticResult(
                    False,
                    f"array element expects {expected_element}, got {actual}",
                )
        return PrefixSemanticResult(ok=True)

    def _check_completed_call(
        self,
        expr: str,
        ctx: _Context,
        *,
        expected_return: str | None = None,
    ) -> PrefixSemanticResult:
        parsed = _parse_completed_call(expr)
        if not parsed:
            return PrefixSemanticResult(ok=True)
        base_expr, name, explicit_args, arg_text = parsed
        signatures: list[FunctionSig] = []
        if base_expr is None:
            signatures.extend(ctx.funcs.get(name, ()))
            class_info = ctx.classes.get(name)
            if class_info:
                if class_info.constructor_sigs:
                    signatures.extend(class_info.constructor_sigs)
                elif class_info.constructors:
                    signatures.extend(
                        FunctionSig(
                            name,
                            class_info.type_params,
                            tuple(None for _ in params),
                            params,
                            (
                                f"{name}<{', '.join(explicit_args)}>"
                                if explicit_args
                                else name
                            ),
                        )
                        for params in class_info.constructors
                    )
                else:
                    signatures.append(
                        FunctionSig(name, class_info.type_params, (), (), name)
                    )
        else:
            base_ty = self._expr_type(base_expr, ctx)
            nominal = _nominal_name(base_ty)
            class_info = ctx.classes.get(nominal) if nominal else None
            if class_info:
                is_type_receiver = bool(base_ty and base_ty.startswith("type:"))
                overloads = (
                    class_info.static_method_overloads
                    if is_type_receiver
                    else class_info.method_overloads
                )
                methods = class_info.static_methods if is_type_receiver else class_info.methods
                signatures.extend(overloads.get(name, ()))
                if not signatures and name in methods:
                    signatures.append(methods[name])
            builtin_sig = _member_call_sig(base_ty, name, ctx)
            if builtin_sig and builtin_sig not in signatures:
                signatures.append(builtin_sig)

        if not signatures:
            return PrefixSemanticResult(ok=True)

        args = [part.strip() for part in _split_top_level(arg_text, ",")]
        if len(args) == 1 and not args[0]:
            args = []
        failures: list[str] = []
        for sig in signatures:
            matched, message = self._signature_accepts(
                sig,
                args,
                explicit_args,
                expected_return,
                ctx,
            )
            if matched:
                return PrefixSemanticResult(ok=True)
            failures.append(message)
        return PrefixSemanticResult(False, failures[0] if failures else "no matching call")

    def _signature_accepts(
        self,
        sig: FunctionSig,
        args: list[str],
        explicit_args: list[str],
        expected_return: str | None,
        ctx: _Context,
    ) -> tuple[bool, str]:
        required = sig.required_params if sig.required_params is not None else len(sig.param_types)
        if len(args) < required or len(args) > len(sig.param_types):
            return False, f"{sig.name} expects {required}..{len(sig.param_types)} argument(s), got {len(args)}"
        if explicit_args and len(explicit_args) != len(sig.type_params):
            return False, f"{sig.name} expects {len(sig.type_params)} type argument(s)"

        subst = _subst_from_explicit(sig, explicit_args)
        if expected_return:
            _bind_typevars(sig.ret, expected_return, set(sig.type_params), subst, ctx)

        positional = 0
        used: set[int] = set()
        for arg in args:
            named = re.match(r"^([A-Za-z_]\w*)\s*:\s*(.+)$", arg, re.S)
            if named:
                try:
                    index = list(sig.param_names).index(named.group(1))
                except ValueError:
                    return False, f"unknown named argument {named.group(1)}"
                arg_expr = named.group(2).strip()
            else:
                while positional in used:
                    positional += 1
                index = positional
                positional += 1
                arg_expr = arg
            if index >= len(sig.param_types) or index in used:
                return False, "invalid or duplicate argument"
            used.add(index)
            pattern = sig.param_types[index]

            if "=>" in arg_expr and _function_type_parts(pattern):
                _infer_lambda_typevars(
                    self,
                    arg_expr,
                    pattern,
                    set(sig.type_params),
                    subst,
                    ctx,
                )
                expected_fn = _apply_subst(pattern, subst)
                lambda_result = self._check_lambda_against(arg_expr, expected_fn, ctx)
                if not lambda_result.ok:
                    return False, lambda_result.message
                continue

            actual = self._expr_type(arg_expr, ctx)
            if not actual or actual.startswith("unknown:"):
                continue
            if _expr_compatible(actual, _apply_subst(pattern, subst), arg_expr, ctx):
                continue
            if not _bind_typevars(pattern, actual, set(sig.type_params), subst, ctx):
                want = _apply_subst(pattern, subst)
                return False, f"expected {want}, got {actual}"

        resolved_ret = _apply_subst(sig.ret, subst)
        if expected_return and not _contains_unbound_typevar(resolved_ret, set(sig.type_params), subst):
            if not _compatible(resolved_ret, expected_return, ctx):
                return False, f"expected {expected_return}, got {resolved_ret}"
        return True, ""

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
            if (
                got_ty
                and not _is_tparam(want_ty, ctx)
                and not _compatible(want_ty, got_ty, ctx)
            ):
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
        expr = expr.strip()
        if expr.startswith("(") and _matching_paren(expr, 0) == len(expr) - 1:
            tuple_parts = [part.strip() for part in _split_top_level(expr[1:-1], ",")]
            if len(tuple_parts) > 1:
                part_types = [self._expr_type(part, ctx) for part in tuple_parts]
                if all(part_types):
                    return f"({', '.join(part_types)})"
                return None
        expr = _strip_outer(expr)
        if not expr:
            return None
        if re.fullmatch(r"true|false", expr):
            return "Bool"
        integer = re.fullmatch(
            r"(?:0[xX][0-9A-Fa-f_]+|0[oO][0-7_]+|0[bB][01_]+|\d[\d_]*)"
            r"(?:i(8|16|32|64))?",
            expr,
        )
        if integer:
            return f"Int{integer.group(1)}" if integer.group(1) else "Int64"
        floating = re.fullmatch(
            r"(?:\d[\d_]*\.\d*|\d[\d_]*[eE][+\-]?\d[\d_]*)"
            r"(?:f(32|64))?",
            expr,
        )
        if floating:
            return f"Float{floating.group(1)}" if floating.group(1) else "Float64"
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
        if _looks_like_generic_construct_prefix(expr):
            return None
        binary = _find_tail_binary(expr)
        if binary and binary[2].strip():
            left, op, right = binary
            left_type = self._expr_type(left, ctx)
            right_type = self._expr_type(right, ctx)
            if op in {"==", "!=", "<", ">", "<=", ">=", "&&", "||"}:
                return "Bool" if left_type and right_type else None
            if op == "+" and left_type == right_type == "String":
                return "String"
            if op in {"+", "-", "*", "/", "%"} and left_type and _same_type(left_type, right_type or ""):
                return left_type
        array = re.fullmatch(r"\[(.*)\]", expr, re.S)
        if array:
            elements = [
                part.strip()
                for part in _split_top_level(array.group(1), ",")
                if part.strip()
            ]
            if not elements:
                return None
            element_type = self._expr_type(elements[0], ctx)
            if element_type:
                return f"Array<{element_type}>"
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
                explicit = _parse_type_arg_list(call.group(2) or "")
                return f"{name}<{', '.join(explicit)}>" if explicit else name
            sig = self._call_sig(name, ctx, _parse_type_arg_list(call.group(2) or ""))
            if sig:
                subst = _subst_from_explicit(sig, _parse_type_arg_list(call.group(2) or ""))
                return _apply_subst(sig.ret, subst)
        member_call = re.match(
            r"(.+)\.([A-Za-z_]\w*)(?:\s*<([^>(){}\n]*)>)?\s*\((.*)\)$",
            expr,
            re.S,
        )
        if member_call:
            base_ty = self._expr_type(member_call.group(1), ctx)
            member = member_call.group(2)
            sig = _member_call_sig(base_ty, member, ctx) if base_ty else None
            if sig:
                explicit = _parse_type_arg_list(member_call.group(3) or "")
                return _apply_subst(sig.ret, _subst_from_explicit(sig, explicit))
            if member == "toString":
                return "String"
            if member == "toArray" and base_ty and _type_head(base_ty) == "ArrayList":
                args = _type_args(base_ty)
                return f"Array<{args[0]}>" if args else "Array"
        member = re.match(r"(.+)\.([A-Za-z_]\w*)$", expr, re.S)
        if member:
            base_ty = self._expr_type(member.group(1), ctx)
            field = member.group(2)
            if base_ty:
                class_info = ctx.classes.get(_nominal_name(base_ty) or "")
                is_type_receiver = base_ty.startswith("type:")
                field_map = class_info.static_fields if class_info and is_type_receiver else class_info.fields if class_info else {}
                if class_info and field in field_map:
                    subst = {
                        name: value
                        for name, value in zip(class_info.type_params, _type_args(base_ty))
                    }
                    return _apply_subst(field_map[field], subst)
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


def _function_sig_from_context(entry: object) -> FunctionSig | None:
    if not isinstance(entry, dict) or not entry.get("name"):
        return None
    return FunctionSig(
        name=str(entry["name"]),
        type_params=tuple(str(item) for item in entry.get("type_params", []) if item),
        param_names=tuple(
            str(item) if item else None for item in entry.get("param_names", [])
        ),
        param_types=tuple(
            _norm_type(str(item)) if item else "" for item in entry.get("param_types", [])
        ),
        ret=_norm_type(str(entry.get("return_type") or "Unit")),
        required_params=(
            int(entry["required_params"])
            if entry.get("required_params") is not None
            else None
        ),
    )


def _parse_completed_call(
    expr: str,
) -> tuple[str | None, str, list[str], str] | None:
    text = _strip_outer(expr.strip())
    if not text.endswith(")"):
        return None
    stack: list[int] = []
    quote: str | None = None
    escaped = False
    outer_open: int | None = None
    for index, ch in enumerate(text):
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
        elif ch == "(":
            stack.append(index)
        elif ch == ")":
            if not stack:
                return None
            opening = stack.pop()
            if index == len(text) - 1:
                outer_open = opening
    if outer_open is None:
        return None
    callee = text[:outer_open].strip()
    match = re.fullmatch(
        r"(?:(?P<base>.+)\.)?(?P<name>[A-Za-z_]\w*)(?:\s*<(?P<targs>.*)>)?",
        callee,
        re.S,
    )
    if not match:
        return None
    return (
        match.group("base").strip() if match.group("base") else None,
        match.group("name"),
        _parse_type_arg_list(match.group("targs") or ""),
        text[outer_open + 1 : -1],
    )


def _nominal_name(ty: str | None) -> str | None:
    if not ty:
        return None
    if ty.startswith("type:") or ty.startswith("interface-type:"):
        return ty.split(":", 1)[1]
    return _type_head(ty)


def _bind_typevars(
    pattern: str,
    actual: str,
    type_params: set[str],
    subst: dict[str, str],
    ctx: _Context | None = None,
) -> bool:
    pattern = _norm_type(pattern)
    actual = _norm_type(actual)
    if pattern in type_params:
        previous = subst.get(pattern)
        if previous is None:
            subst[pattern] = actual
            return True
        return _same_type(previous, actual)

    resolved = _apply_subst(pattern, subst)
    pattern_fn = _function_type_parts(resolved)
    actual_fn = _function_type_parts(actual)
    if pattern_fn and actual_fn:
        if len(pattern_fn[0]) != len(actual_fn[0]):
            return False
        return all(
            _bind_typevars(left, right, type_params, subst, ctx)
            for left, right in zip(pattern_fn[0], actual_fn[0])
        ) and _bind_typevars(pattern_fn[1], actual_fn[1], type_params, subst, ctx)

    pattern_args = _type_args(resolved)
    actual_args = _type_args(actual)
    if pattern_args or actual_args:
        if _type_head(resolved) != _type_head(actual):
            return False
        # A raw nominal type deliberately erases its generic arguments.  It
        # can accept a specialised value of the same nominal type, but two
        # concrete specialisations still have to unify argument-by-argument.
        if not pattern_args or not actual_args:
            return True
        if len(pattern_args) != len(actual_args):
            return False
        return all(
            _bind_typevars(left, right, type_params, subst, ctx)
            for left, right in zip(pattern_args, actual_args)
        )
    return _compatible(actual, resolved, ctx)


def _infer_lambda_typevars(
    checker: PrefixSemanticChecker,
    expr: str,
    expected_pattern: str,
    type_params: set[str],
    subst: dict[str, str],
    ctx: _Context,
) -> None:
    parsed = _parse_lambda_expr(expr)
    expected = _function_type_parts(expected_pattern)
    if not parsed or not expected:
        return
    params, body = parsed
    expected_params, expected_ret = expected
    local = _ctx_with_lambda_params(
        ctx,
        params,
        [_apply_subst(item, subst) for item in expected_params],
    )
    body_type = checker._expr_type(_strip_lambda_body_expr(body), local)
    if body_type:
        _bind_typevars(expected_ret, body_type, type_params, subst, ctx)


def _contains_unbound_typevar(
    ty: str,
    type_params: set[str],
    subst: dict[str, str],
) -> bool:
    return any(
        name not in subst and re.search(rf"\b{re.escape(name)}\b", ty)
        for name in type_params
    )


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


def _first_unknown_type(types: list[str], known: set[str]) -> str | None:
    for declared in types:
        for name in re.findall(r"[A-Za-z_]\w*", declared):
            if name not in known and not any(item.startswith(name) for item in known):
                return name
    return None


def _last_block_value(body: str) -> str | None:
    candidates = [
        part.strip()
        for part in re.split(r"[;\r\n]+", body)
        if part.strip()
    ]
    if not candidates:
        return None
    value = candidates[-1]
    if value.startswith(("let ", "var ", "return ")):
        return None
    return value


def _types_have_join(left: str, right: str, ctx: _Context) -> bool:
    if _compatible(left, right, ctx) or _compatible(right, left, ctx):
        return True

    def ancestors(start: str) -> set[str]:
        reached: set[str] = set()
        pending = [start]
        while pending:
            current = pending.pop()
            if current in reached:
                continue
            reached.add(current)
            head = _type_head(current)
            nominal = ctx.classes.get(head)
            type_params = nominal.type_params if nominal else ()
            supers = nominal.supers if nominal else ()
            if not nominal:
                interface = ctx.interfaces.get(head)
                type_params = interface.type_params if interface else ()
                supers = interface.supers if interface else ()
            subst = {
                name: value
                for name, value in zip(type_params, _type_args(current))
            }
            pending.extend(_apply_subst(item, subst) for item in supers)
        return reached

    return bool(ancestors(left) & ancestors(right))


def _compatible(got: str, want: str, ctx: _Context | None = None) -> bool:
    if got.startswith("unknown:"):
        return False
    if got.startswith("type:") or got.startswith("interface-type:"):
        return False
    if _same_type(got, want):
        return True
    # The competition subset accepts an unspecialised nominal annotation as
    # the raw form of the same generic class (for example ``Box`` as a
    # parameter receiving ``Box<Int64>``).  Keep this deliberately narrower
    # than general covariance: differently specialised concrete types still
    # do not match.
    if (
        _type_head(got) == _type_head(want)
        and (not _type_args(got) or not _type_args(want))
    ):
        return True
    if ctx is None:
        return False

    # Precompute the nominal reachability demanded by the challenge context.
    # Type arguments are substituted along each inheritance edge, so an
    # ArrayList<Int64> can reach Collection<Int64> without making unrelated
    # specialisations covariant.
    pending = [got]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        normalized = _norm_type(current)
        if normalized in seen:
            continue
        seen.add(normalized)
        if _same_type(normalized, want):
            return True
        current_head = _type_head(normalized)
        nominal = ctx.classes.get(current_head)
        type_params: tuple[str, ...] = ()
        supers: tuple[str, ...] = ()
        if nominal:
            type_params = nominal.type_params
            supers = nominal.supers
        else:
            interface = ctx.interfaces.get(current_head)
            if interface:
                type_params = interface.type_params
                supers = interface.supers
        subst = {
            name: value
            for name, value in zip(type_params, _type_args(normalized))
        }
        for super_type in supers:
            reached = _apply_subst(super_type, subst)
            if _same_type(reached, want):
                return True
            if (
                _type_head(reached) == _type_head(want)
                and (not _type_args(reached) or not _type_args(want))
            ):
                return True
            pending.append(reached)
    return False


def _expr_compatible(
    got: str,
    want: str,
    expr: str,
    ctx: _Context | None = None,
) -> bool:
    if got == "String" and want == "Rune":
        return _string_literal_scalar_count(expr) == 1
    return _compatible(got, want, ctx)


def _string_literal_scalar_count(expr: str) -> int | None:
    text = expr.strip()
    if len(text) < 2 or not text.startswith('"') or not text.endswith('"'):
        return None
    content = text[1:-1]
    count = 0
    index = 0
    while index < len(content):
        if content[index] == "\\":
            index += 1
            if index >= len(content):
                return None
            if content[index] == "u" and index + 1 < len(content) and content[index + 1] == "{":
                closing = content.find("}", index + 2)
                if closing < 0:
                    return None
                index = closing + 1
            else:
                index += 1
        else:
            index += 1
        count += 1
    return count


def _is_tparam(ty: str, ctx: _Context | None = None) -> bool:
    if not bool(re.fullmatch(r"[A-Z]\w*", ty)) or ty in _PRIMS:
        return False
    if ctx and (_type_head(ty) in ctx.classes or _type_head(ty) in ctx.interfaces):
        return False
    return True


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
    immutable = set(ctx.immutable_vars) | param_names
    return _Context(
        ctx.funcs,
        ctx.interfaces,
        ctx.classes,
        vars_,
        param_names,
        ctx.current_ret,
        ctx.current_chunk,
        immutable,
    )


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


def _last_open_class_details(
    source: str,
) -> tuple[str, tuple[str, ...], tuple[str, ...], str] | None:
    """Return the innermost source class whose closing brace is not present."""

    pattern = re.compile(
        r"\bclass\s+([A-Za-z_]\w*)\s*(<[^\n{}]*>)?([^\n{}]*)\{"
    )
    out = None
    for match in pattern.finditer(source):
        opening = source.find("{", match.start(), match.end())
        if opening < 0 or _matching_brace(source, opening) is not None:
            continue
        type_params = _parse_type_params(match.group(2) or "")
        header = (match.group(2) or "") + (match.group(3) or "")
        out = (
            match.group(1),
            type_params,
            _parse_supers(header),
            source[opening + 1 :],
        )
    return out


def _last_open_init_body(source: str) -> str | None:
    out = None
    for match in re.finditer(r"\binit\s*\([^{};\n]*\)\s*\{", source):
        opening = source.find("{", match.start(), match.end())
        if opening >= 0 and _matching_brace(source, opening) is None:
            out = source[opening + 1 :]
    return out


def _constructor_signatures_from_body(
    class_name: str,
    type_params: tuple[str, ...],
    body: str,
) -> list[FunctionSig]:
    signatures: list[FunctionSig] = []
    for match in re.finditer(r"\binit\s*\(([^{};\n]*)\)", body):
        names, types = _parse_params(match.group(1))
        signatures.append(
            FunctionSig(
                class_name,
                type_params,
                tuple(names),
                tuple(types),
                class_name,
            )
        )
    return signatures


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


def _collect_open_for_bindings(
    chunk: str,
    variables: dict[str, str],
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    pattern = re.compile(
        r"\bfor\s*\(\s*([A-Za-z_]\w*)\s+in\s+([^()\n{}]+)\)\s*\{"
    )
    for match in pattern.finditer(chunk):
        opening = chunk.find("{", match.start(), match.end())
        if opening < 0 or _matching_brace(chunk, opening) is not None:
            continue
        iterable = match.group(2).strip()
        element = "?"
        if ".." in iterable:
            left = iterable.split("..", 1)[0].strip()
            element = variables.get(left, "Int64")
            if element not in (_INTEGER_TYPES | {"Rune"}):
                element = "Int64"
        else:
            iterable_type = variables.get(iterable, "")
            args = _type_args(iterable_type)
            if _type_head(iterable_type) == "HashMap" and len(args) >= 2:
                element = f"({args[0]}, {args[1]})"
            elif args:
                element = args[0]
            elif iterable_type == "String":
                element = "Rune"
        bindings[match.group(1)] = element
    return bindings


def _after_last(source: str, marker: str) -> str:
    idx = source.rfind(marker)
    return source[idx + len(marker) :] if idx >= 0 else ""


def _physical_line_tail(source: str) -> str:
    """Return only the current physical line for tail-anchored probes."""

    return source[source.rfind("\n") + 1 :].rstrip()


def _active_or_committed_line(source: str) -> str:
    """Return the current statement, including compact one-line programs.

    Semantic errors in the public protocol commonly become irrevocable on the
    token that contains the trailing newline.  Looking strictly after the last
    newline inspected an empty string, while looking only at lines missed
    semicolon-separated programs.  Track boundaries at each brace depth and
    ignore boundaries nested in calls, arrays, strings, and comments.
    """

    # A right brace can close a nested lambda while its surrounding call is
    # still incomplete.  In that situation the physical line remains the
    # active statement and must not be reconstructed as a committed top-level
    # statement.  Newlines and semicolons are the actual statement commits.
    if source and not source.endswith(("\n", "\r", ";")):
        return source[source.rfind("\n") + 1 :].strip()

    end = len(source)
    while end > 0 and source[end - 1] in "\r\n;":
        end -= 1
    brace = paren = bracket = 0
    last_boundary: dict[int, int] = {0: 0}
    state = "code"
    quote = ""
    escaped = False
    i = 0
    while i < end:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < end else ""
        if state == "line_comment":
            if ch in "\r\n":
                state = "code"
                if paren == 0 and bracket == 0:
                    last_boundary[brace] = i + 1
            i += 1
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 2
            else:
                i += 1
            continue
        if state == "string":
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                state = "code"
            i += 1
            continue
        if ch == "/" and nxt == "/":
            state = "line_comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            state = "block_comment"
            i += 2
            continue
        if ch in {'"', "'"}:
            state = "string"
            quote = ch
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
            if paren == 0 and bracket == 0:
                last_boundary[brace] = i + 1
        elif ch == "}" and brace:
            brace -= 1
            if paren == 0 and bracket == 0:
                # A brace followed by a statement/call delimiter belongs to
                # an expression (most notably a lambda or block expression),
                # so it must not erase the beginning of that statement.
                following = source[i + 1 :].lstrip()[:1]
                if following not in {";", ",", ")", "]", "}"}:
                    last_boundary[brace] = i + 1
        elif ch in ";\r\n" and paren == 0 and bracket == 0:
            last_boundary[brace] = i + 1
        i += 1
    start = last_boundary.get(brace, 0)
    return source[start:end].strip()


def _active_variable_declaration(chunk: str) -> str | None:
    """Extract the last variable declaration if its statement is still active.

    This is intentionally a small delimiter scanner instead of a ``.*``
    regular expression: lambda and block-expression braces may occur in the
    initializer and semicolons inside them do not finish the declaration.
    """

    starts = list(re.finditer(r"\b(?:let|var)\s+[A-Za-z_]\w*\s*(?::[^=;{}\n]+)?=", chunk))
    if not starts:
        return None
    start = starts[-1].start()
    tail = chunk[start:]
    paren = bracket = brace = 0
    quote: str | None = None
    escaped = False
    for index, ch in enumerate(tail):
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
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
        elif ch in ";\r\n" and not (paren or bracket or brace):
            following = tail[index + 1 :].strip()
            if following and following.strip("}").strip():
                return None
            return tail[:index].strip()
        elif ch == "}" and not (paren or bracket or brace):
            following = tail[index + 1 :].strip()
            if not following or not following.strip("}").strip():
                return tail[:index].strip()
    return tail.strip()


_VALUE_KEYWORDS = _KEYWORD_PREFIXES | {
    "as", "case", "catch", "do", "finally", "in", "init", "is",
    "main", "match", "package", "import", "super", "this", "throw",
    "try", "where", "true", "false",
}


def _first_undefined_value_name(expr: str, ctx: _Context) -> str | None:
    """Conservatively resolve names inside lambda and block expressions.

    A trailing identifier is treated as a partial lexeme and is rejected only
    when no visible symbol can complete it.  Interior identifiers are already
    stable and therefore require an exact visible declaration.
    """

    stripped_expr = expr.strip()
    if (
        stripped_expr.startswith("{")
        and "=>" not in stripped_expr
        and re.fullmatch(r"\{\s*[A-Za-z_][\w\s,:<>]*", stripped_expr)
    ):
        # Until an operator or fat arrow arrives this is a viable lambda
        # parameter list.  Treating its first identifier as a block-expression
        # lookup would reject every untyped lambda one token too early.
        return None
    masked = list(expr)
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(masked):
        ch = masked[index]
        if quote is not None:
            masked[index] = " "
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            index += 1
            continue
        if ch in {'"', "'"}:
            quote = ch
            masked[index] = " "
        elif ch == "/" and index + 1 < len(masked) and masked[index + 1] == "/":
            while index < len(masked) and masked[index] not in "\r\n":
                masked[index] = " "
                index += 1
            continue
        index += 1
    text = "".join(masked)
    lambda_params: set[str] = set()
    for header in re.finditer(r"\{\s*([^{}]*?)=>", text, re.S):
        for part in _split_top_level(header.group(1), ","):
            name = _leading_ident(part.strip())
            if name:
                lambda_params.add(name)
    possible_header = text[text.rfind("{") + 1 :].strip()
    if possible_header and re.fullmatch(r"[A-Za-z_][\w\s,:<>]*", possible_header):
        for part in _split_top_level(possible_header, ","):
            name = _leading_ident(part.strip())
            if name:
                lambda_params.add(name)

    symbols = (
        set(ctx.vars)
        | set(ctx.funcs)
        | set(ctx.classes)
        | set(ctx.interfaces)
        | lambda_params
        | _PRIMS
        | _BUILTIN_NOMINALS
    )
    stripped_end = len(text.rstrip())
    for match in re.finditer(r"[A-Za-z_]\w*", text):
        name = match.group(0)
        if match.start() > 0 and text[match.start() - 1].isalnum():
            # Numeric literal suffix, e.g. the ``i32`` in ``1i32``.
            continue
        if name in _VALUE_KEYWORDS or name == "_" or name[0].isupper():
            continue
        before = text[: match.start()].rstrip()
        after = text[match.end() :].lstrip()
        if before.endswith(".") or after.startswith(":"):
            continue
        if name in symbols:
            continue
        if match.end() == stripped_end and text.count("(") > text.count(")"):
            # At this point the identifier can still become a named argument
            # once ':' arrives.  Call-prefix validation checks it against the
            # actual parameter names after that delimiter is committed.
            continue
        if match.end() == stripped_end and any(symbol.startswith(name) for symbol in symbols):
            continue
        return name
    return None


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
    for op in ("&&", "||", "==", "!=", "<=", ">=", "..=", "..", "%", "+", "-", "*", "/", "<", ">"):
        idx = _find_top_level_op(expr, op)
        if idx >= 0:
            return expr[:idx].strip(), op, expr[idx + len(op) :].strip()
    return None


def _find_top_level_op(expr: str, op: str) -> int:
    paren = bracket = brace = 0
    quote: str | None = None
    escaped = False
    found = -1
    i = 0
    while i <= len(expr) - len(op):
        ch = expr[i]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in {'"', "'"}:
            quote = ch
            i += 1
            continue
        if ch == "(":
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
        if not (paren or bracket or brace) and expr.startswith(op, i):
            if op in {"+", "-"} and i == 0:
                i += 1
                continue
            if op == "<" and _generic_angle_starts_at(expr, i):
                i += 1
                continue
            if op == ">" and _generic_angle_ends_at(expr, i):
                i += 1
                continue
            found = i
        i += 1
    if found >= 0:
        return found
    return -1


def _generic_angle_starts_at(expr: str, index: int) -> bool:
    if index <= 0 or not (expr[index - 1].isalnum() or expr[index - 1] == "_"):
        return False
    depth = 0
    for pos in range(index, len(expr)):
        if expr[pos] == "<":
            depth += 1
        elif expr[pos] == ">":
            depth -= 1
            if depth == 0:
                return expr[pos + 1 :].lstrip().startswith("(")
    return False


def _generic_angle_ends_at(expr: str, index: int) -> bool:
    if not expr[index + 1 :].lstrip().startswith("("):
        return False
    depth = 0
    for pos in range(index, -1, -1):
        if expr[pos] == ">":
            depth += 1
        elif expr[pos] == "<":
            depth -= 1
            if depth == 0:
                return pos > 0 and (expr[pos - 1].isalnum() or expr[pos - 1] == "_")
    return False


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
    if got in _SIGNED_NUMERIC and want not in _SIGNED_NUMERIC:
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


def _range_part_committed(
    expr: str,
    ty: str | None,
    ctx: _Context,
) -> bool:
    if not expr or ty is None:
        return False
    if not re.fullmatch(r"[A-Za-z_]\w*", expr):
        return True
    head = _type_head(ty)
    if head in {"Array", "ArrayList", "HashMap", "HashSet", "String"}:
        return False
    class_info = ctx.classes.get(head)
    if class_info and (
        any(value in _INTEGER_TYPES for value in class_info.fields.values())
        or any(sig.ret in _INTEGER_TYPES for sig in class_info.methods.values())
    ):
        return False
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


def _member_call_sig(
    base_ty: str | None,
    member: str,
    ctx: _Context | None = None,
) -> FunctionSig | None:
    if not base_ty:
        return None
    head = _type_head(base_ty)
    nominal = _nominal_name(base_ty) or head
    args = _type_args(base_ty)
    if ctx:
        class_info = ctx.classes.get(nominal)
        is_type_receiver = base_ty.startswith("type:")
        methods = (
            class_info.static_methods
            if class_info and is_type_receiver
            else class_info.methods if class_info else {}
        )
        if class_info and member in methods:
            sig = methods[member]
            subst = {
                name: value
                for name, value in zip(class_info.type_params, args)
            }
            return FunctionSig(
                sig.name,
                sig.type_params,
                sig.param_names,
                tuple(_apply_subst(item, subst) for item in sig.param_types),
                _apply_subst(sig.ret, subst),
            )
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
        if member in {"add", "addIfAbsent"}:
            ret = "Bool" if member == "addIfAbsent" else "Unit"
            return FunctionSig(member, (), (None, None), (key, val), ret)
        if member in {"contains", "remove", "get"}:
            ret = val if member == "get" else "Bool"
            return FunctionSig(member, (), (None,), (key,), ret)
    return None
