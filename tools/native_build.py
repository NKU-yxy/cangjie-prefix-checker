"""Shared build inputs for the native semantic checker and its test driver."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "cpp" / "native_semantic_sources.txt"


def native_semantic_sources() -> list[str]:
    """Return repository-relative C++ sources from the shared manifest."""
    try:
        lines = SOURCE_MANIFEST.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(f"cannot read native source manifest: {SOURCE_MANIFEST}") from exc

    sources = [
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not sources:
        raise RuntimeError(f"native source manifest is empty: {SOURCE_MANIFEST}")

    missing = [source for source in sources if not (ROOT / source).is_file()]
    if missing:
        raise RuntimeError(
            "native source manifest references missing files: " + ", ".join(missing)
        )
    return sources


def native_driver_command(
    target: Path,
    *,
    compiler: str = "c++",
    compile_flags: Iterable[str] = ("-std=c++17", "-O2", "-DNDEBUG"),
) -> list[str]:
    """Build a command for the standalone native semantic test driver."""
    return [
        compiler,
        *compile_flags,
        "-Icpp",
        "tools/native_semantic_driver.cpp",
        *native_semantic_sources(),
        "-o",
        str(target),
    ]
