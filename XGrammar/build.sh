#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export TVM_FFI_BUILD_DOCS=1

if ! python3 -m pip --version >/dev/null 2>&1; then
  python3 -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '/tmp/get-pip.py')"
  python3 /tmp/get-pip.py --user
fi

python3 -m pip install --user -r requirements.txt
python3 -m pip install --user --no-deps "xgrammar==0.2.1"

python3 - <<'PY'
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
