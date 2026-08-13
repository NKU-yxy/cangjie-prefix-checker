# G1 grammar scale development report — 2026-08-14

## Verdict

**REJECTED for this round's scale-robustness target.**

G1 removes the near-cubic statement-list growth and makes the 300-local case
fast, but it does not make the 4 KiB identifier case finish.  Both protocols
still time out after 30 seconds after producing only 89 of 527 answers.  The
candidate therefore was not submitted for independent review and no official
50-case A/B/A performance run was performed.

This is a development verdict, not an independent final-acceptance verdict.

## Baselines and local commits

- Starting HEAD: `1fe3f04b95179ad0b88e3e671f6b2f057262c893`
- Accepted control: `68d780d54c25883b4e05c3f3562b315750b38af0`
- Lean production anchor: `c35afaecb32c216bb9c24e00b0288c468a125a89`
- Candidate 0, test-only grammar shadow: `5c0953b3668e30dbca42eb127e9c7ee4a32feaab`
- G1 grammar change: `8c90d6ff7547244c0f31b20b6ed9cf2dc12b44b2`
- G1 candidate including regenerated manifest integrity hashes:
  `499c9c787fdbd8140307c5b5f472e9aee0c9342c`
- Branch: `optimization/grammar-scale-20260813`
- Remote pushes: none

The initial production files at `1fe3f04` were byte-identical to the accepted
control.  The two protected, untracked reports remained byte-identical and
were never staged:

- `TEAM_OPTIMIZATION_PROGRESS_REPORT_20260813.md`:
  `f9423e839acd56d03baec78a0697bd1c1108a8d012a5799d6ec9b7d2ac42d053`
- `CURRENT_BEST_VS_INITIAL_OFFICIAL50_20260813.md`:
  `e25ffb53cc20d3ad36d3e1f037c1133cb124b3f091df8e3483ffb23dca2cf69c`

## Candidate changes

Candidate 0 adds a test-only dual matcher behind
`CANGJIE_GRAMMAR_SHADOW_BUILD=1`.  A normal build does not construct or carry
the second matcher.  The shadow gives both matchers identical fragments and
checks each response, first rejection, accumulated transcript length/content,
and exception type/message.  A matrix generator covers the required local
counts, identifier lengths, whitespace/comment/control-flow/statement cases,
illegal byte boundaries, and byte/random/line/cl100k/whole fragmentation.

G1 makes exactly the requested grammar transformation in both grammars:

```text
raw:   statement (ws statements)?  -> statement (ws statement)*
token: statement statements?       -> statement statement*
```

No whitespace rule, optional semicolon, statement alternative, tokenizer,
input threshold, or semantic rule was changed.  The only other G1 commit
updates the two grammar dependency hashes in the comprehensive manifest; case
contents, labels, corpus hash, and coverage are unchanged.

Default production behavior changes only through:

- `grammar/cangjie.gbnf`
- `grammar/cangjie_token.gbnf`

`build.sh` and `cpp/solution.cpp` contain only compile-time-excluded Candidate
0 test infrastructure.  `test_cases/comprehensive/manifest.json` changes only
the two dependency hashes.

## Integrity hashes

| Artifact | Control | G1 candidate |
|---|---:|---:|
| `grammar/cangjie.gbnf` | `6131041ed52120b65ee75440c97704dfe91d1a0fda0aaf99b3e1c75e3054f989` | `eb4a5cd0b705407281860bd2ddf1e20b97ad48aceafd96621d55c1385c06ca90` |
| `grammar/cangjie_token.gbnf` | `cbe033bea0b88c4d042e258cb4a9b79dfe0912072dc6b5468f742c5d57d6dae0` | `1cb6503b4ce8c24b6a4f12b7ff0ee1a7e8f4d09273bf4e87d254749209096cc1` |
| `cpp/solution.cpp` | `09e479a8d381bbc7957abe4ac7fcb6cd869c7cdf341550f5d90da7e22f097e44` | `7016077080e9b3bdf62d025d9ec7933a1f1d8d0fdcdfc2852c66d2fae0b0d8e5` |
| default Linux AArch64 `solution` | — | `5d9b87076929726411a65d93e5fe1988a71f41ebbcf541c52843f1397c4c4110` |

