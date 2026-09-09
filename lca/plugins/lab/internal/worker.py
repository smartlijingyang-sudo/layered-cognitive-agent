"""Worker registry for LabCarrier execute.

YAML ``factory:`` values resolve here. Lookups on ``get_worker`` are exact;
``bind_carrier`` records aliases so ``invoke`` can map ``perceive.sense`` /
``expose_schemas`` onto the carrier id a plugin registered.
"""

from __future__ import annotations

from typing import Any, Iterable


class Worker:
    """Execute kernel for one graph factory."""

    factory: str = ""

    def execute(self, node: Any, inputs: Any, seams: Any = None) -> dict:
        raise NotImplementedError(self.factory or type(self).__name__)


_WORKERS: dict[str, type[Worker]] = {}
_ALIAS_TO_CANONICAL: dict[str, str] = {}
_CANONICAL_TO_ALIASES: dict[str, tuple[str, ...]] = {}


def register_worker(factory: str, cls: type[Worker]) -> None:
    """Record ``factory`` as an exact lookup key for ``cls``."""
    _WORKERS[factory] = cls


def get_worker(factory: str) -> type[Worker]:
    """Return the class registered under ``factory``. Lookups are exact."""
    try:
        return _WORKERS[factory]
    except KeyError:
        raise KeyError(factory) from None


def bind_factory_aliases(canonical: str, aliases: Iterable[str]) -> None:
    """Record every alias as pointing at ``canonical`` (carrier.id)."""
    uniq: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if alias and alias not in seen:
            seen.add(alias)
            uniq.append(alias)
    stored = tuple(uniq)
    _CANONICAL_TO_ALIASES[canonical] = stored
    for alias in stored:
        _ALIAS_TO_CANONICAL[alias] = canonical


def lookup_worker(factory: str) -> type[Worker]:
    """Exact ``get_worker``, then aliases recorded by ``bind_carrier``."""
    if factory in _WORKERS:
        return _WORKERS[factory]
    canonical = _ALIAS_TO_CANONICAL.get(factory, factory)
    if canonical in _WORKERS:
        return _WORKERS[canonical]
    for alias in _CANONICAL_TO_ALIASES.get(canonical, ()):
        if alias in _WORKERS:
            return _WORKERS[alias]
    raise KeyError(factory)


def reset_workers() -> None:
    """Test-only — drop registered Worker classes. Aliases stay."""
    _WORKERS.clear()


def reset_aliases() -> None:
    """Test-only — drop bind_carrier factory aliases."""
    _ALIAS_TO_CANONICAL.clear()
    _CANONICAL_TO_ALIASES.clear()


__all__ = [
    "Worker",
    "bind_factory_aliases",
    "get_worker",
    "lookup_worker",
    "register_worker",
    "reset_aliases",
    "reset_workers",
]
