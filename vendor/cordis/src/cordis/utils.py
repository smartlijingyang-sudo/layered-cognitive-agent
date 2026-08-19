"""`cordis.utils` — Shared internal helpers.

Faithful 1:1 port of `~/deepseek-harness/vendor/cordis/src/utils.ts`.

Provides:

- :class:`DisposableList` — ordered O(1) deletion collection.
- :data:`symbols` — string-keyed namespace re-exporting framework symbols.
- :func:`is_constructor` — True iff plugin callback should be constructed.
- :func:`join_prototype` — merge two prototype chains.
- :func:`is_object` — truthy object/function predicate.
- :func:`compose_error` — splice caller stack into async-rejected errors.
- :func:`build_outer_stack` — capture a lazy stack-frame supplier.
- :class:`Tracker` — descriptor for service-tracing context wrappers.
- :func:`with_props` — overlay readonly/writable props onto a target.
"""

from __future__ import annotations

import inspect
import sys
import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, TypeVar

__all__ = [
    "DisposableList",
    "EFFECT_META",
    "SHADOW",
    "RECEIVER",
    "ORIGINAL",
    "INIT_HOOKS",
    "CHECK_PROTO",
    "EFFECT",
    "FILTER",
    "ISOLATE",
    "INTERCEPT",
    "INIT",
    "CHECK",
    "CONFIG",
    "INVOKE",
    "EXTEND",
    "TRACKER",
    "RESOLVE_CONFIG",
    "kValidationError",
    "symbols",
    "Tracker",
    "EffectMeta",
    "is_constructor",
    "join_prototype",
    "is_object",
    "get_traceable",
    "with_props",
    "compose_error",
    "build_outer_stack",
]


# Generic TypeVar used internally for typing DisposableList payloads.
_T = TypeVar("_T")


# ---------------------------------------------------------------------------
# DisposableList
# ---------------------------------------------------------------------------


@dataclass
class DisposableList:
    """Ordered collection of disposable values with O(1) deletion by identity.

    Mirrors upstream ``DisposableList<T extends WeakKey>``:

    - ``push(value)`` stores at the next serial; returns an undo callable.
    - ``delete(value)`` removes by ``id(value)``.
    - ``clear()`` drains and returns cleared values in LIFO order.
    - ``__iter__`` yields current values.
    """

    _next_sn: int = field(default=0, init=False)
    _items: dict[int, Any] = field(default_factory=dict, init=False)
    _by_id: dict[int, int] = field(default_factory=dict, init=False)

    def __len__(self) -> int:
        return len(self._items)

    def push(self, value: Any) -> Callable[[], bool]:
        sn = self._next_sn = self._next_sn + 1
        self._items[sn] = value
        self._by_id[id(value)] = sn

        def _undo() -> bool:
            if sn in self._items:
                del self._items[sn]
                self._by_id.pop(id(value), None)
                return True
            return False

        return _undo

    def delete(self, value: Any) -> bool:
        sn = self._by_id.pop(id(value), None)
        if sn is None:
            return False
        existed = sn in self._items
        self._items.pop(sn, None)
        return existed

    def clear(self) -> list[Any]:
        """Drain and return cleared values in LIFO order."""
        values = list(reversed(self._items.values()))
        self._items.clear()
        self._by_id.clear()
        return values

    def __iter__(self) -> Iterator[Any]:
        return iter(self._items.values())

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"DisposableList({list(self._items.values())!r})"


# ---------------------------------------------------------------------------
# Symbol constants (strings — Python has no Symbol primitive)
# ---------------------------------------------------------------------------

EFFECT_META: str = "cordis.effect_meta"
SHADOW: str = "cordis.shadow"
RECEIVER: str = "cordis.receiver"
ORIGINAL: str = "cordis.original"
INIT_HOOKS: str = "cordis.init_hooks"
CHECK_PROTO: str = "cordis.check_proto"

EFFECT: str = "cordis.effect"
FILTER: str = "cordis.filter"
ISOLATE: str = "cordis.isolate"
INTERCEPT: str = "cordis.intercept"

