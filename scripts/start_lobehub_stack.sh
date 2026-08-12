#!/usr/bin/env bash
# LCA + LobeHub v2.2.13 联合启动
#
#   Browser → LobeHub official UI (lobehub-ui/, bun run dev)
#   LobeHub OpenAI client → LCA Gateway (:8765/v1)
#   LCA Gateway → LCA Agent/Team 运行时
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBE_DIR="${ROOT}/lobehub-ui"
RUN_DIR="${ROOT}/.lobehub-stack"
GATEWAY_PORT="${GATEWAY_PORT:-8765}"
LOBE_DEV_PORT="${LOBE_DEV_PORT:-3010}"
SPA_PORT="${SPA_PORT:-9876}"
SPA_MOBILE_PORT="${SPA_MOBILE_PORT:-3012}"
SPA_AUTH_PORT="${SPA_AUTH_PORT:-3013}"
LOBEHUB_RELEASE="${LOBEHUB_RELEASE:-v2.2.13}"

GATEWAY_PID="${RUN_DIR}/gateway.pid"
GATEWAY_LOG="${RUN_DIR}/gateway.log"
LOBE_DEV_PID="${RUN_DIR}/lobehub-dev.pid"
LOBE_ENV="${ROOT}/deploy/lobehub/.env.lca"
NEXT_DEV_LOCK="${LOBE_DIR}/.next/dev/lock"

# Public URL for file downloads (browser-facing).
# IMPORTANT: 0.0.0.0 is a *bind* address, not a client URL — browsers cannot
# download from http://0.0.0.0:PORT. Prefer explicit override, then LAN IP.
_resolve_gateway_public_url() {
  if [[ -n "${GATEWAY_PUBLIC_URL:-}" ]]; then
    printf '%s\n' "${GATEWAY_PUBLIC_URL}"
    return
  fi
  if [[ -n "${LCA_GATEWAY_PUBLIC_URL:-}" ]]; then
    printf '%s\n' "${LCA_GATEWAY_PUBLIC_URL}"
    return
  fi
  local host="${LOBE_LAN_IP:-${VITE_DEV_HOST:-}}"
  if [[ -z "${host}" ]]; then
    host="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}' || true)"
  fi
  if [[ -z "${host}" ]]; then
    host="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
  # Never advertise 0.0.0.0 / empty as a download host.
  if [[ -z "${host}" || "${host}" == "0.0.0.0" ]]; then
    host="127.0.0.1"
  fi
  printf 'http://%s:%s\n' "${host}" "${GATEWAY_PORT}"
}
GATEWAY_PUBLIC_URL="$(_resolve_gateway_public_url)"

log() { printf '[lobehub-stack] %s\n' "$*"; }

_python() {
  if command -v uv >/dev/null 2>&1; then
    uv run python "$@"
  else
    python3 "$@"
  fi
}

_kill_pid_tree() {
  local pid="$1"
  local sig="${2:-TERM}"
  [[ -z "${pid}" || ! "${pid}" =~ ^[0-9]+$ ]] && return 0
  kill -0 "${pid}" 2>/dev/null || return 0
  local child
  for child in $(pgrep -P "${pid}" 2>/dev/null || true); do
    _kill_pid_tree "${child}" "${sig}"
  done
  kill "-${sig}" "${pid}" 2>/dev/null || true
}

_collect_lobehub_dev_pids() {
  local -a pids=()
  local pid lock_pid port_pid

  if [[ -f "${LOBE_DEV_PID}" ]]; then
    pid="$(tr -d '[:space:]' <"${LOBE_DEV_PID}" 2>/dev/null || true)"
    [[ -n "${pid}" ]] && pids+=("${pid}")
  fi

  if [[ -f "${NEXT_DEV_LOCK}" ]]; then
    lock_pid="$(
      _python - "${NEXT_DEV_LOCK}" <<'PY' 2>/dev/null || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text())
except Exception:
    raise SystemExit
pid = data.get("pid")
if isinstance(pid, int):
    print(pid)
