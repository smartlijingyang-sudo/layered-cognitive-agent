"""DisposableList — ordered collection with O(1) delete-by-value."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DisposableList:
    """Dual-index: ``_map`` (sn→value) + ``_weak`` (id→sn) for O(1) delete."""

    def __init__(self) -> None:
        self._sn: int = 0
        self._map: dict[int, Any] = {}
        self._weak: dict[int, int] = {}

    def __len__(self) -> int:
        return len(self._map)

    def push(self, value: Any) -> Callable[[], bool]:
        """Add *value*; return remover."""
        self._sn += 1
        sn = self._sn
        self._map[sn] = value
        self._weak[id(value)] = sn
        return lambda: self._map.pop(sn, None) is not None

    def delete(self, value: Any) -> bool:
        """O(1) delete by value identity."""
        sn = self._weak.pop(id(value), None)
        if sn is None:
            return False
        self._map.pop(sn, None)
        return True

    def clear(self) -> list[Any]:
        """Clear and return values in reverse order (LIFO dispose)."""
        values = list(reversed(self._map.values()))
        self._map.clear()
        self._weak.clear()
        return values

    def __iter__(self) -> iter:  # type: ignore[type-arg]
        return iter(list(self._map.values()))
