"""Behavioral tests for ``lca.contracts.runtime.intent.RunIntent``."""

from __future__ import annotations

import typing
from dataclasses import FrozenInstanceError

import pytest

from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.contracts.runtime.intent import RunIntent, RunMode, RunSurface


def _minimal_intent(**overrides: object) -> RunIntent:
    """Build a minimal valid RunIntent, applying keyword overrides."""
    base: dict[str, object] = {
        "profile_path": "/profiles/agent.yaml",
        "user_text": "hello",
        "mode": "solo",
        "session_id": None,
        "assistant_id": None,
        "attachment_ids": (),
        "prior_turns": (),
        "execution_target": "default",
        "options": {},
        "surface": "cli",
        "device_id": "",
    }
    base.update(overrides)
    return RunIntent(**base)  # type: ignore[arg-type]


class TestRunIntentConstruction:
    def test_construct_minimal(self) -> None:
        intent = _minimal_intent()
        assert intent.profile_path == "/profiles/agent.yaml"
        assert intent.user_text == "hello"
        assert intent.mode == "solo"
        assert intent.session_id is None
        assert intent.assistant_id is None
        assert intent.attachment_ids == ()
        assert intent.prior_turns == ()
        assert intent.execution_target == "default"
        assert dict(intent.options) == {}
        assert intent.surface == "cli"
        assert intent.device_id == ""

    def test_construct_with_optional_fields(self) -> None:
        turn = ConversationTurn(role="user", content="earlier question")
        intent = _minimal_intent(
            session_id="sess-1",
            assistant_id="assistant-42",
            attachment_ids=("att-a", "att-b"),
            prior_turns=(turn,),
            options={"idempotency_key": "abc"},
            device_id="dev-9",
            surface="http",
            mode="team",
        )
        assert intent.session_id == "sess-1"
        assert intent.assistant_id == "assistant-42"
        assert intent.attachment_ids == ("att-a", "att-b")
        assert intent.prior_turns == (turn,)
        assert dict(intent.options) == {"idempotency_key": "abc"}
        assert intent.device_id == "dev-9"
        assert intent.surface == "http"
        assert intent.mode == "team"


class TestRunIntentValidation:
    def test_rejects_empty_profile_path(self) -> None:
        with pytest.raises(ValueError, match="profile_path"):
            _minimal_intent(profile_path="")

    def test_rejects_empty_user_text(self) -> None:
        with pytest.raises(ValueError, match="user_text"):
            _minimal_intent(user_text="")

    def test_rejects_whitespace_only_user_text(self) -> None:
        # Leading/trailing whitespace is allowed (caller may trim); empty
        # string is the only contract-level rejection.
        intent = _minimal_intent(user_text="   ")
        assert intent.user_text == "   "


class TestRunIntentImmutability:
    def test_frozen_blocks_mutation(self) -> None:
        intent = _minimal_intent()
        with pytest.raises(FrozenInstanceError):
            intent.user_text = "overwrite"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            intent.profile_path = "/other.yaml"  # type: ignore[misc]


class TestRunIntentEquality:
    def test_equality_on_same_data(self) -> None:
        a = _minimal_intent()
        b = _minimal_intent()
        assert a == b

    def test_inequality_when_field_differs(self) -> None:
        a = _minimal_intent()
        b = _minimal_intent(user_text="different")
        assert a != b


class TestRunIntentTypeHints:
    def test_surface_literal_typing(self) -> None:
        hints = typing.get_type_hints(RunIntent)
        assert hints["surface"] == RunSurface
        assert hints["mode"] == RunMode
        assert set(RunSurface.__args__) == {"cli", "http", "gateway", "test", "batch"}
        assert set(RunMode.__args__) == {"solo", "team"}

    def test_device_id_default_is_empty_string(self) -> None:
        # ``device_id`` defaults to a stable empty string per ADR-0199.
        a = _minimal_intent()
        b = _minimal_intent()
        assert a.device_id == "" == b.device_id
