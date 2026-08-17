"""Auto-generated surface skeleton for upstream ``llm/llm-pi-ai/src/config.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-pi-ai/src/config.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "DEFAULT_CONTEXT_WINDOW",
    "DEFAULT_INPUT",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_STREAM_IDLE_TIMEOUT_MS",
    "PiAiCompatProfile",
    "PiAiModality",
    "PiAiModelOverride",
    "PiAiModelProfile",
    "PiAiProviderProfile",
    "PiAiReasoningEfforts",
    "PiAiThinkingFormat",
    "ResolvedPiAiProviderProfile",
    "assertServiceable",
    "resolveProfiles",
]

PiAiCompatProfile: TypeAlias = object  # port: surface stub

PiAiModality: TypeAlias = object  # port: surface stub

PiAiModelOverride: TypeAlias = object  # port: surface stub

PiAiModelProfile: TypeAlias = object  # port: surface stub

PiAiReasoningEfforts: TypeAlias = object  # port: surface stub

PiAiThinkingFormat: TypeAlias = object  # port: surface stub

DEFAULT_CONTEXT_WINDOW = None  # port: surface stub

DEFAULT_INPUT = None  # port: surface stub

DEFAULT_MAX_TOKENS = None  # port: surface stub

DEFAULT_STREAM_IDLE_TIMEOUT_MS = None  # port: surface stub

def assertServiceable(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertServiceable``."""
    raise NotImplementedError("port assertServiceable from llm/llm-pi-ai/src/config.ts")

def resolveProfiles(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveProfiles``."""
    raise NotImplementedError("port resolveProfiles from llm/llm-pi-ai/src/config.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class PiAiProviderProfile(Protocol):
    """Surface stub for upstream interface ``PiAiProviderProfile``."""
    pass

class ResolvedPiAiProviderProfile(Protocol):
    """Surface stub for upstream interface ``ResolvedPiAiProviderProfile``."""
    pass
