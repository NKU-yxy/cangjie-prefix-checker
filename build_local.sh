#!/usr/bin/env bash
# Team-authored competition build. XGrammar's disclosed Apache-2.0 C++ core
# is compiled from the source included in this submission. No package index or
# network access is used.

set -euo pipefail

cd "$(dirname "$0")"

run_quiet() {
  local log_file="/tmp/xgrammar_build_$$.log"
  if ! "$@" >"${log_file}" 2>&1; then
    cat "${log_file}" >&2
    rm -f "${log_file}"
    return 1
  fi
  rm -f "${log_file}"
}

verify_sha256() {
  local expected="$1"
  local file="$2"
  local actual
  if [[ ! -s "${file}" ]]; then
    echo "missing required submission file: ${file}" >&2
    exit 1
  fi
  actual="$(sha256sum "${file}")"
  actual="${actual%% *}"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "submission file hash mismatch: ${file}" >&2
    exit 1
  fi
}

verify_sha256 \
  "facb628ab01a52d7ef8f2fe36ca463ccd381e02e45282c82803b793730068303" \
  "context.json"

token_table_archive="assets/cl100k_base.bin.xz"
if [[ ! -s generated/cl100k_base.bin ]]; then
  if [[ -s "${token_table_archive}" ]]; then
    verify_sha256 \
      "91f5569da2fafd5a456261be7ed74fbe9db7bdd43bd22b2c040b0ff3fbb7fd73" \
      "${token_table_archive}"
    run_quiet python3 -c \
      'import lzma, pathlib, sys; source = pathlib.Path(sys.argv[1]); target = pathlib.Path(sys.argv[2]); target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(lzma.decompress(source.read_bytes()))' \
      "${token_table_archive}" generated/cl100k_base.bin
  else
    if ! python3 -c 'import tiktoken' >/dev/null 2>&1; then
      echo "missing self-contained token table and grader tiktoken" >&2
      exit 1
    fi
    cache_key="9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
    if [[ -z "${TIKTOKEN_CACHE_DIR:-}" ]]; then
      cache_candidates=(
        "/opt/cangjie-fragment-checker-finals/tiktoken_cache"
        "/opt/cangjie-fragment-checker/tiktoken_cache"
        "/coursegrader/testdata/tiktoken_cache"
        "/coursegrader/tiktoken_cache"
        "${PWD}/tiktoken_cache"
      )
      for cache_candidate in "${cache_candidates[@]}"; do
        if [[ -s "${cache_candidate}/${cache_key}" ]]; then
          export TIKTOKEN_CACHE_DIR="${cache_candidate}"
          break
        fi
      done
    fi
    run_quiet python3 tools/generate_cl100k_table.py generated/cl100k_base.bin
  fi
fi
verify_sha256 \
  "308b0361bc24138a3ba3b3659cc09083f2d8fcd5dcd080a407b499e97cc2fd34" \
  "generated/cl100k_base.bin"

if [[ ! -s generated/context.bin ]]; then
  run_quiet python3 tools/generate_context_table.py context.json generated/context.bin
fi
verify_sha256 \
  "2cf015b7f60f4d6fbb89a805e4d11daeaae0e70061f6a5813c94dcf0586ec113" \
  "generated/context.bin"

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
  "${xgrammar_sources[@]}" \
  -Wl,-dead_strip -ldl \
  -o solution

strip --strip-unneeded solution
chmod +x solution
