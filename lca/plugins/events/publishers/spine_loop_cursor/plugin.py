"""spine_loop_cursor plugin（ADR-0181 PR-10 / ADR-0183 PR-7）。

# COMPAT(delete-when: cursor 完全切到 EventBus, tracking: ADR-0169)
# cursor phase.fold / step.record_* / writable.iteration.* EP 都从此
# EventBus 入口走；旧 self._spine.append 路径在 cursor worktree
# 改造 PR 中被替身（PR-10 仅引入入口骨架，不动 cursor 内部）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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
from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

log = logging.getLogger(__name__)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


class LoopCursorPlugin:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""

    @staticmethod
    def send(
        *,
        execution_point: str,
        channel: str,
        payload: dict[str, Any],
    ) -> EventRef:
        """cursor 一行 publish 入口（PR-10 旧 _spine.append 替身 / PR-3d 走 helper）。"""
        cat_str = _SPINE_EP_TO_CATEGORY.get(execution_point)
        if cat_str is None:
            raise ValueError(
                f"spine EP {execution_point!r} 未登记 category 映射（PR-10 cursor 切"
                " EventBus 时一并登记）"
            )
        sp = SpineEventPayload(
            category=Category(cat_str),
            execution_point=execution_point,
            channel=channel,
            payload=payload,
        )
        return publish_via_session(sp, producer=LoopCursorPlugin)


@plugin(
    id="events.spine.loop_cursor",
    provides=["event.bus.loop_cursor"],
    requires=[],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "spine_loop_cursor publisher（ADR-0181 PR-10）：EventBus 入口骨架；"
        "cursor phase.fold / step.record_* / writable.iteration.* EP 由本 plugin 发出。"
    ),
    test_suite="tests/plugins/events/publishers/test_spine_loop_cursor.py",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(descriptors=("event.bus.loop_cursor.published",)),
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
            "spine.step.thinking.record",
            "spine.step.tool_call.record",
            "spine.step.tool_result.record",
            "spine.step.reflect.record",
            "spine.step.span.record",
        ),
        state_mutation="forbidden",
    ),
    marker_class=LoopCursorPlugin,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """spine_loop_cursor boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.loop_cursor", LoopCursorPlugin)


__all__ = ["LoopCursorPlugin", "setup"]
