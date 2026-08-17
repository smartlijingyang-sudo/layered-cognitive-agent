"""Auto-generated surface skeleton for upstream ``subagent/subagent-acp/src/run.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent-acp/src/run.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AcpRunSpec",
    "DEFAULT_DISPOSE_EOF_GRACE_MS",
    "DEFAULT_DISPOSE_GRACE_MS",
    "PermissionPolicy",
    "acpContentText",
    "acpStopReason",
    "disposeAcpChild",
    "startAcpRun",
    "toAcpPrompt",
]

PermissionPolicy: TypeAlias = object  # port: surface stub

DEFAULT_DISPOSE_EOF_GRACE_MS = None  # port: surface stub

DEFAULT_DISPOSE_GRACE_MS = None  # port: surface stub

def acpContentText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``acpContentText``."""
    raise NotImplementedError("port acpContentText from subagent/subagent-acp/src/run.ts")

def acpStopReason(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``acpStopReason``."""
    raise NotImplementedError("port acpStopReason from subagent/subagent-acp/src/run.ts")

def disposeAcpChild(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``disposeAcpChild``."""
    raise NotImplementedError("port disposeAcpChild from subagent/subagent-acp/src/run.ts")

def startAcpRun(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``startAcpRun``."""
    raise NotImplementedError("port startAcpRun from subagent/subagent-acp/src/run.ts")

def toAcpPrompt(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``toAcpPrompt``."""
    raise NotImplementedError("port toAcpPrompt from subagent/subagent-acp/src/run.ts")

class AcpRunSpec(Protocol):
    """Surface stub for upstream interface ``AcpRunSpec``."""
    pass
