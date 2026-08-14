# G1 accepted-control integration smoke

This directory records the post-integration smoke run for local commit
`f5f2468c343e7ccc18d48cba0eab0a10920ee1c6` in the locked official Linux
AArch64 image.

The integration commit is the inverse of the earlier G1 revert and restores
the exact grammar and manifest bytes independently audited at candidate
`499c9c787fdbd8140307c5b5f472e9aee0c9342c`.

Results:

- build: PASS, ELF64 AArch64;
- unit tests: `61/61`;
- comprehensive generation check: PASS, `373` current cases;
- official exact-first-error smoke: `50/50`, one fresh-process trial per case;
- non-scale comprehensive: `364/364`;
- authoritative: `219/219`;
- protocol/safe-prefix/input-edge runs: `728/238/26`;
- 300 locals: both protocols completed all `3310` responses with exit code 0,
  empty stderr, and no two-second timeout.

This is an integration-binding smoke, not a replacement for the independent
provenance-bound A/B/A or its full sanitizer/shadow evidence. Those artifacts
are stored in the parent directory. An earlier attempt in a separate temporary
clone stopped immediately after a successful build because the official image
does not contain the optional `file` utility; it entered no correctness test
and is excluded from this valid result. The valid rerun used `readelf`.
