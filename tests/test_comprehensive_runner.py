from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import run_comprehensive_cases as runner


ROOT = Path(__file__).resolve().parents[1]


class ComprehensiveRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_executable(self, name: str, source: str) -> Path:
        path = self.root / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o755)
        return path

    def _write_schema2_manifest(
        self,
        source: str,
        *,
        expected: str,
        safe_prefix_bytes: int | None,
    ) -> Path:
        source_dir = self.root / "invalid"
        source_dir.mkdir(exist_ok=True)
        source_path = source_dir / "case.cj"
        source_path.write_text(source, encoding="utf-8")
        item = {
            "name": "runner-case",
            "family": "runner-test",
            "file": "invalid/case.cj",
            "expected": expected,
            "complete": True,
            "safe_prefix_bytes": safe_prefix_bytes,
            "oracle": False,
            "stage": "syntax" if expected == "reject" else "accept",
        }
        manifest = {
            "schema_version": 2,
            "case_count": 1,
            "family_counts": {"runner-test": 1},
            "expectation_counts": {
                "accept": int(expected == "accept"),
                "prefix_accept": 0,
                "reject": int(expected == "reject"),
            },
            "cases": [item],
        }
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def _run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(ROOT / "tools/run_comprehensive_cases.py"), *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def test_reject_safe_prefix_is_reencoded_and_run_independently(self) -> None:
        import tiktoken

        source = "main() {\n    let value = 1\n    value + true\n}\n"
        safe_source = "main() {\n    let value = 1\n"
        safe_prefix_bytes = len(safe_source.encode("utf-8"))
        encoding = tiktoken.get_encoding("cl100k_base")
        full_count = len(encoding.encode(source))
        safe_count = len(encoding.encode(safe_source))
        self.assertNotEqual(full_count, safe_count)
        solution = self._write_executable(
            "checker.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            f"full_count = {full_count}\n"
            "tokens = []\n"
            "competition = '--competition-output' in sys.argv\n"
            "accept, reject = (('1', '0') if competition else ('0', '1'))\n"
            "for line in sys.stdin:\n"
            "    tokens.append(line)\n"
            "    index = len(tokens) - 1\n"
            "    print(reject if full_count == len(tokens) else accept, flush=True)\n"
            "    if len(tokens) == full_count: break\n",
        )
        manifest = self._write_schema2_manifest(
            source, expected="reject", safe_prefix_bytes=safe_prefix_bytes
        )
        report = self.root / "report.json"
        proc = self._run_cli(
            "--manifest",
            str(manifest),
            "--solution",
            str(solution),
            "--skip-grammar",
            "--skip-oracle",
            "--skip-input-edge-cases",
            "--check-competition-output",
            "--json",
            str(report),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(payload["summary"]["safe_prefix_runs"], 2)
        observation = payload["observations"][0]
        self.assertEqual(observation["token_count"], full_count)
        self.assertEqual(observation["safe_prefix"]["token_count"], safe_count)
        self.assertEqual(
            observation["safe_prefix"]["candidate"]["default"]["answer_count"],
            safe_count,
        )

    def test_dual_protocol_requires_exact_inversion_and_same_reject(self) -> None:
        default = runner.ProtocolResult(
            answers=("0", "1"),
            returncode=0,
            stdout="0\n1\n",
            stderr="",
            reject_token=1,
            reject_byte_end=4,
        )
        competition = runner.ProtocolResult(
            answers=("1", "1"),
            returncode=0,
            stdout="1\n1\n",
            stderr="",
            reject_token=None,
            reject_byte_end=None,
        )
        errors = runner._dual_protocol_errors(default, competition)
        self.assertTrue(any("exact bitwise inversion" in error for error in errors))
        self.assertTrue(any("first reject token differs" in error for error in errors))
        self.assertTrue(any("first reject byte differs" in error for error in errors))

    def test_reference_solution_differential_is_strict_and_reported(self) -> None:
        source = "main() {}\n"
        manifest = self._write_schema2_manifest(
            source, expected="accept", safe_prefix_bytes=None
        )
        candidate = self._write_executable(
            "candidate.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "value = '1' if '--competition-output' in sys.argv else '0'\n"
            "for _ in sys.stdin:\n"
            "    print(value, flush=True)\n",
        )
        reference = self._write_executable(
            "reference.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "value = '0' if '--competition-output' in sys.argv else '1'\n"
            "for _ in sys.stdin:\n"
            "    print(value, flush=True)\n"
            "    break\n"
            "raise SystemExit(7)\n",
        )
        report = self.root / "differential.json"
        proc = self._run_cli(
            "--manifest",
            str(manifest),
            "--solution",
            str(candidate),
            "--reference-solution",
            str(reference),
            "--skip-grammar",
            "--skip-oracle",
            "--skip-input-edge-cases",
            "--check-competition-output",
            "--json",
            str(report),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("answer transcript differs", proc.stderr)
        self.assertIn("exit differs", proc.stderr)
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(payload["summary"]["reference_protocol_runs"], 2)
        self.assertEqual(
            payload["provenance"]["reference_solution_sha256"],
            hashlib.sha256(reference.read_bytes()).hexdigest(),
        )
        self.assertIn("reference", payload["observations"][0])

    def test_input_edge_timeout_becomes_structured_failure(self) -> None:
        import tiktoken

        solution = self._write_executable(
            "sleep.py",
            "#!/usr/bin/env python3\n"
            "import time\n"
            "time.sleep(1)\n",
        )
        runs, errors, observations = runner._input_edge_errors(
            solution,
            tiktoken.get_encoding("cl100k_base"),
            competition_output=False,
            timeout=0.01,
        )
        self.assertEqual(runs, 13)
        self.assertEqual(len(observations), 13)
        self.assertTrue(errors)
        self.assertTrue(any("TimeoutExpired" in error for error in errors))
        self.assertTrue(
            all(
                observation["candidate"]["exception"]["kind"] == "TimeoutExpired"
                for observation in observations
            )
        )

    def test_schema3_integrity_fields_are_verified(self) -> None:
        source = "main() {}\n"
        payload = source.encode("utf-8")
        source_dir = self.root / "valid"
        source_dir.mkdir()
        source_path = source_dir / "case.cj"
        source_path.write_bytes(payload)
        relative = "valid/case.cj"
        source_sha256 = hashlib.sha256(payload).hexdigest()
        corpus = hashlib.sha256()
        corpus.update(relative.encode("utf-8"))
        corpus.update(b"\0")
        corpus.update(payload)
        corpus.update(b"\0")
        manifest = {
            "schema_version": 3,
            "generator": "tools/generate_comprehensive_cases.py",
            "generation": {"seed": 1, "generated_cases_per_family": 0},
            "case_count": 1,
            "family_counts": {"runner-test": 1},
            "expectation_counts": {"accept": 1, "prefix_accept": 0, "reject": 0},
            "stage_counts": {"accept": 1},
            "complete_counts": {"complete": 1, "incomplete": 0},
            "oracle_counts": {"checked": 1, "skipped_complete": 0, "skipped_incomplete": 0},
            "coverage": {
                "required_target_count": 0,
                "covered_target_count": 0,
                "missing_targets": [],
                "counts": {},
            },
            "integrity": {
                "algorithm": "sha256",
                "corpus_digest_format": runner.CORPUS_DIGEST_FORMAT,
                "corpus_sha256": corpus.hexdigest(),
                "dependencies": {},
            },
            "cases": [
                {
                    "name": "runner-case",
                    "family": "runner-test",
                    "file": relative,
                    "expected": "accept",
                    "complete": True,
                    "safe_prefix_bytes": None,
                    "safe_prefix_sha256": None,
                    "oracle": True,
                    "oracle_skip_reason": None,
                    "stage": "accept",
                    "expectation_tier": "authoritative",
                    "covers": [],
                    "source_bytes": len(payload),
                    "source_sha256": source_sha256,
                }
            ],
            "expectation_tier_counts": {"authoritative": 1},
        }
        manifest_path = self.root / "manifest-v3.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        _, cases = runner.load_cases(manifest_path)
        self.assertEqual(cases[0].source_sha256, source_sha256)

        manifest["cases"][0]["source_bytes"] += 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "source_bytes mismatch"):
            runner.load_cases(manifest_path)

    def test_protocol_is_interactive_and_rejects_malformed_stdout(self) -> None:
        interactive = self._write_executable(
            "interactive.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "for _ in sys.stdin:\n"
            "    print('0', flush=True)\n",
        )
        result = runner._run_protocol(
            interactive, [1, 2], [b"a", b"b"], competition_output=False, timeout=1
        )
        self.assertIsNone(result.exception_kind)
        self.assertEqual(result.answers, ("0", "0"))

        buffered = self._write_executable(
            "buffered.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "tokens = sys.stdin.read().splitlines()\n"
            "print('\\n'.join('0' for _ in tokens))\n",
        )
        result = runner._run_protocol(
            buffered, [1, 2], [b"a", b"b"], competition_output=False, timeout=0.05
        )
        self.assertEqual(result.exception_kind, "TimeoutExpired")

        partial = self._write_executable(
            "partial.py",
            "#!/usr/bin/env python3\n"
            "import sys, time\n"
            "for _ in sys.stdin:\n"
            "    sys.stdout.write('0')\n"
            "    sys.stdout.flush()\n"
            "    time.sleep(5)\n",
        )
        result = runner._run_protocol(
            partial, [1], [b"a"], competition_output=False, timeout=2.0
        )
        self.assertEqual(result.exception_kind, "TimeoutExpired")
        self.assertEqual(result.stdout, "0")

        malformed = runner.ProtocolResult(
            answers=(" 0 ",), returncode=0, stdout=" 0 \n", stderr="",
            reject_token=None, reject_byte_end=None,
        )
        self.assertTrue(runner._strict_output_errors(malformed, "test"))

    def test_fail_fast_counts_only_executed_cases_and_skips_edges(self) -> None:
        manifest = self._write_schema2_manifest(
            "main() {}\n", expected="accept", safe_prefix_bytes=None
        )
        solution = self._write_executable(
            "empty.py", "#!/usr/bin/env python3\nimport sys\nfor _ in sys.stdin: pass\n"
        )
        report = self.root / "fail-fast.json"
        proc = self._run_cli(
            "--manifest", str(manifest), "--solution", str(solution),
            "--skip-grammar", "--skip-oracle", "--fail-fast", "--json", str(report),
        )
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(report.read_text())
        self.assertEqual(payload["summary"]["executed_cases"], 1)
        self.assertEqual(payload["summary"]["passed_cases"], 0)
        self.assertEqual(payload["summary"]["input_edge_runs"], 0)

    def test_fail_fast_precheck_counts_the_failing_case(self) -> None:
        manifest = self._write_schema2_manifest(
            "main() { @ }\n", expected="accept", safe_prefix_bytes=None
        )
        report = self.root / "fail-fast-precheck.json"
        proc = self._run_cli(
            "--manifest", str(manifest), "--skip-protocol", "--skip-oracle",
            "--fail-fast", "--json", str(report),
        )
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(report.read_text())
        self.assertEqual(payload["summary"]["executed_cases"], 1)
        self.assertEqual(payload["summary"]["passed_cases"], 0)
        self.assertEqual(payload["summary"]["failed_cases"], 1)
        self.assertTrue(payload["summary"]["aborted"])
        self.assertEqual(payload["summary"]["input_edge_runs"], 0)

    def test_oracle_backed_policy_demotes_diagnostic_label_failure(self) -> None:
        source = "main() {}\n"
        manifest = self._write_schema2_manifest(
            source, expected="reject", safe_prefix_bytes=0
        )
        solution = self._write_executable(
            "accept.py",
            "#!/usr/bin/env python3\nimport sys\nfor _ in sys.stdin: print('0', flush=True)\n",
        )
        report = self.root / "diagnostic.json"
        proc = self._run_cli(
            "--manifest", str(manifest), "--solution", str(solution),
            "--skip-grammar", "--skip-oracle", "--skip-input-edge-cases",
            "--expectation-policy", "oracle-backed", "--json", str(report),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(report.read_text())
        self.assertEqual(payload["summary"]["failed_cases"], 0)
        self.assertEqual(payload["summary"]["diagnostic_disagreements"], 1)


if __name__ == "__main__":
    unittest.main()
