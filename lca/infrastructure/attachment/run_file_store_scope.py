"""Run-scoped FileStore ambient (ADR-0121).

Reasoner code has no explicit ``ctx`` handle, so the only way to reach the
FileStore during prompt assembly is via an ambient contextvar. The CreateRun
handler binds this on every turn; release happens automatically when the
turn completes (see :func:`run_file_store_scope`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from lca.infrastructure.file_store import FileStore

_run_file_store: ContextVar[FileStore | None] = ContextVar(
    "lca_run_file_store",
    default=None,
)


def get_current_run_file_store() -> FileStore | None:
    """Return the run-bound :class:`FileStore`, or ``None`` when unbound."""
    return _run_file_store.get()


@contextmanager
def run_file_store_scope(store: FileStore) -> Iterator[FileStore]:
    """Bind ``store`` for the duration of the turn."""
    token: Token[FileStore | None] = _run_file_store.set(store)
    try:
        yield store
    finally:
        _run_file_store.reset(token)


__all__ = ["get_current_run_file_store", "run_file_store_scope"]
