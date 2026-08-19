"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/api/sessions.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/api/sessions.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "HistoryEntry",
    "ModelCatalogFailure",
    "ModelCatalogModel",
    "ModelProviderGroup",
    "ModelReasoning",
    "ModelReasoningEffort",
    "ModelSelection",
    "PromptContentPart",
    "QueueAction",
    "SessionListMetadata",
    "SessionModels",
    "SessionProjectionsBlock",
    "SessionSearchItem",
    "SessionSummary",
    "SessionsApi",
]

PromptContentPart: TypeAlias = object  # port: surface stub

QueueAction: TypeAlias = object  # port: surface stub

class HistoryEntry(Protocol):
    """Surface stub for upstream interface ``HistoryEntry``."""
    pass

class ModelCatalogFailure(Protocol):
    """Surface stub for upstream interface ``ModelCatalogFailure``."""
    pass

class ModelCatalogModel(Protocol):
    """Surface stub for upstream interface ``ModelCatalogModel``."""
    pass

class ModelProviderGroup(Protocol):
    """Surface stub for upstream interface ``ModelProviderGroup``."""
    pass

class ModelReasoning(Protocol):
    """Surface stub for upstream interface ``ModelReasoning``."""
    pass

class ModelReasoningEffort(Protocol):
    """Surface stub for upstream interface ``ModelReasoningEffort``."""
    pass

class ModelSelection(Protocol):
    """Surface stub for upstream interface ``ModelSelection``."""
    pass

class SessionListMetadata(Protocol):
    """Surface stub for upstream interface ``SessionListMetadata``."""
    pass

class SessionModels(Protocol):
    """Surface stub for upstream interface ``SessionModels``."""
    pass

class SessionProjectionsBlock(Protocol):
    """Surface stub for upstream interface ``SessionProjectionsBlock``."""
    pass

class SessionSearchItem(Protocol):
    """Surface stub for upstream interface ``SessionSearchItem``."""
    pass

class SessionSummary(Protocol):
    """Surface stub for upstream interface ``SessionSummary``."""
    pass

class SessionsApi(Protocol):
    """Surface stub for upstream interface ``SessionsApi``."""
    pass
