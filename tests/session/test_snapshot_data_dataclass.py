"""Regression: Session.append._snapshot_data converts Pydantic/dataclass values.

ContextManifest and other typed dataclasses cross the fact-plane boundary as
nested values inside a Mapping. The boundary, not the caller, owns the
Pydantic/dataclass -> JSON-safe primitive conversion.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from lca.contracts.models.core.perceive.perception import (
    ContextItem,
    ContextManifest,
)
from lca.session import Session


def test_snapshot_accepts_dataclass_value() -> None:
    session = Session("snapshot-dataclass")
    manifest = ContextManifest(
        items=(ContextItem(kind="clock", payload="2026-09-12", provenance="sensor.clock"),),
    )
    event = session.append("context.manifested.v1", {"manifest": manifest})
    assert event.data["manifest"]["items"][0]["kind"] == "clock"
    assert event.data["manifest"]["digest"] == ""


def test_snapshot_accepts_pydantic_value() -> None:
    class SensorReading(BaseModel):
        sensor: str
        value: float

    session = Session("snapshot-pydantic")
    reading = SensorReading(sensor="clock", value=12.5)
    event = session.append("sensor.reading.v1", {"reading": reading})
    assert event.data["reading"] == {"sensor": "clock", "value": 12.5}


def test_snapshot_accepts_nested_pydantic_in_dataclass() -> None:
    @dataclass(frozen=True)
    class Reading:
        sensor: str
        value: float

    session = Session("snapshot-nested")
    payload = {"outer": {"reading": Reading(sensor="clock", value=1.0)}}
    event = session.append("sensor.reading.v1", payload)
    assert event.data["outer"]["reading"] == {"sensor": "clock", "value": 1.0}


def test_snapshot_rejects_unknown_type() -> None:
    session = Session("snapshot-unknown")

    class NotConvertible:
        def __repr__(self) -> str:
            return "NotConvertible()"

    with pytest.raises(TypeError, match="无损 JSON"):
        session.append("sensor.reading.v1", {"value": NotConvertible()})


def test_snapshot_preserves_top_level_mapping_contract() -> None:
    session = Session("snapshot-shape")
    with pytest.raises(TypeError, match="Mapping"):
        session.append("sensor.reading.v1", "not-a-mapping")  # type: ignore[arg-type]
