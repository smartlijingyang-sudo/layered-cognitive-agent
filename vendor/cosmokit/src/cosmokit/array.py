"""Array set and normalization helpers.

1:1 Python port of ``@deepseek-ai/cosmokit/src/array.ts``.
"""

from typing import TypeVar

from cosmokit.misc import isNullable

S = TypeVar("S")
T = TypeVar("T")


def contain(array1: list | tuple, array2: list | tuple) -> bool:
    """Return True when every item in ``array2`` is present in ``array1``."""
    return all(item in array1 for item in array2)


def intersection(array1: list[T] | tuple[T, ...], array2: list[T] | tuple[T, ...]) -> list[T]:
    """Return items present in both arrays, preserving ``array1`` order/multiplicity."""
    return [item for item in array1 if item in array2]


def difference(array1: list[S] | tuple[S, ...], array2: list | tuple) -> list[S]:
    """Return items from ``array1`` that are not in ``array2``."""
    return [item for item in array1 if item not in array2]


def union(array1: list[T] | tuple[T, ...], array2: list[T] | tuple[T, ...]) -> list[T]:
    """Return the set-union while preserving first-occurrence order."""
    return list(dict.fromkeys([*array1, *array2]))


def deduplicate(array: list[T] | tuple[T, ...]) -> list[T]:
    """Remove duplicates while preserving first-occurrence order."""
    return list(dict.fromkeys(array))


def remove(list_: list[T] | None, item: T) -> bool:
    """Remove the first matching item; return whether anything was removed.

    Mirrors the TS optional-chain ``list?.indexOf(item)``: when ``list_`` is
    ``None`` or the item is absent, the call returns ``False`` without raising.
    """
    if list_ is None:
        return False
    try:
        index = list_.index(item)
    except ValueError:
        return False
    del list_[index]
    return True


def make_array(source: None | T | list[T] | tuple[T, ...]) -> list[T]:
    """Normalize ``None`` / scalar / sequence input to a list.

    Mirrors ``Array.isArray(source) ? source : isNullable(source) ? [] : [source]``.
    """
    if isinstance(source, (list, tuple)):
        return list(source)
    if isNullable(source):
        return []
    return [source]  # type: ignore[return-value]


__all__ = [
    "contain",
    "deduplicate",
    "difference",
    "intersection",
    "make_array",
    "remove",
    "union",
]
