"""Auto-generated surface skeleton for upstream ``extensions/cordis-host-runner/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-host-runner/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ApprovalRequestId",
    "CordisDynamicPackageId",
    "CordisDynamicPluginId",
    "CordisDynamicPluginRunId",
    "CordisDynamicRunMode",
    "CordisErrorDetails",
    "CordisHalfState",
    "CordisInspectMethodManifest",
    "CordisInspectPlatform",
    "CordisInspectProviderManifest",
    "CordisInspectProviderView",
    "CordisInspectQueryRequest",
    "CordisInspectQueryResolution",
    "CordisInspectQueryResolved",
    "CordisInspectRequestId",
    "CordisInspectResolveAck",
    "CordisRunDiagnostic",
    "CordisRunStatus",
    "DynamicCordisClientSource",
    "DynamicCordisHostHalfResult",
    "DynamicCordisInventoryPackage",
    "DynamicCordisInventoryRow",
    "DynamicCordisInvokeResult",
    "DynamicCordisPackage",
    "DynamicCordisRenderFailure",
    "DynamicCordisRequestResolved",
    "DynamicCordisResolveAck",
    "DynamicCordisRetracted",
    "DynamicCordisRunAttempt",
    "DynamicCordisRunRequest",
    "DynamicCordisRunResolution",
    "DynamicCordisRunResponse",
    "DynamicCordisStopResponse",
    "DynamicCordisUndefineReceipt",
    "RequestRunOutcome",
]

ApprovalRequestId: TypeAlias = object  # port: surface stub

CordisDynamicPackageId: TypeAlias = object  # port: surface stub

CordisDynamicPluginId: TypeAlias = object  # port: surface stub

CordisDynamicPluginRunId: TypeAlias = object  # port: surface stub

CordisDynamicRunMode: TypeAlias = object  # port: surface stub

CordisInspectPlatform: TypeAlias = object  # port: surface stub

CordisInspectQueryResolution: TypeAlias = object  # port: surface stub

CordisInspectRequestId: TypeAlias = object  # port: surface stub

CordisRunStatus: TypeAlias = object  # port: surface stub

DynamicCordisHostHalfResult: TypeAlias = object  # port: surface stub

DynamicCordisInvokeResult: TypeAlias = object  # port: surface stub

DynamicCordisRunResolution: TypeAlias = object  # port: surface stub

DynamicCordisRunResponse: TypeAlias = object  # port: surface stub

DynamicCordisStopResponse: TypeAlias = object  # port: surface stub

DynamicCordisUndefineReceipt: TypeAlias = object  # port: surface stub

RequestRunOutcome: TypeAlias = object  # port: surface stub

class CordisErrorDetails(Protocol):
    """Surface stub for upstream interface ``CordisErrorDetails``."""
    pass

class CordisHalfState(Protocol):
    """Surface stub for upstream interface ``CordisHalfState``."""
    pass

class CordisInspectMethodManifest(Protocol):
    """Surface stub for upstream interface ``CordisInspectMethodManifest``."""
    pass

class CordisInspectProviderManifest(Protocol):
    """Surface stub for upstream interface ``CordisInspectProviderManifest``."""
    pass

class CordisInspectProviderView(Protocol):
    """Surface stub for upstream interface ``CordisInspectProviderView``."""
    pass

class CordisInspectQueryRequest(Protocol):
    """Surface stub for upstream interface ``CordisInspectQueryRequest``."""
    pass

class CordisInspectQueryResolved(Protocol):
    """Surface stub for upstream interface ``CordisInspectQueryResolved``."""
    pass

class CordisInspectResolveAck(Protocol):
    """Surface stub for upstream interface ``CordisInspectResolveAck``."""
    pass

class CordisRunDiagnostic(Protocol):
    """Surface stub for upstream interface ``CordisRunDiagnostic``."""
    pass

class DynamicCordisClientSource(Protocol):
    """Surface stub for upstream interface ``DynamicCordisClientSource``."""
    pass

class DynamicCordisInventoryPackage(Protocol):
    """Surface stub for upstream interface ``DynamicCordisInventoryPackage``."""
    pass

class DynamicCordisInventoryRow(Protocol):
    """Surface stub for upstream interface ``DynamicCordisInventoryRow``."""
    pass

class DynamicCordisPackage(Protocol):
    """Surface stub for upstream interface ``DynamicCordisPackage``."""
    pass

class DynamicCordisRenderFailure(Protocol):
    """Surface stub for upstream interface ``DynamicCordisRenderFailure``."""
    pass

class DynamicCordisRequestResolved(Protocol):
    """Surface stub for upstream interface ``DynamicCordisRequestResolved``."""
    pass

class DynamicCordisResolveAck(Protocol):
    """Surface stub for upstream interface ``DynamicCordisResolveAck``."""
    pass

class DynamicCordisRetracted(Protocol):
    """Surface stub for upstream interface ``DynamicCordisRetracted``."""
    pass

class DynamicCordisRunAttempt(Protocol):
    """Surface stub for upstream interface ``DynamicCordisRunAttempt``."""
    pass

class DynamicCordisRunRequest(Protocol):
    """Surface stub for upstream interface ``DynamicCordisRunRequest``."""
    pass
