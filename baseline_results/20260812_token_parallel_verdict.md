# Per-token syntax/semantic parallel candidate verdict

Date: 2026-08-12  
Control: `3d1e925`  
Candidate: `84b2de7`  
Verdict: **REJECTED and reverted**

## Change under test

The candidate used one persistent syntax worker. For each token, the worker ran
the XGrammar matcher while the main thread ran the existing semantic checker;
the main thread waited for both results before emitting the one required
response. Initialization remained serial so the previously rejected startup
overlap was not mixed into this candidate. No grammar, context, token table,
semantic rule, dirty-generation timing, or protocol boundary changed.

## Correctness gates

All required correctness gates passed in the locked Linux AArch64 image before
performance measurement:

- official exact-first-error cases: 50/50;
- unit tests: 39/39;
- native fragment differential: 66 cases x 4 fragmentations;
- native context differential: 7/7;
- hidden semantic fuzz, seed 20260805: 144 cases x byte/random/line/cl100k/whole,
  zero failures;
- official oracle corpus: 45/45; project corpus: 57/57;
- comprehensive corpus: 113/113, 96 oracle checks, 226 protocol runs;
- serial shadow with forced scheduling yields: hidden fuzz and comprehensive
  corpus both passed;
- test-only hooks: thread-launch failure serial fallback, forced yields, syntax
  exception, semantic exception, and simultaneous-exception priority passed;
- default concurrency stress: 1000 cold starts, 256-statement/1285-token valid
  stream, 8 x 20 client processes, and all seven resource-fault cases passed;
- one-CPU stress repeated the same 1000/256/8x20 configuration and passed;
- full-process ASan/UBSan: official/project differential, comprehensive corpus,
  and concurrency stress passed.

TSan compiled successfully. It could not start because the locked container
denied libtsan's `ADDR_NO_RANDOMIZE` personality request (exit 66). The raw
diagnostic is retained; this is the same container limitation recorded for the
startup-parallel candidate.

## Formal A/B/A result

Each stage used one warmup and nine measured trials per official case. The
control is the per-case average of A1 and A2 medians.

| Metric | A1 | Control | Candidate | A2 | Candidate improvement |
|---|---:|---:|---:|---:|---:|
| SUM | 1654.163 ms | 1663.989 ms | 1847.624 ms | 1673.814 ms | **-11.036%** |
| MEDIAN | 34.090 ms | 34.351 ms | 38.130 ms | 34.543 ms | **-11.002%** |
| P95 | 42.004 ms | 42.525 ms | 47.065 ms | 43.045 ms | **-10.677%** |
| MAX | 46.474 ms | 46.911 ms | 52.015 ms | 47.348 ms | **-10.880%** |

- A1/A2 SUM drift: 1.181%;
- cross-case median drift: 1.023%;
- faster cases: 0/50; slower cases: 50/50;
- all stages: 50/50 correct with zero failed trials;
- official harness: control 5630.825 ms, candidate 5874.622 ms, candidate
  regression 4.330% (both 50/50).

The low control drift and universal slowdown make the regression conclusive.
The per-token mutex/condition-variable handoff and wake-up overhead exceeded
the work hidden by syntax/semantic overlap. The candidate therefore fails the
performance gate immediately; no 21-trial extension is permitted or needed.

## Disposition

`84b2de7` remains in local Git as an auditable rejected experiment. Its
production changes are reverted before the next candidate. It must not become
the next control and must not be combined with DeclarationSnapshot.
