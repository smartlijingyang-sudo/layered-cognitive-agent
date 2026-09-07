# LobeHub 前端排障

LobeHub dev 是**双进程**：Next.js `:3010`（HTML/API 壳）+ Vite SPA `:9876`（React 模块）。浏览器必须**同时**能访问两个端口；只通 3010 会表现为 Agent 页闪错、无限刷新。

环境变量 SSOT：`deploy/lobehub/.env.lca` → `lobehub-ui/.env`（`VITE_DEV_HOST`、`APP_URL` 必须与浏览器访问的主机名一致）。

**`NEXT_PUBLIC_LCA_GATEWAY_URL` / `NEXT_PUBLIC_LCA_HOST_CONSOLE` 由 `lca-ops lobehub start/restart` 注入到 bun 子进程 env**（不是仅写 `.env`）：vite 的 DefinePlugin 在启动时读一次进程 env，不会热加载 `.env`。如果只改 `.env` 不重启 dev stack，front-end SPA bundle 里 `process.env.NEXT_PUBLIC_LCA_GATEWAY_URL` 是 `undefined`，chat 会抛 `[LCA] chat attempted without LCA gateway configured`。手动 `bun run dev:next` / `bun run dev:spa` 不会注入这两个 env，调试时用 `env NEXT_PUBLIC_LCA_GATEWAY_URL=ws://<host>:<port> bun run dev:*`。

## 1. 30 秒健康检查（服务端）

```bash
./scripts/lca-ops status --json | jq '.[] | select(.service=="lobehub")'
curl -sI http://127.0.0.1:3010/ | head -3
curl -sI http://127.0.0.1:9876/ | head -3
# 与 VITE_DEV_HOST 对齐（默认 deploy/lobehub/.env.lca 里的 LAN IP）
curl -sI "http://${VITE_DEV_HOST:-10.36.6.252}:9876/" | head -3
ls lobehub-ui/src/store/chat/agents/transports/lcaRunCommand.ts \
   lobehub-ui/src/store/chat/agents/transports/lcaRunObserve.ts \
   lobehub-ui/src/store/chat/agents/transports/lcaRunHil.ts
```

| 检查 | 正常 | 异常含义 |
|---|---|---|
| `status` → `spa` check | `:9876` ok | Vite sidecar 未起 → `./scripts/lca-ops lobehub restart` |
| `patches` | 20/20 verified | 补丁未打全 → `uv run python deploy/lobehub/patch_lobehub.py apply lca_run_driver` |
| `lcaRunCommand.ts` 等三文件 | 存在 | `lca_run_driver` 漏拷 → 同上 apply + restart |
| 服务端 curl 9876 | `200` | 本机 Vite 挂了；看 `.lca-ops/lobehub-spa.log` |

## 2. 日志（两个文件，不要混）

```bash
./scripts/lca-ops journal logs lobehub       # Next.js :3010 → .lca-ops/lobehub.log
./scripts/lca-ops journal logs lobehub-spa   # Vite :9876   → .lca-ops/lobehub-spa.log
```

**快速 grep（服务端）：**

```bash
rg -n 'Failed to resolve import|Outdated Optimize Dep|ECONNREFUSED|500 in|server connection lost' \
  .lca-ops/lobehub-spa.log .lca-ops/lobehub.log | tail -30
```

## 3. 浏览器控制台 → 原因 → 动作

| 控制台关键字 | 原因 | 修复 |
|---|---|---|
| `504 (Outdated Optimize Dep)` | Vite 重启后浏览器仍缓存旧 `?v=` 哈希 | 等服务端 Vite `ready` 后 **硬刷新**（Ctrl+Shift+R）；仍失败则 `./scripts/lca-ops lobehub restart` 再硬刷新 |
| `[vite] server connection lost` | Vite 进程重启/崩溃 | `./scripts/lca-ops lobehub restart`；查 `lobehub-spa.log` |
| `ERR_CONNECTION_REFUSED …:9876` | 9876 瞬时不可用或客户端不可达 | 服务端：restart；客户端：`curl -I http://<VITE_DEV_HOST>:9876/` |
| `Failed to resolve import "./lcaRunCommand"` | LCA 补丁 TS 缺失 | `patch_lobehub.py apply lca_run_driver` + restart |
| `Failed to fetch dynamically imported module …/_layout/index.tsx` | 上述任一导致模块链失败 | 先修 Vite/补丁，再硬刷新 |
| `chrome-extension://…` | 浏览器插件噪声 | **忽略**，与 LobeHub 无关 |
| `Uncaught (in promise) Error: [LCA] chat attempted without LCA gateway configured. Set NEXT_PUBLIC_LCA_GATEWAY_URL.` | dev 进程没拿到该 env；只写 `.env` 不够 | `./scripts/lca-ops lobehub restart`（让 `_child_env()` 注入）；硬刷新浏览器；调试点 |

## 4. 客户端 curl 误判

Windows 上若看到 `502 Bad Gateway` + `Proxy-Connection`，常为**系统/公司代理**拦截，不代表服务端挂了。用浏览器能否打开页面为准；必要时：

```bash
curl --noproxy '*' -I http://10.36.6.252:9876/
```

若浏览器能开 3010 但模块全挂，重点仍是 **9876 可达性** 或 **Outdated Optimize Dep**（硬刷新）。

## 5. 标准恢复流程

```bash
# 1. 补丁 + 依赖（勿单独 rm node_modules/.vite 后不 restart）
./scripts/lca-ops lobehub ensure
uv run python deploy/lobehub/patch_lobehub.py verify

# 2. 重启（等 Vite compile 完成，status spa=ok）
./scripts/lca-ops lobehub restart
./scripts/lca-ops status --json | jq '.[] | select(.service=="lobehub")'

# 3. 浏览器硬刷新；仍循环则清站点数据后重开
```

**禁止：** 在 Vite 运行中删除 `lobehub-ui/node_modules/.vite` 且不立即 restart——会触发大规模 dep 重优化与 `Outdated Optimize Dep` 风暴。

## 6. 相关入口

- 补丁机制：[deploy/lobehub/README.md](../../deploy/lobehub/README.md)
- 集成概览：[lobehub-integration.md](../specs/lobehub-integration.md)
- Run 失败（非 UI）：[run-debug-guide.md](./run-debug-guide.md)
