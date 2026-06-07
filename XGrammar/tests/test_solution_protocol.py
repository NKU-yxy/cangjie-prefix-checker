import os
import subprocess
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOLUTION = os.path.join(ROOT, "solution.py")


try:
    import tiktoken
    import xgrammar  # noqa: F401
except Exception as exc:
    tiktoken = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing runtime dependency: {_IMPORT_ERROR}")
class SolutionProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoding = tiktoken.get_encoding("cl100k_base")

    def run_solution(self, source):
        token_ids = self.encoding.encode(source)
        stdin = "".join(f"{token_id}\n" for token_id in token_ids)
        proc = subprocess.run(
            [sys.executable, SOLUTION],
            input=stdin,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ROOT,
            timeout=10,
            check=False,
        )
        return proc, [line.strip() for line in proc.stdout.splitlines()]

    def test_valid_prefixes_output_zero_for_public_harness(self):
        proc, lines = self.run_solution("func main() { return 1 }")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(lines)
        self.assertTrue(all(line == "0" for line in lines), lines)

    def test_invalid_prefix_outputs_one_and_stops_for_public_harness(self):
        proc, lines = self.run_solution("var +")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("1", lines)
        first_one = lines.index("1")
        self.assertEqual(lines[first_one:], ["1"])


if __name__ == "__main__":
    unittest.main()
