# ADR-0119 Followup: "gateway" 命名空间历史映射

**状态:** Superseded(被 [0119-followup-gateway-name-removal.md](0119-followup-gateway-name-removal.md) 覆盖)
**日期:** 2026-08-31
**父 ADR:** [0119-webserver-as-plugin.md](0119-webserver-as-plugin.md)

> **2026-08-31:** 本 ADR 后续被 ADR-0119 followup-2 扩展到全 6 类清除。
> 当时标注"保留"的 B/C/D/E/F 类已经全部改名为符合语境的中性词。本 ADR
> 仍保留作为历史命名空间映射,但当前实际命名以 followup-2 为准。

## 背景

ADR-0119 决定 4 把 LCA 进程入口切到 `uv run python -m lca_kernel serve`,
`lca-ops` 不再管理该进程。但项目代码里"gateway" 这个词仍出现在多处,
新的代码读者会以为是 ADR-0119 提到的那个 LCA 进程(它不是)。

本 ADR 列清 LCA 内部所有 "gateway" 命名的真实语义,避免后续再混淆。

## LCA 内部所有 "gateway" 命名的语义分类

### A. LCA 进程层 —— ADR-0119 后统称 `kernel_serve`

| 命名 | 位置 | 角色 |
|---|---|---|
| `KernelServeConfig` | `lca/infrastructure/cli/config.py` | lca-ops 配置层对 LCA 进程的 network config (host/port/health_path) |
| `KernelServeConfig` | `lca/infrastructure/host_runtime/config.py` | host_runtime 工具视角对 LCA 进程的 client config (url/health_url/token) |
| `KernelServeHttpClient` | `lca/infrastructure/device_gateway/client.py` | sandbox-user / device 端发 HTTP 到 LCA 进程的 SDK |
| `KernelServeService` | `lca/infrastructure/cli/services/kernel_serve.py` | lca-ops 的自愈 service: 探测 `/health` + spawn `lca_kernel serve` 后台 |
| `gateway-client/` (npm 包 + `packages/gateway-client` 目录) | `packages/gateway-client/` | TypeScript SDK, 上面 SDK 的 npm 包名 |

**全部已重命名/确认** —— 这些命名前缀一致是 `KernelServe*`。
**`packages/gateway-client/` 目录保留** —— npm 包名,改发布名要协调外部,
不在本 ADR 范围。**指向 LCA 进程**。

### B. Webserver transport 路由层 —— 继续叫 `GatewayRouter` (历史命名)

| 命名 | 位置 | 角色 |
|---|---|---|
| `LcaGatewayRouter` (Protocol) | `lca/contracts/protocols/gateway_router.py` | HTTP/WebSocket route registry 协议 |
| `GatewayRouter` (实现类) | `lca/plugins/transport/webserver/router.py` | `lca-gateway-router` plugin 实例化的 mutable class,装 `Route` 列表到 `app.router.routes` |
| `gateway_router` capability key | 同上 plugin manifest 的 `provides=("gateway_router",)` | cordis ctx 上的 capability 槽位名,被 4 个 routes plugin 通过 `requires=("gateway_router",)` 消费 |
| `/lca-api/...` URL 路径 (LobeHub proxy) | `deploy/lobehub/patches/proxy/file_proxy_rewrite.py` | Next rewrite,把 `/lca-api/runs` → gateway |

**保留旧名** —— 改 capability key 会让 plugin tree 启动失败
(`requires=("gateway_router",)` 找不到 provider)。
**这是 webserver transport 路由层,不是 LCA 后台进程**。
Router 类比"Starlette route 容器",职责是接收 plugin 注入的 Route,
在 lifespan 一次性 `app.router.routes.extend(...)`。

### C. Session spine 命令层 —— 继续叫 `CommandGateway` (历史命名)

| 命名 | 位置 | 角色 |
|---|---|---|
| `lca/harness/command/gateway.py` (module) | `lca/harness/command/gateway.py` | session spine 内部命令接收 |
| `CommandGateway` (类) | 同上 | `/v1/sessions/{id}/commands/*` 端点的命令路由器 |

**保留旧名** —— 这是 session spine (0090 / 0092) 的固有概念,
不是 LCA 进程,也不是 webserver route。**指向 session spine 命令面**。

