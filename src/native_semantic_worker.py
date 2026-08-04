#!/usr/bin/env python3
"""Lightweight semantic worker for the C++ competition entry.

The parent process owns cl100k decoding and syntax transitions.  Each input
line is one decoded fragment encoded as hexadecimal UTF-8 bytes; each output
line follows the public harness convention (0=continuable, 1=error).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.context_loader import find_context_path, load_context  # noqa: E402
from src.incremental_lexer import IncrementalLexer  # noqa: E402
from src.lexer import Token, TokenType  # noqa: E402
from src.prefix_semantic_checker import PrefixSemanticChecker  # noqa: E402


DECL_START = frozenset({
    TokenType.KW_VAR, TokenType.KW_LET, TokenType.KW_FUNC,
    TokenType.KW_CLASS, TokenType.KW_STRUCT, TokenType.KW_ENUM,
    TokenType.KW_INTERFACE, TokenType.KW_EXTEND,
})
VALID_VAR_TAIL = frozenset({
    TokenType.COLON, TokenType.OP_ASSIGN, TokenType.SEMICOLON,
    TokenType.OP_PLUS_EQ, TokenType.OP_MINUS_EQ, TokenType.OP_MUL_EQ,
    TokenType.OP_DIV_EQ, TokenType.OP_MOD_EQ, TokenType.OP_POW_EQ,
    TokenType.OP_SHL_EQ, TokenType.OP_SHR_EQ, TokenType.OP_AND_EQ,
    TokenType.OP_XOR_EQ, TokenType.OP_OR_EQ, TokenType.OP_ANDAND_EQ,
    TokenType.OP_OROR_EQ, TokenType.OP_INC, TokenType.OP_DEC,
})
DECLARED_GENERIC_HEAD_RE = re.compile(
    r"\b(?:func|class|struct|interface)\s+([A-Za-z_]\w*)"
)
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


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--context", default=None)
    args, _unknown = parser.parse_known_args()
    context_path = find_context_path(args.context, runtime_dir=str(ROOT))
    normalized_context = load_context(context_path)
    checker = PrefixSemanticChecker(normalized_context)
    known_generic_heads = {
        str(item.get("name"))
        for section in ("functions", "classes", "interfaces")
        for item in normalized_context.get(section, [])
        if isinstance(item, dict) and item.get("name")
    }
    lexer = IncrementalLexer()
    previous_tokens: list[Token] = []
    source_parts: list[str] = []
    failed = False
    for line in sys.stdin:
        if failed:
            print(1, flush=True)
            continue
        try:
            fragment = bytes.fromhex(line.strip()).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            print(1, flush=True)
            failed = True
            continue
        source_parts.append(fragment)
        source = "".join(source_parts)
        known_generic_heads.update(DECLARED_GENERIC_HEAD_RE.findall(source))
        lex_result = lexer.feed(fragment)
        for token in lex_result.tokens:
            if _invalid_declaration_context(previous_tokens, token.type):
                failed = True
                break
            previous_tokens.append(token)
            if len(previous_tokens) > 2:
                del previous_tokens[0]
        if not failed and lex_result.partial_candidates:
            failed = all(
                _invalid_declaration_context(previous_tokens, candidate)
                for candidate in lex_result.partial_candidates
            )
        if failed:
            print(1, flush=True)
            continue
        if any(
            match.group(1) in known_generic_heads
            for match in MALFORMED_GENERIC_CALL_RE.finditer(source)
        ):
            print(1, flush=True)
            failed = True
            continue
        result = checker.validate(source)
        failed = not result.ok
        print(1 if failed else 0, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
