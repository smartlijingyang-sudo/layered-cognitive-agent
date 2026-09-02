# ADR-0115: Kernel / Transport 边界 — `lca-kernel` 顶层包与 lint-imports 门禁

> **状态：** Accepted (K1–K8 全部落地)
> **日期：** 2026-08-31
> **落地证据：**
> - `lca_kernel/` 14 文件,`lca_kernel/__init__.py` 公共面 re-export K1–K8 接口
> - K1–K7 由 PR-2 (commit `90dd2c87`) 实现;K8 HMR 由 ADR-0118 + PR-7 (本批)
> - `lca/plugins/transport/webserver/` 独立 transport namespace;`lca-gateway-router` + 4 routes plugin
> - `scripts/check_kernel_boundary.py` 跑 AST 边界 + 全量 kernel 测试 + importlinter
> - `tests/lca_kernel/test_boundary.py` AST 守 (12 项)
> - `pyproject.toml` importlinter `kernel-domain-isolation` + `transport-isolation` 重新配置为 forbidden top-level `lca_kernel` + ignore_imports 白名单(importlinter 2.13 不支持 forbid 外部包子模块)
> **配套 ADR：** [ADR-0083](./0083-deepseek-harness-plugin-implementation-plan.md) W1 主链 · [ADR-0085](./0085-plugin-everything-explained.md) 插件哲学 · [ADR-0105](./0105-package-organization-discipline.md) 包组织纪律 · [ADR-0106](./0106-naming-constitution.md) 命名宪法 · [ADR-0111](./0111-startup-compilation-as-subpackage.md) 启动编译化(本次修订)· [ADR-0112](./0112-gateway-routes-as-plugins.md) Gateway 路由(本次修订) · [ADR-0117](./0117-process-lifecycle-env-whitelist.md) Process 生命周期(本次新立项)
>
> **本 ADR 是新架构顶层设计,优先于 ADR-0111 / 0112 / 0113 / 0114;它们在本文 §"对既有 ADR 的修订" 一节被引用并锁定方向。**

## 背景

当前 LCA 启动链路分散在 5 个位置,职责重叠且边界模糊:

| 位置 | 实际职责 | 越界事实 |
|---|---|---|
| `lca/harness/profile/boot.py` (240 行) | cordis Context + Fiber 启动 | 混合 resolve / spawn_fiber / install_observability / dispose 5 类职责 |
| `lca/harness/profile/lifespan.py` (200 行) | Starlette lifespan 适配 | **kernel 模块 import starlette** —— 违反"kernel 零 transport 知识" |
| `gateway/app.py` (439 行) | ASGI 装配 + 调 `boot_profile` + 硬塞 30+ 路由 + 装 lifespan | **混合 transport 装配 + kernel 启动**,kernel 越界做 transport 的事 |
| `lca/application/api.py:set_default_ctx` | module-level 全局 ctx holder | **违反 ADR-0062**(明确反对 module-level 单例)+ ADR-0115 边界 |
| `scripts/lca-ops` (bash wrapper) | 调用 `lca.infrastructure.cli.cli` | **没有 `lca-ops boot` / `lca-ops kernel` 独立入口**,kernel 启动永远是 gateway 副产物 |

deepseek-harness 的 `packages/boot/app-boot/`(829 行,纯 Python / TS)用最干净的形态解决了同类问题:

```text
app-boot           deps: cordis + yaml + patch + hmr
                   公共: boot(), composeEntries(), loadLayeredEnv(),
                         installFailLoud(), loadProfile(), watchUserPatches()
                   零 transport 知识(不 import HTTP/WS/JSON-RPC/stdio)

host-webserver     deps: 仅 @deepseek-ai/schemastery(一行的 JSON schema)
                   公共: WebServer extends Service;
                         register() / registerUpgrade() / setFallback()
                   零 framework 知识(不 import fastify/express/koa)

apps/cli + apps/web  共享同一棵 plugin tree;只差 webserver 是否装载
```

`host-webserver` 整个包**零 fastify/express 依赖**,只 import `node:http` 和 `cordis.Service`。`app-boot` 不知道有 webserver,只知道"我加载所有 plugin(由 cordis.yml 决定),谁要被 listen 是 plugin 自己声明的事"。**两个包互不 import,通过 `cordis.yml` 的 bundles 组合**。

