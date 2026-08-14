#!/usr/bin/env bash
# Compatibility wrapper. Host runtime SSOT is lca-host.yaml.
# Prefer: uv run python scripts/lca-host.py provision <user>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="${1:-sandbox-user}"
exec uv run python3 "${ROOT}/scripts/lca-host.py" provision "${USER_NAME}"
