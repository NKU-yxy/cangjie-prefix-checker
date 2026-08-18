from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DRIVER_SOURCE = ROOT / "tools" / "native_semantic_driver.cpp"
CONTEXT_CANDIDATES = (
    ROOT / "generated" / "context.bin",
    ROOT.parent / "candidate_generic_header" / "generated" / "context.bin",
)
CONTEXT = next((path for path in CONTEXT_CANDIDATES if path.is_file()), CONTEXT_CANDIDATES[0])

try:
    import tiktoken
except Exception as exc:  # pragma: no cover - environment diagnostic
    tiktoken = None
    TIKTOKEN_IMPORT_ERROR = exc
else:
    TIKTOKEN_IMPORT_ERROR = None


@dataclass(frozen=True)
class InvalidCase:
    name: str
    source: str
    expected_rejection: int


@dataclass(frozen=True)
class ValidCase:
    name: str
    source: str


INVALID_CASES = (
    InvalidCase(
        "same-block let redefinition waits for declaration operator",
        "main(): Unit {\n"
        "  let x: Int64 = 1\n"
        "  let x: Int64 = 2\n"
        "  println((x).toString())\n"
        "}\n",
        17,
    ),
    InvalidCase(
        "same-block var redefinition waits for declaration operator",
        "main(): Unit {\n"
        "  var x: Int64 = 1\n"
        "  var x: Int64 = 2\n"
        "  println((x).toString())\n"
        "}\n",
        17,
    ),
    InvalidCase(
        "Bool relational operands reject at the completed right operand",
        "main(): Unit {\n"
        "  let ok: Bool = (true < false)\n"
        "}\n",
        13,
    ),
    InvalidCase(
        "for range bad step waits for the closed condition",
        "main(): Unit {\n"
        "  for (i in 1..10:1.0) { println(i) }\n"
        "}\n",
        17,
    ),
    InvalidCase(
        "while body must end with Unit",
        "main(): Unit {\n"
        "  var i: Int64 = 0\n"
        "  while (i < 1) {\n"
        "    i = i + 1\n"
        "    i + 1\n"
        "  }\n"
        "}\n",
        38,
    ),
    InvalidCase(
        "for body must end with Unit",
        "main(): Unit {\n"
        "  var s: Int64 = 0\n"
        "  for (i in 0..1) {\n"
        "    s = s + i\n"
        "    s + i\n"
        "  }\n"
        "}\n",
        38,
    ),
    InvalidCase(
        "String plus Int64",
        'main(): Unit {\n  let s: String = "n=" + 1\n}\n',
        17,
    ),
    InvalidCase(
        "String minus String",
        'main(): Unit {\n  let s: String = "a" - "b"\n}\n',
        13,
    ),
    InvalidCase(
        "mixed Int64 and Rune range",
        'main(): Unit {\n  let c: Rune = "a"\n  for (i in 0..c) { println(i) }\n}\n',
        22,
    ),
    InvalidCase(
        "String.concat requires String",
        'main(): Unit {\n  let x: String = "abc".concat(1)\n}\n',
        16,
    ),
    InvalidCase(
        "String.hashCode result is Int64",
        'main(): Unit {\n  let x: String = "abc".hashCode()\n}\n',
        15,
    ),
    InvalidCase(
        "ArrayStack loop element keeps String type",
        "main(): Unit {\n"
        "  let s: ArrayStack<String> = ArrayStack<String>()\n"
        "  for (x in s) { let y: Int64 = x }\n"
        "}\n",
        32,
    ),
    InvalidCase(
        "compact constructor this-field assignment checks its value type",
        'class Point { var x: Int64 init(x: Int64) { this.x = "bad"; } }',
        20,
    ),
    InvalidCase(
        "compact constructor this-field assignment checks the field name",
        "class Point { var x: Int64 init(x: Int64) { this.y = x; } }",
        19,
    ),
    InvalidCase(
        "adjacent compact constructor assignments check the second field",
        "class P { var a: Int64 var b: String init(x: Int64) { "
        "this.a = x this.b = x } }",
        27,
    ),
    InvalidCase(
        "adjacent bare constructor assignments check the second field",
        "class P { var a: Int64 let b: String init(x: Int64) { "
        "a = x b = x } }",
        25,
    ),
    InvalidCase(
        "same-line duplicate field rejects at the second colon",
        "class P { var a: Int64 var a: String init() {} }",
        10,
    ),
    InvalidCase(
        "same-line static and instance field names collide",
        "class P { static let a: Int64 = 1 var a: String init() {} }",
        14,
    ),
    InvalidCase(
        "same-line field and method names collide",
        "class P { var a: Int64 func a(): Int64 { return 1 } }",
        10,
    ),
    InvalidCase(
        "var fields without initializer must be assigned by a constructor",
        "class Point { var x: Float64 var y: Float64 "
        "func dist(): Float64 { return x * x + y * y } }",
        28,
    ),
)