LCA 当前形态部分像 deepseek,但 kernel 越界严重,transport 跟 kernel 高度耦合。本 ADR 锁定 kernel/transport 边界,把 kernel 提到顶层包 `lca-kernel/`,通过 `lint-imports` 强制零 transport 知识。

## 决定

### 决定 1:kernel = `lca-kernel/` 顶层包,8 大职责

新建 `lca-kernel/` 顶层包,跟 `lca/contracts/`、`lca/infrastructure/`、`lca/cognition/`、`lca/runtime/`、`lca/agent/` 平级。**零 transport 知识,零 web framework 依赖**(通过 lint-imports 强制)。

```
lca-kernel/
├── __init__.py            # 公共 API:compile_profile, run_kernel, stop_kernel
├── source.py              # K1:Profile 输入 adapter(yaml + bundle + patch + env refs)
├── resolve.py             # K1:领域校验(manifest / capability / layer / DAG / topo)
├── plan.py                # K2:Plan 编译(CapabilityPlan + ControlPlan + ScopePlan → CompiledRunPlan)
├── boot.py                # K3:cordis Context + Fiber 启动 + bind bootstrap services
├── closure.py             # K4:运行时闭包校验(plan 必填 binding 满足)
├── observability.py       # K5:唯一 BoundObservability 装配点
├── lifecycle.py           # K6:SIGTERM/SIGINT + unhandledRejection + atexit 兜底
├── env.py                 # K7:分层 env 加载 + BOOTSTRAP_NAMES 白名单
├── hmr.py                 # K8:cordis.patch.yml watcher + 热重载
├── stages.py              # Stage(IntEnum) SSOT
├── trace.py               # BootTrace(frozen dataclass)
└── errors.py              # KernelError / FailLoudError / StageError / ReloadError
```

**8 大职责**(借鉴 deepseek `app-boot/src/index.ts` 829 行 + LCA 现状):

| ID | 职责 | deepseek 对应 | LCA 现状迁移 |
|---|---|---|---|
| **K1** | **Profile 解析** | `loadProfile()` + `composeEntries()` + `healProfilesModuleFallback()` | 从 `lca/harness/profile/source.py + resolve.py + declarations.py` 迁出 |
| **K2** | **Plan 编译** | 隐式 in `boot()` | 从 `lca/harness/profile/plan_compiler.py + capability_plan_resolver.py` 迁出 |
| **K3** | **Plugin Tree 启动** | `boot()` + cordis Context Fiber | 从 `lca/harness/profile/boot.py` 拆出 4 文件 |
| **K4** | **运行时闭包校验** | 隐式 via Loader validate | 从 `runtime_binding_validator.py + runtime_closure.py` 迁出 |
| **K5** | **观测装配** | 隐式 via ctx.inject | 从 `_install_observability()` 独立成 `observability.py`(单一装配点) |
| **K6** | **Process 生命周期 + Fail-loud** | `installFailLoud()` + `createProcessShutdown()` + SIGTERM/SIGINT | **新增** —— 现状**完全缺失** |
| **K7** | **环境变量加载 + 白名单** | `loadLayeredEnv()` + `BOOTSTRAP_NAMES` + `BOOTSTRAP_PREFIXES` | **新增** —— 现状 `lca/infrastructure/env/` 目录不存在 |
| **K8** | **HMR / 配置热重载** | `watchUserPatches()` + `cordis-plugin-hmr` | **新增** —— 现状没有任何热重载 |

### 决定 2:transport = `lca/plugins/transport/` 独立 namespace

新建 `lca/plugins/transport/` 目录,跟 `lca/plugins/{seam_definitions, providers, primitives, bridges, ...}` 平级。**每个 transport 是一个 plugin**:

```
lca/plugins/transport/
├── webserver/                    # transport = Starlette-based gateway
│   ├── __init__.py
│   ├── router.py                 # GatewayRouter Protocol + 实现(deepseek WebServer 形态)
│   ├── lifespan_adapter.py       # 把 starlette lifespan 桥到 kernel.run_kernel()
│   └── routes_*.py               # 4 个 routes plugin(详见 ADR-0112 修订)
├── acp/                          # transport = ACP/JSON-RPC(后续 ADR-0118)
└── cli/                          # transport = argv dispatch(后续 ADR-0119,scripts/lca-ops 可迁)
```

