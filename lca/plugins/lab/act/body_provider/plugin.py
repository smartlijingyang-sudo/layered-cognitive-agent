"""act.body_provider — lab.body capability 的 marker provider.
provider: yes

做什么:声明 ``lab.body`` capability key 由本 provider 提供;在 boot 时
通过 Cordis ctx 装配 SimpleBody(由 ``compose`` 函数内部调)。
不做什么:不再 export ``get_body()`` 函数(由 act.compose 节点接管);
不再被 act.execute / body / dispatch 等 worker 文件 import(违反
ADR-0211 §1.3「装配唯一 = Profile/Bundle」)。

ADR-0211 §6 §3:本文件保留但收紧 — ``get_body()`` 函数退役;
``act.compose`` 节点化接管装配职责。

注:provider 不是 worker,需要显式声明 requires(反向依赖),不走反射入口。
loader 通过 docstring 含 ``provider: yes`` 跳过反射,走传统 _CARRIER 自注册。

Engine-compat helper(``get_body()`` + ``plan_ref_default()``)保留供
``agent_lab.runtime.runner._default_seams`` 调用;act 工人**不应**直接
import 此函数。
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier


# ---------------------------------------------------------------------------
# Carrier —— lab.body capability 的 marker(provider 形态,跳过反射)。
# ---------------------------------------------------------------------------
_CARRIER = LabCarrier(
    id="lab.act.body_provider",
    stage="composition",
    kind="PROVIDER",
    description="lab.body provider — SimpleBody composition for act.compose.",
    node_id="body_provider",
    source_module="lca.plugins.lab.act.body_provider.plugin",
    source_class="body_provider",
    provides=("lab.body",),
    requires=(
        "lab.tool_registry",
        "lab.safe_executor",
        "lab.transport",
        "lab.plan_ref",
    ),
    inputs=(),
    outputs=(("body", "body"),),
    out_capabilities=("lab.body",),
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


# ---------------------------------------------------------------------------
# Engine-compat helper —— 唯一允许外部 import 的入口。
# ADR-0211 §6 §3:``get_body()`` 不再被 act 工人文件 import;
# 仅 ``agent_lab/runtime/runner.py`` 这种 graph engine 用它构造 Seams。
# act.execute 等工人走 ``act.compose`` 节点的 BodyHandle,不走这里。
# ---------------------------------------------------------------------------


def get_body(allowed_tools=None):
    """Build a SimpleBody instance with the lab tool registry.

    Engine-only helper(agent_lab.runtime.runner);act 工人**不应**直接 import 此函数。
    """
    from lca.cognition.body.executor.pipeline_safe_executor import PipelineSafeExecutor
    from lca.cognition.body.executor.simple_body import SimpleBody
    from lca.cognition.body.tools.tool_registry import SimpleToolRegistry
    from lca.contracts.models.team.role.team import ToolPermissionManifest
    from lca.plugins.act.action.handlers_provider import DefaultActionHandlerRegistry
    from lca.plugins.composer.act.action_authority import build_action_registry_from_authority

    from lca.plugins.lab.tools.provider.plugin import get_registry as get_lab_registry
    from lca.plugins.lab.transport.provider.plugin import get_transport

    lab_tools = get_lab_registry()
    tools = SimpleToolRegistry()
    for name in lab_tools.names():
        tool = lab_tools.get(name)
        if tool is not None:
            tools.register(tool)

    allowed = sorted(allowed_tools) if allowed_tools else sorted(lab_tools.names())
    safe_executor = PipelineSafeExecutor(ToolPermissionManifest(allowed_tools=allowed))
    transport = get_transport()
    action_registry = build_action_registry_from_authority(
        tools=tools,
        safe_executor=safe_executor,
        transport=transport,
        handler_registry=DefaultActionHandlerRegistry(),
        allowed_actions=frozenset({"use_tool", "respond", "stop"}),
        forbidden_actions=frozenset(),
    )
    return SimpleBody(
        tool_registry=tools,
        safe_executor=safe_executor,
        transport_registry=transport,
        action_registry=action_registry,
    )


def plan_ref_default() -> str:
    """Default plan_ref for the lab act phase."""
    from lca.plugins.lab.session.provider.plugin import PLAN_REF
    return PLAN_REF


__all__ = ["get_body", "plan_ref_default", "setup"]
