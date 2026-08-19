"""Auto-generated surface skeleton for upstream ``subagent/subagent/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "SUBAGENT_DESCRIPTOR_VERSION",
    "AssistantOutputFold",
    "ChildComposition",
    "ContinuableCreateRequest",
    "ContinuableCreateSpec",
    "ContinuableSetupContribution",
    "ContinuableStart",
    "ContinuableStartSpec",
    "ContinuableSubagentDescriptorData",
    "ContinuableSubagentDescriptorInput",
    "CoordinatorMessageSource",
    "DelegatedPolicyOverrides",
    "OneShotSubagentDescriptorData",
    "OneShotSubagentDescriptorInput",
    "ResolvedSubagentStartRequest",
    "SubagentCapabilities",
    "SubagentDepthError",
    "SubagentDescendantListEntry",
    "SubagentDescriptorData",
    "SubagentDescriptorInput",
    "SubagentError",
    "SubagentFollowupOptions",
    "SubagentIdentityProjection",
    "SubagentInterruptAuthority",
    "SubagentListEntry",
    "SubagentProvider",
    "SubagentReportDelivery",
    "SubagentReportMessageSource",
    "SubagentReportOptions",
    "SubagentResult",
    "SubagentRun",
    "SubagentRunEndInfo",
    "SubagentRunId",
    "SubagentRunInfo",
    "SubagentRuntime",
    "SubagentSettledMessageSource",
    "SubagentStartRequest",
    "SubagentStopReason",
    "SubagentStopReasonMap",
    "SubagentTimingProjection",
    "appendDelegatedPolicyOverrides",
    "applyChildComposition",
    "assertSubagentMaxDepth",
    "captureDelegatedPolicyOverrides",
    "childSessionMeta",
    "delegationDepthOf",
    "finalAssistantOutput",
    "foldSubagentDescriptor",
    "resolveChildAgentOptions",
    "resolveChildDepth",
    "seedDescriptorTurn",
    "settleRun",
    "snapshotSubagentDescriptor",
]

ChildComposition: TypeAlias = object  # port: surface stub

ContinuableCreateRequest: TypeAlias = object  # port: surface stub

ContinuableCreateSpec: TypeAlias = object  # port: surface stub

ContinuableSetupContribution: TypeAlias = object  # port: surface stub

ContinuableStart: TypeAlias = object  # port: surface stub

ContinuableStartSpec: TypeAlias = object  # port: surface stub

ContinuableSubagentDescriptorData: TypeAlias = object  # port: surface stub

ContinuableSubagentDescriptorInput: TypeAlias = object  # port: surface stub

CoordinatorMessageSource: TypeAlias = object  # port: surface stub

DelegatedPolicyOverrides: TypeAlias = object  # port: surface stub

OneShotSubagentDescriptorData: TypeAlias = object  # port: surface stub

OneShotSubagentDescriptorInput: TypeAlias = object  # port: surface stub

ResolvedSubagentStartRequest: TypeAlias = object  # port: surface stub

SubagentCapabilities: TypeAlias = object  # port: surface stub

SubagentDescendantListEntry: TypeAlias = object  # port: surface stub

SubagentDescriptorData: TypeAlias = object  # port: surface stub

SubagentDescriptorInput: TypeAlias = object  # port: surface stub

SubagentFollowupOptions: TypeAlias = object  # port: surface stub

SubagentIdentityProjection: TypeAlias = object  # port: surface stub

SubagentInterruptAuthority: TypeAlias = object  # port: surface stub

SubagentListEntry: TypeAlias = object  # port: surface stub

SubagentProvider: TypeAlias = object  # port: surface stub

SubagentReportDelivery: TypeAlias = object  # port: surface stub

SubagentReportMessageSource: TypeAlias = object  # port: surface stub

SubagentReportOptions: TypeAlias = object  # port: surface stub

SubagentResult: TypeAlias = object  # port: surface stub

SubagentRun: TypeAlias = object  # port: surface stub

SubagentRunEndInfo: TypeAlias = object  # port: surface stub

SubagentRunInfo: TypeAlias = object  # port: surface stub

SubagentSettledMessageSource: TypeAlias = object  # port: surface stub

SubagentStartRequest: TypeAlias = object  # port: surface stub

SubagentStopReason: TypeAlias = object  # port: surface stub

SubagentStopReasonMap: TypeAlias = object  # port: surface stub

SubagentTimingProjection: TypeAlias = object  # port: surface stub

class SubagentRuntime:
    """Surface stub for upstream class ``SubagentRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SubagentRuntime.__init__ from subagent/subagent/src/index.ts")

AssistantOutputFold = None  # port: surface stub (reexport)

SUBAGENT_DESCRIPTOR_VERSION = None  # port: surface stub (reexport)

SubagentDepthError = None  # port: surface stub (reexport)

SubagentError = None  # port: surface stub (reexport)

SubagentRunId = None  # port: surface stub (reexport)

appendDelegatedPolicyOverrides = None  # port: surface stub (reexport)

applyChildComposition = None  # port: surface stub (reexport)

assertSubagentMaxDepth = None  # port: surface stub (reexport)

captureDelegatedPolicyOverrides = None  # port: surface stub (reexport)

childSessionMeta = None  # port: surface stub (reexport)

delegationDepthOf = None  # port: surface stub (reexport)

finalAssistantOutput = None  # port: surface stub (reexport)

foldSubagentDescriptor = None  # port: surface stub (reexport)

resolveChildAgentOptions = None  # port: surface stub (reexport)

resolveChildDepth = None  # port: surface stub (reexport)

seedDescriptorTurn = None  # port: surface stub (reexport)

settleRun = None  # port: surface stub (reexport)

snapshotSubagentDescriptor = None  # port: surface stub (reexport)
