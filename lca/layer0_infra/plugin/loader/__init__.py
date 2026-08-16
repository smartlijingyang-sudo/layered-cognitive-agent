"""Loader sub-package — topological plugin loading.

Depends on: ``kernel/`` (PluginHost, reconcile, PluginHandle, etc.)
Depended by: ``include/`` (profile composition)

Public API:
    from lca.layer0_infra.plugin.loader import Loader, PluginEntry, BootedTree
"""

from lca.layer0_infra.plugin.loader._entry import BootedTree, PluginEntry
from lca.layer0_infra.plugin.loader._loader import Loader, LoaderError

__all__ = [
    "BootedTree",
    "Loader",
    "LoaderError",
    "PluginEntry",
]
