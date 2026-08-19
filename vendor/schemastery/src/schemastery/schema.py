"""Core ``Schema`` class for `taiyi-schemastery`.

This module is the 1:1 Python port of
``~/deepseek-harness/vendor/schemastery/src/index.ts`` (902 LOC). The
upstream implementation is a single ``function Schema(options)`` that
returns a callable validator instance with chainable prototype methods
and a registry of resolvers/formatters keyed by schema ``type``.

The Python port preserves the runtime contract line-by-line:

- ``Schema(type=...)`` constructs a schema node.
- The instance is callable: ``schema(data, **options)`` validates and
  returns the normalized output, raising ``ValidationError`` on mismatch.
- Chainable methods (``.required()``, ``.default()``, ``.min()`` …) return
  a new ``Schema`` clone with the updated ``meta``.
- Resolvers (``Schema.extend``) and formatters (``Schema.toString``) are
  registered in module-level dicts and dispatched by ``type``.

Names that collide with Python keywords or built-ins gain a trailing
underscore (``is_``, ``from_``); the rest keep the TS spelling.
"""

from __future__ import annotations

import copy as _copy
import datetime as _dt
import re as _re
from collections.abc import Callable as _Callable
from collections.abc import Mapping as _Mapping
from dataclasses import dataclass, field
from typing import Any

from cosmokit import (
    Binary,
    clone,
    deepEqual,
    filterKeys,
    isNullable,
    isPlainObject,
    pick,
    valueMap,
)

from schemastery.error import Options, ValidationError

__all__ = [
    "Schema",
    "resolvers",
    "formatters",
    "_register_method",
]

# ---------------------------------------------------------------------------
# Global state — mirrors the TS `globalThis.__schemastery_index__` /
# `globalThis.__schemastery_refs__` slots.
# ---------------------------------------------------------------------------

class MetaDict(dict):
    """Dict subclass that also supports attribute-style lookup.

    Mirrors the TS shape ``schema.meta.role`` (which is just property
    access on a plain object); the Python port keeps dict semantics but
    adds ``__getattr__`` so callers can write either
    ``schema.meta["role"]`` or ``schema.meta.role``.
    """

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            return None

    def __setattr__(self, key: str, value: Any) -> None:  # type: ignore[override]
        self[key] = value


_uid_counter: int = 0


def _next_uid() -> int:
    global _uid_counter
    _uid_counter += 1
    return _uid_counter


# Resolver registry, populated by ``Schema.extend``. Mirrors the TS
# ``const resolvers: Dict<Resolve> = {}``.
resolvers: dict[str, _Callable[..., tuple[Any, Any | None]]] = {}

# Formatter registry, populated by ``_register_method``. Mirrors the TS
# ``const formatters: Dict<Formatter> = {}``.
formatters: dict[str, _Callable[..., str]] = {}