INIT: str = "cordis.init"
CHECK: str = "cordis.check"
CONFIG: str = "cordis.config"
INVOKE: str = "cordis.invoke"
EXTEND: str = "cordis.extend"
TRACKER: str = "cordis.tracker"
RESOLVE_CONFIG: str = "cordis.resolve_config"

kValidationError: str = "cordis.validation_error"


@dataclass(frozen=True)
class SymbolTable:
    """Frozen namespace of framework symbol keys (string keys)."""

    shadow: str = SHADOW
    receiver: str = RECEIVER
    original: str = ORIGINAL
    metadata: str = "cordis.metadata"
    init_hooks: str = INIT_HOOKS
    check_proto: str = CHECK_PROTO
    effect: str = EFFECT
    filter: str = FILTER
    isolate: str = ISOLATE
    intercept: str = INTERCEPT
    init: str = INIT
    check: str = CHECK
    config: str = CONFIG
    invoke: str = INVOKE
    extend: str = EXTEND
    tracker: str = TRACKER
    resolve_config: str = RESOLVE_CONFIG


symbols = SymbolTable()


# ---------------------------------------------------------------------------
# Tracker / EffectMeta
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tracker:
    """Metadata used to bind ``ctx`` to service method calls."""

    associate: str | None = None
    property: str | None = None
    no_shadow: bool = False


