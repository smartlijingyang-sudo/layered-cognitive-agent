"""`cordis.plugin` — Plugin decorator and metadata (1:1 to upstream `Plugin`).

Faithful Python translation of `~/deepseek-harness/vendor/cordis/src/plugin.ts`.

Provides:
- :func:`plugin` — decorator that turns an async setup function into a :class:`Plugin`.
- :class:`Plugin` — wraps a setup callback with optional config schema.
- :func:`get_plugin_meta` / :func:`is_plugin` — metadata helpers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

__all__ = ["Plugin", "plugin", "get_plugin_meta", "is_plugin"]


# Symbol table for plugin metadata (mirrors upstream `Plugin.meta`)
_PLUGIN_META_ATTR = "__cordis_plugin_meta__"
_PLUGIN_FLAG_ATTR = "__cordis_plugin__"


@dataclass
class Plugin:
    """Wraps an async setup callback with optional config schema (1:1 to upstream).

    The wrapped callback receives ``(ctx, config)`` and returns either:
    - ``None`` (no disposer)
    - A sync / async callable (registered as a disposer)
    """

    setup: Callable[..., Any]
    Config: type[Any] | None = None
    name: str | None = None
    inject: list[str] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Tag the instance for `is_plugin()` detection.
        try:
            object.__setattr__(self, _PLUGIN_FLAG_ATTR, True)
        except Exception:  # pragma: no cover
            pass


def plugin(
    setup: Callable[..., Any] | None = None,
    *,
    Config: type[Any] | None = None,
    name: str | None = None,
    inject: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> Any:
    """Decorator: turn an async setup function into a :class:`Plugin`.

    Usage:
        @plugin
        async def setup(ctx, config):
            ...

        @plugin(name="my-plugin", inject=["foo"])
        async def setup(ctx, config):
            ...

    Mirrors upstream ``@plugin`` decorator.
    """
    def _wrap(fn: Callable[..., Any]) -> Plugin:
        return Plugin(
            setup=fn,
            Config=Config,
            name=name,
            inject=inject,
            meta=dict(meta) if meta else {},
        )

    if setup is not None and callable(setup):
        # Bare @plugin (no args): setup is the decorated function
        return _wrap(setup)
    # Parameterized @plugin(...): return the wrapper
    return _wrap


def is_plugin(obj: Any) -> bool:
    """Return True if ``obj`` is a :class:`Plugin` instance."""
    if isinstance(obj, Plugin):
        return True
    # Duck-typed check via the flag attr (covers decorated functions in upstream)
    try:
        return bool(getattr(obj, _PLUGIN_FLAG_ATTR, False))
    except Exception:
        return False


def get_plugin_meta(plugin_obj: Plugin | Any) -> dict[str, Any]:
    """Return the metadata dict attached to a plugin (1:1 with upstream).

    For :class:`Plugin` instances, returns ``plugin_obj.meta``. For other
    plugin-like objects, attempts to read ``__cordis_plugin_meta__``.
    """
    if isinstance(plugin_obj, Plugin):
        return dict(plugin_obj.meta)
    try:
        meta = getattr(plugin_obj, _PLUGIN_META_ATTR, None)
        return dict(meta) if meta else {}
    except Exception:
        return {}


def get_plugin_name(plugin_obj: Plugin | Any) -> str | None:
    """Return the plugin's declared name, if any."""
    if isinstance(plugin_obj, Plugin):
        return plugin_obj.name
    try:
        return getattr(plugin_obj, "name", None)
    except Exception:
        return None


def get_plugin_inject(plugin_obj: Plugin | Any) -> list[str] | None:
    """Return the plugin's declared inject dependencies, if any."""
    if isinstance(plugin_obj, Plugin):
        return list(plugin_obj.inject) if plugin_obj.inject is not None else None
    try:
        inj = getattr(plugin_obj, "inject", None)
        return list(inj) if inj is not None else None
    except Exception:
        return None