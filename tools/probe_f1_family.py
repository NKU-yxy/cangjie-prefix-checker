"""F1 family probe: official typechecker (context_final) adjudication vs v12
solution fire behavior for Array.first/last as Optional<T> instance fields.

Usages:
    python3 probe_f1_v12.py oracle     # official typechecker adjudication
    python3 probe_f1_v12.py fire       # solution first-fire token index
    python3 probe_f1_v12.py both       # both (default)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TC = ROOT / "official-reference" / "typechecker"
SOLUTION = ROOT / "project3230617-388044" / "solution"

sys.path.insert(0, str(TC))
import typechecker.builtin_context as bc
bc._CONTEXT_PATH = TC / "typechecker" / "context_final.json"
if hasattr(bc, "_builtin_ctx_singleton"):
    bc._builtin_ctx_singleton = None
from typechecker.parser import parse
from typechecker.checker import typecheck_tree
from typechecker.errors import TypeCheckError

CASES = {
    # legal field usage
    "first_field_opt": (
        'main(): Unit {\n    let a: Array<Int64> = [1, 2]\n'
        '    let o: Optional<Int64> = a.first\n    println((o.isSome).toString())\n}\n'
    ),
    "last_field_opt": (
        'main(): Unit {\n    let a: Array<Int64> = [1, 2]\n'
        '    let o: Optional<Int64> = a.last\n    println((o.isSome).toString())\n}\n'
    ),
    "first_chain": (
        'main(): Unit {\n    let a: Array<Int64> = [1, 2]\n'
        '    let s: String = (a.first.getOrThrow()).toString()\n    println(s)\n}\n'
    ),
    # field-as-call must be invalid
    "first_as_call": (
        'main(): Unit {\n    let a: Array<Int64> = [1, 2]\n'
        '    let o: Optional<Int64> = a.first()\n    println((o.isSome).toString())\n}\n'
    ),
    "last_as_call": (
        'main(): Unit {\n    let a: Array<Int64> = [1, 2]\n'
        '    let o: Optional<Int64> = a.last()\n    println((o.isSome).toString())\n}\n'
    ),
    # String target mismatch (err_array_first_optional family)
    "first_to_string": (
        'main(): Unit {\n    let a: Array<Int64> = [1, 2]\n'
        '    let s: String = a.first\n    println(s)\n}\n'
    ),
    "first_tostring_recover": (
        'main(): Unit {\n    let a: Array<Int64> = [1, 2]\n'
        '    let s: String = (a.first.toString())\n    println(s)\n}\n'
    ),
    # generic substitution
    "first_generic_string": (
        'func pick<T>(a: Array<T>): Optional<T> { a.first }\n'
        'main(): Unit {\n    let s: Optional<String> = pick<String>(["x"])\n'
        '    println((s.isSome).toString())\n}\n'
    ),
    # size stays a field alongside
    "size_field": (
        'main(): Unit {\n    let a: Array<Int64> = [1, 2]\n'
        '    let n: Int64 = a.size\n    println((n).toString())\n}\n'
    ),
}

def oracle(src):
    try:
        typecheck_tree(parse(src))
        return "NO ERROR"
    except TypeCheckError as e:
        diag = getattr(e, "diagnostic", None)
        if diag is None:
            return f"TypeCheckError: {e}"
        return f"[{diag.code}][{diag.phase}] line={diag.line} col={diag.column} msg={diag.message[:70]}"
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:90]}"

def fire_index(src):
    """First token index (cl100k_base) where solution answers 1."""
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    ids = enc.encode(src)
    proc = subprocess.Popen(
        [str(SOLUTION)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1)
    assert proc.stdin and proc.stdout
    try:
        for idx, tok in enumerate(ids):
            proc.stdin.write(f"{tok}\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if line == "":
                return f"EOF after {idx}"
            ans = line.strip()
            if ans not in {"0", "1"}:
                return f"bad reply {ans!r} at {idx}"
            if ans == "1":
                return idx
        return "NO FIRE"
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.terminate()
        proc.wait(timeout=30)

def show(only_oracle=False, only_fire=False):
    for name, src in CASES.items():
        parts = []
        if not only_fire:
            parts.append(f"oracle={oracle(src)}")
        if not only_oracle:
            parts.append(f"fire={fire_index(src)}")
        print(f"{name:24s} {'  '.join(parts)}")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode == "oracle":
        show(only_oracle=True)
    elif mode == "fire":
        show(only_fire=True)
    else:
        show()
