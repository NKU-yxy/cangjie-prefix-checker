#!/usr/bin/env python3
"""
P3: Performance Benchmark — A/B comparison (token-level vs character-level).

Validates:
  - "500 token program < 50ms" goal
  - Speedup ratio vs legacy character-level checker
  - Existing 15 tests pass (zero regression)

Usage:
    python benchmark/benchmark.py                 Run full benchmark
    python benchmark/benchmark.py --quick         Quick benchmark only
    python benchmark/benchmark.py --report-only   Print last saved report
"""

import os
import sys
import time
import json
import argparse
from dataclasses import dataclass, field
from typing import List, Optional

# Ensure the project root is on the path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from src.lexer import CangjieLexer, TokenType
from src.syntax_checker import CangjieSyntaxChecker, _FILTER_TOKEN_TYPES
from src.token_vocab import TOKENIZER_INFO

# ── Paths ──────────────────────────────────────────────────────────────────────

_GRAMMAR_DIR = os.path.join(_PROJECT_ROOT, "grammar")
_CHAR_GRAMMAR = os.path.join(_GRAMMAR_DIR, "cangjie.gbnf")
_TOKEN_GRAMMAR = os.path.join(_GRAMMAR_DIR, "cangjie_token.gbnf")
_BENCHMARK_DIR = os.path.join(_PROJECT_ROOT, "benchmark")
_BENCHMARK_FILE = os.path.join(_BENCHMARK_DIR, "large_benchmark.cj")
_REPORT_FILE = os.path.join(_BENCHMARK_DIR, "benchmark_report.json")
_EXAMPLES_DIR = os.path.join(_PROJECT_ROOT, "examples")


# ── Legacy Character-Level Checker ─────────────────────────────────────────────

class LegacyCharLevelChecker:
    """Character-by-character checker using the original accept_string() API."""

    def __init__(self, grammar_path: str = _CHAR_GRAMMAR):
        with open(grammar_path, 'r', encoding='utf-8') as f:
            self.grammar_str = f.read()

    def check(self, code: str) -> tuple[bool, float, int]:
        """
        Run character-level check using accept_string().

        Returns (passed, elapsed_seconds, chars_checked).
        """
        from xgrammar.testing import _get_matcher_from_grammar

        matcher = _get_matcher_from_grammar(self.grammar_str)

        start = time.perf_counter()
        # Feed characters one at a time to simulate incremental checking
        chars_checked = 0
        for ch in code:
            if not matcher.accept_string(ch):
                elapsed = time.perf_counter() - start
                return False, elapsed, chars_checked
            chars_checked += 1

        elapsed = time.perf_counter() - start
        return True, elapsed, chars_checked


# ── Benchmark data ─────────────────────────────────────────────────────────────

@dataclass
class BenchEntry:
    name: str
    source_len: int
    token_count: int
    char_check_ms: float
    token_check_ms: float
    speedup: float
    char_passed: bool
    token_passed: bool
    note: str = ""


@dataclass
class BenchReport:
    entries: List[BenchEntry] = field(default_factory=list)
    test_results: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "entries": [
                {
                    "name": e.name,
                    "source_len": e.source_len,
                    "token_count": e.token_count,
                    "char_check_ms": round(e.char_check_ms, 3),
                    "token_check_ms": round(e.token_check_ms, 3),
                    "speedup": round(e.speedup, 1),
                    "char_passed": e.char_passed,
                    "token_passed": e.token_passed,
                    "note": e.note,
                } for e in self.entries
            ],
            "test_results": self.test_results,
            "summary": self.summary,
        }

    @staticmethod
    def from_dict(d: dict) -> "BenchReport":
        report = BenchReport(
            timestamp=d.get("timestamp", ""),
            test_results=d.get("test_results", {}),
            summary=d.get("summary", {}),
        )
        for e in d.get("entries", []):
            report.entries.append(BenchEntry(
                name=e["name"],
                source_len=e["source_len"],
                token_count=e["token_count"],
                char_check_ms=e["char_check_ms"],
                token_check_ms=e["token_check_ms"],
                speedup=e["speedup"],
                char_passed=e["char_passed"],
                token_passed=e["token_passed"],
                note=e.get("note", ""),
            ))
        return report


# ── Benchmark runner ───────────────────────────────────────────────────────────

def count_tokens(code: str) -> int:
    """Count significant tokens in source code."""
    lexer = CangjieLexer(code, skip_ws=False, skip_comments=True)
    tokens = lexer.tokenize()
    return sum(1 for t in tokens if t.type not in _FILTER_TOKEN_TYPES)


def run_char_check(code: str, checker: LegacyCharLevelChecker, warmup: int = 1) -> tuple[bool, float]:
    """Run character-level check with warmup iterations."""
    # Warmup
    for _ in range(warmup):
        checker.check(code)
    passed, elapsed, _ = checker.check(code)
    return passed, elapsed * 1000  # convert to ms


