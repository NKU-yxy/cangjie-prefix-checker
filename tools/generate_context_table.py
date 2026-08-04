#!/usr/bin/env python3
"""Compile context.json into the dependency-free native runtime table."""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.context_loader import load_context


MAGIC = b"CJCT\x01\x00\x00\x00"


class Writer:
    def __init__(self) -> None:
        self.data = bytearray(MAGIC)

    def u32(self, value: int) -> None:
        self.data.extend(struct.pack("<I", value))

    def text(self, value: object) -> None:
        encoded = str(value or "").encode("utf-8")
        self.u32(len(encoded))
        self.data.extend(encoded)

    def texts(self, values: list[object]) -> None:
        self.u32(len(values))
        for value in values:
            self.text(value)

    def fields(self, values: dict[str, object]) -> None:
        self.u32(len(values))
        for name, value in sorted(values.items()):
            self.text(name)
            self.text(value)

    def signature(self, value: dict[str, object]) -> None:
        self.text(value.get("name"))
        self.text(value.get("return_type") or "Unit")
        self.texts(list(value.get("type_params") or []))
        self.texts(list(value.get("param_names") or []))
        self.texts(list(value.get("param_types") or []))
        self.u32(int(value.get("required_params") or 0))

    def signatures(self, values: list[dict[str, object]]) -> None:
        self.u32(len(values))
        for value in values:
            self.signature(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    context = load_context(str(args.input))
    writer = Writer()

    variables = context["variables"]
    writer.u32(len(variables))
    for variable in variables:
        writer.text(variable.get("name"))
        writer.text(variable.get("type"))
        writer.u32(1 if variable.get("mutable") else 0)

    writer.signatures(context["functions"])
    nominals = [*context["classes"], *context["interfaces"]]
    writer.u32(len(nominals))
    for nominal in nominals:
        writer.text(nominal.get("name"))
        writer.u32(1 if nominal.get("kind") == "interface" else 0)
        writer.texts(list(nominal.get("type_params") or []))
        writer.texts(list(nominal.get("supers") or []))
        writer.fields(dict(nominal.get("fields") or {}))
        writer.fields(dict(nominal.get("static_fields") or {}))
        writer.signatures(list(nominal.get("methods") or []))
        writer.signatures(list(nominal.get("static_methods") or []))
        writer.signatures(list(nominal.get("constructor_signatures") or []))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(writer.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
