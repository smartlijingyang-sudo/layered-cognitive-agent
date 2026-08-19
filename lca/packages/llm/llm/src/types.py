"""Auto-generated surface skeleton for upstream ``llm/llm/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AssistantMessage",
    "AssistantProvenance",
    "ContentBlock",
    "ContentBlockMap",
    "ContentBlockType",
    "FinishReason",
    "FinishReasonMap",
    "GenerateOptions",
    "ImageBlock",
    "LlmConfigurableProvider",
    "LlmDiscoveredModel",
    "LlmFailure",
    "LlmModelContext",
    "LlmModelDiscoveryRequest",
    "LlmModelInfo",
    "LlmModelReasoningInfo",
    "LlmProviderInfo",
    "LlmReasoningEffortInfo",
    "LlmResolvedModelInfo",
    "Message",
    "MessageSource",
    "MessageSourceMap",
    "ModelMessageSource",
    "ModelModality",
    "ModelModalityMap",
    "ReasoningBlock",
    "StreamChunk",
    "TextBlock",
    "TokenUsage",
    "ToolCallBlock",
    "ToolMessageSource",
    "ToolResultBlock",
    "ToolResultMessage",
    "ToolSchema",
    "UserMessage",
]

AssistantMessage: TypeAlias = object  # port: surface stub

AssistantProvenance: TypeAlias = object  # port: surface stub

ContentBlock: TypeAlias = object  # port: surface stub

ContentBlockType: TypeAlias = object  # port: surface stub

FinishReason: TypeAlias = object  # port: surface stub

Message: TypeAlias = object  # port: surface stub

MessageSource: TypeAlias = object  # port: surface stub

MessageSourceMap: TypeAlias = object  # port: surface stub

ModelMessageSource: TypeAlias = object  # port: surface stub

ModelModality: TypeAlias = object  # port: surface stub

StreamChunk: TypeAlias = object  # port: surface stub

ToolMessageSource: TypeAlias = object  # port: surface stub

ToolResultMessage: TypeAlias = object  # port: surface stub

UserMessage: TypeAlias = object  # port: surface stub

class ContentBlockMap(Protocol):
    """Surface stub for upstream interface ``ContentBlockMap``."""
    pass

class FinishReasonMap(Protocol):
    """Surface stub for upstream interface ``FinishReasonMap``."""
    pass

class GenerateOptions(Protocol):
    """Surface stub for upstream interface ``GenerateOptions``."""
    pass

class ImageBlock(Protocol):
    """Surface stub for upstream interface ``ImageBlock``."""
    pass

class LlmConfigurableProvider(Protocol):
    """Surface stub for upstream interface ``LlmConfigurableProvider``."""
    pass

class LlmDiscoveredModel(Protocol):
    """Surface stub for upstream interface ``LlmDiscoveredModel``."""
    pass

class LlmFailure(Protocol):
    """Surface stub for upstream interface ``LlmFailure``."""
    pass

class LlmModelContext(Protocol):
    """Surface stub for upstream interface ``LlmModelContext``."""
    pass

class LlmModelDiscoveryRequest(Protocol):
    """Surface stub for upstream interface ``LlmModelDiscoveryRequest``."""
    pass

class LlmModelInfo(Protocol):
    """Surface stub for upstream interface ``LlmModelInfo``."""
    pass

class LlmModelReasoningInfo(Protocol):
    """Surface stub for upstream interface ``LlmModelReasoningInfo``."""
    pass

class LlmProviderInfo(Protocol):
    """Surface stub for upstream interface ``LlmProviderInfo``."""
    pass

class LlmReasoningEffortInfo(Protocol):
    """Surface stub for upstream interface ``LlmReasoningEffortInfo``."""
    pass

class LlmResolvedModelInfo(Protocol):
    """Surface stub for upstream interface ``LlmResolvedModelInfo``."""
    pass

class ModelModalityMap(Protocol):
    """Surface stub for upstream interface ``ModelModalityMap``."""
    pass

class ReasoningBlock(Protocol):
    """Surface stub for upstream interface ``ReasoningBlock``."""
    pass

class TextBlock(Protocol):
    """Surface stub for upstream interface ``TextBlock``."""
    pass

class TokenUsage(Protocol):
    """Surface stub for upstream interface ``TokenUsage``."""
    pass

class ToolCallBlock(Protocol):
    """Surface stub for upstream interface ``ToolCallBlock``."""
    pass

class ToolResultBlock(Protocol):
    """Surface stub for upstream interface ``ToolResultBlock``."""
    pass

class ToolSchema(Protocol):
    """Surface stub for upstream interface ``ToolSchema``."""
    pass
