"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentContext",
    "AgentScopeHandle",
    "AssistantBlock",
    "AssistantMessageNode",
    "AssistantProvenanceView",
    "AssistantRequestConfig",
    "AssistantTiming",
    "ChatConversationViewNode",
    "ChatLocationNodeIndex",
    "ChatNodeStore",
    "ChatSnapshot",
    "ClientContext",
    "CommandNode",
    "CompactionSummaryNode",
    "ComposerPhase",
    "ContextMessageNode",
    "ContextProvenanceView",
    "ContextRole",
    "ConversationContext",
    "ConversationContextOriginKind",
    "ConversationContextReader",
    "ConversationEventInput",
    "ConversationEventRegistry",
    "ConversationLocation",
    "ConversationLocationData",
    "ConversationLocationDataScope",
    "ConversationLocationDataStore",
    "ConversationLocationIndex",
    "ConversationMatch",
    "ConversationMatchResult",
    "ConversationNode",
    "ConversationNodeAssembler",
    "ConversationNodeContext",
    "ConversationNodeDefinition",
    "ConversationPreviousContext",
    "ConversationPromptSnapshot",
    "ConversationPublication",
    "ConversationRuntime",
    "ConversationSnapshot",
    "ConversationStepDataMap",
    "ConversationTimelineSnapshot",
    "ConversationTurnDataMap",
    "ConversationViewBuilder",
    "ConversationViewDefinition",
    "ConversationViewNode",
    "ConversationViewRegistry",
    "ConversationViewSnapshotMap",
    "ConversationViewSnapshotStore",
    "DirectoryBrowseError",
    "DirectoryEntry",
    "DirectoryListing",
    "EMPTY_CHAT_SNAPSHOT",
    "EMPTY_CONVERSATION_VIEWS",
    "EngineStoreHandle",
    "EngineStoreInstance",
    "ISession",
    "ISessions",
    "IWorkspaces",
    "JobView",
    "KnownContextForm",
    "LegacyConversationSlice",
    "ModelRetryNode",
    "ObservableSnapshot",
    "PartialAssistant",
    "PendingInteraction",
    "PendingInteractionStatus",
    "PendingKind",
    "PendingPayloads",
    "PendingWait",
    "ProjectionValueStore",
    "ProjectionsBaseline",
    "ProjectionsFace",
    "QueuedMessage",
    "RequestInspectionSnapshot",
    "RequestPromptChange",
    "RequestView",
    "RootOwnerProps",
    "RunningToolCall",
    "Session",
    "SessionBinding",
    "SessionCreateError",
    "SessionFace",
    "SessionId",
    "SessionListPhase",
    "SessionListState",
    "SessionProjectionMap",
    "SessionProvideChannel",
    "SessionProvideChannelHost",
    "SessionProvideContribution",
    "SessionProvideDescriptor",
    "SessionRuntime",
    "SessionSearchResultItem",
    "SessionSummary",
    "SettingsScope",
    "SettingsScopeSnapshot",
    "SettingsScopeSpec",
    "SlotRegistry",
    "SnapshotStore",
    "SteeringMessageNode",
    "StepLocation",
    "SubagentAddress",
    "SubagentCatalogSnapshot",
    "SubagentDescendantSummary",
    "TodoItem",
    "ToolCallBlock",
    "ToolResultNode",
    "TurnErrorNode",
    "TurnLocation",
    "TurnMaxTokensNode",
    "UnknownSurfaceNode",
    "UseConversationSession",
    "UseProjection",
    "UserMessageNode",
    "WorkspaceCreateError",
    "WorkspaceId",
    "WorkspaceListPhase",
    "WorkspaceListState",
    "WorkspaceRuntime",
    "WorkspaceView",
    "apply",
    "contextForm",
    "contextProvenance",
    "conversationContextKey",
    "createScope",
    "createSnapshotStore",
    "defineStore",
    "displayFailureMessage",
    "emptyAssistantBlock",
    "indexSubagentDescendants",
    "inject",
    "isAppendSurfaceEvent",
    "isReplacementSurfaceEvent",
    "isTokenDelta",
    "resolveWorkspacePath",
    "scopeOf",
    "shallowEqual",
    "toAssistantBlock",
    "toAssistantBlocks",
    "workspaceTitleOf",
]

AgentContext: TypeAlias = object  # port: surface stub

AgentScopeHandle: TypeAlias = object  # port: surface stub

