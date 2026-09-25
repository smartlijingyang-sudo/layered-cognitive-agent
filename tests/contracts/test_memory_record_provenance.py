"""ADR-0249: every episode fact carries a non-empty source trace."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.memory.episode import EpisodeFact, ResidualClass


def _fact(**overrides: object) -> EpisodeFact:
    payload: dict[str, object] = {
        "fact_id": "ep_prov",
        "dedupe_key": "fact:execution_error",
        "category": MemoryCategory.FACT,
        "content": "Error",
        "residual": ResidualClass.error,
        "explicit_user_authority": False,
        "source_trace_id": "t1",
        "observed_at_ms": 0,
    }
    payload.update(overrides)
    return EpisodeFact(**payload)  # type: ignore[arg-type]


def test_empty_source_trace_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _fact(source_trace_id="")


def test_source_trace_id_round_trips() -> None:
    fact = _fact(source_trace_id="t1")
    restored = EpisodeFact.model_validate(fact.model_dump())
    assert restored.source_trace_id == "t1"
