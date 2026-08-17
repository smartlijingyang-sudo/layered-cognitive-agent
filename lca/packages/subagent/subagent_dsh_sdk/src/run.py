"""Auto-generated surface skeleton for upstream ``subagent/subagent-dsh-sdk/src/run.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent-dsh-sdk/src/run.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_DISPOSE_EOF_GRACE_MS",
    "DEFAULT_DISPOSE_GRACE_MS",
    "DEFAULT_SHUTDOWN_TIMEOUT_MS",
    "SdkRunSpec",
    "sdkStopReason",
    "startSdkRun",
]

DEFAULT_DISPOSE_EOF_GRACE_MS = None  # port: surface stub

DEFAULT_DISPOSE_GRACE_MS = None  # port: surface stub

DEFAULT_SHUTDOWN_TIMEOUT_MS = None  # port: surface stub

def sdkStopReason(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sdkStopReason``."""
    raise NotImplementedError("port sdkStopReason from subagent/subagent-dsh-sdk/src/run.ts")

def startSdkRun(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``startSdkRun``."""
    raise NotImplementedError("port startSdkRun from subagent/subagent-dsh-sdk/src/run.ts")

class SdkRunSpec(Protocol):
    """Surface stub for upstream interface ``SdkRunSpec``."""
    pass
