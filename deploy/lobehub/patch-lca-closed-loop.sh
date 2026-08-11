#!/usr/bin/env bash
# LCA Mode A closed-loop — alias for patch-lca-integration.py (tool bridge includes closed-loop).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "${ROOT}/deploy/lobehub/patch-lca-integration.py"