The default binary hash is unchanged from Candidate 0's default build,
confirming that enabling the shadow requires an explicit test build.

## Correctness development gates

All completed correctness gates passed in the locked Linux AArch64 image
`docker.educg.net/compiler_system_challenge/cjchecker:20260522`:

| Gate | Default G1 | Grammar shadow G1 | Sanitizer + shadow |
|---|---:|---:|---:|
| Official exact first error | 50/50 | 50/50 | 50/50 |
| Authoritative comprehensive | 219/219 | 219/219 | 219/219 |
| Non-scale comprehensive | 364/364 | 364/364 | 364/364 |
| Protocol runs | 728/728 | 728/728 | 728/728 |
| Safe prefixes | 238/238 | 238/238 | 238/238 |
| Protocol edges | 26/26 | 26/26 | 26/26 |
| Official semantic corpus | 45/45 | 45/45 | 45/45 |
| Project corpus | 57/57 | 57/57 | 57/57 |
| Hidden fuzz, five layouts | 144 x 5, 0 failures | 144 x 5, 0 failures | 144 x 5, 0 failures |

Additional completed gates:

- Strict reference diff against a clean same-container build of `68d780d`:
  728 protocol runs, 238 safe-prefix runs, and 26 edge runs had identical
  transcripts, first rejection, exit code, stderr, and exception outcome.
- Native fragments: 66/66 in each of four fragmentation modes.
- Native contexts: 7/7.
- ASan/LSan/UBSan: no sanitizer or grammar-shadow report.  The build emitted
  only the three pre-existing range-loop warnings in `native_semantic.cpp`.
- Final default-build unit tests after manifest hash refresh: 61/61.
- The full shadow matrix is encoded in tests.  A direct 890-run smoke covered
  89 cases, five layouts, and two protocols.  An extended old=old diagnostic
  reached all local counts through 500 and identifiers through 1024 before it
  was stopped: the old matcher makes the remaining long-identifier cells take
  hours.  The rejected candidate was not allowed to waive this uncompleted
  high-end matrix execution.

Evidence files accompany this report.  The 145 diagnostic/spec-pending cases
retain the control's behavior; their existing 40 label disagreements were not
changed or treated as candidate failures.

## Scale results

The scale corpus was run in both default and competition protocols.  The
300-local case emitted all 3310 answers with exit code 0 and empty stderr in
both modes.  The 4 KiB identifier emitted only 89/527 answers before each
30-second timeout in both modes.  Thus only one of the two mandatory targets
was solved.

Single fresh-process scale-curve measurements against the same-container
control were:

| Local declarations | Control time | G1 time | Control RSS KiB | G1 RSS KiB |
|---:|---:|---:|---:|---:|
| 50 | 0.170 s | 0.040 s | 23,664 | 18,772 |
| 100 | 1.034 s | 0.082 s | 49,104 | 25,976 |
| 150 | 3.648 s | 0.142 s | 114,200 | 33,380 |
| 200 | 9.049 s | 0.221 s | 141,216 | 40,904 |
| 250 | 19.311 s | 0.302 s | 280,260 | 48,968 |
| 300 | >35 s, timed out | 0.400 s | 291,204 at timeout | 62,648 |
| 500 | skipped after control timeout | 0.926 s | — | 86,328 |

This curve no longer resembles the control's near-cubic growth and meets the
300-local target by a wide margin.

