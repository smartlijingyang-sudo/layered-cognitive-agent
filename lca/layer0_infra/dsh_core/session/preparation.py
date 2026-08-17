"""1:1 port of ``@deepseek-ai/dsh-session/preparation``.

Ownership of one unpublished Session before registry publication.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class SessionPreparationOptions:
    """Options for a preparation whose provider retains unpublished state."""

    __slots__ = ("release",)

    def __init__(self, release: Callable[[], None] | None = None) -> None:
        self.release = release


class SessionPreparation:
    """One exact unpublished Session and the provider state that keeps it usable.

    Disposal is synchronous and idempotent.  Providers decide whether release
    returns the Session to a cache or discards it; publication may consume that
    state before disposal, making the callback a no-op.
    """

    __slots__ = ("_options", "_released", "session")

    def __init__(self, session: Any, options: SessionPreparationOptions | None = None) -> None:
        self.session = session
        self._options = options or SessionPreparationOptions()
        self._released = False

    @staticmethod
    def create(
        session: Any,
        options: SessionPreparationOptions | None = None,
    ) -> SessionPreparation:
        """Wrap an unpublished Session in one preparation lifetime."""
        return SessionPreparation(session, options)

    def dispose(self) -> None:
        """Release provider state once when this preparation leaves its caller."""
        if self._released:
            return
        self._released = True
        if self._options.release is not None:
            self._options.release()

    def __enter__(self) -> SessionPreparation:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.dispose()

    def close(self) -> None:
        """Alias for :meth:`dispose` — context-manager protocol."""
        self.dispose()
