from __future__ import annotations

from collections import Counter
import unittest

from benchmark.hidden_semantic_fuzz import (
    _configure_official_oracle,
    generate_cases,
    official_accepts,
)


class HiddenSemanticFuzzTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _configure_official_oracle()

    def test_generator_is_deterministic_unique_and_balanced(self) -> None:
        first = generate_cases(seed=20260805, cases_per_family=2)
        second = generate_cases(seed=20260805, cases_per_family=2)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 24)
        self.assertEqual(len({case.name for case in first}), len(first))
        self.assertEqual(
            Counter(case.family for case in first),
            {
                "multiline": 4,
                "nested_lambda": 4,
                "overload": 4,
                "generic_inheritance": 4,
                "valid_zero_false_positive": 4,
                "scope_isolation": 4,
            },
        )

    def test_generated_labels_are_confirmed_by_official_typechecker(self) -> None:
        for case in generate_cases(seed=991827, cases_per_family=1):
            with self.subTest(case=case.name):
                actual, message = official_accepts(case.source)
                self.assertEqual(case.expected_valid, actual, message)

    def test_mutations_record_a_nonempty_safe_window(self) -> None:
        cases = generate_cases(seed=731991, cases_per_family=2)
        for case in cases:
            if case.expected_valid:
                self.assertIsNone(case.mutation_start)
                self.assertIsNone(case.mutation_commit)
                continue
            with self.subTest(case=case.name):
                self.assertIsNotNone(case.mutation_start)
                self.assertIsNotNone(case.mutation_commit)
                self.assertLess(case.mutation_start, case.mutation_commit)


if __name__ == "__main__":
    unittest.main()
