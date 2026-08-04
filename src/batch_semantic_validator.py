"""Batch semantic validation using the official public Cangjie typechecker."""

from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SemanticDiagnostic:
    code: str
    phase: str
    message: str
    line: int | None = None
    column: int | None = None
    offset: int | None = None


@dataclass(frozen=True)
class SemanticValidationResult:
    ok: bool
    diagnostic: SemanticDiagnostic | None = None
    attempted_parse: bool = False


@dataclass(frozen=True)
class _Candidate:
    source: str
    artificial_start: int
    has_artificial_suffix: bool
    inserted_placeholder: bool
    trusted_comma_call: bool


class BatchSemanticValidator:
    """Validate stabilized source prefixes with the vendored typechecker."""

    def __init__(self, *, context_path: str | None = None) -> None:
        self._root = Path(__file__).resolve().parents[1]
        self._vendor_root = self._root / "third_party" / "cangjie_typechecker"
        vendor_str = str(self._vendor_root)
        if vendor_str not in sys.path:
            sys.path.insert(0, vendor_str)

        self._context_path = Path(context_path).resolve() if context_path else None
        self._configure_context()

        self._parser = importlib.import_module("typechecker.parser")
        self._checker = importlib.import_module("typechecker.checker")
        self._errors = importlib.import_module("typechecker.errors")

    def validate_prefix(self, source: str) -> SemanticValidationResult:
        if not source.strip():
            return SemanticValidationResult(ok=True)

        real_len = len(source)
        real_diagnostics: list[SemanticDiagnostic] = []
        attempted_parse = False

        for candidate in self._candidates(source):
            try:
                tree = self._parser.parse(candidate.source)
            except (
                self._parser.UnexpectedCharacters,
                self._parser.UnexpectedEOF,
                self._parser.UnexpectedToken,
            ):
                continue

            attempted_parse = True
            try:
                self._checker.typecheck_tree(tree)
            except self._errors.TypeCheckError as exc:
                diag = self._diagnostic_from_type_error(exc, candidate.source)
                if self._is_artificial_diagnostic(
                    diag,
                    candidate.artificial_start,
                    candidate.has_artificial_suffix,
                    candidate.inserted_placeholder,
                    candidate.trusted_comma_call,
                ):
                    continue
                real_diagnostics.append(diag)
                continue

            return SemanticValidationResult(ok=True, attempted_parse=True)

        if real_diagnostics:
            return SemanticValidationResult(ok=False, diagnostic=real_diagnostics[0], attempted_parse=attempted_parse)
        return SemanticValidationResult(ok=True, attempted_parse=attempted_parse)

    def _configure_context(self) -> None:
        if self._context_path is None:
            return
        try:
            builtin_context = importlib.import_module("typechecker.builtin_context")
        except Exception:
            return
        builtin_context._CONTEXT_PATH = self._context_path
        if hasattr(builtin_context, "_raw_context"):
            builtin_context._raw_context.cache_clear()
        builtin_context._builtin_ctx_singleton = None

    def _diagnostic_from_type_error(self, exc: Exception, source: str) -> SemanticDiagnostic:
        raw = getattr(exc, "diagnostic", None)
        line = getattr(raw, "line", None)
        column = getattr(raw, "column", None)
        offset = _line_col_to_offset(source, line, column)
        return SemanticDiagnostic(
            code=str(getattr(raw, "code", "E_TYPECHECK")),
            phase=str(getattr(raw, "phase", "check")),
            message=str(getattr(raw, "message", str(exc))),
            line=line,
            column=column,
            offset=offset,
        )

    @staticmethod
    def _is_artificial_diagnostic(
        diag: SemanticDiagnostic,
        artificial_start: int,
        has_artificial_suffix: bool,
        inserted_placeholder: bool,
        trusted_comma_call: bool,
    ) -> bool:
        if diag.offset is None:
            if not has_artificial_suffix:
                return False
            if inserted_placeholder:
                if (
                    trusted_comma_call
                    and diag.code == "E_CHECK_NO_MATCHING_CTOR"
                    and "E_SUBTYPE_MISMATCH" in diag.message
                ):
                    return False
                return True
            if diag.code in {"E_DECL_INTERFACE_METHOD_MISSING", "E_DECL_INTERFACE_METHOD_MISMATCH"}:
                return True
            message = diag.message
            return "got Unit" in message or "expected Unit, got" in message
        return diag.offset >= artificial_start

    def _candidates(self, source: str) -> Iterable[_Candidate]:
        closers = _missing_closers(source)
        closes_expression_tail = ")" in closers or "]" in closers
        trusted_comma_call = _is_trusted_comma_call(source)
        seen: set[str] = set()
        for suffix in _contextual_suffixes(source):
            text = source + suffix + closers
            if text in seen:
                continue
            seen.add(text)
            yield _Candidate(
                text,
                len(source),
                len(text) > len(source),
                bool(suffix.strip()) or closes_expression_tail,
                trusted_comma_call,
            )


