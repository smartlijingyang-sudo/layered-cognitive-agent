"""Shared utility types and object/dict helpers.

1:1 Python port of ``@deepseek-ai/cosmokit/src/misc.ts``.

Notes on translation:

- ``isNullable`` matches only Python ``None``. ``undefined`` does not exist
  in Python; ``void`` is folded into ``None``.
- ``isPlainObject`` mirrors the JS formula ``truthy && typeof === 'object'
  && !Array.isArray``. In Python that becomes ``object-like AND not a list``.
- The TS type aliases (``Dict``, ``Get``, ``Extract``, ``MaybeArray``,
  ``Promisify``, ``Awaitable``, ``Intersect``) are runtime no-ops in Python
  — only ``Dict`` is exposed as a ``TypeAlias`` for re-export symmetry.
- ``defineProperty`` uses ``object.__setattr__`` to bypass Python's
  ``__setattr__`` override (mirrors ``Object.defineProperty`` ignoring
  JS setters).
"""

from typing import Any, TypeAlias

# ---------------------------------------------------------------------------
# Public-surface type aliases
# ---------------------------------------------------------------------------

# ``Dict[K, V]`` mirrors the TS export ``Dict<T, K>``. Python already has
# ``dict[K, V]``; the alias is kept so callers can ``from cosmokit.misc
# import Dict`` and obtain the same shape.
Dict: TypeAlias = dict  # type: ignore[misc]

# ``Get`` mirrors the TS ``K extends keyof T ? T[K] : never``. In Python
# the lookup is dynamic; we expose it as a marker alias only.
Get: TypeAlias = Any

MaybeArray: TypeAlias = Any  # in Python we don't expose a runtime union.

__all__ = [
    "Dict",
    "Get",
    "MaybeArray",
    "defineProperty",
    "filterKeys",
    "isNonNullable",
    "isNullable",
    "isPlainObject",
    "mapValues",
    "noop",
    "omit",
    "pick",
    "valueMap",
]


# ---------------------------------------------------------------------------
# noop
# ---------------------------------------------------------------------------


def noop(*args: Any, **kwargs: Any) -> None:
    """No-op callback. Accepts any positional/keyword arguments, returns ``None``."""
    return


# ---------------------------------------------------------------------------
# Nullish / plain-object predicates
# ---------------------------------------------------------------------------


def isNullable(value: Any) -> bool:
    """Return True when ``value`` is ``None`` (Python's nullish analogue)."""
    return value is None


def isNonNullable(value: Any) -> bool:
    """Return True when ``value`` is not ``None``."""
    return value is not None


_PRIMITIVE_TYPES: tuple[type, ...] = (
    type(None),
    str,
    bytes,
    bytearray,
    int,
    float,
    bool,
    tuple,
    type,
    range,
)


def isPlainObject(data: Any) -> bool:
    """Return True for a non-primitive, non-list object.

    Mirrors ``truthy && typeof === 'object' && !Array.isArray``. The Python
    empty containers (``{}``, ``[]``) are falsy — the literal ``!data``
    guard would falsely reject an empty dict (a perfectly valid plain
    object), so we special-case ``None`` and treat empty containers as
    "shape-OK".
    """
    if data is None:
        return False
    if isinstance(data, list):
        return False
    return not isinstance(data, _PRIMITIVE_TYPES)


# ---------------------------------------------------------------------------
# Dict helpers
# ---------------------------------------------------------------------------


def filterKeys(obj: dict, predicate: Any) -> dict:
    """Filter dict entries with ``predicate(key, value) -> bool``.

    Mirrors ``Object.fromEntries(Object.entries(o).filter(...))``.
    """
    return {k: v for k, v in obj.items() if predicate(k, v)}


def mapValues(obj: dict, transform: Any) -> dict:
    """Map dict values, preserving keys.

    Mirrors ``Object.fromEntries(Object.entries(o).map(...))``.
    The transform receives ``(value, key)`` (the TS contract).
    """
    return {k: transform(v, k) for k, v in obj.items()}


# Backwards-compatible alias matching the TS ``valueMap`` export.
valueMap = mapValues


# ---------------------------------------------------------------------------
# pick / omit
# ---------------------------------------------------------------------------


def pick(source: Any, keys: Any = None, forced: bool = False) -> dict:
    """Pick selected keys from a dict, returning a new dict.

    Mirrors the TS signature:

    - ``pick(source)`` returns a shallow copy of ``source``.
    - ``pick(source, keys)`` keeps only the listed keys whose values are
      not ``None`` in ``source``.
    - ``pick(source, keys, forced=True)`` includes missing keys, with
      their value set to ``None`` (TS's ``undefined`` analogue).

    ``source`` is treated as a mapping for ``source[key]`` access; iterating
    ``keys`` accepts any iterable.
    """
    if keys is None:
        return dict(source)

    result: dict = {}
    for key in keys:
        try:
            value = source[key]
        except (KeyError, TypeError, IndexError, AttributeError):
            if forced:
                result[key] = None
            continue
        if forced or value is not None:
            result[key] = value
    return result


def omit(source: Any, keys: Any = None) -> dict:
    """Omit selected keys from a shallow dict copy.

    Mirrors the TS ``Reflect.deleteProperty`` loop.
    """
    if keys is None:
        return dict(source)
    result = dict(source)
    for key in keys:
        result.pop(key, None)
    return result


# ---------------------------------------------------------------------------
# defineProperty
# ---------------------------------------------------------------------------


def defineProperty(obj: Any, key: str, value: Any) -> Any:
    """Set ``key=value`` on ``obj`` and return ``obj``.

    Mirrors ``Object.defineProperty(obj, key, { writable: true, value, enumerable: false })``:

    - bypasses any ``__setattr__`` override (via ``object.__setattr__``)
    - non-enumerability on the JS side has no Python equivalent; attributes
      always appear in ``vars(obj)``.
    """
    object.__setattr__(obj, key, value)
    return obj
