"""RunAmbit: one immutable snapshot of every ambient resource a turn needs.

ADR-0122. Aggregates the eight previous ``run_*_scope`` contextvars so future
ambient additions only require one new field here instead of shotgun-edits
across every entry point that uses ambient state.

This module owns:

- :class:`RunAmbit` — immutable value object
- :func:`bind_run_ambit` — single ambient-binding context manager
- :func:`current_run_ambit` — read accessor
- :func:`current_file_store` / / :func:`current_workspace` / etc. — narrow
  accessors consumed by components that used to import
  ``get_current_run_file_store()`` / ``get_current_run_workspace()`` etc.

Compatibility window: legacy helpers (``run_id_scope``, ``run_attachment_scope``,
``run_workspace_scope``, ``run_scope``, ``search_run_scope``,
``run_file_store_scope``, ``run_machine_root_scope``, ``adopt_run_scope``)
keep their public surface — they are re-implemented on top of
``RunAmbit`` so callers do not need to migrate immediately. A future PR
will delete them after the 2026-Q4 deprecation window.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.models.observability.journal import RunScope
from lca.infrastructure.file_store import FileStore

__all__ = [
    "RunAmbit",
    "bind_run_ambit",
    "current_attachment_ids",
    "current_file_store",
    "current_plan_ref",
    "current_role",
    "current_run_ambit",
    "current_workspace",
]


@dataclass(frozen=True, slots=True)
class RunAmbit:
    """Immutable snapshot of every ambient resource one turn needs.

    New ambient resources MUST be added as a new field here — never as a
    new ``with (...)`` line at the call site. ADR-0122 / run_f03bd17f77f1.
    """

    scope: RunScope | None = None
    run_id: RunId | None = None
    trace_id: TraceId | None = None
    attachment_ids: tuple[str, ...] = ()
    workspace: Any | None = None
    file_store: FileStore | None = None
    machine_root: str | None = None
    search_state: Any | None = None
    plan_ref: str = ""
    role: str = ""


_run_ambit: ContextVar[RunAmbit | None] = ContextVar("lca_run_ambit", default=None)


@contextmanager
def bind_run_ambit(ambit: RunAmbit) -> Iterator[RunAmbit]:
    """Enter every ambient resource in one frame; LIFO reset on exit."""
    token: Token[RunAmbit | None] = _run_ambit.set(ambit)
    try:
        yield ambit
    finally:
        _run_ambit.reset(token)


def current_run_ambit() -> RunAmbit | None:
    """Return the currently bound ``RunAmbit`` or ``None`` when unbound."""
    return _run_ambit.get()


def current_file_store() -> FileStore | None:
    a = current_run_ambit()
    return a.file_store if a is not None else None


def current_workspace() -> Any | None:
    a = current_run_ambit()
    return a.workspace if a is not None else None


def current_attachment_ids() -> tuple[str, ...]:
    a = current_run_ambit()
    return a.attachment_ids if a is not None else ()


def current_plan_ref() -> str:
    a = current_run_ambit()
    return a.plan_ref if a is not None else ""


def current_role() -> str:
    a = current_run_ambit()
    return a.role if a is not None else ""
