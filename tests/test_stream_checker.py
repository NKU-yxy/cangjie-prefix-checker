import os
import random
import unittest

from src.batch_semantic_validator import SemanticValidationResult
from src.stream_checker import CangjieStreamChecker


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT = os.path.join(ROOT, "context.json")


class _SemanticSpy:
    def __init__(self):
        self.sources = []

    def validate_prefix(self, source):
        self.sources.append(source)
        return SemanticValidationResult(ok=True)


class StreamCheckerTests(unittest.TestCase):
    def test_checkpoint_mode_only_runs_batch_at_commit_suffix(self):
        checker = CangjieStreamChecker(context_path=CONTEXT, semantic_mode="checkpoint")
        spy = _SemanticSpy()
        checker._semantic = spy

        self.assertTrue(checker.feed_text("func").ok)
        self.assertEqual([], spy.sources)
        self.assertTrue(checker.feed_text(" f(): Int64 {").ok)
        self.assertEqual([], spy.sources)
        self.assertTrue(checker.feed_text("\n").ok)
        self.assertEqual(1, len(spy.sources))

    def test_fast_mode_never_initializes_batch_validator(self):
        checker = CangjieStreamChecker(context_path=CONTEXT, semantic_mode="fast")
        source = "func f(): Int64 { return 1 }\n"
        for char in source:
            self.assertTrue(checker.feed_text(char).ok, checker.last_error)
        self.assertFalse(checker._semantic.initialized)

    def test_default_mode_is_zero_lark_fast_path(self):
        checker = CangjieStreamChecker(context_path=CONTEXT)
        self.assertEqual(checker._semantic_mode, "fast")
        self.assertTrue(checker.feed_text("main(): Unit { return }").ok)
        self.assertFalse(checker._semantic.initialized)

    def test_declaration_context_keeps_constant_history(self):
        checker = CangjieStreamChecker(context_path=CONTEXT, semantic_mode="fast")
        source = "func f(): Int64 { let x: Int64 = 1; return x }\n"
        for char in source:
            self.assertTrue(checker.feed_text(char).ok, checker.last_error)
            self.assertLessEqual(len(checker._previous_tokens), 2)

    def test_unknown_semantic_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            CangjieStreamChecker(context_path=CONTEXT, semantic_mode="unknown")

    def test_semantics_do_not_depend_on_fragment_boundaries(self):
        valid = (
            "interface Value { func get(): Int64 }\n"
            "class Box <: Value { var x: Int64 "
            "init(v: Int64) { this.x = v } "
            "func get(): Int64 { x } }\n"
            "main(): Unit { let b: Box = Box(1); println(b.get()) }\n"
        )
        invalid = "main(): Unit { let xs: Array<Int64> = [1, \"bad\"]\n"

        def partitions(source):
            yield list(source)
            yield [source]
            rng = random.Random(20260804)
            chunks = []
            index = 0
            while index < len(source):
                width = rng.randint(1, 9)
                chunks.append(source[index : index + width])
                index += width
            yield chunks

        for chunks in partitions(valid):
            checker = CangjieStreamChecker(
                context_path=CONTEXT,
                semantic_mode="fast",
            )
            for chunk in chunks:
                self.assertTrue(checker.feed_text(chunk).ok, checker.last_error)

        for chunks in partitions(invalid):
            checker = CangjieStreamChecker(
                context_path=CONTEXT,
                semantic_mode="fast",
            )
            status = None
            for chunk in chunks:
                status = checker.feed_text(chunk)
                if not status.ok:
                    break
            self.assertIsNotNone(status)
            self.assertFalse(status.ok)


if __name__ == "__main__":
    unittest.main()
