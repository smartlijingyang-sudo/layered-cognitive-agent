from lca.application.initiative.hooks import evaluate_initiative
from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.contracts.models.initiative.models import InitiativeSignal


def test_evaluate_initiative_normal_returns_none():
    features = {"manual_action_counts": {"fetch_weather": 1}}
    offer = evaluate_initiative(features)
    assert offer is None


def test_evaluate_initiative_repeated_3_times_suggests_routine():
    features = {"manual_action_counts": {"fetch_weather": 3}}
    offer = evaluate_initiative(features)
    assert offer is not None
    assert offer.signal == InitiativeSignal.REPEATED_MANUAL
    assert "例程" in offer.nudge_message
    assert offer.proposed_routine == "fetch_weather"


def test_evaluate_initiative_missing_connector():
    features = {"missing_connectors": ["github"]}
    offer = evaluate_initiative(features)
    assert offer is not None
    assert offer.signal == InitiativeSignal.MISSING_CONNECTOR
    assert "github" in offer.nudge_message


# ----- RA-090: pure unit tests for derive_transcript_features ------------------


def _turn(role: str) -> ConversationTurn:
    return ConversationTurn(role=role, content="x")


def test_derive_features_empty_turns_gives_zero_baseline() -> None:
    from lca.application.initiative.hooks import derive_transcript_features

    assert derive_transcript_features(()) == {
        "user_turn_count": 0,
        "assistant_turn_count": 0,
        "manual_action_counts": {},
    }


def test_derive_features_counts_roles_from_prior_turns() -> None:
    from lca.application.initiative.hooks import derive_transcript_features

    turns = [_turn("user"), _turn("assistant"), _turn("user"), _turn("system")]
    features = derive_transcript_features(turns)
    assert features["user_turn_count"] == 2
    assert features["assistant_turn_count"] == 1
    assert features["manual_action_counts"] == {}


def test_derive_features_caller_override_wins() -> None:
    from lca.application.initiative.hooks import derive_transcript_features

    override = {"user_turn_count": 99, "custom": True}
    features = derive_transcript_features([_turn("user")], override)
    assert features == {"user_turn_count": 99, "custom": True}
    # returned copy is detached from the caller's dict
    assert features is not override


def test_derive_features_empty_override_falls_back_to_baseline() -> None:
    from lca.application.initiative.hooks import derive_transcript_features

    features = derive_transcript_features([_turn("assistant")], {})
    assert features["assistant_turn_count"] == 1
