#!/usr/bin/env bash
# Build the native checker and the namespace-isolated, vendored XGrammar core.
# The unmodified XGrammar wheel/TVM FFI pair is needed only when the explicit
# old/new grammar shadow build is requested.  See THIRD_PARTY_NOTICES.md.

set -euo pipefail

cd "$(dirname "$0")"
export PIP_PROGRESS_BAR=off

run_quiet() {
  local log_file="/tmp/xgrammar_build_$$.log"
  if ! "$@" >"${log_file}" 2>&1; then
    cat "${log_file}" >&2
    rm -f "${log_file}"
    return 1
  fi
  rm -f "${log_file}"
}

if ! python3 -m pip --version >/dev/null 2>&1; then
  run_quiet python3 -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '/tmp/get-pip.py')"
  run_quiet python3 /tmp/get-pip.py --user
fi

if ! python3 -c 'import tiktoken' >/dev/null 2>&1; then
  run_quiet python3 -m pip install --user -q "tiktoken>=0.7.0"
fi

if [[ "${CANGJIE_GRAMMAR_SHADOW_BUILD:-0}" == "1" ]] && ! python3 - <<'PY' >/dev/null 2>&1
from importlib.util import find_spec
from pathlib import Path

xgrammar = find_spec("xgrammar")
tvm_ffi = find_spec("tvm_ffi")
assert xgrammar and xgrammar.submodule_search_locations
assert tvm_ffi and tvm_ffi.submodule_search_locations
root = Path(next(iter(xgrammar.submodule_search_locations)))
assert (root / "include" / "xgrammar" / "xgrammar.h").is_file()
assert any(
    path.suffix in {".so", ".dylib"}
    for path in root.glob("libxgrammar_bindings.*")
)
PY
then
  export TVM_FFI_BUILD_DOCS=1
  run_quiet python3 -m pip install --user -q "apache-tvm-ffi>=0.1.9"
  run_quiet python3 -m pip install --user -q --no-deps "xgrammar==0.2.1"
fi

run_quiet python3 tools/generate_cl100k_table.py generated/cl100k_base.bin
run_quiet python3 tools/generate_context_table.py context.json generated/context.bin

native_cxx="${CXX:-c++}"
native_ar="${AR:-ar}"
vendor_root="vendor/xgrammar-v0.2.1"

required_vendor_files=(
  "${vendor_root}/LICENSE"
  "${vendor_root}/NOTICE"
  "${vendor_root}/cpp/earley_parser.cc"
  "${vendor_root}/cpp/earley_parser.h"
  "${vendor_root}/cpp/grammar_matcher.cc"
  "${vendor_root}/include/xgrammar/xgrammar.h"
  "${vendor_root}/3rdparty/picojson/picojson.h"
  "${vendor_root}/3rdparty/dlpack/include/dlpack/dlpack.h"
)
for required_vendor_file in "${required_vendor_files[@]}"; do
  if [[ ! -f "${required_vendor_file}" ]]; then
    echo "missing vendored XGrammar file: ${required_vendor_file}" >&2
    exit 1
  fi
done

native_build_dir="$(mktemp -d "${TMPDIR:-/tmp}/cangjie-g4-build.XXXXXX")"
cleanup_native_build() {
  if [[ -n "${native_build_dir:-}" && -d "${native_build_dir}" ]]; then
    rm -rf -- "${native_build_dir}"
  fi
}
trap cleanup_native_build EXIT

native_compile_flags=("-std=c++17")
if [[ "${CANGJIE_SANITIZER_BUILD:-0}" == "1" ]]; then
  native_compile_flags+=(
    "-O1" "-g" "-fno-omit-frame-pointer" "-fno-optimize-sibling-calls"
    "-fsanitize=address,undefined" "-fno-sanitize-recover=all"
  )
else
  native_compile_flags+=("-O3" "-DNDEBUG")
fi

native_project_defines=()
if [[ "${CANGJIE_PROFILE_BUILD:-0}" == "1" ]]; then
  native_project_defines+=("-DCANGJIE_ENABLE_PROFILE=1")
fi
if [[ "${CANGJIE_REGEX_SHADOW_BUILD:-0}" == "1" ]]; then
  native_project_defines+=("-DCANGJIE_ENABLE_REGEX_SHADOW=1")
fi
if [[ "${CANGJIE_GRAMMAR_SHADOW_BUILD:-0}" == "1" ]]; then
  native_project_defines+=("-DCANGJIE_ENABLE_GRAMMAR_SHADOW=1")
