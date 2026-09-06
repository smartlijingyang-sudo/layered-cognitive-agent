"""spine_reflector_assistant publisher tests."""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.observability.assistant_ep_closure import ASSISTANT_SKILL_INSTALLED


def test_emit_assistant_skill_installed(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_assistant.plugin import (
        emit_assistant_domain_event,
    )

    ref = emit_assistant_domain_event(
        execution_point=ASSISTANT_SKILL_INSTALLED,
        payload={
            "assistant_id": "asst_test",
            "revision_seq": 1,
            "manifest_digest": "sha256:abc",
            "actor": "agent",
            "skill_id": "demo-skill",
            "skill_digest": "sha256:def",
            "artifact_state": "verified",
        },
    )
    assert ref is not None
    assert ref.category == "spine.assistant.skill.installed"


def test_emit_without_session_logs(caplog: pytest.LogCaptureFixture) -> None:
    from lca.plugins.events.publishers.spine_reflector_assistant.plugin import (
        emit_assistant_domain_event,
    )

    ref = emit_assistant_domain_event(
        execution_point=ASSISTANT_SKILL_INSTALLED,
        payload={"assistant_id": "asst_test", "skill_id": "x"},
    )
    assert ref is None
