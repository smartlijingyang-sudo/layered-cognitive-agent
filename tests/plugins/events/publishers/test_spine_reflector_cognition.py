"""spine_reflector_cognition publisher 端到端（ADR-0181 试点盖章条件 1+2）。"""
from __future__ import annotations

import pytest

from lca_kernel.events.errors import UnauthorizedPublishError
from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism(tmp_path) -> EventMechanism:
    """用工作区 lca_kernel/events/config 构造机制；tmp_path 透传给 sink 落盘。"""
    from pathlib import Path

    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventMechanism(EventRegistry.load(config_dir))


def test_authorized_publisher_sends(monkeypatch, mechanism: EventMechanism) -> None:
    """盖章 1: 业务方只调一行 + typed payload + 鉴权声明通过。"""
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = mechanism.send(
            SpineEventPayload(
                execution_point="brain.perceive.start",
                channel="fact",
                payload={"state_id": "s1"},
            ),
            plugin=ReflectorClass,
        )
        assert ref.category == "spine.cognition.brain.perceive.start"
        assert ref.event_id
    finally:
        EventMechanism.set_default(None)


def test_unauthorized_publisher_rejected(mechanism: EventMechanism) -> None:
    """盖章 2: 未在 yaml publishers 白名单的 plugin 调 send → UnauthorizedPublish。"""
    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedPublishError):
        mechanism.send(
            SpineEventPayload(
                execution_point="brain.perceive.start",
                channel="fact",
                payload={"state_id": "s1"},
            ),
            plugin=NotInWhitelist,
        )


# PR-2 cognition 余 15 emit 全覆盖（API 兼容旧 reflector signature）
def test_emit_brain_perceive_end(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_perceive_end,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_brain_perceive_end(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.brain.perceive.end"
    finally:
        EventMechanism.set_default(None)


def test_emit_brain_think_start(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_think_start,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_brain_think_start(state_id="s1")
        assert ref.category == "spine.cognition.brain.think.start"
    finally:
        EventMechanism.set_default(None)


def test_emit_brain_think_end(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_think_end,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_brain_think_end(state_id="s1", outcome="failure")
        assert ref.category == "spine.cognition.brain.think.end"
    finally:
        EventMechanism.set_default(None)


def test_emit_brain_gate_start(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_gate_start,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_brain_gate_start(state_id="s1")
        assert ref.category == "spine.cognition.brain.gate.start"
    finally:
        EventMechanism.set_default(None)


def test_emit_brain_gate_end(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_gate_end,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_brain_gate_end(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.brain.gate.end"
    finally:
        EventMechanism.set_default(None)


def test_emit_critic_eval_start(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_critic_eval_start,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_critic_eval_start(state_id="s1")
        assert ref.category == "spine.cognition.critic.eval.start"
    finally:
        EventMechanism.set_default(None)


def test_emit_critic_eval_end(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_critic_eval_end,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_critic_eval_end(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.critic.eval.end"
    finally:
        EventMechanism.set_default(None)


def test_emit_reasoner_reason_start(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_reasoner_reason_start,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_reasoner_reason_start(state_id="s1")
        assert ref.category == "spine.cognition.reasoner.reason.start"
    finally:
        EventMechanism.set_default(None)


def test_emit_reasoner_reason_end(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_reasoner_reason_end,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_reasoner_reason_end(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.reasoner.reason.end"
    finally:
        EventMechanism.set_default(None)


def test_emit_prompt_assembler_start(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_prompt_assembler_start,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_prompt_assembler_start(
            state_id="s1",
            template_id="t1",
            sections=["a", "b"],
            decision_path="d1",
        )
        assert ref.category == "spine.cognition.prompt_assembler.assemble.start"
    finally:
        EventMechanism.set_default(None)


def test_emit_prompt_assembler_end(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_prompt_assembler_end,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_prompt_assembler_end(
            state_id="s1",
            template_id="t1",
            section_count=3,
            outcome="success",
        )
        assert ref.category == "spine.cognition.prompt_assembler.assemble.end"
    finally:
        EventMechanism.set_default(None)


def test_emit_synthesizer_merge(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_synthesizer_merge,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_synthesizer_merge(state_id="s1", candidate_count=5, outcome="success")
        assert ref.category == "spine.cognition.synthesizer.merge"
    finally:
        EventMechanism.set_default(None)


def test_emit_skill_router_route(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_skill_router_route,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_skill_router_route(
            state_id="s1", template="t1", decision_path="d1", outcome="success"
        )
        assert ref.category == "spine.cognition.skill_router.route"
    finally:
        EventMechanism.set_default(None)


def test_emit_memory_read(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_memory_read,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_memory_read(state_id="s1", outcome="success")
        assert ref.category == "spine.cognition.memory.read"
    finally:
        EventMechanism.set_default(None)


def test_emit_memory_write(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_memory_write,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = emit_memory_write(state_id="s1", layer="L1", record_id="r1", outcome="success")
        assert ref.category == "spine.cognition.memory.write"
    finally:
        EventMechanism.set_default(None)
