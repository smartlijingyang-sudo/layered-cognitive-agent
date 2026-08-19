"""Auto-generated surface skeleton for upstream ``client/connection/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/connection/src/client/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AbstractApiClient",
    "ApiProxy",
    "ApprovalResponsePayload",
    "ClientConnectionRpc",
    "ClientRequest",
    "ClientResponse",
    "ConfigurableProviderView",
    "ConnectionConfig",
    "ConnectionHandle",
    "ConnectionSinks",
    "ConnectionState",
    "ContentBlock",
    "CredentialView",
    "CredentialsApi",
    "DirectoryEntry",
    "DirectoryListing",
    "DiscoveredModelView",
    "EventsApi",
    "GoalRef",
    "GoalsApi",
    "HistoryEntry",
    "HostApi",
    "HostDescription",
    "HostDescriptionSource",
    "HostFrame",
    "IApiClient",
    "JobView",
    "LlmApi",
    "MessageId",
    "ModelCatalogFailure",
    "ModelCatalogModel",
    "ModelProviderGroup",
    "ModelReasoning",
    "ModelReasoningEffort",
    "ModelSelection",
    "MuxFrame",
    "PromptContentPart",
    "QuestionResponsePayload",
    "QueueAction",
    "QueuedInboxItem",
    "RpcError",
    "RpcErrorCode",
    "RpcId",
    "RpcMessage",
    "RpcReceipt",
    "RpcRequest",
    "RpcResponse",
    "RpcResult",
    "ServerRequest",
    "ServerResponse",
    "SessionEvent",
    "SessionId",
    "SessionModels",
    "SessionSearchItem",
    "SessionSummary",
    "SessionsApi",
    "SettingsApi",
    "SettingsNamespaceView",
    "SettingsPathOpView",
    "SettingsSecretView",
    "SkillEntry",
    "SkillsApi",
    "StreamChunk",
    "SubagentAddress",
    "SubagentCatalog",
    "SubagentListEntry",
    "SubagentPromptReceipt",
    "SubagentsApi",
    "ToolCallView",
    "ToolEventView",
    "ToolResultView",
    "WorkspaceApi",
    "WorkspaceId",
    "WorkspaceView",
    "apply",
    "inject",
    "transportError",
]

ApiProxy: TypeAlias = object  # port: surface stub

ApprovalResponsePayload: TypeAlias = object  # port: surface stub

ClientConnectionRpc: TypeAlias = object  # port: surface stub

ClientRequest: TypeAlias = object  # port: surface stub

ClientResponse: TypeAlias = object  # port: surface stub

ConfigurableProviderView: TypeAlias = object  # port: surface stub

ConnectionConfig: TypeAlias = object  # port: surface stub

ConnectionSinks: TypeAlias = object  # port: surface stub

ConnectionState: TypeAlias = object  # port: surface stub

ContentBlock: TypeAlias = object  # port: surface stub

CredentialView: TypeAlias = object  # port: surface stub

CredentialsApi: TypeAlias = object  # port: surface stub

DirectoryEntry: TypeAlias = object  # port: surface stub

DirectoryListing: TypeAlias = object  # port: surface stub

DiscoveredModelView: TypeAlias = object  # port: surface stub

EventsApi: TypeAlias = object  # port: surface stub

GoalRef: TypeAlias = object  # port: surface stub

GoalsApi: TypeAlias = object  # port: surface stub

HistoryEntry: TypeAlias = object  # port: surface stub

HostApi: TypeAlias = object  # port: surface stub

HostDescription: TypeAlias = object  # port: surface stub

HostFrame: TypeAlias = object  # port: surface stub

IApiClient: TypeAlias = object  # port: surface stub

JobView: TypeAlias = object  # port: surface stub

LlmApi: TypeAlias = object  # port: surface stub

MessageId: TypeAlias = object  # port: surface stub

ModelCatalogFailure: TypeAlias = object  # port: surface stub

ModelCatalogModel: TypeAlias = object  # port: surface stub

ModelProviderGroup: TypeAlias = object  # port: surface stub

ModelReasoning: TypeAlias = object  # port: surface stub

ModelReasoningEffort: TypeAlias = object  # port: surface stub

ModelSelection: TypeAlias = object  # port: surface stub

MuxFrame: TypeAlias = object  # port: surface stub

PromptContentPart: TypeAlias = object  # port: surface stub

QuestionResponsePayload: TypeAlias = object  # port: surface stub

QueueAction: TypeAlias = object  # port: surface stub

QueuedInboxItem: TypeAlias = object  # port: surface stub

RpcError: TypeAlias = object  # port: surface stub

RpcErrorCode: TypeAlias = object  # port: surface stub

RpcMessage: TypeAlias = object  # port: surface stub

RpcReceipt: TypeAlias = object  # port: surface stub

RpcRequest: TypeAlias = object  # port: surface stub

RpcResponse: TypeAlias = object  # port: surface stub

RpcResult: TypeAlias = object  # port: surface stub

ServerRequest: TypeAlias = object  # port: surface stub

ServerResponse: TypeAlias = object  # port: surface stub

SessionEvent: TypeAlias = object  # port: surface stub

SessionId: TypeAlias = object  # port: surface stub

SessionModels: TypeAlias = object  # port: surface stub

SessionSearchItem: TypeAlias = object  # port: surface stub

SessionSummary: TypeAlias = object  # port: surface stub

SessionsApi: TypeAlias = object  # port: surface stub

SettingsApi: TypeAlias = object  # port: surface stub

SettingsNamespaceView: TypeAlias = object  # port: surface stub

SettingsPathOpView: TypeAlias = object  # port: surface stub

SettingsSecretView: TypeAlias = object  # port: surface stub

SkillEntry: TypeAlias = object  # port: surface stub

SkillsApi: TypeAlias = object  # port: surface stub

StreamChunk: TypeAlias = object  # port: surface stub

SubagentAddress: TypeAlias = object  # port: surface stub

SubagentCatalog: TypeAlias = object  # port: surface stub

SubagentListEntry: TypeAlias = object  # port: surface stub

SubagentPromptReceipt: TypeAlias = object  # port: surface stub

SubagentsApi: TypeAlias = object  # port: surface stub

ToolCallView: TypeAlias = object  # port: surface stub

ToolEventView: TypeAlias = object  # port: surface stub

ToolResultView: TypeAlias = object  # port: surface stub

WorkspaceApi: TypeAlias = object  # port: surface stub

WorkspaceId: TypeAlias = object  # port: surface stub

WorkspaceView: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/connection/src/client/index.ts")

AbstractApiClient = None  # port: surface stub (reexport)

RpcId = None  # port: surface stub (reexport)

transportError = None  # port: surface stub (reexport)

class ConnectionHandle(Protocol):
    """Surface stub for upstream interface ``ConnectionHandle``."""
    pass

class HostDescriptionSource(Protocol):
    """Surface stub for upstream interface ``HostDescriptionSource``."""
    pass