PY
    )"
    [[ -n "${lock_pid}" ]] && pids+=("${lock_pid}")
  fi

  if command -v ss >/dev/null 2>&1; then
    port_pid="$(
      ss -tlnp 2>/dev/null \
        | awk -v port=":${LOBE_DEV_PORT}" '$0 ~ port { if (match($0, /pid=([0-9]+)/, m)) { print m[1]; exit } }'
    )"
    [[ -n "${port_pid}" ]] && pids+=("${port_pid}")
  fi

  while IFS= read -r pid; do
    [[ -n "${pid}" ]] && pids+=("${pid}")
  done < <(
    pgrep -f "${LOBE_DIR}/.*devStartupSequence\\.mts" 2>/dev/null \
      || pgrep -f "${LOBE_DIR}/.*scripts/devStartupSequence" 2>/dev/null \
      || true
  )

  while IFS= read -r pid; do
    [[ -n "${pid}" ]] && pids+=("${pid}")
  done < <(pgrep -f "${LOBE_DIR}/.*next dev -p ${LOBE_DEV_PORT}" 2>/dev/null || true)

  # 去重并保持顺序
  local seen="" deduped=""
  for pid in "${pids[@]}"; do
    [[ " ${seen} " == *" ${pid} "* ]] && continue
    seen="${seen} ${pid}"
    deduped="${deduped} ${pid}"
  done
  printf '%s\n' ${deduped}
}

_wait_for_port() {
  local port="$1" timeout_s="${2:-10}" label="${3:-port ${port}}"
  local waited=0
  while [[ ${waited} -lt $((timeout_s * 2)) ]]; do
    if ss -tln 2>/dev/null | grep -q ":${port} "; then
      return 0
    fi
    sleep 0.5
    waited=$((waited + 1))
  done
  log "超时: ${label} 在 ${timeout_s}s 内未监听 :${port}"
  return 1
}

