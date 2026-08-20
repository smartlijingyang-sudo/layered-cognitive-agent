"""SeamRegistry — runtime slot per seam_key; 0..N providers, 0..1 active.

Mirrors DSH's "service registry" pattern (each seam is a single ``extends Service``
in TypeScript). Here every seam key (``llm / sandbox / memory / ...``) is a
``SeamRegistry`` written by :mod:`lca.plugins.seam_definitions` during boot;
Tier-1 service plugins and Tier-2 provider plugins both interact with it via
the same ``register`` / ``current`` API.

Three-layer capability graph (per spec §4 A.7):

* Tier-1 service plugin (e.g. ``lca-llm-service``) → ``ctx.provide("llm", svc)``
  where ``svc`` is itself a :class:`SeamRegistry`-shaped Definition. The service
  plugin also calls ``seam.register("default", svc)`` so the seam registry
  knows one provider exists.
* Tier-2 provider plugin (e.g. ``lca-llm-provider``) → ``ctx.inject("llm").register(...)``
  on the Definition, AND ``ctx.inject("seam:llm").register("provider", adapter)``
  on the seam registry (for inspect-tree / boot-report visibility).
* Composer / runtime → ``require_capability(ctx, "llm")`` calls
  ``ctx.inject("seam:llm").current()`` to fetch the active Definition, then
  delegates ``complete`` / ``stream`` to its current adapter.

The class is intentionally a thin, typed, single-active registry — no hidden
state, no observable side effects beyond the optional change listener.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class SeamRegistry(Generic[T]):
    """Single-active registry for one seam_key. Mirrors DSH service registries.

    ``register(name, provider, activate=False)`` stores one provider. At most
    one is active at a time; first registration wins by default. ``current()``
    returns the active provider or ``None`` if the registry is empty.
    """

    def __init__(self, seam_key: str) -> None:
        self._seam_key = seam_key
        self._providers: dict[str, T] = {}
        self._active: str | None = None
        self._on_change: list[Callable[[], None]] = []

    @property
    def seam_key(self) -> str:
        return self._seam_key

    def register(self, name: str, provider: T, *, activate: bool = False) -> None:
        """Register one provider. First registration wins by default.

        ``activate=True`` forces this provider to become the active one even if
        another is already active. The active provider survives only as long as
        the next register/activate does not replace it.
        """
        key = str(name).strip()
        if not key:
            raise ValueError(f"{self._seam_key}: provider name is empty")
        self._providers[key] = provider
        if self._active is None or activate:
            self._active = key
        self._notify_change()

    def current(self) -> T | None:
        if self._active is None:
            return None
        return self._providers.get(self._active)

    def get(self, name: str) -> T | None:
        return self._providers.get(name)

    def names(self) -> list[str]:
        return list(self._providers)

    @property
    def active(self) -> str | None:
        return self._active

    def on_change(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._on_change.append(listener)

        def off() -> None:
            with contextlib.suppress(ValueError):
                self._on_change.remove(listener)

            return off

        return off

    def _notify_change(self) -> None:
        for listener in list(self._on_change):
            try:
                listener()
            except Exception:
                # Change listeners must never break the registry.
                import structlog

                structlog.get_logger("lca.seam_registry").warning(
                    "seam_change_listener_error",
                    seam=self._seam_key,
                    exc_info=True,
                )

    def __repr__(self) -> str:
        return (
            f"SeamRegistry(seam_key={self._seam_key!r}, "
            f"providers={sorted(self._providers)}, active={self._active!r})"
        )


__all__ = ["SeamRegistry"]


def seam_key_for(binding: str) -> str:
    """Convert a plain capability key to its seam-namespaced alias.

    ``seam_key_for("llm")`` → ``"seam:llm"``.
    """
    return f"seam:{binding}"
