"""Kernel supervisor — minimal supervisord-style process manager.

Why this exists
---------------
LCA's kernel in production is guarded by an external supervisor (ADR-0119).
For the **dev path**, ``lca-ops`` still needs a way to spawn / stop /
restart the kernel locally without each user wiring up supervisord or
systemd. This module is that local supervisor: a small
``KernelSupervisor`` that owns the kernel subprocess, runs an
autorestart loop, and surfaces events to ``lca-ops`` CLI consumers.

Design
------
Three independent loops, each doing one thing:

1. ``spawner`` — call :func:`subprocess.Popen` + emit ``spawned`` event.
2. ``waiter`` — call :func:`proc.wait` (blocking, no busy-poll) +
   emit ``died`` event with exit code.
3. ``decider`` — pull ``died`` events, call :func:`decide_restart`
   (pure function, table-driven) and emit ``restarted`` / ``fatal`` /
   ``stopped`` events.

State is a single :class:`ProgramState` value, mutated only via
:meth:`KernelSupervisor._transition`, which fires the event and wakes
subscribers.

Readiness
---------
After spawning, a one-shot ``GET /health`` probe (via
:func:`health_body_ok`) is attempted every :attr:`KernelSupervisor._READINESS_POLL_S`
until it succeeds or :attr:`ProgramConfig.readiness_timeout` elapses.
A timeout does **not** kill the subprocess; it just leaves state at
STARTING. Death while STARTING triggers the decider.

Why no busy-poll
----------------
:func:`proc.wait` blocks until the kernel exits; no need for
``while poll() is None: sleep(0.1)``. :func:`queue.Queue.get` blocks
until an event is queued; no need for ``while True: check``.

Package layout
--------------
This package splits the former single module into focused submodules:
``config`` (supervisord-syntax parsing), ``state`` (cross-process state
file), ``results`` (action result builders), ``process`` (pid helpers /
phantom proc), ``decisions`` (restart-decision table), ``types``
(shared wire types) and ``supervisor`` (the ``KernelSupervisor`` class
and per-process cache). The public API is re-exported here so existing
importers keep working unchanged.
"""

from __future__ import annotations

from lca.infrastructure.cli.services.kernel.supervisor.config import (
    default_program_config,
    parse_program_config,
)
from lca.infrastructure.cli.services.kernel.supervisor.decisions import (
    decide_restart,
)
from lca.infrastructure.cli.services.kernel.supervisor.results import (
    build_check_config_result,
    build_command_error_result,
    build_config_error_result,
    build_events_result,
    build_restart_result,
    build_start_result,
    build_status_result,
    build_stop_result as build_stop_result,
)
from lca.infrastructure.cli.services.kernel.supervisor.state import (
    clear_state,
    read_state_file,
    status_from_state_file,
)
from lca.infrastructure.cli.services.kernel.supervisor.supervisor import (
    KernelSupervisor,
    get_supervisor,
)
from lca.infrastructure.cli.services.kernel.supervisor.types import (
    ProgramConfig,
    ProgramEvent,
    ProgramState,
    ProgramStatus,
    RestartDecision,
)

__all__ = [
    "KernelSupervisor",
    "ProgramConfig",
    "ProgramEvent",
    "ProgramState",
    "ProgramStatus",
    "RestartDecision",
    "build_check_config_result",
    "build_command_error_result",
    "build_config_error_result",
    "build_events_result",
    "build_restart_result",
    "build_start_result",
    "build_status_result",
    "clear_state",
    "decide_restart",
    "default_program_config",
    "get_supervisor",
    "parse_program_config",
    "read_state_file",
    "status_from_state_file",
]
