"""The supervisor package barrel re-exports the full public API.

After the structural split of the former single ``supervisor.py`` into a
package, every public name must still be importable from the original
module path (``...kernel.supervisor``). This test pins that contract so
the barrel can't silently drop a symbol, and exercises the config
parsing / result builders through the barrel exactly as CLI consumers
do.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.cli.services.kernel.supervisor import (
    ProgramConfig,
    ProgramEvent,
    ProgramState,
    ProgramStatus,
    RestartDecision,
    build_events_result,
    build_start_result,
    build_stop_result,
    decide_restart,
    default_program_config,
    parse_program_config,
)


def test_barrel_exports_all_public_names() -> None:
    import lca.infrastructure.cli.services.kernel.supervisor as sup

    for name in sup.__all__:
        assert hasattr(sup, name), f"barrel missing {name}"
    # build_stop_result is part of the wire contract even though it is
    # not listed in __all__ (matching the original module).
    assert hasattr(sup, "build_stop_result")


def test_parse_program_config_through_barrel(tmp_path: Path) -> None:
    path = tmp_path / "sup.conf"
    path.write_text("[program:app]\ncommand=/bin/echo\n")
    progs = parse_program_config(path)
    assert len(progs) == 1
    assert progs[0].name == "app"
    assert progs[0].command == "/bin/echo"


def test_default_program_config_through_barrel() -> None:
    cfg = default_program_config()
    assert cfg.name == "lca_kernel_dev"
    assert cfg.args[:2] == ("-m", "lca_kernel")


def test_result_builders_through_barrel() -> None:
    cfg = ProgramConfig(name="app", command="/bin/echo")
    status = ProgramStatus(
        name="app",
        state=ProgramState.RUNNING,
        pid=42,
        uptime_s=1.0,
    )
    result = build_start_result(cfg, status, ready=True)
    assert result["verdict"] == "ready"
    assert result["status"]["pid"] == 42

    stop = build_stop_result(cfg, status, orphans_killed=0)
    assert stop["verdict"] == "ready"

    events = build_events_result([ProgramEvent(ts=1.0, kind="spawned", pid=42)])
    assert events["events"][0]["kind"] == "spawned"


def test_decide_restart_through_barrel() -> None:
    d = decide_restart(
        0,
        autorestart=True,
        restart_count=0,
        startretries=3,
        user_stopped=False,
    )
    assert isinstance(d, RestartDecision)
    assert d.next_state == ProgramState.BACKOFF
