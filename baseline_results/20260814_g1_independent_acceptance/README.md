# G1 independent acceptance evidence

This directory archives the independent Linux AArch64 acceptance of G1 as a
**statement-list scale robustness** optimization.

- Control: `68d780d54c25883b4e05c3f3562b315750b38af0`
- Audited candidate: `499c9c787fdbd8140307c5b5f472e9aee0c9342c`
- Final verdict: `STATEMENT-LIST SCALE ROBUSTNESS ACCEPTED`
- Independent report SHA-256:
  `19ba3dad0518739860a343ebdba1fb64e1eed15e4f6dd2afe724d881bf79bbc2`

The earlier development verdict remains historically correct for its broader
combined target: G1 solves the large statement-list problem but does not solve
the 4 KiB identifier timeout. This independent acceptance is deliberately
limited to statement-list robustness and includes a strict non-regression gate
for the unresolved identifier case.

## Archived scope

The archive keeps the readable signed report, the provenance-bound A/B/A raw
trials, correctness/reference/shadow/sanitizer results, scale raw trials,
environment records, anti-cheat evidence, and the analysis scripts needed to
recompute the summaries. Setup-invalid and provenance-invalid early attempts,
temporary clones, ELF files, and duplicate media are intentionally excluded.

Four very large JSON files are stored using deterministic `gzip -n`. Their
SHA-256 values after decompression are:

| Compressed file | Decompressed SHA-256 |
|---|---|
| `evidence/results/scale_locals.json.gz` | `b31676b781b5c117e1530e8286d949b2ff42487284012e84011ea4e64a3ec12b` |
| `evidence/results/scale_profile_locals.json.gz` | `498344b36ca00f3646a3faf8ca98a14d5e28c7d6d9d872d55218c4dc9e637206` |
| `evidence/results/scale_other.json.gz` | `2a0c8f5ee6cbc7609739b5b4250cb27f0aff4763098a1298d2decc00e62f5620` |
| `evidence/results/strict_official.json.gz` | `6c9193bd588a57dbde130203f5f89c9688ac3c0527e9d9325f2a9762c13f2178` |

Verify the stored files with:

```bash
cd baseline_results/20260814_g1_independent_acceptance
shasum -a 256 -c SHA256SUMS
gzip -cd evidence/results/scale_locals.json.gz | shasum -a 256
gzip -cd evidence/results/scale_profile_locals.json.gz | shasum -a 256
gzip -cd evidence/results/scale_other.json.gz | shasum -a 256
gzip -cd evidence/results/strict_official.json.gz | shasum -a 256
```

The official 50 A/B/A improvement (`3.896%` SUM) is a protection result, not a
claim that G1 met the ordinary `>=5%` official-50 performance gate. G1 was
accepted under the contract's predeclared directed-optimization rule because
300 locals improved from a 35-second timeout to about 0.45 seconds while the
official 50 and all correctness gates remained protected.

After the independent verdict, G1 was integrated into local commit
`f5f2468c343e7ccc18d48cba0eab0a10920ee1c6`. The post-integration AArch64
binding smoke is archived under [`integration_smoke_f5f2468/`](integration_smoke_f5f2468/).
