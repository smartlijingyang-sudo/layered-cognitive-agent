"""Shared wire types for the kernel supervisor package.

These types are the public contract of the supervisor: lifecycle state,
program config, events and status snapshots. They live in their own
module so ``config`` / ``state`` / ``results`` / ``supervisor`` can
import them without cycles.
"""

from __future__ import annotations

from enum import StrEnum
import shlex
from dataclasses import dataclass, field


class ProgramState(StrEnum):
    """Lifecycle state of one supervised program.

    String-valued so :class:`ProgramStatus` serialises naturally in
    JSON without a custom encoder; values are stable across the wire.
    """

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    BACKOFF = "backoff"
    FATAL = "fatal"
    STOPPING = "stopping"


@dataclass(frozen=True)
class ProgramConfig:
    """One ``[program:...]`` section, supervisord-compatible keys.

    Mirrors supervisord's vocabulary (subset). Unknown keys raise
    :class:`ValueError` at parse time so mis-typed config fails loud.
    """

    name: str
    command: str
    directory: str = ""
    autorestart: bool = True
    startretries: int = 3
    stopwaitsecs: float = 15.0
    environment: dict[str, str] = field(default_factory=dict)
    stdout_logfile: str | None = None
    stderr_logfile: str | None = None
    readiness_timeout: float = 30.0
    args: tuple[str, ...] = field(default_factory=tuple)

    def argv(self) -> list[str]:
        cmd = shlex.split(self.command) if self.command else []
        return cmd + list(self.args)

    def host(self) -> str:
        for i, a in enumerate(self.args):
            if a == "--host" and i + 1 < len(self.args):
                return self.args[i + 1]
        return "127.0.0.1"

    def port(self) -> int | None:
        for i, a in enumerate(self.args):
            if a == "--port" and i + 1 < len(self.args):
                try:
                    return int(self.args[i + 1])
                except ValueError:
                    return None
        return None


@dataclass(frozen=True)
class ProgramEvent:
    """One supervisor event, emitted on the event stream.

    ``kind`` ∈ ``{spawned, ready, died, restarted, stopped, fatal,
    backoff}``. ``message`` is human-readable; consumers should not
    parse it.
    """

    ts: float
    kind: str
    pid: int | None = None
    exit_code: int | None = None
    message: str = ""


@dataclass(frozen=True)
class ProgramStatus:
    """Snapshot of a supervised program at one moment in time."""

    name: str
    state: ProgramState
    pid: int | None = None
    uptime_s: float = 0.0
    restart_count: int = 0
    last_exit_code: int | None = None
    last_event: str = ""
    spawned_at: float | None = None


@dataclass(frozen=True)
class RestartDecision:
    """Outcome of :func:`decide_restart`."""

    next_state: ProgramState
    backoff_s: float
    reason: str
