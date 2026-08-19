"""Auto-generated surface skeleton for upstream ``subagent/subagent/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ContinuableCreateRequest",
    "ContinuableCreateSpec",
    "ResolvedSubagentStartRequest",
    "SubagentCapabilities",
    "SubagentProvider",
    "SubagentResult",
    "SubagentRun",
    "SubagentRunEndInfo",
    "SubagentRunId",
    "SubagentRunInfo",
    "SubagentStartRequest",
    "SubagentStopReason",
    "SubagentStopReasonMap",
]

SubagentRunId: TypeAlias = object  # port: surface stub

SubagentStopReason: TypeAlias = object  # port: surface stub

class ContinuableCreateRequest(Protocol):
    """Surface stub for upstream interface ``ContinuableCreateRequest``."""
    pass

class ContinuableCreateSpec(Protocol):
    """Surface stub for upstream interface ``ContinuableCreateSpec``."""
    pass

class ResolvedSubagentStartRequest(Protocol):
    """Surface stub for upstream interface ``ResolvedSubagentStartRequest``."""
    pass

class SubagentCapabilities(Protocol):
    """Surface stub for upstream interface ``SubagentCapabilities``."""
    pass

class SubagentProvider(Protocol):
    """Surface stub for upstream interface ``SubagentProvider``."""
    pass

class SubagentResult(Protocol):
    """Surface stub for upstream interface ``SubagentResult``."""
    pass

class SubagentRun(Protocol):
    """Surface stub for upstream interface ``SubagentRun``."""
    pass

class SubagentRunEndInfo(Protocol):
    """Surface stub for upstream interface ``SubagentRunEndInfo``."""
    pass

class SubagentRunInfo(Protocol):
    """Surface stub for upstream interface ``SubagentRunInfo``."""
    pass

class SubagentStartRequest(Protocol):
    """Surface stub for upstream interface ``SubagentStartRequest``."""
    pass

class SubagentStopReasonMap(Protocol):
    """Surface stub for upstream interface ``SubagentStopReasonMap``."""
    pass
