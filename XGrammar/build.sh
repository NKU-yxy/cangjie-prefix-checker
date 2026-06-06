#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! python3 -m pip --version >/dev/null 2>&1; then
  python3 - <<'PY'
import urllib.request

urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", "/tmp/get-pip.py")
PY
  python3 /tmp/get-pip.py --user
fi

python3 -m pip install --user --upgrade pip
python3 -m pip install --user -r requirements.txt

python3 - <<'PY'
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")
enc.decode(enc.encode("warmup"))
PY

rm -rf build dist solution.spec

python3 -m PyInstaller \
  --clean \
  --onefile \
  --name solution \
  --add-data "grammar/cangjie_token.gbnf:grammar" \
  --collect-all xgrammar \
  --collect-all tiktoken \
  --hidden-import tiktoken_ext.openai_public \
  solution.py

cp dist/solution ./solution
chmod +x ./solution
