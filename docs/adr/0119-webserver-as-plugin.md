# ADR-0119: Webserver 完全 Plugin 化(对齐 deepseek-harness 范式)

> **状态：** Proposed
> **日期：** 2026-08-31
> **Supersedes:** [ADR-0115](./0115-kernel-transport-boundary.md) 决定 6(`gateway/app.py` thin factory) + 决定 8(`lca-ops kernel serve` 子命令——本 ADR **彻底删除**,LCA 进程由 `python -m lca_kernel serve` 直接管)
>
> **配套 ADR:** [ADR-0085](./0085-plugin-everything-explained.md) 插件哲学 · [ADR-0112](./0112-gateway-routes-as-plugins.md) Gateway 路由(部分沿用)· [ADR-0115](./0115-kernel-transport-boundary.md) Kernel/Transport 边界(本 ADR 修订)· [ADR-0117](./0117-process-lifecycle-env-whitelist.md) K6 进程生命周期
>
> **落地方案:** `docs/design/2026-08-31-lca-web-server-plugin-design.md`(Step 3 出)

## 背景

[ADR-0115](./0115-kernel-transport-boundary.md) 决定 6 把 `gateway/app.py` 砍到 ≤ 60 行"thin factory",决定 8 规定 `lca-ops kernel serve` 应真执行 uvicorn。**两个决定都未真正落地**:

| 决定 | 设计意图 | 实际状态 |
|---|---|---|
| 决定 6 "thin factory ≤ 60 行" | `gateway/app.py` 只装配 Starlette + 读 `app.state.ctx` + 装路由 | 89–102 行,含 K0 注释膨胀;**核心问题是 `gateway/app.py` 凌驾在 kernel 之外,先于 kernel 装路由而非 plugin 化** |
| 决定 8 "`lca-ops kernel serve` 真执行" | kernel 进程级入口自己起 uvicorn | 当前只 print `uvicorn gateway.app:create_app --factory` 指令,**真进程由 `scripts/serve_observability.py` 起 uvicorn 接管**(本 ADR 决定 4 改为:`lca-ops` 完全不管理 LCA 进程,LCA 入口改为 `python -m lca_kernel serve`,uvicorn 是 `lca-web-server` plugin 内部细节) |

更深的架构问题是:webserver 这一能力**没有作为 plugin 存在**。

- 现状:webserver 进程生命周期 = `gateway/app.py:create_app` + uvicorn 命令行(在 LCA 进程外) + `gateway/bootstrap.py:install_gateway_state`(游离函数,无 plugin 包装) + 4 个 routes plugin(攒 Route 列表)
- 应有:webserver 是个 `lca-web-server` plugin(L1 Service),`ctx.provide("web_server", self)`,`ctx.inject("web_server")` 拿实例,`await web_server.serve()` 阻塞;**所有 transport 资源都通过 ctx 注入,没有游离代码**

deepseek-harness 已实现该范式(`packages/host/webserver/src/index.ts:WebServer extends Service`),无 `gateway/` 目录。

用户原话:
> "重构吧 我觉得一切是从内核驱动 其他的都是被驱动的插件 网站后端也就是插件而已"
> "gateway 能不改名还是怎么 到底名字合适吗 放在这么高层次目录,其实就是一个 plugin,然后这个 plugin 去读 cordis 合适吗 deepseek harness 应该参照他的做法 彻底对齐改好 插件化驱动才对吧"

## 决定

### 决定 1:`gateway/` 目录整个删除,webserver 升格为 L1 Service plugin

- 删除 `gateway/app.py`、`gateway/bootstrap.py`、`gateway/__init__.py` 整个 `gateway/` 目录
- 新增 `lca/plugins/transport/webserver/server.py`:`LcaWebServer` 类(对齐 deepseek `WebServer extends Service`)+ `@plugin(id="lca-web-server", provides=("web_server",), requires=("gateway_router", "file_store", "run_port"), layer="L1", kind=PluginKind.SERVICE)`
- `LcaWebServer` 自我管理:
  - `__init__(ctx, config)`:构造 Starlette + 装 routes plugin 提供的 `Route` 列表
  - `serve(host, port)` 协程:起 `uvicorn.Server(config)`,`ctx.effect(server.shutdown)` LIFO 收口
  - `ctx.provide("web_server", self)`(在 `@plugin setup` 内调)

