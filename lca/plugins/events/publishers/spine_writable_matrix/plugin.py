"""spine_writable_matrix plugin（ADR-0181 PR-10 / ADR-0183 PR-7）。

# COMPAT(delete-when: cursor 完全切到 EventBus, tracking: ADR-0181)
# cursor 旧 self._spine.append(execution_point=..., payload=...) 路径仍
# 是 EventSpine 接口。PR-10 提供 EventBus 入口骨架；cursor 改造
# 在 spine-writable-matrix worktree 中分批做（cursor 内部 5+ 处 append
# 需逐个适配；本 PR 不动 cursor 内部代码）。
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
from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

log = logging.getLogger(__name__)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


class WritableMatrixPlugin:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""

    @staticmethod
    def send(
        *,
        execution_point: str,
        channel: str,
        payload: dict[str, Any],
    ) -> EventRef:
        """cursor 一行 EventBus 入口（PR-10 旧 _spine.append 替身）。"""
        from lca_kernel.events.bus import EventBus

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
        return EventBus.default().publish(sp, producer=WritableMatrixPlugin)


@plugin(
    id="events.spine.writable_matrix",
    provides=["event.bus.writable_matrix"],
    requires=["event.bus"],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "spine_writable_matrix publisher（ADR-0181 PR-10）：EventBus 入口骨架；"
        "writable.step.* / writable.segment.* / writable.iteration.* EP 由本 plugin 发出。"
    ),
    test_suite="tests/plugins/events/publishers/test_spine_writable_matrix.py",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(descriptors=("event.bus.writable_matrix.published",)),
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
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """spine_writable_matrix boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.writable_matrix", WritableMatrixPlugin)


__all__ = ["WritableMatrixPlugin", "setup"]
