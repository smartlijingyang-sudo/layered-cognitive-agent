# ADR-0112: Gateway 路由 Plugin 化(借鉴 deepseek host/webserver)

> **状态：** Proposed(被 [ADR-0115](./0115-kernel-transport-boundary.md) 修订)
> **修订日期：** 2026-08-31
> **配套 ADR：** [ADR-0083](./0083-deepseek-harness-plugin-implementation-plan.md) W6 Team/Mode · [ADR-0103](./0103-locked-surface-and-port-policy.md) wire-shape 锁定 · [ADR-0106](./0106-naming-constitution.md) 命名宪法 · **优先 ADR:**[ADR-0115](./0115-kernel-transport-boundary.md) Kernel/Transport 边界
>
> ⚠️ **本文初版(2026-08-31 上午)规划 `lca/plugins/gateway/` 目录 + `LcaGatewayServer` Protocol + 8 个 routes plugin;被 [ADR-0115](./0115-kernel-transport-boundary.md) 修订方向:gateway 应迁到 `lca/plugins/transport/webserver/` 独立 transport namespace;`GatewayServer` → `GatewayRouter`(ADR-0106 §4.1 合规);8 个 routes plugin 减到 4 个。**

## 修订记录(2026-08-31 被 ADR-0115 锁定)

| 旧内容(初版) | 新内容(ADR-0115 修订) |
|---|---|
| `lca/plugins/gateway/` 目录 | `lca/plugins/transport/webserver/` 独立 transport namespace |
| `LcaGatewayServer` Protocol | `LcaGatewayRouter` Protocol(命名宪法 §4.1 合规 + 准确定义"负责 register/dispose 路由表") |
| `lca-gateway-server` plugin id | `lca-gateway-router` |
| 8 个 routes plugin | **4 个**:`routes_health_options` / `routes_runs_sessions` / `routes_openai_compat_files` / `routes_device` |
| `routes_openai_shim.py` | `routes_openai_compat.py`(ADR-0106 §5 禁词清单) |
| `gateway/app.py` 瘦身到 ≤ 200 行 | `gateway/app.py` thin factory ≤ 60 行 |
| `lca-gateway-server requires compile_profile` | **删除 requires**;`lca-gateway-router` 是被 kernel 启动的普通 plugin,跟 kernel 解耦 |
| `@dataclass(frozen=True) + __setattr__` 反模式 | 用 mutable class + deepseek WebServer 形态 |

## 背景

`gateway/app.py`(700+ 行)同时承担:

1. **ASGI 装配**:`create_app()` 装配 Starlette,定义 lifespan,绑定 services
2. **模块级单例**:`_registry / _file_store / _devices / _device_hub`(L79–83)
3. **module-level 副作用**:`_configure_structlog()`(L109–117)
4. **兼容垫片**:`_load_harness_profile()`(L138–204,死代码)
5. **路由 handler**:`_download_file / _get_file_meta`(L96–104,小包装)
6. **bootstrap 重复块**:处理 `bootstrap_factory` 写了两次(L309–331 + L351–369)
7. **30+ 路由注册**:全部在 `Starlette(routes=[...])` 列表里硬编码(L239–289)

按 ADR-0085 "Plugin 文档即 Manifest" 和 ADR-0106 §3.2 命名宪法,这个文件违反 §3.2(角色后缀必须是 30 个后缀之一)、§4(文件↔类一一对应)、§5 禁词(`utils / helpers / manager`)、§8.1 函数前缀。

deepseek-harness `packages/host/webserver` 完全解决了同类问题:

```typescript
// deepseek host/webserver/src/index.ts
export class WebServer extends Service {
  static Config = z.object({ host: z.union([...]), port: z.natural() }).required()
  register(route: WebRoute): () => void {       // ← 返回 disposer
  registerUpgrade(route: WebUpgradeRoute): () => void
  setFallback(handler): () => void             // ← 单一 fallback seat
  }
}
```

每个 audit-log / api-gateway / frontend-static 都是一个独立 plugin,通过 `ctx.inject(['webServer'], () => new AuditLogService(ctx, config))` 注册路由到 webServer service。

## 决定

### 决定 1:`LcaGatewayServer` Protocol(L0 seam)

新建 `lca/contracts/protocols/gateway_server.py`:

```python
class LcaGatewayServer(Protocol):
    """借鉴 deepseek host/webserver:注册/反注册路由的唯一入口。

    Public surface:
        register_http(route: Route) -> Callable[[], None]
        register_websocket(route: WebSocketRoute) -> Callable[[], None]
        set_fallback(handler: Callable) -> Callable[[], None]
        install(app: Starlette) -> None        # lifespan startup 时调用
    """
```

