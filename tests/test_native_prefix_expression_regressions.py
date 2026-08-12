from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "generated" / "context.bin"

try:
    import tiktoken
except Exception as exc:  # pragma: no cover - build environment diagnostic
    tiktoken = None
    TIKTOKEN_IMPORT_ERROR = exc
else:
    TIKTOKEN_IMPORT_ERROR = None


@dataclass(frozen=True)
class ValidPrefixCase:
    name: str
    source: str


@dataclass(frozen=True)
class CommittedErrorCase:
    name: str
    safe_source: str
    rejected_source: str


VALID_CASES = (
    ValidPrefixCase(
        "lambda block body followed by immediate call",
        "main(): Unit {\n"
        " let value: Int64 = { x: Int64 => { x + 1 } }(2)\n"
        " println(value)\n"
        "}\n",
    ),
    ValidPrefixCase(
        "lambda block body captures an outer local before immediate call",
        "main(): Unit {\n"
        " let offset: Int64 = 3\n"
        " let value: Int64 = { number: Int64 => { number + offset } }(4)\n"
        " println(value)\n"
        "}\n",
    ),
)


LAMBDA_PREFIX = (
    "main(): Unit {\n"
    " let value: Int64 = { item: Int64 => { item + 1 } }("
)

COMMITTED_ERROR_CASES = (
    CommittedErrorCase(
        "closed IIFE argument has the wrong type",
        LAMBDA_PREFIX,
        LAMBDA_PREFIX + '"bad")\n',
    ),
    CommittedErrorCase(
        "closed IIFE has too many arguments",
        LAMBDA_PREFIX + "1",
        LAMBDA_PREFIX + "1, 2)\n",
    ),
    CommittedErrorCase(
        "closed IIFE result mismatches its declaration",
        "main(): Unit {\n"
        ' let value: Int64 = { item: Int64 => { "bad" } }(',
        "main(): Unit {\n"
        ' let value: Int64 = { item: Int64 => { "bad" } }(1)\n',
    ),
)


@unittest.skipUnless(CONTEXT.is_file(), "run build.sh to generate context.bin")
class NativePrefixExpressionRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            raise unittest.SkipTest("C++ compiler is unavailable")
        if tiktoken is None:
            raise unittest.SkipTest(f"missing tiktoken: {TIKTOKEN_IMPORT_ERROR}")
        cls.encoding = tiktoken.get_encoding("cl100k_base")
        cls._temporary_directory = tempfile.TemporaryDirectory(
            prefix="cangjie-native-prefix-expressions-"
        )
        cls.driver = Path(cls._temporary_directory.name) / "native_semantic_driver"
        build = subprocess.run(
            [
                compiler,
                "-std=c++17",
                "-O2",
                "-DNDEBUG",
                "-DCANGJIE_ENABLE_REGEX_SHADOW",
                "-Icpp",
                "tools/native_semantic_driver.cpp",
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
    def fragmentations(cls, source: str, seed: int) -> dict[str, list[bytes]]:
        payload = source.encode("utf-8")
        rng = random.Random(seed)
        random_fragments: list[bytes] = []
        cursor = 0
        while cursor < len(payload):
            width = rng.randint(1, 11)
            random_fragments.append(payload[cursor : cursor + width])
            cursor += width
        line_fragments = [
            line.encode("utf-8") for line in source.splitlines(keepends=True)
        ]
        cl100k_fragments = [
            cls.encoding.decode_single_token_bytes(token_id)
            for token_id in cls.encoding.encode(source)
        ]
        cls._assert_fragments_reconstruct(payload, cl100k_fragments)
        return {
            "whole": [payload],
            "byte": [bytes((byte,)) for byte in payload],
            "random": random_fragments,
            "line": line_fragments,
            "cl100k": cl100k_fragments,
        }

    @staticmethod
    def _assert_fragments_reconstruct(payload: bytes, fragments: list[bytes]) -> None:
        if b"".join(fragments) != payload:
            raise AssertionError("fragmentation does not reconstruct source bytes")

    def run_fragments(self, fragments: list[bytes]) -> tuple[bool, list[str], int]:
        proc = subprocess.run(
            [str(self.driver), str(CONTEXT)],
            input="".join(fragment.hex() + "\n" for fragment in fragments),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        answers = proc.stdout.splitlines()
        self.assertTrue(answers)
        self.assertTrue(all(answer in {"0", "1"} for answer in answers), answers)
        if "1" not in answers:
            self.assertEqual(len(answers), len(fragments), answers)
            return True, answers, sum(len(fragment) for fragment in fragments)
        reject_index = answers.index("1")
        self.assertEqual(answers[-1], "1")
        self.assertTrue(all(answer == "0" for answer in answers[:-1]), answers)
        self.assertEqual(len(answers), reject_index + 1, answers)
        consumed = sum(len(fragment) for fragment in fragments[: reject_index + 1])
        return False, answers, consumed

    def test_valid_lambda_iifes_never_reject_by_fragmentation(self) -> None:
        for case_index, case in enumerate(VALID_CASES):
            for mode, fragments in self.fragmentations(
                case.source, 20260813 + case_index
            ).items():
                with self.subTest(case=case.name, fragmentation=mode):
                    actual, _, consumed = self.run_fragments(fragments)
                    self.assertTrue(actual)
                    self.assertEqual(consumed, len(case.source.encode("utf-8")))

    def test_committed_errors_reject_but_their_safe_prefixes_do_not(self) -> None:
        for case_index, case in enumerate(COMMITTED_ERROR_CASES):
            self.assertTrue(case.rejected_source.startswith(case.safe_source), case.name)
            safe_bytes = len(case.safe_source.encode("utf-8"))
            for mode, safe_fragments in self.fragmentations(
                case.safe_source, 20261813 + case_index
            ).items():
                with self.subTest(case=case.name, fragmentation=mode, phase="safe"):
                    safe, _, consumed = self.run_fragments(safe_fragments)
                    self.assertTrue(safe)
                    self.assertEqual(consumed, safe_bytes)

            for mode, rejected_fragments in self.fragmentations(
                case.rejected_source, 20262813 + case_index
            ).items():
                with self.subTest(case=case.name, fragmentation=mode, phase="error"):
                    accepted, _, consumed = self.run_fragments(rejected_fragments)
                    self.assertFalse(accepted)
                    self.assertGreater(consumed, safe_bytes)


if __name__ == "__main__":
    unittest.main()
