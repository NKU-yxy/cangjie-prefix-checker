from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "run_concurrency_startup_checks.py"
TABLE_MAGIC = b"CJTK\x01\x00\x00\x00"


class ConcurrencyStartupToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="concurrency-tool-test-")
        self.temp = Path(self.temporary.name)
        self.solution = self.temp / "fake-solution"
        self.solution.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import sys

                args = sys.argv[1:]
                if "--context" in args:
                    print("injected context startup failure", file=sys.stderr)
                    raise SystemExit(1)
                accepted = "1" if "--competition-output" in args else "0"
                for line in sys.stdin:
                    if line.strip():
                        print(accepted, flush=True)
                """
            ),
            encoding="utf-8",
        )
        self.solution.chmod(0o755)
        self.token_table = self.temp / "cl100k_base.bin"
        entries = b"".join(struct.pack("<II", value, 1) for value in range(256))
        self.token_table.write_bytes(
            TABLE_MAGIC
            + struct.pack("<II", 256, 256)
            + entries
            + bytes(range(256))
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_tool(self, *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--solution",
                str(self.solution),
                "--token-table",
                str(self.token_table),
                *arguments,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        report = json.loads(proc.stdout)
        return proc, report

    def test_configurable_cold_long_and_parallel_checks(self) -> None:
        proc, report = self.run_tool(
            "--cold-starts",
            "2",
            "--long-statements",
            "3",
            "--parallel-clients",
            "2",
            "--parallel-rounds",
            "2",
            "--skip-resource-faults",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["cold_start"]["runs"], 2)
        self.assertEqual(report["long_input"]["statements"], 3)
        self.assertEqual(report["parallel_stress"]["processes"], 4)
        self.assertTrue(report["cold_start"]["diagnostic_only"])

    def test_resource_faults_do_not_modify_real_solution_layout(self) -> None:
        original = self.solution.read_bytes()
        proc, report = self.run_tool(
            "--cold-starts",
            "0",
            "--long-statements",
            "0",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["resource_faults"]["passed"], 2)
        self.assertFalse(report["resource_faults"]["native_layout_checked"])
        self.assertEqual(self.solution.read_bytes(), original)
        self.assertEqual(set(self.temp.iterdir()), {self.solution, self.token_table})


if __name__ == "__main__":
    unittest.main()
