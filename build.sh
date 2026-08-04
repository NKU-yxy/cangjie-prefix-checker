#!/usr/bin/env bash
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

run_quiet python3 -m pip install --user -q -r requirements.txt
run_quiet python3 -m pip install --user -q --no-deps "xgrammar==0.2.1"

python3 - <<'PY' >/dev/null
import tiktoken
import xgrammar

enc = tiktoken.get_encoding("cl100k_base")
enc.decode(enc.encode("warmup"))
PY

cat > solution <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export TVM_FFI_BUILD_DOCS=1
exec python3 solution.py "$@"
SH

chmod +x solution
