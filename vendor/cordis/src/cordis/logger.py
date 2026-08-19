"""`cordis.logger` — Logger service (1:1 port of upstream `logger.ts`).

Faithful Python translation of `~/deepseek-harness/vendor/cordis/src/logger.ts`.

Provides:
- ``LoggerLevel``: numeric severity enum (ERROR/INFO/WARN/DEBUG).
- ``Message``: structured log record delivered to exporters.
- ``Exporter``: sink receiving structured messages; supports colors, maxLength,
  levels (per-name thresholds), formatters (printf-style).
- ``Logger``: facade with per-severity methods and printf-style ``format``.
- ``LoggerService``: installed as ``ctx.logger``; callable to create a
  named ``Logger``, with severity methods on the instance itself.

Architecture (1:1 with upstream):
- ``LoggerService`` is constructed via ``ctx.effect`` so it disposes with the
  fiber.
- Exporters are added via ``ctx.effect`` to participate in fiber lifecycle.
- Config is resolved by walking the ``ctx[symbols.intercept]`` prototype chain.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from cordis.utils import Tracker

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from cordis.context import Context


__all__ = [
    "LoggerLevel",
    "Message",
    "Exporter",
    "Logger",
    "LoggerService",
    "default_formatters",
    "c16",
    "c256",
    "hyphenate",
]


# ---------------------------------------------------------------------------
# LoggerLevel enum (mirrors upstream `enum LoggerLevel { ERROR=0; INFO=1; WARN=2; DEBUG=3 }`)
# ---------------------------------------------------------------------------


class LoggerLevel:
    """Numeric severity for exporters (mirrors upstream ``LoggerLevel``)."""

    ERROR: ClassVar[int] = 0
    INFO: ClassVar[int] = 1
    WARN: ClassVar[int] = 2
    DEBUG: ClassVar[int] = 3

    _NAMES: ClassVar[dict[int, str]] = {
        0: "error",
        1: "info",
        2: "warn",
        3: "debug",
    }

    @classmethod
    def name(cls, value: int) -> str:
        return cls._NAMES.get(value, "info")


# ---------------------------------------------------------------------------
# Color palettes (ANSI 16-color and 256-color)
# ---------------------------------------------------------------------------


c16: list[int] = [6, 2, 3, 4, 5, 1]
"""ANSI 16-color palette indexes used for logger name coloring."""

c256: list[int] = [
    20, 21, 26, 27, 32, 33, 38, 39, 40, 41, 42, 43, 44, 45, 56, 57, 62,
    63, 68, 69, 74, 75, 76, 77, 78, 79, 80, 81, 92, 93, 98, 99, 112, 113,
    129, 134, 135, 148, 149, 160, 161, 162, 163, 164, 165, 166, 167, 168,
    169, 170, 171, 172, 173, 178, 179, 184, 185, 196, 197, 198, 199, 200,
    201, 202, 203, 204, 205, 206, 207, 208, 209, 214, 215, 220, 221,
]
"""ANSI 256-color palette indexes used for logger name coloring."""


# ---------------------------------------------------------------------------
# Default printf-style formatters (1:1 with upstream `defaultFormatters`)
# ---------------------------------------------------------------------------


Formatter = Callable[[Any, "Exporter", "Message"], Any]


def _fmt_s(value: Any, _exporter: "Exporter", _message: "Message") -> str:
    return str(value)


def _fmt_d(value: Any, _exporter: "Exporter", _message: "Message") -> int:
    return int(Number(value))


def _fmt_i(value: Any, _exporter: "Exporter", _message: "Message") -> int:
    return int(Number(value))


def _fmt_f(value: Any, _exporter: "Exporter", _message: "Message") -> float:
    return float(Number(value))


def _fmt_o(value: Any, exporter: "Exporter", message: "Message") -> str:
    return json.dumps(value, default=_json_default)


def _fmt_O(value: Any, exporter: "Exporter", message: "Message") -> str:
    return json.dumps(value, default=_json_default)


def _fmt_c(_value: Any, _exporter: "Exporter", _message: "Message") -> str:
    return ""


def _fmt_C(value: Any, exporter: "Exporter", message: "Message") -> str:
    code = Logger.code(message.name, exporter.colors)
    return Logger.color(exporter, code, value)


def _json_default(obj: Any) -> Any:
    """JSON serializer fallback for non-trivial types."""
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def Number(value: Any) -> float:
    """Mirror upstream ``Number``: coerce to float."""
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


default_formatters: dict[str, Formatter] = {
    "s": _fmt_s,
    "d": _fmt_d,
    "i": _fmt_i,
    "f": _fmt_f,
    "o": _fmt_o,
    "O": _fmt_O,
    "c": _fmt_c,
    "C": _fmt_C,
}
"""Built-in placeholder formatters used by ``Logger.format()``."""


def hyphenate(name: str) -> str:
    """Convert camelCase to kebab-case (mirrors upstream ``hyphenate``)."""
    result: list[str] = []
    for i, ch in enumerate(name):
        if i > 0 and ch.isupper():
            result.append("-")
        result.append(ch.lower())
    # Strip leading hyphen (mirrors upstream behavior for names starting uppercase)
    if result and result[0] == "-":
        result = result[1:]
    return "".join(result)


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """Structured log record delivered to exporters (1:1 with upstream)."""

    sn: int
    ts: int
    name: str
    type: str
    level: int
    args: list[Any]
    fiber: Any = None  # WeakRef[Fiber] in upstream; we keep a plain reference


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------


@dataclass
class Exporter:
    """Sink receiving structured log messages."""

    export: Callable[[Message], None]
    colors: int | bool | None = None
    max_length: int = 10240
    levels: dict[str, int] | None = None
    formatters: dict[str, Formatter] | None = None


# ---------------------------------------------------------------------------
# Logger (1:1 with upstream `class Logger`)
# ---------------------------------------------------------------------------


def _is_aggregate_error(error: Any) -> bool:
    return isinstance(error, BaseException) and isinstance(getattr(error, "errors", None), list)


class Logger:
    """Logger facade for one named subsystem."""

    def __init__(self, options: dict[str, Any], service: "LoggerService") -> None:
        # Object.assign(this, options) — copy name / level / meta
        self.name: str = options["name"]
        self.level: int | None = options.get("level")
        self.meta: dict[str, Any] = options.get("meta", {}) or {}
        self.service: LoggerService = service
        self.error = self._method("error", LoggerLevel.ERROR)
        self.info = self._method("info", LoggerLevel.INFO)
        self.warn = self._method("warn", LoggerLevel.WARN)
        self.debug = self._method("debug", LoggerLevel.DEBUG)

    def _method(self, type_: str, level: int) -> Callable[..., None]:
        def _emit(*args: Any) -> None:
            # AggregateError / Error handling: recurse or unroll.
            if len(args) == 1 and isinstance(args[0], BaseException):
                err = args[0]
                if err.__cause__ is not None:
                    getattr(self, type_)(err.__cause__)
                    return
                if _is_aggregate_error(err):
                    errors = err.errors
                    for sub in errors:
                        getattr(self, type_)(sub)
                    return
            sn = self.service._sn_message + 1
            self.service._sn_message = sn
            ts = int(time.time() * 1000)
            for exporter in self.service.exporters.values():
                levels = exporter.levels
                target_level: int | None = None
                if levels is not None:
                    if self.name in levels:
                        target_level = levels[self.name]
                    elif "default" in levels:
                        target_level = levels["default"]
                if target_level is None:
                    target_level = self.level if self.level is not None else LoggerLevel.INFO
                if target_level < level:
                    continue
                merged_meta = dict(self.meta)
                merged_meta.setdefault("fiber", None)
                msg = Message(
                    sn=sn,
                    ts=ts,
                    name=self.name,
                    type=type_,
                    level=level,
                    args=list(args),
                    fiber=merged_meta.get("fiber"),
                )
                try:
                    exporter.export(msg)
                except Exception:  # pragma: no cover — exporter must not raise
                    pass

        return _emit

    # ------------------------------------------------------------------
    # Format / color helpers (1:1 with upstream `Logger.format/color/code`)
    # ------------------------------------------------------------------

    @staticmethod
    def color(exporter: Exporter, code: int, value: Any, decoration: str = "") -> str:
        if not exporter.colors:
            return str(value)
        if code < 8:
            color_code = str(code)
        else:
            color_code = "8;5;" + str(code)
        level = exporter.colors if isinstance(exporter.colors, int) else 1
        dec = decoration if level >= 2 else ""
        return f"\x1b[3{color_code}{dec}m{value}\x1b[0m"

    @staticmethod
    def code(name: str, level: int | bool | None = None) -> int:
        hash_ = 0
        for ch in name:
            hash_ = ((hash_ << 3) - hash_) + ord(ch) + 13
            hash_ = hash_ & 0xFFFFFFFF  # simulate 32-bit signed int via two's-complement
        # Python ints are arbitrary-precision; coerce to int32-like behavior
        if hash_ & 0x80000000:
            hash_ -= 0x100000000
        if not level:
            colors: list[int] = []
        elif level >= 2:
            colors = c256
        else:
            colors = c16
        return colors[abs(hash_) % len(colors)] if colors else 0

    @staticmethod
    def format(exporter: Exporter, message: Message) -> str:
        args = list(message.args)
        if args and isinstance(args[0], BaseException):
            err = args[0]
            args[0] = err.stack if getattr(err, "stack", None) else str(err)
            args.insert(0, "%s")
        elif args and not isinstance(args[0], str):
            args.insert(0, "%o")
        if not args:
            return ""
        fmt = args.pop(0)
        if not isinstance(fmt, str):
            fmt = str(fmt)
        # Replace %X tokens with formatted values
        def _replace(match: Any) -> str:
            ch = match.group(1)
            if ch == "%":
                return "%"
            exporter_fmts = exporter.formatters if exporter.formatters else {}
            formatter = exporter_fmts.get(ch)
            if formatter is None:
                formatter = default_formatters.get(ch)
            if callable(formatter):
                if args:
                    value = args.pop(0)
                    return str(formatter(value, exporter, message))
                return match.group(0)
            return match.group(0)

        import re
        fmt_str = re.sub(r"%([a-zA-Z%])", _replace, fmt)
        o_formatter: Formatter = (
            exporter.formatters.get("o") if exporter.formatters else None
        ) or default_formatters["o"]
        for arg in args:
            if isinstance(arg, dict) or (not isinstance(arg, (str, int, float, bool)) and arg is not None):
                try:
                    arg_str = o_formatter(arg, exporter, message)
                except Exception:
                    arg_str = str(arg)
                fmt_str += " " + arg_str
            else:
                fmt_str += " " + str(arg)
        max_length = exporter.max_length if isinstance(exporter.max_length, int) else 10240
        lines = fmt_str.split("\n") if "\n" in fmt_str else [fmt_str]
        out: list[str] = []
        for line in lines:
            if len(line) > max_length:
                out.append(line[:max_length] + "...")
            else:
                out.append(line)
        return "\n".join(out)


# ---------------------------------------------------------------------------
# LoggerService (1:1 with upstream `class LoggerService`)
# ---------------------------------------------------------------------------


class LoggerService:
    """Logging service installed as ``ctx.logger``.

    Call ``ctx.logger()`` to create a named :class:`Logger`, or call
    ``ctx.logger.info(...)`` directly. Severity methods on the instance
    forward to a derived :class:`Logger` facade.
    """

    buffer_size: int = 1000
    buffer: list[Message] = []
    ctx: "Context | None" = None

    _sn_message: int = 0
    _sn_exporter: int = 0
    exporters: dict[int, Exporter] = {}

    def __init__(self, ctx: "Context") -> None:
        # Mirror upstream Tracker pattern.
        self._tracker = Tracker(property="ctx", no_shadow=True)
        try:
            self.__dict__["cordis.tracker"] = self._tracker
        except Exception:  # pragma: no cover — defensive
            pass
        self.ctx = ctx

        # Install default buffer exporter (matches upstream constructor).
        self._install_default_exporter()

    def _install_default_exporter(self) -> None:
        service = self

        def _buffer_export(message: Message) -> None:
            service.buffer.append(message)
            if len(service.buffer) > service.buffer_size:
                service.buffer = service.buffer[-service.buffer_size:]

        self.exporter(Exporter(export=_buffer_export, colors=3))

    # ------------------------------------------------------------------
    # Exporter registration (1:1 with upstream `exporter()`)
    # ------------------------------------------------------------------

    def exporter(self, exporter: Exporter) -> Callable[[], bool]:
        """Register an exporter; dispose with the current fiber."""
        # Always register the exporter so callers (including __init__'s default
        # buffer exporter and tests that bypass __init__) can use it without a
        # fiber-aware ctx.
        self._sn_exporter += 1
        sn = self._sn_exporter
        self.exporters[sn] = exporter

        def _effect_disposer() -> bool:
            return self.exporters.pop(sn, None) is not None

        # Best-effort wiring to ctx.effect so the exporter disposes with the
        # owning fiber (1:1 with upstream). The exporter remains registered
        # regardless — only the disposer is conditional.
        ctx = self.ctx
        if ctx is not None and hasattr(ctx, "effect"):
            try:
                ctx.effect(lambda: _effect_disposer(), "ctx.logger.exporter()")
            except Exception:  # pragma: no cover
                pass
        return _effect_disposer

    # ------------------------------------------------------------------
    # Config resolution (1:1 with upstream `_resolveConfig`)
    # ------------------------------------------------------------------

    def _resolve_config(self) -> dict[str, Any]:
        ctx = self.ctx
        if ctx is None:
            return {}
        try:
            from cordis.utils import symbols as _symbols  # local to avoid cycle
            intercept = ctx[_symbols.intercept]  # type: ignore[index]
        except Exception:
            return {}
        # Walk the prototype chain (handles both dict and class-based intercepts).
        configs: list[dict[str, Any]] = []
        seen: set[int] = set()
        while intercept is not None and id(intercept) not in seen:
            seen.add(id(intercept))
            # Read "logger" config from intercept (dict or class instance).
            if isinstance(intercept, dict):
                own = intercept.get("logger")
            else:
                try:
                    own = getattr(intercept, "logger", None)
                except Exception:
                    own = None
            if isinstance(own, dict):
                configs.insert(0, own)
            # Read next prototype: prefer explicit __proto__ attribute, fall back
            # to type chain (matches upstream behavior for both shapes).
            parent: Any = None
            if isinstance(intercept, dict):
                parent = intercept.get("__proto__")
            else:
                try:
                    parent = object.__getattribute__(intercept, "__proto__")
                except Exception:
                    try:
                        bases = type(intercept).__mro__
                        parent = bases[1] if len(bases) > 1 else None
                    except Exception:
                        parent = None
            if parent is None or parent is intercept:
                break
            intercept = parent
        merged: dict[str, Any] = {}
        for cfg in configs:
            merged.update(cfg)
        return merged

    # ------------------------------------------------------------------
    # Callable / invoke (1:1 with upstream `[symbols.invoke]`)
    # ------------------------------------------------------------------

    def __call__(self, name: str | None = None) -> Logger:
        config = self._resolve_config()
        ctx = self.ctx
        fiber = None
        if ctx is not None:
            try:
                from cordis.utils import symbols as _symbols
                shadow = ctx[_symbols.shadow]  # type: ignore[index]
                target = shadow if shadow is not None else ctx
                fiber = getattr(target, "fiber", None)
            except Exception:
                fiber = getattr(ctx, "fiber", None) if ctx is not None else None
        if name is None:
            name = config.get("name")
        if name is None and fiber is not None:
            name = hyphenate(getattr(fiber, "name", "root") or "root")
        if name is None:
            name = "root"
        meta: dict[str, Any] = {"fiber": fiber}
        return Logger(
            {"name": name, "level": config.get("level"), "meta": meta},
            self,
        )

    # ------------------------------------------------------------------
    # Severity methods on the service (mirrors upstream static block)
    # ------------------------------------------------------------------

    def error(self, *args: Any) -> None:
        try:
            self().error(*args)
        except Exception:  # pragma: no cover — façade never raises
            pass

    def info(self, *args: Any) -> None:
        try:
            self().info(*args)
        except Exception:  # pragma: no cover
            pass

    def warn(self, *args: Any) -> None:
        try:
            self().warn(*args)
        except Exception:  # pragma: no cover
            pass

    def debug(self, *args: Any) -> None:
        try:
            self().debug(*args)
        except Exception:  # pragma: no cover
            pass