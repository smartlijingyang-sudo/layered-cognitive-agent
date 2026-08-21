"""Named provider table used by every Definition service.


- ``register`` returns an idempotent disposer so provider installation is a
  reversible effect (Cordis: "registrations are effects").
- ``replace`` swaps one provider's routing in a single synchronous section,
  emitting the change.
- ``use`` / ``current`` / ``get`` / ``names`` keep the single-active pattern.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class ProviderDispatch(Generic[T]):
    """Definition 内部的 Provider 挂载表：register / use / current / replace。

    多 provider registry seam（llm / web / skills / subagents）的统一形态：
    - ``register`` 返回幂等 disposer，卸载即撤销该 provider 的路由；
    - ``replace`` 在一个同步区段内完成原子路由替换（无空窗期）。
    """

    def __init__(self, seam: str) -> None:
        self._seam = seam
        self._providers: dict[str, T] = {}
        self._active: str | None = None
        self._on_change: list[Callable[[], None]] = []

    def register(self, name: str, provider: T, *, activate: bool = False) -> Callable[[], None]:
        key = name.strip()
        if not key:
            raise ValueError(f"{self._seam}: provider name is empty")
        if key in self._providers:
            raise KeyError(f"{self._seam}: provider {key!r} already registered")
        self._providers[key] = provider
        if self._active is None or activate:
            self._active = key
        disposed = False

        def disposer() -> None:
            nonlocal disposed
            if disposed:
                return
            disposed = True
            self._providers.pop(key, None)
            if self._active == key:
                self._active = next(iter(self._providers), None)
            self._notify_change()

        return disposer

    def replace(self, name: str, provider: T) -> Callable[[], None]:
        """Atomically replace *name*'s provider. Returns the new disposer."""
        if name not in self._providers:
            raise KeyError(f"{self._seam}: unknown provider {name!r}")
        old = self._providers[name]
        if old is provider:
            return lambda: None
        self._providers[name] = provider
        self._notify_change()

        disposed = False

        def disposer() -> None:
            nonlocal disposed
            if disposed:
                return
            disposed = True
            self._providers.pop(name, None)
            if self._active == name:
                self._active = next(iter(self._providers), None)
            self._notify_change()

        return disposer

    def use(self, name: str) -> T:
        if name not in self._providers:
            raise KeyError(
                f"{self._seam}: unknown provider {name!r}; have {sorted(self._providers)}"
            )
        self._active = name
        return self._providers[name]

    def current(self) -> T:
        if self._active is None:
            raise RuntimeError(f"{self._seam}: no provider registered")
        return self._providers[self._active]

    def get(self, name: str) -> T:
        """Look up a provider without changing the active selection."""
        if name not in self._providers:
            raise KeyError(
                f"{self._seam}: unknown provider {name!r}; have {sorted(self._providers)}"
            )
        return self._providers[name]

    def names(self) -> list[str]:
        return list(self._providers)

    @property
    def active(self) -> str | None:
        return self._active

    # ── Change observation (Cordis ``emit`` mirror) ─────────

    def on_change(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a change listener. Returns its disposer."""
        self._on_change.append(listener)

        def off() -> None:
            with contextlib.suppress(ValueError):
                self._on_change.remove(listener)

        return off

    def _notify_change(self) -> None:
        import structlog

        for listener in list(self._on_change):
            try:
                listener()
            except Exception:
                structlog.get_logger("lca.provider").warning(
                    "provider_change_listener_error", seam=self._seam, exc_info=True
                )
