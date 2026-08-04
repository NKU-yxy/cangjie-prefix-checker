#!/usr/bin/env python3
"""Verify native semantics across byte, random, and cl100k fragmentations."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import random
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def project_cases() -> list[tuple[str, str, bool]]:
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "test_cases" for target in node.targets):
            return [(str(name), str(source), bool(valid)) for name, source, valid in ast.literal_eval(node.value)]
    raise RuntimeError("main.py test_cases not found")


def chunks_for(source: str, seed: int) -> list[list[bytes]]:
    payload = source.encode("utf-8")
    rng = random.Random(seed)
    random_chunks: list[bytes] = []
    cursor = 0
    while cursor < len(payload):
        size = rng.randint(1, 11)
        random_chunks.append(payload[cursor : cursor + size])
        cursor += size
    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")
    token_chunks = [encoding.decode([token]).encode("utf-8") for token in encoding.encode(source)]
    return [[bytes([byte]) for byte in payload], random_chunks, token_chunks, [payload]]


def run(driver: Path, context: Path, fragments: list[bytes]) -> bool:
    proc = subprocess.run(
        [str(driver), str(context)],
        input="".join(fragment.hex() + "\n" for fragment in fragments),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return "1" not in proc.stdout.splitlines()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--driver", type=Path)
    args = parser.parse_args()
    context = ROOT / "generated" / "context.bin"
    with tempfile.TemporaryDirectory(prefix="cangjie-native-fragments-") as temp:
        driver = args.driver.resolve() if args.driver else Path(temp) / "native_semantic_driver"
        if not args.driver:
            subprocess.run(
                [
                    "c++", "-std=c++17", "-O2", "-DNDEBUG", "-Icpp",
                    "tools/native_semantic_driver.cpp", "cpp/native_semantic.cpp",
                    "-o", str(driver),
                ],
                cwd=ROOT,
                check=True,
            )
        failures: list[str] = []
        semantic_cases = [case for case in project_cases() if not case[0].startswith("Invalid:")]
        for index, (name, source, expected) in enumerate(semantic_cases):
            results = [run(driver, context, chunks) for chunks in chunks_for(source, args.seed + index)]
            if any(result != expected for result in results) or len(set(results)) != 1:
                failures.append(f"{name}: expected={expected}, fragment results={results}")
        if failures:
            print("\n".join(failures))
            return 1
        print(
            f"native fragment differential: {len(semantic_cases)}/{len(semantic_cases)} "
            "semantic cases x 4 fragmentations passed"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