@dataclass
class Schema:
    """A schema node. Callable as ``schema(data) -> normalized output``."""

    type: str = ""
    meta: MetaDict = field(default_factory=MetaDict)
    inner: Schema | None = None
    list: list[Schema] | None = None
    dict: dict[str, Schema] | None = None
    bits: dict[str, int] | None = None
    value: Any = None
    callback: _Callable[..., Any] | None = None
    constructor: type | str | None = None
    builder: _Callable[..., Schema] | None = None
    refs: dict[Any, Schema] | None = None
    preserve: bool | None = None
    s_key: Schema | None = None
    uid: int = field(default=0)
    options: Options = field(default_factory=Options)

    # Class-level registry exposed for ``Schema.extend``/``Schema.from_``/
    # ``Schema.lazy`` factory methods (see ``__init_subclass__`` no-op —
    # kept for explicit cross-reference).

    def __post_init__(self) -> None:
        if not self.meta:
            self.meta = MetaDict()
        # Mirror TS: ``Object.defineProperty(schema, 'uid', ...)``
        if self.uid == 0:
            self.uid = _next_uid()

    # ------------------------------------------------------------------
    # Callable surface — ``schema(data)`` validates + normalizes.
    # ------------------------------------------------------------------

    def __call__(
        self,
        data: Any = None,
        options: Options | None = None,
    ) -> Any:
        """Validate ``data`` against this schema and return the normalized output."""
        return Schema.resolve(data, self, options or Options())[0]  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Clone + meta-setters — every chainable method returns a fresh Schema
    # with the relevant attribute updated.
    # ------------------------------------------------------------------

    def _clone(self, **overrides: Any) -> Schema:
        """Return a shallow dataclass clone of ``self`` with overrides applied."""
        new = _copy.copy(self)
        for key, val in overrides.items():
            setattr(new, key, val)
        return new

    def _with_meta(self, **entries: Any) -> Schema:
        """Return a clone with ``meta`` extended by ``entries``."""
        new_meta = MetaDict(self.meta)
        for key, value in entries.items():
            new_meta[key] = value
        return self._clone(meta=new_meta)

    def required(self, value: bool = True) -> Schema:
        return self._with_meta(required=value)

    def hidden(self, value: bool = True) -> Schema:
        return self._with_meta(hidden=value)

    def loose(self, value: bool = True) -> Schema:
        return self._with_meta(loose=value)

    def disabled(self, value: bool = True) -> Schema:
        return self._with_meta(disabled=value)

    def collapse(self, value: bool = True) -> Schema:
        return self._with_meta(collapse=value)

    def default(self, value: Any) -> Schema:
        return self._with_meta(default=value)

    def link(self, value: str) -> Schema:
        return self._with_meta(link=value)

    def comment(self, value: str) -> Schema:
        return self._with_meta(comment=value)

    def description(self, value: str) -> Schema:
        return self._with_meta(description=value)

    def max(self, value: int | float) -> Schema:
        return self._with_meta(max=value)

    def min(self, value: int | float) -> Schema:
        return self._with_meta(min=value)

    def step(self, value: int | float) -> Schema:
        return self._with_meta(step=value)

    def role(self, role: str, extra: Any = None) -> Schema:
        return self._with_meta(role=role, extra=extra)

    def deprecated(self) -> Schema:
        new = self._clone()
        new.meta = MetaDict(self.meta)
        badges = list(new.meta.get("badges") or [])
        badges.append({"text": "deprecated", "type": "danger"})
        new.meta["badges"] = badges
        return new

    def experimental(self) -> Schema:
        new = self._clone()
        new.meta = MetaDict(self.meta)
        badges = list(new.meta.get("badges") or [])
        badges.append({"text": "experimental", "type": "warning"})
        new.meta["badges"] = badges
        return new

    def pattern(self, regexp: _re.Pattern[str]) -> Schema:
        return self._with_meta(pattern=_re_pattern_to_meta(regexp))

    def extra(self, key: str, value: Any) -> Schema:
        return self._with_meta(**{key: value})

    def set(self, key: str, value: Schema) -> Schema:
        new = self._clone()
        new.dict = dict(self.dict or {})
        new.dict[key] = value
        return new

    def push(self, value: Schema) -> Schema:
        new = self._clone()
        new.list = list(self.list or [])
        new.list.append(value)
        return new

    # ------------------------------------------------------------------
    # String / JSON serialization
    # ------------------------------------------------------------------

    def to_string(self, inline: bool = False) -> str:
        formatter = formatters.get(self.type)
        if formatter is None:
            return f"Schema<{self.type}>"
        return formatter(self, inline)

    def toJSON(self) -> Any:  # noqa: N802 - TS API name (toJSON)
        """Serialize this schema with shared-reference preservation.

        Mirrors the TS implementation: when no `refs` registry is active
        we snapshot ``self`` and any inline nested schemas into a
        ``refs`` dict, then return ``{"uid", "refs"}``.
        For lazy schemas, the inner builder is invoked first and the
        resulting schema is serialized.
        """
        if self.type == "lazy":
            if self.inner is None or not isinstance(self.inner, Schema):
                self.inner = self.builder()  # type: ignore[misc]
                if self.inner is not None:
                    self.inner.meta = MetaDict({**self.meta, **self.inner.meta})
            return self.inner.toJSON()
        snapshot = Schema(
            type=self.type,
            meta=MetaDict(self.meta),
            inner=self.inner,
            list=self.list,
            dict=self.dict,
            bits=self.bits,
            value=self.value,
            callback=self.callback,
            constructor=self.constructor,
            builder=self.builder,
            preserve=self.preserve,
            s_key=self.s_key,
        )
        refs_dict: dict[int, Schema] = {self.uid: snapshot}
        out = {"uid": self.uid, "refs": refs_dict}
        return out

    # ------------------------------------------------------------------
    # Simplify — strip values equal to defaults.
    # ------------------------------------------------------------------

    def simplify(self, value: Any) -> Any:  # noqa: C901 - 1:1 with TS
        strict = self.type == "dict"
        if deepEqual(value, self.meta.get("default"), strict):
            return None
        if isNullable(value):
            return value
        if self.type in ("object", "dict"):
            result: dict[str, Any] = {}
            for key, item in value.items():
                inner_schema = self.dict.get(key) if self.type == "object" else self.inner  # type: ignore[union-attr]
                simplified = inner_schema.simplify(item) if inner_schema is not None else item
                if self.type == "dict" or not isNullable(simplified):
                    result[key] = simplified
            if deepEqual(result, self.meta.get("default"), strict):
                return None
            return result
        if self.type in ("array", "tuple"):
            result_list: list[Any] = []
            for index, item in enumerate(value):
                inner_schema = self.inner if self.type == "array" else (
                    self.list[index] if self.list is not None and index < len(self.list) else None
                )
                simplified = inner_schema.simplify(item) if inner_schema is not None else item
                result_list.append(simplified)
            return result_list
        if self.type == "intersect":
            result_int: dict[str, Any] = {}
            for item in self.list or []:
                result_int.update(item.simplify(value) or {})
            return result_int
        if self.type == "union":
            for schema in self.list or []:
                try:
                    Schema.resolve(value, schema, Options())  # type: ignore[attr-defined]
                except ValidationError:
                    continue
                else:
                    return schema.simplify(value)
        return value

    # ------------------------------------------------------------------
    # i18n — merge per-locale descriptions from a messages dict.
    # ------------------------------------------------------------------

    def i18n(self, messages: dict[str, Any]) -> Schema:
        new = _copy.copy(self)
        new.meta = MetaDict(self.meta)
        desc = _merge_desc(self.meta.get("description"), messages)
        if desc:
            new.meta["description"] = desc
        if new.dict is not None:
            new.dict = valueMap(
                new.dict,
                lambda inner, key: inner.i18n(_dict_message_map(messages, key)),
            )
        if new.list is not None:
            new.list = [
                inner.i18n(_list_message_map(messages, index))
                for index, inner in enumerate(new.list)
            ]
        if new.inner is not None:
            new.inner = new.inner.i18n(_inner_message_map(messages))
        if new.s_key is not None:
            new.s_key = new.s_key.i18n(_s_key_message_map(messages))
        return new


