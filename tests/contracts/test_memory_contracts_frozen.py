"""ADR-0249: EpisodeFact is a frozen pydantic model, not a mutable dataclass."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.memory.episode import EpisodeFact, ResidualClass


def _fact() -> EpisodeFact:
    return EpisodeFact(
        fact_id="ep_frozen",
        dedupe_key="identity:role",
        category=MemoryCategory.IDENTITY,
        content="用户身份：架构师",
        residual=ResidualClass.instruction,
        explicit_user_authority=True,
        source_trace_id="t1",
        observed_at_ms=1,
    )


def test_episode_fact_is_frozen_and_forbids_extra() -> None:
    fact = _fact()
    assert fact.model_config.get("frozen") is True
    assert fact.model_config.get("extra") == "forbid"
    copied = fact.model_copy(update={"content": "用户身份：其他"})
    assert copied.content == "用户身份：其他"
    assert fact.content == "用户身份：架构师"
    with pytest.raises(ValidationError):
        fact.content = "用户身份：篡改"  # type: ignore[misc]
