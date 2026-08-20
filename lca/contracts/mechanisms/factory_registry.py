"""Named factory registry — fail-on-duplicate multi-impl seam (ADR-0062 §3)."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

T = TypeVar("T")


class FactoryRegistry(Generic[T]):
    """Name → factory table. Duplicate ``register`` raises ``KeyError``."""

    def __init__(self, seam: str) -> None:
        self._seam = seam
        self._entries: dict[str, T] = {}

    @property
    def seam(self) -> str:
        return self._seam

    def register(self, name: str, factory: T, *, activate: bool = False) -> None:
        del activate
        key = str(name).strip()
        if not key:
            raise ValueError(f"{self._seam}: factory name is empty")
        if key in self._entries:
            raise KeyError(f"{self._seam}: factory {key!r} already registered")
        self._entries[key] = factory

    def resolve(self, name: str) -> T:
        key = str(name).strip()
        try:
            return self._entries[key]
        except KeyError as exc:
            raise KeyError(
                f"{self._seam}: unknown factory {key!r}; have {sorted(self._entries)}"
            ) from exc

    def get(self, name: str) -> T | None:
        return self._entries.get(str(name).strip())

    def create(self, name: str, *args: Any, **kwargs: Any) -> Any:
        factory = self.resolve(name)
        if callable(factory):
            return factory(*args, **kwargs)
        return factory

    def names(self) -> list[str]:
        return list(self._entries)

    def __contains__(self, name: str) -> bool:
        return str(name).strip() in self._entries

    def __repr__(self) -> str:
        return f"FactoryRegistry(seam={self._seam!r}, names={sorted(self._entries)})"