@dataclass
class EffectMeta:
    """Tree node for nested effect labels (used by ``Fiber.getEffects``)."""

    label: str
    children: list["EffectMeta"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constructor detection
# ---------------------------------------------------------------------------


def is_constructor(func: Any) -> bool:
    """Return True if ``func`` should be constructed with the plugin class form.

    Faithful to upstream ``isConstructor`` semantics:

    - class (with or without abstract methods) → True.
    - functions / lambdas → False.
    - generator / async-generator functions → False.
    """
    if inspect.isclass(func):
        # Abstract classes can be subclassed; the actual plugin may be a
        # concrete subclass. Upstream distinguishes ``new``-based plugin
        # constructors from call-based function plugins purely by whether
        # the value has a ``prototype`` (class). Mirror that.
        return True
    return False


# ---------------------------------------------------------------------------
# Prototype chain merger
# ---------------------------------------------------------------------------


def join_prototype(proto1: type | None, proto2: type | None) -> type | None:
    """Merge two prototype (parent class) chains into one dynamic base.

    Mirrors upstream ``joinPrototype``: produces a new dynamic class whose
    attribute lookup walks ``proto1`` MRO first, then ``proto2``. Used by
    ``createCallable`` to graft a service's class over a function callable.
    """
    if proto2 is None or proto2 is object:
        if proto1 is None or proto1 is object:
            return None
        return proto1
    if proto1 is None or proto1 is object:
        return proto2

    members: dict[str, Any] = {}
    for klass in proto1.__mro__:
        if klass is object or klass is proto2:
            continue
        members.update(klass.__dict__)

    if not members:
        return type(proto2.__name__, (proto2,), {})

    return type(  # type: ignore[arg-type]
        proto2.__name__,
        (proto2,),
        members,
    )


# ---------------------------------------------------------------------------
# Object predicates
# ---------------------------------------------------------------------------


def is_object(value: Any) -> bool:
    """Return True for non-null objects and functions (same as upstream)."""
    if value is None or value is False:
        return False
    return isinstance(value, (object, type)) or callable(value)


def get_traceable(ctx: Any, value: Any) -> Any:
    """Identity-wrapper used by Reflect for service method binding.

    In Python, bound methods already preserve ``self``, so this is mostly a
    pass-through that respects the upstream ``[symbols.shadow]`` extension
    point. Callers may override this in plugin code if they want richer
    tracking semantics.
    """
    if not is_object(value):
        return value
    if hasattr(value, SHADOW):
        inner = getattr(value, SHADOW, None)
        if inner is not None:
            return inner
    return value


# ---------------------------------------------------------------------------
# withProps (overlay) and createCallable helpers
# ---------------------------------------------------------------------------


@dataclass
class PropsOverlay:
    """Overlay ``props`` on top of ``target`` for attribute reads and writes.

    Faithful Python equivalent of upstream ``withProps``: a tiny proxy class
    where attribute reads check ``props`` first, falling back to ``target``,
    and attribute writes dispatch the same way.
    """

    target: Any
    props: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        if name == "target" or name == "props":
            raise AttributeError(name)
        if name in self.props:
            return self.props[name]
        return getattr(self.target, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("target", "props"):
            object.__setattr__(self, name, value)
            return
        if name in self.props:
            self.props[name] = value
            return
        setattr(self.target, name, value)


def with_props(target: Any, props: dict[str, Any] | None = None) -> Any:
    """Mirror of upstream ``withProps``."""
    if not props:
        return target
    return PropsOverlay(target=target, props=dict(props))


# ---------------------------------------------------------------------------
# Stack-trace composition (composeError)
# ---------------------------------------------------------------------------


@dataclass
class StackInfo:
    """Mutable stack marker passed to ``compose_error`` callbacks."""

    offset: int = 1
    error: BaseException | None = None


def build_outer_stack(offset: int = 0) -> Callable[[], list[str]]:
    """Capture a lazy stack-frame supplier for later error composition."""
    cur: Any = sys._getframe(1)  # noqa: SLF001

    def _take() -> list[str]:
        lines: list[str] = []
        walk: Any = sys._getframe(1)  # noqa: SLF001
        steps = 0
        while walk is not None and steps < 64:
            # Skip frames up to and including the starting frame.
            if walk is cur and steps >= offset:
                break
            lines.append(
                f'  File "{walk.f_code.co_filename}", line {walk.f_lineno}, in {walk.f_code.co_name}'
            )
            walk = walk.f_back
            steps += 1
        return lines

    return _take


def compose_error(
    callback: Callable[[StackInfo], Any],
    get_outer_stack: Callable[[], list[str]] | None = None,
) -> Any:
    """Splice caller stack into sync-raised exceptions and async rejections.

    Mirrors upstream ``composeError``: if ``callback`` raises synchronously,
    or returns an awaitable that rejects, splice ``get_outer_stack()`` lines
    into the resulting exception and re-raise it.

    The port attaches the spliced traceback to ``exc.cordis_stack``; callers
    that wish to render it can read that attribute. The original
    ``__traceback__`` chain is preserved so Python's default formatting
    continues to work.
    """
    if get_outer_stack is None:
        get_outer_stack = build_outer_stack(0)
    info = StackInfo(error=Exception())

    try:
        result = callback(info)
    except BaseException as exc:  # noqa: BLE001
        _handle_error(info, exc, get_outer_stack)
        raise  # pragma: no cover — _handle_error always re-raises

    if inspect.isawaitable(result):
        return _compose_awaitable(result, info, get_outer_stack)

    return result


async def _compose_awaitable(
    awaitable: Any, info: StackInfo, get_outer_stack: Callable[[], list[str]]
) -> Any:
    try:
        return await awaitable
    except BaseException as exc:  # noqa: BLE001
        _handle_error(info, exc, get_outer_stack)
        raise  # pragma: no cover


def _handle_error(
    info: StackInfo,
    reason: BaseException,
    get_outer_stack: Callable[[], list[str]],
) -> None:
    """Re-raise ``reason`` with the outer caller's stack frames spliced in."""
    outer_lines = get_outer_stack()
    if not outer_lines:
        raise reason

    # Combine the original traceback with the outer caller's frames so the
    # reraised exception's ``cordis_stack`` attribute exposes a
    # user-friendly multi-frame traceback.
    base_text = "".join(
        traceback.format_exception(type(reason), reason, reason.__traceback__)
    ).rstrip("\n")
    spliced_text = "\n".join([base_text, *outer_lines])
    try:
        reason.__dict__["cordis_stack"] = spliced_text  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover — defensive
        pass
    raise reason
