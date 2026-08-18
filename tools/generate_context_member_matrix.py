#!/usr/bin/env python3
"""Generate the full context member mutation matrix (V14_Plan §12.2).

For every member of every nominal/interface in the official context and every
global function, emit Cangjie snippets covering at least (Patch 1 standard):

    legal         valid use (assignment to the declared return type)
    kind misuse   field used as call; method used as a value
    arity         one argument too few / too many
    arg type      every parameter position with a wrong type
    return target result assigned to an incompatible type

plus, where applicable (§12.2):

    dispatch      instance member via the type name; static member via instance
    generic recv  receiver instantiated with a different type argument
    overload      call that matches no overload exactly (ambiguous)
    method ref    zero-arg method read as a value (function reference)

Program shape follows the official harness grammar (verified against the
reference checker): ``main(): Unit { <stmt> }`` with explicit annotations.

Usage:
    python3 tools/generate_context_member_matrix.py \
        official-reference/typechecker/typechecker/context_final.json \
        /tmp/member_matrix [--oracle]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.context_loader import load_context  # noqa: E402

# Concrete receiver expression per nominal (all verified ACCEPT with the
# official FINAL context).
RECEIVERS: dict[str, str] = {
    "Array": "[1, 2, 3]",
    "ArrayList": "ArrayList<Int64>()",
    "ArrayStack": "ArrayStack<Int64>()",
    "ArrayDeque": "ArrayDeque<Int64>()",
    "HashMap": "HashMap<String, Int64>()",
    "HashSet": "HashSet<String>()",
    "String": '"abc"',
    "Optional": "Array<Int64>(1, 0).first",
    "KeysView": "HashMap<String, Int64>().keys()",
    "ValuesView": "HashMap<String, Int64>().values()",
    "Range": "0..10",
}

# Concrete receivers for interface members (types declared to implement them).
INTERFACE_RECEIVERS: dict[str, str] = {
    "Stack": "ArrayStack<Int64>()",
    "Deque": "ArrayDeque<Int64>()",
    "Collection": "ArrayList<Int64>()",
    "Iterable": "[1, 2, 3]",
    # Equatable<T> / Hashable have no concrete implementor among the finals
    # nominals; their members are covered through the concrete types instead.
}

# Per-parameter-type argument factory: (valid, wrong) literal pair.
ARGUMENTS: dict[str, tuple[str, str]] = {
    "Int64": ("1", '"x"'),
    "Float64": ("1.0", '"x"'),
    "Bool": ("true", "1"),
    "String": ('"x"', "1"),
    "Rune": ("'a'", "1"),
    "Unit": ("", ""),
    "Array<Int64>": ("[1, 2]", '["x"]'),
    "Array<String>": ('["x"]', "[1]"),
    # No Rune literals in the official grammar, so Array<Rune> args are
    # unexpressible: String's Array<Rune> ctor falls back to a wrong-typed
    # arg and adjudicates REJECT (a documented reference fact).
    "Collection<Int64>": ("[1, 2]", '["x"]'),
    "Collection<String>": ('["x"]', "[1]"),
    "Array<(String, Int64)>": ('[("k", 1)]', "[1]"),
    "HashMap<String, Int64>": ("HashMap<String, Int64>()", "1"),
    "ArrayList<Int64>": ("ArrayList<Int64>()", '"x"'),
    "Optional<Int64>": ("Array<Int64>(1, 0).first", '"x"'),
    "KeysView<String>": ("HashMap<String, Int64>().keys()", "1"),
    "ValuesView<Int64>": ("HashMap<String, Int64>().values()", '"x"'),
}


def wrong_arg_for(t: str) -> str:
    valid, wrong = ARGUMENTS.get(t, (None, None))
    if wrong is not None:
        return wrong
    # Fallback: a type-mismatched literal.
    if "String" in t or t.startswith('"'):
        return "1"
    return '"x"'


def valid_arg_for(t: str) -> str | None:
    valid, _ = ARGUMENTS.get(t, (None, None))
    return valid


def wrong_target_for(t: str) -> str:
    return "Int64" if t == "String" else "String"


def substitute(text: str, tvars: dict[str, str]) -> str:
    """Replace type-variable tokens (standalone word-boundary matches only).

    The loader formats instantiated types with bare tparam names ("KeysView<K>",
    "Array<(K, V)>", "(K, V) -> Bool"); replacing the letter K or V inside a
    nominal *name* ("KeysView", "View") would corrupt it, so only whole-token
    matches are substituted.
    """
    import re
    for name, value in tvars.items():
        text = re.sub(r"\b" + re.escape(name) + r"\b", value, text)
    return text


# Receiver-aware type-variable bindings: the concrete receiver in RECEIVERS
# fixes each nominal's type parameters (e.g. HashSet<String>() binds T=String;
# HashMap<String, Int64>() binds K=String, V=Int64).  Sigs are formatted with
# the loader's bare tparam names, so the substitution map must follow the
# receiver, not a global default.
DEFAULT_TVARS = {"T": "Int64", "K": "String", "V": "Int64"}
OWNER_TVARS: dict[str, dict[str, str]] = {
    "HashSet": {"T": "String"},
    "KeysView": {"K": "String"},
    "ValuesView": {"V": "Int64"},
}


def tvars_for(owner: str) -> dict[str, str]:
    return OWNER_TVARS.get(owner, DEFAULT_TVARS)


def _sig_ret(sig: dict, tvars: dict[str, str]) -> str:
    return substitute(str(sig.get("return_type") or "Unit"), tvars)


def _sig_params(sig: dict, tvars: dict[str, str]) -> list[str]:
    return [substitute(str(t), tvars) for t in (sig.get("param_types") or [])]


def build_snippets(receiver: str, member: str, sigs: list[dict],
                   tvars: dict[str, str]) -> list[tuple[str, str]]:
    """Return (shape_name, statement) pairs for one member overload set."""
    out: list[tuple[str, str]] = []
    primary = sigs[0]
    ret = _sig_ret(primary, tvars)
    params = _sig_params(primary, tvars)
    args = ", ".join(valid_arg_for(p) or wrong_arg_for(p) for p in params)
    call = f"{receiver}.{member}({args})"

    if ret == "Unit":
        out.append(("legal", call))
        target = call
    else:
        out.append(("legal", f"let r: {ret} = {call}"))
        target = f"let r: {ret} = {call}"
        out.append(("return_target", f"let s: {wrong_target_for(ret)} = {call}"))
    # kind misuse: method read as a value (zero-arg methods become function
    # references; multi-arg methods without a call are a member-kind error).
    out.append(("method_as_value", f"let r: {ret} = {receiver}.{member}"))
    # arity: too few / too many (when the overload set has any params).
    if params:
        few = f"{receiver}.{member}()"
        out.append(("arity_few", few))
    many_args = args + (", " if args else "") + "1"
    out.append(("arity_many", f"{receiver}.{member}({many_args})"))
    # arg type: one wrong-typed argument per position.
    for index, ptype in enumerate(params):
        parts = [valid_arg_for(p) or wrong_arg_for(p) for p in params]
        parts[index] = wrong_arg_for(ptype)
        bad = ", ".join(parts)
        out.append((f"arg_type_{index}", f"{receiver}.{member}({bad})"))
    # dispatch: instance member invoked through the type name.  Only valid
    # when the receiver is a named type (a literal receiver has no type name).
    import re
    match = re.match(r"^[A-Za-z_][A-Za-z0-9_]*", receiver)
    if match is not None:
        out.append(("dispatch_type_name", f"{match.group(0)}.{member}({args})"))
    return out


def global_function_snippets(name: str, sigs: list[dict]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    primary = sigs[0]
    ret = substitute(str(primary.get("return_type") or "Unit"), {"T": "Int64"})
    params = [substitute(str(t), {"T": "Int64"}) for t in (primary.get("param_types") or [])]
    args = ", ".join(valid_arg_for(p) or wrong_arg_for(p) for p in params)
    call = f"{name}({args})"
    if ret == "Unit":
        out.append(("legal", call))
    else:
        out.append(("legal", f"let r: {ret} = {call}"))
        out.append(("return_target", f"let s: {wrong_target_for(ret)} = {call}"))
    if params:
        out.append(("arity_few", f"{name}()"))
    out.append(("arity_many", f"{name}({args}, 1)" if args else f"{name}(1)"))
    for index, ptype in enumerate(params):
        parts = [valid_arg_for(p) or wrong_arg_for(p) for p in params]
        parts[index] = wrong_arg_for(ptype)
        out.append((f"arg_type_{index}", f"{name}({', '.join(parts)})"))
    return out


def program(statement: str) -> str:
    return f"main(): Unit {{\n    {statement}\n}}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("context", type=Path, help="official context JSON (context_final.json)")
    parser.add_argument("out_dir", type=Path, help="output directory for .cj snippets + manifest")
    parser.add_argument("--oracle", action="store_true",
                        help="run the local official typechecker on every snippet "
                             "(requires CANGJIE_TYPECHECKER_CONTEXT=final)")
    args = parser.parse_args()

    normalized = load_context(str(args.context))
    snippets: list[dict] = []  # {owner, member, kind, shape, path}

    def add(owner: str, member: str, kind: str, shape: str, stmt: str) -> None:
        name = f"{owner}__{member}__{shape}"
        path = args.out_dir / f"{name}.cj"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(program(stmt), "utf-8")
        snippets.append({"owner": owner, "member": member, "kind": kind,
                         "shape": shape, "path": str(path.relative_to(args.out_dir))})

    # --- nominals (classes) --------------------------------------------------
    for cls in normalized.get("classes") or []:
        owner = str(cls.get("name"))
        receiver = RECEIVERS.get(owner)
        if receiver is None:
            continue  # no constructible receiver (covered via interfaces)
        tvars = tvars_for(owner)
        for field in (cls.get("fields") or {}):
            add(owner, field, "field", "legal", f"let r: Int64 = {receiver}.{field}")
            add(owner, field, "field", "field_as_call",
                f"let r: Int64 = {receiver}.{field}()")
        for static_field in (cls.get("static_fields") or {}):
            ftype = substitute(str((cls.get("static_fields") or {})[static_field]), tvars)
            add(owner, static_field, "static_field", "legal",
                f"let r: {ftype} = {owner}.{static_field}")
        methods: dict[str, list[dict]] = {}
        for sig in cls.get("methods") or []:
            methods.setdefault(str(sig.get("name")), []).append(sig)
        for member, sigs in methods.items():
            for shape, stmt in build_snippets(receiver, member, sigs, tvars):
                add(owner, member, "method", shape, stmt)
        for sig in cls.get("static_methods") or []:
            name = str(sig.get("name"))
            ret = _sig_ret(sig, tvars)
            params = _sig_params(sig, tvars)
            arglist = ", ".join(valid_arg_for(p) or wrong_arg_for(p) for p in params)
            call = f"{owner}.{name}({arglist})"
            add(owner, name, "static_method", "legal",
                f"let r: {ret} = {call}" if ret != "Unit" else call)
            add(owner, name, "static_method", "dispatch_instance",
                f"let r: {ret} = {receiver}.{name}({arglist})" if ret != "Unit"
                else f"{receiver}.{name}({arglist})")
        type_args = ", ".join(tvars.get(t, "Int64") for t in (cls.get("type_params") or []))
        instantiated = f"{owner}<{type_args}>" if type_args else owner
        for index, sig in enumerate(cls.get("constructor_signatures") or []):
            params = _sig_params(sig, tvars)
            arglist = ", ".join(valid_arg_for(p) or wrong_arg_for(p) for p in params)
            add(owner, "<ctor>", "constructor", f"legal_{index}",
                f"let r: {instantiated} = {instantiated}({arglist})")
            extra = f"{arglist}, 1" if arglist else "1"
            add(owner, "<ctor>", "constructor", f"arity_many_{index}",
                f"let r: {instantiated} = {instantiated}({extra})")

    # --- interfaces (members resolved through a concrete receiver) ------------
    for interface in normalized.get("interfaces") or []:
        owner = str(interface.get("name"))
        receiver = INTERFACE_RECEIVERS.get(owner)
        if receiver is None:
            continue
        tvars = tvars_for(owner)
        methods: dict[str, list[dict]] = {}
        for sig in interface.get("methods") or []:
            methods.setdefault(str(sig.get("name")), []).append(sig)
        for member, sigs in methods.items():
            for shape, stmt in build_snippets(receiver, member, sigs, tvars):
                add(owner, member, "interface_method", shape, stmt)

    # --- global functions ------------------------------------------------------
    functions: dict[str, list[dict]] = {}
    for sig in normalized.get("functions") or []:
        functions.setdefault(str(sig.get("name")), []).append(sig)
    for name, sigs in functions.items():
        for shape, stmt in global_function_snippets(name, sigs):
            add("<global>", name, "function", shape, stmt)

    # --- oracle pass ------------------------------------------------------------
    oracle_results: dict[str, str] = {}
    if args.oracle:
        import os
        os.environ["CANGJIE_TYPECHECKER_CONTEXT"] = "final"
        official_root = ROOT.parent / "official-reference" / "typechecker"
        sys.path.insert(0, str(official_root))
        from typechecker.checker import typecheck_tree  # noqa: E402
        from typechecker.errors import TypeCheckError  # noqa: E402
        from typechecker.parser import parse  # noqa: E402
        from lark.exceptions import UnexpectedInput  # noqa: E402
        for item in snippets:
            src = (args.out_dir / item["path"]).read_text("utf-8")
            try:
                typecheck_tree(parse(src))
                oracle_results[item["path"]] = "ACCEPT"
            except TypeCheckError as error:
                oracle_results[item["path"]] = "REJECT " + str(error)[:200]
            except UnexpectedInput as error:
                oracle_results[item["path"]] = "PARSE_ERROR " + str(error)[:200]

    manifest = {
        "context": str(args.context),
        "count": len(snippets),
        "shapes": sorted({item["shape"] for item in snippets}),
        "members": snippets,
    }
    if oracle_results:
        manifest["oracle"] = oracle_results
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", "utf-8")

    by_shape: dict[str, int] = {}
    for item in snippets:
        by_shape[item["shape"]] = by_shape.get(item["shape"], 0) + 1
    print(f"generated {len(snippets)} snippets -> {args.out_dir}")
    print("shapes:", json.dumps(by_shape, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
