#!/usr/bin/env python3
"""Statement-level semantic differential fuzzer (v8).

Covers categories the context-API fuzzer does not generate: wrong-typed
VARIABLES as operands/arguments, arithmetic/relational/equality/logical
operators, if/while/for conditions, indexing, constructor calls, and
assignment type mismatches — all with official-anchored ground-truth rules
calibrated on wrong/ + wrong2/ (100 official cases, exact token positions).

Anchor rules (extracted from wrong_error_positions.json + wrong2_error_positions.json):

  kind            error token = token containing...
  arith_var       the first wrong operand token (err_arith_non_numeric: `true`)
  mod_float       the '%' operator (err_mod_non_int64: `%`)
  unary           the operand token (err_unary_minus_non_numeric / err_unary_not_non_bool)
  logical         the first non-bool operand (err_logical_non_bool: `println` at stmt close — see below)
  cond            the ')' closing the condition (err_if_not_bool / err_while_not_bool: `)`)
  for_iter        the iterable expression token (err_for_not_iterable: `n`)
  index           the bad index literal itself if unfixable, else its end boundary
  arg_var         wrong-typed variable: its end boundary (fixable) or itself (unfixable)
  assign          the statement boundary '\n' (err_arraylist_toarray_assign / err_arith_mixed_family)
  ctor_arg        the argument's end boundary (err_ctor_call_mismatch: `")\n`)
  eq_incomp       the RHS literal's end boundary (err_eq_incomparable: `"\n`)
  rel_unordered   the '<' '>' operator (err_rel_unordered: ` <`)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "third_party" / "cangjie_typechecker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))


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
# Scaffolding
# ---------------------------------------------------------------------------

# One valid main body with declared variables of each type, plus optional
# container construction. The bad statement replaces the trailing println.
VAR_PAD = """func padAlpha(): Int64 {
    1
}

func padBeta(n: Int64): Int64 {
    n + padAlpha()
}

func padGamma(s: String): String {
    s
}

func mkStr(): String {
    "hello"
}

func mkInt(): Int64 {
    42
}

func mkFloat(): Float64 {
    3.5
}

func mkBool(): Bool {
    true
}

func takesStr(s: String): Unit {
    println(s)
}

func takesInt(n: Int64): Int64 {
    n
}

func takesLambda(f: (Int64) -> Int64): Int64 {
    f(1)
}

