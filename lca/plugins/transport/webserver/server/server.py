"""lca-web-server plugin — 接管 ``gateway/app.py`` 的全部职责。

ADR-0119 决定 1 + 决定 3 + ADR-0119 followup-2。``lca-web-server`` 是 L1 SEAM plugin,自我管理:

1. 构造 Starlette app(空 routes)
2. 调 ``ctx.require("install_bootstrap_state")`` 装 ASGI state(run_port / file_store / devices / etc.)
3. 调 ``ctx.require("route_registry").install(app)`` 把 4 个 routes plugin 攒的
   Route 列表 append 到 ``app.router.routes``
4. 调 :func:`lca_kernel.lifespan.make_lifespan` 装 Starlette lifespan 协议
   (test/uvicorn 都用 — 没有 hack、没有 ``app.state.ctx = inner``、没有
   ThreadPoolExecutor 跑 asyncio)
5. ``ctx.provide("web_server", WebServerHandle(app=app, config=cfg, ctx=inner))``
   供 :func:`lca_kernel.cli.serve` 在 K3 完成后 ``await web_server.serve()`` 监听端口

设计取舍(对比 deepseek)
-----------------------
- deepseek ``WebServer extends Service`` 自己在 ``Service.init`` 里 ``createServer + server.listen``
- LCA 用 plugin 模式但 SIGTERM 协调完全一致:K6 LIFO dispose 收口
- 跟 deepseek 等价——deepseek 同样是 plugin setup 完后 ``bin.ts`` 调 ``server[Service.init]()`` 监听
- LCA 多加一层 ``lca_kernel.lifespan`` 是为了让 lifespan 在 plugin/cli/test 三方都能用,
  没有循环依赖
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca_kernel.boot.lifespan import make_lifespan

if TYPE_CHECKING:
    from lca.infrastructure.cron.daemon import CronDaemonService

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LcaWebServerConfig:
    """Plugin 配置 schema。host/port 来自 profile yaml 的 config 块。"""

    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "info"


@dataclass(frozen=True, slots=True)
class WebServerHandle:
    """``ctx.inject("web_server")`` 拿到的句柄。``lca_kernel.cli.serve`` await ``.serve()`` 监听端口。"""

    app: Any  # starlette.applications.Starlette
    config: LcaWebServerConfig
    ctx: Any  # cordis.Context

    async def serve(self) -> None:
        """起 uvicorn.Server 监听端口;SIGTERM 触发 server.shutdown() LIFO 收口。"""
        import uvicorn

        uconfig = uvicorn.Config(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level=self.config.log_level,
            lifespan="on",  # 用 app.router.lifespan_context(由 make_lifespan 装)
        )
        server = uvicorn.Server(uconfig)
        # LIFO dispose:webserver 退出时先 server.shutdown()
        self.ctx.effect(server.shutdown, label="lca-web-server.uvicorn.shutdown")

        await server.serve()


async def start_cron_daemon(
    app: Any,
    lock_dir: Path | None = None,
    workspace_path: str | None = None,
) -> CronDaemonService | None:
    """命名组合步骤:启动常驻 Cron 调度守护协程(ADR-0268 生产运行态)。

    webserver plugin 拥有这次组合:它用显式输入构造 cron store + daemon,
    ``start()`` 后把运行中的 daemon 返回给调用方挂载到
    ``app.state.cron_daemon``。Starlette lifespan
    (``lca_kernel.boot.lifespan.make_lifespan``)不构造 cron,只在 shutdown
    时把它停掉。

    输入全部显式声明为参数(无 ctx getattr 鸭子读取):

    - ``app``:Starlette 应用;``LcaRunHandoffDispatcher(app)`` 在派发时才
      从 ``app.state`` 解析 run_port / registry,因此与 webserver bootstrap
      的启动顺序无关。
    - ``lock_dir``:cron 文件锁目录;默认 ``<lca_home>/locks``。
    - ``workspace_path``:cron worker 的工作区;默认 ``<lca_home>``。

    启动失败策略(显式降级,非静默 try/except):daemon 起不来时记 error 日志
    并返回 ``None``;webserver 照常 boot 并对外服务,只是没有 cron 调度。
    理由:cron 是后台生产运行态需求(ADR-0268),不是请求路径依赖——降级启动
    让服务平面保持可用,失败本身在日志里可见。
    """
    from lca.domain.cron.store import MultiAssistantCronStore
    from lca.infrastructure.cron.daemon import CronDaemonService
    from lca.infrastructure.path.locator import get_lca_home
    from lca.plugins.transport.webserver.handlers.runs.terminal.handoff_dispatch import (
        LcaRunHandoffDispatcher,
    )

    lca_home = get_lca_home()
    try:
        daemon = CronDaemonService(
            store=MultiAssistantCronStore(lca_home / "assistants"),
            lock_dir=lock_dir if lock_dir is not None else (lca_home / "locks"),
            workspace_path=workspace_path if workspace_path is not None else str(lca_home),
            # Resolves run_port / registry off app.state at dispatch time,
            # so boot ordering between the webserver bootstrap and this
            # step does not matter.
            handoff_dispatcher=LcaRunHandoffDispatcher(app),
        )
        await daemon.start()
    except Exception:
        _log.exception("webserver: failed to start CronDaemonService; continuing without cron")
        return None
    return daemon


@plugin(
    id="lca-web-server",
    provides=("web_server",),
    requires=("route_registry", "install_bootstrap_state", "webserver_bootstrap_config"),
    layer="L1",  # 整合 route_registry (L0) + webserver_bootstrap (L0) + 装 Starlette + 装 lifespan
    kind=PluginKind.SEAM,
    effects="none",  # ADR-0119 决定 1 提到 binds:host:port;留 followup ADR 在 EffectCatalog 登记
    description="lca-web-server plugin — 装 Starlette + 装 ASGI state + 装 routes + 装 lifespan + provide web_server 句柄(替代 gateway/app.py).",
    test_suite="tests.lca_plugins.transport.webserver.test_server_plugin",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve", "plugin.bind", "plugin.unbind")),
        observability=EvidenceContract(
            descriptors=("lca-web-server.listening", "lca-web-server.shutdown"),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry", "install_bootstrap_state", "webserver_bootstrap_config"),
        emits=("web_server.ready",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """构造 Starlette + 装 ASGI state + 装 routes + 装 lifespan + provide ``web_server`` 句柄。

    不起 uvicorn 监听——监听由 :func:`lca_kernel.cli.serve` 在 K3 完成后
    await ``web_server.serve()`` 触发。SIGTERM 时 webserver.dispose → server.shutdown()
    由 K6 LIFO 收口。
    """
    from starlette.applications import Starlette

    from lca.plugins.transport.webserver.lifespan.adapter import install_trace_middleware

    # 1. 解析 config(支持 dict 或 LcaWebServerConfig)
    if isinstance(config, LcaWebServerConfig):
        cfg = config
    elif isinstance(config, dict):
        cfg = LcaWebServerConfig(
            host=config.get("host", "127.0.0.1"),
            port=config.get("port", 8765),
            log_level=config.get("log_level", "info"),
        )
    else:
        cfg = LcaWebServerConfig()

    # 2. 拿 cordis Context(PluginContext._runtime() 拿底层 Context)
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]

    # 3. 构造空 Starlette + 装 ASGI state + 装 routes
    app = Starlette(routes=[])

    # 3a. lca-gateway-bootstrap 提供的 install_bootstrap_state 函数
    install_bootstrap_state = ctx.require("install_bootstrap_state")
    bootstrap_config = ctx.require("webserver_bootstrap_config")
    install_bootstrap_state(app, inner, config=bootstrap_config)

    # 3b. lca-webserver-router 提供的 registry 实例,装 routes
    registry = ctx.require("route_registry")
    registry.install(app)

    # 3d. 装 trace_id 上下文隔离中间件(ADR-0183 §3.9 / PR-12)。
    # 必须在 routes 之后:lifespan_adapter.install_trace_middleware 是
    # ``app.add_middleware(...)`` 的最早入口 = ASGI 最外层,跨所有请求隔离。
    install_trace_middleware(app)

    # 3c. 装 Starlette lifespan 协议(让 TestClient(app).lifespan_context(app) 工作)
    # 长期可维护:lifespan 实现放在 lca_kernel.lifespan,plugin/cli/test 三方都用它
    # 不写"app.state.ctx = inner" hack(短期凑合)
    app.router.lifespan_context = cast("Any", make_lifespan(inner))

    # 3e. 常驻 Cron 调度守护(ADR-0268 生产运行态)——命名组合步骤。
    # 构造+启动在这里,shutdown 时的 stop() 由 make_lifespan 负责(LIFO dispose)。
    # 显式降级:起不来返回 None,webserver 照常对外服务(无 cron),见 start_cron_daemon。
    cron_daemon = await start_cron_daemon(app)
    if cron_daemon is not None:
        app.state.cron_daemon = cron_daemon

    # 4. provide web_server 句柄(cli.py:serve 会 await 它)
    handle = WebServerHandle(app=app, config=cfg, ctx=inner)
    ctx.provide("web_server", handle)


__all__ = ["LcaWebServerConfig", "WebServerHandle", "start_cron_daemon"]
