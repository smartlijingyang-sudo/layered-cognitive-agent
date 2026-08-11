#!/usr/bin/env bash
# Point Onlyboxes worker at the LobeHub-aligned terminal runtime image.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE="${ONLYBOXES_WORKER_SERVICE:-onlyboxes-worker-docker}"
DROPIN_DIR="/etc/systemd/system/${SERVICE}.d"
DROPIN_FILE="${DROPIN_DIR}/lca-terminal-runtime.conf"

PREFERRED="${ONLYBOXES_TERMINAL_IMAGE:-coolfan1024/onlyboxes-runtime:lobehub}"
LOCAL_TAG="onlyboxes-terminal-local:lca"

pick_image() {
  if docker image inspect "${PREFERRED}" >/dev/null 2>&1; then
    echo "${PREFERRED}"
    return
  fi
  echo "==> Pulling ${PREFERRED} …" >&2
  if docker pull "${PREFERRED}" >/dev/null 2>&1; then
    echo "${PREFERRED}"
    return
  fi
  echo "==> Preferred image unavailable; building ${LOCAL_TAG} …" >&2
  "${ROOT}/deploy/onlyboxes/build-terminal-image.sh"
  echo "${LOCAL_TAG}"
}

IMAGE="$(pick_image)"
echo "==> Using terminal runtime image: ${IMAGE}"

sudo mkdir -p "${DROPIN_DIR}"
sudo tee "${DROPIN_FILE}" >/dev/null <<EOF
[Service]
Environment=WORKER_TERMINAL_EXEC_DOCKER_IMAGE=${IMAGE}
EOF

sudo systemctl daemon-reload
sudo systemctl restart "${SERVICE}"
echo "==> Worker restarted with WORKER_TERMINAL_EXEC_DOCKER_IMAGE=${IMAGE}"
