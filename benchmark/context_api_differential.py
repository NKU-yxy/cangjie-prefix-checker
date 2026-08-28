#!/usr/bin/env python3
"""context-API semantic differential fuzzer (v2).

Generates Cangjie fragments that misuse the context.json API surface (wrong
argument types, wrong arity, Optional unwrapping, wrong named args, wrong index
types, field-as-method confusion), labels them with the vendored official
typechecker, computes the first non-continuable token index using error-position
rules calibrated on the official wrong/ dataset, then diffs against the full
protocol binary (./solution, default 0=OK/1=error convention).

Error-position rules (calibrated on wrong/ + err_* inference, see
docs/iteration_notes.md):

  kind              error token = token containing...
  arg_type          end boundary of the wrong-typed argument literal
  arity             the call's closing ')'
  opt_unwrap        the newline right after the statement (statement close)
  ret_type          the newline right after the statement
  named_arg         the label token itself
  index_type        the wrong-typed index literal itself
  field_as_method   the '(' right after the field name

Usage (inside the official judge container):

  python3 benchmark/context_api_differential.py \
    --solution /workspace/solution \
    --wrong-dir /ref/wrong --error-json /ref/wrong_error_positions.json \
    --failure-json /tmp/context_api_failures.json \
    --report-md /tmp/context_api_report.md

Exit code 0 even when divergences are found; the report carries findings.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "third_party" / "cangjie_typechecker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))


# ---------------------------------------------------------------------------
# Oracle (vendored official typechecker)
# ---------------------------------------------------------------------------

def _configure_oracle() -> None:
    from typechecker import builtin_context

    builtin_context._CONTEXT_PATH = ROOT / "context.json"
    if hasattr(builtin_context, "_builtin_ctx_singleton"):
        builtin_context._builtin_ctx_singleton = None
    if hasattr(builtin_context, "_raw_context"):
        builtin_context._raw_context.cache_clear()


def oracle_accepts(source: str) -> tuple[bool, str]:
    from typechecker.checker import typecheck_tree
    from typechecker.errors import TypeCheckError
    from typechecker.parser import (
        UnexpectedCharacters,
        UnexpectedEOF,
        UnexpectedToken,
        parse,
    )

    try:
        typecheck_tree(parse(source))
        return True, ""
    except TypeCheckError as error:
        return False, f"TypeCheckError: {error}"
    except (UnexpectedCharacters, UnexpectedEOF, UnexpectedToken) as error:
        return False, f"ParseError: {error}"


# ---------------------------------------------------------------------------
# Type utilities
# ---------------------------------------------------------------------------

TPARAM_DEFAULTS = {"T": "Int64", "K": "String", "V": "Int64", "U": "Int64"}

OK_LITERALS = {"Int64": "1", "Float64": "1.5", "Bool": "true", "String": "\"x\""}

WRONG_LITERALS = {"Int64": "\"bad\"", "Float64": "\"bad\"", "Bool": "1", "String": "1", "Rune": "1"}


def instantiate(t, tparams):
    """Type dict -> Cangjie source type string with tparams concretized."""
    if isinstance(t, str):
        return t
    if "tparam" in t:
        return tparams.get(t["tparam"], "Int64")
    if "nominal" in t:
        args = t.get("args") or []
        inner = ",".join(instantiate(a, tparams) for a in args)
        return f"{t['nominal']}{'<' + inner + '>' if inner else ''}"
    if "tuple" in t:
        return "(" + ",".join(instantiate(a, tparams) for a in t["tuple"]) + ")"
    if "fn" in t:
        params = t["fn"].get("params") or []
        ret = t["fn"].get("ret")
        return "(" + ",".join(instantiate(p, tparams) for p in params) + ") -> " + instantiate(ret, tparams)
    if "optional" in t:
        return "Optional<" + instantiate(t["optional"], tparams) + ">"
    if "array" in t:
        return "Array<" + instantiate(t["array"], tparams) + ">"
    if "unit" in t:
        return "Unit"
    return "Int64"


def is_optional(t) -> bool:
    return isinstance(t, dict) and "optional" in t


def ret_type_str(ret, tparams):
    if isinstance(ret, dict) and "unit" in ret:
        return "Unit"
    return instantiate(ret, tparams)


def ok_arg(t, tparams):
    tstr = instantiate(t, tparams)
    if tstr in OK_LITERALS:
        return OK_LITERALS[tstr]
    return None


def wrong_arg(t, tparams):
    tstr = instantiate(t, tparams)
    if tstr in WRONG_LITERALS:
        return WRONG_LITERALS[tstr]
    return None


# ---------------------------------------------------------------------------
# Scenario scaffolding
# ---------------------------------------------------------------------------

# class -> (receiver var, construction statement, concrete tparams)
SCENARIOS = {
    "Array": ("a", "let a: Array<Int64> = [1, 2, 3]", {"T": "Int64"}),
    "ArrayList": ("a", "let a: ArrayList<Int64> = ArrayList<Int64>([1, 2])", {"T": "Int64"}),
    "HashMap": ("m", "let m: HashMap<String, Int64> = HashMap<String, Int64>()", {"K": "String", "V": "Int64"}),
    "HashSet": ("hs", "let hs: HashSet<Int64> = HashSet<Int64>()", {"T": "Int64"}),
    "String": ("str", "let str: String = \"hello\"", {}),
    "ArrayStack": ("st", "let st: ArrayStack<Int64> = ArrayStack<Int64>()", {"T": "Int64"}),
    "ArrayDeque": ("d", "let d: ArrayDeque<Int64> = ArrayDeque<Int64>()", {"T": "Int64"}),
    "Range": ("r", "let r: Range<Int64> = 0..5", {"T": "Int64"}),
}

HELPER_PREFIX = """
func padAlpha(): Int64 {
    1
}

