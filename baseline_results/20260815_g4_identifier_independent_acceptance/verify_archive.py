#!/usr/bin/env python3
"""Portable, fail-closed verifier for the G4-029 final evidence bundle.

Only the Python 3 standard library is required.  The verifier deliberately
does not rewrite historical evidence: original manifests that name
``/evidence/...`` or ``/audit/...`` are replayed through explicit mappings in
``inventory.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any, Dict, Iterable, List, Tuple


SHA_RE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")
EXPECTED_SCHEMA = "g4-029-portable-evidence-inventory-v1"
OVERALL_MANIFEST = "CONTENT_SHA256SUMS"


class VerificationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise VerificationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative(name: str) -> PurePosixPath:
    item = PurePosixPath(name)
    if (
        not name or "\\" in name or "\x00" in name or ":" in name
        or item.is_absolute() or ".." in item.parts or "." in item.parts
    ):
        fail(f"unsafe archive-relative path: {name!r}")
    return item


def root_join(root: Path, name: str) -> Path:
    item = safe_relative(name)
    target = root.joinpath(*item.parts)
    # Every parent must be a real directory, not an extraction-time symlink.
    cursor = root
    for part in item.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            fail(f"symlink is forbidden in bundle: {cursor}")
    return target


def parse_sha_manifest(path: Path) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read manifest {path}: {exc}")
    for line_number, line in enumerate(lines, 1):
        match = SHA_RE.fullmatch(line)
        if not match:
            fail(f"malformed SHA-256 row {path}:{line_number}")
        rows.append((match.group(1), match.group(2)))
    if len({name for _, name in rows}) != len(rows):
        fail(f"duplicate path in manifest: {path}")
    return rows


def regular_files(root: Path) -> List[str]:
    result: List[str] = []
    for parent, dirnames, filenames in os.walk(str(root), followlinks=False):
        parent_path = Path(parent)
        for dirname in list(dirnames):
            path = parent_path / dirname
            if path.is_symlink():
                fail(f"symlinked directory is forbidden: {path}")
        for filename in filenames:
            path = parent_path / filename
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                fail(f"symlink is forbidden: {path}")
            if not stat.S_ISREG(mode):
                fail(f"non-regular bundle entry is forbidden: {path}")
            result.append(path.relative_to(root).as_posix())
    return sorted(result)


def verify_overall_manifest(root: Path) -> int:
    manifest_path = root / OVERALL_MANIFEST
    if not manifest_path.is_file():
        fail(f"missing {OVERALL_MANIFEST}")
    rows = parse_sha_manifest(manifest_path)
    named = {name for _, name in rows}
    expected = set(regular_files(root)) - {OVERALL_MANIFEST}
    if named != expected:
        missing = sorted(expected - named)
        extra = sorted(named - expected)
        fail(f"overall manifest coverage differs; missing={missing[:8]} extra={extra[:8]}")
    for expected_sha, name in rows:
        target = root_join(root, name)
        if sha256_file(target) != expected_sha:
            fail(f"overall SHA-256 mismatch: {name}")
    return len(rows)


def pointer_get(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        fail(f"invalid JSON pointer: {pointer!r}")
    value = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            try:
                value = value[int(token)]
            except (ValueError, IndexError) as exc:
                fail(f"JSON pointer not found: {pointer}: {exc}")
        elif isinstance(value, dict) and token in value:
            value = value[token]
        else:
            fail(f"JSON pointer not found: {pointer}")
    return value


def verify_claims(root: Path, evidence: Dict[str, Any]) -> int:
    count = 0
    for claim in evidence.get("claim_checks", []):
        path = root_join(root, claim["archive_path"])
        if not path.is_file():
            fail(f"missing claim document for {evidence['id']}: {path}")
        if "sha256" in claim and sha256_file(path) != claim["sha256"]:
            fail(f"claim-document SHA mismatch for {evidence['id']}: {path}")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            fail(f"cannot parse claim document {path}: {exc}")
        for check in claim.get("assertions", []):
            actual = pointer_get(document, check["pointer"])
            if actual != check["equals"]:
                fail(
                    f"claim mismatch {evidence['id']} {check['pointer']}: "
                    f"expected {check['equals']!r}, got {actual!r}"
                )
            count += 1
    return count


def remap_historical_name(
    manifest_archive_path: str,
    historical_name: str,
    mappings: List[Dict[str, str]],
) -> str:
    if historical_name.startswith("/"):
        candidates = sorted(
            (item for item in mappings if historical_name.startswith(item["from_prefix"])),
            key=lambda item: len(item["from_prefix"]),
            reverse=True,
        )
        if not candidates:
            fail(f"absolute historical path has no declared remap: {historical_name}")
        mapping = candidates[0]
        suffix = historical_name[len(mapping["from_prefix"]):]
        return mapping["to_prefix"] + suffix
    parent = PurePosixPath(manifest_archive_path).parent
    return (parent / safe_relative(historical_name)).as_posix()


def verify_historical_manifest(root: Path, evidence: Dict[str, Any]) -> int:
    spec = evidence.get("internal_manifest")
    if spec is None:
        return 0
    manifest_path = root_join(root, spec["archive_path"])
    if sha256_file(manifest_path) != spec["sha256"]:
        fail(f"historical manifest SHA mismatch for {evidence['id']}")
    rows = parse_sha_manifest(manifest_path)
    if len(rows) != spec["entry_count"]:
        fail(f"historical manifest count mismatch for {evidence['id']}")
    for expected_sha, historical_name in rows:
        archive_name = remap_historical_name(
            spec["archive_path"], historical_name, spec.get("path_mappings", [])
        )
        target = root_join(root, archive_name)
        if not target.is_file():
            fail(f"historical manifest target missing: {archive_name}")
        if sha256_file(target) != expected_sha:
            fail(f"historical manifest mismatch: {archive_name}")
    return len(rows)


def verify_tree_binding(root: Path, evidence: Dict[str, Any]) -> int:
    binding = evidence.get("tree_binding")
    if binding is None:
        fail(f"included evidence lacks tree binding: {evidence['id']}")
    if binding.get("algorithm") != "sha256(sorted(relative_path + NUL + file_sha256 + LF))":
        fail(f"unknown evidence tree-binding algorithm: {evidence['id']}")
    subtree = root_join(root, evidence["archive_path"])
    if not subtree.is_dir():
        fail(f"evidence subtree missing: {evidence['archive_path']}")
    digest = hashlib.sha256()
    paths = regular_files(subtree)
    total = 0
    for relative in paths:
        target = root_join(subtree, relative)
        file_sha = sha256_file(target)
        total += target.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha.encode("ascii"))
        digest.update(b"\n")
    if len(paths) != binding["file_count"]:
        fail(f"evidence file-count mismatch: {evidence['id']}")
    if total != binding["total_file_bytes"]:
        fail(f"evidence byte-count mismatch: {evidence['id']}")
    if digest.hexdigest() != binding["sha256"]:
        fail(f"evidence tree-binding mismatch: {evidence['id']}")
    return len(paths)


def verify_artifacts(root: Path, inventory: Dict[str, Any]) -> int:
    count = 0
    for artifact in inventory.get("artifacts", []):
        target = root_join(root, artifact["archive_path"])
        if not target.is_file():
            fail(f"missing bound artifact: {artifact['archive_path']}")
        if sha256_file(target) != artifact["sha256"]:
            fail(f"artifact SHA mismatch: {artifact['archive_path']}")
        if target.stat().st_size != artifact["size_bytes"]:
            fail(f"artifact size mismatch: {artifact['archive_path']}")
        count += 1
    return count


def verify_source_closure(root: Path, inventory: Dict[str, Any]) -> int:
    count = 0
    closure = inventory.get("source_closure", {})
    for item in closure.get("files", []):
        target = root_join(root, item["archive_path"])
        if not target.is_file() or sha256_file(target) != item["sha256"]:
            fail(f"source-closure mismatch: {item['archive_path']}")
        count += 1
    patch = closure.get("full_diff")
    if patch:
        target = root_join(root, patch["archive_path"])
        if not target.is_file() or sha256_file(target) != patch["sha256"]:
            fail("full diff is missing or changed")
        count += 1
    return count


def verify_external_dependencies(root: Path, inventory: Dict[str, Any]) -> int:
    count = 0
    for dependency in inventory.get("external_dependencies", []):
        target = root_join(root, dependency["recursive_manifest_archive_path"])
        if not target.is_file():
            fail(f"external dependency manifest missing: {target}")
        if sha256_file(target) != dependency["recursive_manifest_sha256"]:
            fail(f"external dependency manifest mismatch: {target}")
        count += 1
    return count


def verify_semantics(inventory: Dict[str, Any], allow_incomplete: bool) -> List[str]:
    if inventory.get("schema") != EXPECTED_SCHEMA:
        fail(f"unsupported inventory schema: {inventory.get('schema')!r}")
    blockers: List[str] = []
    ids = set()
    for evidence in inventory.get("evidence", []):
        identifier = evidence.get("id")
        if not identifier or identifier in ids:
            fail(f"empty or duplicate evidence id: {identifier!r}")
        ids.add(identifier)
        status = evidence.get("status")
        contributes = evidence.get("may_contribute")
        included = evidence.get("included")
        tier = evidence.get("tier")
        if contributes and (status != "pass" or not included or tier != "formal"):
            fail(f"illegal contributing evidence state: {identifier}")
        if tier == "supplemental" and contributes:
            fail(f"supplemental evidence may not contribute: {identifier}")
        if status in {"invalid", "pending", "pass_pre_gate"} and contributes:
            fail(f"non-contributing status marked as contributing: {identifier}")
        if evidence.get("required_for_final") and not contributes:
            blockers.append(identifier)
    declared = inventory.get("release", {}).get("blockers", [])
    if sorted(declared) != sorted(blockers):
        fail(f"declared blockers differ: declared={declared}, computed={blockers}")
    sealed = inventory.get("release", {}).get("sealed", False)
    if sealed == bool(blockers):
        fail("release.sealed is inconsistent with blockers")
    if blockers and not allow_incomplete:
        fail(f"bundle is incomplete; blockers={blockers}")
    for dependency in inventory.get("external_dependencies", []):
        if dependency.get("content_included") is not False:
            fail("external dependency content must not be represented as included")
        if dependency.get("verification_scope") != "provenance_manifest_only":
            fail("external dependency verification scope is ambiguous")
    return blockers


def verify(root: Path, allow_incomplete: bool) -> Dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        fail(f"bundle root is not a directory: {root}")
    inventory_path = root / "inventory.json"
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read inventory.json: {exc}")
    blockers = verify_semantics(inventory, allow_incomplete)
    overall = verify_overall_manifest(root)
    artifacts = verify_artifacts(root, inventory)
    source_files = verify_source_closure(root, inventory)
    external_manifests = verify_external_dependencies(root, inventory)
    historical = claims = tree_files = 0
    for evidence in inventory.get("evidence", []):
        if not evidence.get("included"):
            continue
        tree_files += verify_tree_binding(root, evidence)
        historical += verify_historical_manifest(root, evidence)
        claims += verify_claims(root, evidence)
    return {
        "schema": "g4-029-portable-verification-report-v1",
        "status": "PASS",
        "sealed": inventory["release"]["sealed"],
        "blockers": blockers,
        "overall_manifest_entries": overall,
        "historical_manifest_entries": historical,
        "evidence_tree_files": tree_files,
        "bound_artifacts": artifacts,
        "source_closure_files": source_files,
        "external_dependency_manifests": external_manifests,
        "claim_assertions": claims,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_root", type=Path)
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="verify integrity of an explicitly unsealed planning bundle",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        help="write report outside the immutable bundle (stdout is always emitted)",
    )
    args = parser.parse_args(argv)
    try:
        report = verify(args.bundle_root, args.allow_incomplete)
    except VerificationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    sys.stdout.write(rendered)
    if args.json_report:
        report_path = args.json_report.resolve()
        bundle_path = args.bundle_root.resolve()
        if report_path == bundle_path or bundle_path in report_path.parents:
            print("FAIL: --json-report must be outside the immutable bundle", file=sys.stderr)
            return 1
        args.json_report.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