**关键**:transport plugin **不知道 kernel 内部**;只通过 `ctx.inject('compile_profile_result')` 或 kernel 暴露的 capability 交互。

### 决定 3:lint-imports 门禁(kernel/transport 双向禁止)

新增 `scripts/check_kernel_boundary.py`,作为 PR pipeline 阻断门禁:

```python
# scripts/check_kernel_boundary.py

# kernel 允许 import 的所有 dep
ALLOWED_KERNEL_DEPS = {
    "cordis",
    "yaml", "pydantic", "jsonschema",
    # 自身子包
    "lca_kernel.",                # 顶层包公共面
    # LCA 内部允许
    "lca/contracts/", "lca/harness/", "lca/cognition/", "lca/runtime/",
    "lca/agent/", "lca/infrastructure/",
    "lca/plugins/seam_definitions/", "lca/plugins/providers/",
}

# kernel 禁止 import 的 dep(transport / framework)
FORBIDDEN_KERNEL_DEPS = {
    # ASGI / HTTP framework
    "starlette", "fastapi", "uvicorn", "granian", "hypercorn",
    # Transport namespace(transport 反向会提供公共面)
    "gateway/",
    # Process 直接 kill / signal(K6 通过 ShutdownCoordinator 集中处理)
    "os.kill", "signal",
    # 任何 web 协议解析
    "httpx", "aiohttp", "websockets",
}

# 反向:cognition / agent / runtime / plugins 禁止 import kernel 内部模块
# 注意:必须用模块路径,不能用包前缀,否则 transport 公共面也被禁掉
FORBIDDEN_DOMAIN_DEPS = {
    "lca_kernel.source", "lca_kernel.resolve", "lca_kernel.boot",
    "lca_kernel.lifecycle", "lca_kernel.hmr", "lca_kernel.observability",
    "lca_kernel.closure", "lca_kernel.plan", "lca_kernel.env",
    # transport
    "starlette", "fastapi", "gateway/",
}

# transport 禁止 import kernel 内部模块,但允许 import 公共面
# transport 必须通过 ctx.inject 跟 kernel 交互,不能直接调 kernel 函数
FORBIDDEN_TRANSPORT_DEPS = {
    "lca_kernel.source", "lca_kernel.resolve", "lca_kernel.boot",
    "lca_kernel.lifecycle", "lca_kernel.hmr", "lca_kernel.observability",
    "lca_kernel.closure", "lca_kernel.plan", "lca_kernel.env",
    "lca_kernel.stages", "lca_kernel.trace", "lca_kernel.errors",
    # cognition/agent / runtime 不能被 transport 反向 import
    "lca.cognition", "lca.agent", "lca.runtime",
}
```

CI 触发规则:
- `lca-kernel/**/*.py` 触发 `FORBIDDEN_KERNEL_DEPS` 检查
- `lca/{cognition,agent,runtime}/**/*.py` 触发 `FORBIDDEN_DOMAIN_DEPS` 检查
- `lca/plugins/transport/**/*.py` 触发 `FORBIDDEN_TRANSPORT_DEPS` 检查
- `lca/infrastructure/**/*.py` 部分允许(纯基础设施:env/observability 等可被 kernel + transport 双方引用)

**接入**:`pyproject.toml` `[tool.lint-imports]` 加 kernel-boundary 配置 + 新增 importlinter 契约:

```toml
[[tool.importlinter.contracts]]
name = "lca-kernel-domain-isolation"
type = "forbidden"
source_modules = ["lca.contracts", "lca.infrastructure", "lca.cognition", "lca.runtime", "lca.agent"]
forbidden_modules = ["lca-kernel"]
```

(防止下层 `lca/cognition/agent/runtime/...` 反向 import kernel 内部)

### 决定 4:kernel 公开 API(单一入口)