### D. Modes plugin namespace —— `gateway/plugins/default_modes/` (历史命名)

| 命名 | 位置 | 角色 |
|---|---|---|
| `gateway/plugins/default_modes.py` (module path) | `gateway/plugins/default_modes.py` | L4 modes plugin 目录 |
| `emitter="gateway.plugins.default_modes"` (wire schema) | `lca/infrastructure/observability/events/event_descriptors_data.py` | 事件 emitter 字段,写进 JSONL journal |

**保留旧名** —— 这是 plugin id namespace (cordis plugin id 字符串约定),
emitter 字段是 wire schema,**改它会让老 journal 文件解析失败**。
**指向 L4 modes plugin namespace,不是 LCA 进程**。

### E. Event schema 历史 namespace —— `lca.harness.command.gateway` (历史命名)

| 命名 | 位置 | 角色 |
|---|---|---|
| `emitter="lca.harness.command.gateway"` (wire schema) | `lca/infrastructure/observability/events/event_descriptors_data.py` | `TaskCreated` 事件的 emitter 字段,写盘 |
| `lca.harness.command.gateway` (Python module path) | `lca/harness/command/gateway.py` | 真实 module,被 4 处 import |

**保留旧名** —— emitter 是 wire schema 字段(写进 JSONL journal);
module path 是 `lca.harness.command.gateway`,改了会破 import。
**指向 session spine command emitter 命名**。

### F. Docstring / 模板 README 历史叙述 —— 53 个 README + 87 docs

| 位置 | 数量 | 处理 |
|---|---|---|
| 各 lca/*/README.md 第 25 行的 `^- \`gateway\`$` | 53 | **保留** —— 这是包契约 forbidden_dependencies 拦截词,拦截"禁止 import `lca/gateway/` 顶层模块"。这种顶层模块**根本不存在**,规则无意义但保留无害 |
| docs/specs/ + docs/adr/ + docs/design/ + docs/plans/ + docs/superpowers/ + docs/history/ | 87 | **保留** —— 历史叙述,改字面会失真 |
| `AGENTS.md` 的 "Gateway router" 入口行 | 1 | **保留** —— 引用 `GatewayRouter` 类,准确 |

## 决策

1. **LCA 进程层 (A 类)** —— 全部用 `kernel_serve` / `KernelServe*`,已完成。
2. **Webserver transport (B 类)** —— 保留 `GatewayRouter` / `gateway_router` capability key,
   加注释指向本 ADR 说明 "这是 transport 路由层,不是 ADR-0119 的 kernel serve"。
3. **Session spine (C 类)** —— 保留 `CommandGateway` / `lca/harness/command/gateway.py`,
   加注释指向本 ADR。
4. **Modes plugin namespace (D 类)** —— 保留路径 + wire schema emitter 字符串,
   加注释指向本 ADR。
5. **Event emitter namespace (E 类)** —— 保留 wire schema + module path,
   加注释指向本 ADR。
6. **历史叙述 (F 类)** —— 不动字面,docstring 不再追"。

## 索引

- 落地: `lca/infrastructure/cli/services/kernel_serve.py` + `lca/infrastructure/cli/config.py:KernelServeConfig`
- 落地: `lca/infrastructure/host_runtime/config.py:KernelServeConfig` + 字段 `kernel_serve` + `kernel_serve_client_dir`
- 落地: `lca/infrastructure/device_gateway/client.py:KernelServeHttpClient`
- 落地: `lca/infrastructure/observability/events/event_doc.py` (`layer="gateway"` → `"L4"`, docstring 字段不写盘)
- **未改**: `lca/contracts/protocols/gateway_router.py` (Protocol), `lca/plugins/transport/webserver/router.py` (`GatewayRouter` 类 + `gateway_router` capability key)
- **未改**: `lca/harness/command/gateway.py` (module) + `CommandGateway` 类
- **未改**: `gateway/plugins/default_modes.py` + `emitter="gateway.plugins.default_modes"`
- **未改**: `emitter="lca.harness.command.gateway"`
- **未改**: 53 个 README 模板的 forbidden_dependencies 拦截词 + 87 个 docs 历史叙述