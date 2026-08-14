#!/usr/bin/env bash
# lca-host.sh — thin wrapper around lca-host.py
# Usage: scripts/lca-host.sh provision sandbox-user
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run python3 "${ROOT}/scripts/lca-host.py" "$@"
