#!/usr/bin/env bash
# Install the lightweight Python dependency set used by this repository.

set -euo pipefail

cd "$(dirname "$0")/.."

python_command="${PYTHON:-python3}"

# Install ordinary dependencies with their declared transitive requirements.
"${python_command}" -m pip install "$@" -r requirements-base.txt

# Upstream XGrammar declares Torch/Transformers for optional integrations. This
# project uses RAW TokenizerInfo only and supplies lightweight compatibility
# modules at the repository root, so those large ML packages are unnecessary.
"${python_command}" -m pip install "$@" --no-deps -r requirements-xgrammar.txt
