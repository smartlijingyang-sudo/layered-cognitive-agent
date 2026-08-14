#!/usr/bin/env bash
# Provision the host runtime from HostRuntimeSettings (SSOT).
#   uv run python -m lca.layer0_infra.sandbox.host_settings
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQ="${ROOT}/deploy/onlyboxes/requirements-python.txt"

log() { printf '[host-runtime] %s\n' "$*"; }

if ! command -v uv >/dev/null 2>&1; then
  for candidate in "${HOME}/.local/bin/uv" "/home/${SUDO_USER:-${USER}}/.local/bin/uv"; do
    if [[ -x "${candidate}" ]]; then
      PATH="$(dirname "${candidate}"):${PATH}"
      export PATH
      break
    fi
  done
fi

eval "$(cd "${ROOT}" && uv run python -m lca.layer0_infra.sandbox.host_settings)"
USER_NAME="${LCA_HOST_USER}"
HOME_DIR="${LCA_HOST_ROOT}"
GUEST_ROOT="${LCA_HOST_GUEST_ROOT}"
OUTPUTS="${LCA_HOST_OUTPUTS}"
PASS_FILE="${LCA_SUDO_PASS_FILE:-${ROOT}/.lobehub-stack/sudo.pass}"

_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif sudo -n true 2>/dev/null; then
    sudo "$@"
  elif [[ -r "${PASS_FILE}" ]]; then
    sudo -S -p '' "$@" <"${PASS_FILE}"
  else
    sudo "$@"
  fi
}

log "profile user=${USER_NAME} root=${HOME_DIR} guest=${GUEST_ROOT}"

if [[ ! -d "${HOME_DIR}" ]]; then
  log "创建工作区 ${HOME_DIR}"
  _sudo mkdir -p "${HOME_DIR}"
fi

if ! id -u "${USER_NAME}" >/dev/null 2>&1; then
  log "创建系统用户 ${USER_NAME}"
  _sudo useradd --system --create-home --home-dir "${HOME_DIR}" --shell /bin/bash "${USER_NAME}" || true
fi

if id -u "${USER_NAME}" >/dev/null 2>&1; then
  _sudo chown -R "${USER_NAME}:${USER_NAME}" "${HOME_DIR}"
  _sudo chmod 2770 "${HOME_DIR}"
  if ! id -nG "$(id -un)" | grep -qw "${USER_NAME}"; then
    log "将 $(id -un) 加入 ${USER_NAME} 组"
    _sudo usermod -aG "${USER_NAME}" "$(id -un)" || true
  fi
else
  _sudo chown -R "$(id -u):$(id -g)" "${HOME_DIR}"
  _sudo chmod 2770 "${HOME_DIR}"
fi

_sudo mkdir -p "${OUTPUTS}"
if id -u "${USER_NAME}" >/dev/null 2>&1; then
  _sudo chown -R "${USER_NAME}:${USER_NAME}" "${OUTPUTS}"
fi

log "安装 CJK 字体与常用 CLI"
if command -v apt-get >/dev/null 2>&1 && [[ -d /etc/apt ]]; then
  DEBIAN_FRONTEND=noninteractive _sudo apt-get install -y --no-install-recommends \
    fonts-wqy-zenhei fonts-noto-cjk-extra \
    pandoc ffmpeg jq poppler-utils
elif command -v dnf >/dev/null 2>&1; then
  _sudo dnf install -y --setopt=install_weak_deps=False \
    pandoc ffmpeg jq poppler-utils wqy-microhei-fonts
  _sudo dnf install -y --setopt=install_weak_deps=False \
    google-noto-sans-cjk-sc-fonts google-noto-sans-cjk-fonts || true
elif command -v yum >/dev/null 2>&1; then
  _sudo yum install -y pandoc ffmpeg jq poppler-utils wqy-microhei-fonts
else
  log "警告: 无 apt/dnf/yum，跳过系统包"
fi

OFFICECLI="$(command -v officecli || true)"
if [[ -n "${OFFICECLI}" ]]; then
  log "officecli: $(officecli --version 2>/dev/null | head -1 || echo present) @ ${OFFICECLI}"
  if [[ ! -x /usr/local/bin/officecli ]]; then
    log "把 officecli 链到 /usr/local/bin，供 host PATH 使用"
    _sudo ln -sf "${OFFICECLI}" /usr/local/bin/officecli
  fi
else
  log "警告: officecli 不在 PATH"
fi

if [[ -f "${REQ}" ]]; then
  log "同步 Onlyboxes 同款 Python 库到当前 uv 环境"
  (cd "${ROOT}" && uv pip install -r "${REQ}")
fi

if [[ -w "${HOME_DIR}" ]]; then
  log "工作区可写: ${HOME_DIR}"
else
  log "警告: ${HOME_DIR} 当前用户不可写。重新登录或: newgrp ${USER_NAME}"
fi

log "完成。Agent guest=${GUEST_ROOT} → 物理 ${HOME_DIR} 操作用户 ${USER_NAME}"