```python
# lca-kernel/__init__.py
"""LCA Kernel — 编译 profile 到运行中进程。

8 大职责见 ADR-0115 决定 1;本模块是唯一公共面。

Public API
----------
- :func:`compile_profile`   — path → CompiledRunPlan(纯函数,无副作用,no IO)
- :func:`run_kernel`        — CompiledRunPlan → booted cordis.Context
- :func:`stop_kernel`       — graceful shutdown(SIGTERM 友好)
- :func:`run_kernel_lifespan` — AsyncContextManager 把 run_kernel 包给 ASGI lifespan

Why a dedicated module
----------------------
Kernel is the single seam where "声明文本" → "运行中进程" 的转换发生。任何
transport(Starlette / JSON-RPC / stdio)只调 :func:`run_kernel_lifespan` 或
:func:`run_kernel`;它们不直接构造 cordis Context。kernel 不知道有 transport
存在,通过 lint-imports 强制(ADR-0115 决定 3)。
"""

from lca_kernal.source import load_profile_source
from lca_kernal.resolve import resolve_profile
from lca_kernal.plan import compile_run_plan
from lca_kernal.boot import run_kernel, stop_kernel
from lca_kernal.errors import KernelError, FailLoudError
```

**Kernel 不知道有 transport**(N1):transport plugin 在 setup 里调 `ctx.inject('compile_result')`,kernel 提供这个 capability。

### 决定 5:`lca/harness/profile/` 退役(迁移路径)

旧 `lca/harness/profile/` 是 **kernel v1 的占位实现**,本次彻底迁移到 `lca-kernel/`。迁移期保留薄 compat 层:

```python
# lca/harness/profile/__init__.py(迁移期 compat,6 个月后删除)
import warnings
from lca_kernal import boot_profile, boot_resolved_profile, boot_entries
from lca_kernal import resolve_profile, compile_profile  # 新公共面

warnings.warn(
    "lca.harness.profile is deprecated, use lca_kernel instead (ADR-0115)",
    DeprecationWarning, stacklevel=2,
)

__all__ = ["boot_profile", "boot_resolved_profile", "boot_entries",
           "resolve_profile", "compile_profile"]
```

**彻底删除时间**:2027-02-28(6 个月)。

### 决定 6:`gateway/app.py` 改 thin factory

`gateway/app.py` 不再调 `boot_profile()`,**只接受一个已经 booted 的 ctx** 装配 starlette:

```python
# gateway/app.py(新版本,目标 ≤ 60 行)
"""Gateway web transport — Starlette adapter for a booted kernel context.

This module is a thin factory: it consumes a :class:`cordis.Context` produced
by ``lca-kernel.run_kernel`` and wires it into a Starlette application. The
gateway does not know how the kernel booted or which plugins it mounted; it
only reads ``app.state.ctx`` (or ``ctx_provider()``) and registers routes
through :class:`GatewayRouter`.

All route registration goes through ``lca/plugins/transport/webserver/router.py``.
``create_app`` here only wires the ASGI app and lifespan, nothing more.
"""
```

**关键**:uvicorn `--factory gateway.app:create_app` 调用方式不变,但 `create_app` 的**入参/出参/职责** 全部重写。

### 决定 7:`lca/application/api.py:set_default_ctx` 删除

```python
# lca/application/api.py(本次删除)
# 旧:
from lca.application.default_context import set_default_ctx  # 删除
from lca.application.default_context import holder as _default_ctx_holder  # 删除
# 新:全部通过 ctx.inject 拿
from lca.application.spawn import spawn_agent, spawn_team
```

迁移路径:所有 `set_default_ctx(x)` 调用改为在 application entry point 显式 `ctx = await run_kernel(...)`,然后 `await spawn_agent(ctx, ...)`。

### 决定 8:scripts/lca-ops 增加 kernel 子命令

```sh
$ lca-ops kernel boot <profile>     # 启动 kernel,不装 webserver(等价 deepseek `dsh acp`)
$ lca-ops kernel serve <profile>    # 启动 kernel + webserver transport
$ lca-ops kernel stop               # graceful shutdown
$ lca-ops kernel reload <profile>   # 触发 HMR 重载
$ lca-ops kernel compose <profile>  # dump CompiledRunPlan(供 diff / 审计)
```

实现:`lca/infrastructure/cli/cli.py` 新增 `kernel` 子命令 group,内部调 `lca-kernel.run_kernel_lifespan(...)`。

### 决定 9:**Kernel vs Plugin 边界硬约束**(kernel 直接驱动 plugin,无法 plugin 化)

本 ADR 的核心论点:**kernel 是 host,plugin 是 guest;kernel 直接驱动 plugin,这个关系本身无法 plugin 化**。这跟 ADR-0085 "一切皆插件" 是正交的:

