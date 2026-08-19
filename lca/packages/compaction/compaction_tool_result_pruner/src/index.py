"""Auto-generated surface skeleton for upstream ``compaction/compaction-tool-result-pruner/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``compaction/compaction-tool-result-pruner/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "DEFAULTS",
    "PRUNE_MARKER",
    "PruneResult",
    "PrunedEntry",
    "ResolvedConfig",
    "ToolResultPruneConfig",
    "ToolResultPruner",
    "codePointLength",
    "resolveConfig",
]

PruneResult: TypeAlias = object  # port: surface stub

PrunedEntry: TypeAlias = object  # port: surface stub

ResolvedConfig: TypeAlias = object  # port: surface stub

ToolResultPruneConfig: TypeAlias = object  # port: surface stub

class ToolResultPruner:
    """Surface stub for upstream class ``ToolResultPruner``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ToolResultPruner.__init__ from compaction/compaction-tool-result-pruner/src/index.ts")

DEFAULTS = None  # port: surface stub (reexport)

PRUNE_MARKER = None  # port: surface stub (reexport)

codePointLength = None  # port: surface stub (reexport)

resolveConfig = None  # port: surface stub (reexport)
