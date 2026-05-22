"""
Cangjie Lexer — tokenizes Cangjie source code into lexical tokens.
"""

import re
from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional


class TokenType(Enum):
    """Cangjie lexical token types."""
    # Keywords
    KW_FUNC = auto()
    KW_VAR = auto()
    KW_LET = auto()
    KW_MUT = auto()
    KW_CLASS = auto()
    KW_STRUCT = auto()
    KW_ENUM = auto()
    KW_INTERFACE = auto()
    KW_EXTEND = auto()
    KW_IMPORT = auto()
    KW_PACKAGE = auto()
    KW_IF = auto()
    KW_ELSE = auto()
    KW_FOR = auto()
    KW_WHILE = auto()
    KW_DO = auto()
    KW_BREAK = auto()
    KW_CONTINUE = auto()
    KW_RETURN = auto()
    KW_THROW = auto()
    KW_TRY = auto()
    KW_CATCH = auto()
    KW_FINALLY = auto()
    KW_MATCH = auto()
    KW_CASE = auto()
    KW_IN = auto()
    KW_IS = auto()
    KW_AS = auto()
    KW_THIS = auto()
    KW_SUPER = auto()
    KW_OPERATOR = auto()
    KW_TRUE = auto()
    KW_FALSE = auto()
    KW_NEW = auto()
    KW_SPAWN = auto()
    KW_SYNC = auto()
    KW_WHERE = auto()
    KW_TYPE = auto()
    KW_UNSAFE = auto()
    KW_FOREIGN = auto()
    KW_MACRO = auto()
    KW_QUOTE = auto()

    # Literals
    IDENTIFIER = auto()
    RAW_IDENTIFIER = auto()
    INTEGER_LITERAL = auto()
    FLOAT_LITERAL = auto()
    STRING_LITERAL = auto()
    MULTILINE_STRING = auto()
    RUNE_LITERAL = auto()

    # Operators (multi-char checked first)
    OP_EQ = auto()           # ==
    OP_NE = auto()           # !=
    OP_LE = auto()           # <=
    OP_GE = auto()           # >=
    OP_AND = auto()          # &&
    OP_OR = auto()           # ||
    OP_COALESCE = auto()     # ??
    OP_PIPE = auto()         # |>
    OP_COMPOSE = auto()      # ~>
    OP_RANGE_INCL = auto()   # ..=
    OP_RANGE = auto()        # ..
    OP_SHL = auto()          # <<
    OP_SHR = auto()          # >>
    OP_POW = auto()          # **
    OP_ARROW = auto()        # ->
    OP_FAT_ARROW = auto()    # =>
    OP_PLUS_EQ = auto()      # +=
    OP_MINUS_EQ = auto()     # -=
    OP_MUL_EQ = auto()       # *=
    OP_DIV_EQ = auto()       # /=
    OP_MOD_EQ = auto()       # %=
    OP_POW_EQ = auto()       # **=
    OP_SHL_EQ = auto()       # <<=
    OP_SHR_EQ = auto()       # >>=
    OP_AND_EQ = auto()       # &=
    OP_XOR_EQ = auto()       # ^=
    OP_OR_EQ = auto()        # |=
    OP_ANDAND_EQ = auto()    # &&=
    OP_OROR_EQ = auto()      # ||=
    OP_INC = auto()          # ++
    OP_DEC = auto()          # --
    OP_DOT = auto()          # .

    # Single-char operators & punctuation
    OP_PLUS = auto()         # +
    OP_MINUS = auto()        # -
    OP_STAR = auto()         # *
    OP_SLASH = auto()        # /
    OP_PERCENT = auto()      # %
    OP_LT = auto()           # <
    OP_GT = auto()           # >
    OP_NOT = auto()          # !
    OP_BIT_AND = auto()      # &
    OP_BIT_OR = auto()       # |
    OP_BIT_XOR = auto()      # ^
    OP_BIT_NOT = auto()      # ~
    OP_ASSIGN = auto()       # =
    OP_QUESTION = auto()     # ?
    OP_AT = auto()           # @
    OP_DOLLAR = auto()       # $
    OP_HASH = auto()         # #

    # Delimiters
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    SEMICOLON = auto()
    COLON = auto()
    COMMA = auto()
    BACKTICK = auto()

    # Whitespace / special
    WS = auto()
    NEWLINE = auto()
    COMMENT_LINE = auto()
    COMMENT_BLOCK = auto()
    EOF = auto()
    UNKNOWN = auto()


