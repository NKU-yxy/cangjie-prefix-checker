import unittest

import tiktoken

from tools.run_grammar_shadow_matrix import (
    IDENTIFIER_LENGTHS,
    LAYOUTS,
    LOCAL_COUNTS,
    build_cases,
    fragment,
)


class GrammarShadowMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = build_cases()
        cls.by_name = {case.name: case for case in cls.cases}
        cls.encoding = tiktoken.get_encoding("cl100k_base")

    def test_scale_boundaries_cover_all_required_variants(self) -> None:
        for count in LOCAL_COUNTS:
            self.assertEqual(
                sum(case.name.startswith(f"locals-{count}-") for case in self.cases),
                1,
            )
        local_names = {
            case.name for case in self.cases if case.family == "local-count"
        }
        for variant in (
            "semicolon-newline",
            "no-semicolon-newline",
            "semicolon-same-line",
            "no-semicolon-same-line",
            "semicolon-tab",
            "no-semicolon-crlf",
        ):
            self.assertTrue(any(name.endswith(variant) for name in local_names))
        for length in IDENTIFIER_LENGTHS:
            self.assertEqual(
                sum(case.name.startswith(f"identifier-{length}-") for case in self.cases),
                1,
            )
        identifier_names = {
            case.name for case in self.cases if case.family == "identifier-length"
        }
        for placement in ("same-line", "newline"):
            for ending in ("semicolon", "no-semicolon"):
                self.assertTrue(
                    any(
                        name.endswith(f"{placement}-{ending}")
                        for name in identifier_names
                    )
                )

    def test_required_statement_and_prefix_families_are_present(self) -> None:
        required = {
            "line-comment-pseudo",
            "block-comment-pseudo",
            "string-pseudo",
            "variable-declaration",
            "assignment",
            "compound-assignment",
            "expression-statement",
            "call-member-index-postfix",
            "nested-block",
            "lambda-block",
            "if-else",
            "for-loop",
            "while-loop",
            "do-while",
            "try-catch-finally",
            "match-case",
            "function-body",
            "class-body",
            "incomplete-identifier",
            "incomplete-statement",
            "incomplete-block",
            "late-error",
        }
        self.assertTrue(required.issubset(self.by_name))

    def test_illegal_token_is_inserted_at_every_representative_byte_boundary(self) -> None:
        base = "main(): Unit {\nlet value: Int64 = 1;\nvalue += 2;\n}\n"
        names = {
            case.name for case in self.cases if case.family == "illegal-boundary"
        }
        self.assertEqual(
            names,
            {
                f"illegal-token-byte-boundary-{boundary}"
                for boundary in range(len(base.encode("utf-8")) + 1)
            },
        )

    def test_every_layout_reconstructs_the_exact_input_bytes(self) -> None:
        representatives = (
            self.by_name["whitespace-crlf"],
            self.by_name["string-pseudo"],
            next(case for case in self.cases if case.name.startswith("identifier-128-")),
        )
        self.assertEqual(
            LAYOUTS,
            ("byte", "random", "line", "cl100k", "whole"),
        )
        for case in representatives:
            expected = case.source.encode("utf-8")
            for layout in LAYOUTS:
                self.assertEqual(
                    b"".join(fragment(case, layout, self.encoding)),
                    expected,
                    (case.name, layout),
                )


if __name__ == "__main__":
    unittest.main()
