#!/usr/bin/env bash
# This team-authored build script installs and links external dependencies.
# Third-party source code is not vendored into the production submission.
# See THIRD_PARTY_NOTICES.md.

set -euo pipefail

cd "$(dirname "$0")"
export TVM_FFI_BUILD_DOCS=1
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

if ! python3 - <<'PY' >/dev/null 2>&1
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
  run_quiet python3 -m pip install --user -q "apache-tvm-ffi>=0.1.9"
  run_quiet python3 -m pip install --user -q --no-deps "xgrammar==0.2.1"
fi

run_quiet python3 tools/generate_cl100k_table.py generated/cl100k_base.bin
run_quiet python3 tools/generate_context_table.py context.json generated/context.bin
native_xgrammar_dir="$(python3 -c 'from importlib.util import find_spec; print(next(iter(find_spec("xgrammar").submodule_search_locations)))')"
native_tvm_ffi_dir="$(python3 -c 'from importlib.util import find_spec; print(next(iter(find_spec("tvm_ffi").submodule_search_locations)))')"
native_xgrammar_shared="$(python3 -c 'from importlib.util import find_spec; from pathlib import Path; root=Path(next(iter(find_spec("xgrammar").submodule_search_locations))); print(next(path for path in root.glob("libxgrammar_bindings.*") if path.suffix in {".so", ".dylib"}))')"
native_cxx="${CXX:-c++}"
native_profile_flags=()
if [[ "${CANGJIE_PROFILE_BUILD:-0}" == "1" ]]; then
  native_profile_flags+=("-DCANGJIE_ENABLE_PROFILE=1")
fi
native_platform_flags=(
  "-Wl,-rpath,${native_xgrammar_dir}"
  "-Wl,-rpath,${native_tvm_ffi_dir}/lib"
)
if [[ "$(uname -s)" == "Linux" ]]; then
  # DT_RPATH is inherited by transitive dependencies.  XGrammar itself needs
  # libtvm_ffi.so, while DT_RUNPATH would only be searched for direct deps.
  native_platform_flags+=("-Wl,--disable-new-dtags")
fi

run_quiet "${native_cxx}" \
  -std=c++17 -O3 -DNDEBUG -Wall -Wextra -pedantic -pthread \
  "${native_profile_flags[@]}" \
  -I"${native_xgrammar_dir}/include" \
  cpp/solution.cpp \
  cpp/native_semantic.cpp \
  "${native_xgrammar_shared}" \
  -L"${native_tvm_ffi_dir}/lib" -ltvm_ffi -ldl \
  "${native_platform_flags[@]}" \
  -o solution

chmod +x solution
