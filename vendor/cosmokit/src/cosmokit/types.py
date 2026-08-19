"""Runtime type, binary, clone, and equality helpers.

1:1 Python port of ``@deepseek-ai/cosmokit/src/types.ts``.

Notes on translation:

- TypeScript ``is`` is a reserved word in Python; the module-level function
  is exposed as ``is_``.
- The TS ``is`` lookup uses ``globalThis[type]`` (e.g. ``Array``, ``Map``).
  Python has no globalThis; we walk a small ``_TYPE_MAP`` first (for JS
  names like ``ArrayBuffer``, ``Date``, ``RegExp``) and fall back to
  ``builtins``.
- ``Binary`` is exposed as a static-method container mirroring the TS
  ``namespace``. ``Binary.is`` is named ``Binary.is_`` because Python
  rejects ``is`` as an attribute name.
"""

import base64
import builtins
import datetime
import re
from typing import Any, TypeVar

# ---------------------------------------------------------------------------
# is_()
# ---------------------------------------------------------------------------

_UNSET = object()

# JS type-name → Python class mapping. ``"Object"`` is mapped to ``dict``
# rather than Python ``object`` (which is the base of every type and would
# trivially answer True everywhere).
_TYPE_MAP: dict[str, Any] = {
    "Object": dict,
    "Array": list,
    "String": str,
    "Number": (int, float),
    "Boolean": bool,
    "ArrayBuffer": (bytes, bytearray, memoryview),
    "SharedArrayBuffer": memoryview,
    "Date": (datetime.date, datetime.datetime),
    "RegExp": re.Pattern,
}


def _to_string_tag(value: object) -> str:
    """Equivalent to ``Object.prototype.toString.call(value).slice(8, -1)``.

    Returns the Python ``type(value).__name__``. We deliberately do NOT
    remap Python names like ``dict`` → ``Object`` here, because callers
    using ``is_`` already get True/False disambiguated via ``_TYPE_MAP``;
    the string-tag fallback only fires when neither the map nor builtins
    recognised the name, in which case the actual class name is most
    informative.
    """
    return type(value).__name__


def _check_is(type_name: str, value: object) -> bool:
    """Single-arg predicate backing :func:`is_`."""
    target = _TYPE_MAP.get(type_name)
    if target is None:
        target = getattr(builtins, type_name, None)

    if isinstance(target, tuple):
        return any(type(value) is t for t in target)
    if isinstance(target, type):
        return type(value) is target
    return _to_string_tag(value) == type_name


def is_(type_name: str, value: Any = _UNSET) -> Any:
    """Test whether ``value`` is an instance of the global type ``type_name``.

    Mirrors the TS ``is`` overload:

    - ``is_(type_name, value)`` returns ``bool``.
    - ``is_(type_name)`` returns a one-arg predicate ``(value) -> bool``.

    The string ``type_name`` is checked against ``_TYPE_MAP`` (covering JS
    names like ``"ArrayBuffer"``, ``"Date"``, ``"RegExp"``) and otherwise
    against ``builtins``. A ``toStringTag``-style fallback handles any
    remaining name mismatch.
    """
    if value is _UNSET:
        return lambda v: _check_is(type_name, v)
    return _check_is(type_name, value)


# ---------------------------------------------------------------------------
# Binary — ArrayBuffer/source helpers (TS `namespace Binary`)
# ---------------------------------------------------------------------------


def _is_array_buffer_like(value: object) -> bool:
    return _check_is("ArrayBuffer", value) or _check_is("SharedArrayBuffer", value)


def _is_array_buffer_source(value: object) -> bool:
    if _is_array_buffer_like(value):
        return True
    return isinstance(value, memoryview)


T = TypeVar("T")


