"""Unit tests for the post-restart SOP report.

The report lives at
``lca.infrastructure.cli.services.kernel.restart_report`` and is run by
``lca-ops kernel-restart`` after the supervisor declares the kernel
ready. Three phases must produce the right verdicts:

1. ``boot_check`` re-runs profile resolve + plan lift.
2. ``fiber_report`` counts ``boot.pending_event`` rows in the kernel
   stdout file, scoped to the boot whose PID the supervisor spawned.
3. ``health_probe`` GETs ``/health`` and verifies the plugin registry.

The tests stub the IO seams (``resolve_profile`` / ``validate_profile_plans``
/ the stdout file / the HTTP server) so they are hermetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lca.infrastructure.cli.services.kernel import restart_report

if TYPE_CHECKING:
    import pytest as _pytest


@pytest.fixture
def fake_stdout(monkeypatch: _pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the fiber report at a controlled stdout log file."""
    stdout = tmp_path / "lca-kernel.stdout.log"
    monkeypatch.setattr(restart_report, "_STDOUT_LOGFILE", str(stdout))
    return stdout


@pytest.fixture
def fake_stderr(monkeypatch: _pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the stderr-anchor lookup at a controlled stderr file."""
    stderr = tmp_path / "lca-kernel.stderr.log"
    monkeypatch.setattr(restart_report, "_STDERR_LOGFILE", str(stderr))
    return stderr


def _write_fake_stdout(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_fake_stderr(path: Path, pids: list[int]) -> None:
    path.write_text(
        "\n".join(
            f"INFO:     Started server process [{pid}]" for pid in pids
        )
        + "\n",
        encoding="utf-8",
    )


def _boot_event(
    plugin_id: str,
    *,
    layer: str = "L0",
    status: str = "ok",
    duration_ms: float = 0.5,
) -> str:
    """One boot.pending_event line in the format the kernel writes."""
    return (
        f"2026-09-16 12:00:00 [info     ] boot.pending_event             "
        f"duration_ms={duration_ms} event_type=BootPluginFiberSpawned "
        f"kind=provider layer={layer} plugin_id={plugin_id} status={status}"
    )


def test_boot_check_passes_when_validators_pass(
    monkeypatch: _pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "lca.harness.profile.resolve.resolve.resolve_profile",
        lambda _p: object(),
    )
    monkeypatch.setattr(
        "lca_kernel.boot.plan_validation.validate_profile_plans",
        lambda _r: None,
    )

    findings: list[restart_report.Finding] = []
    result = restart_report._run_boot_check(Path("profiles/web-standard.yaml"), findings)

    assert result.ok is True
    assert [c["name"] for c in result.summary["checks"]] == ["resolve", "plan_lift"]
    assert all(c["ok"] for c in result.summary["checks"])
    assert any(f.severity == "info" for f in findings)


def test_boot_check_fails_when_profile_does_not_resolve(
    monkeypatch: _pytest.MonkeyPatch,
) -> None:
    def _raise(_p: object) -> None:
        raise RuntimeError("bad yaml")

    monkeypatch.setattr(
        "lca.harness.profile.resolve.resolve.resolve_profile", _raise
    )

    findings: list[restart_report.Finding] = []
    result = restart_report._run_boot_check(Path("profiles/x.yaml"), findings)

    assert result.ok is False
    err = next(f for f in findings if f.severity == "error")
    assert err.code == "profile.resolve_failed"
    assert err.detail["reason"] == "bad yaml"


def test_fiber_report_counts_layers_and_flags_failures(
    monkeypatch: _pytest.MonkeyPatch, fake_stdout: Path, fake_stderr: Path,
) -> None:
    _write_fake_stdout(
        fake_stdout,
        [
            _boot_event("alpha", layer="L0"),
            _boot_event("beta", layer="L1"),
            _boot_event("gamma", layer="L1", status="failed"),
        ],
    )
    _write_fake_stderr(fake_stderr, [12345])

    findings: list[restart_report.Finding] = []
    result = restart_report._run_fiber_report(findings)

    assert result.summary["total"] == 3
    assert result.summary["fail"] == 1
    assert result.summary["by_layer"] == {"L0": 1, "L1": 2}
    assert result.ok is False
    err = next(f for f in findings if f.severity == "error")
    assert err.code == "fiber.failures"
    assert "1/3" in err.message


def test_fiber_report_reads_full_stdout_after_supervisor_truncate(
    monkeypatch: _pytest.MonkeyPatch, fake_stdout: Path, fake_stderr: Path,
) -> None:
    # The supervisor truncates its stdout log on every start() so the file
    # only contains events from the current boot — no PID-based slicing
    # needed. This test exercises that contract: even with a multi-PID
    # history and an unrelated stderr banner, the report reports the
    # entire stdout contents.
    _write_fake_stdout(
        fake_stdout,
        [_boot_event(f"plugin-{i}") for i in range(7)],
    )
    _write_fake_stderr(fake_stderr, [11111, 22222])

    findings: list[restart_report.Finding] = []
    result = restart_report._run_fiber_report(findings)

    assert result.ok is True
    assert result.summary["total"] == 7
    assert "anchor_pid" not in result.summary


def test_health_probe_ok(monkeypatch: _pytest.MonkeyPatch) -> None:
    body = json.dumps(
        {
            "status": "ok",
            "plugin": {
                "registered": 4,
                "expected": 4,
                "missing": [],
                "fiber_count": 258,
            },
        }
    ).encode("utf-8")

    class _FakeResp:
        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *_exc: object) -> None:
            pass

        def read(self) -> bytes:
            return body

    monkeypatch.setattr(
        restart_report.urllib.request, "urlopen", lambda *_a, **_k: _FakeResp()
    )
    findings: list[restart_report.Finding] = []
    result = restart_report._run_health_probe("127.0.0.1", 8765, findings)

    assert result.ok is True
    assert result.summary["plugin_registered"] == 4
    info = next(f for f in findings if f.code == "health.ok")
    assert "plugin 4/4" in info.message


def test_health_probe_flags_missing_plugins(
    monkeypatch: _pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {
            "status": "ok",
            "plugin": {
                "registered": 2,
                "expected": 4,
                "missing": ["lca-foo", "lca-bar"],
                "fiber_count": 0,
            },
        }
    ).encode("utf-8")

    class _FakeResp:
        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *_exc: object) -> None:
            pass

        def read(self) -> bytes:
            return body

    monkeypatch.setattr(
        restart_report.urllib.request, "urlopen", lambda *_a, **_k: _FakeResp()
    )
    findings: list[restart_report.Finding] = []
    result = restart_report._run_health_probe("127.0.0.1", 8765, findings)

    assert result.ok is False
    err = next(f for f in findings if f.code == "health.unhealthy")
    assert "missing=['lca-foo', 'lca-bar']" in err.message


def test_run_restart_report_skips_phases_when_supervisor_not_running(
    monkeypatch: _pytest.MonkeyPatch,
) -> None:
    """Kernel never came up: only boot_check runs; fiber/health fail-loud."""
    monkeypatch.setattr(
        "lca.harness.profile.resolve.resolve.resolve_profile",
        lambda _p: object(),
    )
    monkeypatch.setattr(
        "lca_kernel.boot.plan_validation.validate_profile_plans",
        lambda _r: None,
    )

    report = restart_report.run_restart_report(
        profile=Path("profiles/web-standard.yaml"),
        host="127.0.0.1",
        port=8765,
        supervisor_state="starting",
        supervisor_last_event="spawned pid=42",
    )

    assert [p.phase for p in report.phases] == [
        "boot_check", "fiber_report", "health_probe"
    ]
    assert report.phases[0].ok is True
    assert report.phases[1].ok is False
    assert report.phases[2].ok is False
    assert report.ok is False
    assert any(f.code == "kernel.not_running" for f in report.findings)
    assert report.next_command and "kernel-supervisor logs" in report.next_command


def test_render_text_includes_three_phases_and_finding_codes() -> None:
    """Text form lists one line per phase + every error / warning finding."""
    findings = [
        restart_report.Finding(
            phase="boot_check", severity="info",
            code="profile.validated", message="profile validated",
        ),
        restart_report.Finding(
            phase="fiber_report", severity="error",
            code="fiber.failures",
            message="1/3 plugin fibers failed",
        ),
        restart_report.Finding(
            phase="health_probe", severity="info",
            code="health.ok",
            message="/health ok (plugin 4/4, fiber_count=258)",
        ),
    ]
    phases = [
        restart_report.PhaseResult(
            phase="boot_check", ok=True, duration_ms=10, findings=[findings[0]],
        ),
        restart_report.PhaseResult(
            phase="fiber_report", ok=False, duration_ms=20,
            findings=[findings[1]],
        ),
        restart_report.PhaseResult(
            phase="health_probe", ok=True, duration_ms=5,
            findings=[findings[2]],
        ),
    ]
    report = restart_report.RestartReport(
        ok=False,
        profile="profiles/web-standard.yaml",
        phases=phases,
        findings=findings,
        duration_ms=35,
        supervisor_state="running",
        supervisor_last_event="readiness probe passed",
        next_command=None,
    )

    text = restart_report.render_text(report)
    assert "verdict=FAILED" in text
    for phase in ("boot_check", "fiber_report", "health_probe"):
        assert phase in text
    assert "fiber.failures" in text
