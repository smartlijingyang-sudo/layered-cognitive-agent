"""spine_reflector_writable plugin（ADR-0181 PR-5 / ADR-0183 PR-7）。

PR-5：writable matrix 全部 7 emit 下沉到 EventBus.publish：
- writable.step.start / .end
- writable.segment.start / .end
- writable.iteration.halt / .closing / .close

实际写入由 cursor._append + WritePort 接管；本 publisher 提供
EventBus 路径的 typed 入口。
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


# ── writable.step.start / .end ────────────────────────────────────────


def emit_writable_step_start(*, step: int, run_id: str) -> EventRef:
    return _send(
        execution_point="writable.step.start",
        channel="control",
        payload={"step": step, "run_id": run_id},
    )


def emit_writable_step_end(
    *,
    step: int,
    run_id: str,
    outcome: str = "success",
) -> EventRef:
    return _send(
        execution_point="writable.step.end",
        channel="control",
        payload={"step": step, "run_id": run_id, "outcome": outcome},
    )


# ── writable.segment.start / .end ────────────────────────────────────


def emit_writable_segment_start(*, segment: int, step: int, run_id: str) -> EventRef:
    return _send(
        execution_point="writable.segment.start",
        channel="control",
        payload={"segment": segment, "step": step, "run_id": run_id},
    )


def emit_writable_segment_end(
    *,
    segment: int,
    step: int,
    run_id: str,
    outcome: str = "success",
) -> EventRef:
    return _send(
        execution_point="writable.segment.end",
        channel="control",
        payload={
            "segment": segment,
            "step": step,
            "run_id": run_id,
            "outcome": outcome,
        },
    )


# ── writable.iteration.halt / .closing / .close ───────────────────────


def emit_writable_iteration_halt(*, run_id: str, reason: str) -> EventRef:
    return _send(
        execution_point="writable.iteration.halt",
        channel="control",
        payload={"run_id": run_id, "reason": reason},
    )


def emit_writable_iteration_closing(*, run_id: str) -> EventRef:
    return _send(
        execution_point="writable.iteration.closing",
        channel="control",
        payload={"run_id": run_id},
    )


def emit_writable_iteration_close(*, run_id: str) -> EventRef:
    return _send(
        execution_point="writable.iteration.close",
        channel="control",
        payload={"run_id": run_id},
    )


__all__ = [
    "ReflectorClass",
    "emit_writable_iteration_close",
    "emit_writable_iteration_closing",
    "emit_writable_iteration_halt",
    "emit_writable_segment_end",
    "emit_writable_segment_start",
    "emit_writable_step_end",
    "emit_writable_step_start",
    "setup",
]




class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine.reflector.writable",
    provides=["event.bus.reflector.writable"],
    requires=[],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "writable publisher（ADR-0181）：event.bus.reflector.writable 由本 plugin 发出。"
    ),
    test_suite="tests/plugins/events/publishers/test_events_spine_reflector_writable.py",
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.writable.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.writable.step.start",
            "spine.writable.step.end",
            "spine.writable.segment.start",
            "spine.writable.segment.end",
            "spine.writable.iteration.halt",
            "spine.writable.iteration.closing",
            "spine.writable.iteration.close",
        ),
        state_mutation="forbidden",
    ),
    marker_class=ReflectorClass,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """events.spine.reflector.writable boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.reflector.writable", ReflectorClass)

