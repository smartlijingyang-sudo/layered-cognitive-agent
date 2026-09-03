"""spine_reflector_agent_spawn plugin（ADR-0181 PR-4 / ADR-0183 PR-7）。

PR-4：agent_loop + agent 全部 5 emit 下沉到 EventBus.publish：
- agent_loop.iteration.start / .end
- agent.spawn / agent.iteration / agent.final
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    """内部 helper：构造 SpineEventPayload + EventBus.publish。

    EventBus 走函数内 lazy import，避免 plugin import 时触发
    lca.infrastructure.observability ↔ lca_kernel 链路 circular import。
    """
    from lca_kernel.events.bus import EventBus

    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


# ── agent_loop.iteration.start / .end ─────────────────────────────────


def emit_agent_loop_iteration_start(
    *,
    trace_id: str,
    role: str = "",
    iteration_kind: str = "fresh",
) -> EventRef:
    """Emit ``agent_loop.iteration.start`` at the entry of one agent turn.

    ``iteration_kind`` is ``"fresh"`` for a new run or ``"resume"`` for
    a resumed checkpoint — distinguishes the two flavours in the
    spine without inventing a new execution point.
    """
    return _send(
        execution_point="agent_loop.iteration.start",
        channel="control",
        payload={
            "trace_id": trace_id,
            "role": role,
            "iteration_kind": iteration_kind,
        },
    )


def emit_agent_loop_iteration_end(
    *,
    trace_id: str,
    role: str = "",
    iteration_kind: str = "fresh",
    outcome: str = "success",
) -> EventRef:
    """Emit ``agent_loop.iteration.end`` at the exit of one agent turn."""
    return _send(
        execution_point="agent_loop.iteration.end",
        channel="control",
        payload={
            "trace_id": trace_id,
            "role": role,
            "iteration_kind": iteration_kind,
            "outcome": outcome,
        },
    )


# ── agent.spawn / agent.iteration / agent.final ──────────────────────
#
# agent 维度（PR-4 新增）：与 agent_loop（每次 turn）正交，记录 agent 整体
# 生命周期 spawn/iteration/final。reader 用 EP 名分组。


def emit_agent_spawn(*, trace_id: str, role: str, agent_id: str) -> EventRef:
    """Emit when a new agent is spawned into the run."""
    return _send(
        execution_point="agent.spawn",
        channel="control",
        payload={"trace_id": trace_id, "role": role, "agent_id": agent_id},
    )


def emit_agent_iteration(
    *,
    trace_id: str,
    role: str,
    agent_id: str,
    iteration: int,
) -> EventRef:
    """Emit at the start of each agent-level iteration (one run = N iterations)."""
    return _send(
        execution_point="agent.iteration",
        channel="control",
        payload={
            "trace_id": trace_id,
            "role": role,
            "agent_id": agent_id,
            "iteration": iteration,
        },
    )


def emit_agent_final(
    *,
    trace_id: str,
    role: str,
    agent_id: str,
    outcome: str = "success",
) -> EventRef:
    """Emit at agent final (terminal)."""
    return _send(
        execution_point="agent.final",
        channel="control",
        payload={
            "trace_id": trace_id,
            "role": role,
            "agent_id": agent_id,
            "outcome": outcome,
        },
    )


__all__ = [
    "ReflectorClass",
    "emit_agent_final",
    "emit_agent_iteration",
    "emit_agent_loop_iteration_end",
    "emit_agent_loop_iteration_start",
    "emit_agent_spawn",
    "setup",
]




class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine.reflector.agent_spawn",
    provides=["event.bus.reflector.agent_spawn"],
    requires=["event.bus"],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "agent_spawn publisher（ADR-0181）：event.bus.reflector.agent_spawn 由本 plugin 发出。"
    ),
    test_suite="tests/plugins/events/publishers/test_events_spine_reflector_agent_spawn.py",
    functional_group=FunctionalGroup.G8_COLLAB,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G8_COLLAB,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.agent_spawn.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.agent_loop.iteration.start",
            "spine.agent_loop.iteration.end",
            "spine.agent.spawn",
            "spine.agent.iteration",
            "spine.agent.final",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """events.spine.reflector.agent_spawn boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.reflector.agent_spawn", ReflectorClass)

