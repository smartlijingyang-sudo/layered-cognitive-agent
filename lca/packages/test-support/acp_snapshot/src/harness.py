"""Auto-generated surface skeleton for upstream ``test-support/acp-snapshot/src/harness.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/acp-snapshot/src/harness.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentUnderTest",
    "HarvestedLog",
    "InputScript",
    "InputStep",
    "PermissionAnswer",
    "RunOptions",
    "RunResult",
    "runScenario",
    "snapshotSpillRoot",
]

AgentUnderTest: TypeAlias = object  # port: surface stub

InputStep: TypeAlias = object  # port: surface stub

def runScenario(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``runScenario``."""
    raise NotImplementedError("port runScenario from test-support/acp-snapshot/src/harness.ts")

def snapshotSpillRoot(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``snapshotSpillRoot``."""
    raise NotImplementedError("port snapshotSpillRoot from test-support/acp-snapshot/src/harness.ts")

class HarvestedLog(Protocol):
    """Surface stub for upstream interface ``HarvestedLog``."""
    pass

class InputScript(Protocol):
    """Surface stub for upstream interface ``InputScript``."""
    pass

class PermissionAnswer(Protocol):
    """Surface stub for upstream interface ``PermissionAnswer``."""
    pass

class RunOptions(Protocol):
    """Surface stub for upstream interface ``RunOptions``."""
    pass

class RunResult(Protocol):
    """Surface stub for upstream interface ``RunResult``."""
    pass