### 决定 2:`install_gateway_state` 改成 `lca-gateway-bootstrap` plugin

- 删除 `gateway/bootstrap.py`
- 新增 `lca/plugins/transport/webserver/bootstrap.py`:`@plugin(id="lca-gateway-bootstrap", provides=("run_port", "device_registry", "device_hub", "file_store_bootstrap"), requires=("file_store", "device_settings"), layer="L2", kind=PluginKind.PROVIDER)`
- 内容:把原 `install_gateway_state(app, ctx)` 改成 plugin `setup(ctx, config)`,把 `LocalFileStore / DeviceRegistry / DeviceHub / RunRegistry` 装到 ctx(**不**依赖 Starlette 入口)

### 决定 3:`lca_kernel/cli.py:serve` 是 LCA 进程入口(严格对齐 deepseek `apps/cli/src/profile-boot.ts:runProfile`)

**核心原则**:`lca_kernel/cli.py:serve` 是 `python -m lca_kernel serve` 这一行启动的 LCA 进程内部**唯一**入口。它**严格镜像** deepseek `runProfile` 的 9 步,每一步都不能少:

| 步骤 | deepseek `runProfile` 做了 | `lca_kernel/cli.py:serve` 应做 | 当前 LCA 状态 |
|---|---|---|---|
| 1. 装 env 快照 | `loadLayeredEnv('lca_kernel')` → `EnvSnapshot` → `hostCtx.provide("env_snapshot", snapshot)` | 调 `lca.infrastructure.env.bootstrap.load_layered_env(bin_name="lca_kernel", dir=cwd)` → `hostCtx.provide("env_snapshot", snapshot)`(**插件可 `ctx.inject("env_snapshot")` 读 .env 值**) | ⚠️ K7 已有 facade 但**没人调** |
| 2. 解析 profile | `composeProfile(profile, patchFiles)` | `run_kernel` 内部 `load_profile_source + resolve_profile` | ✅ |
| 3. 装 cordis Context | `new Context()` + `await ctx.plugin(Loader)` + `mountRootInclude(...)` | `run_kernel_lifespan` 内部 `boot_resolved_profile + _boot_context` | ✅ |
| 4. host provide 钩子 | `prepare(hostCtx)` 在 plugin 装载**之前**调 | **新增** `lca_kernel.cli._host_prepare(ctx, profile_path, env_snapshot, args)`——在 `run_kernel_lifespan` 启动之前 `ctx.provide("env_snapshot", ...)`,然后 lifecycle 内部 `ctx` 创建后调一次 prepare | ❌ **缺** |
| 5. 装 SIGTERM handler | `process.on('SIGTERM', () => interrupt(0))` **装在 boot 之前**,覆盖 startup window | **修正**:`run_kernel_lifespan` 内部 K3 之后才装 SIGTERM,boot 阶段没守护——本 ADR 决定 3 要求 `lca_kernel/cli.py:serve` **先 `install_signal_handlers + install_fail_loud` 再 `run_kernel_lifespan`**,**这跟 deepseek `runProfile` 的顺序一致** | ❌ **错** |
| 6. 装 fail-loud | `installFailLoud(NAME, process, ...)` | 同(走 K6 `install_fail_loud`) | ✅ |
| 7. 装 webserver plugin | Loader 按 DAG 排序,`ctx.webServer = new WebServer(ctx, config)`,`Service.init` 调 `createServer + server.listen` | `lca-web-server` plugin `@plugin setup` 协程里 `await uvicorn.Server(...).serve()` 监听 | ✅ |
| 8. 进程挂着 | `bin.ts:await runProfile(...)` 后不退出 | `await asyncio.Event().wait()` 等 SIGTERM | ✅ |
| 9. SIGTERM 退出 | `process.on('SIGTERM', ...)` → `app.current?.fiber.dispose()` → `sys.exit(0)` | K6 `DefaultShutdownCoordinator.shutdown(0)` → LIFO dispose → `sys.exit(0)` | ✅ |

