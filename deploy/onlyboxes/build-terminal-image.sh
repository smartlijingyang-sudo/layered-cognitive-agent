#!/usr/bin/env bash
# Build / refresh the Onlyboxes terminalExec runtime used by LCA + LobeHub.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_TAG="${ONLYBOXES_TERMINAL_IMAGE:-onlyboxes-terminal-local:lca}"
OFFICECLI_VERSION="${OFFICECLI_VERSION:-1.0.143}"

echo "==> Building terminal runtime ${IMAGE_TAG} (officecli v${OFFICECLI_VERSION})"
docker build \
  -f "${ROOT}/deploy/onlyboxes/Dockerfile.terminal" \
  --build-arg "OFFICECLI_VERSION=${OFFICECLI_VERSION}" \
  -t "${IMAGE_TAG}" \
  "${ROOT}/deploy/onlyboxes"

echo "==> Smoke test (reportlab + pandas)"
docker run --rm "${IMAGE_TAG}" python3 -c \
  "import reportlab,pandas,numpy,openpyxl; print('ok', reportlab.Version, pandas.__version__)"

echo "==> Smoke test (officecli — ADR-0054)"
docker run --rm "${IMAGE_TAG}" sh -c \
  'officecli --version && test -n "$OFFICECLI_SKIP_UPDATE" && \
   officecli create /tmp/smoke.pptx --json && \
   officecli add /tmp/smoke.pptx / --type slide --prop title=Smoke --json && \
   officecli validate /tmp/smoke.pptx --json && \
   echo officecli-smoke-ok'

echo "==> Done. Set worker env:"
echo "    WORKER_TERMINAL_EXEC_DOCKER_IMAGE=${IMAGE_TAG}"
echo "    sudo systemctl restart onlyboxes-worker-docker"
