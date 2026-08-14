#!/usr/bin/env bash
# lobehub-stack — thin wrapper. Implementation: deploy/lobehub/stack/
# Config: deploy/lobehub/stack.yaml
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
if command -v uv >/dev/null 2>&1; then
  exec uv run python3 "${ROOT}/scripts/lobehub-stack.py" "$@"
fi
exec python3 "${ROOT}/scripts/lobehub-stack.py" "$@"
