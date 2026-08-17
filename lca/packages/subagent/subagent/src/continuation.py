"""Auto-generated surface skeleton for upstream ``subagent/subagent/src/continuation.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent/src/continuation.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ContinuableStart",
    "ContinuableStartSpec",
    "CoordinatorMessageSource",
    "SubagentContinuationManager",
    "SubagentDescriptorData",
    "SubagentFollowupOptions",
    "SubagentInterruptAuthority",
    "SubagentReportDelivery",
    "SubagentReportMessageSource",
    "SubagentReportOptions",
    "SubagentSettledMessageSource",
]

SubagentDescriptorData: TypeAlias = object  # port: surface stub

SubagentInterruptAuthority: TypeAlias = object  # port: surface stub

SubagentReportDelivery: TypeAlias = object  # port: surface stub

class SubagentContinuationManager:
    """Surface stub for upstream class ``SubagentContinuationManager``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SubagentContinuationManager.__init__ from subagent/subagent/src/continuation.ts")

class ContinuableStart(Protocol):
    """Surface stub for upstream interface ``ContinuableStart``."""
    pass

class ContinuableStartSpec(Protocol):
    """Surface stub for upstream interface ``ContinuableStartSpec``."""
    pass

class CoordinatorMessageSource(Protocol):
    """Surface stub for upstream interface ``CoordinatorMessageSource``."""
    pass

class SubagentFollowupOptions(Protocol):
    """Surface stub for upstream interface ``SubagentFollowupOptions``."""
    pass

class SubagentReportMessageSource(Protocol):
    """Surface stub for upstream interface ``SubagentReportMessageSource``."""
    pass

class SubagentReportOptions(Protocol):
    """Surface stub for upstream interface ``SubagentReportOptions``."""
    pass

class SubagentSettledMessageSource(Protocol):
    """Surface stub for upstream interface ``SubagentSettledMessageSource``."""
    pass
