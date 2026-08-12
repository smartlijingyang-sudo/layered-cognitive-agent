#!/usr/bin/env bash
# 将 LobeHub 官方 release 同步到 lobehub-ui/（LCA 项目内独立副本，gitignore）
#
# 数据来源：仅 https://github.com/lobehub/lobehub.git @ v2.2.13
# 不读取本机其他 lobehub 目录。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${ROOT}/lobehub-ui"
CACHE="${ROOT}/.lobehub-upstream"
UPSTREAM_REPO="${LOBEHUB_UPSTREAM_REPO:-https://github.com/lobehub/lobehub.git}"
RELEASE_TAG="${LOBEHUB_RELEASE:-v2.2.13}"

usage() {
  cat <<EOF
用法: ./scripts/sync_lobehub_ui.sh [--release TAG] [--cache PATH]

  --release TAG   官方 release tag（默认 v2.2.13）
  --cache PATH    upstream 克隆缓存（默认 .lobehub-upstream/）
  -h, --help

同步后: lobehub-ui/（gitignore）
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release) RELEASE_TAG="$2"; shift 2 ;;
    --cache) CACHE="$2"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
  esac
done

ensure_upstream_at_release() {
  if [[ ! -d "${CACHE}/.git" ]]; then
    echo "[sync] 克隆 ${UPSTREAM_REPO} @ ${RELEASE_TAG} → ${CACHE}"
    git clone --depth 1 --branch "${RELEASE_TAG}" "${UPSTREAM_REPO}" "${CACHE}"
  else
    echo "[sync] 更新 ${CACHE} → ${RELEASE_TAG}"
    git -C "${CACHE}" fetch origin tag "${RELEASE_TAG}" --depth 1 2>/dev/null \
      || git -C "${CACHE}" fetch origin --tags --depth 1
    git -C "${CACHE}" checkout -f "${RELEASE_TAG}"
  fi

  local actual
  actual="$(git -C "${CACHE}" describe --tags --exact-match HEAD 2>/dev/null || git -C "${CACHE}" describe --tags --always)"
  echo "[sync] upstream 版本: ${actual}"
  if [[ "${actual}" != "${RELEASE_TAG}" ]] && [[ "${actual}" != *"${RELEASE_TAG}"* ]]; then
    echo "警告: 期望 ${RELEASE_TAG}，当前 ${actual}" >&2
  fi
}

ensure_upstream_at_release

echo "[sync] ${CACHE} → ${DEST}"
mkdir -p "${DEST}"

rsync -a --delete \
  --exclude '.git/' \
  --exclude 'node_modules/' \
  --exclude '.next/' \
  --exclude 'public/_spa/' \
  --exclude 'public/_spa-auth/' \
  --exclude '.turbo/' \
  --exclude 'dist/' \
  --exclude 'coverage/' \
  --exclude '.pytest_cache/' \
  --exclude 'docker-compose/dev/data/' \
  "${CACHE}/" "${DEST}/"

echo "[sync] 完成 → ${DEST} (${RELEASE_TAG})"

# 来源 manifest（便于确认未与外部目录混淆）
cat > "${DEST}/.lca-origin.json" <<EOF
{
  "source": "github.com/lobehub/lobehub",
  "release": "${RELEASE_TAG}",
  "synced_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "lca_project": "${ROOT}",
  "note": "Independent copy — not linked to any external lobehub checkout"
}
EOF

echo "[sync] manifest: ${DEST}/.lca-origin.json"

# 统一补丁引擎（幂等，含 LAN dev / 默认模型 / lca.events closed-loop / 认证 / 路由）
python3 "${ROOT}/deploy/lobehub/patch_lobehub.py" --reset

# Drift guard — verify all modifications are covered by registered patches
echo "[sync] 运行 drift guard..."
if ! python3 "${ROOT}/deploy/lobehub/patch_lobehub.py" drift; then
  echo "[sync] ❌ drift guard 检测到未注册的源码修改！" >&2
  echo "[sync] 请将所有 lobehub-ui/ 修改注册为补丁。详见:" >&2
  echo "[sync]   python3 deploy/lobehub/patch_lobehub.py doctor" >&2
  exit 1
fi

echo "[sync] 下一步: cd lobehub-ui && bun install && bun run dev"
echo "         或: ./scripts/start_lobehub_stack.sh dev"
