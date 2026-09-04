"""spine_reflector_phase plugin（ADR-0181 PR-5 / ADR-0183 PR-7）。

PR-5：phase 全部 13 emit 下沉到 EventBus.publish：
- perceive.phase.fold / phase.perceive.fold
- phase.think/gate/remember/stop/reflect.fold
- phase.act.fold.start / .end / phase.act.fold
- phase.tool.call.start / .end / phase.tool.denied
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
from lca.plugins.events.publishers._session_publish import publish_via_session

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return publish_via_session(sp, producer=ReflectorClass)


# ── phase.fold 系列（5 + perceive + perceive.phase）────────────────────


def emit_perceive_phase_fold(*, step: int, run_id: str) -> EventRef:
    return _send(
        execution_point="perceive.phase.fold",
        channel="fact",
        payload={"step": step, "run_id": run_id},
    )


def emit_phase_perceive_fold(*, step: int, run_id: str) -> EventRef:
    return _send(
        execution_point="phase.perceive.fold",
        channel="fact",
        payload={"step": step, "run_id": run_id},
    )


def emit_phase_think_fold(
    *,
    step: int,
    run_id: str,
    decision_path: str | None = None,
) -> EventRef:
    payload: dict[str, Any] = {"step": step, "run_id": run_id}
    if decision_path is not None:
        payload["decision_path"] = decision_path
    return _send(
        execution_point="phase.think.fold",
        channel="fact",
        payload=payload,
    )


def emit_phase_gate_fold(
    *,
    step: int,
    run_id: str,
    verdict: str | None = None,
) -> EventRef:
    payload: dict[str, Any] = {"step": step, "run_id": run_id}
    if verdict is not None:
        payload["verdict"] = verdict
    return _send(
        execution_point="phase.gate.fold",
        channel="fact",
        payload=payload,
    )


def emit_phase_remember_fold(*, step: int, run_id: str) -> EventRef:
    return _send(
        execution_point="phase.remember.fold",
        channel="fact",
        payload={"step": step, "run_id": run_id},
    )


def emit_phase_stop_fold(*, step: int, run_id: str, outcome: str) -> EventRef:
    return _send(
        execution_point="phase.stop.fold",
        channel="control",
        payload={"step": step, "run_id": run_id, "outcome": outcome},
    )


def emit_phase_reflect_fold(
    *,
    step: int,
    run_id: str,
    lessons: int | None = None,
) -> EventRef:
    payload: dict[str, Any] = {"step": step, "run_id": run_id}
    if lessons is not None:
        payload["lessons"] = lessons
    return _send(
        execution_point="phase.reflect.fold",
        channel="fact",
        payload=payload,
    )


# ── phase.act.fold 系列（3）──────────────────────────────────────────


def emit_phase_act_fold_start(*, step: int, run_id: str, tool_name: str) -> EventRef:
    return _send(
        execution_point="phase.act.fold.start",
        channel="control",
        payload={"step": step, "run_id": run_id, "tool_name": tool_name},
    )


def emit_phase_act_fold_end(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    outcome: str,
) -> EventRef:
    return _send(
        execution_point="phase.act.fold.end",
        channel="control",
        payload={
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "outcome": outcome,
        },
    )


def emit_phase_act_fold(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    outcome: str,
) -> EventRef:
    """Single phase.act.fold EP（ADR-0169 D11）。"""
    return _send(
        execution_point="phase.act.fold",
        channel="control",
        payload={
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "outcome": outcome,
        },
    )


# ── phase.tool.call 系列（3）─────────────────────────────────────────


def emit_phase_tool_call_start(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    invocation_id: str,
) -> EventRef:
    return _send(
        execution_point="phase.tool.call.start",
        channel="control",
        payload={
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "invocation_id": invocation_id,
        },
    )


def emit_phase_tool_call_end(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    invocation_id: str,
    outcome: str,
) -> EventRef:
    return _send(
        execution_point="phase.tool.call.end",
        channel="control",
        payload={
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "outcome": outcome,
        },
    )


def emit_phase_tool_denied(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    reason: str,
) -> EventRef:
    return _send(
        execution_point="phase.tool.denied",
        channel="control",
        payload={
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "reason": reason,
        },
    )


__all__ = [
    "ReflectorClass",
    "emit_perceive_phase_fold",
    "emit_phase_act_fold",
    "emit_phase_act_fold_end",
    "emit_phase_act_fold_start",
    "emit_phase_gate_fold",
    "emit_phase_perceive_fold",
    "emit_phase_reflect_fold",
    "emit_phase_remember_fold",
    "emit_phase_stop_fold",
    "emit_phase_think_fold",
    "emit_phase_tool_call_end",
    "emit_phase_tool_call_start",
    "emit_phase_tool_denied",
    "setup",
]




class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine.reflector.phase",
    provides=["event.bus.reflector.phase"],
    requires=[],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "phase publisher（ADR-0181）：event.bus.reflector.phase 由本 plugin 发出。"
    ),
    test_suite="tests/plugins/events/publishers/test_events_spine_reflector_phase.py",
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.phase.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.perceive.phase.fold",
            "spine.phase.perceive.fold",
            "spine.phase.think.fold",
            "spine.phase.gate.fold",
            "spine.phase.remember.fold",
            "spine.phase.stop.fold",
            "spine.phase.reflect.fold",
            "spine.phase.act.fold.start",
            "spine.phase.act.fold.end",
            "spine.phase.act.fold",
            "spine.phase.tool.call.start",
            "spine.phase.tool.call.end",
            "spine.phase.tool.denied",
        ),
        state_mutation="forbidden",
    ),
    marker_class=ReflectorClass,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """events.spine.reflector.phase boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.reflector.phase", ReflectorClass)