func padBeta(n: Int64): Int64 {
    n + padAlpha()
}

func padGamma(s: String): String {
    s
}
"""


def make_call(receiver, method_name, overload, tparams, drop_last=0, extra_arg=None, label_first=None):
    """Build `receiver.method(...)` from an overload dict.

    Returns None if a valid literal cannot be produced for some parameter
    (no "1"-fallback: that would silently turn the case into a different
    error kind and corrupt the ground truth).
    """
    params = overload.get("params") or []
    if drop_last > len(params):
        return None
    arg_list = []
    for i, p in enumerate(params[: len(params) - drop_last]):
        lit = ok_arg(p["type"], tparams)
        if lit is None:
            return None
        if label_first is not None and i == 0:
            arg_list.append(f"{label_first}: {lit}")
            continue
        arg_list.append(lit)
        if extra_arg is not None and i == len(params) - 1:
            arg_list.append(extra_arg)
    return f"{receiver}.{method_name}({', '.join(arg_list)})"


OPTIONAL_ONLY_METHODS = ["isSome", "isNone", "getOrThrow"]


def nth_top_level_comma(s, start, n):
    """Char offset of the n-th (1-based) top-level comma after `start`.
    Returns the comma's index in s. The comma itself is the error char."""
    paren = bracket = brace = angle = 0
    in_string = False
    escaped = False
    count = 0
    for i in range(start, len(s)):
        ch = s[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '(':
            paren += 1
        elif ch == ')':
            paren -= 1
        elif ch == '[':
            bracket += 1
        elif ch == ']':
            bracket -= 1
        elif ch == '{':
            brace += 1
        elif ch == '}':
            brace -= 1
        elif ch == '<':
            angle += 1
        elif ch == '>' and angle > 0:
            angle -= 1
        elif ch == ',' and paren == 0 and bracket == 0 and brace == 0 and angle == 0:
            count += 1
            if count == n:
                return i
    return -1


def longest_member_prefix(member, valid_names):
    """Length of the longest character prefix of `member` that is also a
    prefix of some valid member name of the receiver class. 0 means the
    member shares no leading characters with any valid member."""
    best = 0
    for name in valid_names or ():
        i = 0
        while i < len(member) and i < len(name) and member[i] == name[i]:
            i += 1
        if i > best:
            best = i
    return best


def build_bad_stmt(class_name, method_name, overload, kind, tparams, receiver,
                   extra_member_names=None, valid_member_names=None):
    params = overload.get("params") or []
    ret = overload.get("ret")

    if kind == "arg_type" and params:
        # wrong-type literal at first parameter position
        lit = wrong_arg(params[0]["type"], tparams)
        if lit is None:
            return None
        first_ok = ok_arg(params[0]["type"], tparams)
        if first_ok is None:
            return None
        call = make_call(receiver, method_name, overload, tparams)
        if call is None:
            return None
        call = call.replace(f"({first_ok}", f"({lit}", 1)
        bad = call
        # CALIBRATED: official first-error is the token at the literal's END
        # BOUNDARY (the ',' or ')' after it). Verified against
        # err_arraylist_add_type (`a.add("x")` -> `")\n` token) and
        # err_string_contains_arg (`s.contains(1)` -> `)\n` token, because
        # `s.contains(1` can still continue with `.toString())` into a valid
        # program). So the char pos is the first char AFTER the literal, not
        # its last char.
        err_pos = bad.find(lit) + len(lit)
        return bad, f"{class_name}.{method_name} arg_type", err_pos

    if kind == "arity_short" and len(params) >= 1:
        call = make_call(receiver, method_name, overload, tparams, drop_last=1)
        err_pos = call.rfind(")")
        return call, f"{class_name}.{method_name} arity_short", err_pos

    if kind == "arity_long":
        if not params:
            # zero-param method called with one argument
            call = f"{receiver}.{method_name}(1)"
        else:
            call = make_call(receiver, method_name, overload, tparams, extra_arg="1")
            if call is None:
                return None
        # CALIBRATED: with too many arguments the comma AFTER the last legal
        # argument is already non-continuable (`f(1, 2,` can never become a
        # valid program once the arg count exceeds the max), so the official
        # first-error is that comma, not the closing paren. For a zero-param
        # method called with one argument, the first arg itself (`f(1`) is
        # non-continuable.
        n = len(params)
        arg_open = call.find("(")
        if n == 0:
            err_pos = arg_open + 1
        else:
            # start AFTER the '(' so the opening paren isn't counted in depth
            err_pos = nth_top_level_comma(call, arg_open + 1, n)
            if err_pos < 0:
                err_pos = call.rfind(")")
        return call, f"{class_name}.{method_name} arity_long", err_pos

    if kind == "opt_unwrap" and is_optional(ret):
        inner = ret["optional"]
        tstr = instantiate(inner, tparams)
        if tstr not in ("Int64", "String", "Bool", "Float64", "Rune"):
            return None
        call = make_call(receiver, method_name, overload, tparams)
        if call is None:
            return None
        bad = f"let z: {tstr} = {call}"
        # CALIBRATED (2026-08-17): the RHS call can continue with .getOrThrow()
        # etc. on the next line, so the newline is still continuable; the first
        # non-continuable token is the next statement's first token (or the
        # closing '}' when the bad statement is the last one).
        err_pos = len(bad) + 1  # char pos of '}' after "bad_stmt\n}"
        return bad, f"{class_name}.{method_name} opt_unwrap", err_pos

    if kind == "ret_type" and not is_optional(ret) and not (isinstance(ret, dict) and "unit" in ret):
        tstr = ret_type_str(ret, tparams)
        wrong_t = {"Int64": "String", "String": "Int64", "Bool": "Int64", "Float64": "String"}.get(tstr)
        if wrong_t is None:
            return None
        call = make_call(receiver, method_name, overload, tparams)
        if call is None:
            return None
        bad = f"let z: {wrong_t} = {call}"
        # CALIBRATED: same as opt_unwrap — newline continuable (e.g. .toString()),
        # first non-continuable token is the next statement's first token.
        err_pos = len(bad) + 1  # char pos of '}' after "bad_stmt\n}"
        return bad, f"{class_name}.{method_name} ret_type", err_pos

    if kind == "named_arg" and params:
        call = make_call(receiver, method_name, overload, tparams, label_first="zz")
        if call is None:
            return None
        err_pos = call.find("zz")
        return call, f"{class_name}.{method_name} named_arg", err_pos

    if kind == "index_type" and class_name == "Array":
        bad = f"let z: Int64 = {receiver}[true]"
        err_pos = bad.find("true")
        return bad, f"{class_name}.{method_name} index_type", err_pos

    if kind == "field_as_method":
        bad = f"let z: Int64 = {receiver}.size()"
        err_pos = bad.find("(")
        return bad, f"{class_name}.{method_name} field_as_method", err_pos

    if kind in ("missing_member", "opt_method_on_plain"):
        # call a method that does not exist on this receiver
        member = None
        if kind == "opt_method_on_plain":
            member = "isSome"  # Optional-only method on a plain container
            call = f"{receiver}.{member}()"
        else:
            if not extra_member_names:
                return None
            member = extra_member_names[0]
            call = make_call(receiver, member, overload, tparams)
            if call is None:
                return None
        bad = f"let z: Int64 = {call}"
        # CALIBRATED: the official first-non-continuable position is
        # character-based, not token-based. Any character prefix of the
        # member name that is itself a prefix of a REAL member name can be
        # extended to a valid program (e.g. `a.is` + `Empty()` =
        # `a.isEmpty()`, which tokenizes fine), so the error lands just past
        # the longest shared character prefix with a valid member name.
        # The token containing that character is the first-non-continuable
        # token (BPE boundaries like `.is`+`Some` are irrelevant).
        err_pos = bad.find(member) + longest_member_prefix(member, valid_member_names)
        return bad, f"{class_name}.{method_name} {kind}", err_pos

    if kind == "ctor_arg":
        # wrong-typed literal at the first constructor parameter
        lit = wrong_arg(params[0]["type"], tparams) if params else None
        if lit is None:
            return None
        first_ok = ok_arg(params[0]["type"], tparams)
        if first_ok is None:
            return None
        type_args = f"<{', '.join(tparams.values())}>" if tparams else ""
        call = f"{class_name}{type_args}("
        for i, p in enumerate(params):
            if i == 0:
                call += lit
            else:
                call += ok_arg(p["type"], tparams)
            if i < len(params) - 1:
                call += ", "
        call += ")"
        bad = f"let z: {class_name}{type_args} = {call}"
        # scan inside the call's parens only — `find(lit)` on the whole line
        # would hit e.g. the "1" inside `Int64` in the type annotation; the
        # official first-error is the literal's end boundary (see arg_type)
        lit_start = call.index(lit, call.find("("))
        err_pos = bad.find(call) + lit_start + len(lit)
        return bad, f"{class_name}.{method_name} ctor_arg", err_pos

    if kind == "reassign_type":
        # `v = <call>` where the call returns the wrong type for v.
        # `v` (String) is the variable declared in the padding, so the
        # assignment is a genuine type mismatch, not an undeclared variable.
        call = make_call(receiver, method_name, overload, tparams)
        if call is None:
            return None
        bad = f"v = {call}"
        # CALIBRATED: same as ret_type — newline continuable, error at the
        # next statement's first token.
        err_pos = len(bad) + 1
        return bad, f"{class_name}.{method_name} reassign_type", err_pos

    return None


# ---------------------------------------------------------------------------
# Global-function kinds (min/max/clamp/abs/println family)
# ---------------------------------------------------------------------------

GLOBAL_TPARAMS = {"T": "Int64"}

# Oracle probe for the continuation method that can rescue a wrong-typed
# literal: `min(1, "bad", [1, 2])` is still continuable at the string's end
# boundary because `"bad".toInt64()` turns the argument valid; if no such
# method exists, the literal's first char is already non-continuable.
FIXUP_PROBES = {
    ('"bad"', "Int64"): ".toInt64()",
    ('"bad"', "Float64"): ".toFloat64()",
    ("1", "Float64"): ".toFloat64()",
    ("1", "String"): ".toString()",
    ('"x"', "Int64"): ".toInt64()",
    ('"x"', "Float64"): ".toFloat64()",
    ('"x"', "String"): ".toString()",
}
_fixable_cache = {}


def lit_fixable(lit, target_type):
    key = (lit, target_type)
    if key in _fixable_cache:
        return _fixable_cache[key]
    suffix = FIXUP_PROBES.get(key)
    ok = False
    if suffix:
        probe = f'main(): Unit {{\n    let z: {target_type} = {lit}{suffix}\n}}'
        ok, _ = oracle_accepts(probe)
    _fixable_cache[key] = ok
    return ok


def global_ok_arg(t):
    tstr = instantiate(t, GLOBAL_TPARAMS)
    if tstr in OK_LITERALS:
        return OK_LITERALS[tstr]
    if tstr.startswith("Array<"):
        return "[1, 2]"
    return None


def global_call(name, overload, idx=None, lit=None, drop_last=0, extra_arg=None):
    """Build `name(arg, ...)` with param idx replaced by lit (or the last
    `drop_last` params dropped, or `extra_arg` appended)."""
    params = overload.get("params") or []
    args = []
    for i, p in enumerate(params[: len(params) - drop_last]):
        if i == idx and lit is not None:
            args.append(lit)
        else:
            ok = global_ok_arg(p["type"])
            if ok is None:
                return None
            args.append(ok)
    if extra_arg is not None:
        args.append(extra_arg)
    return f"{name}({', '.join(args)})"


def build_bad_global(name, overload, kind, all_ovs=None):
    """Generate a bad variant of a global-function call.

    Ground truth (CALIBRATED against the official continuation model):
    - the comma after a wrong literal LOCKS it (`min(1, "bad", ...)` can
      only be rescued by appending `.toInt64()` BEFORE the comma), so the
      first non-continuable char is the literal's end boundary when a
      fixup method exists, else the literal's first char;
    - a wrong literal in the LAST position (`abs("bad")`) is rescued by
      appending the fixup before the closing paren, so the end boundary
      is the paren itself;
    - arity_long: comma after the last legal argument;
    - arity_short: the closing paren.
    """
    params = overload.get("params") or []
    ret = overload.get("ret")

    if kind == "g_arg" and params:
        generic = bool(overload.get("type_params"))
        for idx in (0, 1):
            if idx >= len(params):
                break
            tstr = instantiate(params[idx]["type"], GLOBAL_TPARAMS)
            lit = WRONG_LITERALS.get(tstr)
            if lit is None:
                continue
            call = global_call(name, overload, idx, lit)
            if call is None:
                continue
            if generic:
                # implicit-generic (min/max): every call fails candidate
                # matching at the closing paren (official: T never binds)
                err_pos = call.rfind(")")
            elif idx == len(params) - 1:
                # trailing arg: checked when it closes at ')'
                err_pos = call.rfind(")")
            else:
                # non-trailing arg: checked when it closes at the comma
                # literal ends at the comma that locks it; do NOT push
                # past it (the char after the literal is the comma itself)
                err_pos = call.find(lit) + len(lit)
            return call, f"{name} g_arg", err_pos
        return None

    if kind == "g_arg_mixed" and params:
        generic = bool(overload.get("type_params"))
        # a VALID literal of the wrong type (numeric-family mixups)
        # NOTE: no Float64 -> "1" entry: Int64 literals convert to Float64
        # implicitly, so `abs(1)` matches abs(Int64) and only fails as the
        # trailing expression of a Unit function (a different error kind).
        mixed = {"Int64": ('"x"', "String"), "String": ("1", "Int64")}
        for idx in (0, 1, 2):
            if idx >= len(params):
                break
            tstr = instantiate(params[idx]["type"], GLOBAL_TPARAMS)
            pair = mixed.get(tstr)
            if pair is None:
                continue
            lit, lit_t = pair
            call = global_call(name, overload, idx, lit)
            if call is None:
                continue
            if generic:
                err_pos = call.rfind(")")
            elif idx == len(params) - 1:
                err_pos = call.rfind(")")
            else:
                err_pos = call.find(lit) + len(lit)
            return call, f"{name} g_arg_mixed", err_pos
        return None

    if kind == "g_rest_elem" and params:
        generic = bool(overload.get("type_params"))
        last = params[-1]
        if instantiate(last["type"], GLOBAL_TPARAMS).startswith("Array<"):
            call = global_call(name, overload, len(params) - 1, '["x"]')
            if call is None:
                return None
            if generic:
                err_pos = call.rfind(")")
            else:
                err_pos = call.find('["x"]') + 4  # after the closing quote of "x"
            return call, f"{name} g_rest_elem", err_pos
        return None

    if kind == "g_arity_short" and params:
        generic = bool(overload.get("type_params"))
        call = global_call(name, overload, drop_last=1)
        if call is None:
            return None
        if generic:
            # min(1, 1) is 2 args < 3 required: candidate fails at ')'
            err_pos = call.rfind(")")
        else:
            err_pos = call.rfind(")")
        return call, f"{name} g_arity_short", err_pos

    if kind == "g_arity_long" and params:
        generic = bool(overload.get("type_params"))
        call = global_call(name, overload, extra_arg="1")
        if call is None:
            return None
        if generic:
            err_pos = call.rfind(")")
        else:
            # A longer overload (e.g. print(s: String, flush: Bool)) can
            # hold the extra argument ONLY if its first param accepts our
            # arg0 (print("x", 1) -> ')' where the 2-param candidate is
            # checked; print(1, 1) -> the comma: arg0 is already wrong for
            # every longer candidate).  Otherwise the extra arg is
            # over-arity and locks at the comma after the last legal arg.
            arg0 = call[call.find("(") + 1:].split(",")[0].strip()
            longer = any(
                len(o.get("params") or []) > len(params) and
                global_ok_arg((o.get("params") or [])[0]["type"]) == arg0
                for o in (all_ovs or [])
            )
            if longer:
                err_pos = call.rfind(")")
            else:
                # comma after the last legal argument locks the arg list
                err_pos = nth_top_level_comma(call, call.find("(") + 1, len(params))
                if err_pos < 0:
                    err_pos = call.rfind(")")
        return call, f"{name} g_arity_long", err_pos

    if kind == "g_ret":
        tstr = ret_type_str(ret, GLOBAL_TPARAMS)
        if tstr == "Unit":
            return None
        wrong_t = {"Int64": "String", "String": "Int64",
                   "Bool": "Int64", "Float64": "String"}.get(tstr)
        if wrong_t is None:
            return None
        call = global_call(name, overload)
        if call is None:
            return None
        bad = f"let z: {wrong_t} = {call}"
        if overload.get("type_params"):
            # implicit-generic: candidate fails at the call's closing paren
            err_pos = bad.rfind(")")
        else:
            # same as ret_type: newline continuable, error at next statement
            err_pos = len(bad) + 1
        return bad, f"{name} g_ret", err_pos

    return None


def load_context():
    return json.loads((ROOT / "context.json").read_text())


def as_overloads(value):
    """instance_methods values are a list of overloads for some methods,
    a single overload dict for others; normalize to a list."""
    if isinstance(value, list):
        return value
    return [value]


# ---------------------------------------------------------------------------
# Token ground truth
# ---------------------------------------------------------------------------

def token_index_of_char(text, token_ids, char_pos, enc):
    """0-based token index of the token containing char position char_pos.

    Python tiktoken lacks encode_with_offsets; decode tokens one by one and
    accumulate character offsets instead.
    """
    acc = 0
    for idx, tok in enumerate(token_ids):
        acc += len(enc.decode_single_token_bytes(tok).decode("utf-8", "replace"))
        if acc > char_pos:
            return idx
    return len(token_ids) - 1


# ---------------------------------------------------------------------------
# Protocol runner
# ---------------------------------------------------------------------------

def run_solution(solution: Path, token_ids, timeout_s=10.0):
    proc = subprocess.run(
        [str(solution)],
        input="".join(f"{t}\n" for t in token_ids),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        check=False,
    )
    lines = [ln.strip() for ln in proc.stdout.splitlines()]
    first_err = next((i for i, ln in enumerate(lines) if ln == "1"), None)
    return proc.returncode, first_err, len(lines), proc.stderr[:300]


# ---------------------------------------------------------------------------
# Validation against official ground truth
# ---------------------------------------------------------------------------

def validate_wrong(wrong_dir: Path, error_json: Path, solution: Path, enc):
    """Run solution on official wrong/ cases, compare first-error index."""
    data = json.loads(error_json.read_text())
    checked = matched = 0
    mismatches = []
    for item in data["wrong_examples"]:
        name = item["name"]
        cj = wrong_dir / f"{name}.cj"
        if not cj.is_file():
            continue
        source = cj.read_text()
        token_ids = enc.encode(source)
        expected = item["first_error_token_index"]
        if expected >= len(token_ids):
            mismatches.append(f"{name}: expected index {expected} out of range ({len(token_ids)} tokens)")
            continue
        rc, first_err, n_lines, err = run_solution(solution, token_ids)
        checked += 1
        if first_err is None:
            mismatches.append(f"{name}: solution reported NO error (expected {expected})")
        elif first_err != expected:
            mismatches.append(f"{name}: solution={first_err} expected={expected}")
        else:
            matched += 1
    return checked, matched, mismatches


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260817)
    parser.add_argument("--solution", type=Path, required=True)
    parser.add_argument("--wrong-dir", type=Path)
    parser.add_argument("--error-json", type=Path)
    parser.add_argument("--failure-json", type=Path)
    parser.add_argument("--report-md", type=Path)
    parser.add_argument("--max-cases", type=int, default=100000)
    args = parser.parse_args()

    _configure_oracle()
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    ctx = load_context()

    validation = {"checked": 0, "matched": 0, "mismatches": []}
    if args.wrong_dir and args.error_json:
        checked, matched, mismatches = validate_wrong(args.wrong_dir, args.error_json, args.solution, enc)
        validation = {"checked": checked, "matched": matched, "mismatches": mismatches}

    # ---- generate + run cases ----
    kinds = ["arg_type", "arity_short", "arity_long", "opt_unwrap", "ret_type",
             "named_arg", "index_type", "field_as_method",
             "missing_member", "opt_method_on_plain", "ctor_arg", "reassign_type"]
    generated = 0
    divergences = []
    padding_cache = {}

    # cross-class zero-param method names for missing-member cases
    foreign_members = {}
    for class_name in SCENARIOS:
        cls = ctx["nominals"].get(class_name)
        if not cls:
            continue
        own = set(cls.get("instance_methods", {}).keys()) | set(cls.get("instance_fields", {}).keys())
        foreign = []
        for other_name in SCENARIOS:
            if other_name == class_name:
                continue
            other = ctx["nominals"].get(other_name)
            if not other:
                continue
            for mname, overloads in other.get("instance_methods", {}).items():
                ov_list = as_overloads(overloads)
                if mname in own or not ov_list:
                    continue
                if not ov_list[0].get("params"):
                    foreign.append(mname)
                if len(foreign) >= 3:
                    break
            if len(foreign) >= 3:
                break
        foreign_members[class_name] = foreign

    for class_name, (receiver, construction, tparams) in SCENARIOS.items():
        cls = ctx["nominals"].get(class_name)
        if not cls:
            continue
        methods = cls.get("instance_methods", {})
        size_is_field = "size" in cls.get("instance_fields", {}) and "size" not in methods
        # per-class valid padding (construction + a couple of valid calls)
        if class_name not in padding_cache:
            pad_calls = []
            for mname, overloads in methods.items():
                ov_list = as_overloads(overloads)
                if not ov_list:
                    continue
                ov = ov_list[0]
                if ov.get("params"):
                    call = make_call(receiver, mname, ov, tparams)
                    if call:
                        pad_calls.append(f"    {call}")
                if len(pad_calls) >= 2:
                    break
            # NOTE: official cases declare the entry point as `main(): Unit`
            # WITHOUT the `func` keyword; `func main` is rejected by the
            # official semantic rules (solution flags it at `():`).
            pad_only = (
                HELPER_PREFIX
                + f"\nmain(): Unit {{\n    {construction}\n    var v: String = \"x\"\n"
                + "\n".join(pad_calls)
                + "\n    println(padGamma(\"ok\"))\n}\n"
            )
            ok, _ = oracle_accepts(pad_only)
            if not ok:
                # class idiom unsupported; skip entirely
                continue
            padding_cache[class_name] = pad_only

        pad_only = padding_cache[class_name]

        for method_name, overloads in methods.items():
            ov_list = as_overloads(overloads)
            if not ov_list:
                continue
            for ov_idx, ov in enumerate(ov_list[:2]):
                for kind in kinds:
                    # kind applicability
                    if kind == "field_as_method" and not size_is_field:
                        continue
                    if kind == "index_type" and class_name != "Array":
                        continue
                    if kind == "missing_member" and not foreign_members.get(class_name):
                        continue
                    extra = foreign_members.get(class_name) if kind == "missing_member" else None
                    valid_names = set(methods.keys()) | set(cls.get("instance_fields", {}).keys())
                    built = build_bad_stmt(class_name, method_name, ov, kind, tparams,
                                           receiver, extra, valid_names)
                    if built is None:
                        continue
                    bad_stmt, desc, err_pos_local = built
                    full = pad_only[: pad_only.rfind("    println")] + f"    {bad_stmt}\n}}\n"
                    # oracle filter: whole program must be invalid
                    ok, msg = oracle_accepts(full)
                    if ok:
                        continue
                    token_ids = enc.encode(full)
                    err_pos_global = full.rfind(f"    {bad_stmt}") + 4 + err_pos_local
                    gt = token_index_of_char(full, token_ids, err_pos_global, enc)
                    if gt >= len(token_ids):
                        continue
                    rc, sol_err, n_lines, stderr = run_solution(args.solution, token_ids)
                    generated += 1
                    if sol_err != gt:
                        divergences.append({
                            "class": class_name,
                            "method": method_name,
                            "overload": ov_idx,
                            "kind": kind,
                            "desc": desc,
                            "gt": gt,
                            "solution": sol_err,
                            "n_lines": n_lines,
                            "oracle": msg[:160],
                            "source": full,
                        })
                        if len(divergences) >= args.max_cases:
                            break
                if len(divergences) >= args.max_cases:
                    break
            if len(divergences) >= args.max_cases:
                break
        if len(divergences) >= args.max_cases:
            break

    # ---- global-function family (min/max/clamp/abs/println/print) ----
    gkinds = ["g_arg", "g_arg_mixed", "g_rest_elem", "g_arity_short",
              "g_arity_long", "g_ret"]
    global_pad = (
        HELPER_PREFIX
        + '\nmain(): Unit {\n    var v: String = "x"\n'
        + '    let xi: Int64 = 1\n    let xf: Float64 = 1.5\n'
        + '    let xb: Bool = true\n'
        + '    println(padGamma("ok"))\n}\n'
    )
    for gname, govs in ctx.get("global_functions", {}).items():
        g_ovs = as_overloads(govs)
        for ov_idx, ov in enumerate(g_ovs[:6]):
            for kind in gkinds:
                built = build_bad_global(gname, ov, kind, g_ovs)
                if built is None:
                    continue
                bad_stmt, desc, err_pos_local = built
                full = global_pad[: global_pad.rfind("    println")] + f"    {bad_stmt}\n}}\n"
                ok, msg = oracle_accepts(full)
                if ok:
                    continue
                token_ids = enc.encode(full)
                err_pos_global = full.rfind(f"    {bad_stmt}") + 4 + err_pos_local
                gt = token_index_of_char(full, token_ids, err_pos_global, enc)
                if gt >= len(token_ids):
                    continue
                rc, sol_err, n_lines, stderr = run_solution(args.solution, token_ids)
                generated += 1
                if sol_err != gt:
                    divergences.append({
                        "class": "global",
                        "method": gname,
                        "overload": ov_idx,
                        "kind": kind,
                        "desc": desc,
                        "gt": gt,
                        "solution": sol_err,
                        "n_lines": n_lines,
                        "oracle": msg[:160],
                        "source": full,
                    })
                    if len(divergences) >= args.max_cases:
                        break
            if len(divergences) >= args.max_cases:
                break
        if len(divergences) >= args.max_cases:
            break

    report = {
        "validation": validation,
        "generated": generated,
        "divergence_count": len(divergences),
        "divergences": divergences[:200],
    }
    if args.failure_json:
        args.failure_json.parent.mkdir(parents=True, exist_ok=True)
        args.failure_json.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    if args.report_md:
        md = [
            "# context-API 差分 fuzz 报告",
            "",
            f"- 生成用例：{generated}",
            f"- 偏差数：{len(divergences)}",
            f"- 规则校验（官方 wrong/ 首错误索引）：{validation['matched']}/{validation['checked']}",
            "",
            "## 偏差统计",
        ]
        counts = Counter((d["class"], d["kind"]) for d in divergences)
        for (cls_, kind), n in counts.most_common():
            md.append(f"- `{cls_}` / `{kind}`: {n}")
        md += ["", "## 前 60 条偏差明细"]
        for d in divergences[:60]:
            md.append(
                f"- {d['desc']}: gt={d['gt']} solution={d['solution']} "
                f"(oracle: {d['oracle']})"
            )
        args.report_md.parent.mkdir(parents=True, exist_ok=True)
        args.report_md.write_text("\n".join(md))

    print(json.dumps({
        "generated": generated,
        "divergences": len(divergences),
        "validation": f"{validation['matched']}/{validation['checked']}",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
