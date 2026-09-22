from lca.application.initiative.hooks import evaluate_initiative
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