> **ADR-0085 的 "一切皆插件" 适用范围 = "Agent 中会变化、需要替换、需要组合、需要授权或需要审计的能力"。Kernel 的职责("把声明文本变成运行中进程")不在此范围,因为没有 plugin 需要 "驱动其他 plugin";kernel 是驱动者本身,不是被驱动者。**

**Kernel-Plugin 通信唯一通道 = cordis Context**:

| 通信动作 | 调用方 | 被调用方 | 通道 |
|---|---|---|---|
| kernel 启动 plugin | `lca-kernel/boot.py:spawn_fiber` | 每个 plugin 的 `setup(ctx, config)` | `ctx.registry.plugin({name, apply, Config}, config)` + `ctx.effect(fiber.dispose)` |
| kernel 装观测 | `lca-kernel/observability.py:install_observability` | 各观测 seam plugin | `ctx.inject('evidence_store_seam')` + `ctx.provide('observability', bound)` |
| kernel 装 trace data | `lca-kernel/trace.py` | JournalEvent subscriber | `ctx.inject('journal')` + `journal.append(BootProfileResolved(...))` |
| plugin 拿 ctx 能力 | 每个 plugin setup | kernel 已 provide 的能力 | `ctx.inject('compile_result')` / `ctx.inject('agent_registry')` |
| plugin 反向通知 kernel | plugin 通过 manifest | kernel 在 boot 期收集 | `ctx.provide('xxx', value)` + `ctx.effect(disposer, label=...)` |

**反模式清单**(违反会被 lint-imports 阻断):

1. **kernel import 任何 plugin 路径**(`lca/plugins/<name>.py`)—— 违反:kernel 必须通过 YAML/profile 装载 plugin,不能 import 名字
2. **plugin import kernel 内部模块**(`lca_kernel.source / resolve / boot / lifecycle / hmr / observability / closure / plan / env`)—— 违反:plugin 只跟 ctx + 公共面交互
3. **plugin 之间直接 import** —— 违反:必须通过 `ctx.inject('xxx')` 交互,不直接 import 另一个 plugin
4. **kernel 有 module-level 单例**(`_default_ctx_holder` 等)—— 违反 ADR-0062 + ADR-0115 决定 7
5. **transport 反向调用 cognition/agent 业务**(`lca/plugins/transport/webserver/...` 直接 `from lca.cognition import Brain`)—— 违反:transport 只通过 ctx.inject('agent_registry') 拿抽象

**为什么 kernel 无法 plugin 化**:
- "启动 plugin 的东西" 不能由 plugin 实现,否则循环依赖(kernel → plugin → kernel)
- 这是架构层面的事实,不是设计偏好;deepseek `app-boot` 同样是 npm workspace 顶层包,不是 plugin
- 但 kernel **本身是可替换的**:可以写一个 `lca-kernel-debug/`(test-only kernel,with null seams)、`lca-kernel-cloud/`(云部署 kernel,集成云观测)—— **kernel 是单进程单实例的,plugin 是多实例的,这是本质差异**

### 决定 10:**游离于插件之外**的完整清单(无法 plugin 化的 4 类,其余都 plugin 化)

用户问题"还有那些游离于插件之外"。本 ADR 锁定答案:**只有 4 类东西游离于 plugin 之外,其余必须 plugin 化**。

#### A. 游离层(无法 plugin 化,共 4 类)

| # | 类型 | 例子 | 理由 |
|---|---|---|---|
| **A1** | **Kernel 自身** | `lca-kernel/` 顶层包 | "启动 plugin 的东西" 不能由 plugin 实现(循环依赖) |
| **A2** | **Composition Root** | `lca/application/`(L4 组合根,组装 Agent / Team);`apps/cli`(deepseek 的 profile-boot) | "选择 bundle + 装配 plugin 树"是单实例决策,不是 plugin 能力 |
| **A3** | **Vendored 框架** | `cordis/`(vended, kernel 借用其 lifecycle);`pydantic`(vended) | 框架由 upstream 维护,LCA 只是 user,不能 plugin 化 |
| **A4** | **Python stdlib + 基础设施** | `os` / `asyncio` / `signal` / `threading` / `pathlib` / `json` / `yaml` | 语言层;`lca/infrastructure/env/` 是 A4 的延伸(纯静态常量 + 纯函数,不调 os.environ) |

#### B. 必须 plugin 化的层(任何不是 A1-A4 的都走 plugin)

