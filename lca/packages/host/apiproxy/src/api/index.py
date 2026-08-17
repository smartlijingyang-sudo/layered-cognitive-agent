"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/api/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/api/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentPresetEntry",
    "AgentPresetsApi",
    "ApiProxy",
    "ApprovalResponsePayload",
    "ClientRequest",
    "ClientResponse",
    "ConfigurableProviderView",
    "CredentialView",
    "CredentialsApi",
    "DirectoryEntry",
    "DirectoryListing",
    "DiscoveredModelView",
    "DownloadsApi",
    "EventsApi",
    "GoalId",
    "GoalRef",
    "GoalsApi",
    "HistoryEntry",
    "HostApi",
    "HostFrame",
    "JobView",
    "LlmApi",
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
    "RequestPayload",
    "ResponseValue",
    "RpcError",
    "RpcErrorCode",
    "RpcErrorDetailsMap",
    "RpcId",
    "RpcMessage",
    "RpcMethodMap",
    "RpcReceipt",
    "RpcRequest",
    "RpcResponse",
    "RpcResult",
    "SESSION_SEARCH_RESULT_LIMIT",
    "SESSION_SEARCH_SNIPPET_MAX_CODE_POINTS",
    "ServerRequest",
    "ServerResponse",
    "SessionListMetadata",
    "SessionModels",
    "SessionProjectionsBlock",
    "SessionSearchItem",
    "SessionSummary",
    "SessionsApi",
    "SettingsApi",
    "SettingsNamespaceView",
    "SettingsPathOpView",
    "SettingsSecretView",
    "SkillEntry",
    "SkillsApi",
    "SubagentAddress",
    "SubagentCatalog",
    "SubagentInterruptReceipt",
    "SubagentListEntry",
    "SubagentPromptReceipt",
    "SubagentsApi",
    "ToolCallView",
    "ToolEventView",
    "ToolResultView",
    "WorkspaceApi",
    "WorkspaceId",
    "WorkspaceView",
    "clientRequestSchema",
    "serverRequestSchema",
    "serverResponseSchema",
    "transportError",
]

AgentPresetEntry: TypeAlias = object  # port: surface stub

AgentPresetsApi: TypeAlias = object  # port: surface stub

ApprovalResponsePayload: TypeAlias = object  # port: surface stub

ClientRequest: TypeAlias = object  # port: surface stub

ClientResponse: TypeAlias = object  # port: surface stub

ConfigurableProviderView: TypeAlias = object  # port: surface stub

CredentialView: TypeAlias = object  # port: surface stub

CredentialsApi: TypeAlias = object  # port: surface stub

DirectoryEntry: TypeAlias = object  # port: surface stub

DirectoryListing: TypeAlias = object  # port: surface stub

DiscoveredModelView: TypeAlias = object  # port: surface stub

DownloadsApi: TypeAlias = object  # port: surface stub

EventsApi: TypeAlias = object  # port: surface stub

GoalId: TypeAlias = object  # port: surface stub

GoalRef: TypeAlias = object  # port: surface stub

GoalsApi: TypeAlias = object  # port: surface stub

HistoryEntry: TypeAlias = object  # port: surface stub

HostApi: TypeAlias = object  # port: surface stub

HostFrame: TypeAlias = object  # port: surface stub

JobView: TypeAlias = object  # port: surface stub

LlmApi: TypeAlias = object  # port: surface stub

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

RequestPayload: TypeAlias = object  # port: surface stub

ResponseValue: TypeAlias = object  # port: surface stub

RpcError: TypeAlias = object  # port: surface stub

RpcErrorCode: TypeAlias = object  # port: surface stub

RpcErrorDetailsMap: TypeAlias = object  # port: surface stub

RpcMessage: TypeAlias = object  # port: surface stub

RpcMethodMap: TypeAlias = object  # port: surface stub

RpcReceipt: TypeAlias = object  # port: surface stub

RpcRequest: TypeAlias = object  # port: surface stub

RpcResponse: TypeAlias = object  # port: surface stub

RpcResult: TypeAlias = object  # port: surface stub

ServerRequest: TypeAlias = object  # port: surface stub

ServerResponse: TypeAlias = object  # port: surface stub

SessionListMetadata: TypeAlias = object  # port: surface stub

SessionModels: TypeAlias = object  # port: surface stub

SessionProjectionsBlock: TypeAlias = object  # port: surface stub

SessionSearchItem: TypeAlias = object  # port: surface stub

SessionSummary: TypeAlias = object  # port: surface stub

SessionsApi: TypeAlias = object  # port: surface stub

SettingsApi: TypeAlias = object  # port: surface stub

SettingsNamespaceView: TypeAlias = object  # port: surface stub

SettingsPathOpView: TypeAlias = object  # port: surface stub

SettingsSecretView: TypeAlias = object  # port: surface stub

SkillEntry: TypeAlias = object  # port: surface stub

SkillsApi: TypeAlias = object  # port: surface stub

SubagentAddress: TypeAlias = object  # port: surface stub

SubagentCatalog: TypeAlias = object  # port: surface stub

SubagentInterruptReceipt: TypeAlias = object  # port: surface stub

SubagentListEntry: TypeAlias = object  # port: surface stub

SubagentPromptReceipt: TypeAlias = object  # port: surface stub

SubagentsApi: TypeAlias = object  # port: surface stub

ToolCallView: TypeAlias = object  # port: surface stub

ToolEventView: TypeAlias = object  # port: surface stub

ToolResultView: TypeAlias = object  # port: surface stub

WorkspaceApi: TypeAlias = object  # port: surface stub

WorkspaceId: TypeAlias = object  # port: surface stub

WorkspaceView: TypeAlias = object  # port: surface stub

RpcId = None  # port: surface stub (reexport)

SESSION_SEARCH_RESULT_LIMIT = None  # port: surface stub (reexport)

SESSION_SEARCH_SNIPPET_MAX_CODE_POINTS = None  # port: surface stub (reexport)

clientRequestSchema = None  # port: surface stub (reexport)

serverRequestSchema = None  # port: surface stub (reexport)

serverResponseSchema = None  # port: surface stub (reexport)

transportError = None  # port: surface stub (reexport)

class ApiProxy(Protocol):
    """Surface stub for upstream interface ``ApiProxy``."""
    pass
