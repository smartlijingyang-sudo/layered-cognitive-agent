"""execute subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Re-exports the carrier surface from the facade module so handlers can keep
their existing import paths. The legacy ``_record_terminal_materialization``
shim is gone in ADR-0122 — the real implementation lives in
``lca.plugins.transport.webserver.handlers.runs.terminal.materialization``.
"""

from lca.plugins.transport.webserver.handlers.runs.execute.execute import (
    create_run_session,
    execute_run,
    resume_run,
    schedule_run,
)
from lca.plugins.transport.webserver.handlers.runs.lifecycle import RunLifecycleCoordinator

__all__ = [
    "RunLifecycleCoordinator",
    "create_run_session",
    "execute_run",
    "resume_run",
    "schedule_run",
]