| 类别 | plugin 例子 |
|---|---|
| **观测 seam** | `lca-observability-assembly` / `lca-journal-backend` / `lca-evidence-store-seam` |
| **观测 sink** | `lca-tracer-backend` / `lca-metrics-backend` / `lca-cost-meter` |
| **能力 seam** | `lca-llm-service` / `lca-tools-service` / `lca-memory-service` / `lca-sandbox-service` |
| **能力 provider** | `lca-llm-resolver` / `lca-tools-provider` / `lca-sandbox-provider` |
| **Transport** | `lca-gateway-router` / 4 routes / `lca-acp-transport` / `lca-cli-dispatch` |
| **生命周期钩子** | `lca-fail-loud-handler` / `lca-shutdown-coordinator` / `lca-env-loader`(K7 plugin 入口,跟 kernel facade 分离) |
| **可观测事件** | `BootJournalEvent`(typed dataclass,不是 plugin;但产生它们的 hook 是 plugin) |
| **Phase executor / control slot** | 11 个 control slot contributions / 6 个 PhaseExecutor |
| **Team / Agent / Role** | `lca-agent` / `lca-team` / `lca-role-library` |
| **业务 tool** | `tool-bash` / `tool-web-search` / `tool-fs` / `tool-subagent` |
| **业务 mode** | `mode-solo` / `mode-team` / `mode-creator` / `mode-code` |
| **业务 Adapter** | MCP adapter / A2A adapter / OpenAI compat adapter / LobeHub adapter |

#### C. 不能 plugin 化的边界约束(强约束)

| 边界 | 谁不能做 | 谁可以做 |
|---|---|---|
| **kernel 不能 plugin 化** | 不存在"lca-kernel plugin",kernel 是 host | plugin 在 setup 里被 kernel 启动 |
| **composition root 不能 plugin 化** | 不存在"lca-application plugin",它是 spawn() / run() 入口 | agent / team 由它 spawn,但 spawn 本身是 L4 责任 |
| **public Protocol 不能 plugin 化** | contracts/Protocol 不能 plugin 化(只描述能力,不实现) | seam / provider 由 plugin 实现 |
| **typed dataclass 不能 plugin 化** | JournalEvent / CompiledRunPlan / Stage / BootTrace 不是 plugin | 但**生成**它们的 hook 是 plugin |
| **Process 信号不能 plugin 化** | `signal.SIGTERM` 由 kernel 集中处理 | 任何 plugin 想响应 SIGTERM 必须 `ctx.inject('shutdown_coordinator').on_shutdown(handler)` |
| **Process 单例不能 plugin 化** | `_default_ctx_holder` 这类 module-level 单例**禁止** | 任何状态都走 ctx |
| **vendored 框架不能 plugin 化** | cordis / pydantic / Cosmokit 不属于 LCA,不能 plugin 化 | LCA 通过 Protocol + Adapter 适配 vendored 框架 |

#### D. 一个常见误解澄清:"decorator 装饰的函数 = plugin" 不等于 "plugin 可无限嵌套"

LCA 的 `@plugin` 装饰器标记的是一个**宿主单元**,它必须在 Profile/Bundle 里被**显式列出**才会被装载。**plugin 不装载另一个 plugin**;plugin **声明 requires**,kernel **按拓扑序**装载所有 plugin。**"plugin 驱动 plugin" 是 kernel 的责任,不是 plugin 之间的事**。

## 对既有 ADR 的修订

### 修订 ADR-0111(启动编译化)

| 原 ADR-0111 内容 | 本 ADR 修订 |
|---|---|
| `lca/harness/profile/compilation/` 子包 | → `lca-kernel/` 顶层包(独立,跟 `lca/` 平级) |
| 6 文件拆分 | → 12 文件(8 大职责 + stages + trace + errors + __init__) |
| `boot→compile` 改名 | **删除改名**,保留 `boot_profile / boot_resolved_profile / boot_entries` 公共 API(评审一致反对改名) |
| `_install_observability` 双源 | → `lca-kernel/observability.py` 唯一装配点 + `lca-kernel/trace.py` 独立 trace 数据 |
| `invariant.py` | **删除**(评审 YAGNI,合并到 `@plugin` 装饰器后续 ADR) |

### 修订 ADR-0112(Gateway 路由 plugin 化)

