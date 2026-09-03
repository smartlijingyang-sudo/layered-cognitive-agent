"""spine_reflector_cognition publisher 端到端（ADR-0181 试点盖章条件 1+2 / ADR-0183 PR-7）。"""

from __future__ import annotations

import pytest

from lca_kernel.events.bus import EventBus
from lca_kernel.events.errors import UnauthorizedPublishError
from lca_kernel.events import _DEFAULT_CONFIG_DIR
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def bus() -> EventBus:
    """用工作区 lca_kernel/events/config 构造 EventBus。"""
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    return EventBus(registry)


def test_authorized_publisher_sends(bus: EventBus) -> None:
    """盖章 1: 业务方只调一行 + typed payload + 鉴权声明通过。"""
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    EventBus.set_default(bus)
    try:
        ref = bus.publish(
            SpineEventPayload(
                execution_point="brain.perceive.start",
                channel="fact",
                payload={"state_id": "s1"},
            ),
            producer=ReflectorClass,
        )
        assert ref.category == "spine.cognition.brain.perceive.start"
        assert ref.event_id
    finally:
        EventBus.set_default(None)


def test_unauthorized_publisher_rejected(bus: EventBus) -> None:
    """盖章 2: 未在 yaml publishers 白名单的 plugin 调 publish → UnauthorizedPublish。"""

    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedPublishError):
        bus.publish(
            SpineEventPayload(
                execution_point="brain.perceive.start",
                channel="fact",
                payload={"state_id": "s1"},
            ),
            producer=NotInWhitelist,
        )


# PR-2 cognition 余 15 emit 全覆盖（API 兼容旧 reflector signature）
def test_emit_brain_perceive_end(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_perceive_end,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_brain_perceive_end(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.brain.perceive.end"
    finally:
        EventBus.set_default(None)


def test_emit_brain_think_start(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_think_start,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_brain_think_start(state_id="s1")
        assert ref.category == "spine.cognition.brain.think.start"
    finally:
        EventBus.set_default(None)


def test_emit_brain_think_end(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_think_end,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_brain_think_end(state_id="s1", outcome="failure")
        assert ref.category == "spine.cognition.brain.think.end"
    finally:
        EventBus.set_default(None)


def test_emit_brain_gate_start(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_gate_start,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_brain_gate_start(state_id="s1")
        assert ref.category == "spine.cognition.brain.gate.start"
    finally:
        EventBus.set_default(None)


def test_emit_brain_gate_end(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_gate_end,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_brain_gate_end(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.brain.gate.end"
    finally:
        EventBus.set_default(None)


def test_emit_critic_eval_start(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_critic_eval_start,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_critic_eval_start(state_id="s1")
        assert ref.category == "spine.cognition.critic.eval.start"
    finally:
        EventBus.set_default(None)


def test_emit_critic_eval_end(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_critic_eval_end,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_critic_eval_end(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.critic.eval.end"
    finally:
        EventBus.set_default(None)


def test_emit_reasoner_reason_start(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_reasoner_reason_start,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_reasoner_reason_start(state_id="s1")
        assert ref.category == "spine.cognition.reasoner.reason.start"
    finally:
        EventBus.set_default(None)


def test_emit_reasoner_reason_end(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_reasoner_reason_end,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_reasoner_reason_end(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.reasoner.reason.end"
    finally:
        EventBus.set_default(None)


def test_emit_prompt_assembler_start(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_prompt_assembler_start,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_prompt_assembler_start(
            state_id="s1",
            template_id="t1",
            sections=["a", "b"],
            decision_path="d1",
        )
        assert ref.category == "spine.cognition.prompt_assembler.assemble.start"
    finally:
        EventBus.set_default(None)


def test_emit_prompt_assembler_end(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_prompt_assembler_end,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_prompt_assembler_end(
            state_id="s1",
            template_id="t1",
            section_count=3,
            outcome="success",
        )
        assert ref.category == "spine.cognition.prompt_assembler.assemble.end"
    finally:
        EventBus.set_default(None)


def test_emit_synthesizer_merge(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_synthesizer_merge,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_synthesizer_merge(state_id="s1", candidate_count=5, outcome="success")
        assert ref.category == "spine.cognition.synthesizer.merge"
    finally:
        EventBus.set_default(None)


def test_emit_skill_router_route(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_skill_router_route,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_skill_router_route(
            state_id="s1", template="t1", decision_path="d1", outcome="success"
        )
        assert ref.category == "spine.cognition.skill_router.route"
    finally:
        EventBus.set_default(None)


def test_emit_memory_read(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_memory_read,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_memory_read(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.memory.read"
    finally:
        EventBus.set_default(None)


def test_emit_memory_write(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_memory_write,
    )

    EventBus.set_default(bus)
    try:
        ref = emit_memory_write(state_id="s1", layer="L1", record_id="r1", outcome="success")
        assert ref.category == "spine.cognition.memory.write"
    finally:
        EventBus.set_default(None)
