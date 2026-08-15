#!/usr/bin/env bash
# Verify an Onlyboxes guest image satisfies GuestLayout.onlyboxes() / LobeHub /mnt/data.
set -euo pipefail

IMAGE="${1:?usage: smoke-guest-layout.sh <image>}"
ROOT="/mnt/data"

docker run --rm "${IMAGE}" sh -c "
  test \"\$(pwd)\" = '${ROOT}' || { echo \"WORKDIR must be ${ROOT}, got \$(pwd)\" >&2; exit 1; }
  test -d '${ROOT}/outputs' || { echo 'missing ${ROOT}/outputs' >&2; exit 1; }
  cd '${ROOT}' && test \"\$(pwd)\" = '${ROOT}'
  echo guest-layout-contract: ok
"
