"""assistant.webserver_bridge plugin —— ADR-0187 §3 D7/D12 的 web 面桥。

两个投影职责（均不写助理域真值）：

1. 安装 ``app.state.assistant_catalog`` —— ``routes_assistants`` 的
   ``/v1/assistants`` handler 经此找到 catalog（web-standard 无本插件 ⇒
   属性缺省 ⇒ 路由保持 501 兜底，I-A1/I-A10 不破）。
2. 提供 ``assistant.frontend_bridge`` capability —— 把新建助理投影成
   LobeHub agents 行（TRPC ``agent.createAgent``），使前端助理列表与
   ``/agent/<agt_id>`` 可见。映射真值 = agents 行
   ``agencyConfig.lcaAssistantId``（前端 LcaRunDriver 读回并发
   ``assistant_id`` 进 ``POST /runs``）；本插件不落第二份映射文件。

失败语义：前端注册是 fail-soft 投影 —— 网络失败 / 非 200 / 解析失败
返回 ``None`` + warning log，不阻断 ``catalog.create``（创建真值在 Home，
已发 ``assistant.created`` EP）。``lobehub_url`` 为空 = 关闭注册（返回
``None``）。

外部后果：注册成功会在 LobeHub Postgres ``agents`` 表新增一行
（dev 环境经 ``ENABLE_MOCK_DEV_USER`` 旁路认证，归属 ``MOCK_DEV_USER_ID``）。
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_FRONTEND_BRIDGE
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin

log = structlog.get_logger(__name__)

_TRPC_CREATE_AGENT_PATH = "/trpc/lambda/agent.createAgent"
"""LobeHub lambda TRPC 的 agent.createAgent 过程路径（superjson 非批处理形态）。"""

_DEFAULT_TIMEOUT_S = 10.0
_SOUL_SUMMARY_MAX_CHARS = 2000
"""systemRole 摘要长度上限（LobeHub agents.system_role 是 text 列；防人设全文膨胀）。"""


# ── Plugin 配置 ───────────────────────────────────────────────────────


class Config(BaseModel):
    """webserver_bridge 配置。

    ``lobehub_url`` 仅来自 Profile 注入（``{from_env: LCA_LOBEHUB_URL}``
    required:false 或 patch literal）；**禁止**本模块读 ``os.environ``
    （ADR-0187 §6 删除条件）。空字符串 = 关闭前端注册。
    """

    model_config = ConfigDict(extra="forbid")

    lobehub_url: str = ""
    timeout_s: float = Field(default=_DEFAULT_TIMEOUT_S, gt=0)


# ── Bridge 实现 ──────────────────────────────────────────────────────


class AssistantFrontendBridge:
    """助理 → 前端 agents 行的单向投影。

    单一职责：构造 TRPC ``agent.createAgent`` 请求并解析 ``agentId``。
    不做重试、不持有状态；调用方（``create_assistant`` 工具）决定降级策略。
    """

    def __init__(self, *, lobehub_url: str, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self._base = lobehub_url.rstrip("/")
        self._timeout_s = timeout_s

    @property
    def enabled(self) -> bool:
        return bool(self._base)

    async def register(
        self,
        *,
        assistant_id: str,
        name: str,
        description: str,
        emoji: str,
        system_role: str,
        opening_message: str = "",
    ) -> str | None:
        """投影一个助理到前端；成功返回 ``agt_*`` agent id，失败返回 ``None``。

        Precondition：``assistant_id`` / ``name`` 非空（catalog.create 已保证）。
        Failure：未启用 / 网络错误 / 非 200 / 响应缺 ``agentId`` ⇒ ``None``
        + warning log（fail-soft；创建真值不受影响）。
        """
        if not self.enabled:
            log.info("assistant.frontend_bridge.disabled", assistant_id=assistant_id)
            return None

        config: dict[str, Any] = {
            "title": name,
            "description": description,
            "avatar": emoji,
            "model": "solo",
            "systemRole": system_role[:_SOUL_SUMMARY_MAX_CHARS],
            # 映射真值：前端 LcaRunDriver 读 agencyConfig.lcaAssistantId
            # 并在 POST /runs 带出 assistant_id（ADR-0187 §3 D7 绑定）。
            "agencyConfig": {"lcaAssistantId": assistant_id},
        }
        if opening_message:
            config["openingMessage"] = opening_message
        body = {"json": {"config": config}}

        try:
            import httpx

            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(
                    f"{self._base}{_TRPC_CREATE_AGENT_PATH}",
                    json=body,
                    headers={"content-type": "application/json"},
                )
        except Exception as exc:  # httpx 网络/超时/连接错误统一降级
            log.warning(
                "assistant.frontend_bridge.request_failed",
                assistant_id=assistant_id,
                error=str(exc),
            )
            return None

        if response.status_code != 200:
            log.warning(
                "assistant.frontend_bridge.bad_status",
                assistant_id=assistant_id,
                status=response.status_code,
                body=response.text[:200],
            )
            return None

        agent_id = _extract_agent_id(response.text)
        if agent_id is None:
            log.warning(
                "assistant.frontend_bridge.bad_response",
                assistant_id=assistant_id,
                body=response.text[:200],
            )
        return agent_id


def _extract_agent_id(response_text: str) -> str | None:
    """从 superjson TRPC 响应提取 ``agentId``。

    形态：``{"result": {"data": {"json": {"agentId": "..."}}}}``。
    """
    import json

    try:
        payload = json.loads(response_text)
    except ValueError:
        return None
    data = payload.get("result", {}).get("data", {}) if isinstance(payload, dict) else {}
    inner = data.get("json") if isinstance(data, dict) else None
    agent_id = inner.get("agentId") if isinstance(inner, dict) else None
    return agent_id if isinstance(agent_id, str) and agent_id else None


# ── Plugin manifest ───────────────────────────────────────────────────


@plugin(
    id="lca.plugins.assistant.webserver_bridge",
    provides=(ASSISTANT_FRONTEND_BRIDGE.key,),
    requires=(ASSISTANT_CATALOG.key, "web_server"),
    layer="L4",
    kind=PluginKind.BRIDGE,
    effects=(EffectClass.NETWORK,),
    description=(
        "把助理域桥到 web 面：安装 app.state.assistant_catalog 供 "
        "/v1/assistants 路由，并提供 assistant.frontend_bridge 把新建助理"
        "投影成 LobeHub agents 行（fail-soft）。不写助理域真值。"
    ),
    test_suite="tests/plugins/assistant/test_webserver_bridge.py",
    functional_group=FunctionalGroup.G9_INTERACTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G9_INTERACTION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca.plugins.assistant.webserver_bridge.checked",
                "lca.plugins.assistant.webserver_bridge.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key, "web_server"),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """安装 app.state.assistant_catalog + 延迟挂载 /v1/assistants 路由。

    时序：requires ``web_server`` ⇒ 本插件在 ``lca-web-server`` 建好
    Starlette app 之后 boot；``app.state`` 与 ``app.router.routes`` 此时可写。

    路由延迟挂载原因：``assistant-runtime`` bundle 在 profile 的 bundles 列表
    中排在 ``web-app`` 之后，``routes_assistants`` 的 RouteSpec 注册晚于
    ``lca-web-server`` 的 ``registry.install(app)``；由本插件（boot 序保证
    在 app 就绪后）把 ``ROUTE_SPECS`` 物化进 ``app.router.routes``。
    已存在同路径路由时跳过（防 bundle 顺序变化导致重复）。
    """
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    handle = ctx.require("web_server")
    app = getattr(handle, "app", None)
    if app is not None and hasattr(app, "state"):
        app.state.assistant_catalog = catalog

    if app is not None and hasattr(app, "router"):
        _mount_assistant_routes(ctx, app)

    bridge = AssistantFrontendBridge(
        lobehub_url=config.lobehub_url,
        timeout_s=config.timeout_s,
    )
    ctx.provide(ASSISTANT_FRONTEND_BRIDGE.key, bridge)


def _mount_assistant_routes(ctx: PluginContext, app: Any) -> None:
    """把 ``/v1/assistants`` 路由物化进已就绪的 Starlette app。

    幂等：``app.router.routes`` 已有同 path 路由时跳过该 spec。
    dispose 经 ``ctx.effect`` 收口（kernel teardown LIFO）。
    """
    from lca.plugins.transport.webserver.route_register import _starlette_route
    from lca.plugins.transport.webserver.routes_assistants import ROUTE_SPECS

    existing = {getattr(route, "path", None) for route in app.router.routes}
    for spec in ROUTE_SPECS:
        if spec.path in existing:
            continue
        route = _starlette_route(spec)
        app.router.routes.append(route)
        existing.add(spec.path)

        def _dispose(_route: Any = route) -> None:
            try:
                app.router.routes.remove(_route)
            except ValueError:
                pass

        inner: Any = ctx._runtime()  # type: ignore[attr-defined]
        inner.effect(_dispose, label=f"route:{spec.path}")


__all__ = ["AssistantFrontendBridge", "Config", "setup"]
