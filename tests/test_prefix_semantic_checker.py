import unittest

from src.context_loader import normalize_context
from src.prefix_semantic_checker import PrefixSemanticChecker


class PrefixSemanticCheckerTests(unittest.TestCase):
    def test_all_challenge_numeric_types_are_recognized(self):
        checker = PrefixSemanticChecker()
        self.assertTrue(
            checker.validate("main(): Unit {\nlet x: Int32 = 1i32\n").ok
        )
        result = checker.validate("main(): Unit {\nlet x: Int32 = 1i64\n")
        self.assertFalse(result.ok)
        self.assertIn("expected Int32", result.message)

    def test_array_literal_element_type_is_checked(self):
        checker = PrefixSemanticChecker()
        self.assertTrue(
            checker.validate("main(): Unit {\nlet xs: Array<Int64> = [1, 2]\n").ok
        )
        result = checker.validate(
            'main(): Unit {\nlet xs: Array<Int64> = ["bad"]\n'
        )
        self.assertFalse(result.ok)
        self.assertIn("array element", result.message)

    def test_nominal_interface_reachability_preserves_type_arguments(self):
        context = normalize_context({
            "interfaces": {
                "Collection": {"type_params": ["T"], "methods": {}},
            },
            "classes": {
                "Bag": {
                    "type_params": ["T"],
                    "constructors": [{"params": []}],
                    "supers": [
                        {"nominal": "Collection", "args": [{"tparam": "T"}]},
                    ],
                },
            },
        })
        checker = PrefixSemanticChecker(context)
        self.assertTrue(
            checker.validate(
                "main(): Unit {\n"
                "let xs: Collection<Int64> = Bag<Int64>()\n"
            ).ok
        )
        result = checker.validate(
            "main(): Unit {\n"
            "let xs: Collection<String> = Bag<Int64>()\n"
        )
        self.assertFalse(result.ok)

    def test_block_and_lambda_name_resolution_is_prefix_safe(self):
        checker = PrefixSemanticChecker()
        self.assertTrue(
            checker.validate(
                "func f(): Unit {\nvar g: (Int64) -> Int64 = { x: Int64 => x + 1 }\n"
            ).ok
        )
        result = checker.validate(
            "func f(): Unit {\nvar x: Int64 = { missing +"
        )
        self.assertFalse(result.ok)
        self.assertIn("undefined identifier missing", result.message)

    def test_constructor_only_rules_do_not_need_batch_parser(self):
        checker = PrefixSemanticChecker()
        self.assertFalse(
            checker.validate("class Point { init() { return 1").ok
        )
        self.assertFalse(
            checker.validate(
                'class Point { var x: Int64 init() { this.unknown'
            ).ok
        )


if __name__ == "__main__":
    unittest.main()