每个 `register_*` 返回 `() -> None` disposer,**调用方必须 `ctx.effect(disposer, label=...)`**;违反抛出 `UndeclaredInteractionError`(沿用 ADR-0061 审计)。

### 决定 2:`lca-gateway-server` L0 seam plugin

`lca/plugins/gateway/server.py`:

```python
@plugin(
    id="lca-gateway-server",
    provides=("gateway_server",),
    requires=("compile_profile",),     # compile_profile 来自 ADR-0111
    layer="L0",
    kind=PluginKind.SEAM,
    effects=frozenset({EffectClass.NONE}),
    test_suite="tests.plugins.gateway.test_server",
)
def setup(ctx, config) -> None:
    """Make GatewayServer discoverable via ctx.inject('gateway_server').

    The seam registers an empty route registry; route plugins call
    register() during their own setup. activate() listens on config.port.
    """
    app = Starlette(routes=[])
    server = GatewayServer(ctx, app, config)   # 详见决定 3
    ctx.provide("gateway_server", server)
```

Lifespan(由 ADR-0111 的 compile_profile 装配)负责 `server.activate()` 启动监听。**模块加载时不再自动跑 `create_app()`**;`gateway/app.py:app` 这一行改为 `app: Starlette | None = None`,由 `lca-ops serve` 或 uvicorn 配置 `--factory` 触发。

### 决定 3:`GatewayServer` 不可变数据 + 服务实现

`lca/contracts/protocols/gateway_server.py` 只定义 Protocol;`lca/plugins/gateway/server.py` 内的 `GatewayServer` 是具体实现:

```python
@dataclass(frozen=True, slots=True)
class GatewayServer:
    ctx: Context
    app: Starlette
    config: GatewayServerConfig
    _routes: tuple[Route, ...] = ()
    _upgrades: tuple[WebSocketRoute, ...] = ()
    _fallback: Callable | None = None

    def register_http(self, route: Route) -> Callable[[], None]:
        new = self._routes + (route,)
        object.__setattr__(self, "_routes", new)
        self.app.router.routes.append(route)
        return lambda: self._remove_http(route)
    # ... register_websocket / set_fallback 同形态
```

`@dataclass(frozen=True)` + `__setattr__` 绕过保证路由表始终追加(单写者:plugin setup),不破坏 frozen 不变量。这是"自描述契约 + 显式可变操作"的混合。

### 决定 4:每组路由拆为独立 plugin

按 deepseek 模式,把现有 30+ 路由分组,每组一个 L3 provider plugin:

| Plugin ID | 注册路径 | 依赖 |
|---|---|---|
| `lca-gateway-routes-health` | `/health`、`/options` | `gateway_server` |
| `lca-gateway-routes-context` | `/context` | `gateway_server`, `run_registry` |
| `lca-gateway-routes-journal` | `/journal/live`(SSE) | `gateway_server`, `journal` |
| `lca-gateway-routes-runs` | `/runs` 系 7 个 endpoint | `gateway_server`, `run_registry`, `compile_profile` |
| `lca-gateway-routes-sessions` | `/v1/sessions` 系 8 个 endpoint | `gateway_server`, `agent_registry`, `command_gateway` |
| `lca-gateway-routes-files` | `/files/{id}`、`/files/{id}/meta` | `gateway_server`, `file_store` |
| `lca-gateway-routes-openai-shim` | `/v1/models`、`/v1/chat/completions`、`/v1/embeddings`、`/v1/responses` | `gateway_server`, `llm_resolver` |
| `lca-gateway-routes-device` | `/api/device/*`(8 个 endpoint) | `gateway_server`, `device_hub`, `machine_resolver` |

每个 plugin 文件 `lca/plugins/gateway/routes_<name>.py` 顶部 docstring 严格遵循 ADR-0111 模板,setup 函数体 ≤ 40 行,只做"register + ctx.effect(disposer)"。

例 `routes_health.py`:

```python
"""Register the /health and OPTIONS routes."""
@plugin(id="lca-gateway-routes-health", provides=("gateway_health_route",),
 requires=("gateway_server",), layer="L3", kind=PluginKind.PROVIDER,
 test_suite="tests.plugins.gateway.test_routes_health")
def setup(ctx, config):
    server = ctx.inject("gateway_server")
    dispose = server.register_http(Route("/health", health_handler, methods=["GET"]))
    ctx.effect(dispose, label="route:/health")
    for path in ("/context", "/journal/live", "/runs", "/v1/sessions", ...):
        server.register_http(Route(path, _options, methods=["OPTIONS"]))
```

