"""execute subpackage of gateway.runs — split per ADR-0105 §11.2.

Re-exports RunLifecycleCoordinator FIRST so that execute.py can
``from gateway.runs.execute import RunLifecycleCoordinator`` without
triggering a circular import. Then imports the facade module.
"""

# 1. lifecycle first (so execute.py can re-import via this package)
# 2. facade module last
from gateway.runs.execute.execute import (
    _record_terminal_materialization,
    create_run_session,
    execute_run,
    llm_status,
    resume_run,
    sanitize_error,
    schedule_run,
)
from gateway.runs.lifecycle import RunLifecycleCoordinator

__all__ = [
    "RunLifecycleCoordinator",
    "_record_terminal_materialization",
    "create_run_session",
    "execute_run",
    "llm_status",
    "resume_run",
    "sanitize_error",
    "schedule_run",
]
