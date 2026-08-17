#!/usr/bin/env python3
"""Create a byte-reproducible .tar.gz from a verified staging directory."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
from typing import Iterable, List, Tuple


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def entries(root: Path) -> Tuple[List[str], List[str]]:
    directories = {""}
    files: List[str] = []
    for parent, dirnames, filenames in os.walk(str(root), followlinks=False):
        parent_path = Path(parent)
        for dirname in dirnames:
            path = parent_path / dirname
            if path.is_symlink():
                raise RuntimeError(f"symlink forbidden: {path}")
            directories.add(path.relative_to(root).as_posix())
        for filename in filenames:
            path = parent_path / filename
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise RuntimeError(f"non-regular file forbidden: {path}")
            files.append(path.relative_to(root).as_posix())
    return sorted(directories), sorted(files)


def normalized_info(name: str, *, directory: bool, executable: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name + ("/" if directory and not name.endswith("/") else ""))
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.size = 0
    info.mode = 0o755 if directory or executable else 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.pax_headers = {}
    return info


def create(root: Path, output: Path, root_name: str) -> None:
    root = root.resolve()
    output = output.resolve()
    if not root.is_dir():
        raise RuntimeError(f"staging root missing: {root}")
    if output == root or root in output.parents:
        raise RuntimeError("tar output must be outside staging root")
    archive_root = PurePosixPath(root_name)
    if archive_root.is_absolute() or ".." in archive_root.parts or len(archive_root.parts) != 1:
        raise RuntimeError("root-name must be one safe POSIX path component")
    directories, files = entries(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents an unnoticed overwrite of a previous seal.
    with output.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                for relative in directories:
                    name = archive_root.as_posix() if not relative else (archive_root / relative).as_posix()
                    archive.addfile(normalized_info(name, directory=True))
                for relative in files:
                    source = root / PurePosixPath(relative)
                    executable = bool(source.stat().st_mode & 0o111)
                    name = (archive_root / relative).as_posix()
                    info = normalized_info(name, directory=False, executable=executable)
                    info.size = source.stat().st_size
                    with source.open("rb") as stream:
                        archive.addfile(info, stream)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("staging_root", type=Path)
    parser.add_argument("output_tar_gz", type=Path)
    parser.add_argument("--root-name", default="g4-029-identifier-independent-acceptance")
    parser.add_argument("--allow-unsealed", action="store_true")
    args = parser.parse_args(argv)
    try:
        # Import the sibling verifier whether this tool is run from the plan
        # directory or from tools/ inside a staged bundle.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import verify_archive
        report = verify_archive.verify(args.staging_root, args.allow_unsealed)
        create(args.staging_root, args.output_tar_gz, args.root_name)
        result = {
            "schema": "g4-029-deterministic-tar-result-v1",
            "status": "PASS",
            "input_verification": report,
            "tar_gz": str(args.output_tar_gz),
            "size_bytes": args.output_tar_gz.stat().st_size,
            "sha256": sha256_file(args.output_tar_gz),
        }
        print(json.dumps(result, sort_keys=True, indent=2))
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
