"""Compose and invoke LCA SimpleBody for act.execute.

Node implementation detail (not an agent_lab adapter).

- SafeExecutor: PipelineSafeExecutor (mints CommandEnvelope under plan_ref)
- plan_ref: ADR-0074 ContextVar via plan_ref_scope
- Transport: InternalTransport + echo agent for lab delegate/handoff demos
- Actions: respond / use_tool / stop / ask_human / delegate / handoff
"""

from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path
from typing import Any

from agent_lab.nodes.act.execute.runtime_bind import plan_ref as lab_plan_ref
from agent_lab.tools.registry import ToolRegistry as LabToolRegistry
from lca.cognition.body.executor.pipeline_safe_executor import PipelineSafeExecutor
from lca.cognition.body.executor.simple_body import SimpleBody
from lca.cognition.body.tools.tool_registry import SimpleToolRegistry
from lca.cognition.wire.registry_factory import build_transport_registry
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import (
    Decision,
    DelegationSpec,
    Observation,
    ToolCall,
)
from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.observability.plan.ref import plan_ref_scope
from lca.contracts.models.team.role.team import ToolPermissionManifest
from lca.infrastructure.transport.agent_transport import InternalTransport
from lca.plugins.act.action.handlers_provider import DefaultActionHandlerRegistry
from lca.plugins.composer.act.action_authority import build_action_registry_from_authority

_ALLOWED_ACTIONS = frozenset(
    {
        ActionType.RESPOND.value,
        ActionType.USE_TOOL.value,
        ActionType.STOP.value,
        ActionType.ASK_HUMAN.value,
        ActionType.DELEGATE.value,
        ActionType.HANDOFF.value,
    }
)

_LAB_ECHO_ROLE = "lab_echo"
_LAB_TOOLS: LabToolRegistry | None = None


def configure_lab_tools(registry: LabToolRegistry) -> None:
    """Boot hook: share the YAML-loaded lab tool inventory with Body."""
    global _LAB_TOOLS
    _LAB_TOOLS = registry


def lab_tools() -> LabToolRegistry:
    global _LAB_TOOLS
    if _LAB_TOOLS is None:
        reg = LabToolRegistry()
        reg.load_from_yaml(Path(__file__).resolve().parents[3] / "tools" / "registry.yaml")
        _LAB_TOOLS = reg
    return _LAB_TOOLS


def as_lca_tool_registry(lab: LabToolRegistry | None = None) -> SimpleToolRegistry:
    """Copy lab tools into LCA SimpleToolRegistry (get → None on miss)."""
    src = lab or lab_tools()
    out = SimpleToolRegistry()
    for name in src.names():
        out.register(src.get(name))
    return out


def _lab_transport() -> Any:
    """InternalTransport with an echo member for delegate/handoff demos."""
    transport = InternalTransport()

    async def _echo(subtask: str) -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=f"echo:{subtask}",
        )

    transport.register_agent(_LAB_ECHO_ROLE, _echo)
    return build_transport_registry(transport)


def build_body(*, allowed_tools: list[str] | tuple[str, ...]) -> SimpleBody:
    """Build Body with PipelineSafeExecutor + full solo/lead action set."""
    tools = as_lca_tool_registry()
    allowed = sorted(allowed_tools) if allowed_tools else sorted(tools.list())
    safe_executor = PipelineSafeExecutor(ToolPermissionManifest(allowed_tools=allowed))
    transport_registry = _lab_transport()
    action_registry = build_action_registry_from_authority(
        tools=tools,
        safe_executor=safe_executor,
        transport=transport_registry,
        handler_registry=DefaultActionHandlerRegistry(),
        allowed_actions=_ALLOWED_ACTIONS,
        forbidden_actions=frozenset(),
    )
    action_registry.register_alias("call_tool", ActionType.USE_TOOL.value)
    return SimpleBody(
        tool_registry=tools,
        safe_executor=safe_executor,
        transport_registry=transport_registry,
        action_registry=action_registry,
    )


