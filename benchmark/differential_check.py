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
        checker = CangjieStreamChecker(
            semantic_mode=args.mode,
            context_path=str(context_path),
        )
        first_error = None
        for index, token_id in enumerate(encoding.encode(source)):
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
        checker = CangjieStreamChecker(
            semantic_mode=args.mode,
            context_path=str(context_path),
        )
        actual = True
        for token_id in encoding.encode(source):
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

    summary = {
        "mode": args.mode,
        "public_exact": len(registry) - sum(
            1 for item in failures if item.startswith("err_")
        ),
        "public_total": len(registry),
        "oracle_corpus_matched": corpus_matched,
        "oracle_corpus_total": corpus_total,
        "failures": len(failures),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
