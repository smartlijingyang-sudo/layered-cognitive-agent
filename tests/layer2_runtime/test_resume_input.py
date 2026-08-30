from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.protocols.resume_input import ResumeInput
from lca.runtime.resume_input import HumanAnswerResumeInputAdapter


def test_human_answer_adapter_preserves_empty_resume_without_turn() -> None:
    normalized = HumanAnswerResumeInputAdapter().normalize(None)

    assert normalized == ResumeInput(input_value=None)


def test_human_answer_adapter_projects_text_into_auditable_turn() -> None:
    normalized = HumanAnswerResumeInputAdapter().normalize("继续执行")

    assert normalized.input_value == "继续执行"
    assert normalized.turn is not None
    assert normalized.turn.decision.action_type is ActionType.ASK_HUMAN
    assert normalized.turn.decision.tool_calls[0].tool_name == "askUserQuestion"
    assert normalized.turn.observation.payload == "继续执行"
    assert normalized.turn.observation.extra == {
        "source": "human_answer",
        "tool_name": "askUserQuestion",
    }


def test_human_answer_adapter_rejects_non_text_input() -> None:
    import pytest

    with pytest.raises(ValueError, match="human answer resume input must be a string"):
        HumanAnswerResumeInputAdapter().normalize({"approved": True})
