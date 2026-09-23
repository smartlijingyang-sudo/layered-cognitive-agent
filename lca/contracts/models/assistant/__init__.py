"""Assistant domain contracts models — AssistantSpec frozen view (ADR-0187 §3 D3)."""

from lca.contracts.models.assistant.spec import (
    PROFILE_RUNTIME_AUTO_REVIEW_MODE,
    PROFILE_RUNTIME_VOCAL_MODE,
    PROFILE_RUNTIME_WAKE_SOURCE,
    AssistantBootstrapRefs,
    AssistantSpec,
)

__all__ = [
    "PROFILE_RUNTIME_AUTO_REVIEW_MODE",
    "PROFILE_RUNTIME_VOCAL_MODE",
    "PROFILE_RUNTIME_WAKE_SOURCE",
    "AssistantBootstrapRefs",
    "AssistantSpec",
    "GraphOverride",
    "PlanOverlay",
    "PromptOverride",
    "SectionOverride",
]
