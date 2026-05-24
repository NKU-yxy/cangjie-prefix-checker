#!/usr/bin/env python3
"""
Cangjie Syntax Checker CLI

Usage:
    python main.py <file.cj>           Check a Cangjie source file
    python main.py --code "<code>"     Check code directly from command line
    python main.py --test              Run built-in test cases

Output format:
    token: t1 t2 t3 t4 ...
    结果：1, 1, 0
"""

import sys
import os
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Cangjie Syntax Checker - token-by-token validation using XGrammar"
    )
    parser.add_argument(
        "file", nargs="?", help="Path to Cangjie source file (.cj)"
    )
    parser.add_argument(
        "--code", "-c", type=str, help="Cangjie source code string to check"
    )
    parser.add_argument(
        "--test", "-t", action="store_true", help="Run built-in test cases"
    )
    parser.add_argument(
        "--grammar", "-g", type=str, default=None,
        help="Path to custom GBNF grammar file"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )

    args = parser.parse_args()

    if args.test:
        run_tests(args.grammar, args.verbose)
        return

    # Read source code
    if args.code:
        source = args.code
        filename = "<command-line>"
    elif args.file:
        filepath = args.file
        if not os.path.isfile(filepath):
            print(f"Error: File not found: {filepath}", file=sys.stderr)
            sys.exit(1)
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        filename = filepath
    else:
        parser.print_help()
        sys.exit(1)

    # Run checker
    from src.syntax_checker import check_cangjie

    if args.verbose:
        print(f"Checking: {filename}")
        print(f"Source length: {len(source)} chars")
        print()

    result = check_cangjie(source, grammar_path=args.grammar)

    print(result.format_output())

    if args.verbose:
        total = len(result.tokens)
        syn_ok = sum(result.syntax_results)
        sem_ok = sum(result.semantic_results)
        print(f"\nTokens: {total}")
        print(f"Syntax: {syn_ok} valid, {total - syn_ok} invalid")
        print(f"Semantic: {sem_ok} valid, {total - sem_ok} invalid")
        if not result.passed:
            err_tok = result.error_token or "(end)"
            err_line = result.error_line or "?"
            err_col = result.error_col or "?"
            print(f"First error: [{result.error_type}] '{err_tok}' "
                  f"line {err_line}, column {err_col}")
            if result.error_message:
                print(f"  {result.error_message}")

    sys.exit(0 if result.passed else 1)


