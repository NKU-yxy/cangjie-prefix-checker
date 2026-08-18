#!/usr/bin/env python3
"""Token-by-token interaction test harness.

Subprocess protocol (this repo's convention; **not** the competition's 1/0 labels):
1. Harness sends one tiktoken token ID per line on stdin (full file text, default
   encoding ``cl100k_base``).
2. Subprocess replies with one line per round: ``"0"`` or ``"1"``.
   - ``"0"``: no error reported at this round (prefix still treated as OK for this harness).
   - ``"1"``: error reported at this round (prefix should be treated as not continuable).

**First error token (registry meaning):** For a wrong example listed in
``wrong_error_positions.json``, ``first_error_token_index`` is the **0-based**
index into the same tiktoken ``encode(file_text)`` stream the harness uses. It is
the index ``i`` of the **first** token such that the prefix consisting of tokens
``0..i`` (inclusive) **cannot** be extended to a fully compilable Cangjie program,
while the strict prefix ``0..i-1`` **still can**. If you number tokens from 1, that
is the smallest ``k`` such that tokens ``1..(k-1)`` are continuable and tokens ``1..k``
are not; then ``first_error_token_index = k - 1``. This is **not** the same as the
first ``cjc`` diagnostic line/column; do not infer the index from the compiler alone.

Judging:
- For stems listed in ``wrong_error_positions.json``: the subprocess is correct iff
  it returns ``"1"`` on the round whose index equals ``first_error_token_index``, and
  ``"0"`` on all earlier rounds (the harness stops after the first ``"1"``).
- For other files (treated as correct): the subprocess is correct iff it always
  returns ``"0"``.

Final output is exactly: PASSED or FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_first_error_token_indices(json_path: Path) -> dict[str, int]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for item in data.get("wrong_examples", []):
        name = item["name"]
        if "first_error_token_index" not in item:
            raise ValueError(
                f"{json_path}: entry {name!r} missing first_error_token_index."
            )
        out[name] = int(item["first_error_token_index"])
    return out


def resolve_cj_file(root: Path, user_arg: str) -> Path:
    p = Path(user_arg)
    if p.exists():
        return p.resolve()

    rel = user_arg
    if rel.startswith("samples/"):
        rel = rel[len("samples/") :]

    candidates = [
        root / rel,
        root / "wrong" / rel,
        root / "wrong" / Path(rel).name,
        root / Path(rel).name,
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError(f"Cangjie file not found: {user_arg}")


def run_test(
    cj_file: Path,
    token_ids: list[int],
    target_idx: int | None,
    command: list[str],
    timeout_s: float,
) -> bool:
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    assert proc.stdin is not None
    assert proc.stdout is not None

    try:
        for idx, tok in enumerate(token_ids):
            proc.stdin.write(f"{tok}\n")
            proc.stdin.flush()

            line = proc.stdout.readline()
            if line == "":
                return False
            ans = line.strip()
            if ans not in {"0", "1"}:
                return False

            expected = "1" if (target_idx is not None and idx == target_idx) else "0"
            if ans != expected:
                return False

            if expected == "1":
                return True

        return target_idx is None
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=timeout_s)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run token interaction test against a subprocess."
    )
    parser.add_argument("cangjie_file", help="Cangjie file path or filename.")
    parser.add_argument(
        "--encoding",
        default="cl100k_base",
        help="tiktoken encoding name (default: cl100k_base).",
    )
    parser.add_argument(
        "--error-json",
        default=None,
        help="Path to wrong_error_positions.json (default: wrong_error_positions.json).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Subprocess terminate wait timeout in seconds (default: 2.0).",
    )
    parser.add_argument(
        "--cmd",
        nargs=argparse.REMAINDER,
        required=True,
        help="Command to test, e.g. --cmd python3 solution.py",
    )
    args = parser.parse_args()

    root = repo_root()

    tiktoken_cache_dir = root / "tiktoken_cache"
    tiktoken_cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(tiktoken_cache_dir))

    import tiktoken  # pylint: disable=import-outside-toplevel

    error_json = (
        Path(args.error_json).resolve()
        if args.error_json
        else (root / "wrong_error_positions.json")
    )
    error_map = load_first_error_token_indices(error_json)

    cj_file = resolve_cj_file(root, args.cangjie_file)
    text = cj_file.read_text(encoding="utf-8")

    enc = tiktoken.get_encoding(args.encoding)
    token_ids = enc.encode(text)

    stem = cj_file.stem
    target_idx: int | None = None
    if stem in error_map:
        target_idx = error_map[stem]
        if target_idx < 0 or target_idx >= len(token_ids):
            raise SystemExit(
                f"{error_json}: first_error_token_index {target_idx} out of range "
                f"for {cj_file} (token count {len(token_ids)})"
            )

    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        raise SystemExit("Missing command after --cmd")

    ok = run_test(cj_file, token_ids, target_idx, cmd, timeout_s=args.timeout)
    print("PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
