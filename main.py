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


# 主入口：解析命令行，读取源码文件/代码串，调用检查器并打印结果
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


# 运行内置测试用例（合法/非法样例逐一检查并统计通过数）
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

        # --- P1-5 valid: init constructor semantic checking ---
        ("P1-5: init assigns this field",
         "class Point { var x: Int64 init(x: Int64) { this.x = x; } }",
         True),
        ("P1-5: init allows bare return",
         "class Point { init() { return; } }",
         True),
        ("P1-5: constructor call checks valid args",
         "class Point { init(x: Int64) { } } func main() { var p = Point(1); }",
         True),
        ("P1-5: delegated this constructor call",
         "class Point { init(x: Int64) { } init() { this(0); } }",
         True),

        # --- P1-6 valid: Expression-position generic construction ---
        ("P1-6: generic class construct substitutes Int64",
         "class Box<T> { init(x: T) { } } func main() { var b = Box<Int64>(1); }",
         True),
        ("P1-6: generic class construct substitutes multiple params",
         'class Pair<T, U> { init(a: T, b: U) { } } func main() { var p = Pair<String, Int64>("id", 7); }',
         True),
        ("P1-6: zero-arg generic class construct",
         'class Empty<T> { } func main() { var e = Empty<String>(); }',
         True),
        ("P1-6: builtin Array generic construct with size",
         "func main() { var a = Array<Int64>(10); }",
         True),
        ("P1-6: builtin Map generic construct",
         "func main() { var m = Map<String, Int64>(); }",
         True),
        ("P1-6: generic construct as function argument",
         "class Box<T> { init(x: T) { } } func useBox(b: Box): Int64 { return 0 } func main() { var x: Int64 = useBox(Box<Int64>(1)); }",
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

        # --- P1-5 invalid: init constructor semantic checking ---
        ("P1-5: init rejects return value",
         "class Point { init() { return 1; } }",
         False),
        ("P1-5: constructor arg count mismatch",
         "class Point { init(x: Int64) { } } func main() { var p = Point(); }",
         False),
        ("P1-5: constructor arg type mismatch",
         'class Point { init(x: Int64) { } } func main() { var p = Point("bad"); }',
         False),
        ("P1-5: delegated this arg type mismatch",
         'class Point { init(x: Int64) { } init() { this("bad"); } }',
         False),
        ("P1-5: this field must exist",
         "class Point { var x: Int64 init() { this.y = 1; } }",
         False),

        # --- P1-6 invalid: Generic construction must be checked semantically ---
        ("P1-6: generic class construct type mismatch",
         'class Box<T> { init(x: T) { } } func main() { var b = Box<Int64>("bad"); }',
         False),
        ("P1-6: generic class multi-param substitution direction",
         'class Pair<T, U> { init(a: T, b: U) { } } func main() { var p = Pair<String, Int64>(1, "id"); }',
         False),
        ("P1-6: generic class constructor arg count mismatch",
         "class Box<T> { init(x: T) { } } func main() { var b = Box<Int64>(); }",
         False),
        ("P1-6: generic class type arg count mismatch",
         "class Pair<T, U> { init(a: T, b: U) { } } func main() { var p = Pair<Int64>(1, 2); }",
         False),
        ("P1-6: builtin Array constructor arg type mismatch",
         'func main() { var a = Array<Int64>("bad"); }',
         False),
        ("P1-6: malformed generic construct missing gt",
         "class Box<T> { init(x: T) { } } func main() { var b = Box<Int64(1); }",
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
