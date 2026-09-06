"""spine_reflector_cognition publisher 端到端（ADR-0181 / ADR-0194 P2-11）。"""

from __future__ import annotations

import pytest

from lca.loop.fact_gateway import reset_fact_gateway_env
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session
from lca_kernel.events.bus import EventBus
from lca_kernel.events.errors import UnauthorizedPublishError
from lca_kernel.events.payloads import SpineEventPayload


def test_authorized_publisher_sends(bus: EventBus) -> None:
    """盖章 1: 业务方只调一行 + typed payload + 鉴权声明通过。"""
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import ReflectorClass

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


def test_unauthorized_publisher_rejected(bound_session) -> None:
    """盖章 2: 未在 yaml publishers 白名单的 plugin 走 session 路径 → UnauthorizedPublish。"""
    from lca.plugins.events.publishers._session_publish import publish_via_session

    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedPublishError):
        publish_via_session(
            SpineEventPayload(
                execution_point="brain.perceive.start",
                channel="fact",
                payload={"state_id": "s1"},
            ),
            producer=NotInWhitelist,
        )


def _session_emit_test(emit_fn, expected_type: str) -> None:
    session = Session("cognition-reflector")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:
        receipt = emit_fn()
        assert receipt is not None
        events = [event for event in session.snapshot_events() if event.type == expected_type]
        assert len(events) == 1
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)


def test_emit_brain_perceive_end() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_perceive_end,
    )

    _session_emit_test(
        lambda: emit_brain_perceive_end(state_id="s1", outcome="success"),
        "spine.cognition.brain.perceive.end",
    )


def test_emit_brain_think_start() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_think_start,
    )

    _session_emit_test(
        lambda: emit_brain_think_start(state_id="s1"),
        "spine.cognition.brain.think.start",
    )


def test_emit_brain_think_end() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import emit_brain_think_end

    _session_emit_test(
        lambda: emit_brain_think_end(state_id="s1", outcome="failure"),
        "spine.cognition.brain.think.end",
    )


def test_emit_think_gate_start() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import emit_think_gate_start

    _session_emit_test(
        lambda: emit_think_gate_start(state_id="s1"),
        "spine.cognition.think.gate.start",
    )


def test_emit_brain_gate_start_compat_alias() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import emit_brain_gate_start

    _session_emit_test(
        lambda: emit_brain_gate_start(state_id="s1"),
        "spine.cognition.think.gate.start",
    )


def test_emit_think_gate_end() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import emit_think_gate_end

    _session_emit_test(
        lambda: emit_think_gate_end(state_id="s1", outcome="success"),
        "spine.cognition.think.gate.end",
    )


def test_emit_brain_gate_end_compat_alias() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import emit_brain_gate_end

    _session_emit_test(
        lambda: emit_brain_gate_end(state_id="s1", outcome="success"),
        "spine.cognition.think.gate.end",
    )


def test_emit_critic_eval_start() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_critic_eval_start,
    )

    _session_emit_test(
        lambda: emit_critic_eval_start(state_id="s1"),
        "spine.cognition.critic.eval.start",
    )


def test_emit_critic_eval_end() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import emit_critic_eval_end

    _session_emit_test(
        lambda: emit_critic_eval_end(state_id="s1", outcome="success"),
        "spine.cognition.critic.eval.end",
    )


def test_emit_reasoner_reason_start() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_reasoner_reason_start,
    )

    _session_emit_test(
        lambda: emit_reasoner_reason_start(state_id="s1"),
        "spine.cognition.reasoner.reason.start",
    )


def test_emit_reasoner_reason_end() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_reasoner_reason_end,
    )

    _session_emit_test(
        lambda: emit_reasoner_reason_end(state_id="s1", outcome="success"),
        "spine.cognition.reasoner.reason.end",
    )


def test_emit_prompt_assembler_start() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_prompt_assembler_start,
    )

    _session_emit_test(
        lambda: emit_prompt_assembler_start(
            state_id="s1",
            template_id="react_prompt",
            sections=["role"],
            decision_path="profile_default",
        ),
        "spine.cognition.prompt_assembler.assemble.start",
    )


def test_emit_prompt_assembler_end() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_prompt_assembler_end,
    )

    _session_emit_test(
        lambda: emit_prompt_assembler_end(
            state_id="s1",
            template_id="react_prompt",
            section_count=1,
            total_chars=42,
        ),
        "spine.cognition.prompt_assembler.assemble.end",
    )


def test_emit_synthesizer_merge() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_synthesizer_merge,
    )

    _session_emit_test(
        lambda: emit_synthesizer_merge(state_id="s1", candidate_count=5, outcome="success"),
        "spine.cognition.synthesizer.merge",
    )


def test_emit_skill_router_route() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_skill_router_route,
    )

    _session_emit_test(
        lambda: emit_skill_router_route(
            state_id="s1",
            template="research_prompt",
            decision_path="keyword_match",
        ),
        "spine.cognition.skill_router.route",
    )


def test_emit_memory_read() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import emit_memory_read

    _session_emit_test(
        lambda: emit_memory_read(state_id="s1", outcome="success"),
        "spine.cognition.memory.read",
    )


def test_emit_memory_write() -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import emit_memory_write

    _session_emit_test(
        lambda: emit_memory_write(state_id="s1", layer="L1", record_id="r1", outcome="success"),
        "spine.cognition.memory.write",
    )
