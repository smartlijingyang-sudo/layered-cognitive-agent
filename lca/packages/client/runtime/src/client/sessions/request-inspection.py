"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/request-inspection.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/request-inspection.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AssistantProvenanceView",
    "AssistantRequestConfig",
    "ConversationPromptSnapshot",
    "RequestInspectionSnapshot",
    "RequestPromptChange",
    "RequestView",
]

AssistantProvenanceView: TypeAlias = object  # port: surface stub

AssistantRequestConfig: TypeAlias = object  # port: surface stub

RequestView: TypeAlias = object  # port: surface stub

class ConversationPromptSnapshot(Protocol):
    """Surface stub for upstream interface ``ConversationPromptSnapshot``."""
    pass

class RequestInspectionSnapshot(Protocol):
    """Surface stub for upstream interface ``RequestInspectionSnapshot``."""
    pass

class RequestPromptChange(Protocol):
    """Surface stub for upstream interface ``RequestPromptChange``."""
    pass
