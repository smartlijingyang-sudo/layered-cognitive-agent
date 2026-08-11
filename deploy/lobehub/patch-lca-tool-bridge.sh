#!/usr/bin/env bash
# LCA tool wire + lca.events SSE → LobeHub tool UI + Mode A closed-loop.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "${ROOT}/deploy/lobehub/patch-lca-integration.py"
