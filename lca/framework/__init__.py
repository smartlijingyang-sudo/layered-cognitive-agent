"""Framework plugin collections owned by the framework author.

These collections host the ``@plugin`` declarations that compose the
declarative phase-graph interpreter and the subgraph runtime that drives
it.  Business-domain plugins (think / reflect / runtime_provider …) live
under :mod:`lca.plugins` and must remain independent from anything inside
this package.

Sibling packages (declarative / subgraph) are imported lazily so the
existing pre-implementation directory tree keeps importable as the
framework plugin files are filled in commit-by-commit (see plan §10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.framework import declarative, subgraph


def __getattr__(name: str):
    """Lazy attribute access for ``declarative`` and ``subgraph`` subpackages.

    Both subpackages contain plugin modules whose individual ``.py``
    files land in subsequent commits.  Eagerly importing them here
    would break ``lca.framework.subgraph.plugins.channel`` import on
    branches where only the subgraph plugin set has been wired up.
    """
    if name in {"declarative", "subgraph"}:
        import importlib

        module = importlib.import_module(f"lca.framework.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module 'lca.framework' has no attribute {name!r}")


__all__ = ["declarative", "subgraph"]