main(): Unit {
    var v: String = "x"
    let n: Int64 = 1
    let f: Float64 = 1.5
    let b: Bool = true
    let s: String = "abc"
    let arr: Array<Int64> = [1, 2, 3]
    let m: HashMap<String, Int64> = HashMap<String, Int64>()
    let st: ArrayStack<Int64> = ArrayStack<Int64>()
    let d: ArrayDeque<Int64> = ArrayDeque<Int64>()
    let al: ArrayList<Int64> = ArrayList<Int64>([1, 2])
    println(padGamma("ok"))
}
"""


def main_body() -> str:
    # body of main() (declarations + final println line)
    inner = VAR_PAD[VAR_PAD.index("main(): Unit {") + len("main(): Unit {"):]
    inner = inner[: inner.rindex("}")]
    return inner


BAD_TEMPLATE = VAR_PAD[: VAR_PAD.rindex("    println(padGamma(\"ok\"))")] + "{bad_stmt}\n}\n"


def case(source: str, kind: str, desc: str, err_pos: int, oracle_msg: str = ""):
    return {"source": source, "kind": kind, "desc": desc, "err_pos": err_pos, "oracle": oracle_msg}


# ---------------------------------------------------------------------------
# Case builders. Each returns (bad_stmt, kind, desc, char_pos_of_error) or None.
# ---------------------------------------------------------------------------

def arith_var_cases():
    out = []
    for lit, tname in [("true", "Bool"), ('"abc"', "String")]:
        bad = f"let z: Int64 = {lit} + 1"
        out.append((bad, "arith_var", f"{tname} + Int64", bad.find(lit)))
    # variable operand (unfixable types anchor at the variable token itself)
    bad = "let z: Int64 = b + 1"
    out.append((bad, "arith_var", "Bool var + Int64", bad.find("b")))
    bad = "let z: Int64 = s + 1"
    out.append((bad, "arith_var", "String var + Int64", bad.find("s")))
    # valid mixed numeric arith assigned to Int64 -> anchor at stmt boundary
    bad = "let z: Int64 = f + 1"
    out.append((bad, "assign_boundary", "Float64 + Int64 -> Int64", len(bad) + 1))
    return out


def mod_cases():
    out = []
    bad = "let z: Int64 = 1.0 % 2"
    out.append((bad, "mod_float", "Float64 % Int64", bad.find("%")))
    bad = "let z: Int64 = 1 % 2.0"
    out.append((bad, "mod_float", "Int64 % Float64", bad.find("%")))
    bad = "let z: Int64 = n % s"
    out.append((bad, "mod_float", "Int64 % String", bad.find("%")))
    bad = "let z: Int64 = 1.5 % 2"
    out.append((bad, "mod_float", "literal Float64 %", bad.find("%")))
    return out


def unary_cases():
    out = []
    bad = "let z: Int64 = -s"
    out.append((bad, "unary", "unary - on String var", bad.find("s")))
    bad = "let z: Int64 = -true"
    out.append((bad, "unary", "unary - on Bool literal", bad.find("true")))
    bad = "let z: Bool = !n"
    out.append((bad, "unary", "unary ! on Int64 var", bad.find("n")))
    bad = "let z: Bool = !1"
    out.append((bad, "unary", "unary ! on Int64 literal", bad.find("1")))
    return out


def logical_cases():
    out = []
    # `n && b` — first operand wrong; official anchors at the operand? err_logical_non_bool
    # anchors at the NEXT statement (statement-boundary deferral). Use boundary rule.
    bad = "let z: Bool = n && b"
    out.append((bad, "assign_boundary", "Int64 && Bool", len(bad) + 1))
    bad = "let z: Bool = b && 1"
    out.append((bad, "assign_boundary", "Bool && Int64", len(bad) + 1))
    return out


def cond_cases():
    out = []
    for bad in ["if (n) {\n        println(1)\n    }", "if (s) {\n        println(1)\n    }",
                "if (1) {\n        println(1)\n    }", 'if ("x") {\n        println(1)\n    }',
                "while (n) {\n        println(1)\n    }", "while (1) {\n        println(1)\n    }",
                "while (s) {\n        println(1)\n    }", "if (mkInt()) {\n        println(1)\n    }",
                "if (mkStr()) {\n        println(1)\n    }"]:
        # find the ')' closing the condition (first ')' that brings depth to 0)
        depth = 0
        close_paren = -1
        for i in range(len(bad)):
            if bad[i] == "(":
                depth += 1
            elif bad[i] == ")":
                depth -= 1
                if depth == 0:
                    close_paren = i
                    break
        out.append((bad, "cond", bad[: bad.find("(") + 1] + "…)", close_paren))
    return out


def for_iter_cases():
    out = []
    for bad, tname in [("for (i in n) {\n        println(1)\n    }", "Int64 var"),
                       ("for (i in 1) {\n        println(1)\n    }", "Int64 literal"),
                       ("for (i in s) {\n        println(1)\n    }", "String var"),
                       ("for (i in true) {\n        println(1)\n    }", "Bool literal"),
                       ("for (i in 1.5) {\n        println(1)\n    }", "Float64 literal")]:
        # iterable expression starts right after "in "
        pos = bad.find("in ") + 3
        out.append((bad, "for_iter", f"for over {tname}", pos))
    return out


def index_cases():
    out = []
    # Array[true] — Bool unfixable -> anchor at literal itself (official)
    bad = "let z: Int64 = arr[true]"
    out.append((bad, "index", "arr[Bool]", bad.find("true")))
    # Array[s] — s: String fixable by .toInt64() -> end boundary of s
    bad = "let z: Int64 = arr[s]"
    out.append((bad, "index", "arr[String var]", bad.find("s") + 1))
    # Array[1.5] — Float64 literal fixable by .toInt64()? -> boundary
    bad = "let z: Int64 = arr[1.5]"
    out.append((bad, "index", "arr[Float64 literal]", bad.find("1.5") + 3))
    # HashMap<String,Int64>[1] — wrong key type Int64, fixable by 1.toString()
    # -> anchor at the literal's end boundary
    bad = "let z: Int64 = m[1]"
    out.append((bad, "index", "map[Int64] vs String key", bad.find("1") + 1))
    # HashMap<String,Int64>[s] — valid
    # index non-array: String[s]? String supports [] with Int64; use Float64
    bad = "let z: Rune = s[1.5]"
    out.append((bad, "index", "str[Float64]", bad.find("1.5")))
    return out


def arg_var_cases():
    out = []
    # method arg with wrong-typed VARIABLE; s: String fixable -> end boundary
    bad = "al.add(s)"
    out.append((bad, "arg_var", "ArrayList.add(String var)", bad.find("s") + 1))
    bad = "arr.fill(s)"
    out.append((bad, "arg_var", "Array.fill(String var)", bad.find("s") + 1))
    bad = "st.push(s)"
    out.append((bad, "arg_var", "ArrayStack.push(String var)", bad.find("s") + 1))
    bad = "d.addLast(s)"
    out.append((bad, "arg_var", "ArrayDeque.addLast(String var)", bad.find("s") + 1))
    bad = "m.put(1, 1)"
    out.append((bad, "arg_var", "HashMap.put(Int64 key)", bad.find("1")))
    bad = "m.put(s, s)"
    out.append((bad, "arg_var", "HashMap.put(String value)", bad.find("s", bad.find(",")) + 1))
    # non-trailing arg var: fixed at the comma after it
    bad = "let h: HashMap<String, Int64> = HashMap<String, Int64>([1, 2], 3)"
    out.append((bad, "arg_var", "HashMap ctor array 1st", bad.find("[1, 2]") + 1))
    # Bool var is unfixable -> anchor at var itself
    bad = "al.add(b)"
    out.append((bad, "arg_var", "ArrayList.add(Bool var)", bad.find("b")))
    # method chain receiver: s.size() — String has no size() -> missing member
    bad = "let z: Int64 = s.size()"
    out.append((bad, "missing_member", "String.size()", bad.find("size")))
    return out


def assign_cases():
    out = []
    # call returning String assigned to Int64 -> statement boundary
    bad = "let z: Int64 = mkStr()"
    out.append((bad, "assign_boundary", "Int64 = String call", len(bad) + 1))
    bad = "let z: Int64 = s.substring(1)"
    out.append((bad, "assign_boundary", "Int64 = String method", len(bad) + 1))
    bad = "let z: Int64 = mkBool()"
    out.append((bad, "assign_boundary", "Int64 = Bool call", len(bad) + 1))
    bad = "let z: String = mkInt()"
    out.append((bad, "assign_boundary", "String = Int64 call", len(bad) + 1))
    bad = "let z: Bool = mkInt()"
    out.append((bad, "assign_boundary", "Bool = Int64 call", len(bad) + 1))
    # reassign to var of wrong type -> boundary
    bad = "v = mkInt()"
    out.append((bad, "assign_boundary", "String var = Int64 call", len(bad) + 1))
    bad = "v = n + 1"
    out.append((bad, "assign_boundary", "String var = Int64 expr", len(bad) + 1))
    # Optional unwrap missing: get returns Optional
    bad = "let z: Int64 = m.get(s)"
    out.append((bad, "assign_boundary", "Int64 = Optional get", len(bad) + 1))
    # literal type mismatch -> anchor at literal (official err_type_mismatch: `true`)
    bad = "let z: Int64 = true"
    out.append((bad, "literal_type", "Int64 = true", bad.find("true")))
    bad = "let z: Int64 = 1.5"
    out.append((bad, "literal_type", "Int64 = 1.5", bad.find("1.5")))
    return out


def ctor_cases():
    out = []
    # ctor arg wrong var -> anchor at its end boundary (official: `")\n`)
    bad = "let a2: Array<Int64> = Array<Int64>(s)"
    out.append((bad, "ctor_arg", "Array<Int64>(String var)", bad.find("(s)") + 2))
    bad = "let a2: Array<Int64> = Array<Int64>(b)"
    out.append((bad, "ctor_arg", "Array<Int64>(Bool var)", bad.find("(b)") + 2))
    bad = "let hs: HashSet<String> = HashSet<String>(1)"
    out.append((bad, "ctor_arg", "HashSet<String>(Int64)", bad.find("(1)") + 2))
    return out


def eq_rel_cases():
    out = []
    # eq with incompatible literal RHS -> RHS literal end boundary (official `"\n`)
    bad = "let z: Bool = n == \"x\""
    out.append((bad, "eq_incomp", "Int64 == String lit", bad.find('"x"') + 3))
    bad = "let z: Bool = s == 1"
    out.append((bad, "eq_incomp", "String == Int64 lit", bad.find("1") + 1))
    bad = "let z: Bool = n == true"
    out.append((bad, "eq_incomp", "Int64 == Bool lit", bad.find("true") + 4))
    # rel unordered -> anchor at operator (official err_rel_unordered: ` <`)
    bad = "let z: Bool = n < s"
    out.append((bad, "rel_unordered", "Int64 < String var", bad.find("<")))
    bad = "let z: Bool = s < n"
    out.append((bad, "rel_unordered", "String < Int64 var", bad.find("<")))
    bad = "let z: Bool = b > n"
    out.append((bad, "rel_unordered", "Bool > Int64 var", bad.find(">")))
    bad = "let z: Bool = n < \"x\""
    out.append((bad, "rel_unordered", "Int64 < String lit", bad.find("<")))
    # mixed numeric relational is VALID (numeric widening)
    bad = "let z: Bool = n < 1.5"
    out.append((bad, "assign_boundary", "Bool = mixed numeric rel", len(bad) + 1))
    return out


def forin_elem_cases():
    out = []
    bad = "for (x in arr) {\n        let y: String = x\n    }"
    out.append((bad, "forin_elem", "String = Int64 elem", len(bad) + 1))
    return out


def lambda_arg_cases():
    out = []
    # takesLambda expects (Int64)->Int64; body returns String -> lambda close boundary
    bad = "takesLambda({ x: Int64 => \"bad\" })"
    out.append((bad, "lambda_ret", "lambda body String", bad.find("})") + 2))
    # wrong param count: (Int64, Int64)->Int64 vs (Int64)->Int64
    bad = "takesLambda({ x: Int64, y: Int64 => x + y })"
    out.append((bad, "lambda_arity", "lambda 2 params", bad.find("})") + 2))
    # param type wrong: String vs Int64
    bad = "takesLambda({ x: String => 1 })"
    out.append((bad, "lambda_param", "lambda param String", bad.find("})") + 2))
    return out


def build_all():
    cases = []
    builders = [arith_var_cases, mod_cases, unary_cases, logical_cases, cond_cases,
                for_iter_cases, index_cases, arg_var_cases, assign_cases, ctor_cases,
                eq_rel_cases, forin_elem_cases, lambda_arg_cases]
    for builder in builders:
        for bad_stmt, kind, desc, err_pos in builder():
            full = BAD_TEMPLATE.replace("{bad_stmt}", bad_stmt)
            cases.append((full, kind, desc, err_pos))
    return cases


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def token_index_of_char(text, token_ids, char_pos, enc):
    acc = 0
    for idx, tok in enumerate(token_ids):
        acc += len(enc.decode_single_token_bytes(tok).decode("utf-8", "replace"))
        if acc > char_pos:
            return idx
    return len(token_ids) - 1


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
    return first_err, len(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solution", type=Path, required=True)
    parser.add_argument("--failure-json", type=Path)
    parser.add_argument("--report-md", type=Path)
    args = parser.parse_args()

    _configure_oracle()
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")

    generated = 0
    divergences = []
    for full, kind, desc, err_pos_local in build_all():
        ok, msg = oracle_accepts(full)
        if ok:
            continue
        token_ids = enc.encode(full)
        bad_start = full.rindex("    ") if False else full.find("    let ")  # unused
        # the bad stmt is the block starting after the last var decl:
        # BAD_TEMPLATE = VAR_PAD[...] + "{bad_stmt}\n}}\n" -> find offset
        template_off = VAR_PAD[: VAR_PAD.rindex("    println(padGamma(\"ok\"))")]
        idx = full.find(template_off)
        # compute char offset of the bad statement inside full
        bad_block = full[len(template_off):]
        # err_pos_local is relative to the bad statement text
        err_pos_global = len(template_off) + err_pos_local
        gt = token_index_of_char(full, token_ids, err_pos_global, enc)
        if gt >= len(token_ids):
            continue
        sol_err, n_lines = run_solution(args.solution, token_ids)
        generated += 1
        if sol_err != gt:
            divergences.append({
                "kind": kind,
                "desc": desc,
                "gt": gt,
                "solution": sol_err,
                "n_lines": n_lines,
                "oracle": msg[:160],
                "source": full,
            })

    report = {"generated": generated, "divergence_count": len(divergences),
              "divergences": divergences[:300]}
    if args.failure_json:
        args.failure_json.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report_md:
        md = ["# statement-level 差分 fuzz 报告", "",
              f"- 生成用例：{generated}", f"- 偏差数：{len(divergences)}", "",
              "## 偏差统计"]
        counts = Counter(d["kind"] for d in divergences)
        for kind, n in counts.most_common():
            md.append(f"- `{kind}`: {n}")
        md += ["", "## 明细"]
        for d in divergences[:80]:
            md.append(f"- {d['desc']}: gt={d['gt']} solution={d['solution']} (oracle: {d['oracle']})")
        args.report_md.write_text("\n".join(md))
    print(json.dumps({"generated": generated, "divergences": len(divergences)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
