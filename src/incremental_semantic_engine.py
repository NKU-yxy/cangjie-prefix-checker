"""Incremental semantic state for the streaming checker.

The state machine in this module consumes each stable Cangjie lexical token
exactly once.  The lightweight prefix checker remains as a conservative probe
for rules that have not yet moved to token-local transitions; unlike the old
batch validator it caches declarations and never invokes Lark in ``fast``
mode.  Keeping the transition API separate lets those probes be replaced one
rule at a time without changing the competition protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .lexer import Token, TokenType
from .prefix_semantic_checker import PrefixSemanticChecker


TypeId = int


@dataclass(frozen=True)
class CheckStatus:
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class TokenEvent:
    token: Token


@dataclass(frozen=True)
class PartialLexeme:
    text: str
    candidates: frozenset[TokenType] = frozenset()


@dataclass
class ScopeFrame:
    kind: str = "block"
    symbols: dict[str, TypeId] = field(default_factory=dict)
    mutable: set[str] = field(default_factory=set)
    in_function: bool = False
    in_loop: bool = False
    in_class: bool = False
    in_lambda: bool = False


@dataclass
class ExprFrame:
    expected: TypeId | None = None
    current: TypeId | None = None
    operators: list[TokenType] = field(default_factory=list)


@dataclass
class CallFrame:
    callee: str = ""
    argument_index: int = 0
    named_arguments: set[str] = field(default_factory=set)
    candidates: tuple[str, ...] = ()


@dataclass
class ConstraintSet:
    bindings: dict[TypeId, TypeId] = field(default_factory=dict)

    def bind(self, variable: TypeId, actual: TypeId) -> bool:
        previous = self.bindings.get(variable)
        if previous is None:
            self.bindings[variable] = actual
            return True
        return previous == actual


class TypeArena:
    """Intern type spellings so comparisons and state snapshots use integers."""

    def __init__(self) -> None:
        self._ids: dict[str, TypeId] = {}
        self._types: list[str] = []
        for spelling in (
            "Int8", "Int16", "Int32", "Int64", "Float32", "Float64",
            "Bool", "Rune", "String", "Unit", "?",
        ):
            self.intern(spelling)

    def intern(self, spelling: str) -> TypeId:
        normalized = " ".join(str(spelling).split())
        existing = self._ids.get(normalized)
        if existing is not None:
            return existing
        type_id = len(self._types)
        self._ids[normalized] = type_id
        self._types.append(normalized)
        return type_id

    def spelling(self, type_id: TypeId) -> str:
        return self._types[type_id]

    def __len__(self) -> int:
        return len(self._types)


@dataclass(frozen=True)
class SemanticCheckpoint:
    scopes: tuple[ScopeFrame, ...]
    expr_frames: tuple[ExprFrame, ...]
    call_frames: tuple[CallFrame, ...]
    constraints: tuple[dict[TypeId, TypeId], ...]
    recent_tokens: tuple[Token, ...]
    pending_declaration: tuple[str, str | None] | None
    next_scope_kind: str | None
    accepted_events: int


class IncrementalSemanticEngine:
    """Token-once semantic state with conservative partial-lexeme probing."""

    def __init__(self, preload_context: dict | None = None) -> None:
        self.types = TypeArena()
        self.scopes: list[ScopeFrame] = [ScopeFrame(kind="global")]
        self.expr_frames: list[ExprFrame] = []
        self.call_frames: list[CallFrame] = []
        self.constraints: list[ConstraintSet] = []
        self._recent_tokens: list[Token] = []
        self._pending_declaration: tuple[str, str | None] | None = None
        self._next_scope_kind: str | None = None
        self._accepted_events = 0
        self._probe_checker = PrefixSemanticChecker(preload_context)
        self._load_symbols(preload_context or {})

    @property
    def accepted_events(self) -> int:
        return self._accepted_events

    @property
    def visible_symbols(self) -> frozenset[str]:
        return frozenset(
            name
            for scope in self.scopes
            for name in scope.symbols
        )

    def can_complete_symbol(self, prefix: str) -> bool:
        return any(name.startswith(prefix) for name in self.visible_symbols)

    def accept(self, event: TokenEvent) -> CheckStatus:
        token = event.token
        self._accepted_events += 1

        if token.type in (TokenType.KW_LET, TokenType.KW_VAR):
            self._pending_declaration = (
                "variable",
                "mutable" if token.type == TokenType.KW_VAR else "immutable",
            )
        elif token.type == TokenType.KW_FUNC:
            self._pending_declaration = ("function", None)
            self._next_scope_kind = "function"
        elif token.type == TokenType.KW_CLASS:
            self._pending_declaration = ("class", None)
            self._next_scope_kind = "class"
        elif token.type == TokenType.KW_INTERFACE:
            self._pending_declaration = ("interface", None)
            self._next_scope_kind = "interface"
        elif token.type in (TokenType.KW_FOR, TokenType.KW_WHILE):
            self._next_scope_kind = "loop"
        elif token.type == TokenType.OP_FAT_ARROW:
            self._next_scope_kind = "lambda"
        elif token.type == TokenType.IDENTIFIER and self._pending_declaration:
            category, modifier = self._pending_declaration
            unknown = self.types.intern("?")
            if category == "variable" and token.text in self.scopes[-1].symbols:
                return CheckStatus(False, f"duplicate variable {token.text}")
            self.scopes[-1].symbols.setdefault(token.text, unknown)
            if category == "variable" and modifier == "mutable":
                self.scopes[-1].mutable.add(token.text)
            self._pending_declaration = None
        elif token.type == TokenType.LBRACE:
            kind = self._next_scope_kind or "block"
            parent = self.scopes[-1]
            self.scopes.append(
                ScopeFrame(
                    kind=kind,
                    in_function=parent.in_function or kind == "function",
                    in_loop=parent.in_loop or kind == "loop",
                    in_class=parent.in_class or kind == "class",
                    in_lambda=parent.in_lambda or kind == "lambda",
                )
            )
            self._next_scope_kind = None
        elif token.type == TokenType.RBRACE and len(self.scopes) > 1:
            self.scopes.pop()
        elif token.type == TokenType.LPAREN:
            callee = self._recent_tokens[-1].text if self._recent_tokens else ""
            self.call_frames.append(CallFrame(callee=callee))
            self.expr_frames.append(ExprFrame())
        elif token.type == TokenType.COMMA and self.call_frames:
            self.call_frames[-1].argument_index += 1
        elif token.type == TokenType.RPAREN:
            if self.call_frames:
                self.call_frames.pop()
            if self.expr_frames:
                self.expr_frames.pop()

        self._recent_tokens.append(token)
        if len(self._recent_tokens) > 3:
            del self._recent_tokens[0]
        return CheckStatus(ok=True)

    def probe(self, partial: PartialLexeme, source: str) -> CheckStatus:
        # Partial lexical candidates are checked by the grammar matcher.  This
        # probe owns semantic reachability and intentionally does not commit
        # any state for the unstable lexeme.
        result = self._probe_checker.validate(source)
        return CheckStatus(result.ok, result.message)

    def checkpoint(self) -> SemanticCheckpoint:
        return SemanticCheckpoint(
            scopes=tuple(_copy_scope(item) for item in self.scopes),
            expr_frames=tuple(_copy_expr(item) for item in self.expr_frames),
            call_frames=tuple(_copy_call(item) for item in self.call_frames),
            constraints=tuple(dict(item.bindings) for item in self.constraints),
            recent_tokens=tuple(self._recent_tokens),
            pending_declaration=self._pending_declaration,
            next_scope_kind=self._next_scope_kind,
            accepted_events=self._accepted_events,
        )

    def rollback(self, checkpoint: SemanticCheckpoint) -> None:
        self.scopes = [_copy_scope(item) for item in checkpoint.scopes]
        self.expr_frames = [_copy_expr(item) for item in checkpoint.expr_frames]
        self.call_frames = [_copy_call(item) for item in checkpoint.call_frames]
        self.constraints = [ConstraintSet(dict(item)) for item in checkpoint.constraints]
        self._recent_tokens = list(checkpoint.recent_tokens)
        self._pending_declaration = checkpoint.pending_declaration
        self._next_scope_kind = checkpoint.next_scope_kind
        self._accepted_events = checkpoint.accepted_events

    def _load_symbols(self, context: dict) -> None:
        global_scope = self.scopes[0]
        for variable in context.get("variables", []):
            if isinstance(variable, dict) and variable.get("name"):
                type_id = self.types.intern(str(variable.get("type") or "?"))
                name = str(variable["name"])
                global_scope.symbols[name] = type_id
                if variable.get("mutable"):
                    global_scope.mutable.add(name)
        for section in ("functions", "classes", "interfaces"):
            for item in context.get(section, []):
                if isinstance(item, dict) and item.get("name"):
                    global_scope.symbols.setdefault(
                        str(item["name"]), self.types.intern("?"),
                    )


def _copy_scope(frame: ScopeFrame) -> ScopeFrame:
    return ScopeFrame(
        kind=frame.kind,
        symbols=dict(frame.symbols),
        mutable=set(frame.mutable),
        in_function=frame.in_function,
        in_loop=frame.in_loop,
        in_class=frame.in_class,
        in_lambda=frame.in_lambda,
    )


def _copy_expr(frame: ExprFrame) -> ExprFrame:
    return ExprFrame(frame.expected, frame.current, list(frame.operators))


def _copy_call(frame: CallFrame) -> CallFrame:
    return CallFrame(
        frame.callee,
        frame.argument_index,
        set(frame.named_arguments),
        tuple(frame.candidates),
    )
