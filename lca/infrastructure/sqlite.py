"""Shared SQLite transaction discipline for infrastructure stores.

Single home for the BEGIN IMMEDIATE transaction pattern used by the
sqlite-backed durable stores: open one IMMEDIATE transaction, roll back on
any exception (including BaseException, so KeyboardInterrupt /
CancelledError never leave a half-written row), commit otherwise.

Callers pass their own connection factory because each store configures its
connection differently (WAL pragmas, registered SQL functions, row factory);
only the transaction discipline is shared.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager


@contextmanager
def transaction(
    connection_factory: Callable[[], AbstractContextManager[sqlite3.Connection]],
) -> Iterator[sqlite3.Connection]:
    """Run one IMMEDIATE transaction on a connection from connection_factory."""
    with connection_factory() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()


__all__ = ["transaction"]