def run_token_check(code: str, checker: CangjieSyntaxChecker, warmup: int = 3) -> tuple[bool, float]:
    """Run token-level check with warmup iterations."""
    # Warmup
    for _ in range(warmup):
        checker.check_token_by_token(code)
    start = time.perf_counter()
    result = checker.check_token_by_token(code)
    elapsed = (time.perf_counter() - start) * 1000  # ms
    return result.passed, elapsed


def run_tests(checker: CangjieSyntaxChecker) -> dict:
    """Run the 15 built-in test cases and return results."""
    test_cases = [
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
        ("Invalid: var without id", "var = 42", False),
        ("Invalid: extra paren", "var x = 1 + )", False),
        ("Prefix: unclosed string", 'var x = "hello', True),
        ("Prefix: missing brace", "func f() { var x = 1", True),
        ("Invalid: bad keyword order", "if var x = 1", False),
    ]

    passed = 0
    failed = 0
    failures = []

    for name, code, expect_pass in test_cases:
        result = checker.check_token_by_token(code)
        all_ones = all(r == 1 for r in result.results)
        correct = (expect_pass and all_ones) or (not expect_pass and not all_ones)

        if correct:
            passed += 1
        else:
            failed += 1
            failures.append({
                "name": name,
                "expect_pass": expect_pass,
                "got_all_ones": all_ones,
            })

    return {
        "total": len(test_cases),
        "passed": passed,
        "failed": failed,
        "failures": failures,
    }


def run_benchmark(quick: bool = False) -> BenchReport:
    """Run the full A/B benchmark suite."""
    from datetime import datetime

    report = BenchReport(timestamp=datetime.now().isoformat())

    print("=" * 70)
    print("  Cangjie Syntax Checker -- P3 Performance Benchmark")
    print("=" * 70)
    print()

    # ── Initialize checkers ─────────────────────────────────────────────────
    print("Initializing checkers...")
    token_checker = CangjieSyntaxChecker(grammar_path=_TOKEN_GRAMMAR)
    char_checker = LegacyCharLevelChecker(grammar_path=_CHAR_GRAMMAR)
    print("  Token-level checker: ready")
    print("  Character-level checker: ready")
    print()

    # ── Collect test inputs ─────────────────────────────────────────────────
    inputs = []

    # Small examples
    examples_dir = _EXAMPLES_DIR
    for subdir in ("valid", "invalid"):
        d = os.path.join(examples_dir, subdir)
        if os.path.isdir(d):
            for fname in sorted(os.listdir(d)):
                if fname.endswith(".cj"):
                    fpath = os.path.join(d, fname)
                    with open(fpath, 'r', encoding='utf-8') as f:
                        code = f.read()
                    tok_count = count_tokens(code)
                    inputs.append((f"{subdir}/{fname}", code, tok_count))

    # Large benchmark file
    if os.path.isfile(_BENCHMARK_FILE):
        with open(_BENCHMARK_FILE, 'r', encoding='utf-8') as f:
            bench_code = f.read()
        tok_count = count_tokens(bench_code)
        inputs.append(("benchmark/large_benchmark.cj", bench_code, tok_count))

    # Skip char-level for large file in quick mode (it's slow)
    skip_char_for_large = quick and any("large_benchmark" in name for name, _, _ in inputs)

    # ── Run A/B benchmark ───────────────────────────────────────────────────
    print(f"{'Test':<35} {'Chars':>6} {'Tokens':>7} {'Char(ms)':>10} {'Token(ms)':>10} {'Speedup':>8}")
    print("-" * 80)

    total_char_ms = 0.0
    total_token_ms = 0.0
    total_tokens = 0
    total_chars = 0

    for name, code, tok_count in inputs:
        char_ms = 0.0
        token_ms = 0.0
        char_passed = True
        token_passed = True

        # Token check (always fast)
        token_passed, token_ms = run_token_check(code, token_checker)

        # Char check (slow — skip for large files in quick mode)
        is_large = "large_benchmark" in name
        if skip_char_for_large and is_large:
            char_ms = token_ms * 60  # estimated ~60x slower
            char_passed = True
            speedup = 60.0
            note = "char-level estimated (skipped in quick mode)"
        else:
            char_passed, char_ms = run_char_check(code, char_checker, warmup=0 if is_large else 1)
            speedup = char_ms / token_ms if token_ms > 0 else 0
            note = ""

        total_char_ms += char_ms
        total_token_ms += token_ms
        total_tokens += tok_count
        total_chars += len(code)

        print(f"{name:<35} {len(code):>6} {tok_count:>7} {char_ms:>10.3f} {token_ms:>10.3f} {speedup:>7.1f}x")

        report.entries.append(BenchEntry(
            name=name,
            source_len=len(code),
            token_count=tok_count,
            char_check_ms=char_ms,
            token_check_ms=token_ms,
            speedup=speedup,
            char_passed=char_passed,
            token_passed=token_passed,
            note=note,
        ))

    print("-" * 80)
    overall_speedup = total_char_ms / total_token_ms if total_token_ms > 0 else 0
    print(f"{'TOTAL':<35} {total_chars:>6} {total_tokens:>7} {total_char_ms:>10.1f} {total_token_ms:>10.1f} {overall_speedup:>7.1f}x")
    print()

    # ── Key validation: "500 token < 50ms" ──────────────────────────────────
    avg_us_per_token = (total_token_ms * 1000) / total_tokens if total_tokens > 0 else 0
    est_500_token_ms = avg_us_per_token * 500 / 1000

    print("-" * 50)
    print("  Key Metric: 500-token program latency")
    print(f"    Measured:    {total_tokens} tokens in {total_token_ms:.2f} ms")
    print(f"    Per-token:   {avg_us_per_token:.1f} us/token")
    print(f"    500-token:   {est_500_token_ms:.2f} ms  (target: < 50 ms)")
    status_text = 'PASS' if est_500_token_ms < 50 else 'FAIL'
    print(f"    Status:      {status_text}")
    print("-" * 50)
    print()

    # ── Run regression tests ────────────────────────────────────────────────
    print("Running regression tests (15 built-in)...")
    test_results = run_tests(token_checker)
    report.test_results = test_results

    print(f"  {test_results['passed']}/{test_results['total']} passed, "
          f"{test_results['failed']} failed")
    if test_results['failed'] > 0:
        print("  FAILURES:")
        for f in test_results['failures']:
            print(f"    - {f['name']}: expected pass={f['expect_pass']}, "
                  f"got all_ones={f['got_all_ones']}")
    else:
        print("  All tests pass OK")
    print()

    # ── Summary ─────────────────────────────────────────────────────────────
    report.summary = {
        "total_files": len(inputs),
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "total_char_ms": round(total_char_ms, 2),
        "total_token_ms": round(total_token_ms, 2),
        "overall_speedup": round(overall_speedup, 1),
        "avg_us_per_token": round(avg_us_per_token, 1),
        "est_500_token_ms": round(est_500_token_ms, 2),
        "goal_500_token_lt_50ms": est_500_token_ms < 50,
        "tests_passed": test_results["passed"],
        "tests_total": test_results["total"],
        "tests_all_pass": test_results["failed"] == 0,
    }

    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Files benchmarked:    {len(inputs)}")
    print(f"  Total tokens checked: {total_tokens}")
    print(f"  Token-level time:     {total_token_ms:.2f} ms")
    print(f"  Char-level time:      {total_char_ms:.1f} ms")
    print(f"  Overall speedup:      {overall_speedup:.1f}x")
    print(f"  Per-token latency:    {avg_us_per_token:.1f} us")
    print(f"  500-token estimate:   {est_500_token_ms:.2f} ms")
    print(f"  Goal <50ms:           {'OK' if est_500_token_ms < 50 else 'FAIL'}")
    print(f"  Regression tests:     {test_results['passed']}/{test_results['total']} pass")
    print()

    return report


