"""Tests for Onboarding naming contracts (ADR-0195 C13, INV-06)."""

import pytest
from pydantic import ValidationError

from lca.contracts.models.onboarding.naming import NamingCandidate, NamingWidgetPayload


def test_naming_candidate_contract_immutability():
    cand = NamingCandidate(id="cand_1", name="Athena", vibe="敏锐高效", emoji="🦉")
    assert cand.id == "cand_1"
    assert cand.name == "Athena"
    assert cand.vibe == "敏锐高效"
    assert cand.emoji == "🦉"

    # Frozen check
    with pytest.raises(ValidationError):
        cand.name = "NewName"  # type: ignore[misc]


def test_naming_candidate_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        NamingCandidate(id="cand_1", name="Athena", vibe="敏锐", unexpected="field")  # type: ignore[call-arg]


def test_naming_widget_payload_contract():
    cand1 = NamingCandidate(id="c1", name="Athena", vibe="敏锐高效")
    cand2 = NamingCandidate(id="c2", name="Nova", vibe="灵动敏捷", emoji="🌟")

    payload = NamingWidgetPayload(
        token="widget_nonce_123",  # noqa: S106
        assistant_id="asst_abc",
        candidates=(cand1, cand2),
        allow_custom=True,
        keep_muse=False,
    )
    assert payload.token == "widget_nonce_123"  # noqa: S105
    assert payload.assistant_id == "asst_abc"
    assert len(payload.candidates) == 2
    assert payload.candidates[0].name == "Athena"
    assert payload.allow_custom is True
    assert payload.keep_muse is False

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        NamingWidgetPayload(  # type: ignore[call-arg]
            token="widget_nonce_t",  # noqa: S106
            assistant_id="a",
            candidates=(),
            extra="disallowed",
        )
