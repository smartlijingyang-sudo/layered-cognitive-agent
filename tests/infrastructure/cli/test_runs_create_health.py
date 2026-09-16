"""``post_create_report`` rewrite tests for ``lca-ops runs create`` (PR-1 / Task 1.5).

Per spec
``docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md``
§2.4 (post_create_report rewrite) + §15 G-1..G-5 (live-SOP garbage
inventory): the eight scattered SOP fields (``events_streamed``,
``new_exceptions_streamed``, ``tail_cap_s``, ``exceptions``) are
replaced by ``health: RunHealthReport.model_dump(mode="json")`` and
``health_summary: {overall, by_type}``.

The 7 cases below pin the new shape and prove the 5 garbage items
are deleted. Tests are written BEFORE the rewrite (TDD red); the
green phase ships the rewrite + deletions.

Pre-existing ``tests/infrastructure/cli/test_runs_create_facade_path.py``
covers the CLI facade path and stays green through the rewrite (no
SOP code path touched there). 12 tests in that file should remain
green after the green-phase rewrite.

Note: in the RED phase the existing ``_build_post_create_report``
calls ``_live_sop_run`` which tails spine/sidecar files forever.
Tests that exercise the rewrite's new field shape write a spine
with a ``kernel.run.stop`` event AND patch the trace root so the
function can find it; the live-SOP tail loop exits on seeing
``kernel.run.stop`` (no hang). The shape-presence tests below
additionally pre-stub ``_live_sop_run`` (when it exists) to keep
the red-phase test fast.
"""

from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


_RUNS_MODULE = "lca.infrastructure.cli.commands.runs.runs"


# ── helpers ─────────────────────────────────────────────────────────


def _runs_module():
    """Import the runs CLI module (cached after first import)."""
    return importlib.import_module(_RUNS_MODULE)


def _write_spine(tmp_path: Path, run_id: str, outcome: str = "success") -> Path:
    """Write a minimal spine with ``kernel.run.stop`` so the live-SOP
    tail loop (pre-rewrite) exits cleanly with the outcome."""
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        json.dumps(
            {
                "event_id": f"{run_id}:1",
                "ts": "2026-09-16T02:00:00+00:00",
                "run_id": run_id,
                "execution_point": "kernel.run.stop",
                "payload": {"outcome": outcome},
            }
        )
        + "\n"
    )
    # The sidecar is empty in these tests; the live-SOP loop tolerates
    # a missing file (returns empty bytes).
    return spine_path


# ── post_create_report shape (3 cases) ─────────────────────────────


def test_post_create_report_has_health_field() -> None:
    """``_build_post_create_report(run_id, base_url)`` returns a dict
    whose ``health`` value round-trips through ``RunHealthReport``.

    Per spec §2.4: ``health: RunHealthReport.model_dump(mode="json")``.
    The test pins the field presence; the green-state implementation
    must wire the fold call into the report builder.
    """
    from lca.contracts.observability.health.report import RunHealthReport

    runs = _runs_module()

    # Stub the deleted/legacy live-SOP loop in the RED phase so the
    # function returns quickly without spinning on tail.
    no_op = patch.object(
        runs, "_live_sop_run", return_value=(0, "success", 0), create=True
    )
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        run_id = "run_x"
        _write_spine(td_path, run_id)
        with patch.object(runs, "_DEFAULT_TRACES_ROOT", td_path), no_op:
            report = runs._build_post_create_report(run_id, "http://x")

    assert "health" in report, f"expected 'health' key, got {list(report.keys())}"
    parsed = RunHealthReport.model_validate(report["health"])
    assert parsed.schema_version == "1.0"
    assert parsed.run_id == run_id


def test_post_create_report_has_health_summary() -> None:
    """``health_summary.overall`` is one of the 4 closed statuses;
    ``health_summary.by_type`` is a dict."""
    from lca.contracts.observability.health.condition import RunHealthStatus

    runs = _runs_module()
    no_op = patch.object(
        runs, "_live_sop_run", return_value=(0, "success", 0), create=True
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        run_id = "run_y"
        _write_spine(td_path, run_id)
        with patch.object(runs, "_DEFAULT_TRACES_ROOT", td_path), no_op:
            report = runs._build_post_create_report(run_id, "http://x")

    assert "health_summary" in report, (
        f"expected 'health_summary' key, got {list(report.keys())}"
    )
    summary = report["health_summary"]
    assert isinstance(summary, dict)
    assert "overall" in summary
    assert "by_type" in summary
    allowed = set(RunHealthStatus.__args__)  # type: ignore[attr-defined]
    assert summary["overall"] in allowed
    assert isinstance(summary["by_type"], dict)


def test_post_create_report_no_longer_references_ep_formatting() -> None:
    """The rewritten report does NOT carry ``events_streamed``,
    ``new_exceptions_streamed``, or ``tail_cap_s``.

    Per spec §15 G-1..G-5: these are deleted in the same PR; no
    COMPAT shim, no half-deletion. We pin the deletions by
    asserting the keys are absent.
    """
    runs = _runs_module()
    no_op = patch.object(
        runs, "_live_sop_run", return_value=(0, "success", 0), create=True
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        run_id = "run_z"
        _write_spine(td_path, run_id)
        with patch.object(runs, "_DEFAULT_TRACES_ROOT", td_path), no_op:
            report = runs._build_post_create_report(run_id, "http://x")

    for forbidden in ("events_streamed", "new_exceptions_streamed", "tail_cap_s"):
        assert forbidden not in report, (
            f"deleted key {forbidden!r} still present in report: {list(report.keys())}"
        )


# ── live-SOP garbage deleted (4 cases) ────────────────────────────


def test_live_sop_run_function_removed() -> None:
    """``_live_sop_run`` is deleted from the module (spec §15 G-3).

    We check via ``hasattr`` on the module dict — if the symbol
    exists, the rewrite did not delete it.
    """
    runs = _runs_module()
    assert not hasattr(runs, "_live_sop_run"), (
        "_live_sop_run should be deleted per spec §15 G-3"
    )


def test_format_spine_event_function_removed() -> None:
    """``_format_spine_event`` is deleted from the module (spec §15 G-4)."""
    runs = _runs_module()
    assert not hasattr(runs, "_format_spine_event"), (
        "_format_spine_event should be deleted per spec §15 G-4"
    )


def test_live_sop_ep_prefixes_constant_removed() -> None:
    """``_LIVE_SOP_EP_PREFIXES`` is deleted from the module (spec §15 G-1)."""
    runs = _runs_module()
    assert not hasattr(runs, "_LIVE_SOP_EP_PREFIXES"), (
        "_LIVE_SOP_EP_PREFIXES should be deleted per spec §15 G-1"
    )


def test_live_sop_ep_suppress_constant_removed() -> None:
    """``_LIVE_SOP_EP_SUPPRESS`` is deleted from the module (spec §15 G-2)."""
    runs = _runs_module()
    assert not hasattr(runs, "_LIVE_SOP_EP_SUPPRESS"), (
        "_LIVE_SOP_EP_SUPPRESS should be deleted per spec §15 G-2"
    )