| 原 ADR-0112 内容 | 本 ADR 修订 |
|---|---|
| `lca/plugins/gateway/` 目录 | → `lca/plugins/transport/webserver/` |
| `LcaGatewayServer` Protocol | → `LcaGatewayRouter` Protocol(命名宪法 + 准确定义) |
| `lca-gateway-server` plugin id | → `lca-gateway-router` |
| 8 个 routes plugin | → **4 个**:`routes_health_options` / `routes_runs_sessions` / `routes_openai_compat_files` / `routes_device` |
| `routes_openai_shim.py` | → `routes_openai_compat.py`(禁词 shim 替换) |
| `gateway/app.py` 瘦身到 ≤ 200 行 | → `gateway/app.py` thin factory ≤ 60 行 |

### 合并 ADR-0113 + ADR-0114 → ADR-0116

| 原 ADR-0113 + 0114 | → ADR-0116 |
|---|---|
| `TraceSink / JsonlFileSink / JournalSink` 三个新概念 | **全部砍掉**(已有 `traces/lca_trace.jsonl` + `bundles/observability-default.yaml` 覆盖) |
| `traces/boot/*.jsonl` 独立文件路径 | → 复用 `traces/lca_journal.jsonl` |
| `lca-ops trace boot` 子命令 | → `lca-ops journal logs -r <run_id>` 复用现有 CLI（按 `traces/runs/<id>/events.jsonl` SSOT 直读）|
| 5 个 typed JournalEvent | → 3 个 typed (`BootProfileResolved / BootPluginFiberSpawned / BootObservabilityAssembled`) + 2 个走 `RuntimeObserved` 复用 ADR-0063 |

### 新增 ADR-0117(Process 生命周期 + Fail-loud + Env 白名单)

K6 + K7 单独成 ADR,见 [ADR-0117](./0117-process-lifecycle-env-whitelist.md)。本 ADR 不重复内容,只在决定 1 表里引用。

## 与既有 ADR 的衔接

| 既有 | 衔接 |
|---|---|
| ADR-0062 插件运行时收口 | 本 ADR 是 ADR-0062 §4 "Cordis Fiber Boot + L4 严格闭合" 的具体实现 |
| ADR-0083 W1 主链收紧 | 本 ADR 是 W1 的"kernel 顶层化"具体落地 |
| ADR-0085 插件哲学 | 本 ADR 把"启动过程也是 plugin 化"哲学推到 kernel/transport 二元论 |
| ADR-0105 包组织纪律 | 本 ADR 锁定 `lca-kernel/` ≤ 13 文件 + 每个文件 ≤ 200 行 |
| ADR-0106 命名宪法 | `lca-kernel/` 是 group 名(隐含 kernel),子文件名是 subject 名(stages/boot/...);函数前缀用 §8.1 表(`compile / run / install / spawn / load / watch`) |
| ADR-0103 锁定面 | `gateway/app.py` 是 transport,wire-shape 锁定仍生效 |

## CI 门禁

新增 / 复用:

- `scripts/check_kernel_boundary.py`(新建):决定 3 的双向 lint-imports 门禁;扫所有 `lca-kernel/**/*.py` + `lca/{cognition,agent,runtime}/**/*.py` + `lca/plugins/transport/**/*.py`。
- `tests/lca_kernel/`(新建):8 大职责对应的 8 个测试文件,每个职责至少 1 个 contract test + 1 个 fail-loud test。
- `tests/lca_kernel/test_boundary.py`(新建):kernel 模块只能 import 允许的 dep,transport 反向不可 import kernel 内部。
- `tests/gateway/test_thin_factory.py`(新建):`create_app()` ≤ 60 行,只装配 starlette + 读 `app.state.ctx`,不调 `boot_profile`。
- `tests/test_kernel_no_transport_knowledge.py`(新建):`grep -rE 'starlette|fastapi|uvicorn' lca-kernel/` 必须为空。
- `scripts/check_package_size.py`(ADR-0105):`lca-kernel/` ≤ 13 文件,每个 ≤ 200 行。
- `scripts/check_function_verb_prefix.py`(ADR-0106 §8.1):`lca-kernel/` 内函数必须以 `compile / run / install / spawn / load / watch / stop` 等前缀开头。

## 放弃的方案