AssistantBlock: TypeAlias = object  # port: surface stub

AssistantMessageNode: TypeAlias = object  # port: surface stub

AssistantProvenanceView: TypeAlias = object  # port: surface stub

AssistantRequestConfig: TypeAlias = object  # port: surface stub

AssistantTiming: TypeAlias = object  # port: surface stub

ChatConversationViewNode: TypeAlias = object  # port: surface stub

ChatLocationNodeIndex: TypeAlias = object  # port: surface stub

ChatNodeStore: TypeAlias = object  # port: surface stub

ChatSnapshot: TypeAlias = object  # port: surface stub

ClientContext: TypeAlias = object  # port: surface stub

CommandNode: TypeAlias = object  # port: surface stub

CompactionSummaryNode: TypeAlias = object  # port: surface stub

ComposerPhase: TypeAlias = object  # port: surface stub

ContextMessageNode: TypeAlias = object  # port: surface stub

ContextProvenanceView: TypeAlias = object  # port: surface stub

ContextRole: TypeAlias = object  # port: surface stub

ConversationContext: TypeAlias = object  # port: surface stub

ConversationContextOriginKind: TypeAlias = object  # port: surface stub

ConversationContextReader: TypeAlias = object  # port: surface stub

ConversationEventInput: TypeAlias = object  # port: surface stub

ConversationLocation: TypeAlias = object  # port: surface stub

ConversationLocationData: TypeAlias = object  # port: surface stub

ConversationLocationDataScope: TypeAlias = object  # port: surface stub

ConversationLocationDataStore: TypeAlias = object  # port: surface stub

ConversationMatch: TypeAlias = object  # port: surface stub

ConversationMatchResult: TypeAlias = object  # port: surface stub

ConversationNode: TypeAlias = object  # port: surface stub

ConversationNodeContext: TypeAlias = object  # port: surface stub

ConversationNodeDefinition: TypeAlias = object  # port: surface stub

ConversationPreviousContext: TypeAlias = object  # port: surface stub

ConversationPromptSnapshot: TypeAlias = object  # port: surface stub

ConversationPublication: TypeAlias = object  # port: surface stub

ConversationRuntime: TypeAlias = object  # port: surface stub

ConversationSnapshot: TypeAlias = object  # port: surface stub

ConversationStepDataMap: TypeAlias = object  # port: surface stub

ConversationTimelineSnapshot: TypeAlias = object  # port: surface stub

ConversationTurnDataMap: TypeAlias = object  # port: surface stub

ConversationViewBuilder: TypeAlias = object  # port: surface stub

ConversationViewDefinition: TypeAlias = object  # port: surface stub

ConversationViewNode: TypeAlias = object  # port: surface stub

ConversationViewSnapshotMap: TypeAlias = object  # port: surface stub

ConversationViewSnapshotStore: TypeAlias = object  # port: surface stub

DirectoryEntry: TypeAlias = object  # port: surface stub

DirectoryListing: TypeAlias = object  # port: surface stub

EngineStoreHandle: TypeAlias = object  # port: surface stub

EngineStoreInstance: TypeAlias = object  # port: surface stub

ISession: TypeAlias = object  # port: surface stub

ISessions: TypeAlias = object  # port: surface stub

IWorkspaces: TypeAlias = object  # port: surface stub

JobView: TypeAlias = object  # port: surface stub

KnownContextForm: TypeAlias = object  # port: surface stub

LegacyConversationSlice: TypeAlias = object  # port: surface stub

ModelRetryNode: TypeAlias = object  # port: surface stub

ObservableSnapshot: TypeAlias = object  # port: surface stub

PartialAssistant: TypeAlias = object  # port: surface stub

PendingInteraction: TypeAlias = object  # port: surface stub

PendingInteractionStatus: TypeAlias = object  # port: surface stub

PendingKind: TypeAlias = object  # port: surface stub

PendingPayloads: TypeAlias = object  # port: surface stub

ProjectionValueStore: TypeAlias = object  # port: surface stub

ProjectionsBaseline: TypeAlias = object  # port: surface stub

ProjectionsFace: TypeAlias = object  # port: surface stub

QueuedMessage: TypeAlias = object  # port: surface stub

RequestInspectionSnapshot: TypeAlias = object  # port: surface stub

RequestPromptChange: TypeAlias = object  # port: surface stub

RequestView: TypeAlias = object  # port: surface stub

