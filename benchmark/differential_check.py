#!/usr/bin/env python3
"""Differential regression against the public oracle and its unit corpus.

This checker intentionally derives cases from the official repository rather
than embedding public file names or answer positions in production code.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _official_programs(test_root: Path):
    seen: set[str] = set()
    for path in sorted(test_root.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in (
            item for item in tree.body if isinstance(item, ast.FunctionDef)
        ):
            for node in ast.walk(function):
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                target = node.targets[0]
                if not isinstance(target, ast.Name) or target.id not in {"src", "program"}:
                    continue
                try:
                    source = ast.literal_eval(node.value)
                except (TypeError, ValueError):
                    continue
                if not isinstance(source, str) or source in seen:
                    continue
                if not any(marker in source for marker in ("main", "func ", "class ", "interface ")):
                    continue
                seen.add(source)
                yield path.name, function.name, source


def _project_programs(main_path: Path):
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "test_cases"
            for target in node.targets
        ):
            continue
        try:
            cases = ast.literal_eval(node.value)
        except (TypeError, ValueError):
            return
        for name, source, expected in cases:
            yield str(name), str(source), bool(expected)
        return


def _external_first_error(
    solution: Path,
    token_ids: list[int],
    *,
    mode: str,
    context_path: Path,
) -> tuple[int | None, str]:
    command = [str(solution), "--semantic-mode", mode, "--context", str(context_path)]
    proc = subprocess.run(
        command,
        cwd=ROOT,
        input="".join(f"{token_id}\n" for token_id in token_ids),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        return 0, f"exit={proc.returncode}: {proc.stderr.strip()[:300]}"
    lines = [line.strip() for line in proc.stdout.splitlines()]
    for index, answer in enumerate(lines):
        if answer == "1":
            return index, ""
        if answer != "0":
            return index, f"invalid answer {answer!r}"
    if len(lines) != len(token_ids):
        return len(lines), f"expected {len(token_ids)} responses, got {len(lines)}"
    return None, ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--official-root",
        type=Path,
        default=ROOT.parent / "cangjie-fragment-checker",
    )
    parser.add_argument(
        "--mode",
        choices=("fast", "checkpoint", "legacy"),
        default="fast",
    )
    parser.add_argument(
        "--solution",
        type=Path,
        default=None,
        help="Run an external protocol executable instead of the Python checker.",
    )
    args = parser.parse_args()

    official = args.official_root.resolve()
    context_path = ROOT / "context.json"
    import tiktoken

    from src.batch_semantic_validator import BatchSemanticValidator
    from src.stream_checker import CangjieStreamChecker

    # Configure and import the vendored public oracle.
    BatchSemanticValidator(context_path=str(context_path))
    from typechecker.checker import typecheck_tree
    from typechecker.errors import TypeCheckError
    from typechecker.parser import parse

    encoding = tiktoken.get_encoding("cl100k_base")
    failures: list[str] = []

    registry = json.loads(
        (official / "wrong_error_positions.json").read_text(encoding="utf-8")
    )["wrong_examples"]
    for item in registry:
        source = (official / "wrong" / f"{item['name']}.cj").read_text(
            encoding="utf-8"
        )
        token_ids = encoding.encode(source)
        if args.solution:
            first_error, protocol_error = _external_first_error(
                args.solution.resolve(), token_ids, mode=args.mode,
                context_path=context_path,
            )
            if protocol_error:
                failures.append(f"{item['name']}: {protocol_error}")
        else:
            checker = CangjieStreamChecker(
                semantic_mode=args.mode,
                context_path=str(context_path),
            )
            first_error = None
            for index, token_id in enumerate(token_ids):
                if not checker.feed_text(encoding.decode([token_id])).ok:
                    first_error = index
                    break
        expected = int(item["first_error_token_index"])
        if first_error != expected:
            failures.append(
                f"{item['name']}: expected token {expected}, got {first_error}"
            )

    corpus_total = 0
    corpus_matched = 0
    for filename, test_name, source in _official_programs(
        official / "typechecker" / "tests"
    ):
        try:
            typecheck_tree(parse(source))
            expected = True
        except TypeCheckError:
            expected = False
        except Exception:
            # Some parser-focused tests intentionally use syntax outside the
            # semantic corpus.  The token grammar tests those separately.
            continue
        corpus_total += 1
        token_ids = encoding.encode(source)
        if args.solution:
            first_error, protocol_error = _external_first_error(
                args.solution.resolve(), token_ids, mode=args.mode,
                context_path=context_path,
            )
            actual = first_error is None
            if protocol_error:
                failures.append(f"{filename}:{test_name}: {protocol_error}")
        else:
            checker = CangjieStreamChecker(
                semantic_mode=args.mode,
                context_path=str(context_path),
            )
            actual = True
            for token_id in token_ids:
                status = checker.feed_text(encoding.decode([token_id]))
                if not status.ok:
                    actual = False
                    break
        if actual == expected:
            corpus_matched += 1
        else:
            failures.append(
                f"{filename}:{test_name}: expected valid={expected}, got {actual}"
            )

    project_total = 0
    project_matched = 0
    if args.solution:
        for test_name, source, expected in _project_programs(ROOT / "main.py"):
            project_total += 1
            first_error, protocol_error = _external_first_error(
                args.solution.resolve(), encoding.encode(source), mode=args.mode,
                context_path=context_path,
            )
            actual = first_error is None
            if not protocol_error and actual == expected:
                project_matched += 1
            else:
                detail = f"; {protocol_error}" if protocol_error else ""
                failures.append(
                    f"main.py:{test_name}: expected valid={expected}, got {actual}{detail}"
                )

    summary = {
        "mode": args.mode,
        "solution": str(args.solution) if args.solution else "python-in-process",
        "public_exact": len(registry) - sum(
            1 for item in failures if item.startswith("err_")
        ),
        "public_total": len(registry),
        "oracle_corpus_matched": corpus_matched,
        "oracle_corpus_total": corpus_total,
        "project_corpus_matched": project_matched,
        "project_corpus_total": project_total,
        "failures": len(failures),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