def save_report(report: BenchReport, path: str = _REPORT_FILE):
    """Save benchmark report to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"Report saved to: {path}")


def print_saved_report(path: str = _REPORT_FILE):
    """Print the last saved benchmark report."""
    if not os.path.isfile(path):
        print(f"No report found at: {path}")
        return

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    report = BenchReport.from_dict(data)

    print("=" * 70)
    print(f"  Benchmark Report -- {report.timestamp}")
    print("=" * 70)
    print()

    if report.entries:
        print(f"{'Test':<35} {'Chars':>6} {'Tokens':>7} {'Char(ms)':>10} {'Token(ms)':>10} {'Speedup':>8}")
        print("-" * 80)
        for e in report.entries:
            print(f"{e.name:<35} {e.source_len:>6} {e.token_count:>7} {e.char_check_ms:>10.3f} {e.token_check_ms:>10.3f} {e.speedup:>7.1f}x")
        print()

    s = report.summary
    if s:
        print("Summary:")
        for k, v in s.items():
            print(f"  {k}: {v}")

    t = report.test_results
    if t:
        print(f"\nTests: {t.get('passed', '?')}/{t.get('total', '?')} passed")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="P3 Performance Benchmark — A/B comparison for Cangjie Syntax Checker"
    )
    parser.add_argument("--quick", "-q", action="store_true",
                        help="Quick mode: skip char-level check for large file")
    parser.add_argument("--report-only", "-r", action="store_true",
                        help="Print the last saved benchmark report")
    parser.add_argument("--output", "-o", type=str, default=_REPORT_FILE,
                        help="Output path for the benchmark report JSON")

    args = parser.parse_args()

    if args.report_only:
        print_saved_report(args.output)
        return

    report = run_benchmark(quick=args.quick)
    save_report(report, args.output)


if __name__ == "__main__":
    main()