@dataclass
class Token:
    """A lexical token with type, text, and position."""
    type: TokenType
    text: str
    line: int
    column: int

    def __repr__(self):
        return f"Token({self.type.name}, {self.text!r}, {self.line}:{self.column})"


# ---------------------------------------------------------------
# Keyword map
# ---------------------------------------------------------------
KEYWORDS: dict[str, TokenType] = {
    "func": TokenType.KW_FUNC,
    "var": TokenType.KW_VAR,
    "let": TokenType.KW_LET,
    "mut": TokenType.KW_MUT,
    "class": TokenType.KW_CLASS,
    "struct": TokenType.KW_STRUCT,
    "enum": TokenType.KW_ENUM,
    "interface": TokenType.KW_INTERFACE,
    "extend": TokenType.KW_EXTEND,
    "import": TokenType.KW_IMPORT,
    "package": TokenType.KW_PACKAGE,
    "if": TokenType.KW_IF,
    "else": TokenType.KW_ELSE,
    "for": TokenType.KW_FOR,
    "while": TokenType.KW_WHILE,
    "do": TokenType.KW_DO,
    "break": TokenType.KW_BREAK,
    "continue": TokenType.KW_CONTINUE,
    "return": TokenType.KW_RETURN,
    "throw": TokenType.KW_THROW,
    "try": TokenType.KW_TRY,
    "catch": TokenType.KW_CATCH,
    "finally": TokenType.KW_FINALLY,
    "match": TokenType.KW_MATCH,
    "case": TokenType.KW_CASE,
    "in": TokenType.KW_IN,
    "is": TokenType.KW_IS,
    "as": TokenType.KW_AS,
    "this": TokenType.KW_THIS,
    "super": TokenType.KW_SUPER,
    "operator": TokenType.KW_OPERATOR,
    "true": TokenType.KW_TRUE,
    "false": TokenType.KW_FALSE,
    "new": TokenType.KW_NEW,
    "spawn": TokenType.KW_SPAWN,
    "sync": TokenType.KW_SYNC,
    "where": TokenType.KW_WHERE,
    "type": TokenType.KW_TYPE,
    "unsafe": TokenType.KW_UNSAFE,
    "foreign": TokenType.KW_FOREIGN,
    "macro": TokenType.KW_MACRO,
    "quote": TokenType.KW_QUOTE,
}

# Contextual keywords (can be identifiers, but also have special meaning)
CONTEXTUAL_KEYWORDS: set[str] = {
    "abstract", "open", "override", "private", "protected",
    "public", "redef", "get", "set", "sealed", "internal",
}

# Primitive type names (treated as identifiers in lexer, semantics in checker)
PRIMITIVE_TYPES: set[str] = {
    "Int8", "Int16", "Int32", "Int64", "IntNative",
    "UInt8", "UInt16", "UInt32", "UInt64", "UIntNative",
    "Float16", "Float32", "Float64",
    "Bool", "Rune", "String", "Unit", "Nothing",
    "VArray", "This",
}


