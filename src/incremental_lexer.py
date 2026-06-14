"""Incremental lexical adapter for tiktoken-fragmented input."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Sequence, Set, Tuple

from .lexer import CangjieLexer, KEYWORDS, Token, TokenType


_SKIP_TOKEN_TYPES = frozenset({
    TokenType.WS,
    TokenType.NEWLINE,
    TokenType.COMMENT_LINE,
    TokenType.COMMENT_BLOCK,
})

_IDENT_PREFIX_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMERIC_PREFIX_RE = re.compile(
    r"^(?:"
    r"0[xX][0-9A-Fa-f]*|"
    r"0[oO][0-7]*|"
    r"0[bB][01]*|"
    r"\d+(?:\.\d*)?(?:[eE][+\-]?\d*)?"
    r")(?:[iu](?:8|16|32|64)|f(?:16|32|64))?$"
)

_OPERATOR_PREFIXES: dict[str, Set[TokenType]] = {
    ".": {TokenType.OP_DOT, TokenType.OP_RANGE, TokenType.OP_RANGE_INCL},
    "..": {TokenType.OP_RANGE, TokenType.OP_RANGE_INCL},
    "...": {TokenType.OP_RANGE_INCL},
    "..=": {TokenType.OP_RANGE_INCL},
    "=": {TokenType.OP_ASSIGN, TokenType.OP_EQ, TokenType.OP_FAT_ARROW},
    "==": {TokenType.OP_EQ},
    "=>": {TokenType.OP_FAT_ARROW},
    "!": {TokenType.OP_NOT, TokenType.OP_NE},
    "!=": {TokenType.OP_NE},
    "<": {TokenType.OP_LT, TokenType.OP_LE, TokenType.OP_LT_COLON, TokenType.OP_SHL, TokenType.OP_SHL_EQ},
    "<=": {TokenType.OP_LE},
    "<:": {TokenType.OP_LT_COLON},
    "<<": {TokenType.OP_SHL, TokenType.OP_SHL_EQ},
    "<<=": {TokenType.OP_SHL_EQ},
    ">": {TokenType.OP_GT, TokenType.OP_GE, TokenType.OP_SHR, TokenType.OP_SHR_EQ},
    ">=": {TokenType.OP_GE},
    ">>": {TokenType.OP_SHR, TokenType.OP_SHR_EQ},
    ">>=": {TokenType.OP_SHR_EQ},
    "&": {TokenType.OP_BIT_AND, TokenType.OP_AND, TokenType.OP_AND_EQ, TokenType.OP_ANDAND_EQ},
    "&&": {TokenType.OP_AND, TokenType.OP_ANDAND_EQ},
    "&&=": {TokenType.OP_ANDAND_EQ},
    "&=": {TokenType.OP_AND_EQ},
    "|": {TokenType.OP_BIT_OR, TokenType.OP_OR, TokenType.OP_OR_EQ, TokenType.OP_OROR_EQ, TokenType.OP_PIPE},
    "||": {TokenType.OP_OR, TokenType.OP_OROR_EQ},
    "||=": {TokenType.OP_OROR_EQ},
    "|=": {TokenType.OP_OR_EQ},
    "|>": {TokenType.OP_PIPE},
    "?": {TokenType.OP_QUESTION, TokenType.OP_COALESCE},
    "??": {TokenType.OP_COALESCE},
    "~": {TokenType.OP_BIT_NOT, TokenType.OP_COMPOSE},
    "~>": {TokenType.OP_COMPOSE},
    "*": {TokenType.OP_STAR, TokenType.OP_POW, TokenType.OP_MUL_EQ, TokenType.OP_POW_EQ},
    "**": {TokenType.OP_POW, TokenType.OP_POW_EQ},
    "**=": {TokenType.OP_POW_EQ},
    "*=": {TokenType.OP_MUL_EQ},
    "+": {TokenType.OP_PLUS, TokenType.OP_INC, TokenType.OP_PLUS_EQ},
    "++": {TokenType.OP_INC},
    "+=": {TokenType.OP_PLUS_EQ},
    "-": {TokenType.OP_MINUS, TokenType.OP_DEC, TokenType.OP_MINUS_EQ, TokenType.OP_ARROW},
    "--": {TokenType.OP_DEC},
    "-=": {TokenType.OP_MINUS_EQ},
    "->": {TokenType.OP_ARROW},
    "/": {TokenType.OP_SLASH, TokenType.OP_DIV_EQ},
    "/=": {TokenType.OP_DIV_EQ},
    "%": {TokenType.OP_PERCENT, TokenType.OP_MOD_EQ},
    "%=": {TokenType.OP_MOD_EQ},
    "^": {TokenType.OP_BIT_XOR, TokenType.OP_XOR_EQ},
    "^=": {TokenType.OP_XOR_EQ},
}


@dataclass
class IncrementalLexResult:
    tokens: List[Token] = field(default_factory=list)
    remaining: str = ""
    partial_text: str = ""
    partial_candidates: Set[TokenType] = field(default_factory=set)
    lexically_continuable: bool = True


class IncrementalLexer:
    """Convert arbitrary decoded fragments into stable Cangjie tokens."""

    def __init__(self) -> None:
        self._buffer = ""
        self._base_line = 1
        self._base_col = 1

    @property
    def remaining(self) -> str:
        return self._buffer

    def feed(self, text: str) -> IncrementalLexResult:
        if text:
            self._buffer += text
        return self._drain_stable_prefix()

    def _drain_stable_prefix(self) -> IncrementalLexResult:
        if not self._buffer:
            return IncrementalLexResult()

        token_entries = self._tokenize_with_offsets(self._buffer)
        split_at = self._stable_split_offset(self._buffer, token_entries)

        emitted: List[Token] = []
        for token, _start, end in token_entries:
            if end > split_at:
                break
            if token.type in _SKIP_TOKEN_TYPES:
                continue
            emitted.append(self._with_absolute_position(token))

        consumed = self._buffer[:split_at]
        if consumed:
            self._advance_base_position(consumed)
            self._buffer = self._buffer[split_at:]

        candidates = self._partial_candidates(self._buffer)
        return IncrementalLexResult(
            tokens=emitted,
            remaining=self._buffer,
            partial_text=self._buffer,
            partial_candidates=candidates,
            lexically_continuable=self._partial_is_lexically_continuable(self._buffer, candidates),
        )

    @staticmethod
    def _tokenize_with_offsets(source: str) -> List[Tuple[Token, int, int]]:
        lexer = CangjieLexer(source, skip_ws=False, skip_comments=False)
        return lexer.tokenize_with_str_context()

    def _with_absolute_position(self, token: Token) -> Token:
        line = self._base_line + token.line - 1
        column = self._base_col + token.column - 1 if token.line == 1 else token.column
        return Token(token.type, token.text, line, column)

    def _advance_base_position(self, text: str) -> None:
        newline_count = text.count("\n")
        if newline_count == 0:
            self._base_col += len(text)
            return
        self._base_line += newline_count
        self._base_col = len(text) - text.rfind("\n")

    def _stable_split_offset(self, source: str, token_entries: Sequence[Tuple[Token, int, int]]) -> int:
        if not token_entries:
            return 0 if source else len(source)

        unstable_start = len(source)
        unclosed_start = self._unclosed_construct_start(source)
        if unclosed_start is not None:
            unstable_start = min(unstable_start, unclosed_start)

        _last_token, _last_start, last_end = token_entries[-1]
        if last_end == len(source):
            token_unstable_start = self._token_unstable_start(token_entries)
            if token_unstable_start is not None:
                unstable_start = min(unstable_start, token_unstable_start)

        return max(0, unstable_start)

    def _token_unstable_start(self, token_entries: Sequence[Tuple[Token, int, int]]) -> int | None:
        token, start, _end = token_entries[-1]
        text = token.text

        if token.type == TokenType.BACKTICK:
            return start
        if token.type == TokenType.UNKNOWN:
            return None
        if token.type == TokenType.IDENTIFIER or token.type.name.startswith("KW_"):
            return start
        if token.type in (TokenType.INTEGER_LITERAL, TokenType.FLOAT_LITERAL):
            return start
        if token.type == TokenType.OP_DOT and len(token_entries) >= 2:
            prev, prev_start, prev_end = token_entries[-2]
            if prev_end == start and prev.type == TokenType.INTEGER_LITERAL:
                return prev_start
        if text in _OPERATOR_PREFIXES:
            return start
        return None

    def _unclosed_construct_start(self, source: str) -> int | None:
        starts: List[int] = []
        block_start = self._unclosed_block_comment_start(source)
        if block_start is not None:
            starts.append(block_start)

        token_entries = self._tokenize_with_offsets(source)
        for token, start, end in token_entries:
            if token.type == TokenType.BACKTICK:
                starts.append(start)
                continue
            if end != len(source):
                continue
            if token.type == TokenType.COMMENT_LINE and not token.text.endswith(("\n", "\r")):
                starts.append(start)
            elif token.type == TokenType.STRING_LITERAL and not self._closed_string(token.text):
                starts.append(start)
            elif token.type == TokenType.MULTILINE_STRING and not self._closed_multiline_string(token.text):
                starts.append(start)
            elif token.type == TokenType.RUNE_LITERAL and not self._closed_rune(token.text):
                starts.append(start)

        return min(starts) if starts else None

    @staticmethod
    def _unclosed_block_comment_start(source: str) -> int | None:
        depth = 0
        first_open: int | None = None
        i = 0
        while i < len(source) - 1:
            pair = source[i:i + 2]
            if pair == "/*":
                if depth == 0:
                    first_open = i
                depth += 1
                i += 2
                continue
            if pair == "*/" and depth > 0:
                depth -= 1
                if depth == 0:
                    first_open = None
                i += 2
                continue
            i += 1
        return first_open if depth > 0 else None

    @staticmethod
    def _closed_string(text: str) -> bool:
        return len(text) >= 2 and text.endswith('"') and not text.endswith('\\"')

    @staticmethod
    def _closed_multiline_string(text: str) -> bool:
        return len(text) >= 6 and text.startswith('"""') and text.endswith('"""')

    @staticmethod
    def _closed_rune(text: str) -> bool:
        if len(text) < 3 or not text.startswith("r"):
            return False
        delim = text[1]
        return delim in {'"', "'"} and text.endswith(delim) and not text.endswith("\\" + delim)

    def _partial_candidates(self, partial: str) -> Set[TokenType]:
        if not partial:
            return set()
        if partial.isspace() or partial.startswith("//") or partial.startswith("/*"):
            return set()

        candidates: Set[TokenType] = set()
        if _IDENT_PREFIX_RE.match(partial):
            candidates.add(TokenType.IDENTIFIER)
            for word, token_type in KEYWORDS.items():
                if word.startswith(partial):
                    candidates.add(token_type)
            if partial == "r":
                candidates.add(TokenType.RUNE_LITERAL)
            return candidates

        if _NUMERIC_PREFIX_RE.match(partial):
            candidates.add(TokenType.INTEGER_LITERAL)
            if any(ch in partial for ch in ".eEf"):
                candidates.add(TokenType.FLOAT_LITERAL)
            return candidates

        if partial.startswith('"""'):
            return {TokenType.MULTILINE_STRING}
        if partial.startswith('"'):
            return {TokenType.STRING_LITERAL}
        if partial.startswith("r'") or partial.startswith('r"'):
            return {TokenType.RUNE_LITERAL}
        if partial.startswith("`"):
            return {TokenType.RAW_IDENTIFIER}

        for prefix, token_types in _OPERATOR_PREFIXES.items():
            if prefix.startswith(partial) or partial.startswith(prefix):
                candidates.update(token_types)
        if candidates:
            return candidates

        entries = self._tokenize_with_offsets(partial + " ")
        if entries:
            token = entries[0][0]
            if token.type not in _SKIP_TOKEN_TYPES:
                candidates.add(token.type)
        return candidates

    @staticmethod
    def _partial_is_lexically_continuable(partial: str, candidates: Set[TokenType]) -> bool:
        if not partial:
            return True
        if partial.isspace() or partial.startswith("//") or partial.startswith("/*"):
            return True
        return bool(candidates) and TokenType.UNKNOWN not in candidates
