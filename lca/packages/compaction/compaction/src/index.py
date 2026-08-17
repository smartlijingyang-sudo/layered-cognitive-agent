"""Auto-generated surface skeleton for upstream ``compaction/compaction/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``compaction/compaction/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CompactionAgentContext",
    "CompactionCheckpointSource",
    "CompactionEngine",
    "CompactionId",
    "CompactionResult",
    "CompactionTrigger",
    "ManualCompactAgentContext",
    "ManualCompactionError",
    "ManualCompactionErrorCode",
    "compactCheckpointSource",
    "isCompactCheckpointSource",
    "toolPairingBalancedAfter",
    "toolPairingBalancedBefore",
]

CompactionCheckpointSource: TypeAlias = object  # port: surface stub

CompactionResult: TypeAlias = object  # port: surface stub

CompactionTrigger: TypeAlias = object  # port: surface stub

ManualCompactionErrorCode: TypeAlias = object  # port: surface stub

class CompactionEngine:
    """Surface stub for upstream class ``CompactionEngine``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CompactionEngine.__init__ from compaction/compaction/src/index.ts")

class ManualCompactionError:
    """Surface stub for upstream class ``ManualCompactionError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ManualCompactionError.__init__ from compaction/compaction/src/index.ts")

CompactionId = None  # port: surface stub (reexport)

compactCheckpointSource = None  # port: surface stub (reexport)

isCompactCheckpointSource = None  # port: surface stub (reexport)

toolPairingBalancedAfter = None  # port: surface stub (reexport)

toolPairingBalancedBefore = None  # port: surface stub (reexport)

class CompactionAgentContext(Protocol):
    """Surface stub for upstream interface ``CompactionAgentContext``."""
    pass

class ManualCompactAgentContext(Protocol):
    """Surface stub for upstream interface ``ManualCompactAgentContext``."""
    pass
