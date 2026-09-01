"""lca-ops lobehub status must treat HTTP reachability as ground truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from lca.infrastructure.cli.config import KernelServeConfig, LobeHubConfig
from lca.infrastructure.cli.service import ServiceStatus
from lca.infrastructure.cli.services.lobehub import (
    LobeHubService,
    _parse_verify_output,
)
from lca.infrastructure.cli.state import StateStore


@dataclass(frozen=True, slots=True)
class _VerifySummaryStub:
    ok: int
    broken: int
    names: tuple[str, ...] = ()
    error: str = ""


@pytest.fixture
def lobehub_svc(tmp_path: Path) -> LobeHubService:
    root = tmp_path / "repo"
    ui_dir = root / "lobehub-ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "package.json").write_text('{"version": "2.2.13"}')
    (ui_dir / ".lca-patched").write_text("ok")
    deploy_dir = root / "deploy" / "lobehub" / "patches"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "sample.py").write_text("# patch\n")

    state_dir = tmp_path / "state"
    svc = LobeHubService(
        LobeHubConfig(dir="lobehub-ui", dev_port=3010),
        KernelServeConfig(port=8765),
        state_dir,
        root,
    )
    StateStore(state_dir).save_snapshot("patches", [root / "deploy" / "lobehub"], "*")
    return svc


def test_status_running_when_dev_up_but_stored_pid_stale(lobehub_svc: LobeHubService) -> None:
    """next-server may outlive the bun parent recorded in the pid file."""
    lobehub_svc._state.write_pid("lobehub", 999_999)

    with (
        patch("lca.infrastructure.cli.services.lobehub.http_ready", return_value=True),
        patch("lca.infrastructure.cli.services.lobehub.pid_on_port", return_value=42_001),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_alive",
            side_effect=lambda pid: pid in {42_001, 42_002},
        ),
    ):
        state = lobehub_svc.state()

    assert state.status == ServiceStatus.RUNNING
    assert state.is_running
    assert not state.next_action
    assert lobehub_svc._state.read_pid("lobehub") == 42_001


def test_status_stopped_when_dev_down_and_pid_stale(lobehub_svc: LobeHubService) -> None:
    lobehub_svc._state.write_pid("lobehub", 999_999)

    with (
        patch("lca.infrastructure.cli.services.lobehub.http_ready", return_value=False),
        patch("lca.infrastructure.cli.services.lobehub.pid_on_port", return_value=None),
        patch("lca.infrastructure.cli.services.lobehub.pid_alive", return_value=False),
    ):
        state = lobehub_svc.state()

    assert state.status == ServiceStatus.STOPPED
    assert state.next_action == "./scripts/lca-ops lobehub start"


def _port_pid(next_pid: int | None, spa_pid: int | None = None):
    def _lookup(port: int) -> int | None:
        if port == 3010:
            return next_pid
        if port == 9876:
            return spa_pid
        return None

    return _lookup


def test_start_spawns_next_and_spa_not_coupled_dev(lobehub_svc: LobeHubService) -> None:
    spawned: list[list[str]] = []

    class _Proc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def _popen(cmd: object, **_kwargs: object) -> _Proc:
        spawned.append(list(cmd))  # type: ignore[arg-type]
        return _Proc(100 + len(spawned))

    hits = {"n": 0}

    def _ready(*_a: object, **_k: object) -> bool:
        hits["n"] += 1
        return hits["n"] > 1

    with (
        patch.object(lobehub_svc, "ensure_ready", return_value=False),
        patch("lca.infrastructure.cli.services.lobehub.subprocess.Popen", side_effect=_popen),
        # state() now calls patch verify; suppress it for this SPA-spawn path.
        patch(
            "lca.infrastructure.cli.services.lobehub.subprocess.run",
            return_value=type("_R", (), {"stdout": "", "stderr": "", "returncode": 0})(),
        ),
        patch("lca.infrastructure.cli.services.lobehub.http_ready", side_effect=_ready),
        patch("lca.infrastructure.cli.services.lobehub.time.sleep"),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_on_port", side_effect=_port_pid(None, None)
        ),
    ):
        state = lobehub_svc.start()

    assert state.status == ServiceStatus.RUNNING
    scripts = list(spawned)
    assert ["bun", "run", "dev"] not in scripts
    assert ["bun", "run", "dev:next"] in scripts
    assert ["bun", "run", "dev:spa"] in scripts
    assert lobehub_svc._state.read_pid("lobehub") == 101
    assert lobehub_svc._state.read_pid("lobehub-spa") == 102


def test_next_up_spa_down_is_degraded_not_stopped(lobehub_svc: LobeHubService) -> None:
    lobehub_svc._state.write_pid("lobehub", 42_001)

    with (
        patch("lca.infrastructure.cli.services.lobehub.http_ready", return_value=True),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_on_port",
            side_effect=_port_pid(42_001, None),
        ),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_alive",
            side_effect=lambda pid: pid in {42_001, 42_002},
        ),
    ):
        state = lobehub_svc.state()

    assert state.status == ServiceStatus.DEGRADED
    assert state.pid == 42_001
    assert any(c.name == "spa" and not c.ok for c in state.checks)
    assert state.next_action == "./scripts/lca-ops lobehub heal"


def test_heal_spa_only_does_not_respawn_next(lobehub_svc: LobeHubService) -> None:
    lobehub_svc._state.write_pid("lobehub", 42_001)
    spawned: list[list[str]] = []

    class _Proc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def _popen(cmd: object, **_kwargs: object) -> _Proc:
        spawned.append(list(cmd))  # type: ignore[arg-type]
        return _Proc(77)

    with (
        patch.object(lobehub_svc, "ensure_ready", return_value=False),
        patch.object(lobehub_svc, "stop") as stop,
        patch("lca.infrastructure.cli.services.lobehub.subprocess.Popen", side_effect=_popen),
        # state() now calls patch verify; suppress it for this SPA-spawn path.
        patch(
            "lca.infrastructure.cli.services.lobehub.subprocess.run",
            return_value=type("_R", (), {"stdout": "", "stderr": "", "returncode": 0})(),
        ),
        patch("lca.infrastructure.cli.services.lobehub.http_ready", return_value=True),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_on_port",
            side_effect=_port_pid(42_001, None),
        ),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_alive",
            side_effect=lambda pid: pid in {42_001, 77},
        ),
    ):
        state = lobehub_svc.heal()

    stop.assert_not_called()
    assert spawned == [["bun", "run", "dev:spa"]]
    assert lobehub_svc._state.read_pid("lobehub") == 42_001
    assert lobehub_svc._state.read_pid("lobehub-spa") == 77
    assert state.status == ServiceStatus.DEGRADED or state.pid == 42_001


# ── verify parser + cache (new — status reflects reality, not file count) ─


def test_parse_verify_output_counts_ok_and_broken() -> None:
    """Parser must read the real ``[verify]`` summary, not file counts."""
    stdout = (
        "[patch] OK                 dev_auth_files\n"
        "[patch] OK                 dev_auth_vite\n"
        "[patch] BROKEN             middleware_mock_user\n"
        "[patch] MISS               file_proxy_rewrite\n"
        "[patch] SKIP               topic_route_test\n"
        "[verify] 2 ok, 2 broken/missing\n"
    )
    summary = _parse_verify_output(stdout)
    assert summary.ok == 2
    assert summary.broken == 2
    assert summary.names == ("middleware_mock_user", "file_proxy_rewrite")
    assert summary.error == ""


def test_parse_verify_output_handles_missing_summary_line() -> None:
    """Older engine versions may not emit the summary line."""
    stdout = "[patch] OK                 dev_auth_files\n[patch] OK                 dev_auth_vite\n"
    summary = _parse_verify_output(stdout)
    assert summary.ok == 2
    assert summary.broken == 0
    assert summary.names == ()


def test_parse_verify_output_empty_when_no_patches() -> None:
    assert _parse_verify_output("") == _parse_verify_output("\n")


def test_run_patch_verify_uses_subprocess_and_caches(tmp_path: Path) -> None:
    """status() must not fork a verify subprocess on every call."""
    root = tmp_path / "repo"
    deploy = root / "deploy" / "lobehub"
    deploy.mkdir(parents=True)
    (deploy / "patch_lobehub.py").write_text("#!/usr/bin/env python3\nprint('fake')\n")
    ui_dir = root / "lobehub-ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "package.json").write_text('{"version": "2.2.13"}')

    svc = LobeHubService(
        LobeHubConfig(dir="lobehub-ui", dev_port=3010),
        KernelServeConfig(port=8765),
        tmp_path / "state",
        root,
    )

    calls = {"n": 0}

    class _FakeProc:
        stdout = "[verify] 5 ok, 0 broken/missing\n"
        stderr = ""

        def __init__(self) -> None:
            calls["n"] += 1

    with patch(
        "lca.infrastructure.cli.services.lobehub.subprocess.run",
        return_value=_FakeProc(),
    ):
        first = svc._run_patch_verify()
        second = svc._run_patch_verify()
        third = svc._run_patch_verify()

    assert calls["n"] == 1, "subprocess.run should fire exactly once (30s cache)"
    assert first.ok == 5 and first.broken == 0
    assert second is first
    assert third is first


def test_status_patches_field_reports_verify_count_not_file_count(
    lobehub_svc: LobeHubService,
) -> None:
    """status must not lie by counting ``deploy/lobehub/patches/**/*.py``."""
    lobehub_svc._run_patch_verify = lambda: _VerifySummaryStub(  # type: ignore[attr-defined]
        ok=18, broken=0, names=()
    )

    with (
        patch("lca.infrastructure.cli.services.lobehub.http_ready", return_value=True),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_on_port",
            side_effect=_port_pid(42_001, 42_002),
        ),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_alive",
            side_effect=lambda pid: pid in {42_001, 42_002},
        ),
    ):
        state = lobehub_svc.state()

    patches_check = next(c for c in state.checks if c.name == "patches")
    assert patches_check.ok
    assert patches_check.detail == "18/18 verified"
    assert not state.next_action


def test_status_patches_broken_suggests_patch_engine_directly(
    lobehub_svc: LobeHubService,
) -> None:
    """When verify finds broken markers, the next action must bypass `ensure`."""
    lobehub_svc._verify_cache = None
    lobehub_svc._run_patch_verify = lambda: _VerifySummaryStub(  # type: ignore[attr-defined]
        ok=15, broken=3, names=("file_proxy_rewrite", "host_console", "office_preview_local")
    )

    with (
        patch("lca.infrastructure.cli.services.lobehub.http_ready", return_value=True),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_on_port",
            side_effect=_port_pid(42_001, 42_002),
        ),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_alive",
            side_effect=lambda pid: pid in {42_001, 42_002},
        ),
    ):
        state = lobehub_svc.state()

    patches_check = next(c for c in state.checks if c.name == "patches")
    assert not patches_check.ok
    assert "15/18 verified" in patches_check.detail
    assert "file_proxy_rewrite" in patches_check.detail
    assert state.next_action == "python3 deploy/lobehub/patch_lobehub.py"
    assert state.status == ServiceStatus.RUNNING


def test_heal_runs_patch_engine_in_place_when_markers_broken(tmp_path: Path) -> None:
    """heal() must NOT stop+restart Next just to reapply patches.

    Uses its own fixture so the shared ``lobehub_svc`` stays free of the
    ``patch_lobehub.py`` script (its absence is what triggers the in-place
    repair branch).
    """
    root = tmp_path / "repo_heal"
    ui_dir = root / "lobehub-ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "package.json").write_text('{"version": "2.2.13"}')
    (ui_dir / ".lca-patched").write_text("ok")
    deploy_dir = root / "deploy" / "lobehub"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "patch_lobehub.py").write_text("#!/usr/bin/env python3\n")
    (deploy_dir / "patches").mkdir(parents=True)

    svc = LobeHubService(
        LobeHubConfig(dir="lobehub-ui", dev_port=3010),
        KernelServeConfig(port=8765),
        tmp_path / "state_heal",
        root,
    )
    svc._state.write_pid("lobehub", 42_001)
    svc._run_patch_verify = lambda: _VerifySummaryStub(  # type: ignore[attr-defined]
        ok=15, broken=3, names=("file_proxy_rewrite",)
    )

    invoked: list[list[str]] = []

    def _fake_run(cmd: object, **_kwargs: object) -> object:
        invoked.append(list(cmd))  # type: ignore[arg-type]

        class _R:
            returncode = 0
            stderr = ""
            stdout = "[patch] APPLIED file_proxy_rewrite\n[verify] 18 ok, 0 broken/missing\n"

        return _R()

    with (
        patch.object(svc, "stop") as stop,
        patch.object(svc, "start") as start,
        patch("lca.infrastructure.cli.services.lobehub.subprocess.run", side_effect=_fake_run),
        patch("lca.infrastructure.cli.services.lobehub.http_ready", return_value=True),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_on_port",
            side_effect=_port_pid(42_001, 42_002),
        ),
        patch(
            "lca.infrastructure.cli.services.lobehub.pid_alive",
            side_effect=lambda pid: pid in {42_001, 42_002},
        ),
    ):
        state = svc.heal()

    stop.assert_not_called()
    start.assert_not_called()
    assert invoked and invoked[0][0] == "python3"
    assert state.status == ServiceStatus.RUNNING
