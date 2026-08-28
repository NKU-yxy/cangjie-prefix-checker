#!/usr/bin/env bash
# v4: hardened competition build.
#
# The submission contains all source inputs needed to generate its runtime
# tables and compile the native checker. There are no network accesses; failure
# means a required source input or toolchain is unavailable.

set -euo pipefail

cd "$(dirname "$0")"

# 静默执行构建命令：成功时不输出，失败时打印完整日志并返回失败
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

# The native semantic engine is split across the sources listed here. Tests and
# benchmarks read the same manifest through tools/native_build.py, so adding a
# new implementation file only requires updating one list.
native_source_manifest="cpp/native_semantic_sources.txt"
if [[ ! -s "${native_source_manifest}" ]]; then
  echo "missing native source manifest: ${native_source_manifest}" >&2
  exit 1
fi
native_semantic_sources=()
while IFS= read -r native_source || [[ -n "${native_source}" ]]; do
  [[ -z "${native_source}" || "${native_source}" == \#* ]] && continue
  if [[ ! -f "${native_source}" ]]; then
    echo "native source manifest references missing file: ${native_source}" >&2
    exit 1
  fi
  native_semantic_sources+=("${native_source}")
done < "${native_source_manifest}"
if [[ ${#native_semantic_sources[@]} -eq 0 ]]; then
  echo "native source manifest is empty: ${native_source_manifest}" >&2
  exit 1
fi

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
# Generate the context table from the submitted final context definition.
if [[ ! -s context.json || ! -s tools/generate_context_table.py ]]; then
  echo "missing context.json or tools/generate_context_table.py" >&2
  exit 1
fi
run_quiet python3 tools/generate_context_table.py context.json generated/context.bin.tmp
mv -f generated/context.bin.tmp generated/context.bin

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
native_link_flags=()
case "$(uname -s)" in
  Linux)
    native_link_flags+=("-Wl,--gc-sections" "-ldl")
    ;;
  Darwin)
    native_link_flags+=("-Wl,-dead_strip")
    ;;
  *)
    echo "unsupported build host: $(uname -s)" >&2
    exit 1
    ;;
esac
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
  "${native_semantic_sources[@]}" \
  "${xgrammar_sources[@]}" \
  "${native_link_flags[@]}" \
  -o solution

# strip is a nicety, not a requirement
strip --strip-unneeded solution 2>/dev/null || true
chmod +x solution
