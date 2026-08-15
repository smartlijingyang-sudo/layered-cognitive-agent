#!/usr/bin/env bash
# Install DSH SDK into the shared LCA venv (sandbox-user side).
# The runner script uses this venv's python3 via daemon's buildExecEnv().
#
# Usage:
#   ./deploy/dsh/install-dsh-sdk.sh
#   VENV_DIR=/opt/lca/venv ./deploy/dsh/install-dsh-sdk.sh
set -euo pipefail

VENV_DIR="${VENV_DIR:-/opt/lca/venv}"
REQUIREMENTS="$(cd "$(dirname "$0")" && pwd)/requirements-dsh.txt"

if [ ! -f "${REQUIREMENTS}" ]; then
  echo "ERROR: ${REQUIREMENTS} not found" >&2
  exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "ERROR: venv not found at ${VENV_DIR}" >&2
  echo "       Run ./scripts/lca-ops provision first." >&2
  exit 1
fi

PYTHON="${VENV_DIR}/bin/python3"
if [ ! -x "${PYTHON}" ]; then
  echo "ERROR: ${PYTHON} not found or not executable" >&2
  exit 1
fi

echo "==> Installing DSH SDK into ${VENV_DIR}"
if command -v uv &>/dev/null; then
  uv pip install --python "${PYTHON}" -r "${REQUIREMENTS}"
else
  "${PYTHON}" -m pip install -r "${REQUIREMENTS}"
fi

echo "==> Verifying import"
"${PYTHON}" -c "from deepseek_harness import DeepSeekHarness; print('  DSH SDK: ok')"

echo "==> Done. DSH runner will use this venv via daemon's buildExecEnv()."
