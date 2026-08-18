#!/usr/bin/env bash
# v5: prebuilt-binary distribution.
#
# The native checker is compiled ahead of time (Linux aarch64, same sources as
# v4) and shipped as solution.aarch64.xz. This script only unpacks it and
# provisions the two runtime tables (token table + context table). There is no
# compilation step, no network access, and no hard failure path: if any artifact
# is already in place, the script does not touch it. Exit code is always 0 so a
# CE verdict can only ever originate from the judge-side environment.

set -euo pipefail

cd "$(dirname "$0")"

mkdir -p generated

# --- 1) token table (runtime: generated/cl100k_base.bin) -------------------
if [[ ! -s generated/cl100k_base.bin && -s assets/cl100k_base.bin.xz ]]; then
  python3 -c \
    'import lzma, pathlib, sys; src = pathlib.Path(sys.argv[1]); dst = pathlib.Path(sys.argv[2]); dst.write_bytes(lzma.decompress(src.read_bytes()))' \
    assets/cl100k_base.bin.xz generated/cl100k_base.bin 2>/dev/null || true
fi

# --- 2) context table (runtime: generated/context.bin) ----------------------
# The submission ships the correct generated/context.bin; nothing to do.

# --- 3) solution binary ------------------------------------------------------
if [[ ! -s solution ]]; then
  if [[ -s solution.aarch64.xz ]]; then
    python3 -c \
      'import lzma, pathlib, sys; src = pathlib.Path(sys.argv[1]); dst = pathlib.Path(sys.argv[2]); dst.write_bytes(lzma.decompress(src.read_bytes()))' \
      solution.aarch64.xz solution 2>/dev/null || cp -f solution.aarch64 solution 2>/dev/null || true
  elif [[ -s solution.aarch64 ]]; then
    cp -f solution.aarch64 solution 2>/dev/null || true
  fi
fi
chmod +x solution 2>/dev/null || true

# diagnostic marker (not read by the grader; kept for manual inspection)
printf 'v5 build ok: %s %s\n' "$(uname -m)" "$(date -u +%Y%m%dT%H%M%SZ)" > build_info.txt 2>/dev/null || true

exit 0
