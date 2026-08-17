"""Auto-generated surface skeleton for upstream ``compaction/compaction-basic/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``compaction/compaction-basic/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "BasicCompactionConfig",
    "CompactionPolicyConfig",
    "ModelCompactPolicyConfig",
    "ResolvedCompactSpec",
    "ResolvedConfig",
    "ResolvedRetention",
    "ResolvedTargetPolicy",
]

ResolvedCompactSpec: TypeAlias = object  # port: surface stub

ResolvedConfig: TypeAlias = object  # port: surface stub

ResolvedRetention: TypeAlias = object  # port: surface stub

ResolvedTargetPolicy: TypeAlias = object  # port: surface stub

class BasicCompactionConfig(Protocol):
    """Surface stub for upstream interface ``BasicCompactionConfig``."""
    pass

class CompactionPolicyConfig(Protocol):
    """Surface stub for upstream interface ``CompactionPolicyConfig``."""
    pass

class ModelCompactPolicyConfig(Protocol):
    """Surface stub for upstream interface ``ModelCompactPolicyConfig``."""
    pass
