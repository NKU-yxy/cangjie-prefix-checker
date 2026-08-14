from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import run_g4_identifier_scale as harness


class G4IdentifierScaleHarnessTest(unittest.TestCase):
    def _parse(self, *extra: str) -> argparse.Namespace:
        arguments = [
            "--control-root",
            "/audit/control",
            "--candidate-root",
            "/audit/candidate",
            "--official-root",
            "/audit/official",
            "--control-sha",
            harness.LOCKED_ACCEPTED_CONTROL_SHA,
            "--candidate-sha",
            "0123456789abcdef0123456789abcdef01234567",
            "--official-sha",
            harness.LOCKED_OFFICIAL_SHA,
            "--output",
            "/audit-output/g4-raw.json",
            *extra,
        ]
        return harness.build_parser().parse_args(arguments)

    def test_fixed_sources_have_exact_ascii_identifier_lengths(self) -> None:
        self.assertEqual(
            harness.IDENTIFIER_LENGTHS,
            (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384),
        )
        prefix = "main(): Unit { let "
        suffix = ": Int64 = 1 }"
        for length in harness.IDENTIFIER_LENGTHS:
            source = harness.identifier_source(length)
            self.assertTrue(source.startswith(prefix))
            self.assertTrue(source.endswith(suffix))
            self.assertNotIn("\n", source)
            self.assertNotIn(";", source)
            identifier = source[len(prefix) : -len(suffix)]
            self.assertEqual(identifier, "a" + "x" * (length - 1))
            self.assertEqual(len(identifier.encode("ascii")), length)

    def test_permanent_plan_has_192_unique_alternating_trials(self) -> None:
        cases = harness.build_generated_cases()
        anchor_source = harness._manifest_anchor_expected_source()
        cases.append(
            harness.IdentifierCase(
                name=harness.MANIFEST_ANCHOR_CASE_NAME,
                source=anchor_source,
                source_sha256=harness._sha256_bytes(anchor_source.encode("utf-8")),
                source_path="<unit-test-anchor>",
                origin="unit-test",
                identifier_bytes=harness.MANIFEST_ANCHOR_IDENTIFIER_BYTES,
                sweep_length=None,
            )
        )
        plan = harness.build_trial_plan(cases)
        self.assertEqual(len(plan), 192)
        self.assertEqual(
            harness._canonical_json_sha256(plan),
            harness.LOCKED_FULL_TRIAL_PLAN_SHA256,
        )
        self.assertEqual([entry["ordinal"] for entry in plan], list(range(1, 193)))
        self.assertEqual(len({entry["trial_id"] for entry in plan}), 192)

        for case in cases:
            for protocol in harness.PROTOCOLS:
                group = [
                    entry
                    for entry in plan
                    if entry["case_name"] == case.name
                    and entry["protocol"] == protocol
                ]
                self.assertEqual(len(group), 6)
                self.assertTrue(
                    all(
                        group[index]["role"] != group[index + 1]["role"]
                        for index in range(5)
                    )
                )
                for role in harness.ROLES:
                    self.assertEqual(
                        [
                            entry["role_repetition"]
                            for entry in group
                            if entry["role"] == role
                        ],
                        [1, 2, 3],
                    )
                self.assertTrue(
                    all(entry["timeout_seconds"] == 30.0 for entry in group)
                )
                self.assertTrue(all(entry["rss_sample_ms"] == 5.0 for entry in group))

    def test_cli_defaults_to_anchor_and_rejects_invalid_provenance(self) -> None:
        args = self._parse()
        self.assertTrue(args.include_manifest_anchor)
        harness.validate_cli_shape(args)

        no_anchor = self._parse("--no-include-manifest-anchor")
        self.assertFalse(no_anchor.include_manifest_anchor)
        harness.validate_cli_shape(no_anchor)

        bad = self._parse()
        bad.control_sha = "f5f2468"
        with self.assertRaisesRegex(harness.HarnessError, "full lowercase 40-hex"):
            harness.validate_cli_shape(bad)

        same_root = self._parse()
        same_root.candidate_root = same_root.control_root
        with self.assertRaisesRegex(harness.HarnessError, "roots must be distinct"):
            harness.validate_cli_shape(same_root)

    def test_existing_output_fails_before_any_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "already-there.json"
            output.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(harness.HarnessError, "refusing to overwrite"):
                harness._preflight_output(
                    output,
                    (root / "control", root / "candidate", root / "official"),
                )
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")

            args = self._parse()
            args.output = output
            with mock.patch.object(harness, "_locked_artifacts") as locked_artifacts:
                with self.assertRaisesRegex(
                    harness.HarnessError, "refusing to overwrite"
                ):
                    harness.collect(args)
            locked_artifacts.assert_not_called()


if __name__ == "__main__":
    unittest.main()