**修正后的 `lca_kernel/cli.py`**(严格镜像 deepseek `runProfile` 9 步):

```python
# lca_kernel/cli.py(新)— LCA 唯一进程入口,严格对齐 deepseek runProfile 9 步
from __future__ import annotations
import argparse
import asyncio
import sys
from typing import NoReturn

from lca_kernel import run_kernel_lifespan
from lca_kernel.lifecycle import create_shutdown_coordinator, install_signal_handlers, install_fail_loud
from lca.infrastructure.env.bootstrap import load_layered_env
from lca.contracts.atoms.env_snapshot import EnvSnapshot  # K7 facade 返回类型


def serve(profile_path: str, host: str, port: int) -> int:
    """LCA 进程入口。类比 deepseek apps/cli/src/profile-boot.ts:runProfile。"""
    # 步骤 1: 装 env 快照(在 run_kernel_lifespan 之前,任何 plugin 都能 ctx.inject("env_snapshot"))
    env_snapshot: EnvSnapshot = load_layered_env(bin_name="lca_kernel", dir=".")

    # 步骤 5+6: 装 SIGTERM/SIGINT + fail-loud(在 boot 之前,覆盖 startup window,跟 deepseek runProfile 一致)
    coordinator = create_shutdown_coordinator(kernel=None)  # kernel 后面再 bind
    install_signal_handlers(coordinator)
    install_fail_loud(coordinator)

    async def main() -> int:
        async with run_kernel_lifespan(profile_path) as state:    # 步骤 2+3+4+7:K1-K6 装 plugin 树
            ctx = state["ctx"]
            # 步骤 4: host provide(env_snapshot + cmdline + bounded exit request,跟 deepseek prepare 一样)
            ctx.provide("env_snapshot", env_snapshot)
            ctx.provide("cmdline", {
                "profile": profile_path,
                "host": host,
                "port": port,
                "exit": lambda code: sys.exit(code),
            })
            # bind kernel 给 coordinator(供 SIGTERM 触发 LIFO dispose)
            coordinator._kernel = ctx  # type: ignore[attr-defined]
            # 步骤 8: 进程挂着不退
            await asyncio.Event().wait()
        return 0

    return asyncio.run(main())


def main() -> NoReturn:
    parser = argparse.ArgumentParser(prog="lca_kernel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve_p = sub.add_parser("serve", help="启动 LCA 进程(对齐 deepseek runProfile 9 步)")
    serve_p.add_argument("--profile", required=True, help="YAML profile 路径")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.cmd == "serve":
        sys.exit(serve(args.profile, args.host, args.port))
    raise SystemExit(f"unknown cmd: {args.cmd}")
```

**对照 deepseek `runProfile` 9 步的差异修正清单**:

| deepseek | LCA 现状 | 本 ADR 决定 3 修正 |
|---|---|---|
| `loadLayeredEnv` 在 runProfile 第一行 | K7 facade 存在但**没人调** | `lca_kernel/cli.py:serve` 第一行调 |
| `process.on('SIGTERM')` 装在 `boot()` 之前 | K6 `install_signal_handlers` 装在 K3 之后 | `serve` 入口处**先装钩子再 run_kernel_lifespan** |
| `prepare(hostCtx)` 在 plugin 装载前调 `hostCtx.provide(...)` | K3 内部不调任何 prepare 钩子 | `serve` 在 `async with run_kernel_lifespan(state) as state` 拿到 ctx 后**第一行**调 `ctx.provide("env_snapshot", ...)` |
| `ctx.fiber.dispose()` + `sys.exit(0)` | K6 `coordinator.shutdown(0)` | 同(已对齐) |

**修正 4 个差异后,LCA 进程 = deepseek 范式**。

### 决定 4:`lca-ops` **不再管理 LCA 进程**(对齐 deepseek——bin = 唯一进程)