fi

vendor_sources=(
  "${vendor_root}/cpp/compiled_grammar.cc"
  "${vendor_root}/cpp/config.cc"
  "${vendor_root}/cpp/earley_parser.cc"
  "${vendor_root}/cpp/fsm.cc"
  "${vendor_root}/cpp/fsm_builder.cc"
  "${vendor_root}/cpp/grammar.cc"
  "${vendor_root}/cpp/grammar_builder.cc"
  "${vendor_root}/cpp/grammar_compiler.cc"
  "${vendor_root}/cpp/grammar_functor.cc"
  "${vendor_root}/cpp/grammar_matcher.cc"
  "${vendor_root}/cpp/grammar_parser.cc"
  "${vendor_root}/cpp/grammar_printer.cc"
  "${vendor_root}/cpp/json_schema_converter.cc"
  "${vendor_root}/cpp/json_schema_converter_ext.cc"
  "${vendor_root}/cpp/regex_converter.cc"
  "${vendor_root}/cpp/structural_tag.cc"
  "${vendor_root}/cpp/support/logging.cc"
  "${vendor_root}/cpp/support/recursion_guard.cc"
  "${vendor_root}/cpp/testing.cc"
  "${vendor_root}/cpp/tokenizer_info.cc"
)

vendor_include_flags=(
  "-I${vendor_root}/include"
  "-I${vendor_root}/cpp"
  "-I${vendor_root}/3rdparty/picojson"
  "-I${vendor_root}/3rdparty/dlpack/include"
)
vendor_objects=()
vendor_index=0
for vendor_source in "${vendor_sources[@]}"; do
  vendor_object="${native_build_dir}/xgrammar_g4_${vendor_index}.o"
  run_quiet "${native_cxx}" \
    "${native_compile_flags[@]}" \
    -pthread \
    -DXGRAMMAR_ENABLE_CPPTRACE=0 \
    -DXGRAMMAR_ENABLE_INTERNAL_CHECK=0 \
    -Dxgrammar=xgrammar_g4 \
    "${vendor_include_flags[@]}" \
    -c "${vendor_source}" \
    -o "${vendor_object}"
  vendor_objects+=("${vendor_object}")
  vendor_index=$((vendor_index + 1))
done

vendor_archive="${native_build_dir}/libxgrammar_g4.a"
run_quiet "${native_ar}" rcs "${vendor_archive}" "${vendor_objects[@]}"

native_shadow_link_inputs=()
native_platform_flags=()
native_system_libraries=()
if [[ "$(uname -s)" == "Linux" ]]; then
  native_system_libraries+=("-ldl")
fi
if [[ "${CANGJIE_GRAMMAR_SHADOW_BUILD:-0}" == "1" ]]; then
  native_xgrammar_dir="$(python3 -c 'from importlib.util import find_spec; print(next(iter(find_spec("xgrammar").submodule_search_locations)))')"
  native_tvm_ffi_dir="$(python3 -c 'from importlib.util import find_spec; print(next(iter(find_spec("tvm_ffi").submodule_search_locations)))')"
  native_xgrammar_shared="$(python3 -c 'from importlib.util import find_spec; from pathlib import Path; root=Path(next(iter(find_spec("xgrammar").submodule_search_locations))); print(next(path for path in root.glob("libxgrammar_bindings.*") if path.suffix in {".so", ".dylib"}))')"
  native_shadow_link_inputs+=(
    "${native_xgrammar_shared}"
    "-L${native_tvm_ffi_dir}/lib"
    "-ltvm_ffi"
  )
  native_platform_flags+=(
    "-Wl,-rpath,${native_xgrammar_dir}"
    "-Wl,-rpath,${native_tvm_ffi_dir}/lib"
  )
  if [[ "$(uname -s)" == "Linux" ]]; then
    # DT_RPATH is inherited by the legacy shadow DSO's TVM FFI dependency.
    native_platform_flags+=("-Wl,--disable-new-dtags")
  fi
fi

run_quiet "${native_cxx}" \
  "${native_compile_flags[@]}" \
  -Wall -Wextra -pedantic -pthread \
  "${native_project_defines[@]}" \
  "${vendor_include_flags[@]}" \
  cpp/solution.cpp \
  cpp/g4_syntax.cc \
  cpp/native_semantic.cpp \
  "${vendor_archive}" \
  "${native_shadow_link_inputs[@]}" \
  "${native_system_libraries[@]}" \
  "${native_platform_flags[@]}" \
  -o solution

chmod +x solution
