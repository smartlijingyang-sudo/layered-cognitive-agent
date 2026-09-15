"""``KernelSupervisor`` — table-driven decide_restart + supervisord
config parsing + cross-process state file.

These tests do NOT spawn the LCA kernel (they run in CI and don't have
the deps). They pin the wire-stable contract:

- :func:`decide_restart` — pure decision, table-driven
- :func:`parse_program_config` — supervisord syntax
- :func:`read_state_file` / :func:`clear_state` — cross-process state
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.cli.services.kernel.supervisor import (
    ProgramConfig,
    ProgramEvent,
    ProgramState,
    ProgramStatus,
    build_check_config_result,
    build_command_error_result,
    build_config_error_result,
    build_events_result,
    build_restart_result,
    build_start_result,
    build_status_result,
    build_stop_result,
    clear_state,
    decide_restart,
    get_supervisor,
    parse_program_config,
    read_state_file,
)

# ── decide_restart (pure, table-driven) ──────────────────────────────


class TestDecideRestart:
    """Each rule in ``decide_restart`` gets its own test for clarity."""

    def test_user_stopped_returns_stopped_no_matter_what(self) -> None:
        d = decide_restart(
            0, autorestart=True, restart_count=0, startretries=3,
            user_stopped=True,
        )
        assert d.next_state == ProgramState.STOPPED
        assert d.backoff_s == 0.0
        assert "user stop" in d.reason

    def test_clean_exit_with_autorestart_false_returns_stopped(self) -> None:
        d = decide_restart(
            0, autorestart=False, restart_count=0, startretries=3,
            user_stopped=False,
        )
        assert d.next_state == ProgramState.STOPPED

    def test_clean_exit_with_autorestart_true_backs_off(self) -> None:
        d = decide_restart(
            0, autorestart=True, restart_count=0, startretries=3,
            user_stopped=False,
        )
        assert d.next_state == ProgramState.BACKOFF
        assert d.backoff_s == 1.0  # 2^0 = 1
        assert "1/3" in d.reason

    def test_exhausted_startretries_returns_fatal(self) -> None:
        d = decide_restart(
            1, autorestart=True, restart_count=3, startretries=3,
            user_stopped=False,
        )
        assert d.next_state == ProgramState.FATAL
        assert "exhausted" in d.reason

    def test_backoff_capped_at_30(self) -> None:
        # 2^5 = 32, capped to 30
        d = decide_restart(
            1, autorestart=True, restart_count=5, startretries=10,
            user_stopped=False,
        )
        assert d.backoff_s == 30.0

    def test_user_stopped_wins_over_clean(self) -> None:
        # Even with autorestart=False and clean exit, user_stopped
        # takes precedence (the supervisor was asked to stop).
        d = decide_restart(
            0, autorestart=False, restart_count=0, startretries=3,
            user_stopped=True,
        )
        assert d.next_state == ProgramState.STOPPED
        assert "user stop" in d.reason


# ── parse_program_config (supervisord syntax) ──────────────────────


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "sup.conf"
    p.write_text(content)
    return p


class TestParseProgramConfig:
    def test_minimal_program(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "[program:app]\ncommand=/bin/echo\n",
        )
        progs = parse_program_config(path)
        assert len(progs) == 1
        assert progs[0].name == "app"
        assert progs[0].command == "/bin/echo"
        assert progs[0].autorestart is True
        assert progs[0].startretries == 3
        assert progs[0].stopwaitsecs == 15.0

    def test_args_are_split_shell_style(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "[program:app]\ncommand=/bin/echo\n"
            "args=--foo \"hello world\" --bar=42\n",
        )
        progs = parse_program_config(path)
        assert progs[0].args == ("--foo", "hello world", "--bar=42")

    def test_unknown_keys_raise_loud(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "[program:app]\ncommand=/bin/echo\n"
            "user=root\n",  # supervisord doesn't have this
        )
        with pytest.raises(ValueError, match="unknown keys"):
            parse_program_config(path)

    def test_invalid_bool_raises_loud(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "[program:app]\ncommand=/bin/echo\n"
            "autorestart=maybe\n",
        )
        with pytest.raises(ValueError, match="autorestart"):
            parse_program_config(path)

    def test_invalid_int_raises_loud(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "[program:app]\ncommand=/bin/echo\n"
            "startretries=many\n",
        )
        with pytest.raises(ValueError, match="startretries"):
            parse_program_config(path)

    def test_missing_command_raises(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "[program:app]\nautorestart=true\n",
        )
        with pytest.raises(ValueError, match="command="):
            parse_program_config(path)

    def test_no_programs_raises(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "[supervisord]\nlogfile=/tmp/x.log\n",
        )
        with pytest.raises(ValueError, match="no \\[program:"):
            parse_program_config(path)

    def test_env_parsing(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "[program:app]\ncommand=/bin/echo\n"
            "environment=KEY1=val1,KEY2=val2\n",
        )
        progs = parse_program_config(path)
        assert progs[0].environment == {"KEY1": "val1", "KEY2": "val2"}

    def test_unknown_section_ignored(self, tmp_path: Path) -> None:
        # supervisord section + unix_http_server are valid supervisord
        # but LCA doesn't use them — should be silently ignored.
        path = _write(
            tmp_path,
            "[supervisord]\nlogfile=/tmp/x.log\n"
            "[unix_http_server]\nfile=/tmp/x.sock\n"
            "[program:app]\ncommand=/bin/echo\n",
        )
        progs = parse_program_config(path)
        assert [p.name for p in progs] == ["app"]


# ── read_state_file / clear_state ─────────────────────────────────


class TestStateFile:
    def test_clear_removes_file(self, tmp_path: Path, monkeypatch) -> None:
        # Override LCA_SUPERVISOR_STATE for the test.
        import lca.infrastructure.cli.services.kernel.supervisor as mod
        state = tmp_path / "state.json"
        state.write_text('{"program":"x","pid":1}')
        monkeypatch.setattr(mod, "_STATE_PATH", state)
        assert mod._read_state_file() == {"program": "x", "pid": 1}
        clear_state()
        assert not state.exists()
        assert read_state_file() is None

    def test_read_missing_returns_none(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import lca.infrastructure.cli.services.kernel.supervisor as mod
        state = tmp_path / "nonexistent.json"
        monkeypatch.setattr(mod, "_STATE_PATH", state)
        assert read_state_file() is None

    def test_read_malformed_returns_none(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import lca.infrastructure.cli.services.kernel.supervisor as mod
        state = tmp_path / "state.json"
        state.write_text("not json")
        monkeypatch.setattr(mod, "_STATE_PATH", state)
        assert read_state_file() is None


# ── get_supervisor (singleton + hydration) ──────────────────────────


class TestGetSupervisor:
    def test_returns_same_instance_for_same_config(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Reset module-level cache so the test is hermetic.
        import lca.infrastructure.cli.services.kernel.supervisor as mod
        monkeypatch.setattr(mod, "_SUPERVISOR_CACHE", {})

        cfg = ProgramConfig(
            name="test_app", command="/bin/echo", args=("hi",),
        )
        a = get_supervisor(cfg)
        b = get_supervisor(cfg)
        assert a is b

    def test_returns_different_instance_for_different_config(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import lca.infrastructure.cli.services.kernel.supervisor as mod
        monkeypatch.setattr(mod, "_SUPERVISOR_CACHE", {})

        a = get_supervisor(
            ProgramConfig(name="x", command="/bin/echo", args=())
        )
        b = get_supervisor(
            ProgramConfig(name="y", command="/bin/echo", args=())
        )
        assert a is not b


# ── Action result builders (wire contract) ──────────────────────────


def _status_fixture(state: ProgramState = ProgramState.RUNNING) -> ProgramStatus:
    return ProgramStatus(
        name="lca_kernel_dev",
        state=state,
        pid=12345,
        uptime_s=4.5,
        restart_count=0,
        last_exit_code=None,
        last_event="readiness probe passed",
        spawned_at=1234567890.0,
    )


class TestActionResultBuilders:
    """Pin the wire-stable output shape across all actions.

    Every ``build_*_result`` returns a dict with stable keys
    (verdict, detail|reason, status?, next_command?). Service-layer
    tests pin this contract so refactors can't silently change it.
    """

    def test_build_start_ready(self) -> None:
        cfg = ProgramConfig(name="lca_kernel_dev", command="/bin/echo")
        status = _status_fixture()
        result = build_start_result(cfg, status, ready=True)
        assert result["verdict"] == "ready"
        assert "started pid=" in result["detail"]
        assert result["status"]["pid"] == 12345
        assert "kernel-supervisor status" in result["next_command"]

    def test_build_start_failed(self) -> None:
        cfg = ProgramConfig(
            name="lca_kernel_dev", command="/bin/echo",
            readiness_timeout=30.0,
        )
        status = _status_fixture(state=ProgramState.STARTING)
        result = build_start_result(cfg, status, ready=False)
        assert result["verdict"] == "failed"
        assert "did not become ready within" in result["detail"]
        assert "kernel-supervisor logs" in result["next_command"]

    def test_build_stop(self) -> None:
        cfg = ProgramConfig(name="lca_kernel_dev", command="/bin/echo")
        status = _status_fixture(state=ProgramState.STOPPED)
        result = build_stop_result(cfg, status, orphans_killed=2)
        assert result["verdict"] == "ready"
        assert "orphans_killed=2" in result["detail"]
        assert "kernel-supervisor start" in result["next_command"]

    def test_build_restart_ready(self) -> None:
        cfg = ProgramConfig(name="lca_kernel_dev", command="/bin/echo")
        status = _status_fixture()
        result = build_restart_result(cfg, status, ready=True)
        assert result["verdict"] == "ready"
        assert "LCA kernel restarted" in result["detail"]

    def test_build_restart_failed(self) -> None:
        cfg = ProgramConfig(
            name="lca_kernel_dev", command="/bin/echo",
            readiness_timeout=15.0,
        )
        status = _status_fixture(state=ProgramState.STARTING)
        result = build_restart_result(cfg, status, ready=False)
        assert result["verdict"] == "failed"
        assert "kernel-supervisor logs" in result["next_command"]

    def test_build_status_running(self) -> None:
        cfg = ProgramConfig(name="lca_kernel_dev", command="/bin/echo")
        events = [
            ProgramEvent(ts=1.0, kind="spawned", pid=12345, message="hi"),
        ]
        result = build_status_result(
            cfg, _status_fixture(), events=events,
        )
        assert result["verdict"] == "ready"
        assert "next_command" not in result
        assert len(result["events"]) == 1
        assert result["events"][0]["kind"] == "spawned"

    def test_build_status_fatal_includes_next_command(self) -> None:
        cfg = ProgramConfig(name="lca_kernel_dev", command="/bin/echo")
        status = _status_fixture(state=ProgramState.FATAL)
        result = build_status_result(
            cfg, status, events=[], is_fatal=True,
        )
        assert result["verdict"] == "failed"
        assert "kernel-supervisor logs" in result["next_command"]

    def test_build_events(self) -> None:
        events = [
            ProgramEvent(ts=1.0, kind="spawned", pid=42),
            ProgramEvent(ts=2.0, kind="died", exit_code=1),
        ]
        result = build_events_result(events)
        assert result["verdict"] == "ready"
        assert len(result["events"]) == 2
        assert result["events"][0]["kind"] == "spawned"
        assert result["events"][1]["exit_code"] == 1

    def test_build_check_config(self) -> None:
        progs = [
            ProgramConfig(name="app_a", command="/bin/echo"),
            ProgramConfig(
                name="app_b", command="/bin/echo",
                args=("--port", "8080"),
            ),
        ]
        result = build_check_config_result("/tmp/sup.conf", progs)
        assert result["verdict"] == "ready"
        assert result["config_path"] == "/tmp/sup.conf"
        assert len(result["programs"]) == 2

    def test_build_config_error(self) -> None:
        result = build_config_error_result(
            "/tmp/bad.conf", ValueError("missing command"),
        )
        assert result["verdict"] == "failed"
        assert "missing command" in result["reason"]
        assert "check-config" in result["next_command"]

    def test_build_command_error_with_orphans(self) -> None:
        cfg = ProgramConfig(name="app", command="/bin/echo")
        result = build_command_error_result(
            "start", cfg, orphan_pids=[123, 456],
            status=_status_fixture(),
        )
        assert result["verdict"] == "failed"
        assert "pid=[123, 456]" in result["reason"]
        assert "kernel-supervisor stop" in result["next_command"]

    def test_build_command_error_unknown_action(self) -> None:
        result = build_command_error_result("foobar", None)
        assert result["verdict"] == "failed"
        assert "unknown action 'foobar'" in result["reason"]
        assert "--help" in result["next_command"]
