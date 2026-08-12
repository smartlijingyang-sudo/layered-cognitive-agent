#!/usr/bin/env bash
# Point Onlyboxes worker at the LCA terminal runtime image (with officecli).
#
# systemd drop-ins for unit `foo.service` live under `foo.service.d/`,
# NOT `foo.d/` — the latter is silently ignored (DropInPaths empty).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE="${ONLYBOXES_WORKER_SERVICE:-onlyboxes-worker-docker}"
# Correct systemd drop-in directory: <unit>.service.d
DROPIN_DIR="/etc/systemd/system/${SERVICE}.service.d"
DROPIN_FILE="${DROPIN_DIR}/lca-terminal-runtime.conf"
# Stale path used by earlier script versions (ignored by systemd).
LEGACY_DROPIN_DIR="/etc/systemd/system/${SERVICE}.d"

# Default: LCA-built image with officecli (ADR-0054). Official
# coolfan1024/onlyboxes-runtime:{default,lobehub} do NOT ship officecli.
LOCAL_TAG="onlyboxes-terminal-local:lca"
PREFERRED="${ONLYBOXES_TERMINAL_IMAGE:-${LOCAL_TAG}}"

pick_image() {
  if docker image inspect "${PREFERRED}" >/dev/null 2>&1; then
    echo "${PREFERRED}"
    return
  fi

  # If user overrode to a remote tag, try pull once.
  if [[ "${PREFERRED}" != "${LOCAL_TAG}" ]]; then
    echo "==> Pulling ${PREFERRED} …" >&2
    if docker pull "${PREFERRED}" >/dev/null 2>&1; then
      echo "${PREFERRED}"
      return
    fi
    echo "==> Preferred image unavailable; falling back to ${LOCAL_TAG}" >&2
  fi

  if docker image inspect "${LOCAL_TAG}" >/dev/null 2>&1; then
    echo "${LOCAL_TAG}"
    return
  fi

  echo "==> Building ${LOCAL_TAG} (officecli terminal runtime) …" >&2
  "${ROOT}/deploy/onlyboxes/build-terminal-image.sh"
  echo "${LOCAL_TAG}"
}

IMAGE="$(pick_image)"
echo "==> Using terminal runtime image: ${IMAGE}"

# Verify officecli when using the LCA local image (hard fail = wrong image).
if [[ "${IMAGE}" == "${LOCAL_TAG}" ]] || [[ "${IMAGE}" == onlyboxes-terminal-local:* ]]; then
  if ! docker run --rm "${IMAGE}" officecli --version >/dev/null 2>&1; then
    echo "ERROR: ${IMAGE} missing officecli — rebuild with build-terminal-image.sh" >&2
    exit 1
  fi
  echo "==> officecli present in ${IMAGE}"
fi

# Remove legacy ignored drop-in dir so operators are not misled.
if [[ -d "${LEGACY_DROPIN_DIR}" ]]; then
  echo "==> Removing ignored legacy drop-in dir: ${LEGACY_DROPIN_DIR}"
  sudo rm -rf "${LEGACY_DROPIN_DIR}"
fi

sudo mkdir -p "${DROPIN_DIR}"
sudo tee "${DROPIN_FILE}" >/dev/null <<EOF
[Service]
Environment=WORKER_TERMINAL_EXEC_DOCKER_IMAGE=${IMAGE}
EOF

sudo systemctl daemon-reload
sudo systemctl restart "${SERVICE}"
echo "==> Worker restarted with WORKER_TERMINAL_EXEC_DOCKER_IMAGE=${IMAGE}"
echo "==> Drop-in: ${DROPIN_FILE}"
# Kill stale terminalExec containers still on base image without officecli.
stale="$(docker ps -q --filter ancestor=coolfan1024/onlyboxes-runtime:default 2>/dev/null || true)"
if [[ -n "${stale}" ]]; then
  echo "==> Removing stale terminalExec containers on :default (no officecli)"
  # shellcheck disable=SC2086
  docker rm -f ${stale} >/dev/null 2>&1 || true
fi
