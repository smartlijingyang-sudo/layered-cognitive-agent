"""spine_step_tree_accumulator plugin 实现（ADR-0181 试点 + PR-2 复审）。

试点只累积 state；完整 deriver 逻辑（含 step_tree 写 model_visible/）
按 PR-8 迁移。

PR-2 复审：用 :func:`is_spine_event` 替换散落的 ``hasattr`` 守卫。
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

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
from lca_kernel.events import EventRef
from lca_kernel.events.spine_runtime import is_spine_event

log = logging.getLogger(__name__)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


class SpineStepTreeAccumulator:
    """subscriber plugin（FD-2 contained 由机制保证）。"""

    _state: ClassVar[list[dict[str, Any]]] = []

    @classmethod
    def reset(cls) -> None:
        cls._state = []

    def __call__(self, payload: Any, ref: EventRef) -> None:
        """subscriber callback（FD-2：抛错被机制 try/except contained）。"""
        if not is_spine_event(payload):
            raise TypeError(
                f"SpineStepTreeAccumulator 只接 SpineEventPayload；got {type(payload).__name__}"
            )
        record = {
            "event_id": ref.event_id,
            "execution_point": payload.execution_point,
            "state_id": payload.payload.get("state_id"),
        }
        self._state.append(record)
        log.debug("step_tree.append ep=%s state_id=%s", payload.execution_point, record["state_id"])


@plugin(
    id="events.spine.step_tree_accumulator",
    provides=["event.bus.step_tree_accumulator"],
    requires=[],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "SpineStepTreeAccumulator（ADR-0181 试点 + PR-2）：subscriber plugin；"
        "yaml 授权 spine.cognition.brain.perceive.* 前缀下的 EP 累积 step_tree。"
    ),
    test_suite="tests/plugins/events/subscribers/test_spine_step_tree_accumulator.py",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.subscribe",)),
        observability=EvidenceContract(
            descriptors=("event.bus.step_tree_accumulator.appended",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(),
        state_mutation="forbidden",
    ),
    marker_class=SpineStepTreeAccumulator,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """spine_step_tree_accumulator boot：注册 subscriber marker 给 ctx。

    # COMPAT(delete-when: PR-6 鉴权三方一致, tracking: ADR-0183)
    # yaml consumer_rules 当前仍按类路径订阅；plugin 上线后逐步迁至
    # registry-based 订阅，PR-6 收口。setup 内部仅注册 marker + 提供 capability。
    """
    ctx.provide("event.bus.step_tree_accumulator", SpineStepTreeAccumulator())


__all__ = ["SpineStepTreeAccumulator", "setup"]
