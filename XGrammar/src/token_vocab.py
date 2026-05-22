"""
Cangjie Token Vocabulary — maps lexer TokenType to XGrammar-compatible token IDs.

Each token type gets a unique string name in the vocabulary. The GBNF grammar
references these names as string literals. The lexer maps source tokens to their
corresponding vocab indices, and GrammarMatcher.accept_token(token_id) validates
the token sequence.
"""

from xgrammar import TokenizerInfo, VocabType

from .lexer import TokenType

# ── TokenType → vocab string mapping ──────────────────────────────────────────

TOKEN_TYPE_TO_VOCAB: dict[TokenType, str] = {
    # Keywords
    TokenType.KW_FUNC:       "FUNC",
    TokenType.KW_VAR:        "VAR",
    TokenType.KW_LET:        "LET",
    TokenType.KW_MUT:        "MUT",
    TokenType.KW_CLASS:      "CLASS",
    TokenType.KW_STRUCT:     "STRUCT",
    TokenType.KW_ENUM:       "ENUM",
    TokenType.KW_INTERFACE:  "INTERFACE",
    TokenType.KW_EXTEND:     "EXTEND",
    TokenType.KW_IMPORT:     "IMPORT",
    TokenType.KW_PACKAGE:    "PACKAGE",
    TokenType.KW_IF:         "IF",
    TokenType.KW_ELSE:       "ELSE",
    TokenType.KW_FOR:        "FOR",
    TokenType.KW_WHILE:      "WHILE",
    TokenType.KW_DO:         "DO",
    TokenType.KW_BREAK:      "BREAK",
    TokenType.KW_CONTINUE:   "CONTINUE",
    TokenType.KW_RETURN:     "RETURN",
    TokenType.KW_THROW:      "THROW",
    TokenType.KW_TRY:        "TRY",
    TokenType.KW_CATCH:      "CATCH",
    TokenType.KW_FINALLY:    "FINALLY",
    TokenType.KW_MATCH:      "MATCH",
    TokenType.KW_CASE:       "CASE",
    TokenType.KW_IN:         "IN",
    TokenType.KW_IS:         "IS",
    TokenType.KW_AS:         "AS",
    TokenType.KW_THIS:       "THIS",
    TokenType.KW_SUPER:      "SUPER",
    TokenType.KW_OPERATOR:   "OPERATOR",
    TokenType.KW_TRUE:       "TRUE",
    TokenType.KW_FALSE:      "FALSE",
    TokenType.KW_NEW:        "NEW",
    TokenType.KW_SPAWN:      "SPAWN",
    TokenType.KW_SYNC:       "SYNC",
    TokenType.KW_WHERE:      "WHERE",
    TokenType.KW_TYPE:       "TYPE",
    TokenType.KW_UNSAFE:     "UNSAFE",
    TokenType.KW_FOREIGN:    "FOREIGN",
    TokenType.KW_MACRO:      "MACRO",
    TokenType.KW_QUOTE:      "QUOTE",

    # Identifier placeholders
    TokenType.IDENTIFIER:     "IDENT",
    TokenType.RAW_IDENTIFIER: "RAW_IDENT",

    # Literal placeholders
    TokenType.INTEGER_LITERAL: "INT_LIT",
    TokenType.FLOAT_LITERAL:   "FLOAT_LIT",
    TokenType.STRING_LITERAL:  "STR_LIT",
    TokenType.MULTILINE_STRING: "ML_STR_LIT",
    TokenType.RUNE_LITERAL:    "RUNE_LIT",

    # Multi-character operators
    TokenType.OP_EQ:          "EQ",
    TokenType.OP_NE:          "NE",
    TokenType.OP_LE:          "LE",
    TokenType.OP_GE:          "GE",
    TokenType.OP_AND:         "AND",
    TokenType.OP_OR:          "OR",
    TokenType.OP_COALESCE:    "COALESCE",
    TokenType.OP_PIPE:        "PIPE",
    TokenType.OP_COMPOSE:     "COMPOSE",
    TokenType.OP_RANGE_INCL:  "RANGE_INCL",
    TokenType.OP_RANGE:       "RANGE",
    TokenType.OP_SHL:         "SHL",
    TokenType.OP_SHR:         "SHR",
    TokenType.OP_POW:         "POW",
    TokenType.OP_ARROW:       "ARROW",
    TokenType.OP_FAT_ARROW:   "FAT_ARROW",
    TokenType.OP_PLUS_EQ:     "PLUS_EQ",
    TokenType.OP_MINUS_EQ:    "MINUS_EQ",
    TokenType.OP_MUL_EQ:      "MUL_EQ",
    TokenType.OP_DIV_EQ:      "DIV_EQ",
    TokenType.OP_MOD_EQ:      "MOD_EQ",
    TokenType.OP_POW_EQ:      "POW_EQ",
    TokenType.OP_SHL_EQ:      "SHL_EQ",
    TokenType.OP_SHR_EQ:      "SHR_EQ",
    TokenType.OP_AND_EQ:      "AND_EQ",
    TokenType.OP_XOR_EQ:      "XOR_EQ",
    TokenType.OP_OR_EQ:       "OR_EQ",
    TokenType.OP_ANDAND_EQ:   "ANDAND_EQ",
    TokenType.OP_OROR_EQ:     "OROR_EQ",
    TokenType.OP_INC:         "INC",
    TokenType.OP_DEC:         "DEC",
    TokenType.OP_DOT:         "DOT",

    # Single-character operators
    TokenType.OP_PLUS:        "PLUS",
    TokenType.OP_MINUS:       "MINUS",
    TokenType.OP_STAR:        "STAR",
    TokenType.OP_SLASH:       "SLASH",
    TokenType.OP_PERCENT:     "PERCENT",
    TokenType.OP_LT:          "LT",
    TokenType.OP_GT:          "GT",
    TokenType.OP_NOT:         "NOT",
    TokenType.OP_BIT_AND:     "BIT_AND",
    TokenType.OP_BIT_OR:      "BIT_OR",
    TokenType.OP_BIT_XOR:     "BIT_XOR",
    TokenType.OP_BIT_NOT:     "BIT_NOT",
    TokenType.OP_ASSIGN:      "ASSIGN",
    TokenType.OP_QUESTION:    "QUESTION",
    TokenType.OP_AT:          "AT",
    TokenType.OP_DOLLAR:      "DOLLAR",
    TokenType.OP_HASH:        "HASH",

    # Delimiters
    TokenType.LPAREN:    "LPAREN",
    TokenType.RPAREN:    "RPAREN",
    TokenType.LBRACE:    "LBRACE",
    TokenType.RBRACE:    "RBRACE",
    TokenType.LBRACKET:  "LBRACKET",
    TokenType.RBRACKET:  "RBRACKET",
    TokenType.SEMICOLON: "SEMICOLON",
    TokenType.COLON:     "COLON",
    TokenType.COMMA:     "COMMA",

    # Whitespace
    TokenType.WS:      "WS",
    TokenType.NEWLINE: "NEWLINE",

    # Special
    TokenType.BACKTICK: "BACKTICK",
    TokenType.UNKNOWN:  "UNKNOWN",
}


