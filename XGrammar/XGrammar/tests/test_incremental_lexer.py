import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.incremental_lexer import IncrementalLexer
from src.lexer import TokenType


def pairs(result):
    return [(token.type, token.text) for token in result.tokens]


class IncrementalLexerTests(unittest.TestCase):
    def test_identifier_split_across_fragments(self):
        lexer = IncrementalLexer()
        self.assertEqual(pairs(lexer.feed("Int")), [])
        result = lexer.feed("64 ")
        self.assertEqual(pairs(result), [(TokenType.IDENTIFIER, "Int64")])
        self.assertEqual(result.remaining, "")

    def test_float_split_across_fragments(self):
        lexer = IncrementalLexer()
        self.assertEqual(pairs(lexer.feed("123")), [])
        result = lexer.feed(".45 ")
        self.assertEqual(pairs(result), [(TokenType.FLOAT_LITERAL, "123.45")])

    def test_range_keeps_number_until_dot_is_disambiguated(self):
        lexer = IncrementalLexer()
        self.assertEqual(pairs(lexer.feed("0.")), [])
        result = lexer.feed(". ")
        self.assertEqual(pairs(result), [(TokenType.INTEGER_LITERAL, "0"), (TokenType.OP_RANGE, "..")])

    def test_inclusive_range_split(self):
        lexer = IncrementalLexer()
        self.assertEqual(pairs(lexer.feed(".")), [])
        result = lexer.feed(".= ")
        self.assertEqual(pairs(result), [(TokenType.OP_RANGE_INCL, "..=")])

    def test_string_split_across_fragments(self):
        lexer = IncrementalLexer()
        self.assertEqual(pairs(lexer.feed('"hel')), [])
        result = lexer.feed('lo" ')
        self.assertEqual(pairs(result), [(TokenType.STRING_LITERAL, '"hello"')])

    def test_line_comment_is_skipped_after_newline(self):
        lexer = IncrementalLexer()
        result = lexer.feed("// comment")
        self.assertEqual(pairs(result), [])
        self.assertEqual(result.remaining, "// comment")
        result = lexer.feed("\nvar ")
        self.assertEqual(pairs(result), [(TokenType.KW_VAR, "var")])

    def test_block_comment_is_skipped_after_close(self):
        lexer = IncrementalLexer()
        result = lexer.feed("/* comment")
        self.assertEqual(pairs(result), [])
        result = lexer.feed(" */let ")
        self.assertEqual(pairs(result), [(TokenType.KW_LET, "let")])

    def test_raw_identifier_split_across_fragments(self):
        lexer = IncrementalLexer()
        self.assertEqual(pairs(lexer.feed("`na")), [])
        result = lexer.feed("me` ")
        self.assertEqual(pairs(result), [(TokenType.RAW_IDENTIFIER, "`name`")])

    def test_stable_single_char_token_flushes_identifier(self):
        lexer = IncrementalLexer()
        self.assertEqual(pairs(lexer.feed("EUR")), [])
        result = lexer.feed("#")
        self.assertEqual(pairs(result), [(TokenType.IDENTIFIER, "EUR"), (TokenType.OP_HASH, "#")])

    def test_backtick_inside_string_is_not_raw_identifier(self):
        lexer = IncrementalLexer()
        result = lexer.feed('"`" ')
        self.assertEqual(pairs(result), [(TokenType.STRING_LITERAL, '"`"')])


if __name__ == "__main__":
    unittest.main()
