# 735a52e Linux AArch64 correctness gate

- Candidate: `735a52e20671930f7e956401d39d5ca1c69d3ec9`
- Direct-parent control: `68d780d54c25883b4e05c3f3562b315750b38af0`
- Image: `docker.educg.net/compiler_system_challenge/cjchecker:20260522`
- Image digest: `sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90`
- Runtime: Linux AArch64, 10 CPUs, 8,126,480 KiB MemTotal
- Compiler: GCC 11.4.0
- Candidate production solution SHA-256: `a54c466d4d50466d9f611f746935e1a32e7172d92ce1f532b5cd63793688fb45`
- Control production solution SHA-256: `5d9b87076929726411a65d93e5fe1988a71f41ebbcf541c52843f1397c4c4110`
- Candidate shadow solution SHA-256: `93174dfca70b40d4eafc1d55e828bd5602349dea3504f5a064adbf52d059ffad`
- Candidate ASan/UBSan + shadow solution SHA-256: `353bace2a394323d0ccf92517d63a490341bb2d89dc61c3db6290d5688e29cff`

## Locked input checks

- `context.json`: `8058e383390f444f56ee4ac0008493c44c8e32fa632d18ed48f998dc36623348`
- `grammar/cangjie.gbnf`: `6131041ed52120b65ee75440c97704dfe91d1a0fda0aaf99b3e1c75e3054f989`
- `grammar/cangjie_token.gbnf`: `cbe033bea0b88c4d042e258cb4a9b79dfe0912072dc6b5468f742c5d57d6dae0`
- `build.sh`: `f3232ef08d4fde32c0f9670e8d658234d7a96ba1411c0ad676d96ca0626f85e6`
- comprehensive manifest: `e0af56059f58f8f5d99fc9c1d243c75ed9df9670f2057b20421292dc48782496`
- comprehensive generator: `3ba41564238358e487e72cf40678aef8606921a26da14b30a2ba4ed6ddc51c4a`
- comprehensive runner: `d04f1df184b095996503f004598b6b99d42d414f94a410710e81ff8ac125b55e`
- official first-error registry: `2425e64184d69dd392f6cdec52dc20d42d0977cbe84be744a0ffbd1dfad374f2`
- official sample commit: `88336c400e7a4a671424e3e6c46c0866c8c0af93`

## Production build and gates

- Default ELF: ELF64 AArch64 PIE.
- Default strings: zero `CANGJIE_PROFILE`, zero `CANGJIE_PHASE_PROFILE`, zero regex-shadow divergence messages.
- Unit tests: 57/57 passed after installing the repository's Python test dependencies. The initial container-only run lacked `lark`/`pydantic`; that was an environment setup error and the full suite was rerun from the beginning.
- Native fragment differential: 66/66 cases x byte/random/cl100k/whole passed.
- Native context differential: 7/7 passed.
- Hidden semantic fuzz, seed 20260805: 144 cases x byte/random/line/cl100k/whole, zero failures.
- Official exact first-error: 50/50.
- Vendored oracle corpus: 45/45.
- Project corpus: 57/57.
- Deterministic comprehensive generation check: 373 current.
- Non-scale comprehensive: 364/364, authoritative 219/219, infrastructure failures 0.
- Strict candidate/control reference equality: 728 protocol runs, 238 safe-prefix runs, and 26 input-edge runs on each side; transcripts, first rejection, exit code, stderr, exceptions, and timeouts matched exactly.
- Scale diagnostic: 9/9 executed with zero infrastructure failures; two pre-existing diagnostics remained: `four-kilobyte-identifier` and `three-hundred-local-declarations`, both timing out at 30 s in both protocols. Scale diagnostics are not hard-gate failures.

## Independent legacy-regex shadow

- Shadow full solution: profile markers 0, shadow divergence markers 7.
- Unit tests: 57/57.
- Native fragment differential using prebuilt shadow driver: 66/66 x 4.
- Native context differential using prebuilt shadow driver: 7/7.
- Hidden fuzz: 144 x 5, zero failures.
- Official/oracle/project: 50/50, 45/45, 57/57.
- Comprehensive strict reference diff: 364/364, authoritative 219/219, zero infrastructure failures; 728 protocol + 238 safe-prefix + 26 edge runs matched the parent control.
- No declaration record, Model, FunctionContext, or semantic CheckStatus shadow assertion fired.

## ASan/UBSan plus legacy-regex shadow

- Full solution and native driver were built with `-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -DCANGJIE_ENABLE_REGEX_SHADOW=1`.
- Runtime options: `ASAN_OPTIONS=detect_leaks=1:halt_on_error=1:abort_on_error=1:strict_string_checks=1`; `UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`.
- Native fragment differential: 66/66 x 4 passed.
- Native context differential: 7/7 passed.
- Hidden fuzz: 144 x 5 plus full protocol solution, zero failures.
- Official/oracle/project: 50/50, 45/45, 57/57.
- Comprehensive non-scale: 364/364, authoritative 219/219, 728 protocol + 238 safe-prefix + 26 edge runs, zero infrastructure failures.
- No ASan, LeakSanitizer, UBSan, or shadow assertion report occurred.
- Three `-Wrange-loop-construct` warnings in the sanitizer diagnostic build are inherited warnings also present in the prior control's sanitizer log; the default production `build.sh` was warning-free.

## Test-layout notes

- One attempted sanitizer fuzz run used the full solution from `/gate/logs`, so its executable-relative `generated/` resource directory was absent. It was stopped and excluded. The identical binary was copied next to the candidate resources and the complete 144 x 5 run was restarted from case 1 and passed. No source was changed.
- No performance benchmark was run by this gate task.

Conclusion: **PASS — candidate is eligible to proceed to the separate formal A/B/A performance gate.**
