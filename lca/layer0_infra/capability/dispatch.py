"""Named provider table used by every Definition service."""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class ProviderDispatch(Generic[T]):
    """Definition 内部的 Provider 挂载表：register / use / current。"""

    def __init__(self, seam: str) -> None:
        self._seam = seam
        self._providers: dict[str, T] = {}
        self._active: str | None = None

    def register(self, name: str, provider: T, *, activate: bool = False) -> None:
        key = name.strip()
        if not key:
            raise ValueError(f"{self._seam}: provider name is empty")
        self._providers[key] = provider
        if self._active is None or activate:
            self._active = key

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
