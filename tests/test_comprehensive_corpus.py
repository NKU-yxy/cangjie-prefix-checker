from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "test_cases" / "comprehensive"


class ComprehensiveCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
        cls.cases = cls.manifest["cases"]

    def test_manifest_has_broad_balanced_coverage(self) -> None:
        self.assertEqual(self.manifest["schema_version"], 3)
        self.assertEqual(self.manifest["case_count"], len(self.cases))
        self.assertGreaterEqual(len(self.cases), 350)
        self.assertGreaterEqual(len(self.manifest["family_counts"]), 25)
        counts = self.manifest["expectation_counts"]
        self.assertGreaterEqual(counts["accept"], 200)
        self.assertGreaterEqual(counts["reject"], 110)
        self.assertGreaterEqual(counts["prefix_accept"], 35)
        coverage = self.manifest["coverage"]
        self.assertGreaterEqual(coverage["required_target_count"], 300)
        self.assertEqual(coverage["required_target_count"], coverage["covered_target_count"])
        self.assertEqual(coverage["missing_targets"], [])

    def test_manifest_statistics_are_exactly_recomputed(self) -> None:
        family_counts = Counter(case["family"] for case in self.cases)
        expectation_counts = Counter(
            "prefix_accept" if not case["complete"] else case["expected"]
            for case in self.cases
        )
        stage_counts = Counter(case["stage"] for case in self.cases)
        complete_counts = Counter(
            "complete" if case["complete"] else "incomplete"
            for case in self.cases
        )
        oracle_counts = Counter(
            "checked" if case["oracle"] else (
                "skipped_complete" if case["complete"] else "skipped_incomplete"
            )
            for case in self.cases
        )
        expectation_tier_counts = Counter(case["expectation_tier"] for case in self.cases)
        self.assertEqual(self.manifest["family_counts"], dict(sorted(family_counts.items())))
        self.assertEqual(
            self.manifest["expectation_counts"],
            dict(sorted(expectation_counts.items())),
        )
        self.assertEqual(self.manifest["stage_counts"], dict(sorted(stage_counts.items())))
        self.assertEqual(self.manifest["complete_counts"], dict(complete_counts))
        self.assertEqual(self.manifest["oracle_counts"], dict(oracle_counts))
        self.assertEqual(
            self.manifest["expectation_tier_counts"],
            dict(sorted(expectation_tier_counts.items())),
        )
        self.assertEqual(complete_counts, {"complete": 338, "incomplete": 39})
        self.assertEqual(oracle_counts, {
            "checked": 227,
            "skipped_complete": 111,
            "skipped_incomplete": 39,
        })
        self.assertEqual(expectation_tier_counts, {
            "authoritative": 219,
            "diagnostic_spec_pending": 149,
            "diagnostic_scale": 9,
        })

    def test_case_names_files_and_safe_prefixes_are_consistent(self) -> None:
        names = [case["name"] for case in self.cases]
        files = [case["file"] for case in self.cases]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(files), len(set(files)))
        actual_files = {
            path.relative_to(CORPUS).as_posix()
            for path in CORPUS.rglob("*.cj")
        }
        self.assertEqual(actual_files, set(files))
        for case in self.cases:
            with self.subTest(case=case["name"]):
                path = CORPUS / case["file"]
                self.assertTrue(path.is_file(), path)
                payload = path.read_bytes()
                self.assertEqual(path.suffix, ".cj")
                self.assertEqual(case["source_bytes"], len(payload))
                self.assertEqual(
                    case["source_sha256"], hashlib.sha256(payload).hexdigest()
                )
                if case["expected"] == "reject":
                    self.assertIsNotNone(case["safe_prefix_bytes"])
                    safe = case["safe_prefix_bytes"]
                    self.assertIsInstance(safe, int)
                    self.assertGreaterEqual(safe, 0)
                    self.assertLess(safe, len(payload))
                    payload[:safe].decode("utf-8")
                    self.assertEqual(
                        case["safe_prefix_sha256"],
                        hashlib.sha256(payload[:safe]).hexdigest(),
                    )
                else:
                    self.assertIsNone(case["safe_prefix_bytes"])
                    self.assertIsNone(case["safe_prefix_sha256"])
                if case["oracle"]:
                    self.assertIsNone(case["oracle_skip_reason"])
                else:
                    self.assertIsInstance(case["oracle_skip_reason"], str)
                    self.assertTrue(case["oracle_skip_reason"])
                if not case["complete"]:
                    self.assertEqual(case["expected"], "accept")
                    self.assertFalse(case["oracle"])
                    self.assertEqual(
                        case["oracle_skip_reason"],
                        "incomplete_prefix_not_supported_by_complete_oracle",
                    )
                    self.assertEqual(case["stage"], "prefix")
                elif case["expected"] == "accept":
                    self.assertEqual(case["stage"], "accept")
                else:
                    self.assertIn(case["stage"], {"syntax", "semantic"})

    def test_every_declared_coverage_target_is_backed_by_a_case(self) -> None:
        coverage = self.manifest["coverage"]
        observed = Counter(
            target
            for case in self.cases
            for target in case.get("covers", [])
        )
        self.assertEqual(coverage["counts"], dict(sorted(observed.items())))
        for target, count in coverage["counts"].items():
            with self.subTest(target=target):
                self.assertGreaterEqual(count, 1)
                self.assertIn(target, observed)

    def test_source_and_dependency_hashes_are_reproducible(self) -> None:
        integrity = self.manifest["integrity"]
        self.assertEqual(integrity["algorithm"], "sha256")
        self.assertEqual(
            integrity["corpus_digest_format"],
            "sorted-path-nul-source-bytes-nul-v1",
        )
        digest = hashlib.sha256()
        for case in sorted(self.cases, key=lambda item: item["file"]):
            payload = (CORPUS / case["file"]).read_bytes()
            digest.update(case["file"].encode("utf-8"))
            digest.update(b"\0")
            digest.update(payload)
            digest.update(b"\0")
        self.assertEqual(integrity["corpus_sha256"], digest.hexdigest())

        dependencies = integrity["dependencies"]
        required = {
            "tools/generate_comprehensive_cases.py",
            "benchmark/hidden_semantic_fuzz.py",
            "context.json",
            "grammar/cangjie.gbnf",
            "grammar/cangjie_token.gbnf",
            "third_party/cangjie_typechecker/typechecker/cangjie.lark",
            "third_party/cangjie_typechecker/typechecker/context.json",
        }
        self.assertTrue(required.issubset(dependencies))
        for relative, expected in dependencies.items():
            with self.subTest(dependency=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file(), path)
                self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_known_safe_prefixes_use_the_intended_marker_occurrence(self) -> None:
        from tools.generate_comprehensive_cases import _case

        occurrence = _case(
            "occurrence",
            "syntax",
            "a) b) c)",
            "reject",
            marker=")",
            marker_occurrence=2,
        )
        self.assertEqual(occurrence.safe_prefix_bytes, len("a) b".encode("utf-8")))
        started = _case(
            "start",
            "syntax",
            "a) b) c)",
            "reject",
            marker=")",
            marker_start=3,
        )
        self.assertEqual(started.safe_prefix_bytes, len("a) b".encode("utf-8")))
        with self.assertRaises(ValueError):
            _case("missing", "syntax", "abc", "reject", marker=")")

        by_name = {case["name"]: case for case in self.cases}

        def byte_offset(name: str, character_offset: int) -> int:
            source = (CORPUS / by_name[name]["file"]).read_text(encoding="utf-8")
            return len(source[:character_offset].encode("utf-8"))

        source = (CORPUS / by_name["extra-right-paren"]["file"]).read_text(
            encoding="utf-8"
        )
        expected = source.index("1)") + 1
        self.assertEqual(
            by_name["extra-right-paren"]["safe_prefix_bytes"],
            byte_offset("extra-right-paren", expected),
        )

        source = (CORPUS / by_name["dangling-binary-operator"]["file"]).read_text(
            encoding="utf-8"
        )
        expected = source.index("+ )") + 2
        self.assertEqual(
            by_name["dangling-binary-operator"]["safe_prefix_bytes"],
            byte_offset("dangling-binary-operator", expected),
        )

        source = (CORPUS / by_name["for-variable-escapes-loop"]["file"]).read_text(
            encoding="utf-8"
        )
        expected = source.rindex("item)")
        self.assertEqual(
            by_name["for-variable-escapes-loop"]["safe_prefix_bytes"],
            byte_offset("for-variable-escapes-loop", expected),
        )

    def test_generated_semantic_cases_change_with_seed(self) -> None:
        from tools.generate_comprehensive_cases import build_cases

        first = {
            case.name: case.source
            for case in build_cases(seed=101, generated_cases_per_family=1)
            if case.family.startswith("generated_")
        }
        second = {
            case.name: case.source
            for case in build_cases(seed=202, generated_cases_per_family=1)
            if case.family.startswith("generated_")
        }
        self.assertEqual(len(first), 12)
        self.assertEqual(len(second), 12)
        self.assertNotEqual(first, second)

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

    def test_generator_refuses_unsafe_or_unmanaged_output(self) -> None:
        command = [sys.executable, "tools/generate_comprehensive_cases.py"]
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        root_proc = subprocess.run(
            [*command, "--output", str(ROOT)],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        self.assertNotEqual(root_proc.returncode, 0)
        self.assertIn("unsafe corpus output directory", root_proc.stderr)

        with tempfile.TemporaryDirectory(prefix="cangjie-corpus-guard-") as temp:
            output = Path(temp)
            sentinel = output / "do-not-delete.cj"
            sentinel.write_bytes(b"keep me\n")
            proc = subprocess.run(
                [*command, "--output", str(output)],
                cwd=ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("without ownership marker", proc.stderr)
            self.assertEqual(sentinel.read_bytes(), b"keep me\n")

        with tempfile.TemporaryDirectory(prefix="cangjie-corpus-forged-") as temp:
            output = Path(temp)
            (output / "valid").mkdir()
            sentinel = output / "valid" / "do-not-delete.cj"
            sentinel.write_bytes(b"keep me\n")
            (output / "manifest.json").write_text(
                json.dumps({"generator": "tools/generate_comprehensive_cases.py"}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [*command, "--output", str(output)],
                cwd=ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertTrue(sentinel.is_file())

        with tempfile.TemporaryDirectory(prefix="cangjie-corpus-self-consistent-") as temp:
            from tools.generate_comprehensive_cases import (
                OWNERSHIP_MARKER,
                OWNERSHIP_MARKER_CONTENT,
            )

            output = Path(temp)
            (output / "valid").mkdir()
            sentinel = output / "valid" / "user-data.cj"
            payload = b"must survive\n"
            sentinel.write_bytes(payload)
            (output / OWNERSHIP_MARKER).write_text(
                OWNERSHIP_MARKER_CONTENT, encoding="utf-8"
            )
            relative = "valid/user-data.cj"
            digest = hashlib.sha256()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(payload)
            digest.update(b"\0")
            forged = {
                "schema_version": 3,
                "generator": "tools/generate_comprehensive_cases.py",
                "case_count": 1,
                "cases": [{"file": relative, "source_sha256": hashlib.sha256(payload).hexdigest()}],
                "integrity": {
                    "algorithm": "sha256",
                    "corpus_digest_format": "sorted-path-nul-source-bytes-nul-v1",
                    "corpus_sha256": digest.hexdigest(),
                },
            }
            (output / "manifest.json").write_text(json.dumps(forged), encoding="utf-8")
            proc = subprocess.run(
                [*command, "--output", str(output)],
                cwd=ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("refusing to delete stale", proc.stderr)
            self.assertEqual(sentinel.read_bytes(), payload)

        # Even a complete, self-consistent manifest and the public ownership
        # marker must not authorize overwriting user bytes at a path that the
        # current generator happens to use.
        with tempfile.TemporaryDirectory(prefix="cangjie-corpus-forged-target-") as temp:
            from tools.generate_comprehensive_cases import (
                OWNERSHIP_MARKER,
                OWNERSHIP_MARKER_CONTENT,
            )

            output = Path(temp)
            relative = "valid/classes_interfaces__class_constructor_field_method.cj"
            sentinel = output / relative
            sentinel.parent.mkdir(parents=True)
            payload = b"must survive at a generated target path\n"
            sentinel.write_bytes(payload)
            (output / OWNERSHIP_MARKER).write_text(
                OWNERSHIP_MARKER_CONTENT, encoding="utf-8"
            )
            digest = hashlib.sha256()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(payload)
            digest.update(b"\0")
            forged = {
                "schema_version": 3,
                "generator": "tools/generate_comprehensive_cases.py",
                "case_count": 1,
                "cases": [
                    {
                        "file": relative,
                        "source_sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
                "integrity": {
                    "algorithm": "sha256",
                    "corpus_digest_format": "sorted-path-nul-source-bytes-nul-v1",
                    "corpus_sha256": digest.hexdigest(),
                },
            }
            (output / "manifest.json").write_text(json.dumps(forged), encoding="utf-8")
            proc = subprocess.run(
                [*command, "--output", str(output)],
                cwd=ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("refusing to overwrite", proc.stderr)
            self.assertEqual(sentinel.read_bytes(), payload)

        with tempfile.TemporaryDirectory(prefix="cangjie-corpus-unknown-") as temp:
            output = Path(temp)
            subprocess.run(
                [*command, "--output", str(output)], cwd=ROOT, env=environment, check=True
            )
            sentinel = output / "valid" / "unknown-user-data.cj"
            sentinel.write_bytes(b"keep me\n")
            proc = subprocess.run(
                [*command, "--output", str(output)],
                cwd=ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("unknown .cj", proc.stderr)
            self.assertTrue(sentinel.is_file())


if __name__ == "__main__":
    unittest.main()
