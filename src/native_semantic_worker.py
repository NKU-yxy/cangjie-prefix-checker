#!/usr/bin/env python3
"""Lightweight semantic worker for the C++ competition entry.

The parent process owns cl100k decoding and syntax transitions.  Requests use
a little-endian uint32 byte length followed by raw token bytes; responses are
one byte (0=continuable, 1=error).  An incremental UTF-8 decoder also supports
token boundaries that split a multi-byte source character.
"""

from __future__ import annotations

import codecs
import os
import re
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.context_loader import find_context_path, load_context  # noqa: E402
from src.incremental_lexer import IncrementalLexer  # noqa: E402
from src.lexer import Token, TokenType  # noqa: E402
from src.prefix_semantic_checker import PrefixSemanticChecker  # noqa: E402


DECL_START = frozenset({
    TokenType.KW_VAR, TokenType.KW_LET, TokenType.KW_FUNC,
    TokenType.KW_CLASS, TokenType.KW_STRUCT, TokenType.KW_ENUM,
    TokenType.KW_INTERFACE, TokenType.KW_EXTEND,
})
GENERIC_DECL_START = frozenset({
    TokenType.KW_FUNC, TokenType.KW_CLASS, TokenType.KW_STRUCT,
    TokenType.KW_INTERFACE,
})
VALID_VAR_TAIL = frozenset({
    TokenType.COLON, TokenType.OP_ASSIGN, TokenType.SEMICOLON,
    TokenType.OP_PLUS_EQ, TokenType.OP_MINUS_EQ, TokenType.OP_MUL_EQ,
    TokenType.OP_DIV_EQ, TokenType.OP_MOD_EQ, TokenType.OP_POW_EQ,
    TokenType.OP_SHL_EQ, TokenType.OP_SHR_EQ, TokenType.OP_AND_EQ,
    TokenType.OP_XOR_EQ, TokenType.OP_OR_EQ, TokenType.OP_ANDAND_EQ,
    TokenType.OP_OROR_EQ, TokenType.OP_INC, TokenType.OP_DEC,
})
MALFORMED_GENERIC_CALL_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*<[^>{};\n]*\("
)


def _invalid_declaration_context(previous: list[Token], token_type: TokenType) -> bool:
    if previous and previous[-1].type in DECL_START:
        return token_type != TokenType.IDENTIFIER
    if len(previous) < 2 or previous[-2].type not in DECL_START:
        return False
    if previous[-1].type != TokenType.IDENTIFIER:
        return False
    keyword = previous[-2].type
    if keyword in (TokenType.KW_VAR, TokenType.KW_LET):
        return token_type not in VALID_VAR_TAIL
    if keyword == TokenType.KW_FUNC:
        return token_type not in {TokenType.LPAREN, TokenType.COLON, TokenType.OP_LT}
    return token_type not in {
        TokenType.COLON, TokenType.LBRACE, TokenType.OP_LT,
        TokenType.OP_LT_COLON,
    }


def _read_exact(stream, size: int, *, clean_eof: bool = False) -> bytes | None:
    """Read one framed request without relying on pipe read boundaries."""
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            if clean_eof and remaining == size:
                return None
            raise EOFError("truncated semantic worker request")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def main() -> int:
    context_arg = None
    try:
        context_index = sys.argv.index("--context")
        context_arg = sys.argv[context_index + 1]
    except (ValueError, IndexError):
        pass
    context_path = find_context_path(context_arg, runtime_dir=ROOT)
    normalized_context = load_context(context_path)
    checker = PrefixSemanticChecker(normalized_context)
    known_generic_heads = {
        str(item.get("name"))
        for section in ("functions", "classes", "interfaces")
        for item in normalized_context.get(section, [])
        if isinstance(item, dict) and item.get("name")
    }
    lexer = IncrementalLexer()
    utf8_decoder = codecs.getincrementaldecoder("utf-8")()
    previous_tokens: list[Token] = []
    source = ""
    failed = False
    input_stream = sys.stdin.buffer
    while True:
        try:
            header = _read_exact(input_stream, 4, clean_eof=True)
            if header is None:
                break
            payload_size = int.from_bytes(header, "little")
            payload = _read_exact(input_stream, payload_size)
            assert payload is not None
            fragment = utf8_decoder.decode(payload, final=False)
        except (EOFError, UnicodeDecodeError):
            return 1
        if failed:
            os.write(1, b"\x01")
            continue
        source += fragment
        lex_result = lexer.feed(fragment)
        for token in lex_result.tokens:
            if _invalid_declaration_context(previous_tokens, token.type):
                failed = True
                break
            if (
                token.type in (TokenType.IDENTIFIER, TokenType.RAW_IDENTIFIER)
                and previous_tokens
                and previous_tokens[-1].type in GENERIC_DECL_START
            ):
                known_generic_heads.add(token.text.strip("`"))
            previous_tokens.append(token)
            if len(previous_tokens) > 2:
                del previous_tokens[0]
        if not failed and lex_result.partial_candidates:
            failed = all(
                _invalid_declaration_context(previous_tokens, candidate)
                for candidate in lex_result.partial_candidates
            )
        if failed:
            os.write(1, b"\x01")
            continue
        if "(" in fragment and any(
            match.group(1) in known_generic_heads
            for match in MALFORMED_GENERIC_CALL_RE.finditer(source)
        ):
            os.write(1, b"\x01")
            failed = True
            continue
        result = checker.validate(source)
        failed = not result.ok
        os.write(1, b"\x01" if failed else b"\x00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
