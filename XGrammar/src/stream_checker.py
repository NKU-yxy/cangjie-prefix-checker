"""Streaming competition checker."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

os.environ["TVM_FFI_BUILD_DOCS"] = "1"

from xgrammar import GrammarCompiler, GrammarMatcher

from .batch_semantic_validator import BatchSemanticValidator
from .incremental_lexer import IncrementalLexer, IncrementalLexResult
from .lexer import Token, TokenType
from .prefix_semantic_checker import PrefixSemanticChecker
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
    ) -> None:
        _ = preload_context
        self.lexer = IncrementalLexer()
        self._grammar_path = grammar_path or self._default_grammar_path()
        with open(self._grammar_path, "r", encoding="utf-8") as f:
            grammar_str = f.read()
        self._compiler = GrammarCompiler(TOKENIZER_INFO, cache_enabled=False)
        self._compiled_grammar = self._compiler.compile_grammar(grammar_str)
        self._matcher = GrammarMatcher(self._compiled_grammar)
        self._semantic = BatchSemanticValidator(context_path=context_path)
        self._prefix_semantic = PrefixSemanticChecker()
        self._source_prefix = ""
        self._last_semantic_source = ""
        self._accepted_token_ids: list[int] = []
        self._accepted_tokens: list[Token] = []
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

        prefix_status = self._prefix_semantic.validate(self._source_prefix)
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

        self._accepted_token_ids.append(token_id)
        self._accepted_tokens.append(token)
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
        matcher = GrammarMatcher(self._compiled_grammar)
        for token_id in self._accepted_token_ids:
            if not matcher.accept_token(token_id):
                return False
        try:
            token_id = get_token_id(token_type)
        except Exception:
            return False
        return matcher.accept_token(token_id)

    def _check_semantic_prefix(self, lex_result: IncrementalLexResult) -> StreamStatus:
        if lex_result.remaining:
            return StreamStatus(ok=True)
        stable_source = self._source_prefix
        if stable_source == self._last_semantic_source:
            return StreamStatus(ok=True)
        if stable_source.rstrip().endswith(")") and not stable_source.endswith(("\n", "\r", ";")):
            return StreamStatus(ok=True)
        self._last_semantic_source = stable_source

        result = self._semantic.validate_prefix(stable_source)
        if result.ok:
            return StreamStatus(ok=True)
        diag = result.diagnostic
        message = diag.message if diag else "Semantic error"
        return StreamStatus(ok=False, error_type="semantic", error_message=message)

    def _token_invalid_in_kw_context(self, token: Token) -> bool:
        entries = self._accepted_tokens + [token]
        idx = len(entries) - 1
        if idx >= 1:
            prev = entries[idx - 1]
            if prev.type in _KW_DECL_START and token.type != TokenType.IDENTIFIER:
                return True
        if idx >= 2:
            prev2 = entries[idx - 2]
            prev1 = entries[idx - 1]
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