RootOwnerProps: TypeAlias = object  # port: surface stub

RunningToolCall: TypeAlias = object  # port: surface stub

Session: TypeAlias = object  # port: surface stub

SessionBinding: TypeAlias = object  # port: surface stub

SessionFace: TypeAlias = object  # port: surface stub

SessionId: TypeAlias = object  # port: surface stub

SessionListPhase: TypeAlias = object  # port: surface stub

SessionListState: TypeAlias = object  # port: surface stub

SessionProjectionMap: TypeAlias = object  # port: surface stub

SessionProvideChannelHost: TypeAlias = object  # port: surface stub

SessionProvideContribution: TypeAlias = object  # port: surface stub

SessionProvideDescriptor: TypeAlias = object  # port: surface stub

SessionSearchResultItem: TypeAlias = object  # port: surface stub

SessionSummary: TypeAlias = object  # port: surface stub

SettingsScope: TypeAlias = object  # port: surface stub

SettingsScopeSnapshot: TypeAlias = object  # port: surface stub

SettingsScopeSpec: TypeAlias = object  # port: surface stub

SnapshotStore: TypeAlias = object  # port: surface stub

SteeringMessageNode: TypeAlias = object  # port: surface stub

StepLocation: TypeAlias = object  # port: surface stub

SubagentAddress: TypeAlias = object  # port: surface stub

SubagentCatalogSnapshot: TypeAlias = object  # port: surface stub

SubagentDescendantSummary: TypeAlias = object  # port: surface stub

TodoItem: TypeAlias = object  # port: surface stub

ToolCallBlock: TypeAlias = object  # port: surface stub

ToolResultNode: TypeAlias = object  # port: surface stub

TurnErrorNode: TypeAlias = object  # port: surface stub

TurnLocation: TypeAlias = object  # port: surface stub

TurnMaxTokensNode: TypeAlias = object  # port: surface stub

UnknownSurfaceNode: TypeAlias = object  # port: surface stub

UseConversationSession: TypeAlias = object  # port: surface stub

UseProjection: TypeAlias = object  # port: surface stub

UserMessageNode: TypeAlias = object  # port: surface stub

WorkspaceId: TypeAlias = object  # port: surface stub

WorkspaceListPhase: TypeAlias = object  # port: surface stub

WorkspaceListState: TypeAlias = object  # port: surface stub

WorkspaceView: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/runtime/src/client/index.ts")

ConversationEventRegistry = None  # port: surface stub (reexport)

ConversationLocationIndex = None  # port: surface stub (reexport)

ConversationNodeAssembler = None  # port: surface stub (reexport)

ConversationViewRegistry = None  # port: surface stub (reexport)

DirectoryBrowseError = None  # port: surface stub (reexport)

EMPTY_CHAT_SNAPSHOT = None  # port: surface stub (reexport)

EMPTY_CONVERSATION_VIEWS = None  # port: surface stub (reexport)

PendingWait = None  # port: surface stub (reexport)

SessionCreateError = None  # port: surface stub (reexport)

SessionProvideChannel = None  # port: surface stub (reexport)

SessionRuntime = None  # port: surface stub (reexport)

SlotRegistry = None  # port: surface stub (reexport)

WorkspaceCreateError = None  # port: surface stub (reexport)

WorkspaceRuntime = None  # port: surface stub (reexport)

contextForm = None  # port: surface stub (reexport)

contextProvenance = None  # port: surface stub (reexport)

conversationContextKey = None  # port: surface stub (reexport)

createScope = None  # port: surface stub (reexport)

createSnapshotStore = None  # port: surface stub (reexport)

defineStore = None  # port: surface stub (reexport)

displayFailureMessage = None  # port: surface stub (reexport)

emptyAssistantBlock = None  # port: surface stub (reexport)

indexSubagentDescendants = None  # port: surface stub (reexport)

isAppendSurfaceEvent = None  # port: surface stub (reexport)

isReplacementSurfaceEvent = None  # port: surface stub (reexport)

isTokenDelta = None  # port: surface stub (reexport)

resolveWorkspacePath = None  # port: surface stub (reexport)

scopeOf = None  # port: surface stub (reexport)

shallowEqual = None  # port: surface stub (reexport)

toAssistantBlock = None  # port: surface stub (reexport)

toAssistantBlocks = None  # port: surface stub (reexport)

workspaceTitleOf = None  # port: surface stub (reexport)
