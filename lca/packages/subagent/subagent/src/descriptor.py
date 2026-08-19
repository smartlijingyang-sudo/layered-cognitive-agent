"""Auto-generated surface skeleton for upstream ``subagent/subagent/src/descriptor.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent/src/descriptor.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SUBAGENT_DESCRIPTOR_VERSION",
    "ContinuableSubagentDescriptorData",
    "ContinuableSubagentDescriptorInput",
    "OneShotSubagentDescriptorData",
    "OneShotSubagentDescriptorInput",
    "SubagentDescriptorData",
    "SubagentDescriptorInput",
    "foldSubagentDescriptor",
    "snapshotSubagentDescriptor",
]

SubagentDescriptorData: TypeAlias = object  # port: surface stub

SubagentDescriptorInput: TypeAlias = object  # port: surface stub

SUBAGENT_DESCRIPTOR_VERSION = None  # port: surface stub

def foldSubagentDescriptor(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``foldSubagentDescriptor``."""
    raise NotImplementedError("port foldSubagentDescriptor from subagent/subagent/src/descriptor.ts")

def snapshotSubagentDescriptor(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``snapshotSubagentDescriptor``."""
    raise NotImplementedError("port snapshotSubagentDescriptor from subagent/subagent/src/descriptor.ts")

class ContinuableSubagentDescriptorData(Protocol):
    """Surface stub for upstream interface ``ContinuableSubagentDescriptorData``."""
    pass

class ContinuableSubagentDescriptorInput(Protocol):
    """Surface stub for upstream interface ``ContinuableSubagentDescriptorInput``."""
    pass

class OneShotSubagentDescriptorData(Protocol):
    """Surface stub for upstream interface ``OneShotSubagentDescriptorData``."""
    pass

class OneShotSubagentDescriptorInput(Protocol):
    """Surface stub for upstream interface ``OneShotSubagentDescriptorInput``."""
    pass
