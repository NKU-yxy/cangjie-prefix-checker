import os
import unittest

from src.context_loader import load_context, normalize_context


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ContextLoaderTests(unittest.TestCase):
    def test_project_context_preserves_overloads_and_nominal_members(self):
        context = load_context(os.path.join(ROOT, "context.json"))

        println = [item for item in context["functions"] if item["name"] == "println"]
        self.assertEqual(5, len(println))
        self.assertEqual(
            {"String", "Int64", "Float64", "Bool", "Rune"},
            {item["param_types"][0] for item in println},
        )

        function_names = {item["name"] for item in context["functions"]}
        self.assertTrue({"min", "max", "abs", "clamp"}.issubset(function_names))

        array = next(item for item in context["classes"] if item["name"] == "Array")
        self.assertEqual("Int64", array["fields"]["size"])
        self.assertEqual(3, len(array["constructors"]))
        self.assertIn("fill", {item["name"] for item in array["methods"]})
        self.assertIn("indexOf", {item["name"] for item in array["methods"]})
        self.assertIn("Iterable<T>", array["supers"])

        nominal_names = {item["name"] for item in context["classes"]}
        self.assertTrue({"ArrayStack", "ArrayDeque"}.issubset(nominal_names))

        hashable = next(item for item in context["interfaces"] if item["name"] == "Hashable")
        self.assertIn("hashCode", {item["name"] for item in hashable["methods"]})
        interface_names = {item["name"] for item in context["interfaces"]}
        self.assertTrue({"Stack", "Deque"}.issubset(interface_names))

    def test_classes_alias_and_structured_types_are_supported(self):
        context = normalize_context({
            "classes": {
                "Box": {
                    "type_params": ["T"],
                    "instance_fields": {"value": {"tparam": "T"}},
                    "instance_methods": {
                        "map": [{
                            "params": [{
                                "name": "f",
                                "type": {
                                    "function": {
                                        "params": [{"tparam": "T"}],
                                        "ret": "String",
                                    }
                                },
                            }],
                            "ret": {"tuple": ["String", "Int64"]},
                        }],
                    },
                },
            },
        })

        box = context["classes"][0]
        self.assertEqual("T", box["fields"]["value"])
        self.assertEqual("(T) -> String", box["methods"][0]["param_types"][0])
        self.assertEqual("(String, Int64)", box["methods"][0]["return_type"])


if __name__ == "__main__":
    unittest.main()
