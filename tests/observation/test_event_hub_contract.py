"""M0 — EventHubConfig contract tests.

Test behavior, not implementation:
- validate_fanout_table raises EventHubConfigError with literal message
  for duplicate ep or duplicate observer (the rules a future dev can break).
- extra="forbid" and frozen=True are first-class Pydantic features; assert
  with the literal exception type Pydantic raises, not just "not None".
- Happy path constructs without error (sanity that valid config wires up).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.observability.observation import (
    EventHubConfig,
    EventHubConfigError,
    FanoutRule,
    validate_fanout_table,
)


def test_validate_fanout_table_rejects_duplicate_ep() -> None:
    with pytest.raises(EventHubConfigError, match="duplicate ep"):
        validate_fanout_table(
            (
                FanoutRule(
                    ep="phase_graph.node.start", observer_capability="observation.node_enter"
                ),
                FanoutRule(
                    ep="phase_graph.node.start", observer_capability="observation.node_exit"
                ),
            )
        )


def test_validate_fanout_table_rejects_duplicate_observer() -> None:
    with pytest.raises(EventHubConfigError, match="duplicate observer_capability"):
        validate_fanout_table(
            (
                FanoutRule(
                    ep="phase_graph.node.start", observer_capability="observation.node_enter"
                ),
                FanoutRule(ep="phase_graph.node.end", observer_capability="observation.node_enter"),
            )
        )


def test_validate_fanout_table_happy_path() -> None:
    """3 SPINE EPs mapped to 3 distinct observer capabilities — the real
    configuration the plugin will ship with."""
    validate_fanout_table(
        (
            FanoutRule(
                ep="phase_graph.node.start",
                observer_capability="observation.node_enter",
            ),
            FanoutRule(
                ep="phase_graph.node.end",
                observer_capability="observation.node_exit",
            ),
            FanoutRule(
                ep="runtime.reducer.apply",
                observer_capability="observation.runtime_bookkeeping",
            ),
        )
    )


def test_validate_fanout_table_accepts_empty() -> None:
    """Empty table is a valid degenerate case (no fanout at all)."""
    validate_fanout_table(())


def test_fanout_rule_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        FanoutRule(ep="x", observer_capability="a", unknown_field="boom")  # type: ignore[call-arg]


def test_fanout_rule_is_frozen() -> None:
    rule = FanoutRule(ep="x", observer_capability="a")
    with pytest.raises(ValidationError):
        rule.ep = "y"  # type: ignore[misc]


def test_event_hub_config_pydantic_validator_catches_duplicate_ep() -> None:
    """Constructing EventHubConfig directly with duplicate ep must fail
    at the Pydantic layer too — so even callers that skip
    `validate_fanout_table` get caught."""
    with pytest.raises(ValidationError, match="duplicate ep"):
        EventHubConfig(
            rules=(
                FanoutRule(ep="x", observer_capability="a"),
                FanoutRule(ep="x", observer_capability="b"),
            )
        )


def test_event_hub_config_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        EventHubConfig(rules=(), bonus="nope")  # type: ignore[call-arg]

