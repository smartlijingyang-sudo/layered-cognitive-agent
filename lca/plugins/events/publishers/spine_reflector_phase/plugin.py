"""spine_reflector_phase plugin（ADR-0181 PR-5 / ADR-0183 PR-7）。

# COMPAT(owner: ADR-0194 P2-12, from: spine_reflector_phase emit_*,
# to: lca.loop.phase_spine_commit + tool_journal_commit,
# delete_when: P2-16 plugin dir removed + rg "spine_reflector_phase" lca/
# --glob '!**/spine_reflector_phase/**' = 0,
# forbidden_new_usage: production import of emit_* from this package)

Thin adapter: fold EPs delegate to ``phase_spine_commit``; tool EPs to
``tool_journal_commit``. No production callers remain — loop cursor owns fold
production via ``spine_loop_cursor`` until that publisher migrates.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
from lca.loop.fact_gateway import publish_ep_bound
from lca.loop.phase_spine_commit import (
    commit_perceive_phase_fold as _commit_perceive_phase_fold,
)
from lca.loop.phase_spine_commit import (
    commit_phase_act_fold as _commit_phase_act_fold,
)
from lca.loop.phase_spine_commit import (
    commit_phase_act_fold_end as _commit_phase_act_fold_end,
)
from lca.loop.phase_spine_commit import (
    commit_phase_act_fold_start as _commit_phase_act_fold_start,
)
from lca.loop.phase_spine_commit import (
    commit_phase_perceive_fold as _commit_phase_perceive_fold,
)
from lca.loop.phase_spine_commit import (
    commit_phase_reflect_fold as _commit_phase_reflect_fold,
)
from lca.loop.phase_spine_commit import (
    commit_phase_remember_fold as _commit_phase_remember_fold,
)
from lca.loop.phase_spine_commit import (
    commit_phase_stop_fold as _commit_phase_stop_fold,
)
from lca.loop.phase_spine_commit import (
    commit_phase_think_fold as _commit_phase_think_fold,
)

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def emit_perceive_phase_fold(*, step: int, run_id: str) -> EventRef | None:
    return _commit_perceive_phase_fold(step=step, run_id=run_id)


def emit_phase_perceive_fold(*, step: int, run_id: str) -> EventRef | None:
    return _commit_phase_perceive_fold(step=step, run_id=run_id)


def emit_phase_think_fold(
    *,
    step: int,
    run_id: str,
    decision_path: str | None = None,
) -> EventRef | None:
    return _commit_phase_think_fold(step=step, run_id=run_id, decision_path=decision_path)


def emit_phase_remember_fold(*, step: int, run_id: str) -> EventRef | None:
    return _commit_phase_remember_fold(step=step, run_id=run_id)


def emit_phase_stop_fold(*, step: int, run_id: str, outcome: str) -> EventRef | None:
    return _commit_phase_stop_fold(step=step, run_id=run_id, outcome=outcome)


def emit_phase_reflect_fold(
    *,
    step: int,
    run_id: str,
    lessons: int | None = None,
) -> EventRef | None:
    return _commit_phase_reflect_fold(step=step, run_id=run_id, lessons=lessons)


def emit_phase_act_fold_start(*, step: int, run_id: str, tool_name: str) -> EventRef | None:
    return _commit_phase_act_fold_start(step=step, run_id=run_id, tool_name=tool_name)


def emit_phase_act_fold_end(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    outcome: str,
) -> EventRef | None:
    return _commit_phase_act_fold_end(
        step=step, run_id=run_id, tool_name=tool_name, outcome=outcome
    )


def emit_phase_act_fold(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    outcome: str,
) -> EventRef | None:
    return _commit_phase_act_fold(
        step=step, run_id=run_id, tool_name=tool_name, outcome=outcome
    )


def emit_phase_tool_call_start(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    invocation_id: str,
) -> EventRef | None:
    return publish_ep_bound(
        "phase.tool.call.start",
        {
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "invocation_id": invocation_id,
        },
        actor="phase",
    )


def emit_phase_tool_call_end(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    invocation_id: str,
    outcome: str,
) -> EventRef | None:
    return publish_ep_bound(
        "phase.tool.call.end",
        {
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "outcome": outcome,
        },
        actor="phase",
    )


def emit_phase_tool_denied(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    reason: str,
) -> EventRef | None:
    return publish_ep_bound(
        "phase.tool.denied",
        {
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "reason": reason,
        },
        actor="phase",
    )


__all__ = [
    "ReflectorClass",
    "emit_perceive_phase_fold",
    "emit_phase_act_fold",
    "emit_phase_act_fold_end",
    "emit_phase_act_fold_start",
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