class LazyBatchSemanticValidator:
    """Create the Lark/typechecker stack only when a fallback is required."""

    def __init__(self, *, context_path: str | None = None) -> None:
        self._context_path = context_path
        self._validator: BatchSemanticValidator | None = None

    @property
    def initialized(self) -> bool:
        return self._validator is not None

    def validate_prefix(self, source: str) -> SemanticValidationResult:
        if self._validator is None:
            self._validator = BatchSemanticValidator(context_path=self._context_path)
        return self._validator.validate_prefix(source)


def _line_col_to_offset(source: str, line: int | None, column: int | None) -> int | None:
    if line is None or column is None or line < 1 or column < 1:
        return None
    cur_line = 1
    cur_col = 1
    for idx, ch in enumerate(source):
        if cur_line == line and cur_col == column:
            return idx
        if ch == "\n":
            cur_line += 1
            cur_col = 1
        else:
            cur_col += 1
    if cur_line == line and cur_col == column:
        return len(source)
    return None


def _contextual_suffixes(source: str) -> list[str]:
    stripped = source.rstrip()
    if not stripped:
        return [""]

    suffixes = [""]
    if stripped.endswith(("=", "=>", "+", "-", "*", "/", "%", "<", ">", "<=", ">=", "==", "!=", "&&", "||", "..", "..=", ":", ",")):
        suffixes.extend([" 0", " Int64", " x"])
    if stripped.endswith(("return", "let", "var")):
        suffixes.extend([" 0", " x: Int64 = 0"])
    if stripped.endswith(("func", "class", "interface", "init")):
        suffixes.append(" __dummy")
    if stripped.endswith(("(", "[", "{")):
        suffixes.extend(["0", ""])
    suffixes.extend(["\n", "\n0", "\nlet __dummy: Int64 = 0"])
    return suffixes


def _is_trusted_comma_call(source: str) -> bool:
    return re.search(r"\.\s*add\s*\([^()\n]*,\s*$", source.rstrip()) is not None


def _missing_closers(source: str) -> str:
    stack: list[str] = []
    i = 0
    state = "code"
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                state = "line_comment"
                i += 2
                continue
            if ch == "/" and nxt == "*":
                state = "block_comment"
                i += 2
                continue
            if source.startswith('"""', i):
                state = "triple_string"
                i += 3
                continue
            if ch == '"':
                state = "string"
                i += 1
                continue
            if ch == "'":
                state = "rune"
                i += 1
                continue
            if ch in "([{":
                stack.append(ch)
            elif ch in ")]}" and stack and _matches(stack[-1], ch):
                stack.pop()
            i += 1
            continue
        if state == "line_comment":
            if ch in "\r\n":
                state = "code"
            i += 1
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 2
            else:
                i += 1
            continue
        if state == "triple_string":
            if source.startswith('"""', i):
                state = "code"
                i += 3
            else:
                i += 1
            continue
        if state in {"string", "rune"}:
            quote = '"' if state == "string" else "'"
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                state = "code"
            i += 1
            continue

    return "".join({"(": ")", "[": "]", "{": "}"}[opener] for opener in reversed(stack))


def _matches(opener: str, closer: str) -> bool:
    return (opener, closer) in {("(", ")"), ("[", "]"), ("{", "}")}
