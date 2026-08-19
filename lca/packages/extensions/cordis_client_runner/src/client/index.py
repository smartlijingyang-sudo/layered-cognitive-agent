"""Auto-generated surface skeleton for upstream ``extensions/cordis-client-runner/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-client-runner/src/client/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ApprovalRequestId",
    "ClientCordisInspectHost",
    "ClientCordisInspectProviderRegistration",
    "ClientCordisInspectQueryContext",
    "ClientCordisInspectRegistry",
    "ClientTimerService",
    "CordisDynamicPackageId",
    "CordisDynamicPluginId",
    "CordisDynamicPluginRunId",
    "CordisObservable",
    "CordisRunActivity",
    "CordisRunFailure",
    "CordisRunHostSeam",
    "CordisRunOrchestrator",
    "CordisRunOrchestratorEnv",
    "CordisRunRequest",
    "CordisRunnerFace",
    "CordisUserRunRequest",
    "DynamicCordisClientHalf",
    "DynamicCordisClosureEnv",
    "DynamicCordisEvaluatedPlugin",
    "DynamicCordisGuardEnv",
    "DynamicCordisLivePackage",
    "DynamicCordisLoadErrorCause",
    "DynamicCordisLoadResult",
    "DynamicCordisPackage",
    "DynamicCordisPackageRunner",
    "DynamicCordisRenderFailure",
    "DynamicCordisRunnerEnv",
    "DynamicCordisSlotLedgerRow",
    "DynamicCordisStyles",
    "apply",
    "dynamicCordisContext",
    "evaluateClientHalf",
    "inject",
    "isDynamicCordisPlugin",
    "name",
]

ApprovalRequestId: TypeAlias = object  # port: surface stub

ClientCordisInspectHost: TypeAlias = object  # port: surface stub

ClientCordisInspectProviderRegistration: TypeAlias = object  # port: surface stub

ClientCordisInspectQueryContext: TypeAlias = object  # port: surface stub

CordisDynamicPackageId: TypeAlias = object  # port: surface stub

CordisDynamicPluginId: TypeAlias = object  # port: surface stub

CordisDynamicPluginRunId: TypeAlias = object  # port: surface stub

CordisObservable: TypeAlias = object  # port: surface stub

CordisRunActivity: TypeAlias = object  # port: surface stub

CordisRunFailure: TypeAlias = object  # port: surface stub

CordisRunHostSeam: TypeAlias = object  # port: surface stub

CordisRunOrchestratorEnv: TypeAlias = object  # port: surface stub

CordisRunRequest: TypeAlias = object  # port: surface stub

CordisUserRunRequest: TypeAlias = object  # port: surface stub

DynamicCordisClientHalf: TypeAlias = object  # port: surface stub

DynamicCordisClosureEnv: TypeAlias = object  # port: surface stub

DynamicCordisEvaluatedPlugin: TypeAlias = object  # port: surface stub

DynamicCordisGuardEnv: TypeAlias = object  # port: surface stub

DynamicCordisLivePackage: TypeAlias = object  # port: surface stub

DynamicCordisLoadErrorCause: TypeAlias = object  # port: surface stub

DynamicCordisLoadResult: TypeAlias = object  # port: surface stub

DynamicCordisPackage: TypeAlias = object  # port: surface stub

DynamicCordisRenderFailure: TypeAlias = object  # port: surface stub

DynamicCordisRunnerEnv: TypeAlias = object  # port: surface stub

DynamicCordisSlotLedgerRow: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from extensions/cordis-client-runner/src/client/index.ts")

ClientCordisInspectRegistry = None  # port: surface stub (reexport)

ClientTimerService = None  # port: surface stub (reexport)

CordisRunOrchestrator = None  # port: surface stub (reexport)

DynamicCordisPackageRunner = None  # port: surface stub (reexport)

DynamicCordisStyles = None  # port: surface stub (reexport)

dynamicCordisContext = None  # port: surface stub (reexport)

evaluateClientHalf = None  # port: surface stub (reexport)

isDynamicCordisPlugin = None  # port: surface stub (reexport)

class CordisRunnerFace(Protocol):
    """Surface stub for upstream interface ``CordisRunnerFace``."""
    pass
