"""Probe /ref (official) typechecker behavior on min/max/varargs cases."""
import sys
from pathlib import Path

sys.path.insert(0, "/ref/typechecker")
import typechecker.builtin_context as bc  # noqa: E402

bc._CONTEXT_PATH = Path("/workspace/context.json")
bc._builtin_ctx_singleton = None
from typechecker.checker import typecheck_tree  # noqa: E402
from typechecker.errors import TypeCheckError  # noqa: E402
from typechecker.parser import parse  # noqa: E402

PAD = Path("/tmp/ref_probe.cj").read_text()
MARKER = "min(1, 2, [3, 4])"


def probe(stmt):
    src = PAD.replace(MARKER, stmt)
    try:
        typecheck_tree(parse(src))
        return "ACCEPT"
    except TypeCheckError as e:
        return str(e)[:200]


cases = [
    'min(1, "x", [3])',
    'min(1, "x", 3)',
    "min(1, 2)",
    "min(1, 2, [3, 4])",
    "min(1, 2, 3)",
    'min("x", 1, [3])',
    "max(1, 2)",
    "max(1.5, 2.5, [3.5])",
    "max(1, 2, 3)",
    "abs(1)",
    "abs(1.5)",
    'abs("bad")',
    "clamp(1.5, 0.5, 2.5)",
    "clamp(1, 1.5, 1.5)",
    "println('a')",
    "println('a', 1)",
    'print("x", 1)',
    "print(1, true)",
    "min(1, 1, [1, 2])",
    "let z: String = min(1, 1, [1, 2])",
]
for c in cases:
    print(f"{c!r:34s} -> {probe(c)}")