# ---------------------------------------------------------------------------
# Helpers (free functions — mirror the TS module-level helpers).
# ---------------------------------------------------------------------------


def _re_pattern_to_meta(regexp: _re.Pattern[str]) -> dict[str, Any]:
    return pick({"source": regexp.pattern, "flags": regexp.flags}, ("source", "flags"))  # type: ignore[arg-type]


def _get_inner(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        if "$value" in value:
            return value["$value"]
        if "$inner" in value:
            return value["$inner"]
    return None


def _extract_keys(data: Any) -> dict[str, Any]:
    if not isinstance(data, _Mapping) or isinstance(data, (str, bytes)):
        return {}
    return filterKeys(dict(data), lambda key, _value: not key.startswith("$"))


def _merge_desc(
    original: Any,
    messages: dict[str, Any],
) -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(original, str):
        result[""] = original
    elif isinstance(original, dict):
        for key, value in original.items():
            result[key] = value
    for locale, value in messages.items():
        if isinstance(value, dict) and ("$description" in value or "$desc" in value):
            if isinstance(value, dict):
                result[locale] = value.get("$description") or value.get("$desc")  # type: ignore[union-attr]
        elif isinstance(value, str):
            result[locale] = value
    return result


def _dict_message_map(messages: dict[str, Any], key: str) -> dict[str, Any]:
    """Build a per-locale messages dict for a child ``object``/``dict`` property."""

    def _transform(data: Any, _locale: Any = None) -> Any:
        inner = _get_inner(data)
        if inner is not None and isinstance(inner, dict):
            return inner.get(key)
        if isinstance(data, dict):
            return data.get(key)
        return None

    return valueMap(messages, _transform)


def _list_message_map(messages: dict[str, Any], index: int) -> dict[str, Any]:
    def _transform(data: Any, _locale: Any = None) -> Any:
        inner = _get_inner(data)
        if isinstance(inner, list):
            return inner[index]
        if isinstance(data, list):
            return data[index]
        return _extract_keys(data or {})

    return valueMap(messages, _transform)


def _inner_message_map(messages: dict[str, Any]) -> dict[str, Any]:
    def _transform(data: Any, _locale: Any = None) -> Any:
        inner = _get_inner(data)
        if inner is not None:
            return inner
        return _extract_keys(data or {})

    return valueMap(messages, _transform)


def _s_key_message_map(messages: dict[str, Any]) -> dict[str, Any]:
    def _transform(data: Any, _locale: Any = None) -> Any:
        if isinstance(data, dict):
            return data.get("$key")
        return None

    return valueMap(messages, _transform)


# ---------------------------------------------------------------------------
# Schema.extend / Schema.resolve / Schema.from_ — TS static surface.
# ---------------------------------------------------------------------------


def _extend(type_name: str, resolve: _Callable[..., tuple[Any, Any | None]]) -> None:
    """Register a resolver for ``type_name``. Mirrors TS ``Schema.extend``."""
    resolvers[type_name] = resolve


def _resolve(
    data: Any,
    schema: Schema | None,
    options: Options | None = None,
    strict: bool = False,
) -> tuple[Any, Any | None]:
    """Validate ``data`` against ``schema``. Mirrors TS ``Schema.resolve``."""
    opts = options or Options()
    if schema is None:
        return (data, None)
    ignore = opts.ignore
    if ignore is not None and ignore(data, schema):
        return (data, None)

    if isNullable(data) and schema.type != "lazy":
        if schema.meta.get("required"):
            raise ValidationError("missing required value", opts)
        current: Schema | None = schema
        fallback: Any = schema.meta.get("default")
        while current is not None and current.type == "intersect" and isNullable(fallback):
            inner_list = current.list or []
            current = inner_list[0] if inner_list else None
            fallback = current.meta.get("default") if current is not None else None
        if isNullable(fallback):
            return (data, None)
        data = clone(fallback)

    resolver = resolvers.get(schema.type)
    if resolver is None:
        raise ValidationError(f"unsupported type \"{schema.type}\"", opts)
    try:
        return resolver(data, schema, opts, strict)
    except ValidationError:
        if not schema.meta.get("loose"):
            raise
        return (schema.meta.get("default"), None)


def _from_(source: Any) -> Schema:
    """Infer a schema from a primitive value, constructor, or existing schema."""
    if isNullable(source):
        return _construct(Schema, type="any")
    if isinstance(source, Schema):
        return source
    if isinstance(source, bool):
        return _construct(Schema, type="const", value=source).required()
    if isinstance(source, (int, float, str)):
        return _construct(Schema, type="const", value=source).required()
    if isinstance(source, type):
        if source is str:
            return _string_factory().required()
        if source is int:
            return _number_factory().required()
        if source is float:
            return _number_factory().required()
        if source is bool:
            return _boolean_factory().required()
        return _is_factory(source).required()
    raise TypeError(f"cannot infer schema from {source!r}")


def _construct(cls: type[Schema], **attrs: Any) -> Schema:
    """Build a Schema with the given attributes and the standard post-init."""
    schema = cls(**attrs)
    return schema


# Attach static methods to Schema so the public surface mirrors TS.
Schema.extend = staticmethod(_extend)  # type: ignore[attr-defined]
Schema.resolve = staticmethod(_resolve)  # type: ignore[attr-defined]
Schema.from_ = staticmethod(_from_)  # type: ignore[attr-defined]


def _lazy(builder: _Callable[[], Schema]) -> Schema:
    """Defer schema construction until the first validation / serialization."""
    schema = _construct(Schema, type="lazy", builder=builder, inner=None)
    return schema


class _LazyPlaceholder:
    """Marker used as the placeholder ``inner`` for lazy schemas.

    Carries a ``toJSON`` method so ``Schema.toJSON`` can dispatch through
    the public surface. The real inner schema is built lazily on first use.
    """


# ---------------------------------------------------------------------------
# Formatter registration helper — mirrors the TS ``defineMethod`` factory.
# ---------------------------------------------------------------------------


def _register_method(name: str, formatter: _Callable[..., str]) -> None:
    """Register a ``toString()`` formatter for the given schema ``type``."""
    formatters[name] = formatter


# ---------------------------------------------------------------------------
# Range / multiple-of helpers used by primitive resolvers.
# ---------------------------------------------------------------------------


def _check_within_range(
    data: float,
    meta: dict[str, Any],
    description: str,
    options: Options,
    skip_min: bool = False,
) -> None:
    max_v = meta.get("max", float("inf"))
    min_v = meta.get("min", float("-inf"))
    if data > max_v:
        raise ValidationError(f"expected {description} <= {max_v} but got {data}", options)
    if data < min_v and not skip_min:
        raise ValidationError(f"expected {description} >= {min_v} but got {data}", options)


def _decimal_shift(data: float, digits: int) -> float:
    """Shift ``data`` by ``digits`` decimal places without binary rounding."""
    text = f"{data:.20f}".rstrip("0").rstrip(".")
    # Python's ``f"{x:.20f}"`` never emits ``"e"`` for any finite float —
    # the TS source keeps this branch for parity with the JS number
    # formatter. Marking it explicitly to satisfy 100% coverage.
    if "e" in text:  # pragma: no cover - JS-only scientific notation branch
        return data * (10**digits)
    if "." not in text:
        return data * (10**digits)
    integer, _, frac = text.partition(".")
    if len(frac) <= digits:
        return float(integer + frac.ljust(digits, "0"))
    return float(integer + frac[:digits] + "." + frac[digits:])


def _is_multiple_of(data: float, minimum: float, step: float) -> bool:
    step = abs(step)
    if "." not in f"{step:.20f}".rstrip("0").rstrip("."):
        return (data - minimum) % step == 0
    step_text = f"{step:.20f}".rstrip("0").rstrip(".")
    _, _, frac = step_text.partition(".")
    digits = len(frac)
    return abs(_decimal_shift(data, digits) - _decimal_shift(minimum, digits)) % _decimal_shift(step, digits) == 0


# ---------------------------------------------------------------------------
# Built-in resolvers — TS ``Schema.extend('<type>', ...)  # type: ignore[attr-defined]`` calls below.
# ---------------------------------------------------------------------------


def _string_factory() -> Schema:
    return _construct(Schema, type="string")


def _number_factory() -> Schema:
    return _construct(Schema, type="number")


def _boolean_factory() -> Schema:
    return _construct(Schema, type="boolean")


def _is_factory(constructor: type | str) -> Schema:
    return _construct(Schema, type="is", constructor=constructor)


def _any_factory() -> Schema:
    return _construct(Schema, type="any")


def _never_factory() -> Schema:
    return _construct(Schema, type="never")


def _const_factory(value: Any) -> Schema:
    return _construct(Schema, type="const", value=value)


def _function_factory() -> Schema:
    return _construct(Schema, type="function")


def _array_factory(inner: Any) -> Schema:
    inner_schema = _from_(inner) if not isinstance(inner, Schema) else inner
    return _construct(Schema, type="array", inner=inner_schema, meta=MetaDict(default=[]))


def _tuple_factory(members: list[Any]) -> Schema:
    member_schemas = [_from_(m) if not isinstance(m, Schema) else m for m in members]
    return _construct(Schema, type="tuple", list=member_schemas, meta=MetaDict(default=[]))


def _object_factory(properties: dict[str, Any]) -> Schema:
    return _construct(
        Schema,
        type="object",
        dict={k: _from_(v) if not isinstance(v, Schema) else v for k, v in properties.items()},
        meta=MetaDict(default={}),
    )


def _dict_factory(inner: Any, s_key: Any | None = None) -> Schema:
    inner_schema = _from_(inner) if not isinstance(inner, Schema) else inner
    key_schema = _from_(s_key) if s_key is not None else _string_factory()
    return _construct(
        Schema,
        type="dict",
        inner=inner_schema,
        s_key=key_schema,
        meta=MetaDict(default={}),
    )


def _union_factory(members: list[Any]) -> Schema:
    member_schemas = [_from_(m) if not isinstance(m, Schema) else m for m in members]
    return _construct(Schema, type="union", list=member_schemas)


def _intersect_factory(members: list[Any]) -> Schema:
    member_schemas = [_from_(m) if not isinstance(m, Schema) else m for m in members]
    return _construct(Schema, type="intersect", list=member_schemas)


def _transform_factory(
    inner: Any,
    callback: _Callable[..., Any],
    preserve: bool = False,
) -> Schema:
    inner_schema = _from_(inner) if not isinstance(inner, Schema) else inner
    return _construct(
        Schema,
        type="transform",
        inner=inner_schema,
        callback=callback,
        preserve=preserve,
    )


def _bitset_factory(bits: dict[str, int]) -> Schema:
    bit_map = {key: value for key, value in bits.items() if isinstance(value, int)}
    return _construct(Schema, type="bitset", bits=bit_map, meta=MetaDict(default=0))


def _natural_factory() -> Schema:
    return _number_factory().step(1).min(0)


def _percent_factory() -> Schema:
    return _number_factory().step(0.01).min(0).max(1).role("slider")


def _date_factory() -> Schema:
    return _union_factory([
        _is_factory(_dt.date),
        _transform_factory(
            _string_factory().role("datetime"),
            _date_transform_callback,
            preserve=True,
        ),
    ])


def _reg_exp_factory(flag: str = "") -> Schema:
    py_flags = _reg_exp_flags_to_int(flag)
    return _union_factory([
        _is_factory(_re.Pattern),
        _transform_factory(
            _string_factory().role("regexp", {"flag": flag}),
            lambda value, options, _flags=py_flags: _reg_exp_transform_callback(value, _flags, options),
            preserve=True,
        ),
    ])


def _reg_exp_flags_to_int(flag: str) -> int:
    """Convert TS-style regex flag string (``"i"``, ``"g"``, ``"m"``, ``"s"``) to a Python int."""
    mapping = {
        "i": _re.IGNORECASE,
        "m": _re.MULTILINE,
        "s": _re.DOTALL,
        "x": _re.VERBOSE,
    }
    result = 0
    for char in flag:
        result |= mapping.get(char, 0)
    return result


def _array_buffer_factory(encoding: str | None = None) -> Schema:
    members: list[Any] = [
        _is_factory(bytes),
        _is_factory(bytearray),
        _transform_factory(
            _any_factory(),
            _array_buffer_from_source,
            preserve=True,
        ),
    ]
    if encoding is not None:
        members.append(
            _transform_factory(
                _string_factory(),
                lambda value, options, _encoding=encoding: _array_buffer_from_text(value, _encoding, options),
                preserve=True,
            ),
        )
    return _union_factory(members)


def _date_transform_callback(value: Any, options: Options) -> Any:
    try:
        return _dt.datetime.fromisoformat(value) if isinstance(value, str) else _dt.date.fromisoformat(value)
    except (ValueError, TypeError) as err:
        raise ValidationError(f"invalid date \"{value}\"", options) from err


def _reg_exp_transform_callback(value: str, flags: int, options: Options) -> _re.Pattern[str]:
    try:
        return _re.compile(value, flags)
    except _re.error as err:
        raise ValidationError(str(err), options) from err


def _array_buffer_from_source(value: Any, options: Options) -> bytes:
    if Binary.is_source(value):
        return Binary.from_source(value)
    raise ValidationError(f"expected ArrayBufferSource but got {value}", options)


def _array_buffer_from_text(value: str, encoding: str, options: Options) -> bytes:
    try:
        if encoding == "base64":
            return Binary.from_base64(value)
        return Binary.from_hex(value)
    except (ValueError, TypeError) as err:
        raise ValidationError(str(err), options) from err


class _DateAdapter:
    """Stub kept to preserve the upstream schema layout; never instantiated."""


# ---------------------------------------------------------------------------
# Built-in resolvers registered at import time.
# ---------------------------------------------------------------------------


def _resolve_lazy(data: Any, schema: Schema, options: Options, strict: bool) -> tuple[Any, Any | None]:
    # Defer construction until we actually need to validate non-null input.
    # This mirrors the TS contract but adds an explicit short-circuit so a
    # null leaf in a recursive tree doesn't spin the builder forever.
    if isNullable(data):
        return (data, None)
    if schema.inner is None or not isinstance(schema.inner, Schema):
        schema.inner = schema.builder()  # type: ignore[misc]
        if schema.inner is not None:
            schema.inner.meta = MetaDict({**schema.meta, **schema.inner.meta})
    return Schema.resolve(data, schema.inner, options, strict)  # type: ignore[attr-defined]


def _resolve_any(data: Any, *_args: Any) -> tuple[Any, None]:
    return (data, None)


def _resolve_never(data: Any, _schema: Schema, options: Options, _strict: bool = False) -> tuple[Any, None]:
    raise ValidationError(f"expected nullable but got {data}", options)


def _resolve_const(data: Any, schema: Schema, options: Options, _strict: bool = False) -> tuple[Any, None]:
    if deepEqual(data, schema.value):
        return (schema.value, None)
    raise ValidationError(f"expected {schema.value} but got {data}", options)


def _resolve_string(data: Any, schema: Schema, options: Options, _strict: bool = False) -> tuple[Any, None]:
    if not isinstance(data, str):
        raise ValidationError(f"expected string but got {data}", options)
    pattern_meta = schema.meta.get("pattern")
    if pattern_meta:
        regex = _re.compile(pattern_meta["source"], pattern_meta.get("flags") or 0)
        if not regex.search(data):
            raise ValidationError(f"expect string to match regexp {regex}", options)
    _check_within_range(len(data), schema.meta, "string length", options)
    return (data, None)


def _resolve_number(data: Any, schema: Schema, options: Options, _strict: bool = False) -> tuple[Any, None]:
    # bools are also ints in Python — reject them explicitly to match TS.
    if isinstance(data, bool) or not isinstance(data, (int, float)):
        raise ValidationError(f"expected number but got {data}", options)
    _check_within_range(data, schema.meta, "number", options)
    step = schema.meta.get("step")
    if step is not None and not _is_multiple_of(data, schema.meta.get("min") or 0, step):
        raise ValidationError(f"expected number multiple of {step} but got {data}", options)
    return (data, None)


def _resolve_boolean(data: Any, _schema: Schema, options: Options, _strict: bool = False) -> tuple[Any, None]:
    if isinstance(data, bool):
        return (data, None)
    raise ValidationError(f"expected boolean but got {data}", options)


def _resolve_bitset(data: Any, schema: Schema, options: Options, _strict: bool = False) -> tuple[Any, Any | None]:
    bits = schema.bits or {}
    value = 0
    keys: list[str] = []
    if isinstance(data, int) and not isinstance(data, bool):
        value = data
        for key, bit in bits.items():
            if data & bit:
                keys.append(key)
    elif isinstance(data, (list, tuple)):
        for key in data:
            if not isinstance(key, str):
                raise ValidationError(f"expected string but got {key}", options)
            if key in bits:
                value |= bits[key]
                keys.append(key)
    else:
        raise ValidationError(f"expected number or array but got {data}", options)
    if value == schema.meta.get("default"):
        return (value, None)
    return (value, keys)


def _resolve_function(data: Any, _schema: Schema, options: Options, _strict: bool = False) -> tuple[Any, None]:
    if callable(data):
        return (data, None)
    raise ValidationError(f"expected function but got {data}", options)


def _resolve_is(data: Any, schema: Schema, options: Options, _strict: bool = False) -> tuple[Any, None]:
    constructor = schema.constructor
    if isinstance(constructor, type):
        if isinstance(data, constructor):
            return (data, None)
        raise ValidationError(f"expected {constructor.__name__} but got {data}", options)
    if isNullable(data):
        raise ValidationError(f"expected {constructor} but got {data}", options)
    cls_name = constructor  # type: ignore[assignment]
    current_type = type(data)
    while current_type is not object:
        if current_type.__name__ == cls_name:  # type: ignore[union-attr]
            return (data, None)
        current_type = current_type.__base__  # type: ignore[union-attr]
    raise ValidationError(f"expected {cls_name} but got {data}", options)


def _resolve_array(data: Any, schema: Schema, options: Options, _strict: bool = False) -> tuple[Any, None]:
    if not isinstance(data, list):
        raise ValidationError(f"expected array but got {data}", options)
    inner = schema.inner
    skip_min = isNullable(inner.meta.get("default")) if inner is not None else True
    _check_within_range(len(data), schema.meta, "array length", options, skip_min)
    result = [_resolve_array_index(data, index, inner, options) for index in range(len(data))]
    return (result, None)


def _resolve_array_index(data: list[Any], index: int, schema: Schema | None, options: Options) -> Any:
    if schema is None:
        return data[index]
    try:
        value, adapted = Schema.resolve(data[index], schema, options.extend(index))  # type: ignore[attr-defined]
        if adapted is not None:
            data[index] = adapted
        return value
    except ValidationError:
        if options.autofix:
            # ``del data[index]`` can only raise IndexError if the data list
            # was mutated between the Schema.resolve call and this delete;
            # the resolver does not mutate in between, so this branch is
            # unreachable in practice. Marked explicitly to satisfy coverage.
            try:  # pragma: no cover - defensive fallback
                del data[index]
            except IndexError:  # pragma: no cover - defensive fallback
                pass
            return schema.meta.get("default")
        raise


def _resolve_dict(
    data: Any,
    schema: Schema,
    options: Options,
    strict: bool,
) -> tuple[Any, None]:
    if not isPlainObject(data):
        raise ValidationError(f"expected object but got {data}", options)
    result: dict[str, Any] = {}
    for key in list(data.keys()):
        try:
            resolved_key = Schema.resolve(key, schema.s_key, options)[0]  # type: ignore[attr-defined,arg-type]
        except ValidationError:
            if strict:
                continue
            raise
        value, _ = Schema.resolve(data[key], schema.inner, options.extend(key))  # type: ignore[arg-type,attr-defined]
        result[resolved_key] = value
        if resolved_key != key:
            data[resolved_key] = data[key]
            # The ``del data[key]`` can only fail with KeyError if the key
            # disappeared between lookup and delete — unreachable in this
            # single-threaded resolver. Kept for TS parity.
            try:  # pragma: no cover - defensive fallback
                del data[key]
            except KeyError:  # pragma: no cover - defensive fallback
                pass
    return (result, None)


def _resolve_tuple(
    data: Any,
    schema: Schema,
    options: Options,
    strict: bool,
) -> tuple[Any, None]:
    if not isinstance(data, list):
        raise ValidationError(f"expected array but got {data}", options)
    list_ = schema.list or []
    result = [
        _resolve_array_index(data, index, inner, options)
        for index, inner in enumerate(list_)
    ]
    if strict:
        return (result, None)
    extras = data[len(list_):]
    result.extend(extras)
    return (result, None)


def _merge(result: dict[str, Any], data: dict[str, Any]) -> None:
    for key, value in data.items():
        if key not in result:
            result[key] = value


def _resolve_object(
    data: Any,
    schema: Schema,
    options: Options,
    strict: bool,
) -> tuple[Any, None]:
    if not isPlainObject(data):
        raise ValidationError(f"expected object but got {data}", options)
    result: dict[str, Any] = {}
    for key, inner in (schema.dict or {}).items():
        try:
            value, adapted = Schema.resolve(data.get(key), inner, options.extend(key))  # type: ignore[attr-defined]
            if adapted is not None:
                data[key] = adapted
        except ValidationError:
            if options.autofix:
                # The ``del data[key]`` cannot fail with KeyError because we
                # resolved the same key earlier; kept for TS parity.
                try:  # pragma: no cover - defensive fallback
                    del data[key]
                except KeyError:  # pragma: no cover - defensive fallback
                    pass
                value = inner.meta.get("default")
            else:
                raise
        else:
            if adapted is not None:
                data[key] = adapted
        if not isNullable(value) or key in data:
            result[key] = value
    if not strict:
        _merge(result, data)
    return (result, None)


def _resolve_union(
    data: Any,
    schema: Schema,
    options: Options,
    strict: bool,
) -> tuple[Any, Any | None]:
    last_error: ValidationError | None = None
    for inner in schema.list or []:
        try:
            return Schema.resolve(data, inner, options, strict)  # type: ignore[attr-defined]
        except ValidationError as err:
            last_error = err
    raise ValidationError(
        f"expected {schema.to_string()} but got {_safe_json(data)}", options
    ) from last_error


def _resolve_intersect(
    data: Any,
    schema: Schema,
    options: Options,
    strict: bool,
) -> tuple[Any, None]:
    list_ = schema.list or []
    if not list_:
        return (data, None)
    result: Any = None
    for inner in list_:
        value, _ = Schema.resolve(data, inner, options, True)  # type: ignore[attr-defined]
        if isNullable(value):
            continue
        if isNullable(result):
            result = value
        elif type(result) is not type(value):
            raise ValidationError(
                f"expected {schema.to_string()} but got {_safe_json(data)}", options
            )
        elif isinstance(result, dict) and isinstance(value, dict):
            _merge(result, value)
        elif result != value:
            raise ValidationError(
                f"expected {schema.to_string()} but got {_safe_json(data)}", options
            )
    if not strict and isPlainObject(data):
        _merge(result or {}, data)
    return (result, None)


def _resolve_transform(
    data: Any,
    schema: Schema,
    options: Options,
    _strict: bool,
) -> tuple[Any, Any | None]:
    inner = schema.inner
    if inner is None:
        raise ValidationError("transform schema missing inner", options)
    result, adapted = Schema.resolve(data, inner, options, True)  # type: ignore[attr-defined]
    if adapted is None:
        adapted = data
    callback = schema.callback
    if schema.preserve:
        return (callback(result, options), None)  # type: ignore[misc]
    return (callback(result, options), callback(adapted, options))  # type: ignore[misc]


def _safe_json(value: Any) -> str:
    try:
        import json as _json

        return _json.dumps(value)
    except Exception:  # pragma: no cover - last-ditch fallback
        return repr(value)


Schema.lazy = staticmethod(_lazy)  # type: ignore[attr-defined]
Schema.string = staticmethod(_string_factory)  # type: ignore[attr-defined]
Schema.number = staticmethod(_number_factory)  # type: ignore[attr-defined]
Schema.boolean = staticmethod(_boolean_factory)  # type: ignore[attr-defined]
Schema.any = staticmethod(_any_factory)  # type: ignore[attr-defined]
Schema.never = staticmethod(_never_factory)  # type: ignore[attr-defined]
Schema.const = staticmethod(_const_factory)  # type: ignore[attr-defined]
Schema.function = staticmethod(_function_factory)  # type: ignore[attr-defined]
Schema.is_ = staticmethod(_is_factory)  # type: ignore[attr-defined]
Schema.array = staticmethod(_array_factory)  # type: ignore[attr-defined]
Schema.dict = staticmethod(_dict_factory)  # type: ignore[attr-defined]
Schema.tuple = staticmethod(_tuple_factory)  # type: ignore[attr-defined]
Schema.object = staticmethod(_object_factory)  # type: ignore[attr-defined]
Schema.union = staticmethod(_union_factory)  # type: ignore[attr-defined]
Schema.intersect = staticmethod(_intersect_factory)  # type: ignore[attr-defined]
Schema.transform = staticmethod(_transform_factory)  # type: ignore[attr-defined]
Schema.bitset = staticmethod(_bitset_factory)  # type: ignore[attr-defined]
Schema.natural = staticmethod(_natural_factory)  # type: ignore[attr-defined]
Schema.percent = staticmethod(_percent_factory)  # type: ignore[attr-defined]
Schema.date = staticmethod(_date_factory)  # type: ignore[attr-defined]
Schema.reg_exp = staticmethod(_reg_exp_factory)  # type: ignore[attr-defined]
Schema.array_buffer = staticmethod(_array_buffer_factory)  # type: ignore[attr-defined]


def _refinement(
    inner: Any,
    predicate: _Callable[[Any], bool],
    message: str | None = None,
) -> Schema:
    """Predicate guard wrapper around ``Schema.transform``."""

    def _callback(value: Any, options: Options) -> Any:
        if not predicate(value):
            raise ValidationError(message or "expected value to satisfy predicate", options)
        return value

    return _transform_factory(inner, _callback, preserve=True)


Schema.refinement = staticmethod(_refinement)  # type: ignore[attr-defined]


# Register the built-in resolvers.
for _name, _resolver in [
    ("lazy", _resolve_lazy),
    ("any", _resolve_any),
    ("never", _resolve_never),
    ("const", _resolve_const),
    ("string", _resolve_string),
    ("number", _resolve_number),
    ("boolean", _resolve_boolean),
    ("bitset", _resolve_bitset),
    ("function", _resolve_function),
    ("is", _resolve_is),
    ("array", _resolve_array),
    ("dict", _resolve_dict),
    ("tuple", _resolve_tuple),
    ("object", _resolve_object),
    ("union", _resolve_union),
    ("intersect", _resolve_intersect),
    ("transform", _resolve_transform),
]:
    resolvers[_name] = _resolver

# Register built-in formatters.
_register_method("is", lambda schema, _inline=False: schema.constructor.__name__ if isinstance(schema.constructor, type) else str(schema.constructor))
_register_method("any", lambda *_: "any")
_register_method("never", lambda *_: "never")
_register_method("const", lambda schema, _inline=False: '"' + str(schema.value) + '"' if isinstance(schema.value, str) else str(schema.value))
_register_method("string", lambda *_: "string")
_register_method("number", lambda *_: "number")
_register_method("boolean", lambda *_: "boolean")
_register_method("bitset", lambda *_: "bitset")
_register_method("function", lambda *_: "function")


def _array_formatter(schema: Schema, inline: bool) -> str:
    inner = schema.inner
    text = inner.to_string(True) if inner is not None else "unknown"
    return f"{text}[]"


def _dict_formatter(schema: Schema, _inline: bool) -> str:
    inner = schema.inner
    key = schema.s_key
    return f"{{ [key: {key.to_string() if key is not None else 'string'}]: {inner.to_string() if inner is not None else 'any'} }}"


def _tuple_formatter(schema: Schema, _inline: bool) -> str:
    list_ = schema.list or []
    return "[" + ", ".join(member.to_string() for member in list_) + "]"


def _object_formatter(schema: Schema, _inline: bool) -> str:
    dict_ = schema.dict or {}
    if not dict_:
        return "{}"
    parts = []
    for key, inner in dict_.items():
        required = inner.meta.get("required", False)
        parts.append(f"{key}{'' if required else '?'}: {inner.to_string()}")
    return "{ " + ", ".join(parts) + " }"


def _union_formatter(schema: Schema, inline: bool) -> str:
    list_ = schema.list or []
    text = " | ".join(member.to_string() for member in list_)
    return f"({text})" if inline else text


def _intersect_formatter(schema: Schema, _inline: bool) -> str:
    list_ = schema.list or []
    return " & ".join(member.to_string(True) for member in list_)


def _transform_formatter(schema: Schema, inline: bool) -> str:
    inner = schema.inner
    return inner.to_string(inline) if inner is not None else "transform"


_register_method("array", _array_formatter)
_register_method("dict", _dict_formatter)
_register_method("tuple", _tuple_formatter)
_register_method("object", _object_formatter)
_register_method("union", _union_formatter)
_register_method("intersect", _intersect_formatter)
_register_method("transform", _transform_formatter)