### 决定 5:`gateway/app.py` 瘦身

新 `gateway/app.py` ≤ 200 行,只剩:

- `create_app(profile_path=None, **kwargs) -> Starlette`:thin adapter,调 `compile_profile` 装配 lifespan,返回 starlette 实例
- `app = create_app()` 在 module 底部保留(uvicorn `--factory` 兼容),但不构造路由,路由全部由 plugin 注入
- 删 `_load_harness_profile / _configure_structlog / _download_file / _get_file_meta / bootstrap 重复块`

## 与既有 ADR 的衔接

| 既有 | 衔接 |
|---|---|
| ADR-0103 wire-shape 锁定 | 本 ADR 不改 wire shape;只把"在 `app.py` 里硬塞 30 条 `Route(...)`"改为"plugin 调用 `server.register_http(Route(...))`" |
| ADR-0106 命名宪法 | 每个 plugin 文件名 `routes_<subject>.py`,setup 函数以 `register` 前缀开头,符合 §8.1 |
| ADR-0111 启动编译化 | `lca-gateway-server` requires `compile_profile`;lifespan 在 startup 时 activate server |
| ADR-0083 W6 Team/Mode | gateway 不再持有 mode 分支;mode 由 `run_mode_registry` capability 决定,见 [ADR-0052](0052-unified-dynamic-casting.md) |

## CI 门禁

新增 / 复用:

- `scripts/check_route_owners.py`(新建):扫描所有 `@plugin` 声明,`provides=("gateway_server",)` 必须唯一;routes_* plugin 必须 require `gateway_server`;防止重复注册或孤立 route。
- `tests/plugins/gateway/test_server.py`:LcaGatewayServer Protocol 一致性 + register/dispose 幂等性。
- `tests/plugins/gateway/test_routes_health.py` 等 8 个:每个 route plugin 一个 spec,覆盖"register/dispose 在 ctx.effect 下完整"路径。
- `tests/test_architecture_gateway.py`(扩展):确保删除 gateway/app.py 的死代码后,`lca-ops serve` 仍能 listen 3080 + `/health` 返回 200 + `/runs` 返回 200。

## 放弃的方案

- **完全删 `gateway/app.py`,把 `create_app()` 挪到 `lca-gateway-server` plugin 内部**:Starlette 要求 ASGI app 实例在 module-load 时确定;uvicorn `--factory` 工作流依赖 `gateway.app:app` 入口;移到 plugin 内部会破坏 uvicorn 启动契约。保留 thin adapter。
- **保留 module-level 单例 `_registry / _file_store`**:违反 C2 双平面 + 借鉴 deepseek 取消 module-level 副作用的精神;统一改为 `application.state`。
- **把所有路由塞进一个 `lca-gateway-routes` 大 plugin**:违反"一 plugin 一职责";deepseek 把每个 endpoint group 拆独立 package,是有意为之——可独立替换 audit-log 而不影响 api-gateway。

## 后果

正面:
- Gateway 路由 100% plugin 化,新增 endpoint 只增 plugin + profile/bundle entry,不修改 `gateway/app.py`。
- `gateway/app.py` 从 700+ 行降到 ≤ 200 行,职责单一(只做 ASGI 装配)。
- 死代码 + module-level 副作用消失。
- 与 deepseek 的 `host/webserver` + `host/audit-log` + `host/apiproxy` 三段式对齐。

负面:
- 9 个新 plugin 拆分后,profile/bundle 需要新增对应 entry(默认 `web-app.yaml` 已经覆盖大部分)。
- `app = create_app()` 改为 lazy 装配,uvicorn `gateway.app:app` 工作流需要 `--factory` 或 `--reload` 兼容(已在 `pyproject.toml` 标注)。
- 当前 tests 假设 `gateway.app:app` 已注册所有路由,需要全部改用 `compile_profile` + lifespan 路径(预计 30+ tests 改动)。

## 索引

| 主题 | 文档 |
|---|---|
| deepseek host/webserver | `~/deepseek-harness/packages/host/webserver/src/index.ts` |
| deepseek host/audit-log | `~/deepseek-harness/packages/host/audit-log/src/plugin.ts` |
| 现有 Gateway | `gateway/app.py` · `gateway/routes.py` · `gateway/cors.py` |
| LcaGatewayServer Protocol | `lca/contracts/protocols/gateway_server.py` |
| 路由 plugin 目录 | `lca/plugins/gateway/routes_*.py` |
| 命名宪法 | [`docs/design/naming-constitution.md`](../design/naming-constitution.md) |
| Locked-surface 策略 | [ADR-0103](./0103-locked-surface-and-port-policy.md) |