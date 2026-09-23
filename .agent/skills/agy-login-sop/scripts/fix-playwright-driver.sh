#!/usr/bin/env bash
# Fix the Playwright driver + Chromium for the agy (Antigravity CLI) OAuth flow.
#
# Why: agy's embedded playwright-go v1.57.0 downloads its driver from
# playwright.azureedge.net, which is deprecated and returns 404 in CN network.
# This installs the driver from the npmmirror mirror and installs Chromium v1200.
# Idempotent: safe to re-run.
set -euo pipefail

DRIVER_DIR="$HOME/.cache/ms-playwright-go/1.57.0"
MIRROR="https://cdn.npmmirror.com/binaries/playwright"
DRIVER_URL="$MIRROR/builds/driver/playwright-1.57.0-linux.zip"
CHROMIUM_DIR="$HOME/.cache/ms-playwright/chromium-1200"

echo "==> Ensuring playwright driver at $DRIVER_DIR"
if [ ! -x "$DRIVER_DIR/node" ] || [ ! -f "$DRIVER_DIR/package/cli.js" ]; then
  mkdir -p "$DRIVER_DIR"
  echo "    Downloading driver from $DRIVER_URL ..."
  curl -fL --connect-timeout 30 -o /tmp/playwright-1.57.0-linux.zip "$DRIVER_URL"
  (cd "$DRIVER_DIR" && unzip -oq /tmp/playwright-1.57.0-linux.zip && rm -f /tmp/playwright-1.57.0-linux.zip)
  chmod +x "$DRIVER_DIR/node" "$DRIVER_DIR/package/cli.js"
else
  echo "    Driver already present."
fi

echo "==> Driver version: $("$DRIVER_DIR/node" "$DRIVER_DIR/package/cli.js" --version)"

if [ ! -d "$CHROMIUM_DIR" ]; then
  echo "==> Installing Chromium (playwright build v1200) from npmmirror ..."
  (cd "$DRIVER_DIR" && PLAYWRIGHT_DOWNLOAD_HOST="$MIRROR" ./node package/cli.js install chromium)
else
  echo "==> Chromium already present."
fi

echo "==> Playwright driver + browser ready."