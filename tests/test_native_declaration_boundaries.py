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


@dataclass(frozen=True)
class DeclarationBoundaryCase:
    name: str
    source: str
    expected_valid: bool


# These cases deliberately lock the native checker's existing declaration-scan
# behaviour.  They are a differential guard for refactors of the scan/index
# implementation, not a statement that every semantic-only source is valid
# Cangjie syntax.
CASES = (
    DeclarationBoundaryCase(
        "duplicate nominal keeps record order",
        "class Box { init(x: Int64) {} }\n"
        "class Box { init(x: String) {} }\n"
        'main(): Unit { let box: Box = Box("ok"); }',
        True,
    ),
    DeclarationBoundaryCase(
        "duplicate nominal replacement affects constructor",
        "class Box { init(x: Int64) {} }\n"
        "class Box { init(x: String) {} }\n"
        "main(): Unit { let box: Box = Box(1); }",
        False,
    ),
    DeclarationBoundaryCase(
        "nested nominal delimiter ownership",
        "class Outer { class Inner { init(x: Int64) {} } }\n"
        'main(): Unit { let inner: Inner = Inner("bad"); }',
        False,
    ),
    DeclarationBoundaryCase(
        "CRLF multiline function",
        "func choose(\r\n"
        "    value: Int64\r\n"
        "): Int64 {\r\n"
        "    return value\r\n"
        "}\r\n"
        "main(): Unit { let value: Int64 = choose(1); }",
        True,
    ),
    DeclarationBoundaryCase(
        "CRLF multiline function return use mismatch",
        "func choose(\r\n"
        "    value: Int64\r\n"
        "): Int64 {\r\n"
        "    return value\r\n"
        "}\r\n"
        "main(): Unit { let value: String = choose(1); }",
        False,
    ),
    DeclarationBoundaryCase(
        "comment contains nominal-looking declaration",
        "/* class Ghost { init(value: String) {} } */\n"
        'main(): Unit { let ghost: Ghost = Ghost("ok"); }',
        True,
    ),
    DeclarationBoundaryCase(
        "string contains nominal-looking declaration",
        'main(): Unit { let marker: String = "class Phantom { '
        'init(value: String) {} }"; let value: Phantom = Phantom("ok"); }',
        True,
    ),
    DeclarationBoundaryCase(
        "unclosed nominal retains optional delimiter close",
        "class Open<T> { init(value: T) { }\n"
        "func use(value: Open<Int64>): Int64 { return 1 }",
        True,
    ),
    DeclarationBoundaryCase(
        "unclosed multiline function header is an accepted prefix",
        "func pending(\r\n    value: Int64\r\n): Int64",
        True,
    ),
    DeclarationBoundaryCase(
        "func main open body uses func context semantics",
        "func main(): Int64 { missing",
        True,
    ),
    DeclarationBoundaryCase(
        "bare main open body uses main context semantics",
        "main(): Int64 { missing",
        False,
    ),
    DeclarationBoundaryCase(
        "func main closes and commits deferred error",
        "func main(): Int64 { missing }",
        False,
    ),
    DeclarationBoundaryCase(
        "latest function context wins",
        'func main(): String { "ok" }\n'
        'main(): Unit { let value: Int64 = "bad"; }',
        False,
    ),
)


@unittest.skipUnless(CONTEXT.is_file(), "run build.sh to generate context.bin")
class NativeDeclarationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            raise unittest.SkipTest("C++ compiler is unavailable")
        cls._temporary_directory = tempfile.TemporaryDirectory(
            prefix="cangjie-native-declaration-boundaries-"
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

    @staticmethod
    def fragmentations(source: str, seed: int) -> dict[str, list[bytes]]:
        payload = source.encode("utf-8")
        rng = random.Random(seed)
        random_fragments: list[bytes] = []
        cursor = 0
        while cursor < len(payload):
            size = rng.randint(1, 11)
            random_fragments.append(payload[cursor : cursor + size])
            cursor += size
        line_fragments = [
            line.encode("utf-8") for line in source.splitlines(keepends=True)
        ]
        return {
            "whole": [payload],
            "byte": [bytes((byte,)) for byte in payload],
            "random": random_fragments,
            "line": line_fragments,
        }

    def run_fragments(self, fragments: list[bytes]) -> tuple[bool, list[str]]:
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
        if "1" in answers:
            self.assertEqual(answers[-1], "1")
            self.assertTrue(all(answer == "0" for answer in answers[:-1]), answers)
        return "1" not in answers, answers

    def test_declaration_boundaries_match_across_fragmentations(self) -> None:
        for case_index, case in enumerate(CASES):
            observed: dict[str, bool] = {}
            for fragmentation, fragments in self.fragmentations(
                case.source, 20260812 + case_index
            ).items():
                with self.subTest(case=case.name, fragmentation=fragmentation):
                    actual, _ = self.run_fragments(fragments)
                    self.assertEqual(case.expected_valid, actual)
                    observed[fragmentation] = actual
            self.assertEqual({case.expected_valid}, set(observed.values()), case.name)


if __name__ == "__main__":
    unittest.main()
