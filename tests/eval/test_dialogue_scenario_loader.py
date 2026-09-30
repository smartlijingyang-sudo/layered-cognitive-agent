"""验证多轮对话场景评测 Loader 与 DTO 模型的解析契约与强类型断言。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.application.eval.dialogue_scenario_loader import (
    load_commercial_scenarios,
    parse_dialogue_scenarios_from_yaml,
)
from lca.application.eval.dialogue_scenario_models import (
    CommercialEvalSuite,
    DialogueScenario,
    DialogueTurn,
)


def test_load_commercial_scenarios_returns_16_typed_scenarios() -> None:
    scenarios = load_commercial_scenarios()
    assert len(scenarios) == 16
    for sc in scenarios:
        assert isinstance(sc, DialogueScenario)
        assert sc.id
        assert sc.title
        assert sc.quadrant
        assert len(sc.turns) >= 3
        for turn in sc.turns:
            assert isinstance(turn, DialogueTurn)
            assert turn.turn >= 1
            assert turn.user
            assert turn.expected_behavior


def test_first_scenario_detailed_structure() -> None:
    scenarios = load_commercial_scenarios()
    first = scenarios[0]
    assert first.id == "MEM_CROSS_TOPIC_REMIND"
    assert first.quadrant == "muse_memory"
    assert "胃酸反流" in first.turns[0].user
    assert "INV-EVAL-WRITE-BEFORE-REPLY" in first.turns[0].invariants
    assert len(first.turns[0].checklist) >= 1


def test_dialogue_scenario_models_are_frozen() -> None:
    scenarios = load_commercial_scenarios()
    sc = scenarios[0]
    with pytest.raises(ValidationError):
        # Attempting mutation on frozen model
        sc.title = "New Title"  # type: ignore[misc]


def test_models_forbid_extra_fields() -> None:
    invalid_yaml = """
version: "1.0"
scenarios:
  - id: TEST_EXTRA
    quadrant: muse_memory
    title: "Test Extra Field"
    unexpected_field: "hacked"
    turns:
      - turn: 1
        user: "hi"
        expected_behavior: "greet"
"""
    with pytest.raises(ValidationError):
        parse_dialogue_scenarios_from_yaml(invalid_yaml)


def test_parse_dialogue_scenarios_from_yaml_valid() -> None:
    valid_yaml = """
version: "1.0"
scenarios:
  - id: TEST_VALID
    quadrant: grok_wit
    title: "Test Valid Scenario"
    description: "Sample description"
    turns:
      - turn: 1
        user: "how are you?"
        expected_behavior: "answer wittily"
        checklist: ["is witty?"]
        invariants: ["INV-EVAL-TOOL-LEAKAGE-ZERO"]
"""
    suite = parse_dialogue_scenarios_from_yaml(valid_yaml)
    assert isinstance(suite, CommercialEvalSuite)
    assert len(suite.scenarios) == 1
    assert suite.scenarios[0].id == "TEST_VALID"