class CangjieLexer:
    """Lexer for the Cangjie programming language."""

    # Token patterns ordered by priority (longest match wins in each category)
    TOKEN_SPECS: list[tuple[str, TokenType | None]] = [
        # --- Whitespace & comments (skip or capture as needed) ---
        (r'[ \t]+', TokenType.WS),
        (r'\n', TokenType.NEWLINE),
        (r'\r\n?', TokenType.NEWLINE),

        # --- Comments ---
        (r'//[^\n\r]*', TokenType.COMMENT_LINE),
        (r'/\*.*?\*/', TokenType.COMMENT_BLOCK),  # simplified, no nesting in regex

        # --- Multi-character operators (longest first) ---
        (r'\.\.\.', TokenType.OP_RANGE_INCL),  # actually ... is variadic, but ..= is range_incl
        (r'\.\.=', TokenType.OP_RANGE_INCL),
        (r'\.\.', TokenType.OP_RANGE),
        (r'==', TokenType.OP_EQ),
        (r'!=', TokenType.OP_NE),
        (r'<=', TokenType.OP_LE),
        (r'>=', TokenType.OP_GE),
        (r'&&=', TokenType.OP_ANDAND_EQ),
        (r'\|\|=', TokenType.OP_OROR_EQ),
        (r'&&', TokenType.OP_AND),
        (r'\|\|', TokenType.OP_OR),
        (r'\?\?', TokenType.OP_COALESCE),
        (r'\|>', TokenType.OP_PIPE),
        (r'~>', TokenType.OP_COMPOSE),
        (r'=>', TokenType.OP_FAT_ARROW),
        (r'->', TokenType.OP_ARROW),
        (r'<<=', TokenType.OP_SHL_EQ),
        (r'>>=', TokenType.OP_SHR_EQ),
        (r'<<', TokenType.OP_SHL),
        (r'>>', TokenType.OP_SHR),
        (r'\*\*=', TokenType.OP_POW_EQ),
        (r'\*\*', TokenType.OP_POW),
        (r'\+=', TokenType.OP_PLUS_EQ),
        (r'-=', TokenType.OP_MINUS_EQ),
        (r'\*=', TokenType.OP_MUL_EQ),
        (r'/=', TokenType.OP_DIV_EQ),
        (r'%=', TokenType.OP_MOD_EQ),
        (r'&=', TokenType.OP_AND_EQ),
        (r'\^=', TokenType.OP_XOR_EQ),
        (r'\|=', TokenType.OP_OR_EQ),
        (r'\+\+', TokenType.OP_INC),
        (r'--', TokenType.OP_DEC),

        # --- Multi-line string ("""...""") ---
        (r'"""', TokenType.MULTILINE_STRING),

        # --- String literal ("...") ---
        (r'"', TokenType.STRING_LITERAL),

        # --- Rune literal (r'...' or r"...") ---
        (r"r'", TokenType.RUNE_LITERAL),
        (r'r"', TokenType.RUNE_LITERAL),

        # --- Raw identifier (`...`) ---
        (r'`[a-zA-Z_][a-zA-Z0-9_]*`', TokenType.RAW_IDENTIFIER),

        # --- Float literal ---
        (r'\d+\.\d+([eE][+\-]?\d+)?(f16|f32|f64)?', TokenType.FLOAT_LITERAL),
        (r'\d+[eE][+\-]?\d+(f16|f32|f64)?', TokenType.FLOAT_LITERAL),

        # --- Integer literal with suffix ---
        (r'0[xX][0-9a-fA-F]+(i8|i16|i32|i64|u8|u16|u32|u64)?', TokenType.INTEGER_LITERAL),
        (r'0[oO][0-7]+(i8|i16|i32|i64|u8|u16|u32|u64)?', TokenType.INTEGER_LITERAL),
        (r'0[bB][01]+(i8|i16|i32|i64|u8|u16|u32|u64)?', TokenType.INTEGER_LITERAL),
        (r'\d+(i8|i16|i32|i64|u8|u16|u32|u64)?', TokenType.INTEGER_LITERAL),

        # --- Identifier or keyword ---
        (r'[a-zA-Z_][a-zA-Z0-9_]*', TokenType.IDENTIFIER),

        # --- Single-character operators & delimiters ---
        (r'\(', TokenType.LPAREN),
        (r'\)', TokenType.RPAREN),
        (r'\{', TokenType.LBRACE),
        (r'\}', TokenType.RBRACE),
        (r'\[', TokenType.LBRACKET),
        (r'\]', TokenType.RBRACKET),
        (r';', TokenType.SEMICOLON),
        (r':', TokenType.COLON),
        (r',', TokenType.COMMA),
        (r'\.', TokenType.OP_DOT),
        (r'\+', TokenType.OP_PLUS),
        (r'-', TokenType.OP_MINUS),
        (r'\*', TokenType.OP_STAR),
        (r'/', TokenType.OP_SLASH),
        (r'%', TokenType.OP_PERCENT),
        (r'<', TokenType.OP_LT),
        (r'>', TokenType.OP_GT),
        (r'!', TokenType.OP_NOT),
        (r'&', TokenType.OP_BIT_AND),
        (r'\|', TokenType.OP_BIT_OR),
        (r'\^', TokenType.OP_BIT_XOR),
        (r'~', TokenType.OP_BIT_NOT),
        (r'=', TokenType.OP_ASSIGN),
        (r'\?', TokenType.OP_QUESTION),
        (r'@', TokenType.OP_AT),
        (r'\$', TokenType.OP_DOLLAR),
        (r'#', TokenType.OP_HASH),
        (r'`', TokenType.BACKTICK),

        # --- Unknown (catch-all single char) ---
        (r'.', TokenType.UNKNOWN),
    ]

    def __init__(self, source: str, *, skip_ws: bool = True, skip_comments: bool = True):
        self.source = source
        self.skip_ws = skip_ws
        self.skip_comments = skip_comments
        self._pos = 0
        self._line = 1
        self._col = 1

    def _classify_identifier(self, text: str) -> TokenType:
        """Classify an identifier token as keyword, primitive type, or plain identifier."""
        if text in KEYWORDS:
            return KEYWORDS[text]
        return TokenType.IDENTIFIER

    def _match(self, pattern: str) -> Optional[re.Match]:
        return re.compile(pattern).match(self.source, self._pos)

    def tokenize(self) -> List[Token]:
        """Tokenize the entire source and return list of tokens."""
        tokens = []
        for token in self._generate():
            if self.skip_ws and token.type == TokenType.WS:
                continue
            if self.skip_comments and token.type in (TokenType.COMMENT_LINE, TokenType.COMMENT_BLOCK):
                continue
            if self.skip_ws and token.type == TokenType.NEWLINE:
                # Keep newlines that are statement terminators for syntax checking
                # But collapse consecutive newlines
                if tokens and tokens[-1].type == TokenType.NEWLINE:
                    continue
            tokens.append(token)
        return tokens

    def tokenize_with_str_context(self) -> List[tuple[Token, int, int]]:
        """
        Tokenize and return tokens with their (start, end) byte offsets
        in the original source.

        Returns:
            List of (Token, start_offset, end_offset)
        """
        result = []
        for token in self._generate():
            if self.skip_ws and token.type == TokenType.WS:
                continue
            if self.skip_comments and token.type in (TokenType.COMMENT_LINE, TokenType.COMMENT_BLOCK):
                continue
            # Get current position as the start offset
            # We'll track end offset separately
            result.append((token, self._pos - len(token.text), self._pos))
        return result

    def _generate(self):
        """Generator that yields tokens one at a time."""
        while self._pos < len(self.source):
            matched = False
            for pattern, token_type in self.TOKEN_SPECS:
                m = self._match(pattern)
                if m:
                    text = m.group(0)
                    start_line = self._line
                    start_col = self._col

                    # Classify identifier-like tokens
                    actual_type = token_type
                    if token_type == TokenType.IDENTIFIER:
                        actual_type = self._classify_identifier(text)

                    # Handle special multi-line string scanning
                    if token_type == TokenType.MULTILINE_STRING:
                        # Scan until closing """
                        end = self.source.find('"""', self._pos + 3)
                        if end == -1:
                            text = self.source[self._pos:]
                        else:
                            text = self.source[self._pos:end + 3]
                            # Update position tracking
                            newlines = text.count('\n')
                            if newlines > 0:
                                self._line += newlines
                                last_nl = text.rfind('\n')
                                self._col = len(text) - last_nl
                            else:
                                self._col += len(text)
                            self._pos += len(text)
                            yield Token(TokenType.MULTILINE_STRING, text, start_line, start_col)
                            matched = True
                            break

                    # Handle string literal scanning
                    if token_type == TokenType.STRING_LITERAL:
                        text = self._scan_string(start_line, start_col)
                        if text is not None:
                            self._pos += len(text)
                            newlines = text.count('\n')
                            self._line += newlines
                            if newlines > 0:
                                last_nl = text.rfind('\n')
                                self._col = len(text) - last_nl
                            else:
                                self._col += len(text)
                            yield Token(TokenType.STRING_LITERAL, text, start_line, start_col)
                            matched = True
                            break
                        else:
                            # Unterminated string — consume rest of line
                            end = self.source.find('\n', self._pos)
                            if end == -1:
                                end = len(self.source)
                            text = self.source[self._pos:end]
                            self._line += text.count('\n')
                            self._col += len(text)
                            self._pos += len(text)
                            yield Token(TokenType.STRING_LITERAL, text, start_line, start_col)
                            matched = True
                            break

                    # Handle rune literal scanning
                    if token_type == TokenType.RUNE_LITERAL:
                        text = self._scan_rune(start_line, start_col)
                        if text is not None:
                            self._pos += len(text)
                            self._col += len(text)
                            yield Token(TokenType.RUNE_LITERAL, text, start_line, start_col)
                            matched = True
                            break
                        else:
                            # Unterminated rune — consume rest of line
                            end = self.source.find('\n', self._pos)
                            if end == -1:
                                end = len(self.source)
                            text = self.source[self._pos:end]
                            self._line += text.count('\n')
                            self._col += len(text)
                            self._pos += len(text)
                            yield Token(TokenType.RUNE_LITERAL, text, start_line, start_col)
                            matched = True
                            break

                    # Handle block comment nesting
                    if token_type == TokenType.COMMENT_BLOCK and '/*' in text:
                        text = self._scan_block_comment()
                        newlines = text.count('\n')
                        self._line += newlines
                        if newlines > 0:
                            last_nl = text.rfind('\n')
                            self._col = len(text) - last_nl
                        else:
                            self._col += len(text)
                        self._pos += len(text)
                        yield Token(TokenType.COMMENT_BLOCK, text, start_line, start_col)
                        matched = True
                        break

                    # Update position
                    newlines = text.count('\n')
                    self._line += newlines
                    if newlines > 0:
                        last_nl = text.rfind('\n')
                        self._col = len(text) - last_nl
                    else:
                        self._col += len(text)

                    self._pos += len(text)
                    yield Token(actual_type, text, start_line, start_col)
                    matched = True
                    break

            if not matched:
                # Should never happen with the catch-all '.' pattern
                ch = self.source[self._pos]
                token = Token(TokenType.UNKNOWN, ch, self._line, self._col)
                self._pos += 1
                self._col += 1
                yield token

    def _scan_string(self, start_line: int, start_col: int) -> Optional[str]:
        """Scan a string literal starting with an opening double-quote."""
        pos = self._pos + 1  # skip opening "
        text_parts = ['"']

        while pos < len(self.source):
            ch = self.source[pos]
            if ch == '"':
                text_parts.append('"')
                return ''.join(text_parts)
            elif ch == '\\':
                text_parts.append(ch)
                pos += 1
                if pos < len(self.source):
                    text_parts.append(self.source[pos])
                pos += 1
            elif ch == '\n':
                # Unterminated string
                return None
            else:
                text_parts.append(ch)
                pos += 1
        return None  # unterminated

    def _scan_rune(self, start_line: int, start_col: int) -> Optional[str]:
        """Scan a rune literal r'x' or r\"x\"."""
        delimiter = self.source[self._pos + 1]  # ' or "
        pos = self._pos + 2  # skip r and opening quote
        text_parts = ['r', delimiter]

        while pos < len(self.source):
            ch = self.source[pos]
            if ch == delimiter:
                text_parts.append(delimiter)
                return ''.join(text_parts)
            elif ch == '\\':
                text_parts.append(ch)
                pos += 1
                if pos < len(self.source):
                    text_parts.append(self.source[pos])
                pos += 1
            elif ch == '\n':
                return None
            else:
                text_parts.append(ch)
                pos += 1
        return None

    def _scan_block_comment(self) -> str:
        """Scan a block comment with nesting support."""
        depth = 1
        pos = self._pos + 2  # skip opening /*
        text_parts = ['/*']

        while pos < len(self.source) and depth > 0:
            if pos + 1 < len(self.source) and self.source[pos:pos+2] == '/*':
                depth += 1
                text_parts.append('/*')
                pos += 2
            elif pos + 1 < len(self.source) and self.source[pos:pos+2] == '*/':
                depth -= 1
                text_parts.append('*/')
                pos += 2
            else:
                text_parts.append(self.source[pos])
                pos += 1

        return ''.join(text_parts)