| Identifier length | Control time | G1 time | Control RSS KiB | G1 RSS KiB |
|---:|---:|---:|---:|---:|
| 128 | 0.225 s | 0.215 s | 17,032 | 17,984 |
| 256 | 1.659 s | 1.568 s | 38,236 | 36,432 |
| 512 | 14.519 s | 13.505 s | 142,792 | 127,028 |
| 1024 | >35 s, timed out | >35 s, timed out | 270,052 | 267,564 |

The identifier curve is essentially unchanged and still has explosive
growth.  The requested 4096-byte point therefore cannot satisfy the two-second
or 10x criteria.

The other seven scale cases had no time regression over 10%.  The largest
relative slowdown was the 64-nested-comment case at 5.5%, only 0.57 ms in
absolute time.  Every measured candidate/control peak-RSS ratio was below
1.25.  Detailed times, answer counts, first errors, stderr, and RSS are in:

- `20260814_g1_499c9c7_scale_curve.json`
- `20260814_g1_499c9c7_other_scale_profile.json`
- `20260814_g1_499c9c7_scale_gate.json`

## G2 and G3 stopping decisions

### G2 — full-vocabulary `AcceptToken`

A throwaway, uncommitted XGrammar 0.2.1 API probe used the full 100,277-entry
cl100k vocabulary with `TokenizerInfo(VocabType::RAW)` and `AcceptToken`.
Measured costs were approximately 18.5–18.9 ms for `TokenizerInfo`, 345–355 ms
for grammar compilation, and 58.4 MiB startup RSS.  Short transcript shadow
cases matched `AcceptString`, and an 8 KiB string's 5135 token accepts took
about 2.9 ms, but the 4 KiB identifier still exceeded 30 seconds.  It therefore
failed both the target-benefit and startup/RSS stopping conditions.  No G2
production change or commit was retained.

### G3 — identifier-led factoring

An uncommitted prototype factored identifier/generic primary alternatives and
removed the redundant statement-level assignment alternative already covered
by assignment expressions.  It left the 4 KiB identifier above 30 seconds and
did not materially improve G1's 300-local result, so it was restored without a
commit.

A separate, deliberately non-equivalent diagnostic requiring non-empty
whitespace between statements made the 4 KiB case finish in about 0.05 seconds.
This isolated the dominant ambiguity: because statement separators may be
empty, semicolons are optional, and keywords can match identifier prefixes, a
long identifier can be partitioned at many character boundaries into adjacent
expression statements.  XGrammar's supported GBNF/regex converter has no
lookahead or word-boundary assertion with which to express maximal-munch
identifier boundaries while preserving all current prefixes.  Safely fixing
that requires a lexer/token-state redesign at G4 scope.  G4 was explicitly out
of scope for this round and was not implemented.

## Performance and anti-cheat disposition

The official 50-case A1/candidate/A2 benchmark was intentionally not run:
the candidate had already failed the mandatory 4 KiB scale gate, so the
contract says to stop before formal performance measurement.  Correctness
results above are development prechecks only and are not independent final
acceptance.

A production diff audit found no sample names, test paths, Docker/container or
benchmark/harness detection, official first-error constants, scale length/count
thresholds, environment-driven semantic paths, or CPU/Apple-specific flags.
The only numeric-bound search hit was the generic hex decoder's `a`–`f` range
inside test-only shadow input handling.  Default binary strings contain no
grammar-shadow option, class, mismatch text, profile marker, or test/scale
specialization marker.

## Remaining risk and disposition

- G1 appears grammar-equivalent on every completed control diff and shadow
  gate, but the old matcher prevented exhaustive execution of the largest
  explicit shadow-matrix identifier cells.
- More importantly, G1 does not solve one of the two required problems.
- No candidate from this round is `AWAITING INDEPENDENT REVIEW`, and no new
  accepted control is proposed.
- A separate local revert commit restores the G1 grammar and manifest hashes;
  its full SHA is reported in the final handoff.  Candidate 0's test-only
  diagnostics and this evidence remain available locally.
