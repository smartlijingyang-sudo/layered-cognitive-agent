"""spine_reflector_runtime plugin（ADR-0181 PR-3 / ADR-0183 PR-7）。

# COMPAT(owner: ADR-0194 P2-10, from: spine_reflector_runtime emit_*,
# to: lca.infrastructure.session.runtime_emit, delete_when: P2-16 plugin dir
# removed + rg "spine_reflector_runtime" lca/ --glob '!**/spine_reflector_runtime/**' = 0,
# forbidden_new_usage: production import of emit_* from this package)

Thin adapter: all emit helpers delegate to ``runtime_emit.publish_ep_bound``.
Production callers must import ``lca.infrastructure.session.runtime_emit``.
"""

from __future__ import annotations

import logging
from typing import Any

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
from lca.infrastructure.session.runtime_emit import (
    emit_exception_finally as _emit_exception_finally,
)
from lca.infrastructure.session.runtime_emit import (
    emit_lifecycle_finally as _emit_lifecycle_finally,
)
from lca.infrastructure.session.runtime_emit import (
    emit_runtime_checkpoint_create as _emit_runtime_checkpoint_create,
)
from lca.infrastructure.session.runtime_emit import (
    emit_runtime_event_publisher_publish as _emit_runtime_event_publisher_publish,
)
from lca.infrastructure.session.runtime_emit import (
    emit_runtime_observed as _emit_runtime_observed,
)
from lca.infrastructure.session.runtime_emit import (
    emit_runtime_reducer_apply_end as _emit_runtime_reducer_apply_end,
)
from lca.infrastructure.session.runtime_emit import (
    emit_runtime_reducer_apply_start as _emit_runtime_reducer_apply_start,
)
from lca.infrastructure.session.runtime_emit import (
    emit_runtime_resume_end as _emit_runtime_resume_end,
)
from lca.infrastructure.session.runtime_emit import (
    emit_runtime_resume_start as _emit_runtime_resume_start,
)
from lca.infrastructure.session.runtime_emit import (
    set_active_run_id as _set_active_run_id,
)

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def set_active_run_id(run_id: str | None) -> None:
    """Install the active run_id for runtime EP payloads."""
    _set_active_run_id(run_id)


def emit_runtime_reducer_apply_start(*, method: str, run_id: str | None = None) -> Any:
    return _emit_runtime_reducer_apply_start(method=method, run_id=run_id)


def emit_runtime_reducer_apply_end(
    *, method: str, outcome: str, run_id: str | None = None
) -> Any:
    return _emit_runtime_reducer_apply_end(method=method, outcome=outcome, run_id=run_id)


def emit_runtime_checkpoint_create(
    *, plan_ref: str, state_ref: str, node_id: str, outcome: str = "success"
) -> Any:
    return _emit_runtime_checkpoint_create(
        plan_ref=plan_ref, state_ref=state_ref, node_id=node_id, outcome=outcome
    )


def emit_runtime_resume_start(*, plan_ref: str, state_ref: str, node_id: str) -> Any:
    return _emit_runtime_resume_start(
        plan_ref=plan_ref, state_ref=state_ref, node_id=node_id
    )


def emit_runtime_resume_end(
    *, plan_ref: str, state_ref: str, node_id: str, outcome: str
) -> Any:
    return _emit_runtime_resume_end(
        plan_ref=plan_ref, state_ref=state_ref, node_id=node_id, outcome=outcome
    )


def emit_runtime_event_publisher_publish(
    *, event_type: str, trace_id: str, outcome: str = "success"
) -> Any:
    return _emit_runtime_event_publisher_publish(
        event_type=event_type, trace_id=trace_id, outcome=outcome
    )


def emit_runtime_observed(*, observed_at: str, detail: str, run_id: str | None = None) -> Any:
    return _emit_runtime_observed(observed_at=observed_at, detail=detail, run_id=run_id)


def emit_exception_finally(
    *, boundary: str, trace_id: str | None = None, outcome: str = "failure"
) -> Any:
    return _emit_exception_finally(boundary=boundary, trace_id=trace_id, outcome=outcome)


def emit_lifecycle_finally(*, boundary: str, trace_id: str | None = None) -> Any:
    return _emit_lifecycle_finally(boundary=boundary, trace_id=trace_id)


__all__ = [
    "ReflectorClass",
    "emit_exception_finally",
    "emit_lifecycle_finally",
    "emit_runtime_checkpoint_create",
    "emit_runtime_event_publisher_publish",
    "emit_runtime_observed",
    "emit_runtime_reducer_apply_end",
    "emit_runtime_reducer_apply_start",
    "emit_runtime_resume_end",
    "emit_runtime_resume_start",
    "set_active_run_id",
    "setup",
]


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine.reflector.runtime",
    provides=["event.bus.reflector.runtime"],
    requires=[],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=("runtime publisher（ADR-0181）：event.bus.reflector.runtime 由本 plugin 发出。"),
    test_suite="tests/plugins/events/publishers/test_events_spine_reflector_runtime.py",
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
            descriptors=("event.bus.reflector.runtime.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.lifecycle.finally",
            "spine.exception.finally",
            "spine.runtime.reducer.apply",
            "spine.runtime.checkpoint.create",
            "spine.runtime.resume.start",
            "spine.runtime.resume.end",
            "spine.runtime.event_publisher.publish",
            "spine.runtime.observed",
        ),
        state_mutation="forbidden",
    ),
    marker_class=ReflectorClass,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """events.spine.reflector.runtime boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.reflector.runtime", ReflectorClass)
