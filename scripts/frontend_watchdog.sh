#!/usr/bin/env bash
# Frontend auto-heal watchdog for LCA LobeHub & Vite SPA.
# Heals when Vite (:9876) is down, Next (:3010) is down/500, or the dev
# route table collapsed (/signin answers a redirect instead of 200).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

export PATH="/home/lichao/.bun/bin:/home/lichao/.local/node-v24/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

LOG_FILE=".lca-ops/watchdog.log"
mkdir -p .lca-ops

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [watchdog] Starting LCA frontend watchdog..." >> "$LOG_FILE"

while true; do
    # Probe Vite SPA (:9876), Next.js (:3010), and route integrity (/signin).
    VITE_OK=$(curl -s --max-time 1 -o /dev/null -w "%{http_code}" "http://127.0.0.1:9876/" 2>/dev/null || echo "000")
    DEV_OK=$(curl -s --max-time 1 -o /dev/null -w "%{http_code}" "http://127.0.0.1:3010/" 2>/dev/null || echo "000")
    SIGNIN_OK=$(curl -s --max-time 2 -o /dev/null -w "%{http_code}" "http://127.0.0.1:3010/signin" 2>/dev/null || echo "000")

    # A healthy /signin must answer 200. A 3xx here means the route table
    # collapsed (every URL falls into not-found -> redirect('/')), which the
    # root probe misses because 302/307 look like a normal signin redirect.
    ROUTE_BROKEN=0
    case "$SIGNIN_OK" in
        301|302|307|308) ROUTE_BROKEN=1 ;;
    esac

    # Heal when Vite is down, Next is down/500, or routes collapsed.
    if [ "$VITE_OK" != "200" ] || [ "$DEV_OK" = "000" ] || [ "$DEV_OK" = "500" ] || [ "$ROUTE_BROKEN" = "1" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [watchdog] Unhealthy detected (vite=$VITE_OK, dev=$DEV_OK, signin=$SIGNIN_OK, route_broken=$ROUTE_BROKEN). Auto-healing..." >> "$LOG_FILE"
        ./scripts/lca-ops lobehub heal >> "$LOG_FILE" 2>&1
        sleep 2
    fi
    sleep 3
done