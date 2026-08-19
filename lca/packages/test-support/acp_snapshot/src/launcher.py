"""Auto-generated surface skeleton for upstream ``test-support/acp-snapshot/src/launcher.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/acp-snapshot/src/launcher.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "AcpTestLaunchOptions",
    "AgentUnderTest",
    "LaunchedAcpTestAgent",
    "launchAcpTestAgent",
]

def launchAcpTestAgent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``launchAcpTestAgent``."""
    raise NotImplementedError("port launchAcpTestAgent from test-support/acp-snapshot/src/launcher.ts")

class AcpTestLaunchOptions(Protocol):
    """Surface stub for upstream interface ``AcpTestLaunchOptions``."""
    pass

class AgentUnderTest(Protocol):
    """Surface stub for upstream interface ``AgentUnderTest``."""
    pass

class LaunchedAcpTestAgent(Protocol):
    """Surface stub for upstream interface ``LaunchedAcpTestAgent``."""
    pass
