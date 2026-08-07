#!/usr/bin/env bash
# 重启 LCA 可观测性 UI：SSE 网关 (8765) + Vite 前端 (5180)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT}/.observability-ui"
GATEWAY_HOST="${GATEWAY_HOST:-0.0.0.0}"
GATEWAY_PORT="${GATEWAY_PORT:-8765}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-5180}"
GATEWAY_LOG="${RUN_DIR}/gateway.log"
WEB_LOG="${RUN_DIR}/web.log"
GATEWAY_PID="${RUN_DIR}/gateway.pid"
WEB_PID="${RUN_DIR}/web.pid"

mkdir -p "${RUN_DIR}"

log() {
  printf '[obs-ui] %s\n' "$*"
}

free_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  elif command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      kill ${pids} 2>/dev/null || true
      sleep 0.3
      kill -9 ${pids} 2>/dev/null || true
    fi
  else
    log "警告: 未找到 fuser/lsof，无法自动释放端口 ${port}"
  fi
}

stop_pidfile() {
  local pidfile="$1"
  local name="$2"
  if [[ -f "${pidfile}" ]]; then
    local pid
    pid="$(cat "${pidfile}")"
    if kill -0 "${pid}" 2>/dev/null; then
      log "停止 ${name} (pid ${pid})"
      kill "${pid}" 2>/dev/null || true
      sleep 0.5
      kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f "${pidfile}"
  fi
}

stop_all() {
  log "停止已有进程…"
  stop_pidfile "${GATEWAY_PID}" "gateway"
  stop_pidfile "${WEB_PID}" "web"
  free_port "${GATEWAY_PORT}"
  free_port "${WEB_PORT}"
}

wait_http() {
  local url="$1"
  local name="$2"
  local tries="${3:-40}"
  for ((i = 1; i <= tries; i++)); do
    if curl -sf "${url}" >/dev/null 2>&1; then
      log "${name} 就绪: ${url}"
      return 0
    fi
    sleep 0.25
  done
  log "错误: ${name} 启动超时 (${url})"
  log "最近日志:"
  tail -n 20 "${GATEWAY_LOG}" 2>/dev/null || true
  return 1
}

lan_ip() {
  hostname -I 2>/dev/null | awk '{print $1}' || true
}

start_gateway() {
  log "启动 SSE 网关 ${GATEWAY_HOST}:${GATEWAY_PORT}"
  (
    cd "${ROOT}"
    exec uv run python scripts/serve_observability.py --host "${GATEWAY_HOST}" --port "${GATEWAY_PORT}"
  ) >>"${GATEWAY_LOG}" 2>&1 &
  echo $! >"${GATEWAY_PID}"
  wait_http "http://127.0.0.1:${GATEWAY_PORT}/health" "gateway"
}

start_web() {
  if [[ ! -d "${ROOT}/web/node_modules" ]]; then
    log "安装前端依赖 (npm install)…"
    (cd "${ROOT}/web" && npm install)
  fi
  log "启动前端 ${WEB_HOST}:${WEB_PORT}"
  (
    cd "${ROOT}/web"
    exec npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}"
  ) >>"${WEB_LOG}" 2>&1 &
  echo $! >"${WEB_PID}"
  local tries=40
  for ((i = 1; i <= tries; i++)); do
    if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1; then
      log "web 就绪: http://127.0.0.1:${WEB_PORT}/"
      return 0
    fi
    sleep 0.25
  done
  log "错误: web 启动超时"
  tail -n 20 "${WEB_LOG}" 2>/dev/null || true
  return 1
}

print_urls() {
  local ip
  ip="$(lan_ip)"
  log "────────────────────────────────────────"
  log "本机:   http://127.0.0.1:${WEB_PORT}/"
  if [[ -n "${ip}" ]]; then
    log "局域网: http://${ip}:${WEB_PORT}/"
  fi
  log "网关:   http://127.0.0.1:${GATEWAY_PORT}/health"
  log "日志:   ${GATEWAY_LOG}"
  log "        ${WEB_LOG}"
  log "停止:   $0 stop"
  log "────────────────────────────────────────"
}

start_all() {
  stop_all
  start_gateway
  start_web
  print_urls
}

status_all() {
  for pair in "gateway:${GATEWAY_PID}:${GATEWAY_PORT}" "web:${WEB_PID}:${WEB_PORT}"; do
    IFS=: read -r name pidfile port <<<"${pair}"
    if [[ -f "${pidfile}" ]] && kill -0 "$(cat "${pidfile}")" 2>/dev/null; then
      log "${name}: 运行中 (pid $(cat "${pidfile}"), port ${port})"
    else
      log "${name}: 未运行"
    fi
  done
}

usage() {
  cat <<EOF
用法: $0 [start|stop|restart|status]

  start    启动网关 + 前端（会先释放 ${GATEWAY_PORT}/${WEB_PORT}）
  stop     停止并释放端口
  restart  等同 start（默认）
  status   查看进程状态

环境变量: GATEWAY_HOST GATEWAY_PORT WEB_HOST WEB_PORT
EOF
}

cmd="${1:-restart}"
case "${cmd}" in
  start | restart)
    start_all
    ;;
  stop)
    stop_all
    log "已停止"
    ;;
  status)
    status_all
    ;;
  -h | --help | help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
