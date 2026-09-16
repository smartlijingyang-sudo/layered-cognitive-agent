"""Tests for ADR-0231 RegionPrefix enum — region SSOT = `lca/nodes/<region>/` directory name.

``RegionPrefix`` is a typed view of the ``lca/nodes/`` top-level directories.
It parses region strings, rejects unknown / colon-prefixed regions, and exposes
the canonical value set so plugin shape + bundle shape validators can compare
strings against the SSOT.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.region_prefix import (
    RegionPrefix,
    UnknownRegionPrefixError,
    collect_region_prefixes,
)


# Region set observed at 2026-09-16 — the canonical value set is whatever
# directories exist under ``lca/nodes/``. If you add a new region directory,
# this test auto-picks it up because collect_region_prefixes walks the FS.
_EXPECTED_REGIONS = frozenset(
    {
        "act",
        "concept",
        "delegate",
        "intervene",
        "loop",
        "perceive",
        "plan",
        "reflect",
        "remember",
        "stop",
        "think",
    }
)


class TestRegionPrefixValues:
    """``collect_region_prefixes`` returns the live SSOT — `lca/nodes/` dirs."""

    def test_collect_returns_only_known_directories(self):
        values = collect_region_prefixes()
        assert isinstance(values, frozenset)
        # Every collected value must be a non-empty identifier (no colons, no slashes).
        for v in values:
            assert v and ":" not in v and "/" not in v, (
                f"collected region {v!r} contains disallowed characters"
            )

    def test_current_snapshot_matches_expected_regions(self):
        """Frozen snapshot of the 2026-09-16 region set.

        If you intentionally add / remove a region directory under
        ``lca/nodes/``, update this expected set and document the change
        in ADR-0231.
        """
        assert collect_region_prefixes() == _EXPECTED_REGIONS, (
            "lca/nodes/ region set drifted from the ADR-0231 snapshot"
        )


class TestRegionPrefixEnum:
    """RegionPrefix enum members mirror ``collect_region_prefixes``."""

    def test_enum_members_match_collected_set(self):
        # Every enum member value must be in the FS-collected set,
        # and the FS-collected set must contain every enum value.
        enum_values = frozenset(m.value for m in RegionPrefix)
        collected = collect_region_prefixes()
        assert enum_values == collected, (
            f"enum drift: enum={enum_values - collected}, fs={collected - enum_values}"
        )

    def test_str_compare_succeeds(self):
        """str Enum semantics — ``RegionPrefix.THINK == "think"`` is True."""
        assert RegionPrefix("think") == "think"


class TestRegionPrefixParse:
    """``RegionPrefix.parse(raw)`` enforces the SSOT strictly."""

    def test_parse_known_region(self):
        assert RegionPrefix.parse("think") is RegionPrefix.THINK
        assert RegionPrefix.parse("act") is RegionPrefix.ACT
        assert RegionPrefix.parse("intervene") is RegionPrefix.INTERVENE

    def test_parse_unknown_raises(self):
        with pytest.raises(UnknownRegionPrefixError) as excinfo:
            RegionPrefix.parse("not-a-region")
        assert "not-a-region" in str(excinfo.value)

    def test_parse_colon_prefixed_raises(self):
        """``phase:think`` / ``region:intervene`` style strings are rejected."""
        with pytest.raises(UnknownRegionPrefixError):
            RegionPrefix.parse("phase:think")
        with pytest.raises(UnknownRegionPrefixError):
            RegionPrefix.parse("region:intervene")

    def test_parse_empty_raises(self):
        with pytest.raises(UnknownRegionPrefixError):
            RegionPrefix.parse("")

    def test_parse_none_raises(self):
        with pytest.raises(UnknownRegionPrefixError):
            RegionPrefix.parse(None)  # type: ignore[arg-type]


class TestRegionPrefixContains:
    """``RegionPrefix.contains(raw)`` is a non-throwing lookup."""

    def test_contains_known(self):
        assert RegionPrefix.contains("think") is True
        assert RegionPrefix.contains("act") is True

    def test_contains_unknown(self):
        assert RegionPrefix.contains("phase:think") is False
        assert RegionPrefix.contains("not-a-region") is False
        assert RegionPrefix.contains("") is False
        assert RegionPrefix.contains(None) is False  # type: ignore[arg-type]
