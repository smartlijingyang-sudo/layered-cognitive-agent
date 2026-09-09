"""act.compose — capability refs → BodyHandle + lab.body provider.

provider: yes
worker: compose(*, plan_ref, body_ref, tool_registry_ref, safe_executor_ref, transport_ref) -> body_handle
kind: TRANSFORMER
out_port: body_handle
config: plan_ref body_ref tool_registry_ref safe_executor_ref transport_ref
in: plan_ref=plan_ref body_ref=body_ref tool_registry_ref=tool_registry_ref safe_executor_ref=safe_executor_ref transport_ref=transport_ref

What this plugin owns (post body_provider absorption):
- The ``lab.body`` capability key — declared via ``bind_carrier(provides=("lab.body",))``.
- The ``get_body()`` engine-compat helper, which builds a SimpleBody from the
  lab tool registry + safe executor + transport (only ``agent_lab.runtime.runner``
  may import this; act workers go through the BodyHandle typed protocol).
- The ``compose()`` worker function returning a typed ``BodyHandle`` for act.execute.

Why it lives under ``act/``:the compose step is a graph node that produces a
BodyHandle;the lab.body provider role is colocated with that node because the
two share the same set of ``requires`` (lab.tool_registry / lab.safe_executor /
lab.transport / lab.plan_ref) and the same assembly semantics. PR-E eliminated
the standalone ``act/body_provider`` module — see ADR-0211 §459.

The ``provider: yes`` docstring marker tells the lab hook loader to skip
reflection and trust the module-level ``bind_carrier(_CARRIER)`` self-registration
(see ``lca.plugins.lab.internal.loader.load_all``). Without it, the reflective
``bind_worker`` path would derive ``requires`` from compose()'s keyword-only
parameter names instead of the capability keys we need here.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.plugins.lab.internal.loader import _LAB_HOOKS


# ---------------------------------------------------------------------------
# BodyHandle —— typed ref 协议;framework 在 setup 时按 ref 装配 SimpleBody,
# act.execute 只持 typed ref。
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BodyHandle:
    body_ref: str
    tool_registry_ref: str
    safe_executor_ref: str
    transport_ref: str
    plan_ref: str

    def act(self, *, decision: object) -> object:
        """纯协议转发:framework 在调用时根据 refs 装配 SimpleBody。"""
        return {"decision": decision, "body_ref": self.body_ref, "plan_ref": self.plan_ref}


def compose(
    *,
    plan_ref: str,
    body_ref: str = "lab.body",
    tool_registry_ref: str = "lab.tool_registry",
    safe_executor_ref: str = "lab.safe_executor",
    transport_ref: str = "lab.transport",
) -> BodyHandle:
    """按 capability refs 组装 typed BodyHandle(只装配,不执行)。"""
    return BodyHandle(
        body_ref=body_ref,
        tool_registry_ref=tool_registry_ref,
        safe_executor_ref=safe_executor_ref,
        transport_ref=transport_ref,
        plan_ref=plan_ref,
    )


# ---------------------------------------------------------------------------
# Marker —— act.compose 节点 + lab.body capability provider(吸收 body_provider)。
# ---------------------------------------------------------------------------
_MARKER = {
    "id": "lab.act.compose",
    "stage": "act",
    "kind": "TRANSFORMER",
    "description": "act.compose — capability refs → BodyHandle; owns lab.body provider.",
    "module": "lca.plugins.lab.act.compose.plugin",
    "class": "compose",
    "provides": ("lab.body",),
    "requires": (
        "lab.tool_registry",
        "lab.safe_executor",
        "lab.transport",
        "lab.plan_ref",
    ),
    "inputs": [
        {"port": "plan_ref", "kind": "any", "required": True},
        {"port": "body_ref", "kind": "any", "required": True},
        {"port": "tool_registry_ref", "kind": "any", "required": True},
        {"port": "safe_executor_ref", "kind": "any", "required": True},
        {"port": "transport_ref", "kind": "any", "required": True},
    ],
    "outputs": [{"port": "body_handle", "kind": "body_handle"}],
    "out_capabilities": ("lab.body",),
    "factory_aliases": ("compose",),
    "worker_fn": compose,
    "config_params": [],
}


_LAB_HOOKS[_MARKER["id"]] = _MARKER


def setup(ctx, config):
    """Compatibility no-op; marker is registered at import time."""
    del ctx, config


# ---------------------------------------------------------------------------
# Engine-compat helper —— lab.body 装配入口。
# 唯一允许外部 import 的入口;仅 ``agent_lab/runtime/runner.py`` 这种 graph
# engine 调用。act.execute 走 BodyHandle 协议,不直接调此函数。
# ---------------------------------------------------------------------------
def get_body(allowed_tools=None):
    """Build a SimpleBody instance with the lab tool registry."""
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


__all__ = [
    "BodyHandle",
    "compose",
    "get_body",
    "plan_ref_default",
    "setup",
]
