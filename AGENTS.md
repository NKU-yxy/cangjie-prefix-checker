# Repository Instructions

## Performance optimization and benchmarking

Before changing performance-sensitive code or running any benchmark, read and follow
[`OPTIMIZATION_TESTING_CONTRACT.md`](OPTIMIZATION_TESTING_CONTRACT.md) in full.

The contract is mandatory. In particular:

- build and test in the locked official Linux AArch64 Docker image;
- preserve exact first-error behavior and pass all 50 official public samples;
- do not change official samples, answer positions, context, grammar, or timing boundaries;
- do not use Apple-specific CPU flags, `-march=native`, host-specific APIs, or sample-specific shortcuts;
- use the prescribed warmups, repetitions, seed, fresh-process protocol, and A/B/A control procedure;
- retain every trial and archive reports under `baseline_results/` without overwriting prior results;
- classify results using the contract's `ACCEPTED`, `PROVISIONAL`, `NO PROVEN GAIN`,
  `REJECTED`, or `INVALID` rules;
- never describe a change as an optimization unless it passes the contract.

Correctness failures take precedence over all performance measurements.
