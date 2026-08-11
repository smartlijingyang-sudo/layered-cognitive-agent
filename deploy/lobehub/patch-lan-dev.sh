#!/usr/bin/env bash
# 局域网 dev：让 signin/SPA 页面的 Vite 资源 URL 使用 LAN IP，而非 localhost
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPA_HTML="${ROOT}/lobehub-ui/src/libs/spaHtml/index.ts"
LAN_IP="${LOBE_LAN_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"

if [[ ! -f "${SPA_HTML}" ]]; then
  echo "错误: 找不到 ${SPA_HTML}，请先 ./scripts/sync_lobehub_ui.sh" >&2
  exit 1
fi

if grep -q 'VITE_DEV_HOST' "${SPA_HTML}"; then
  echo "[patch-lan] 已打过 LAN 补丁，跳过"
  exit 0
fi

python3 <<PY
from pathlib import Path

path = Path("${SPA_HTML}")
text = path.read_text()
old = """export const resolveViteDevOrigin = () =>
  \`http://localhost:\${Number(process.env.VITE_DEV_PORT) || 9876}\`;"""
new = """export const resolveViteDevOrigin = () => {
  const host = process.env.VITE_DEV_HOST || 'localhost';
  const port = Number(process.env.VITE_DEV_PORT) || 9876;
  return \`http://\${host}:\${port}\`;
};"""
if old not in text:
    raise SystemExit(f"patch target not found in {path}")
path.write_text(text.replace(old, new, 1))
print(f"[patch-lan] patched {path}")
PY

echo "[patch-lan] LAN IP: ${LAN_IP}"
