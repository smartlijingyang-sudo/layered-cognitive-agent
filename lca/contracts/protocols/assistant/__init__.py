"""Assistant domain Protocols — AssistantCatalog thin facade (ADR-0187 §3 D4)."""

from lca.contracts.protocols.assistant.catalog import (
    AssistantCatalog,
    AssistantHandle,
    AssistantSummary,
    CreateAssistantRequest,
    PlanRevision,
    ProfilePatch,
)

__all__ = [
    "AssistantCatalog",
    "AssistantHandle",
    "AssistantSummary",
    "CreateAssistantRequest",
    "PlanRevision",
    "ProfilePatch",
]
