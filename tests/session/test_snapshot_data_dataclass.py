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


def test_snapshot_rejects_oversized_payload() -> None:
    """Backpressure: single event payload exceeding ``_MAX_SNAPSHOT_BYTES`` fails loud.

    Regression for the 2026-09-16 stall postmortem: an emit that grew with
    log size would synchronously monopolise the asyncio loop for seconds.
    The hard cap turns that into an immediate ``TypeError`` so the
    observation path stays cheap and the run keeps making progress.
    """
    from lca.session.append import _MAX_SNAPSHOT_BYTES

    session = Session("snapshot-oversized")
    # Build a payload comfortably larger than the cap regardless of platform.
    target = _MAX_SNAPSHOT_BYTES + 1024
    big = "x" * target
    with pytest.raises(TypeError, match="_MAX_SNAPSHOT_BYTES"):
        session.append("huge.blob.v1", {"blob": big})
    # Log must remain untouched on failure (Session invariant).
    assert session.seq == 0


def test_snapshot_rejects_nan_payload() -> None:
    """NaN/Infinity are not JSON-safe and must be rejected pre-snapshot."""
    import math

    session = Session("snapshot-nan")
    with pytest.raises(TypeError, match="非 JSON 数值"):
        session.append("sensor.reading.v1", {"value": math.nan})
    with pytest.raises(TypeError, match="非 JSON 数值"):
        session.append("sensor.reading.v1", {"value": math.inf})


def test_snapshot_breaks_aliases_at_boundary() -> None:
    """Snapshot decouples from caller aliases: caller mutates neither alias nor target.

    The boundary (``_to_jsonable``) already lifts shared references into
    distinct dict copies, and ``copy.deepcopy`` keeps that isolation. After
    ``append``, neither mutating the original alias nor a post-hoc mutation
    of one snapshot alias leaks into the other snapshot branch.
    """
    session = Session("snapshot-aliased")
    inner = {"k": "v"}
    event = session.append("ref.aliased.v1", {"a": inner, "b": inner})
    inner["k"] = "MUTATED"
    assert event.data["a"]["k"] == "v"
    assert event.data["b"]["k"] == "v"
    event.data["a"]["k"] = "POST_MUTATED"
    assert event.data["b"]["k"] == "v"


def test_snapshot_is_decoupled_from_caller_mutation() -> None:
    """Returned snapshot must not track later mutations of the caller's input."""
    session = Session("snapshot-decouple")
    payload = {"value": [1, 2, 3]}
    event = session.append("mut.after.append.v1", payload)
    payload["value"].append(999)
    assert event.data["value"] == [1, 2, 3]


def test_snapshot_fast_path_on_realistic_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Micro-regression: ~1 MiB realistic payload snapshots in well under 100 ms.

    Locks in the asymptotic improvement from ``json.dumps + json.loads`` to
    ``copy.deepcopy + lightweight validation``, plus the hard size cap that
    keeps the asyncio loop from being monopolised by single oversized emits.
    """
    import time

    from lca.session import append as _append_mod

    monkeypatch.setattr(_append_mod, "_MAX_SNAPSHOT_BYTES", 32 * 1024 * 1024)
    session = Session("snapshot-perf")
    payload = {
        "graph_state": {
            f"node_{i}": {"attrs": {f"k_{j}": f"value_{i}_{j}" for j in range(30)}}
            for i in range(900)
        }
    }
    started = time.perf_counter()
    event = session.append("graph.snapshot.v1", payload)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 100, f"snapshot too slow: {elapsed_ms:.1f} ms"
    assert len(event.data["graph_state"]) == 900


def test_snapshot_fast_path_microbenchmark_5mib(monkeypatch: pytest.MonkeyPatch) -> None:
    """5 MiB realistic payload snapshots in well under 250 ms.

    Complements ``test_snapshot_fast_path_on_realistic_payload`` at a
    larger scale. The 8 MiB default cap lets us lift it to 16 MiB for
    this benchmark via monkeypatch (auto-restored).
    """
    import time

    from lca.session import append as _append_mod

    monkeypatch.setattr(_append_mod, "_MAX_SNAPSHOT_BYTES", 16 * 1024 * 1024)
    session = Session("snapshot-perf-5mib")
    payload = {
        "graph_state": {
            f"node_{i}": {"attrs": {f"k_{j}": f"value_{i}_{j}" for j in range(50)}}
            for i in range(2500)
        }
    }
    started = time.perf_counter()
    event = session.append("graph.snapshot.v1", payload)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 250, f"snapshot too slow on 5 MiB: {elapsed_ms:.1f} ms"
    assert len(event.data["graph_state"]) == 2500
