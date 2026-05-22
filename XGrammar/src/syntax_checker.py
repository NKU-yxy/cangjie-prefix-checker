"""
Cangjie Syntax & Semantic Checker -- unified token-by-token validation.

Syntax checking: XGrammar accept_token() — O(1) bitmask lookup.
Semantic checking: scope, type inference, context constraints.

Outputs 1 for each valid token, 0 for the first invalid token, then stops.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from xgrammar import GrammarCompiler, GrammarMatcher

from .lexer import CangjieLexer, Token, TokenType
from .semantic_checker import SemanticChecker
from .token_vocab import TOKENIZER_INFO, get_token_id

# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    """Result of unified syntax + semantic checking."""
    tokens: List[str] = field(default_factory=list)
    syntax_results: List[int] = field(default_factory=list)
    semantic_results: List[int] = field(default_factory=list)
    passed: bool = True
    error_token: Optional[str] = None
    error_line: Optional[int] = None
    error_col: Optional[int] = None
    error_type: str = ""  # "syntax" or "semantic"
    error_message: str = ""

    # Backwards compat: .results returns syntax results
    @property
    def results(self) -> List[int]:
        return self.syntax_results

    def format_output(self) -> str:
        token_str = " ".join(self.tokens)
        syn_str = ", ".join(str(r) for r in self.syntax_results)
        sem_str = ", ".join(str(r) for r in self.semantic_results)
        lines = [
            f"token: {token_str}",
            f"语法: {syn_str}",
            f"语义: {sem_str}",
        ]
        if self.error_message:
            lines.append(f"错误: {self.error_message}")
        return "\n".join(lines)


# ── Tokens filtered from the grammar stream ───────────────────────────────────

_FILTER_TOKEN_TYPES = frozenset({
    TokenType.WS,
    TokenType.NEWLINE,
    TokenType.COMMENT_LINE,
    TokenType.COMMENT_BLOCK,
    TokenType.UNKNOWN,
})


# Keyword token types that start declarations
_KW_DECL_START = frozenset({
    TokenType.KW_VAR, TokenType.KW_LET, TokenType.KW_FUNC,
    TokenType.KW_CLASS, TokenType.KW_STRUCT, TokenType.KW_ENUM,
    TokenType.KW_INTERFACE, TokenType.KW_EXTEND,
})

# Valid token types after `keyword identifier` in a declaration
_VALID_AFTER_KW_IDENT = frozenset({
    TokenType.COLON,
    TokenType.OP_ASSIGN,
    TokenType.SEMICOLON,
    TokenType.OP_PLUS_EQ, TokenType.OP_MINUS_EQ,
    TokenType.OP_MUL_EQ, TokenType.OP_DIV_EQ,
    TokenType.OP_MOD_EQ, TokenType.OP_POW_EQ,
    TokenType.OP_SHL_EQ, TokenType.OP_SHR_EQ,
    TokenType.OP_AND_EQ, TokenType.OP_XOR_EQ, TokenType.OP_OR_EQ,
    TokenType.OP_ANDAND_EQ, TokenType.OP_OROR_EQ,
    TokenType.OP_INC, TokenType.OP_DEC,
})


# ── Checker ───────────────────────────────────────────────────────────────────

class CangjieSyntaxChecker:
    """Token-by-token syntax checker for Cangjie using XGrammar accept_token()."""

    def __init__(self, grammar_path: Optional[str] = None):
        if grammar_path is None:
            grammar_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "grammar", "cangjie_token.gbnf"
            )
        with open(grammar_path, 'r', encoding='utf-8') as f:
            self.grammar_str = f.read()

        self._compiler = GrammarCompiler(TOKENIZER_INFO, cache_enabled=False)
        self._compiled_grammar = self._compiler.compile_grammar(self.grammar_str)

    def check_token_by_token(
        self, code: str, *, verbose: bool = False
    ) -> CheckResult:
        """Check Cangjie source code token-by-token.

        Runs both syntax and semantic checking on the same token stream.
        Returns a CheckResult with 1 for each valid token, 0 at the first
        invalid token (and stops there).
        """
        processed = self._preprocess_comments(code)
        lexer = CangjieLexer(processed, skip_ws=False, skip_comments=True)
        all_tokens = lexer.tokenize()

        significant = [
            t for t in all_tokens
            if t.type not in _FILTER_TOKEN_TYPES
        ]
        if not significant:
            return CheckResult(tokens=[], passed=True)

        matcher = GrammarMatcher(self._compiled_grammar)
        semantic = SemanticChecker()

        display_tokens: List[str] = []
        syntax_results: List[int] = []
        semantic_results: List[int] = []

        for idx, token in enumerate(significant):
            token_id = get_token_id(token.type)

            # --- Syntax check (grammar + keyword context) ---
            syntax_ok = True
            if not matcher.accept_token(token_id):
                syntax_ok = False
            elif self._token_invalid_in_kw_context(token, significant, idx):
                syntax_ok = False

            if not syntax_ok:
                display_tokens.append(token.text)
                syntax_results.append(0)
                semantic_results.append(0)
                return CheckResult(
                    tokens=display_tokens,
                    syntax_results=syntax_results,
                    semantic_results=semantic_results,
                    passed=False,
                    error_token=token.text,
                    error_line=token.line,
                    error_col=token.column,
                    error_type="syntax",
                )

            # --- Semantic check ---
            sem_result = semantic.process(token)
            if not sem_result.ok:
                display_tokens.append(token.text)
                syntax_results.append(1)
                semantic_results.append(0)
                return CheckResult(
                    tokens=display_tokens,
                    syntax_results=syntax_results,
                    semantic_results=semantic_results,
                    passed=False,
                    error_token=token.text,
                    error_line=token.line,
                    error_col=token.column,
                    error_type="semantic",
                    error_message=sem_result.error,
                )

            display_tokens.append(token.text)
            syntax_results.append(1)
            semantic_results.append(1)

        # End-of-input semantic check
        final = semantic.finalize()
        if not final.ok:
            # Append error to last token position
            semantic_results[-1] = 0
            return CheckResult(
                tokens=display_tokens,
                syntax_results=syntax_results,
                semantic_results=semantic_results,
                passed=False,
                error_type="semantic",
                error_message=final.error,
            )

        return CheckResult(
            tokens=display_tokens,
            syntax_results=syntax_results,
            semantic_results=semantic_results,
            passed=True,
        )

    def _token_invalid_in_kw_context(
        self,
        token: Token,
        entries: List[Token],
        idx: int,
    ) -> bool:
        """Check if token is invalid in a keyword declaration context.

        Case A: keyword immediately followed by invalid token (e.g. 'let +')
        Case B: keyword <ident> then invalid token (e.g. 'let a +')
        """
        # Case A: keyword at idx-1
        if idx >= 1:
            prev = entries[idx - 1]
            if prev.type in _KW_DECL_START:
                if token.type != TokenType.IDENTIFIER:
                    return True

        # Case B: keyword at idx-2, identifier at idx-1
        if idx >= 2:
            prev2 = entries[idx - 2]
            prev1 = entries[idx - 1]
            if prev2.type in _KW_DECL_START and prev1.type == TokenType.IDENTIFIER:
                vset = self._valid_after_kw_ident(prev2.type)
                if vset is not None and token.type not in vset:
                    return True

        return False

    @staticmethod
    def _valid_after_kw_ident(kw_type: TokenType):
        """Return set of valid token types after `keyword <identifier>`."""
        if kw_type in (TokenType.KW_LET, TokenType.KW_VAR):
            return _VALID_AFTER_KW_IDENT
        if kw_type == TokenType.KW_FUNC:
            return {TokenType.LPAREN, TokenType.COLON, TokenType.OP_LT}
        if kw_type in (TokenType.KW_CLASS, TokenType.KW_STRUCT,
                       TokenType.KW_ENUM, TokenType.KW_INTERFACE,
                       TokenType.KW_EXTEND):
            return {TokenType.COLON, TokenType.LBRACE,
                    TokenType.OP_LT, TokenType.OP_LT_COLON}
        return None

    @staticmethod
    def _preprocess_comments(code: str) -> str:
        """Strip line comments (//) and block comments (/* */) from source."""
        result = []
        i = 0
        while i < len(code):
            if i + 1 < len(code) and code[i:i+2] == '//':
                while i < len(code) and code[i] not in '\n\r':
                    i += 1
                continue
            if i + 1 < len(code) and code[i:i+2] == '/*':
                depth = 1
                i += 2
                while i < len(code) and depth > 0:
                    if i + 1 < len(code) and code[i:i+2] == '/*':
                        depth += 1
                        i += 2
                    elif i + 1 < len(code) and code[i:i+2] == '*/':
                        depth -= 1
                        i += 2
                    else:
                        i += 1
                continue
            result.append(code[i])
            i += 1
        return ''.join(result)


def check_cangjie(code: str, grammar_path: Optional[str] = None) -> CheckResult:
    """Check Cangjie source code syntax. Returns CheckResult."""
    checker = CangjieSyntaxChecker(grammar_path=grammar_path)
    return checker.check_token_by_token(code)
