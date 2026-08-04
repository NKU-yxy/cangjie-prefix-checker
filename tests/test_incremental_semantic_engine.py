import unittest

from src.incremental_semantic_engine import (
    IncrementalSemanticEngine,
    PartialLexeme,
    TokenEvent,
)
from src.lexer import Token, TokenType


class IncrementalSemanticEngineTests(unittest.TestCase):
    def test_stable_tokens_are_consumed_once_and_symbols_are_indexed(self):
        engine = IncrementalSemanticEngine()
        for token_type, text in (
            (TokenType.KW_LET, "let"),
            (TokenType.IDENTIFIER, "answer"),
            (TokenType.COLON, ":"),
            (TokenType.IDENTIFIER, "Int64"),
        ):
            self.assertTrue(engine.accept(TokenEvent(Token(token_type, text, 1, 1))).ok)
        self.assertEqual(engine.accepted_events, 4)
        self.assertIn("answer", engine.visible_symbols)
        self.assertTrue(engine.can_complete_symbol("ans"))

    def test_checkpoint_and_rollback_restore_state(self):
        engine = IncrementalSemanticEngine()
        checkpoint = engine.checkpoint()
        engine.accept(TokenEvent(Token(TokenType.KW_VAR, "var", 1, 1)))
        engine.accept(TokenEvent(Token(TokenType.IDENTIFIER, "temporary", 1, 5)))
        self.assertIn("temporary", engine.visible_symbols)
        engine.rollback(checkpoint)
        self.assertNotIn("temporary", engine.visible_symbols)
        self.assertEqual(engine.accepted_events, 0)

    def test_probe_does_not_commit_partial_lexeme(self):
        engine = IncrementalSemanticEngine()
        before = engine.checkpoint()
        status = engine.probe(
            PartialLexeme("ans", frozenset({TokenType.IDENTIFIER})),
            "main(): Unit { let answer: Int64 = 1\n ans",
        )
        self.assertTrue(status.ok)
        after = engine.checkpoint()
        self.assertEqual(before.accepted_events, after.accepted_events)


if __name__ == "__main__":
    unittest.main()