def decision_from_intent(content: dict[str, Any]) -> Decision:
    """Rebuild an LCA Decision for Body.act from a stamped Intent."""
    tool_calls = _tool_calls_from_content(content)
    delegations = _delegations_from_content(content)

    action_type = str(content.get("action_type") or ActionType.RESPOND.value)
    if action_type in ("call_tool", ActionType.USE_TOOL.value):
        action_type = ActionType.USE_TOOL.value
    elif action_type == "refuse":
        action_type = ActionType.RESPOND.value

    return Decision(
        decision_id=str(content.get("decision_id") or "dec_act"),
        action_type=action_type,
        rationale=str(content.get("rationale") or ""),
        confidence=float(content.get("confidence") or 1.0),
        tool_calls=tool_calls,
        delegations=delegations,
        response_text=content.get("response_text"),
        degraded_from=content.get("degraded_from"),
    )


def _tool_calls_from_content(content: dict[str, Any]) -> list[ToolCall]:
    tool_calls: list[ToolCall] = []
    raw_calls = content.get("tool_calls")
    if isinstance(raw_calls, list) and raw_calls:
        for tc in raw_calls:
            if not isinstance(tc, dict):
                continue
            name = str(tc.get("name") or tc.get("tool_name") or "")
            if not name:
                continue
            args = tc.get("arguments") or tc.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            tool_calls.append(
                ToolCall(
                    call_id=str(tc.get("call_id") or ""),
                    tool_name=name,
                    arguments=args,
                )
            )
    elif content.get("tool") not in (None, "", "__none__"):
        args = content.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        tool_calls.append(
            ToolCall(
                call_id=str(content.get("call_id") or ""),
                tool_name=str(content["tool"]),
                arguments=args,
            )
        )
    return tool_calls


def _delegations_from_content(content: dict[str, Any]) -> list[DelegationSpec]:
    raw = content.get("delegations") or []
    if not isinstance(raw, list):
        return []
    out: list[DelegationSpec] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        subtask = str(item.get("subtask") or "")
        if not subtask:
            continue
        out.append(
            DelegationSpec(
                subtask=subtask,
                target_role=item.get("target_role") or _LAB_ECHO_ROLE,
                target_agent_id=item.get("target_agent_id"),
                protocol=item.get("protocol") or "internal",
                timeout_s=item.get("timeout_s"),
            )
        )
    return out


def minimal_state(*, decision_id: str = "") -> AgentState:
    return AgentState(
        trace_id=f"act-{decision_id or 'anon'}",
        task="agent_lab.act",
        budget=Budget(),
    )


def run_body_act(
    content: dict[str, Any],
    *,
    allowed_tools: list[str] | tuple[str, ...],
) -> Observation:
    """Synchronously run SimpleBody.act under plan_ref_scope (Envelope mint)."""
    body = build_body(allowed_tools=allowed_tools)
    decision = decision_from_intent(content)
    state = minimal_state(decision_id=decision.decision_id)
    with plan_ref_scope(lab_plan_ref()):
        return asyncio.run(body.act(decision, state))


def observation_to_receipt(
    obs: Observation,
    *,
    decision_id: str,
    action_type: str = "",
    tool: str | None = None,
) -> dict[str, Any]:
    """Fold an LCA Observation into tool.receipt.v1 content.

    Boundary: Body ``Observation.extra`` may carry in-process Enums
    (e.g. ``MemoryRecordKind``); receipt/observation artifacts must be
    JSON-plain so digests, Session.append, and logs stay closed.
    """
    tool_name = tool if tool not in (None, "__none__") else None
    extra = _jsonable(dict(obs.extra or {}))
    if not isinstance(extra, dict):
        extra = {"raw": extra}
    payload = _jsonable(obs.payload)
    base = {
        "decision_id": decision_id,
        "action_type": action_type,
        "observation_id": obs.observation_id,
        "success": obs.success,
        "payload": payload,
        "extra": extra,
        "degraded_from": obs.degraded_from,
    }
    # Surface envelope at top-level for easy asserts when present.
    if "command_envelope" in extra:
        base["command_envelope"] = extra["command_envelope"]
    if obs.success:
        return {
            **base,
            "status": "ok",
            "tool": tool_name,
            "result": payload,
        }
    return {
        **base,
        "status": "error",
        "tool": tool_name,
        "error": obs.error or "unknown",
    }


def _jsonable(value: Any) -> Any:
    """Collapse Enums / nested structures to JSON-plain values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _jsonable(value.model_dump())
    return value