**核心原则**:LCA 进程 = 唯一 Python 进程。LCA 进程的生命周期由它自己管(挂 SIGTERM/SIGINT 钩子 → K6 ctx.dispose),**不需要**外部 ops 工具协调。

- `lca/infrastructure/cli/commands/kernel.py:kernel_serve` 当前只 print uvicorn 命令 → **删除**(`lca-ops` 不再有 `kernel serve` 子命令)
- `lca/infrastructure/cli/services/gateway.py`:**删除 `start` / `stop` / `restart` 实现**;LCA 进程是前台进程,直接 `python -m lca_kernel serve` 起 + Ctrl-C 停,**ops 工具不再"代管"它的生命周期**
- `lca-ops.yaml` 的 `gateway.*` 整段:**删除**。LCA 进程不再写进平台 SSOT,只由用户终端起
- `scripts/serve_observability.py` **删除**
- `lca/infrastructure/cli/services/gateway.py` 类本身:**整个文件删除**;`lca/infrastructure/cli/commands/services.py:gateway` 装饰的 typer 命令:**删除**
- `scripts/lca-ops` 的 help 输出里**删除 `gateway` 子命令**;`lca-ops` 只剩 `infra / lobehub / daemon / onlyboxes / status / heal / logs / dev / stop`(注:`dev` 仍可起 LCA 进程作为整套开发环境的一部分,但**用 subprocess 短跑**,不作为"长跑"管)

**LCA 进程入口**:
```sh
# 唯一的"起 LCA"命令
uv run python -m lca_kernel serve --profile profiles/web-standard.yaml --host 127.0.0.1 --port 8765
# Ctrl-C / SIGTERM → K6 graceful shutdown → sys.exit
```

**`lca_kernel/cli.py` 内部**:
```python
import asyncio
from lca_kernel import run_kernel_lifespan

def serve(profile_path: str, host: str, port: int) -> int:
    """LCA 进程入口。对齐 deepseek apps/cli/src/bin.ts + profile-boot.ts:runProfile。"""
    async def main() -> int:
        async with run_kernel_lifespan(profile_path) as state:        # K1-K6 装 plugin 树
            ctx = state["ctx"]
            # lca-web-server plugin 已在 setup 协程里 await listen;
            # 这里 await 一个永久事件,让 LCA 进程挂着不退
            await asyncio.Event().wait()
        return 0
    return asyncio.run(main())
```

**为什么 `lca-ops` 不再管 LCA 进程**(对齐 deepseek 哲学):
- 外部 harness CLI既是 CLI 也是 LCA 进程的入口;LCA 进程 = bin 进程,SIGTERM 自然退
- LCA 现状是 "LCA 进程" 被 "uvicorn 进程" 套娃包装,所以需要 `lca-ops` 当中间人协调两个进程的生死
- **重构后 uvicorn 不再是外壳**——它是 `lca-web-server` plugin 内部细节,LCA 进程 = 唯一进程
- 一个进程 = 一个入口 = 用户的 shell 管生命周期。不需要 ops 工具介入
- `lca-ops` 退回到"管平台外部服务" 的本职:管 lobehub (Next.js dev server)、infra (postgres/redis docker)、daemon (sandbox-user CLI connect)、onlyboxes (worker runtime)

**前后对比**:
| 操作 | 旧 | 新 |
|---|---|---|
| 起 LCA | `./scripts/lca-ops gateway start` (spawn uvicorn) | `python -m lca_kernel serve` (前台) |
| 关 LCA | `./scripts/lca-ops gateway stop` (杀 uvicorn) | Ctrl-C / SIGTERM (LCA 进程自己 dispose) |
| 重启 LCA | `./scripts/lca-ops gateway restart` | 同上 shell 重起 |
| 状态 | `./scripts/lca-ops gateway status` | `ps aux | grep lca_kernel` |
| 平台 ops | `lca-ops` 仍是入口(管 lobehub/infra/daemon/onlyboxes) | 同上(LCA 进程不归它管) |

### 决定 5:`pyproject.toml` importlinter 契约更新

