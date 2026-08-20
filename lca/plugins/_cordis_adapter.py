"""DSH-style @plugin wrapper — typed metadata for plugins.

Vendored ``cordis.plugin`` only accepts ``(name, Config, inject, meta)``. This
adapter layers DSH's ``provides / requires / implements / layer / side_effects /
policy_class / test_suite / description`` fields on top — without modifying the
vendored source. Use this decorator instead of ``cordis.plugin`` whenever the
plugin wants DSH-style field declarations; tests can read these fields off the
returned ``Plugin.meta`` dict.

Design contract (1:1 with ``~/deepseek-harness/vendor/cordis/src/registry.ts``)::

    @plugin(
        name="<id>",
        Config=BaseModel,
        inject=["..."],
        provides=["..."],          # capability keys published via ctx.provide
        requires=["..."],          # capability keys consumed via ctx.inject
        implements=[Protocol, ...],
        layer="service|provider|behavior|guard|sensor",
        side_effects="none|tools|memory|world",
        policy_class="observe|control|execute",
        test_suite="tests/test_<x>.py",
        description="...",
    )
    async def setup(ctx: Context, config: Config) -> None: ...

The resulting :class:`cordis.Plugin` carries every DSH field under ``meta``; the
inspect CLI / BootReport / ``tests/test_plugin_alignment.py`` reads them via
``get_plugin_meta(plugin)``.

Why this is an adapter, not a vendored change:

* Vendored ``cordis/src/cordis/`` is a faithful 1:1 Python port of the upstream
  TypeScript kernel; modifying it would diverge from upstream and block future
  re-vendoring.
* All extension lives here, under one obvious import.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cordis import plugin as _cordis_plugin

__all__ = ["plugin"]

# Field names — kept as constants so tests can assert against them.
_PROVIDES_FIELD = "provides"
_REQUIRES_FIELD = "requires"
_IMPLEMENTS_FIELD = "implements"
_LAYER_FIELD = "layer"
_SIDE_EFFECTS_FIELD = "side_effects"
_POLICY_CLASS_FIELD = "policy_class"
_TEST_SUITE_FIELD = "test_suite"
_DESCRIPTION_FIELD = "description"


def _normalize_implements(values: Any) -> list[str]:
    """Accept Protocol classes / name strings; return a list of bare class names."""
    if not values:
        return []
    out: list[str] = []
    for v in values:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, type):
            out.append(v.__name__)
        else:
            out.append(str(v))
    return out


def plugin(
    setup: Callable[..., Any] | None = None,
    *,
    Config: type[Any] | None = None,  # noqa: N803 — DSH field name parity
    name: str | None = None,
    inject: list[str] | None = None,
    provides: list[str] | None = None,
    requires: list[str] | None = None,
    implements: Any = None,
    layer: str | None = None,
    side_effects: str | None = None,
    policy_class: str | None = None,
    test_suite: str | None = None,
    description: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Any:
    """DSH-style @plugin wrapper — see module docstring for the contract."""
    merged_meta: dict[str, Any] = dict(meta) if meta else {}
    if provides is not None:
        merged_meta[_PROVIDES_FIELD] = list(provides)
    if requires is not None:
        merged_meta[_REQUIRES_FIELD] = list(requires)
    impl_names = _normalize_implements(implements)
    if impl_names:
        merged_meta[_IMPLEMENTS_FIELD] = impl_names
    if layer is not None:
        merged_meta[_LAYER_FIELD] = layer
    if side_effects is not None:
        merged_meta[_SIDE_EFFECTS_FIELD] = side_effects
    if policy_class is not None:
        merged_meta[_POLICY_CLASS_FIELD] = policy_class
    if test_suite is not None:
        merged_meta[_TEST_SUITE_FIELD] = test_suite
    if description is not None:
        merged_meta[_DESCRIPTION_FIELD] = description
    return _cordis_plugin(
        setup,
        Config=Config,
        name=name,
        inject=inject,
        meta=merged_meta or None,
    )
