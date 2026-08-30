"""Recursive immutable containers for compile-time Profile facts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class _FrozenMapping(dict[str, Any]):
    """Dict-compatible container that rejects mutation after projection."""

    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("profile projection values are immutable")

    def __deepcopy__(self, _memo: dict[int, object]) -> _FrozenMapping:
        return self

    __setitem__ = _immutable
    __delitem__ = _immutable
    __ior__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable


class _FrozenList(list[Any]):
    """List-compatible container that rejects mutation after projection."""

    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("profile projection values are immutable")

    def __deepcopy__(self, _memo: dict[int, object]) -> _FrozenList:
        return self

    __setitem__ = _immutable
    __delitem__ = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable


def freeze_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Recursively freeze one profile fact without changing its readable shape."""
    return _FrozenMapping({key: _freeze_value(value) for key, value in values.items()})


def _freeze_value(value: Any) -> Any:
    """Turn mutable declaration containers into immutable plan-fact values."""
    if isinstance(value, Mapping):
        return freeze_mapping(value)
    if isinstance(value, list):
        return _FrozenList(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return value


__all__ = ["freeze_mapping"]
