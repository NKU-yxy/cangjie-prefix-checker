"""Streaming competition checker."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

os.environ["TVM_FFI_BUILD_DOCS"] = "1"

from xgrammar import GrammarCompiler, GrammarMatcher

from .batch_semantic_validator import LazyBatchSemanticValidator
from .context_loader import load_context
from .incremental_lexer import IncrementalLexer, IncrementalLexResult
from .incremental_semantic_engine import (
    IncrementalSemanticEngine,
    PartialLexeme,
    TokenEvent,
)
from .lexer import Token, TokenType
from .token_vocab import TOKENIZER_INFO, get_token_id


_KW_DECL_START = frozenset({
    TokenType.KW_VAR, TokenType.KW_LET, TokenType.KW_FUNC,
    TokenType.KW_CLASS, TokenType.KW_STRUCT, TokenType.KW_ENUM,
    TokenType.KW_INTERFACE, TokenType.KW_EXTEND,
})

_VALID_AFTER_KW_IDENT = frozenset({
    TokenType.COLON, TokenType.OP_ASSIGN, TokenType.SEMICOLON,
    TokenType.OP_PLUS_EQ, TokenType.OP_MINUS_EQ, TokenType.OP_MUL_EQ,
    TokenType.OP_DIV_EQ, TokenType.OP_MOD_EQ, TokenType.OP_POW_EQ,
    TokenType.OP_SHL_EQ, TokenType.OP_SHR_EQ, TokenType.OP_AND_EQ,
    TokenType.OP_XOR_EQ, TokenType.OP_OR_EQ, TokenType.OP_ANDAND_EQ,
    TokenType.OP_OROR_EQ, TokenType.OP_INC, TokenType.OP_DEC,
})

# Deep validation reparses and typechecks a completed source candidate.  It is
# only useful when the latest fragment commits a semantic unit.  In
# particular, validating after every whitespace-delimited tiktoken fragment
# makes the overall checker quadratic in the source length.
# Commas are handled by the online call/constraint frames.  Re-running the
# whole fallback typechecker for every parameter and argument comma was both
# redundant and particularly expensive in lambda-heavy programs.
_SEMANTIC_COMMIT_SUFFIXES = ("\n", "\r", ";", "}")

_HASHMAP_DECL_RE = re.compile(
    r"\b(?:let|var)\s+([A-Za-z_]\w*)\s*:\s*HashMap\b"
)
_HASHMAP_FOR_RE = re.compile(
    r"\bfor\s*\(\s*([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)\s*\)\s*\{"
)


@dataclass
class StreamStatus:
    ok: bool
    error_type: str = ""
    error_message: str = ""


class CangjieStreamChecker:
    """Incremental checker for the competition stdin/stdout protocol."""

    def __init__(
        self,
        grammar_path: Optional[str] = None,
        *,
        preload_context: Optional[dict] = None,
        context_path: Optional[str] = None,
        semantic_mode: Optional[str] = None,
    ) -> None:
        self.lexer = IncrementalLexer()
        self._grammar_path = grammar_path or self._default_grammar_path()
        with open(self._grammar_path, "r", encoding="utf-8") as f:
            grammar_str = f.read()
        self._compiler = GrammarCompiler(TOKENIZER_INFO, cache_enabled=False)
        self._compiled_grammar = self._compiler.compile_grammar(grammar_str)
        self._matcher = GrammarMatcher(self._compiled_grammar)
        normalized_context = preload_context if preload_context is not None else load_context(context_path)
        self._semantic_mode = semantic_mode or os.environ.get(
            "CANGJIE_SEMANTIC_MODE", "fast"
        )
        if self._semantic_mode not in {"legacy", "checkpoint", "fast"}:
            raise ValueError(f"unsupported semantic mode: {self._semantic_mode}")
        self._semantic = LazyBatchSemanticValidator(context_path=context_path)
        self._semantic_engine = IncrementalSemanticEngine(normalized_context)
        self._source_prefix = ""
        self._last_semantic_source = ""
        # Only the two immediately preceding tokens are needed by
        # _token_invalid_in_kw_context().  Keeping the complete history caused
        # a full-list copy for every accepted token.
        self._previous_tokens: list[Token] = []
        self._failed = False
        self._last_error = StreamStatus(ok=True)

    @staticmethod
    def _default_grammar_path() -> str:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, "grammar", "cangjie_token.gbnf")

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def last_error(self) -> StreamStatus:
        return self._last_error

    def feed_text(self, text: str) -> StreamStatus:
        if self._failed:
            return self._last_error

        if text:
            self._source_prefix += text
        lex_result = self.lexer.feed(text)
        for token in lex_result.tokens:
            status = self._accept_complete_token(token)
            if not status.ok:
                self._failed = True
                self._last_error = status
                return status

        status = self._check_partial(lex_result)
        if not status.ok:
            self._failed = True
            self._last_error = status
            return status

        prefix_status = self._semantic_engine.probe(
            PartialLexeme(
                lex_result.partial_text,
                frozenset(lex_result.partial_candidates),
            ),
            self._source_prefix,
        )
        if not prefix_status.ok:
            status = StreamStatus(ok=False, error_type="semantic", error_message=prefix_status.message)
            self._failed = True
            self._last_error = status
            return status

        status = self._check_semantic_prefix(lex_result)
        if not status.ok:
            self._failed = True
            self._last_error = status
        return status

    def _accept_complete_token(self, token: Token) -> StreamStatus:
        if token.type == TokenType.UNKNOWN:
            return StreamStatus(ok=False, error_type="syntax", error_message=f"Unknown token {token.text!r}")
        try:
            token_id = get_token_id(token.type)
        except Exception:
            return StreamStatus(ok=False, error_type="syntax", error_message=f"Unsupported token {token.text!r}")
        if not self._matcher.accept_token(token_id):
            return StreamStatus(ok=False, error_type="syntax", error_message=f"Unexpected token {token.text!r}")
        if self._token_invalid_in_kw_context(token):
            return StreamStatus(ok=False, error_type="syntax", error_message=f"Invalid declaration token {token.text!r}")

        semantic_status = self._semantic_engine.accept(TokenEvent(token))
        if not semantic_status.ok:
            return StreamStatus(
                ok=False,
                error_type="semantic",
                error_message=semantic_status.message,
            )

        self._previous_tokens.append(token)
        if len(self._previous_tokens) > 2:
            del self._previous_tokens[0]
        return StreamStatus(ok=True)

    def _check_partial(self, lex_result: IncrementalLexResult) -> StreamStatus:
        if not lex_result.lexically_continuable:
            return StreamStatus(ok=False, error_type="lexical", error_message="Invalid lexical prefix")
        if not lex_result.partial_text:
            return StreamStatus(ok=True)
        if not lex_result.partial_candidates:
            return StreamStatus(ok=True)

        for token_type in lex_result.partial_candidates:
            token = Token(token_type, lex_result.partial_text, 0, 0)
            if self._token_invalid_in_kw_context(token):
                continue
            if self._trial_accept(token_type):
                return StreamStatus(ok=True)
        return StreamStatus(ok=False, error_type="syntax", error_message="Partial token cannot continue here")

    def _trial_accept(self, token_type: TokenType) -> bool:
        try:
            token_id = get_token_id(token_type)
        except Exception:
            return False
        matcher = self._matcher.fork()
        return matcher.accept_token(token_id)

    def _check_semantic_prefix(self, lex_result: IncrementalLexResult) -> StreamStatus:
        if self._semantic_mode == "fast":
            return StreamStatus(ok=True)
        if lex_result.remaining:
            return StreamStatus(ok=True)
        stable_source = self._source_prefix
        if self._semantic_mode == "checkpoint":
            if not stable_source.endswith(_SEMANTIC_COMMIT_SUFFIXES):
                return StreamStatus(ok=True)
        elif stable_source.rstrip().endswith(")") and not stable_source.endswith(("\n", "\r", ";")):
            return StreamStatus(ok=True)
        if stable_source == self._last_semantic_source:
            return StreamStatus(ok=True)
        self._last_semantic_source = stable_source

        result = self._semantic.validate_prefix(stable_source)
        if result.ok:
            return StreamStatus(ok=True)
        diag = result.diagnostic
        message = diag.message if diag else "Semantic error"
        if _transient_hashmap_for_diagnostic(stable_source, message):
            return StreamStatus(ok=True)
        return StreamStatus(ok=False, error_type="semantic", error_message=message)

    def _token_invalid_in_kw_context(self, token: Token) -> bool:
        if self._previous_tokens:
            prev = self._previous_tokens[-1]
            if prev.type in _KW_DECL_START and token.type != TokenType.IDENTIFIER:
                return True
        if len(self._previous_tokens) >= 2:
            prev2 = self._previous_tokens[-2]
            prev1 = self._previous_tokens[-1]
            if prev2.type in _KW_DECL_START and prev1.type == TokenType.IDENTIFIER:
                valid_after = self._valid_after_kw_ident(prev2.type)
                if valid_after is not None and token.type not in valid_after:
                    return True
        return False

    @staticmethod
    def _valid_after_kw_ident(kw_type: TokenType):
        if kw_type in (TokenType.KW_LET, TokenType.KW_VAR):
            return _VALID_AFTER_KW_IDENT
        if kw_type == TokenType.KW_FUNC:
            return {TokenType.LPAREN, TokenType.COLON, TokenType.OP_LT}
        if kw_type in (TokenType.KW_CLASS, TokenType.KW_STRUCT, TokenType.KW_ENUM, TokenType.KW_INTERFACE, TokenType.KW_EXTEND):
            return {TokenType.COLON, TokenType.LBRACE, TokenType.OP_LT, TokenType.OP_LT_COLON}
        return None


def _transient_hashmap_for_diagnostic(source: str, message: str) -> bool:
    if "not iterable" not in message or "HashMap" not in message:
        return False
    hashmap_vars = {
        m.group(1)
        for m in _HASHMAP_DECL_RE.finditer(source)
    }
    for m in _HASHMAP_FOR_RE.finditer(source):
        bound, iterable = m.group(1), m.group(2)
        if iterable in hashmap_vars and not re.search(rf"(?:\(\s*{re.escape(bound)}\s*\)|\b{re.escape(bound)})\s*\.", source[m.end():]):
            return True
    return False