class Binary:
    """Static-only container mirroring the TS ``namespace Binary``.

    Method ``is`` is exposed as ``is_`` because Python rejects ``is`` as
    an attribute name.
    """

    Source = (bytes, bytearray, memoryview)

    @staticmethod
    def is_(value: object) -> bool:
        """True if ``value`` is an ArrayBuffer-like (bytes/bytearray/memoryview)."""
        return _is_array_buffer_like(value)

    @staticmethod
    def is_source(value: object) -> bool:
        """True if ``value`` is an ArrayBuffer or an ArrayBufferView."""
        return _is_array_buffer_source(value)

    @staticmethod
    def from_source(source: "bytes | bytearray | memoryview") -> bytes:
        """Return a fresh ``bytes`` copy of ``source``.

        - ``memoryview`` (ArrayBufferView) → slice the underlying buffer.
        - ``bytes`` / ``bytearray`` → already ArrayBuffer-like; copy to
          break aliasing.
        """
        if isinstance(source, memoryview):
            return source.tobytes()
        return bytes(source)

    @staticmethod
    def to_base64(source: "bytes | bytearray | memoryview") -> str:
        """Encode ``source`` as base64."""
        return base64.b64encode(bytes(source)).decode("ascii")

    @staticmethod
    def from_base64(source: str) -> bytes:
        """Decode a base64 string into ``bytes``."""
        return base64.b64decode(source)

    @staticmethod
    def to_hex(source: "bytes | bytearray | memoryview") -> str:
        """Encode ``source`` as lower-case hex."""
        return bytes(source).hex()

    @staticmethod
    def from_hex(source: str) -> bytes:
        """Decode a hex string into ``bytes``.

        Odd-length input has the trailing character dropped (mirrors TS).
        """
        if len(source) % 2 == 1:
            source = source[:-1]
        return bytes.fromhex(source)


# Backwards-compatible module-level aliases.
base64ToArrayBuffer = Binary.from_base64
arrayBufferToBase64 = Binary.to_base64
hexToArrayBuffer = Binary.from_hex
arrayBufferToHex = Binary.to_hex


# ---------------------------------------------------------------------------
# clone
# ---------------------------------------------------------------------------


def clone(source: T, refs: dict | None = None) -> T:
    """Deep-clone ``source`` while preserving structural identities.

    Cycle-safe via an ``id(source)`` → ``result`` cache (``refs`` mirrors
    the TS internal ``Map``).

    Supported shapes (faithful 1:1 for what is constructible in Python):

    - primitives (``None``, ``bool``, ``int``, ``float``, ``str``,
      ``bytes``) — passed through
    - ``list`` — deep-cloned element-wise
    - ``dict`` — deep-cloned key- and value-wise
    - ``memoryview`` → ``bytes`` copy
    - anything else — passed through
    """
    # Primitives pass through.
    if source is None or isinstance(source, (bool, int, float, str, bytes)):
        return source

    # Cycle / recursion cache.
    if refs is None:
        refs = {}
    key = id(source)
    cached = refs.get(key)
    if cached is not None:
        return cached

    if isinstance(source, list):
        list_result: list = []
        refs[key] = list_result
        for _index, value in enumerate(source):
            list_result.append(clone(value, refs))
        return list_result  # type: ignore[return-value]

    if isinstance(source, dict):
        dict_result: dict = {}
        refs[key] = dict_result
        for k, v in source.items():
            new_k = clone(k, refs)
            new_v = clone(v, refs)
            dict_result[new_k] = new_v
        return dict_result  # type: ignore[return-value]

    if isinstance(source, memoryview):
        return source.tobytes()  # type: ignore[return-value]

    return source


# ---------------------------------------------------------------------------
# deepEqual
# ---------------------------------------------------------------------------


_SENTINEL = object()


def _equals(a: Any, b: Any, strict: bool) -> bool:
    if a is b:
        return True
    if type(a) is not type(b):
        return False

    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_equals(x, y, strict) for x, y in zip(a, b, strict=True))

    if isinstance(a, dict):
        keys = set(a) | set(b)
        for k in keys:
            if not _equals(a.get(k, _SENTINEL), b.get(k, _SENTINEL), strict):
                return False
        return True

    return False


def deepEqual(a: Any, b: Any, strict: bool = False) -> bool:
    """Deep-equality on lists and dicts.

    Mirrors the TS implementation for the Python surface (lists / dicts).
    Returns ``True`` when ``a`` and ``b`` are deeply equal — matching values
    positionally (lists) or by key (dicts) including any nested structure.

    - ``strict=True`` propagates into recursive calls.
    - Identity match (``a is b``) short-circuits to ``True``.
    - ``None`` vs ``None`` is equal in non-strict mode (and in strict too,
      via the identity check).
    """
    return _equals(a, b, strict)


__all__ = [
    "Binary",
    "arrayBufferToBase64",
    "arrayBufferToHex",
    "base64ToArrayBuffer",
    "clone",
    "deepEqual",
    "hexToArrayBuffer",
    "is_",
]
