import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "solution"

try:
    import tiktoken
except Exception as exc:  # pragma: no cover - build environment diagnostic
    tiktoken = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


def _is_native_binary(path: Path) -> bool:
    try:
        return path.read_bytes()[:2] != b"#!" and os.access(path, os.X_OK)
    except OSError:
        return False


@unittest.skipIf(IMPORT_ERROR is not None, f"missing tiktoken: {IMPORT_ERROR}")
@unittest.skipUnless(_is_native_binary(SOLUTION), "run build.sh to create native solution")
class NativeSolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoding = tiktoken.get_encoding("cl100k_base")

    def run_source(self, source: str) -> list[str]:
        token_ids = self.encoding.encode(source)
        proc = subprocess.run(
            [str(SOLUTION)],
            cwd=ROOT,
            input="".join(f"{token_id}\n" for token_id in token_ids),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.splitlines()

    def test_valid_comments_generics_interfaces_and_empty_blocks(self):
        source = (
            "/* outer /* nested */ comment */\n"
            "interface I { func id(): Int64 }\n"
            "class A <: I { public init() {} public func id(): Int64 { 1 } }\n"
            "func pick(flag: Bool): I { if (flag) { A() } else { A() } }\n"
            "main(): Unit { // line comment\n println(pick(true).id()) }\n"
        )
        answers = self.run_source(source)
        self.assertTrue(answers)
        self.assertTrue(all(answer == "0" for answer in answers), answers)

    def test_syntax_error_stops_on_first_native_rejection(self):
        answers = self.run_source("main(): Unit { let value + other = 1 }")
        self.assertIn("1", answers)
        first_error = answers.index("1")
        self.assertTrue(all(answer == "0" for answer in answers[:first_error]))
        self.assertEqual(answers[first_error:], ["1"])

    def test_utf8_codepoint_split_across_cl100k_tokens(self):
        source = 'main(): Unit { println("编译🚀") }'
        token_bytes = [
            self.encoding.decode_single_token_bytes(token_id)
            for token_id in self.encoding.encode(source)
        ]
        self.assertTrue(
            any(
                payload and payload[-1] >= 0x80
                and index + 1 < len(token_bytes)
                and token_bytes[index + 1]
                and token_bytes[index + 1][0] >= 0x80
                for index, payload in enumerate(token_bytes)
            ),
            token_bytes,
        )
        answers = self.run_source(source)
        self.assertTrue(answers)
        self.assertTrue(all(answer == "0" for answer in answers), answers)


if __name__ == "__main__":
    unittest.main()