- **保持 `lca/harness/profile/` 不动,只在内部拆文件**:违反 ADR-0105 "子包规模"约束(240 行文件 > 1500 行上限本身未触犯,但跨 8 大职责的职责分离要求新顶层包)。
- **`lca-kernel/` 拆为多个子包(`lca-kernel-profile/`、`lca-kernel-runtime/` ...)**:增加不必要的层级;deepseek `app-boot` 单包 829 行,LCA 12 文件 ≈ 300 行更轻,不需要进一步拆。
- **kernel 不做 K6 / K7 / K8(借鉴 deepseek 完整 8 大职责)**:K6 Fail-loud 是生产稳定性硬需求,K7 BOOTSTRAP_NAMES 是 deepseek 的安全模式,K8 HMR 是 deepseek 长期运行的标配,只做 K1-K5 等于"半个 kernel"。
- **`lca/application/` 不动**:ADR-0062 已经否决 module-level 单例,但 `lca/application/api.py` 还在 `set_default_ctx`,这是历史遗留债,本 ADR 一并清理。
- **`gateway/` 不迁到 `lca/plugins/transport/`**:`gateway/` 是个 Python 包目录,跟 `lca/plugins/transport/webserver/` 的 plugin 概念混淆;transport 是 plugin namespace,跟 LCA 内部 `gateway/` 物理包分开。

## 后果

正面:
- kernel/transport 边界由 `lint-imports` 强制,违反即阻断 PR,长期演化有保证
- 8 大职责跟 deepseek 1:1 对齐,新人读 `lca-kernel/` 立刻理解 LCA 跟业界先进实践的关系
- 4 个新 ADR + 修订 4 个旧 ADR 形成完整治理链,可追溯
- transport 真正可替换:JSON-RPC / stdio CLI / gRPC 加新 transport 都是 `lca/plugins/transport/<name>/`,不动任何现有代码
- `lca/application/api.py:set_default_ctx` 删除,清掉历史 ADR-0062 违反债

负面:
- 12 文件新顶层包 + 5 旧文件迁移 ≈ 5 PR,改动面较大,但每 PR 独立可 merge
- `lca-kernel/` 必须等 `lca/infrastructure/env/`(K7)+ `lca-kernel/lifecycle.py`(K6)就绪后才完整,中间状态按 §决定 5 兼容层过渡
- transport 抽象 vs 现有 `gateway/` 物理包**两层结构**,新人需要在 `lca/plugins/transport/webserver/` 和 `gateway/` 之间跳转;Plan 通过 docstring 路径说明缓解

## 索引

| 主题 | 文档 |
|---|---|
| deepseek app-boot | `~/deepseek-harness/packages/boot/app-boot/src/index.ts` |
| deepseek host-webserver | `~/deepseek-harness/packages/host/webserver/src/index.ts` |
| deepseek apps/cli | `~/deepseek-harness/apps/cli/src/{bin,profile-boot}.ts` |
| deepseek BOOTSTRAP_NAMES | `~/deepseek-harness/packages/boot/app-boot/src/index.ts:51-99` |
| 现行 kernel 占位 | `lca/harness/profile/boot.py` (240 行) |
| 现行 lifespan 越界 | `lca/harness/profile/lifespan.py` (200 行) |
| 现行 gateway 混合 | `gateway/app.py` (439 行) |
| 现行 set_default_ctx 违反 | `lca/application/api.py:31-35` + `lca/application/default_context.py` |
| 插件哲学 | [ADR-0085](./0085-plugin-everything-explained.md) |
| DeepSeek Harness 实施计划 | [ADR-0083](./0083-deepseek-harness-plugin-implementation-plan.md) |
| 启动编译化(本次修订) | [ADR-0111](./0111-startup-compilation-as-subpackage.md) |
| Gateway 路由(本次修订) | [ADR-0112](./0112-gateway-routes-as-plugins.md) |
| Process 生命周期(本次新立项) | [ADR-0117](./0117-process-lifecycle-env-whitelist.md) |
| 启动事件词表与可观测性收敛 | [ADR-0116](./0116-boot-event-observability-convergence.md)(合并原 0113+0114) |
| 包组织纪律 | [ADR-0105](./0105-package-organization-discipline.md) |
| 命名宪法 | [ADR-0106](./0106-naming-constitution.md) |
| Locked-surface | [ADR-0103](./0103-locked-surface-and-port-policy.md) |