"""MVA-1 golden fixture + SSE projection contract (placeholder).

Full projection via ``ConsumerContract`` is MVA-4. This test only checks
that the minimal v2.0.0 envelope fixture parses and that
``expected_projection.json`` is well-formed.
"""

from __future__ import annotations

import json
from pathlib import Path

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "journal_v2_minimal"
FIXTURE = _FIXTURE_DIR / "run_001.jsonl"
EXPECTED = _FIXTURE_DIR / "expected_projection.json"

_ENVELOPE_FIELDS = (
    "schema_version",
    "event_id",
    "trace_id",
    "run_id",
    "run_seq",
    "plan_ref",
    "occurred_at",
    "descriptor",
    "payload",
    "scope",
    "causation",
    "evidence",
)


def test_golden_fixture_projects_to_expected() -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    frames = [json.loads(line) for line in lines if line.strip()]
    assert len(frames) == 5
    for frame in frames:
        assert frame["schema_version"] == "v2.0.0"
        for key in _ENVELOPE_FIELDS:
            assert key in frame
        assert isinstance(frame["event_id"], str)
        assert isinstance(frame["run_seq"], int)
        assert isinstance(frame["descriptor"], dict)
        assert isinstance(frame["payload"], dict)
        assert "type" in frame["descriptor"]
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert isinstance(expected, list)
    assert len(expected) == 4
    assert all(isinstance(entry, dict) and "kind" in entry for entry in expected)