VALID_CASES = (
    ValidCase(
        "while assignment is Unit",
        "main(): Unit {\n var i: Int64 = 0\n while (i < 1) { i = i + 1 }\n}\n",
    ),
    ValidCase(
        "for assignment is Unit",
        "main(): Unit {\n var s: Int64 = 0\n for (i in 0..1) { s = s + i }\n}\n",
    ),
    ValidCase(
        "String plus String",
        'main(): Unit { let s: String = "a" + "b" }\n',
    ),
    ValidCase(
        "String plus conversion continued after newline",
        'main(): Unit {\n let s: String = "n=" + 1\n.toString()\n}\n',
    ),
    ValidCase(
        "numeric subtraction",
        "main(): Unit { let n: Int64 = 4 - 1 }\n",
    ),
    ValidCase(
        "same-type integer range",
        "main(): Unit { for (i in 0..2) { println(i) } }\n",
    ),
    ValidCase(
        "String.concat String",
        'main(): Unit { let s: String = "a".concat("b") }\n',
    ),
    ValidCase(
        "String.hashCode assigned to Int64",
        'main(): Unit { let n: Int64 = "a".hashCode() }\n',
    ),
    ValidCase(
        "ArrayStack String loop element",
        "main(): Unit {\n"
        " let s: ArrayStack<String> = ArrayStack<String>()\n"
        " for (x in s) { let y: String = x }\n"
        "}\n",
    ),
    ValidCase(
        "nested control flow remains Unit",
        "main(): Unit {\n"
        " var n: Int64 = 0\n"
        " while (n < 2) { if (n == 0) { n = n + 1 } else { n = n + 1 } }\n"
        "}\n",
    ),
    ValidCase(
        "escaped String literal member call",
        'main(): Unit { let n: Int64 = "a\\\"b".hashCode() }\n',
    ),
    ValidCase(
        "unsupported UInt8 suffix preserves the generic transcript",
        "main(): Unit { let value: UInt8 = 5u8 }\n",
    ),
    ValidCase(
        "unsupported UInt16 suffix preserves the generic transcript",
        "main(): Unit { let value: UInt16 = 6u16 }\n",
    ),
    ValidCase(
        "unsupported UInt32 suffix preserves the generic transcript",
        "main(): Unit { let value: UInt32 = 7u32 }\n",
    ),
    ValidCase(
        "unsupported UInt64 suffix preserves the generic transcript",
        "main(): Unit { let value: UInt64 = 8u64 }\n",
    ),
    ValidCase(
        "unsupported UIntNative suffix preserves the generic transcript",
        "main(): Unit { let value: UIntNative = 1u64 }\n",
    ),
    ValidCase(
        "compact constructor initializes a var field",
        "class Point { var x: Int64 init(x: Int64) { this.x = x; } }",
    ),
    ValidCase(
        "compact constructor initializes a let field",
        "class Point { let x: Int64 init(x: Int64) { this.x = x; } }",
    ),
    ValidCase(
        "adjacent compact constructor assignments preserve field types",
        "class P { var a: Int64 var b: String init(x: Int64, y: String) { "
        "this.a = x this.b = y } }",
    ),
    ValidCase(
        "adjacent bare constructor assignments preserve field flow",
        "class P { var a: Int64 let b: String init(x: Int64, y: String) { "
        "a = x b = y } }",
    ),
    ValidCase(
        "fake adjacent assignment in a String literal is ignored",
        "class P { var a: Int64 var b: String init(x: Int64) { "
        'this.a = x this.b = "this.a = x" } }',
    ),
)


@unittest.skipUnless(CONTEXT.is_file(), "run build.sh to generate context.bin")
class ControlOpsRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            raise unittest.SkipTest("C++ compiler is unavailable")
        if tiktoken is None:
            raise unittest.SkipTest(f"missing tiktoken: {TIKTOKEN_IMPORT_ERROR}")
        if not DRIVER_SOURCE.is_file():
            raise unittest.SkipTest(f"missing native driver source: {DRIVER_SOURCE}")
        cls.encoding = tiktoken.get_encoding("cl100k_base")
        cls._temporary_directory = tempfile.TemporaryDirectory(
            prefix="cangjie-control-ops-regressions-"
        )
        cls.driver = Path(cls._temporary_directory.name) / "native_semantic_driver"
        build = subprocess.run(
            [
                compiler,
                "-std=c++17",
                "-O2",
                "-DNDEBUG",
                "-Icpp",
                str(DRIVER_SOURCE),
                "cpp/native_semantic.cpp",
                "-o",
                str(cls.driver),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        if build.returncode != 0:
            raise AssertionError(build.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    @classmethod
    def run_source(cls, source: str) -> tuple[list[str], str]:
        fragments = [
            cls.encoding.decode_single_token_bytes(token_id)
            for token_id in cls.encoding.encode(source)
        ]
        proc = subprocess.run(
            [str(cls.driver), str(CONTEXT)],
            input="".join(fragment.hex() + "\n" for fragment in fragments),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            env={**os.environ, "CANGJIE_DEBUG_SEMANTIC": "1"},
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        answers = proc.stdout.splitlines()
        if not answers or any(answer not in {"0", "1"} for answer in answers):
            raise AssertionError(f"invalid transcript: {answers!r}; stderr={proc.stderr!r}")
        return answers, proc.stderr

    def test_final_negative_cases_reject_at_the_audited_first_token(self) -> None:
        for case in INVALID_CASES:
            with self.subTest(case=case.name):
                answers, stderr = self.run_source(case.source)
                self.assertIn("1", answers, stderr)
                rejection = answers.index("1")
                self.assertEqual(rejection, case.expected_rejection, stderr)
                self.assertTrue(all(answer == "0" for answer in answers[:rejection]))
                self.assertEqual(answers[rejection:], ["1"])

    def test_valid_counterparts_accept_every_cl100k_token(self) -> None:
        for case in VALID_CASES:
            with self.subTest(case=case.name):
                answers, stderr = self.run_source(case.source)
                token_count = len(self.encoding.encode(case.source))
                self.assertEqual(answers, ["0"] * token_count, stderr)


if __name__ == "__main__":
    unittest.main()
