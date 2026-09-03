"""spine_reflector_cognition plugin（ADR-0181 试点 + PR-2 cognition 全迁 / ADR-0183 PR-7）。

试点（已合并）：emit_brain_perceive_start
PR-2（本）：cognition 余 15 emit 全迁；signature 严格对齐旧
lca/plugins/observability/spine/reflectors/cognition.py，确保
lca/cognition/brain/reasoner.py 等调用方零改动。旧 _safe_append
的 outcome 字段映射到 payload.outcome（ShellEventPayload 用 payload
承载，不另开字段，保留旧 API 兼容）。

业务方一行调：
    EventBus.default().publish(
        SpineEventPayload(execution_point="...", channel="...", payload={...}),
        producer=ReflectorClass,
    )
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
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
from lca_kernel.events.bus import EventBus
from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

log = logging.getLogger(__name__)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> Any:
    """内部 helper：构造 SpineEventPayload + EventBus.publish。

    category 由 execution_point 通过 _SPINE_EP_TO_CATEGORY 派生。
    """
    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


def emit_brain_perceive_start(*, state_id: str) -> Any:
    return _send(
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": state_id},
    )


def emit_brain_perceive_end(*, state_id: str, outcome: str = "success") -> Any:
    return _send(
        execution_point="brain.perceive.end",
        channel="fact",
        payload={"state_id": state_id, "outcome": outcome},
    )


def emit_brain_think_start(*, state_id: str) -> Any:
    return _send(
        execution_point="brain.think.start",
        channel="fact",
        payload={"state_id": state_id},
    )


def emit_brain_think_end(*, state_id: str, outcome: str = "success") -> Any:
    return _send(
        execution_point="brain.think.end",
        channel="fact",
        payload={"state_id": state_id, "outcome": outcome},
    )


def emit_brain_gate_start(*, state_id: str) -> Any:
    return _send(
        execution_point="brain.gate.start",
        channel="control",
        payload={"state_id": state_id},
    )


def emit_brain_gate_end(*, state_id: str, outcome: str = "success") -> Any:
    return _send(
        execution_point="brain.gate.end",
        channel="control",
        payload={"state_id": state_id, "outcome": outcome},
    )


def emit_critic_eval_start(*, state_id: str) -> Any:
    return _send(
        execution_point="critic.eval.start",
        channel="fact",
        payload={"state_id": state_id},
    )


def emit_critic_eval_end(*, state_id: str, outcome: str = "success") -> Any:
    return _send(
        execution_point="critic.eval.end",
        channel="fact",
        payload={"state_id": state_id, "outcome": outcome},
    )


def emit_reasoner_reason_start(*, state_id: str) -> Any:
    return _send(
        execution_point="reasoner.reason.start",
        channel="fact",
        payload={"state_id": state_id},
    )


def emit_reasoner_reason_end(*, state_id: str, outcome: str = "success") -> Any:
    return _send(
        execution_point="reasoner.reason.end",
        channel="fact",
        payload={"state_id": state_id, "outcome": outcome},
    )


def emit_prompt_assembler_start(
    *,
    state_id: str,
    template_id: str,
    sections: Sequence[str] | None = None,
    decision_path: str | None = None,
    activated_skills: Sequence[str] | None = None,
    tools_count: int | None = None,
    available_skills_count: int | None = None,
) -> Any:
    payload: dict[str, Any] = {"state_id": state_id, "template_id": template_id}
    if sections is not None:
        payload["sections"] = list(sections)
    if decision_path is not None:
        payload["decision_path"] = decision_path
    if activated_skills is not None:
        payload["activated_skills"] = list(activated_skills)
    if tools_count is not None:
        payload["tools_count"] = tools_count
    if available_skills_count is not None:
        payload["available_skills_count"] = available_skills_count
    return _send(
        execution_point="prompt_assembler.assemble.start",
        channel="fact",
        payload=payload,
    )


def emit_prompt_assembler_end(
    *,
    state_id: str,
    template_id: str,
    section_count: int,
    section_outputs: Sequence[Mapping[str, Any]] | None = None,
    total_chars: int | None = None,
    outcome: str = "success",
) -> Any:
    payload: dict[str, Any] = {
        "state_id": state_id,
        "template_id": template_id,
        "section_count": section_count,
        "outcome": outcome,
    }
    if section_outputs is not None:
        payload["section_outputs"] = [
            {k: v for k, v in dict(item).items() if v is not None} for item in section_outputs
        ]
    if total_chars is not None:
        payload["total_chars"] = total_chars
    return _send(
        execution_point="prompt_assembler.assemble.end",
        channel="fact",
        payload=payload,
    )


def emit_synthesizer_merge(*, state_id: str, candidate_count: int, outcome: str = "success") -> Any:
    return _send(
        execution_point="synthesizer.merge",
        channel="fact",
        payload={"state_id": state_id, "candidate_count": candidate_count, "outcome": outcome},
    )


def emit_skill_router_route(
    *,
    state_id: str,
    template: str,
    decision_path: str | None = None,
    outcome: str = "success",
) -> Any:
    payload: dict[str, Any] = {
        "state_id": state_id,
        "template": template,
        "outcome": outcome,
    }
    if decision_path is not None:
        payload["decision_path"] = decision_path
    return _send(
        execution_point="skill_router.route",
        channel="control",
        payload=payload,
    )


def emit_memory_read(*, state_id: str, outcome: str = "success") -> Any:
    return _send(
        execution_point="memory.read",
        channel="fact",
        payload={"state_id": state_id, "outcome": outcome},
    )


def emit_memory_write(
    *,
    state_id: str,
    layer: str,
    record_id: str | None = None,
    outcome: str = "success",
) -> Any:
    payload: dict[str, Any] = {
        "state_id": state_id,
        "layer": layer,
        "outcome": outcome,
    }
    if record_id is not None:
        payload["record_id"] = record_id
    return _send(
        execution_point="memory.write",
        channel="fact",
        payload=payload,
    )


__all__ = [
    "ReflectorClass",
    "emit_brain_gate_end",
    "emit_brain_gate_start",
    "emit_brain_perceive_end",
    "emit_brain_perceive_start",
    "emit_brain_think_end",
    "emit_brain_think_start",
    "emit_critic_eval_end",
    "emit_critic_eval_start",
    "emit_memory_read",
    "emit_memory_write",
    "emit_prompt_assembler_end",
    "emit_prompt_assembler_start",
    "emit_reasoner_reason_end",
    "emit_reasoner_reason_start",
    "emit_skill_router_route",
    "emit_synthesizer_merge",
    "setup",
]


@plugin(
    id="events.spine.reflector.cognition",
    provides=["event.bus.reflector.cognition"],
    requires=["event.bus"],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "spine_reflector_cognition publisher（ADR-0181 PR-2）：cognition 16 emit 由本 plugin 发出；"
        "覆盖 brain / critic / reasoner / prompt_assembler / synthesizer / skill_router / memory。"
    ),
    test_suite="tests/plugins/events/publishers/test_spine_reflector_cognition.py",
    functional_group=FunctionalGroup.G5_COGNITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.cognition.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.cognition.brain.perceive.start",
            "spine.cognition.brain.perceive.end",
            "spine.cognition.brain.think.start",
            "spine.cognition.brain.think.end",
            "spine.cognition.brain.gate.start",
            "spine.cognition.brain.gate.end",
            "spine.cognition.critic.eval.start",
            "spine.cognition.critic.eval.end",
            "spine.cognition.reasoner.reason.start",
            "spine.cognition.reasoner.reason.end",
            "spine.cognition.prompt_assembler.assemble.start",
            "spine.cognition.prompt_assembler.assemble.end",
            "spine.cognition.synthesizer.merge",
            "spine.cognition.skill_router.route",
            "spine.cognition.memory.read",
            "spine.cognition.memory.write",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """spine_reflector_cognition boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.reflector.cognition", ReflectorClass)
