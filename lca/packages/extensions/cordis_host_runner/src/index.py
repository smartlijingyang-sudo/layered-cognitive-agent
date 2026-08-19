"""Auto-generated surface skeleton for upstream ``extensions/cordis-host-runner/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-host-runner/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "HOST_BUILTIN_INSPECTION",
    "ApprovalRequestId",
    "Config",
    "CordisDynamicPackageId",
    "CordisDynamicPluginId",
    "CordisDynamicPluginRunId",
    "CordisInspectRegistryService",
    "DynamicCordisDefineReceipt",
    "DynamicCordisDefineRequest",
    "DynamicCordisDefinition",
    "DynamicCordisHandler",
    "DynamicCordisPackageInspection",
    "DynamicCordisPlugin",
    "DynamicCordisPluginInspection",
    "DynamicCordisReference",
    "DynamicCordisRun",
    "DynamicCordisRunnerService",
    "DynamicCordisSnapshotRow",
    "HostCordisInspectProviderRegistration",
]

DynamicCordisDefineReceipt: TypeAlias = object  # port: surface stub

DynamicCordisDefineRequest: TypeAlias = object  # port: surface stub

DynamicCordisDefinition: TypeAlias = object  # port: surface stub

DynamicCordisHandler: TypeAlias = object  # port: surface stub

DynamicCordisPackageInspection: TypeAlias = object  # port: surface stub

DynamicCordisPlugin: TypeAlias = object  # port: surface stub

DynamicCordisPluginInspection: TypeAlias = object  # port: surface stub

DynamicCordisReference: TypeAlias = object  # port: surface stub

DynamicCordisRun: TypeAlias = object  # port: surface stub

HostCordisInspectProviderRegistration: TypeAlias = object  # port: surface stub

def ApprovalRequestId(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``ApprovalRequestId``."""
    raise NotImplementedError("port ApprovalRequestId from extensions/cordis-host-runner/src/index.ts")

def CordisDynamicPackageId(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``CordisDynamicPackageId``."""
    raise NotImplementedError("port CordisDynamicPackageId from extensions/cordis-host-runner/src/index.ts")

def CordisDynamicPluginId(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``CordisDynamicPluginId``."""
    raise NotImplementedError("port CordisDynamicPluginId from extensions/cordis-host-runner/src/index.ts")

def CordisDynamicPluginRunId(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``CordisDynamicPluginRunId``."""
    raise NotImplementedError("port CordisDynamicPluginRunId from extensions/cordis-host-runner/src/index.ts")

class DynamicCordisRunnerService:
    """Surface stub for upstream class ``DynamicCordisRunnerService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DynamicCordisRunnerService.__init__ from extensions/cordis-host-runner/src/index.ts")

CordisInspectRegistryService = None  # port: surface stub (reexport)

HOST_BUILTIN_INSPECTION = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class DynamicCordisSnapshotRow(Protocol):
    """Surface stub for upstream interface ``DynamicCordisSnapshotRow``."""
    pass
