#!/usr/bin/env bash
# Build / refresh the Onlyboxes terminalExec runtime used by LCA + LobeHub.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_TAG="${ONLYBOXES_TERMINAL_IMAGE:-onlyboxes-terminal-local:lca}"

echo "==> Building terminal runtime ${IMAGE_TAG}"
docker build \
  -f "${ROOT}/deploy/onlyboxes/Dockerfile.terminal" \
  -t "${IMAGE_TAG}" \
  "${ROOT}/deploy/onlyboxes"

echo "==> Smoke test (reportlab + pandas)"
docker run --rm "${IMAGE_TAG}" python3 -c \
  "import reportlab,pandas,numpy,openpyxl; print('ok', reportlab.Version, pandas.__version__)"

echo "==> Done. Set worker env:"
echo "    WORKER_TERMINAL_EXEC_DOCKER_IMAGE=${IMAGE_TAG}"
echo "    sudo systemctl restart onlyboxes-worker-docker"
