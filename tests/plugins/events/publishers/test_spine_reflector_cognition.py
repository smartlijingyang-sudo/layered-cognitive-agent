"""spine_reflector_cognition publisher 端到端（ADR-0181 试点盖章条件 1+2 / ADR-0183 PR-7）。"""

from __future__ import annotations

from typing import Any

import pytest

from lca_kernel.events.bus import EventBus
from lca_kernel.events.errors import UnauthorizedPublishError
from lca_kernel.events.payloads import SpineEventPayload


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


def test_unauthorized_publisher_rejected(bound_session: Any) -> None:
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


# PR-2 cognition 余 15 emit 全覆盖（API 兼容旧 reflector signature）
def test_emit_brain_perceive_end(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_perceive_end,
    )

    ref = emit_brain_perceive_end(state_id="s1", outcome="success")
    assert ref.category == "spine.cognition.brain.perceive.end"


def test_emit_brain_think_start(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_think_start,
    )

    ref = emit_brain_think_start(state_id="s1")
    assert ref.category == "spine.cognition.brain.think.start"


def test_emit_brain_think_end(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_think_end,
    )

    ref = emit_brain_think_end(state_id="s1", outcome="failure")
    assert ref.category == "spine.cognition.brain.think.end"


def test_emit_brain_gate_start(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_gate_start,
    )

    ref = emit_brain_gate_start(state_id="s1")
    assert ref.category == "spine.cognition.brain.gate.start"


def test_emit_brain_gate_end(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_brain_gate_end,
    )

    ref = emit_brain_gate_end(state_id="s1", outcome="success")
    assert ref.category == "spine.cognition.brain.gate.end"


def test_emit_critic_eval_start(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_critic_eval_start,
    )

    ref = emit_critic_eval_start(state_id="s1")
    assert ref.category == "spine.cognition.critic.eval.start"


def test_emit_critic_eval_end(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_critic_eval_end,
    )

    ref = emit_critic_eval_end(state_id="s1", outcome="success")
    assert ref.category == "spine.cognition.critic.eval.end"


def test_emit_reasoner_reason_start(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_reasoner_reason_start,
    )

    ref = emit_reasoner_reason_start(state_id="s1")
    assert ref.category == "spine.cognition.reasoner.reason.start"


def test_emit_reasoner_reason_end(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_reasoner_reason_end,
    )

    ref = emit_reasoner_reason_end(state_id="s1", outcome="success")
    assert ref.category == "spine.cognition.reasoner.reason.end"


def test_emit_prompt_assembler_start(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_prompt_assembler_start,
    )

    ref = emit_prompt_assembler_start(
        state_id="s1",
        template_id="t1",
        sections=["a", "b"],
        decision_path="d1",
    )
    assert ref.category == "spine.cognition.prompt_assembler.assemble.start"


def test_emit_prompt_assembler_end(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_prompt_assembler_end,
    )

    ref = emit_prompt_assembler_end(
        state_id="s1",
        template_id="t1",
        section_count=3,
        outcome="success",
    )
    assert ref.category == "spine.cognition.prompt_assembler.assemble.end"


def test_emit_synthesizer_merge(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_synthesizer_merge,
    )

    ref = emit_synthesizer_merge(state_id="s1", candidate_count=5, outcome="success")
    assert ref.category == "spine.cognition.synthesizer.merge"


def test_emit_skill_router_route(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_skill_router_route,
    )

    ref = emit_skill_router_route(
        state_id="s1", template="t1", decision_path="d1", outcome="success"
    )
    assert ref.category == "spine.cognition.skill_router.route"


def test_emit_memory_read(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_memory_read,
    )

    ref = emit_memory_read(state_id="s1", outcome="success")
    assert ref.category == "spine.cognition.memory.read"


def test_emit_memory_write(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        emit_memory_write,
    )

    ref = emit_memory_write(state_id="s1", layer="L1", record_id="r1", outcome="success")
    assert ref.category == "spine.cognition.memory.write"
