#!/usr/bin/env bash
# v4: hardened competition build.
#
# Runtime files (grammar/, generated/context.bin) are shipped in the submission
# itself, so this script only provisions derived artifacts and compiles the
# native checker. There are no hash pinning steps, no network accesses, and no
# hard failure paths except when no runnable solution can be produced at all
# (missing token table or missing toolchain with no fallback).

set -euo pipefail

cd "$(dirname "$0")"

run_quiet() {
  local log_file="/tmp/cangjie_build_$$.log"
  if ! "$@" >"${log_file}" 2>&1; then
    cat "${log_file}" >&2
    rm -f "${log_file}"
    return 1
  fi
  rm -f "${log_file}"
}

mkdir -p generated

# --- 1) token table (runtime: generated/cl100k_base.bin) -------------------
# The shipped assets/cl100k_base.bin.xz is self-contained; python3 is present on
# the judge because the interaction harness itself is a python script.
if [[ ! -s generated/cl100k_base.bin ]]; then
  if [[ -s assets/cl100k_base.bin.xz ]]; then
    run_quiet python3 -c \
      'import lzma, pathlib, sys; src = pathlib.Path(sys.argv[1]); dst = pathlib.Path(sys.argv[2]); dst.write_bytes(lzma.decompress(src.read_bytes()))' \
      assets/cl100k_base.bin.xz generated/cl100k_base.bin || true
  fi
fi
if [[ ! -s generated/cl100k_base.bin ]]; then
  echo "missing self-contained token table: generated/cl100k_base.bin" >&2
  exit 1
fi

# --- 2) context table (runtime: generated/context.bin) ---------------------
# The submission ships the correct generated/context.bin. If context.json and
# the generator are present, regenerate; on any failure keep the shipped one.
if [[ -s context.json && -s tools/generate_context_table.py ]]; then
  if run_quiet python3 tools/generate_context_table.py context.json generated/context.bin.tmp; then
    mv -f generated/context.bin.tmp generated/context.bin
  fi
fi
rm -f generated/context.bin.tmp
if [[ ! -s generated/context.bin ]]; then
  echo "missing context table: generated/context.bin" >&2
  exit 1
fi

# --- 3) compile the native checker -----------------------------------------
xgrammar_root="third_party/xgrammar_core"
xgrammar_sources=(
  "${xgrammar_root}/src/compiled_grammar.cc"
  "${xgrammar_root}/src/earley_parser.cc"
  "${xgrammar_root}/src/fsm.cc"
  "${xgrammar_root}/src/fsm_builder.cc"
  "${xgrammar_root}/src/grammar.cc"
  "${xgrammar_root}/src/grammar_builder.cc"
  "${xgrammar_root}/src/grammar_compiler.cc"
  "${xgrammar_root}/src/grammar_functor.cc"
  "${xgrammar_root}/src/grammar_matcher.cc"
  "${xgrammar_root}/src/grammar_parser.cc"
  "${xgrammar_root}/src/grammar_printer.cc"
  "${xgrammar_root}/src/json_schema_converter.cc"
  "${xgrammar_root}/src/json_schema_converter_ext.cc"
  "${xgrammar_root}/src/regex_converter.cc"
  "${xgrammar_root}/src/structural_tag.cc"
  "${xgrammar_root}/src/tokenizer_info.cc"
  "${xgrammar_root}/src/support/logging.cc"
  "${xgrammar_root}/src/support/recursion_guard.cc"
)

native_cxx="${CXX:-c++}"
native_compile_flags=("-std=c++17")
if [[ "${CANGJIE_PROFILE_BUILD:-0}" == "1" ]]; then
  native_compile_flags+=("-DCANGJIE_ENABLE_PROFILE=1")
fi
if [[ "${CANGJIE_REGEX_SHADOW_BUILD:-0}" == "1" ]]; then
  native_compile_flags+=("-DCANGJIE_ENABLE_REGEX_SHADOW=1")
fi
if [[ "${CANGJIE_GRAMMAR_SHADOW_BUILD:-0}" == "1" ]]; then
  native_compile_flags+=("-DCANGJIE_ENABLE_GRAMMAR_SHADOW=1")
fi

run_quiet "${native_cxx}" \
  -O3 -DNDEBUG -Wall -Wextra -pthread \
  -ffunction-sections -fdata-sections \
  -DXGRAMMAR_ENABLE_CPPTRACE=0 \
  -DXGRAMMAR_ENABLE_INTERNAL_CHECK=0 \
  "${native_compile_flags[@]}" \
  -I"${xgrammar_root}/include" \
  -I"${xgrammar_root}/src" \
  -I"${xgrammar_root}/third_party/picojson" \
  -I"${xgrammar_root}/third_party/dlpack" \
  cpp/solution.cpp \
  cpp/native_semantic.cpp \
  cpp/call_frontier.cpp \
  cpp/continuation.cpp \
  "${xgrammar_sources[@]}" \
  -Wl,--gc-sections -ldl \
  -o solution

# strip is a nicety, not a requirement
strip --strip-unneeded solution 2>/dev/null || true
chmod +x solution
