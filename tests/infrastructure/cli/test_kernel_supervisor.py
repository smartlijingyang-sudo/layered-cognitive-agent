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
    ProgramState,
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
