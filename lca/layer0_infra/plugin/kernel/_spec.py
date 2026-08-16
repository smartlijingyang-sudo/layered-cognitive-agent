"""PluginSpec — plugin descriptor for 3 shapes (function/class/object)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lca.layer0_infra.plugin.kernel._types import Apply


@dataclass(frozen=True)
class PluginSpec:
    """Plugin descriptor.

    ``apply`` semantics depend on ``is_class``:
    - False → ``apply(ctx, config)`` function
    - True  → ``cls(ctx, config)`` constructor (Service subclass)
    """

    name: str
    apply: Apply
    inject: tuple[str, ...] = ()
    provides: str | None = None
    validate: Callable[[Any], Any] | None = None
    is_class: bool = False