_wait_for_lobehub_dev() {
  local timeout_s="${1:-120}"
  local waited=0
  log "等待 LobeHub dev 就绪 (最长 ${timeout_s}s)…"
  while [[ ${waited} -lt $((timeout_s * 2)) ]]; do
    if curl -sf --max-time 5 "http://127.0.0.1:${LOBE_DEV_PORT}/" >/dev/null 2>&1; then
      log "LobeHub dev 就绪 ✓ (http://127.0.0.1:${LOBE_DEV_PORT})"
      return 0
    fi
    # 检查进程是否还活着
    local pid
    if [[ -f "${LOBE_DEV_PID}" ]]; then
      pid="$(tr -d '[:space:]' <"${LOBE_DEV_PID}" 2>/dev/null || true)"
      if [[ -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then
        log "错误: LobeHub dev 进程 (pid ${pid}) 已退出"
        return 1
      fi
    fi
    sleep 0.5
    waited=$((waited + 1))
  done
  log "超时: LobeHub dev 在 ${timeout_s}s 内未就绪"
  return 1
}

_clean_stale_dev_state() {
  # 清理残留的 PID 文件和 Next.js dev lock，防止二次启动卡住
  if [[ -f "${LOBE_DEV_PID}" ]]; then
    local pid
    pid="$(tr -d '[:space:]' <"${LOBE_DEV_PID}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then
      log "清理残留 PID 文件 (进程 ${pid} 已不存在)"
      rm -f "${LOBE_DEV_PID}" 2>/dev/null || true
    fi
  fi
  if [[ -f "${NEXT_DEV_LOCK}" ]]; then
    local lock_pid
    lock_pid="$(
      _python - "${NEXT_DEV_LOCK}" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
try:
    data = json.loads(Path(sys.argv[1]).read_text())
    pid = data.get("pid")
    if isinstance(pid, int): print(pid)
except Exception: pass
PY
    )"
    if [[ -n "${lock_pid}" ]] && ! kill -0 "${lock_pid}" 2>/dev/null; then
      log "清理残留 Next.js dev lock (进程 ${lock_pid} 已不存在)"
      rm -f "${NEXT_DEV_LOCK}" 2>/dev/null || true
    fi
  fi
  # 端口仍被占用但无存活进程 → 残留 socket，等内核回收
  if ss -tln 2>/dev/null | grep -q ":${LOBE_DEV_PORT} "; then
    local holder
    holder="$(ss -tlnp 2>/dev/null | awk -v p=":${LOBE_DEV_PORT}" '$0~p{if(match($0,/pid=([0-9]+)/,m))print m[1];exit}')"
    if [[ -n "${holder}" ]] && ! kill -0 "${holder}" 2>/dev/null; then
      log "端口 ${LOBE_DEV_PORT} 有残留 socket (pid ${holder} 已僵)，等待回收…"
      sleep 2
    fi
  fi
}

lobehub_dev_running() {
  curl -sf --max-time 2 "http://127.0.0.1:${LOBE_DEV_PORT}/" >/dev/null 2>&1
}

stop_lobehub_dev() {
  local pid
  local -a targets=()
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] && targets+=("${pid}")
  done < <(_collect_lobehub_dev_pids)

  if [[ ${#targets[@]} -eq 0 ]]; then
    rm -f "${LOBE_DEV_PID}" "${NEXT_DEV_LOCK}" 2>/dev/null || true
    return 0
  fi

  log "停止已有 LobeHub dev（: ${LOBE_DEV_PORT}，pids: ${targets[*]}）"
  for pid in "${targets[@]}"; do
    _kill_pid_tree "${pid}" TERM
  done

  local waited=0
  while [[ ${waited} -lt 20 ]]; do
    local still=0
    for pid in "${targets[@]}"; do
      kill -0 "${pid}" 2>/dev/null && still=1
    done
    [[ ${still} -eq 0 ]] && break
    sleep 0.5
    waited=$((waited + 1))
  done

  for pid in "${targets[@]}"; do
    _kill_pid_tree "${pid}" KILL
  done

  rm -f "${LOBE_DEV_PID}" "${NEXT_DEV_LOCK}" 2>/dev/null || true

  if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":${LOBE_DEV_PORT} "; then
    log "警告: 端口 ${LOBE_DEV_PORT} 仍被占用，请手动检查"
    return 1
  fi
  return 0
}

_collect_vite_spa_pids() {
  local -a pids=()
  local port port_pid
  for port in "${SPA_PORT}" "${SPA_MOBILE_PORT}" "${SPA_AUTH_PORT}"; do
    if command -v ss >/dev/null 2>&1; then
      port_pid="$(
        ss -tlnp 2>/dev/null \
          | awk -v port=":${port}" '$0 ~ port { if (match($0, /pid=([0-9]+)/, m)) { print m[1]; exit } }'
      )"
      [[ -n "${port_pid}" ]] && pids+=("${port_pid}")
    fi
  done
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] && pids+=("${pid}")
  done < <(pgrep -f "${LOBE_DIR}/node_modules/.bin/vite" 2>/dev/null || true)
  local seen="" deduped=""
  for pid in "${pids[@]}"; do
    [[ " ${seen} " == *" ${pid} "* ]] && continue
    seen="${seen} ${pid}"
    deduped="${deduped} ${pid}"
  done
  printf '%s\n' ${deduped}
}

stop_vite_spa() {
  local pid
  local -a targets=()
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] && targets+=("${pid}")
  done < <(_collect_vite_spa_pids)
  if [[ ${#targets[@]} -eq 0 ]]; then
    return 0
  fi
  log "停止 Vite SPA（pids: ${targets[*]}）"
  for pid in "${targets[@]}"; do
    _kill_pid_tree "${pid}" TERM
  done
  local waited=0
  while [[ ${waited} -lt 10 ]]; do
    local still=0
    for pid in "${targets[@]}"; do
      kill -0 "${pid}" 2>/dev/null && still=1
    done
    [[ ${still} -eq 0 ]] && break
    sleep 0.5
    waited=$((waited + 1))
  done
  for pid in "${targets[@]}"; do
    _kill_pid_tree "${pid}" KILL
  done
}

prepare_lobehub_dev() {
  if [[ "${LOBE_REUSE_DEV:-0}" == "1" ]] && lobehub_dev_running; then
    log "LobeHub dev 已在运行，复用 http://127.0.0.1:${LOBE_DEV_PORT}（LOBE_REUSE_DEV=1）"
    return 1
  fi
  stop_lobehub_dev
}

_infra_port_open() {
  local host="$1"
  local port="$2"
  _python - "${host}" "${port}" <<'PY' 2>/dev/null
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
with socket.create_connection((host, port), timeout=1.5):
    pass
PY
}

_infra_targets_from_env() {
  local env_file="${LOBE_DIR}/.env"
  [[ -f "${env_file}" ]] || env_file="${LOBE_ENV}"
  [[ -f "${env_file}" ]] || return 0
  _python - "${env_file}" <<'PY'
import sys
from pathlib import Path
from urllib.parse import urlparse

path = Path(sys.argv[1])
env = {}
for line in path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    env[key.strip()] = value.strip().strip('"').strip("'")

checks = []
db = env.get("DATABASE_URL")
if db:
    parsed = urlparse(db)
    checks.append(("postgres", parsed.hostname or "127.0.0.1", parsed.port or 5432))
redis = env.get("REDIS_URL")
if redis:
    parsed = urlparse(redis)
    checks.append(("redis", parsed.hostname or "127.0.0.1", parsed.port or 6379))
s3 = env.get("S3_ENDPOINT")
if s3:
    parsed = urlparse(s3)
    if parsed.hostname:
        checks.append(
            (
                "s3",
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
            )
        )

for name, host, port in checks:
    print("{}\t{}\t{}".format(name, host, port))
PY
}

infra_endpoints_ready() {
  local line name host port
  local any=0
  while IFS=$'\t' read -r name host port; do
    [[ -z "${name}" ]] && continue
    any=1
    if ! _infra_port_open "${host}" "${port}"; then
      return 1
    fi
  done < <(_infra_targets_from_env)
  [[ "${any}" -eq 1 ]]
}

start_infra() {
  if [[ "${LOBE_SKIP_INFRA:-0}" == "1" ]]; then
    log "跳过 docker infra（LOBE_SKIP_INFRA=1）"
    return 0
  fi

  if [[ "${LOBE_FORCE_INFRA:-0}" != "1" ]] && infra_endpoints_ready; then
    log "复用已有基础设施（lobehub-ui/.env 中的 postgres / redis / s3 端口可达，跳过 docker compose）"
    return 0
  fi

  local compose="${LOBE_DIR}/docker-compose/dev/docker-compose.yml"
  if [[ ! -f "${compose}" ]] || ! command -v docker >/dev/null 2>&1; then
    if infra_endpoints_ready; then
      log "无 docker compose，但已有基础设施可用"
      return 0
    fi
    log "跳过 docker infra（无 compose 或未安装 docker）"
    return 0
  fi

  log "启动 LobeHub 基础设施 (postgres + redis + rustfs)…"
  local compose_err=""
  compose_err="$(
    cd "${LOBE_DIR}/docker-compose/dev"
    if [[ ! -f .env ]]; then
      cp .env.example .env 2>/dev/null || true
    fi
    docker compose up -d postgresql redis rustfs rustfs-init 2>&1 \
      || docker compose up -d 2>&1
  )" || true

  if infra_endpoints_ready; then
    if [[ -n "${compose_err}" ]] && [[ "${compose_err}" == *"Conflict"* || "${compose_err}" == *"already in use"* ]]; then
      log "docker compose 与已有容器名冲突，但当前 .env 指向的基础设施已可用，继续"
    else
      log "基础设施就绪"
    fi
    return 0
  fi

  log "警告: 基础设施未就绪（postgres / redis / s3 端口不可达）"
  if [[ -n "${compose_err}" ]]; then
    printf '[lobehub-stack] compose 输出:\n%s\n' "${compose_err}" | tail -5
  fi
  log "提示: 若已手动运行 lobe-postgres(:25432) / lobe-minio(:19000)，可忽略 compose；否则检查 ${compose}"
  return 0
}

sync_lobehub_ui() {
  LOBEHUB_RELEASE="${LOBEHUB_RELEASE}" "${ROOT}/scripts/sync_lobehub_ui.sh"
}

ensure_lobehub_ui() {
  local need_sync=0
  if [[ ! -f "${LOBE_DIR}/package.json" ]]; then
    need_sync=1
  elif ! grep -q '"version": "2.2.13"' "${LOBE_DIR}/package.json" 2>/dev/null; then
    log "lobehub-ui/ 版本不是 2.2.13，重新同步…"
    need_sync=1
  fi
  if [[ "${need_sync}" -eq 1 ]]; then
    sync_lobehub_ui
  fi
}

ensure_lobehub_env() {
  if [[ ! -f "${LOBE_DIR}/.env" ]]; then
    if [[ -f "${LOBE_ENV}" ]]; then
      log "复制 LCA 环境模板 → lobehub-ui/.env"
      cp "${LOBE_ENV}" "${LOBE_DIR}/.env"
    else
      log "警告: 缺少 ${LOBE_ENV}，请手动配置 lobehub-ui/.env"
    fi
  fi
  inject_qwen_from_lca_env
}

inject_qwen_from_lca_env() {
  local lobe_env="${LOBE_DIR}/.env"
  [[ -f "${lobe_env}" ]] || return 0

  local gateway_url="http://127.0.0.1:${GATEWAY_PORT}/v1"
  local agent_config="model=solo;provider=openai;chatConfig.searchMode=off"

  # 合并模板中 LCA 路由项（不覆盖用户已改的其他键）
  if [[ -f "${LOBE_ENV}" ]]; then
    while IFS= read -r line || [[ -n "${line}" ]]; do
      [[ "${line}" =~ ^[[:space:]]*# ]] && continue
      [[ "${line}" =~ ^[[:space:]]*$ ]] && continue
      [[ "${line}" == *"="* ]] || continue
      local key="${line%%=*}"
      if ! grep -q "^${key}=" "${lobe_env}" 2>/dev/null; then
        printf '%s\n' "${line}" >>"${lobe_env}"
      fi
    done < <(grep -E '^(QWEN_|DEFAULT_AGENT_CONFIG=|OPENAI_)' "${LOBE_ENV}" || true)
  fi

  _set_lobe_env() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "${lobe_env}" 2>/dev/null; then
      sed -i "s|^${key}=.*|${key}=${value}|" "${lobe_env}"
    else
      printf '%s=%s\n' "${key}" "${value}" >>"${lobe_env}"
    fi
  }

  _set_lobe_env "OPENAI_PROXY_URL" "${gateway_url}"
  _set_lobe_env "OPENAI_API_KEY" "lca-local"
  _set_lobe_env "QWEN_PROXY_URL" "${gateway_url}"
  _set_lobe_env "QWEN_API_KEY" "lca-local"
  _set_lobe_env "ENABLED_QWEN" "1"
  _set_lobe_env "DEFAULT_AGENT_CONFIG" "${agent_config}"
}

apply_lca_lobehub_patches() {
  if [[ ! -f "${LOBE_DIR}/package.json" ]]; then
    return 0
  fi
  # patch 脚本对 BROKEN 补丁返回 exit 1，这是警告不是致命错误
  _python "${ROOT}/deploy/lobehub/patch_lobehub.py" || true
}

stop_gateway() {
  if [[ -f "${GATEWAY_PID}" ]]; then
    local pid
    pid="$(cat "${GATEWAY_PID}")"
    kill "${pid}" 2>/dev/null || true
    rm -f "${GATEWAY_PID}"
    log "已停止 gateway (pid ${pid})"
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${GATEWAY_PORT}/tcp" >/dev/null 2>&1 || true
  fi
}

gateway_needs_restart() {
  [[ "${LCA_GATEWAY_FORCE_RESTART:-0}" == "1" ]] && return 0
  [[ ! -f "${GATEWAY_PID}" ]] && return 0
  local pid
  pid="$(cat "${GATEWAY_PID}" 2>/dev/null || true)"
  [[ -z "${pid}" ]] && return 0
  kill -0 "${pid}" 2>/dev/null || return 0
  local proc_start gateway_dir newest
  proc_start="$(ps -p "${pid}" -o lstart= 2>/dev/null || true)"
  [[ -z "${proc_start}" ]] && return 0
  gateway_dir="${ROOT}/gateway"
  newest="$(find "${gateway_dir}" "${ROOT}/lca" -name '*.py' -printf '%T@\n' 2>/dev/null | sort -n | tail -1 || true)"
  [[ -z "${newest}" ]] && return 0
  local proc_epoch newest_int
  proc_epoch="$(date -d "${proc_start}" +%s 2>/dev/null || echo 0)"
  newest_int="${newest%.*}"
  [[ "${newest_int}" -gt "${proc_epoch}" ]]
}

start_gateway() {
  mkdir -p "${RUN_DIR}"
  if [[ -f "${GATEWAY_PID}" ]] && kill -0 "$(cat "${GATEWAY_PID}")" 2>/dev/null; then
    if gateway_needs_restart; then
      log "gateway 代码已更新，重启以加载新 Python"
      stop_gateway
    else
      log "gateway 已在运行 (pid $(cat "${GATEWAY_PID}"))"
      return 0
    fi
  fi
  log "启动 LCA Gateway (OpenAI 面) :${GATEWAY_PORT} (public: ${GATEWAY_PUBLIC_URL})"
  (
    cd "${ROOT}"
    export LCA_GATEWAY_PUBLIC_URL="${GATEWAY_PUBLIC_URL}"
    exec uv run python scripts/serve_observability.py --host 0.0.0.0 --port "${GATEWAY_PORT}"
  ) >>"${GATEWAY_LOG}" 2>&1 &
  echo $! >"${GATEWAY_PID}"

  for _ in $(seq 1 40); do
    if curl -sf "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
      log "gateway 就绪: http://127.0.0.1:${GATEWAY_PORT}/health"
      return 0
    fi
    sleep 0.25
  done
  log "gateway 启动超时，见 ${GATEWAY_LOG}"
  return 1
}

start_lobehub_dev() {
  ensure_lobehub_ui
  ensure_lobehub_env
  apply_lca_lobehub_patches

  if [[ ! -d "${LOBE_DIR}/node_modules" ]]; then
    log "安装 LobeHub 依赖 (bun install)…"
    (cd "${LOBE_DIR}" && bun install)
  fi

  if ! prepare_lobehub_dev; then
    return 0
  fi

  # v2.2.13 官方：OpenAI 兼容 provider → LCA gateway
  export OPENAI_PROXY_URL="${OPENAI_PROXY_URL:-http://127.0.0.1:${GATEWAY_PORT}/v1}"
  export OPENAI_API_KEY="${OPENAI_API_KEY:-lca-local}"
  export ENABLED_OPENAI="${ENABLED_OPENAI:-1}"
  export PORT="${LOBE_DEV_PORT}"

  if [[ "${LOBE_CLEAN_CACHE:-0}" == "1" ]]; then
    log "清理 Vite 依赖缓存 + .next（LOBE_CLEAN_CACHE=1）"
    rm -rf "${LOBE_DIR}/node_modules/.vite/deps" "${LOBE_DIR}/.next"
  elif [[ -d "${LOBE_DIR}/node_modules/.vite/deps/_metadata.json" ]]; then
    local meta_age
    meta_age="$(find "${LOBE_DIR}/node_modules/.vite/deps/_metadata.json" -mmin +1440 2>/dev/null)"
    [[ -n "${meta_age}" ]] && log "提示: Vite 依赖缓存超过 24h，如遇 'outdated optimize dep' 可加 LOBE_CLEAN_CACHE=1 重启"
  fi

  # ── 前置检查：gateway 必须可达 ──────────────────────────
  if ! curl -sf --max-time 3 "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
    log "警告: gateway :${GATEWAY_PORT} 未就绪，尝试先启动 gateway…"
    start_gateway
    if ! _wait_for_port "${GATEWAY_PORT}" 10 "gateway"; then
      log "错误: gateway 启动失败，LobeHub dev 无法工作 (OpenAI → :${GATEWAY_PORT}/v1)"
      return 1
    fi
  fi

  log "启动 LobeHub ${LOBEHUB_RELEASE} dev (OpenAI → ${OPENAI_PROXY_URL})"
  log "访问: http://127.0.0.1:${LOBE_DEV_PORT}"

  # ── 守护进程化启动 ──────────────────────────────────────
  # nohup + setsid 使进程脱离当前终端，SSH 断开不会杀进程
  local dev_log="${RUN_DIR}/lobehub-dev.log"
  mkdir -p "${RUN_DIR}"
  cd "${LOBE_DIR}"
  nohup setsid bash -c 'exec bun run dev' </dev/null >"${dev_log}" 2>&1 &
  local dev_pid=$!
  echo "${dev_pid}" >"${LOBE_DEV_PID}"
  disown "${dev_pid}" 2>/dev/null || true
  log "LobeHub dev 已后台启动 (pid ${dev_pid}, log: ${dev_log})"

  # ── 健康检查 ────────────────────────────────────────────
  if _wait_for_lobehub_dev 120; then
    return 0
  fi

  # 启动失败 → 打印日志末尾帮助诊断，清理残留
  log "── LobeHub dev 启动失败，最近日志 ──"
  tail -20 "${dev_log}" 2>/dev/null | while IFS= read -r line; do log "  ${line}"; done
  log "── 尝试清理残留状态 ──"
  stop_lobehub_dev || true
  return 1
}

stop_all() {
  stop_lobehub_dev || true
  stop_vite_spa || true
  stop_gateway
  _clean_stale_dev_state
}

usage() {
  cat <<EOF
用法: $0 <dev|gateway|sync|stop|status|restart|restart-gateway>

  dev              同步 v2.2.13 + 应用 LCA 补丁 + 启动 gateway + bun run dev
  gateway          仅启动 LCA OpenAI 兼容网关（代码更新时自动重启）
  restart          全量重启：停止所有 → 重启 gateway + infra + 前端
  restart-gateway  强制重启 gateway（加载最新 Python）
  sync             强制从官方拉取 v2.2.13 到 lobehub-ui/ 并打补丁
  stop             停止 LobeHub dev + gateway
  status           查看 gateway / lobehub dev 状态

环境变量:
  LOBEHUB_RELEASE   release tag（默认 v2.2.13）
  GATEWAY_PORT      LCA 网关端口（默认 8765）
  GATEWAY_PUBLIC_URL  文件下载的公开 URL（浏览器可达；默认检测 LAN IP，
                      如 http://10.x.x.x:8765；勿用 0.0.0.0）
  LOBE_LAN_IP / VITE_DEV_HOST  未设 GATEWAY_PUBLIC_URL 时用于拼公开基址
  LOBE_DEV_PORT     LobeHub dev 端口（默认 3010）
  LOBE_REUSE_DEV    设为 1 时若 dev 已在运行则复用、不重启
  LOBE_SKIP_INFRA   设为 1 时跳过 docker compose
  LOBE_FORCE_INFRA  设为 1 时即使端口可达也尝试 docker compose
  LOBE_CLEAN_CACHE  设为 1 时清除 .vite/deps + .next 缓存再启动（日常不要开，会丢失预构建加速）
  LCA_GATEWAY_FORCE_RESTART  设为 1 时强制重启 gateway
  OPENAI_PROXY_URL  LobeHub 指向的 OpenAI 兼容 URL
EOF
}

cmd="${1:-dev}"
shift || true

case "${cmd}" in
  dev) start_gateway; start_infra; start_lobehub_dev ;;
  restart) _clean_stale_dev_state; stop_all; LCA_GATEWAY_FORCE_RESTART=1 start_gateway; start_infra; start_lobehub_dev ;;
  gateway) start_gateway ;;
  restart-gateway) LCA_GATEWAY_FORCE_RESTART=1 start_gateway ;;
  sync) sync_lobehub_ui ;;
  stop) stop_all ;;
  status)
    if [[ -f "${GATEWAY_PID}" ]] && kill -0 "$(cat "${GATEWAY_PID}")" 2>/dev/null; then
      log "gateway: 运行中 (pid $(cat "${GATEWAY_PID}"), port ${GATEWAY_PORT})"
    else
      log "gateway: 未运行"
    fi
    if lobehub_dev_running; then
      dev_pids="$(_collect_lobehub_dev_pids | tr '\n' ' ')"
      log "lobehub dev: 运行中 (port ${LOBE_DEV_PORT}, pids:${dev_pids:- unknown})"
    else
      log "lobehub dev: 未运行"
    fi
    if [[ -f "${LOBE_DIR}/package.json" ]]; then
      log "lobehub-ui: $(grep '"version"' "${LOBE_DIR}/package.json" | head -1 | tr -d ' ",')"
    else
      log "lobehub-ui: 未同步"
    fi
    ;;
  -h | --help) usage ;;
  *) usage >&2; exit 2 ;;
esac
