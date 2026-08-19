#!/usr/bin/env python3
"""Create the self-contained contest submission archive.

The archive deliberately contains sources plus the one supported build script;
it never contains a prebuilt ``solution`` or generated build outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import stat
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_CONTEXT_SHA256 = "facb628ab01a52d7ef8f2fe36ca463ccd381e02e45282c82803b793730068303"
DEFAULT_OUTPUT = ROOT / "dist" / "cangjie-fragment-checker-submission.zip"
TOP_LEVEL_FILES = ("build.sh", "context.json", "THIRD_PARTY_NOTICES.md")
TREE_PATHS = (
    "assets/cl100k_base.bin.xz",
    "cpp",
    "grammar",
    "third_party/xgrammar_core",
)
EXTRA_FILES = (
    "tools/generate_context_table.py",
    "src/__init__.py",
    "src/context_loader.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collect_files() -> list[Path]:
    files = [ROOT / relative for relative in TOP_LEVEL_FILES]
    files += [ROOT / relative for relative in EXTRA_FILES]
    for relative in TREE_PATHS:
        candidate = ROOT / relative
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(path for path in sorted(candidate.rglob("*")) if path.is_file())
        else:
            raise FileNotFoundError(candidate)
    missing = [str(path.relative_to(ROOT)) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing submission files: " + ", ".join(missing))
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def validate(files: list[Path]) -> None:
    context = ROOT / "context.json"
    actual_hash = sha256(context)
    if actual_hash != EXPECTED_CONTEXT_SHA256:
        raise ValueError(
            "context.json does not match context_final.json: "
            f"expected {EXPECTED_CONTEXT_SHA256}, got {actual_hash}"
        )
    build_script = ROOT / "build.sh"
    if not build_script.stat().st_mode & stat.S_IXUSR:
        raise ValueError("build.sh must be executable")
    names = [path.relative_to(ROOT).as_posix() for path in files]
    if names.count("build.sh") != 1:
        raise ValueError("submission must contain exactly one build.sh")
    forbidden = {"solution", "build_local.sh"}
    present = forbidden.intersection(names)
    if present:
        raise ValueError("generated artifacts must not be packaged: " + ", ".join(sorted(present)))


def write_entry(archive: zipfile.ZipFile, path: Path) -> None:
    name = path.relative_to(ROOT).as_posix()
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    # Preserve owner read/write bits and mark build.sh executable in the archive.
    mode = 0o755 if name == "build.sh" else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="output ZIP path")
    args = parser.parse_args()
    output = args.output.resolve()
    files = collect_files()
    validate(files)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for path in files:
            write_entry(archive, path)
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP integrity check failed at {bad}")
        archive_names = archive.namelist()
    if archive_names.count("build.sh") != 1 or "solution" in archive_names:
        raise RuntimeError("output ZIP layout validation failed")
    print(f"created {output}")
    print(f"files: {len(archive_names)}")
    print(f"context.json sha256: {sha256(ROOT / 'context.json')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
