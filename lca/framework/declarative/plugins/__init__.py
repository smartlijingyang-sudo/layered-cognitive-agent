"""Declarative framework plugins (Cordis ``@plugin`` registrations).

Each module exports a single ``setup`` coroutine decorated with ``@plugin``.
Loading this package has no side effect beyond making those symbols
importable; Cordis profile loaders iterate the explicit ``setup``
attributes to register the capabilities.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "delta_reducer",
    "effect_gateway",
    "interpreter",
    "interpreter_factory",
    "journal_committer",
    "lifecycle_publisher",
    "loop_guard_evaluator",
    "phase_observer",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(f"{__name__}.{name}")
    globals()[name] = module
    return module
