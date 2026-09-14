"""Regression + behavior tests for ``lca-ops kernel plugins`` and ``kernel boot-log``.

Both commands exist so agents / operators do not have to ``grep`` boot
stderr or hand-parse ``kernel_compose --json`` to answer "what loaded".
They project the same resolved-profile SSOT that boot wired into
``BootPluginFiberSpawned`` and ``CompiledRunPlan.plugin_specs``.

Each command has two tests:
- a default human-readable form (column-aligned, grouped by layer);
- a ``--json`` form that emits the full structured payload.

The ``boot-log`` command reads the kernel's stderr file written by
``KernelServeSpawner``. To keep the test hermetic we point the reader
at a fixed ``--stderr`` path under ``tmp_path`` rather than the
latest live kernel; the reader ignores other ``lca-kernel.stderr.*``
files when an explicit path is supplied.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.infrastructure.cli.cli.cli import app

PROFILE = Path("profiles/web-standard.yaml")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ── kernel plugins ────────────────────────────────────────────────────


def test_kernel_plugins_lists_all_enabled(runner: CliRunner) -> None:
    """Default form prints every enabled plugin grouped by layer."""
    result = runner.invoke(app, ["kernel_plugins", "-p", str(PROFILE)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "L0 (62)" in result.stdout, result.stdout
    assert "L1 (82)" in result.stdout, result.stdout
    assert "L2 (68)" in result.stdout, result.stdout
    # Sample plugin ids from each layer appear under their group.
    assert "lca-decision-classifier-seam" in result.stdout
    assert "events.subscriber.exception_index_writer" in result.stdout


def test_kernel_plugins_json_matches_compile(runner: CliRunner) -> None:
    """``--json`` form is the same plugin_specs projection as ``kernel_compose --json``."""
    compose_result = runner.invoke(
        app, ["kernel_compose", str(PROFILE), "--json"], catch_exceptions=False
    )
    plugins_result = runner.invoke(app, ["kernel_plugins", "-p", str(PROFILE), "--json"])
    assert plugins_result.exit_code == 0, plugins_result.stdout + plugins_result.stderr

    compose_payload = json.loads(compose_result.stdout)
    plugins_payload = json.loads(plugins_result.stdout)

    compose_ids = {spec["id"] for spec in compose_payload["plugin_specs"]}
    plugins_ids = {spec["id"] for spec in plugins_payload["plugins"]}
    assert compose_ids == plugins_ids
    assert len(plugins_payload["plugins"]) >= 240


def test_kernel_plugins_filters_by_id(runner: CliRunner) -> None:
    """``--id`` narrows the list to exactly one entry by plugin id."""
    result = runner.invoke(
        app,
        ["kernel_plugins", "-p", str(PROFILE), "--id", "lca-decision-classifier-seam"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    # Exactly one plugin id is present, and it is the requested one.
    assert "lca-decision-classifier-seam" in result.stdout
    assert "events.subscriber.exception_index_writer" not in result.stdout


def test_kernel_plugins_filters_by_layer(runner: CliRunner) -> None:
    """``--layer`` narrows the list to plugins in the requested layers."""
    result = runner.invoke(
        app,
        ["kernel_plugins", "-p", str(PROFILE), "--layer", "L0", "--json"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["plugins"], payload
    assert all(spec["layer"] == "L0" for spec in payload["plugins"])


# ── kernel boot-log ───────────────────────────────────────────────────


def _write_fake_stderr(path: Path) -> None:
    """Drop a deterministic boot stderr file the reader can parse."""
    path.write_text(
        "\n".join(
            [
                "2026-09-14 20:00:00 [info     ] boot.profile_resolved          "
                "duration_ms=767.0 plugin_count=3 profile_path=",
                "2026-09-14 20:00:00 [info     ] boot.observability_assembled   "
                "bound_seams=('journal', 'policy') evidence_store_kind=FilesystemEvidenceStore",
                "2026-09-14 20:00:00 [info     ] boot.pending_event             "
                "duration_ms=2.5 event_type=BootPluginFiberSpawned "
                "kind=provider layer=L1 plugin_id=lca-decision-classifier-seam status=ok",
                "2026-09-14 20:00:00 [info     ] boot.pending_event             "
                "duration_ms=1.1 event_type=BootPluginFiberSpawned "
                "kind=provider layer=L1 plugin_id=lca-factory-seams-default status=ok",
                "2026-09-14 20:00:00 [info     ] boot.pending_event             "
                "duration_ms=0.4 event_type=BootPluginFiberSpawned "
                "kind=provider layer=L0 plugin_id=lca-tools-service status=ok",
                "INFO:     Uvicorn running on http://0.0.0.0:8765",
            ]
        )
    )


def test_kernel_boot_log_parses_fake_stderr(runner: CliRunner, tmp_path: Path) -> None:
    """``boot-log --stderr <file>`` reports three plugins, two layers."""
    fake = tmp_path / "lca-kernel.stderr.12345.20260914000000.log"
    _write_fake_stderr(fake)
    result = runner.invoke(app, ["kernel_boot_log", "--stderr", str(fake), "--json"])
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["plugin_count"] == 3, payload
    ids = [entry["plugin_id"] for entry in payload["entries"]]
    assert ids == [
        "lca-decision-classifier-seam",
        "lca-factory-seams-default",
        "lca-tools-service",
    ]
    assert payload["entries"][0]["layer"] == "L1"
    assert payload["entries"][2]["duration_ms"] == 0.4


def test_kernel_boot_log_filters_failed_only(runner: CliRunner, tmp_path: Path) -> None:
    """``--failed-only`` keeps only entries whose ``status`` is not ``ok``."""
    fake = tmp_path / "lca-kernel.stderr.99.20260914000000.log"
    fake.write_text(
        "\n".join(
            [
                "2026-09-14 [info] boot.pending_event "
                "duration_ms=2.0 event_type=BootPluginFiberSpawned "
                "kind=provider layer=L1 plugin_id=alpha status=ok",
                "2026-09-14 [info] boot.pending_event "
                "duration_ms=3.0 event_type=BootPluginFiberSpawned "
                "kind=provider layer=L2 plugin_id=beta status=failed",
            ]
        )
    )
    result = runner.invoke(
        app, ["kernel_boot_log", "--stderr", str(fake), "--failed-only", "--json"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["plugin_count"] == 1
    assert payload["entries"][0]["plugin_id"] == "beta"
    assert payload["entries"][0]["status"] == "failed"
