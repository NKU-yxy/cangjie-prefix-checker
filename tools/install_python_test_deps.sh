#!/usr/bin/env bash
# Install the Python dependency set used by this repository.

set -euo pipefail

cd "$(dirname "$0")/.."

python_command="${PYTHON:-python3}"

# requirements.txt is the repository's only Python dependency manifest.
"${python_command}" -m pip install "$@" -r requirements.txt
