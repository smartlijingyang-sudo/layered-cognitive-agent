"""Cross-process state file for the kernel supervisor.

Each CLI invocation is a fresh process; the supervisor's ``_proc`` /
``_state`` live only inside that process. The state file lets ``status``
(in process A) read what ``start`` (in process B) wrote. Format is
JSON, atomic write via tmp + rename.
"""

from __future__ import annotations

import contextlib
import json as _json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from lca.infrastructure.cli.services.kernel.supervisor.process import (
    _PhantomProc,
    _pid_alive,
)
from lca.infrastructure.cli.services.kernel.supervisor.types import (
    ProgramConfig,
    ProgramState,
    ProgramStatus,
)

if TYPE_CHECKING:
    from lca.infrastructure.cli.services.kernel.supervisor.supervisor import (
        KernelSupervisor,
    )

_STATE_PATH = Path(
    os.environ.get(
        "LCA_SUPERVISOR_STATE",
        "/tmp/lca-supervisor.state.json",  # noqa: S108
    )
)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: tmp + rename, so readers never see a torn
    file. Best-effort; readers fall back to "unknown" on read failure.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(_json.dumps(data), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


def read_state_file() -> dict | None:
    """Public read of the cross-process state file.

    Returns the parsed dict written by the most recent
    :meth:`KernelSupervisor._transition`, or ``None`` if the file is
    missing / unreadable / malformed.
    """
    return _read_state_file()


def _read_state_file() -> dict | None:
    """Best-effort read of the supervisor state file."""
    try:
        return _json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_state(name: str, snapshot: ProgramStatus) -> None:
    _atomic_write_json(
        _STATE_PATH,
        {
            "program": name,
            "pid": snapshot.pid,
            "state": snapshot.state.value,
            "uptime_s": snapshot.uptime_s,
            "restart_count": snapshot.restart_count,
            "last_exit_code": snapshot.last_exit_code,
            "last_event": snapshot.last_event,
            "spawned_at": snapshot.spawned_at,
            "ts": time.time(),
        },
    )


def clear_state() -> None:
    """Delete the cross-process state file. Idempotent."""
    with contextlib.suppress(OSError):
        _STATE_PATH.unlink(missing_ok=True)


def _hydrate_from_state_file(sup: KernelSupervisor, cfg: ProgramConfig) -> None:
    """Read the most recent state-file snapshot and apply it to ``sup``
    IF the persisted pid is still alive. Called from
    :func:`get_supervisor` on first use within a process.
    """
    st = read_state_file()
    if st is None or st.get("program") != cfg.name:
        return
    persisted_pid = st.get("pid")
    if persisted_pid is None or not _pid_alive(int(persisted_pid)):
        clear_state()
        return
    sup._state = ProgramState(st["state"])
    sup._last_event = st.get("last_event", "")
    sup._restart_count = st.get("restart_count", 0)
    sup._last_exit_code = st.get("last_exit_code")
    sup._spawned_at = time.monotonic()  # reset the clock for this process
    sup._proc = _PhantomProc(int(persisted_pid))


def status_from_state_file(cfg: ProgramConfig) -> ProgramStatus | None:
    """Read the persisted snapshot, returning ``None`` if the state
    file is missing or refers to a different program.
    """
    st = read_state_file()
    if st is None or st.get("program") != cfg.name:
        return None
    try:
        state = ProgramState(st["state"])
    except (KeyError, ValueError):
        return None
    return ProgramStatus(
        name=cfg.name,
        state=state,
        pid=st.get("pid"),
        uptime_s=st.get("uptime_s", 0.0),
        restart_count=st.get("restart_count", 0),
        last_exit_code=st.get("last_exit_code"),
        last_event=st.get("last_event", ""),
        spawned_at=st.get("spawned_at"),
    )