def build_vocab_list() -> list[str]:
    """Build ordered vocabulary list from the mapping.

    Order is: keywords first, then identifiers, literals, operators, delimiters,
    whitespace.  This keeps the vocab deterministic and organized.

    Returns:
        List of vocab strings, where the index of each string is its token ID.
    """
    seen: set[str] = set()
    vocab: list[str] = []

    def add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            vocab.append(name)

    # Keywords
    for t in TokenType:
        if t.name.startswith("KW_"):
            add(TOKEN_TYPE_TO_VOCAB[t])

    # Identifier placeholders
    add("IDENT")
    add("RAW_IDENT")

    # Literal placeholders
    for t in (TokenType.INTEGER_LITERAL, TokenType.FLOAT_LITERAL,
              TokenType.STRING_LITERAL, TokenType.MULTILINE_STRING,
              TokenType.RUNE_LITERAL):
        add(TOKEN_TYPE_TO_VOCAB[t])

    # Operators (multi-char first, then single-char)
    for t in TokenType:
        if t.name.startswith("OP_"):
            add(TOKEN_TYPE_TO_VOCAB[t])

    # Delimiters
    for t in (TokenType.LPAREN, TokenType.RPAREN, TokenType.LBRACE,
              TokenType.RBRACE, TokenType.LBRACKET, TokenType.RBRACKET,
              TokenType.SEMICOLON, TokenType.COLON, TokenType.COMMA):
        add(TOKEN_TYPE_TO_VOCAB[t])

    # Whitespace
    add("WS")
    add("NEWLINE")

    # Special
    add("BACKTICK")
    add("UNKNOWN")

    return vocab


# ── Build the vocabulary and TokenizerInfo ────────────────────────────────────

_vocab_list = build_vocab_list()

# Public mapping: TokenType → token_id
TOKEN_ID_MAP: dict[TokenType, int] = {
    t: _vocab_list.index(name)
    for t, name in TOKEN_TYPE_TO_VOCAB.items()
}

# The TokenizerInfo instance used by GrammarCompiler
TOKENIZER_INFO = TokenizerInfo(_vocab_list, vocab_type=VocabType.RAW)

# Vocab size for reference
VOCAB_SIZE = len(_vocab_list)


def get_token_id(token_type: TokenType) -> int:
    """Get the XGrammar token ID for a Cangjie TokenType.

    Returns the corresponding vocab index, or the IDENT fallback if the token
    type is not explicitly mapped.
    """
    return TOKEN_ID_MAP.get(token_type, TOKEN_ID_MAP[TokenType.IDENTIFIER])


def get_token_name(token_type: TokenType) -> str:
    """Get the vocab string name for a Cangjie TokenType."""
    return TOKEN_TYPE_TO_VOCAB.get(token_type, "IDENT")


def token_type_to_id(token_type: TokenType) -> int:
    """Map a Cangjie TokenType to its XGrammar token ID.

    Unknown token types fall back to the IDENT token ID.
    """
    return TOKEN_ID_MAP.get(token_type, TOKEN_ID_MAP[TokenType.IDENTIFIER])
