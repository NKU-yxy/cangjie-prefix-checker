#!/usr/bin/env python3
"""Exercise native loading of variables, overloads, defaults, and generic classes."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.native_build import native_driver_command


CONTEXT = {
    "global_variables": {"external": {"kind": "let", "type": "Int64"}},
    "global_functions": {
        "choose": [
            {"params": [{"name": "x", "type": "Int64"}], "ret": "Int64"},
            {"params": [{"name": "x", "type": "String"}], "ret": "String"},
        ],
        "sumDefault": [{
            "params": [
                {"name": "a", "type": "Int64"},
                {"name": "b", "type": "Int64"},
            ],
            "defaults": {"b": "0"},
            "ret": "Int64",
        }],
    },
    "interfaces": {"Named": {"methods": {"get": [{"params": [], "ret": "Int64"}]}}},
    "classes": {
        "Gadget": {
            "type_params": ["T"],
            "constructors": [{"params": [{"name": "value", "type": {"tparam": "T"}}]}],
            "instance_fields": {"value": {"tparam": "T"}},
            "instance_methods": {"get": [{"params": [], "ret": {"tparam": "T"}}]},
            "static_fields": {"version": "Int64"},
        }
    },
}


CASES = [
    ("global variable", "main(): Unit { let x: Int64 = external; }", True),
    ("overload", "main(): Unit { let x: String = choose(\"ok\"); }", True),
    ("overload mismatch", "main(): Unit { let x: String = choose(1); }", False),
    ("default parameter", "main(): Unit { let x: Int64 = sumDefault(1); }", True),
    ("generic class", "main(): Unit { let g: Gadget<Int64> = Gadget<Int64>(1); let x: Int64 = g.get(); }", True),
    ("generic constructor mismatch", "main(): Unit { let g: Gadget<Int64> = Gadget<Int64>(\"bad\"); }", False),
    ("static field", "main(): Unit { let x: Int64 = Gadget.version; }", True),
]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cangjie-native-context-") as temp_name:
        temp = Path(temp_name)
        source_context = temp / "context.json"
        context_table = temp / "context.bin"
        driver = temp / "native_semantic_driver"
        source_context.write_text(json.dumps(CONTEXT), encoding="utf-8")
        subprocess.run(
            [sys.executable, "tools/generate_context_table.py", str(source_context), str(context_table)],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            native_driver_command(driver),
            cwd=ROOT,
            check=True,
        )
        failures: list[str] = []
        for name, source, expected in CASES:
            fragments = [source[index : index + 3].encode("utf-8") for index in range(0, len(source), 3)]
            proc = subprocess.run(
                [str(driver), str(context_table)],
                input="".join(fragment.hex() + "\n" for fragment in fragments),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            actual = "1" not in proc.stdout.splitlines()
            if actual != expected:
                failures.append(f"{name}: expected={expected}, got={actual}")
        if failures:
            print("\n".join(failures))
            return 1
        print(f"native context differential: {len(CASES)}/{len(CASES)} passed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