- **删除** contract 5 `plugins:不得依赖 gateway`(`gateway/` 目录已删)
- **保留** 现有 `transport-isolation` / `kernel-domain-isolation` 契约
- **新增** `lca_kernel-no-uvicorn` contract:扫描 `lca_kernel/` 模块不得 import `uvicorn` / `starlette` / `fastapi`(以防 kernel 未来被污染)
- 现有 `lca_kernel-no-uvicorn` 类检查已在 `tests/lca_kernel/test_boundary.py` 中存在(12 项),不重复添加

### 决定 6:13 个测试改入口

- 用 `from gateway.app import create_app` 的 13 个测试改为从 `from lca_kernel.cli import build_asgi_app`(新 helper,内部 run kernel + 拿 `web_server.app`)拿 ASGI app
- 新增 `tests/lca_plugins/transport/webserver/test_server_plugin.py`:`LcaWebServer.serve()` 端到端 + 真实 fetch
- 新增 `tests/lca_plugins/transport/webserver/test_bootstrap_plugin.py`:`lca-gateway-bootstrap` 装到 ctx 后所有 capability 可读
- 删除 `tests/gateway/test_thin_factory.py`(因 `gateway/app.py` 不再存在,`thin factory` 概念被 `lca-web-server` plugin 替代)
- 删除 `tests/test_gateway_lazy_reexport.py`(因 `gateway/__init__.py` 不再存在)

## 命名约定(对齐 deepseek 朴素命名)

| deepseek-harness | LCA 现状 | LCA 重构后 |
|---|---|---|
| `packages/host/webserver/` | `gateway/app.py` + `lca/plugins/transport/webserver/` | **`lca/plugins/transport/webserver/server.py`**(webserver 升格为主) |
| `class WebServer extends Service` | 散落在 `gateway/app.py` + `gateway/bootstrap.py` | **`LcaWebServer` 类**(单文件单一类) |
| `ctx.webServer` | `app.state.ctx` + `app.state.gateway_router` | **`ctx.web_server: LcaWebServer`**(module augmentation) |
| `apps/cli/src/profile-boot.ts` | `scripts/serve_observability.py` | **`lca_kernel/cli.py`**(python 镜像,类比 `apps/cli/src/bin.ts` + `profile-boot.ts:runProfile` 合一) |
| `Service.init` 生命周期钩子 | uvicorn 命令行起 server | **`LcaWebServer.serve()` 协程** |

## 与既有 ADR 的衔接

### 对 ADR-0115 决定 6 的修订

- 旧:`gateway/app.py` 改 thin factory ≤ 60 行
- 新:**删除 `gateway/app.py`**;webserver 是 L1 Service plugin,自管 Starlette + uvicorn + 路由注册 + dispose

### 对 ADR-0115 决定 8 的修订

- 旧:`lca-ops kernel serve` 应真执行 uvicorn
- 新:`lca-ops kernel serve` 通过 `subprocess.Popen(["uv", "run", "python", "-m", "scripts_lca_kernel", "serve"])` 真执行;`lca_kernel.cli:serve()` 是 K0 入口(类似 deepseek `apps/cli/src/profile-boot.ts`)

### 对 ADR-0112 的沿用

- ADR-0112 已规定 4 个 routes plugin + `lca-gateway-router` SEAM,**全部保留**
- 本 ADR 增 `lca-web-server`(主) + `lca-gateway-bootstrap`(游离代码搬家)

### 对 ADR-0117(K6)的沿用

- K6 `lca_kernel/lifecycle.py:run_kernel_lifespan` 提供 SIGTERM/SIGINT 守护 + fail-loud
- 本 ADR 在 `lca_kernel/cli.py` 中调用 `run_kernel_lifespan`,K6 机制不变

## CI 门禁

