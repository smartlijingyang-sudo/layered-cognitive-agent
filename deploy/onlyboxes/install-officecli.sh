#!/usr/bin/env bash
# Install a pinned officecli binary into a container image (or host for smoke).
# Usage:
#   OFFICECLI_VERSION=1.0.143 ./install-officecli.sh [/usr/local/bin]
set -euo pipefail

VERSION="${OFFICECLI_VERSION:-1.0.143}"
DEST_DIR="${1:-/usr/local/bin}"
ARCH_RAW="${OFFICECLI_ARCH:-${TARGETARCH:-$(uname -m)}}"

case "${ARCH_RAW}" in
  amd64|x86_64|x64) ARCH="x64" ;;
  arm64|aarch64) ARCH="arm64" ;;
  *)
    echo "unsupported arch: ${ARCH_RAW}" >&2
    exit 1
    ;;
esac

# Debian/glibc runtime (onlyboxes-runtime). Alpine assets are NOT used.
ASSET="officecli-linux-${ARCH}"
URL="https://github.com/iOfficeAI/OfficeCLI/releases/download/v${VERSION}/${ASSET}"
TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT

echo "==> officecli v${VERSION} (${ASSET})"

# Try mirror first (faster in China), then fall back to direct GitHub.
MIRROR_URLS=(
  "https://mirror.ghproxy.com/${URL}"
  "https://ghfast.top/${URL}"
  "https://gh-proxy.com/${URL}"
)

downloaded=false
for try_url in "${MIRROR_URLS[@]}" "${URL}"; do
  echo "  trying: ${try_url}"
  if command -v curl >/dev/null 2>&1; then
    if curl -fsSL --connect-timeout 10 --max-time 120 "${try_url}" -o "${TMP}" 2>/dev/null; then
      downloaded=true
      break
    fi
  elif command -v wget >/dev/null 2>&1; then
    if wget -q --timeout=10 -O "${TMP}" "${try_url}" 2>/dev/null; then
      downloaded=true
      break
    fi
  fi
done

if [ "${downloaded}" != "true" ]; then
  echo "ERROR: failed to download officecli from all mirrors" >&2
  exit 1
fi

install -m 0755 "${TMP}" "${DEST_DIR}/officecli"
# Stability: never auto-update inside sandbox sessions.
export OFFICECLI_SKIP_UPDATE=1
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 "${DEST_DIR}/officecli" --version
echo "==> installed ${DEST_DIR}/officecli"
