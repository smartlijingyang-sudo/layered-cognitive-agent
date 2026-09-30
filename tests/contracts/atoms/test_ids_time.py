"""Tests for the shared UTC time helpers in ``lca.contracts.atoms.ids``.

These helpers are the single seam for wall-clock timestamps across memory
persistence, retrieval scoring, and assistant-home manifests; every module must
use them instead of redefining local ``_utc_now_*`` variants.
"""

from __future__ import annotations

from datetime import datetime

from lca.contracts.atoms.ids.ids import utc_now, utc_now_iso, utc_now_ms


def test_utc_now_is_timezone_aware() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() is not None


def test_utc_now_ms_is_positive_and_grows() -> None:
    a = utc_now_ms()
    b = utc_now_ms()
    assert a > 0
    assert b >= a


def test_utc_now_ms_matches_datetime_epoch() -> None:
    import time

    before = int(time.time() * 1000)
    value = utc_now_ms()
    after = int(time.time() * 1000)
    assert before <= value <= after


def test_utc_now_iso_format() -> None:
    iso = utc_now_iso()
    # Expected shape: YYYY-MM-DDTHH:MM:SSZ
    assert len(iso) == 20
    assert iso.endswith("Z")
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_utc_now_iso_roundtrips_through_datetime() -> None:
    iso = utc_now_iso()
    # The value must parse as a valid UTC wall-clock time.
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    assert parsed.year >= 2024