def run_tests(grammar_path=None, verbose=False):
    """Run built-in test cases."""
    from src.syntax_checker import check_cangjie

    test_cases = [
        # --- Valid cases ---
        ("Valid: simple var decl", "var x: Int32 = 42", True),
        ("Valid: let without type", 'let name = "Cangjie"', True),
        ("Valid: expression", "var x = 1 + 2 * 3 - 4", True),
        ("Valid: function decl", "func f(x: Int32): Int32 { return x }", True),
        ("Valid: if-else", "func test(a: Int32) { if a > 0 { return 1 } else { return 0 } }", True),
        ("Valid: while loop", "func loop() { var i = 0 while i < 10 { i = i + 1 } }", True),
        ("Valid: for-in", "func sum(v: Int32) { for (i in 0..10) { i = i + 1 } }", True),
        ("Valid: class", "class Point { x: Float64 y: Float64 func dist(): Float64 { return x * x + y * y } }", True),
        ("Valid: package+import", "package app\n\nimport std.io\n\nfunc main() { io.println(\"hello\") }", True),
        ("Valid: match", 'func f(x: Int32) { match (x) { case 0 => "zero", case 1 => "one", case _ => "other" } }', True),

        # --- P1-3 valid: Lambda semantic checking ---
        ("P1-3: lambda typed param", "func f() { var g = { x: Int32 => x + 1 }; var r = g(5); }", True),
        ("P1-3: lambda untyped param", "func f() { var g = { x => x + 1 }; var r = g(5); }", True),
        ("P1-3: lambda no params", "func f() { var g = { => 42 }; var r = g(); }", True),
        ("P1-3: lambda block body", "func f() { var g = { x: Int32 => { return x + 1; } }; var r = g(5); }", True),
        ("P1-3: block expression with defined var", "func f(): Int64 { var x = 1; var r = { x + 1 }; return r; }", True),
        ("P1-3: empty block expression", "func f() { var x = { }; }", True),
        ("P1-3: nested lambda", "func f() { var g = { x: Int32 => { y: Int32 => x + y } }; }", True),
        ("P1-3: lambda multi params", "func f() { var g = { x: Int32, y: Int32 => x + y }; }", True),
        ("P1-3: lambda IIFE", "func f(): Int64 { var r = { x: Int32 => x + 1 }(5); return r; }", True),

        # --- P1-4 valid: Generic type parameter inference ---
        ("P1-4: infer Int64 generic return",
         "func identity<T>(x: T): T { return x } func main() { var a: Int64 = identity(42); }",
         True),
        ("P1-4: infer String generic return",
         'func identity<T>(x: T): T { return x } func main() { var s: String = identity("hello"); }',
         True),
        ("P1-4: infer multiple generic params",
         'func second<T, U>(a: T, b: U): U { return b } func main() { var s: String = second(1, "ok"); }',
         True),
        ("P1-4: generic return can use non-last arg",
         'func first<T, U>(a: T, b: U): T { return a } func main() { var x: Int64 = first(1, "ok"); }',
         True),
        ("P1-4: repeated generic param consistent",
         "func same<T>(a: T, b: T): T { return a } func main() { var x: Int64 = same(1, 2); }",
         True),

        # --- Invalid cases ---
        ("Invalid: var without id", "var = 42", False),
        ("Invalid: extra paren", "var x = 1 + )", False),
        ("Prefix: unclosed string", 'var x = "hello', True),
        ("Prefix: missing brace", "func f() { var x = 1", True),
        ("Invalid: bad keyword order", "if var x = 1", False),

        # --- P1-3 invalid: Lambda semantic checking ---
        ("P1-3: block expr undefined var", "func f() { var r = { y + 1 }; }", False),
        ("P1-3: nested block undefined var", "func f() { var x = 1; var r = { { z + 1 } }; }", False),
        ("P1-3: lambda body undefined var", "func f() { var g = { x: Int32 => z }; }", False),

        # --- P1-4 invalid: Generic inference rejects bad constraints ---
        ("P1-4: inferred return type mismatch",
         "func identity<T>(x: T): T { return x } func main() { var s: String = identity(42); }",
         False),
        ("P1-4: repeated generic param mismatch",
         'func same<T>(a: T, b: T): T { return a } func main() { var x: Int64 = same(1, "x"); }',
         False),
        ("P1-4: non-last generic return type mismatch",
         'func first<T, U>(a: T, b: U): T { return a } func main() { var s: String = first(1, "ok"); }',
         False),
        ("P1-4: concrete param still checked",
         'func take<T>(x: T, count: Int64): T { return x } func main() { var x: String = take("x", "bad"); }',
         False),
    ]

    passed = 0
    failed = 0

    for name, code, expect_pass in test_cases:
        result = check_cangjie(code, grammar_path=grammar_path)

        correct = (expect_pass == result.passed)

        status = "OK" if correct else "FAIL"
        if correct:
            passed += 1
        else:
            failed += 1

        if verbose or not correct:
            print(f"[{status}] {name}")
            if not correct:
                print(f"       Expected pass={expect_pass}, got passed={result.passed}")
                print(f"       Code: {code!r}")
                if result.error_message:
                    print(f"       Error: [{result.error_type}] {result.error_message}")
                print(f"       {result.format_output()}")
        else:
            syn_part = result.format_output().split('\n')[1] if '\n' in result.format_output() else '?'
            print(f"[{status}] {name}: {syn_part}")

    print(f"\nTotal: {passed} passed, {failed} failed out of {len(test_cases)} tests")


if __name__ == "__main__":
    main()
