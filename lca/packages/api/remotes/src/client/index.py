"""Auto-generated surface skeleton for upstream ``api/remotes/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``api/remotes/src/client/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "ApiRemoteForwardedEvent",
    "ApprovalRequestId",
    "ClientRemote",
    "ClientResponse",
    "ConfigurableProviderView",
    "ConnectionHandle",
    "ConnectionSinks",
    "ContentBlock",
    "CordisDynamicPackageId",
    "CordisDynamicPluginId",
    "CordisDynamicPluginRunId",
    "CordisDynamicRunMode",
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
    "CredentialView",
    "DirectoryListing",
    "DiscoveredModelView",
    "DynamicCordisClientSource",
    "DynamicCordisHostHalfResult",
    "DynamicCordisInventoryRow",
    "DynamicCordisInvokeResult",
    "DynamicCordisPackage",
    "DynamicCordisRequestResolved",
    "DynamicCordisResolveAck",
    "DynamicCordisRetracted",
    "DynamicCordisRunAttempt",
    "DynamicCordisRunRequest",
    "DynamicCordisRunResolution",
    "DynamicCordisRunResponse",
    "DynamicCordisStopResponse",
    "DynamicCordisUndefineReceipt",
    "HistoryEntry",
    "HostFrame",
    "IApiClient",
    "JobView",
    "JsonValue",
    "MessageId",
    "ModelCatalogFailure",
    "ModelProviderGroup",
    "ModelReasoningEffort",
    "ModelSelection",
    "MuxFrame",
    "PluginInventorySnapshot",
    "PromptContentPart",
    "QuestionResponsePayload",
    "QueueAction",
    "RequestRunOutcome",
    "RpcError",
    "RpcId",
    "RpcReceipt",
    "RpcRequest",
    "RpcResponse",
    "RpcResult",
    "SessionId",
    "SessionModels",
    "SessionSearchItem",
    "SessionSummary",
    "SettingsNamespaceView",
    "SettingsPathOpView",
    "SkillEntry",
    "StreamChunk",
    "SubagentAddress",
    "SubagentCatalog",
    "ToolCallView",
    "ToolEventView",
    "ToolResultView",
    "WorkspaceId",
    "WorkspaceView",
    "apply",
    "inject",
]

ApiRemoteForwardedEvent: TypeAlias = object  # port: surface stub

ApprovalRequestId: TypeAlias = object  # port: surface stub

ClientRemote: TypeAlias = object  # port: surface stub

ClientResponse: TypeAlias = object  # port: surface stub

ConfigurableProviderView: TypeAlias = object  # port: surface stub

ConnectionHandle: TypeAlias = object  # port: surface stub

ConnectionSinks: TypeAlias = object  # port: surface stub

ContentBlock: TypeAlias = object  # port: surface stub

CordisDynamicPackageId: TypeAlias = object  # port: surface stub

CordisDynamicPluginId: TypeAlias = object  # port: surface stub

CordisDynamicPluginRunId: TypeAlias = object  # port: surface stub

CordisDynamicRunMode: TypeAlias = object  # port: surface stub

CordisHalfState: TypeAlias = object  # port: surface stub

CordisInspectMethodManifest: TypeAlias = object  # port: surface stub

CordisInspectPlatform: TypeAlias = object  # port: surface stub

CordisInspectProviderManifest: TypeAlias = object  # port: surface stub

CordisInspectProviderView: TypeAlias = object  # port: surface stub

CordisInspectQueryRequest: TypeAlias = object  # port: surface stub

CordisInspectQueryResolution: TypeAlias = object  # port: surface stub

CordisInspectQueryResolved: TypeAlias = object  # port: surface stub

CordisInspectRequestId: TypeAlias = object  # port: surface stub

CordisInspectResolveAck: TypeAlias = object  # port: surface stub

CordisRunDiagnostic: TypeAlias = object  # port: surface stub

CordisRunStatus: TypeAlias = object  # port: surface stub

CredentialView: TypeAlias = object  # port: surface stub

DirectoryListing: TypeAlias = object  # port: surface stub

DiscoveredModelView: TypeAlias = object  # port: surface stub

DynamicCordisClientSource: TypeAlias = object  # port: surface stub

DynamicCordisHostHalfResult: TypeAlias = object  # port: surface stub

DynamicCordisInventoryRow: TypeAlias = object  # port: surface stub

DynamicCordisInvokeResult: TypeAlias = object  # port: surface stub

DynamicCordisPackage: TypeAlias = object  # port: surface stub

DynamicCordisRequestResolved: TypeAlias = object  # port: surface stub

DynamicCordisResolveAck: TypeAlias = object  # port: surface stub

DynamicCordisRetracted: TypeAlias = object  # port: surface stub

DynamicCordisRunAttempt: TypeAlias = object  # port: surface stub

DynamicCordisRunRequest: TypeAlias = object  # port: surface stub

DynamicCordisRunResolution: TypeAlias = object  # port: surface stub

DynamicCordisRunResponse: TypeAlias = object  # port: surface stub

DynamicCordisStopResponse: TypeAlias = object  # port: surface stub

DynamicCordisUndefineReceipt: TypeAlias = object  # port: surface stub

HistoryEntry: TypeAlias = object  # port: surface stub

HostFrame: TypeAlias = object  # port: surface stub

IApiClient: TypeAlias = object  # port: surface stub

JobView: TypeAlias = object  # port: surface stub

JsonValue: TypeAlias = object  # port: surface stub

MessageId: TypeAlias = object  # port: surface stub

ModelCatalogFailure: TypeAlias = object  # port: surface stub

ModelProviderGroup: TypeAlias = object  # port: surface stub

ModelReasoningEffort: TypeAlias = object  # port: surface stub

ModelSelection: TypeAlias = object  # port: surface stub

MuxFrame: TypeAlias = object  # port: surface stub

PluginInventorySnapshot: TypeAlias = object  # port: surface stub

PromptContentPart: TypeAlias = object  # port: surface stub

QuestionResponsePayload: TypeAlias = object  # port: surface stub

QueueAction: TypeAlias = object  # port: surface stub

RequestRunOutcome: TypeAlias = object  # port: surface stub

RpcError: TypeAlias = object  # port: surface stub

RpcId: TypeAlias = object  # port: surface stub

RpcReceipt: TypeAlias = object  # port: surface stub

RpcRequest: TypeAlias = object  # port: surface stub

RpcResponse: TypeAlias = object  # port: surface stub

RpcResult: TypeAlias = object  # port: surface stub

SessionId: TypeAlias = object  # port: surface stub

SessionModels: TypeAlias = object  # port: surface stub

SessionSearchItem: TypeAlias = object  # port: surface stub

SessionSummary: TypeAlias = object  # port: surface stub

SettingsNamespaceView: TypeAlias = object  # port: surface stub

SettingsPathOpView: TypeAlias = object  # port: surface stub

SkillEntry: TypeAlias = object  # port: surface stub

StreamChunk: TypeAlias = object  # port: surface stub

SubagentAddress: TypeAlias = object  # port: surface stub

SubagentCatalog: TypeAlias = object  # port: surface stub

ToolCallView: TypeAlias = object  # port: surface stub

ToolEventView: TypeAlias = object  # port: surface stub

ToolResultView: TypeAlias = object  # port: surface stub

WorkspaceId: TypeAlias = object  # port: surface stub

WorkspaceView: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from api/remotes/src/client/index.ts")
