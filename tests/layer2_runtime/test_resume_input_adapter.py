from __future__ import annotations

import pytest

from lca.contracts.models.core.message import agent_message_text
from lca.layer2_runtime.resume_input import HumanAnswerResumeInputAdapter


def test_human_answer_adapter_preserves_text_and_none() -> None:
    adapter = HumanAnswerResumeInputAdapter()
    assert adapter.normalize(None).input_value is None
    normalized = adapter.normalize("approved")
    assert normalized.input_value == "approved"
    assert normalized.turn is not None
    assert normalized.turn.observation.payload == "approved"


def test_human_answer_adapter_normalizes_agent_message_text() -> None:
    message = agent_message_text("approved")

    normalized = HumanAnswerResumeInputAdapter().normalize(message)

    assert normalized.input_value is message
    assert normalized.turn is not None
    assert normalized.turn.observation.payload == "approved"


def test_human_answer_adapter_rejects_non_text_carrier_values() -> None:
    with pytest.raises(
        ValueError, match="human answer resume input must be a string or AgentMessage"
    ):
        HumanAnswerResumeInputAdapter().normalize({"answer": "approved"})
