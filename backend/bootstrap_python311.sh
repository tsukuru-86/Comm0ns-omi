#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
VENV_DIR="${VENV_DIR:-.venv311}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Missing ${PYTHON_BIN}. Install Python 3.11 first." >&2
    exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/pip" install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.template .env
    echo "Created .env from .env.template"
fi

echo "Bootstrap complete"
echo "  Python: $(${VENV_DIR}/bin/python --version)"
echo "  Venv:   ${VENV_DIR}"
echo "Next: bash start_local.sh"
