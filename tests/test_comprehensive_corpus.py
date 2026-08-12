from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "test_cases" / "comprehensive"


class ComprehensiveCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
        cls.cases = cls.manifest["cases"]

    def test_manifest_has_broad_balanced_coverage(self) -> None:
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(self.manifest["case_count"], len(self.cases))
        self.assertGreaterEqual(len(self.cases), 100)
        self.assertGreaterEqual(len(self.manifest["family_counts"]), 12)
        counts = self.manifest["expectation_counts"]
        self.assertGreaterEqual(counts["accept"], 35)
        self.assertGreaterEqual(counts["reject"], 35)
        self.assertGreaterEqual(counts["prefix_accept"], 10)

    def test_case_names_files_and_safe_prefixes_are_consistent(self) -> None:
        names = [case["name"] for case in self.cases]
        files = [case["file"] for case in self.cases]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(files), len(set(files)))
        for case in self.cases:
            with self.subTest(case=case["name"]):
                path = CORPUS / case["file"]
                self.assertTrue(path.is_file(), path)
                payload = path.read_bytes()
                self.assertEqual(path.suffix, ".cj")
                if case["expected"] == "reject":
                    self.assertIsNotNone(case["safe_prefix_bytes"])
                    self.assertLess(case["safe_prefix_bytes"], len(payload))
                if not case["complete"]:
                    self.assertEqual(case["expected"], "accept")
                    self.assertFalse(case["oracle"])

    def test_checked_in_files_match_deterministic_generator(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            [sys.executable, "tools/generate_comprehensive_cases.py", "--check"],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
