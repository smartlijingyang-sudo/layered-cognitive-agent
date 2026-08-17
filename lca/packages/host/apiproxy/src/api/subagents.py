"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/api/subagents.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/api/subagents.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SubagentAddress",
    "SubagentCatalog",
    "SubagentInterruptReceipt",
    "SubagentListEntry",
    "SubagentPromptReceipt",
    "SubagentsApi",
]

SubagentAddress: TypeAlias = object  # port: surface stub

SubagentListEntry: TypeAlias = object  # port: surface stub

class SubagentCatalog(Protocol):
    """Surface stub for upstream interface ``SubagentCatalog``."""
    pass

class SubagentInterruptReceipt(Protocol):
    """Surface stub for upstream interface ``SubagentInterruptReceipt``."""
    pass

class SubagentPromptReceipt(Protocol):
    """Surface stub for upstream interface ``SubagentPromptReceipt``."""
    pass

class SubagentsApi(Protocol):
    """Surface stub for upstream interface ``SubagentsApi``."""
    pass
