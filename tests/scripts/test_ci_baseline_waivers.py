"""Tests for narrowly-scoped, expiring CI baseline waivers."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from ci_baseline_waivers import BaselineWaiverError, check_waiver, load_waivers  # noqa: E402


def _manifest(tmp_path: Path, *, expires: str = "2026-11-07") -> tuple[Path, str]:
    output = "known package-organization baseline\n"
    manifest = {
        "version": 1,
        "waivers": {
            "package-size": {
                "owner": "smartlijingyang-sudo",
                "expires": expires,
                "reason": "Refactor the existing oversized packages.",
                "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            }
        },
    }
    path = tmp_path / "waivers.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, output


def test_waiver_matches_only_the_exact_baseline_output(tmp_path: Path) -> None:
    path, output = _manifest(tmp_path)
    waivers = load_waivers(path, today=date(2026, 10, 8))

    allowed, detail = check_waiver("package-size", output, waivers)
    assert allowed is True
    assert "smartlijingyang-sudo" in detail
    assert "2026-11-07" in detail

    allowed, detail = check_waiver("package-size", output + "new finding\n", waivers)
    assert allowed is False
    assert "output fingerprint changed" in detail


def test_expired_waiver_is_a_configuration_error(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path, expires="2026-10-07")

    with pytest.raises(BaselineWaiverError, match="expired"):
        load_waivers(path, today=date(2026, 10, 8))


def test_missing_gate_waiver_does_not_suppress_failure(tmp_path: Path) -> None:
    path, output = _manifest(tmp_path)
    waivers = load_waivers(path, today=date(2026, 10, 8))

    allowed, detail = check_waiver("typed-port-graph", output, waivers)
    assert allowed is False
    assert "no waiver registered" in detail
