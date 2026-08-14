# G4 ranged-state v1 — REJECTED

Date: 2026-08-14 (Asia/Shanghai)

This directory records the first G4 implementation trial.  It is retained as
negative evidence and is not an accepted optimization.

## Provenance

- accepted G1 control: `f5f2468c343e7ccc18d48cba0eab0a10920ee1c6`
- rejected candidate: `a111caf933cef64f32f3362a7294b80a37ff7271`
- independent rollback: `a62b256` (production bytes restored to the G1 control)
- official sample repo: `88336c400e7a4a671424e3e6c46c0866c8c0af93`
- official registry SHA-256:
  `2425e64184d69dd392f6cdec52dc20d42d0977cbe84be744a0ffbd1dfad374f2`
- image digest:
  `sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90`
- environment: Linux AArch64, 10 CPUs, 8,321,515,520 bytes visible memory

## Mechanism

The candidate represented the complete Earley relation using a state signature
that excluded only `rule_start_pos`, with the exact start-position set stored as
disjoint intervals.  It used interval-delta worklists and finalized-history
segment summaries.  It did not inspect identifier names or lengths, source text,
token count, machine identity, harness identity, or sample metadata.

## Correctness evidence before performance

- official 50: `50/50` in both protocols (`100/100` protocol runs)
- authoritative: `219/219`
- non-scale corpus: `364/364`
- candidate/control strict runs: protocol `728/728` each, safe prefix `238/238`
  each, input edge `26/26` each; zero transcript/first-reject/exit/stderr diff
- sanitizer production: official `100/100`; non-scale `364/364`, authoritative
  `219/219`, protocol/safe-prefix/edge `728/238/26`, zero failures
- fixed sanitizer fuzz: 144 generated cases, byte/random/line/cl100k/whole
  fragmentations, zero failures
- unittest `61/61`; native fragment `66 × 4`; native context `7/7`; official
  differential `50/50 + 45/45 + 57/57`
- old/new shadow: 6,900 source/layout runs, 2,070 rollback/Fork/reset runs and
  144 AcceptToken scenarios with zero strict diff
- fresh complete old/new dynamic shadow limit: 512-byte identifier.  No claim
  is made that the old matcher dynamically completed the 4 KiB interval.

## Pre-registered performance result

All values below are medians of the raw collector runs unless noted.

| Gate | Control | Candidate | Result |
|---|---:|---:|---|
| 4 KiB identifier, default | timeout at 30 s | 434.2 ms | target met |
| 4 KiB identifier, competition | timeout at 30 s | 436.3 ms | target met |
| 300 locals, default | 463.0 ms | 5,378.1 ms | **failed `<2 s`** |
| 300 locals, competition | 452.7 ms | 5,372.3 ms | **failed `<2 s`** |
| worst other-scale time ratio | — | 7.397× | **failed `≤1.10×`** |
| worst manifest-scale RSS ratio | — | 1.180× | met |
| locals-500 RSS ratio, competition | — | 1.272× | **failed `≤1.25×`** |

The worst other-scale timing was `two-hundred-crlf-lines` in the default
protocol: 241.4 ms control versus 1,785.5 ms candidate.  The candidate was
therefore classified **REJECTED** immediately after scale validation.  The
official-50 A/B/A performance run was intentionally not executed.

`scale_raw.json.gz` is the complete checkpointed 232-run collector output;
no trial was removed.  `scale_raw.stdout` preserves the schedule and
`scale_raw.stderr` is empty.
