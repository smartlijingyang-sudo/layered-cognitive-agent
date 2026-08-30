"""Tests for scripts/quarterly_legacy_cleanup.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from quarterly_legacy_cleanup import (  # noqa: E402
    Entry,
    days_since_commit,
    parse_legacy,
)


def test_parse_legacy_returns_list():
    entries = parse_legacy()
    assert isinstance(entries, list)


def test_parse_legacy_skips_comments():
    """Comments and blank lines should be ignored."""
    entries = parse_legacy()
    for e in entries:
        assert not e.path.startswith("#")
        assert e.path  # non-empty


def test_entry_is_stable_with_old_days():
    e = Entry(path="x.py", note="", last_touched="abc123 2020-01-01", days_since=365)
    assert e.is_stable is True


def test_entry_is_not_stable_with_recent_days():
    e = Entry(path="x.py", note="", last_touched="abc123 2026-01-01", days_since=1)
    assert e.is_stable is False


def test_entry_is_not_stable_when_days_none():
    e = Entry(path="x.py", note="", last_touched=None, days_since=None)
    assert e.is_stable is False


def test_days_since_commit_parses_correctly():
    days = days_since_commit("abc123 2020-01-01 12:00:00 +0000")
    assert days is not None
    assert days > 2000  # way in the past


def test_days_since_commit_handles_garbage():
    assert days_since_commit("garbage") is None
    assert days_since_commit("") is None