- `tests/lca_kernel/test_boundary.py` 现有 12 项 + `lca_kernel/` 不 import `uvicorn`(`grep -rE 'import uvicorn|from uvicorn' lca_kernel/` 必须为空)
- `tests/lca_plugins/transport/webserver/test_server_plugin.py`(新建):`LcaWebServer.serve()` + 真实 fetch + dispose
- `tests/lca_plugins/transport/webserver/test_bootstrap_plugin.py`(新建):`lca-gateway-bootstrap` 装到 ctx 后 capability 可读
- `tests/lca_plugins/transport/webserver/test_*.py`(已存在的 4 个 routes + 1 个 router 测试)继续全过
- `pyproject.toml` importlinter 全过
- `gateway/` 目录必须不存在(`! [ -d gateway ]` 在 CI 守)
- `uv run pytest tests/lca_kernel/`:所有 kernel 测试继续过(包括 K3 boot 事件顺序)
- `uv run pytest tests/`:全量测试过
- `uv run python -m lca_kernel serve --profile profiles/web-standard.yaml` 起 LCA 进程,`curl :8765/health` 200,Ctrl-C 后 K6 触发 graceful shutdown
- `python -m lca_kernel serve --profile profiles/web-standard.yaml` 能独立启动

## 放弃的方案

### 方案 A:把 `gateway/app.py` 改成 ≤ 60 行 thin factory(原计划 Step 1-4)

理由放弃:用户明确要求**彻底**对齐 deepseek,**不留过渡**。原方案的"两步过渡"(Step 2 双路径并存 → Step 3 改 thin factory → Step 4 删除 `bootstrap.py`)违反 "plugin-everything 第一性原理"。彻底方案一个原子 PR 到位,反而减少分支复杂度。

### 方案 B:用 ASGI 中间件做 kernel 注入(不引入 webserver plugin)

理由放弃:ASGI middleware 不能 listen 端口,不能 LIFO dispose,不能 cordis effect 收口,违反 deepseek 范式。

## 后果

### 积极后果

- 真正实现 "plugin-everything",与 deepseek 范式完全对齐
- `gateway/` 目录删除,顶层目录结构更干净
- `lca-web-server` 可被替换(测试用 in-process webserver、生产用 uvicorn)
- K6 `run_kernel_lifespan` 守护的不再是 Starlette+uvicorn 进程,而是"plugin 树 + webserver plugin"——职责更清晰
- `lca-ops kernel serve` 第一次真正落地(ADR-0115 决定 8 一年未实现)

### 风险

| 风险 | 概率 | 缓解 |
|---|---|---|
| 13 个测试改 import 路径漏改 | 高 | Step 2 前 `grep -rln 'from gateway.app' tests/`,一次性列清单;每个改完跑对应测试 |
| uvicorn + lifespan 嵌套导致 K3 boot 事件 flush 时序错乱 | 低 | 跑 `tests/lca_kernel/test_boot_events_emitted.py` 验证 3 个事件按预期顺序 |
| `lca-ops` 旧 help 输出仍带 `gateway` 子命令 | 中 | Step 2 同时改 `scripts/lca-ops` bash 注释 + `lca.infrastructure.cli.services.gateway.py` 整个文件删除 |
| `lca_kernel.run_kernel_lifespan` 已有 132 测试,Step 2 改动 lifespan 行为可能影响 K6 测试 | 中 | 跑 `tests/lca_kernel/test_lifespan.py` + `tests/test_profile_lifespan_concurrency.py` 验证 K6 行为不变 |

## 索引

- **决定 1 落地:** `lca/plugins/transport/webserver/server.py` + `bundles/web-app.yaml` 加 `lca-web-server` entry
- **决定 2 落地:** `lca/plugins/transport/webserver/bootstrap.py` + `bundles/web-app.yaml` 加 `lca-gateway-bootstrap` entry
- **决定 3 落地:** `lca_kernel/cli.py` 新文件(LCA 进程入口)
- **决定 4 落地:** 删除 `lca/infrastructure/cli/commands/kernel.py:kernel_serve` + `lca/infrastructure/cli/services/gateway.py` 整个文件 + `lca-ops.yaml` 的 `gateway.*` 整段 + `scripts/serve_observability.py`
- **决定 5 落地:** `pyproject.toml` importlinter
- **决定 6 落地:** `tests/lca_plugins/transport/webserver/test_server_plugin.py` + `tests/lca_plugins/transport/webserver/test_bootstrap_plugin.py` + 13 个测试改 import
