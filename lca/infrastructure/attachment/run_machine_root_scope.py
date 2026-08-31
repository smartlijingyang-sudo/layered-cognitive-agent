"""Machine-root ambient for tests and overrides (ADR-0121).

Lets the default attachment provider stage into a sandbox-free ``/mnt/data``
path during tests without touching the read-only ``ONLYBOXES`` constant.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_machine_root: ContextVar[str | None] = ContextVar(
    "lca_attachment_machine_root",
    default=None,
)


def get_current_machine_root() -> str | None:
    return _machine_root.get()


@contextmanager
def run_machine_root_scope(root: str) -> Iterator[str]:
    token: Token[str | None] = _machine_root.set(root)
    try:
        yield root
    finally:
        _machine_root.reset(token)


__all__ = ["get_current_machine_root", "run_machine_root_scope"]