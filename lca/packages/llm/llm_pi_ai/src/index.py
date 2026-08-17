"""Auto-generated surface skeleton for upstream ``llm/llm-pi-ai/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-pi-ai/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "PiAiAdapter",
    "PiAiAdapterOptions",
    "PiAiCompatProfile",
    "PiAiModality",
    "PiAiModelOverride",
    "PiAiModelProfile",
    "PiAiProviderProfile",
    "PiAiReasoningEfforts",
    "PiAiThinkingFormat",
    "ResolvedPiAiProviderProfile",
    "apply",
    "inject",
    "name",
    "supportedProtocols",
]

PiAiAdapterOptions: TypeAlias = object  # port: surface stub

PiAiCompatProfile: TypeAlias = object  # port: surface stub

PiAiModality: TypeAlias = object  # port: surface stub

PiAiModelOverride: TypeAlias = object  # port: surface stub

PiAiModelProfile: TypeAlias = object  # port: surface stub

PiAiProviderProfile: TypeAlias = object  # port: surface stub

PiAiReasoningEfforts: TypeAlias = object  # port: surface stub

PiAiThinkingFormat: TypeAlias = object  # port: surface stub

ResolvedPiAiProviderProfile: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from llm/llm-pi-ai/src/index.ts")

Config = None  # port: surface stub (reexport)

PiAiAdapter = None  # port: surface stub (reexport)

supportedProtocols = None  # port: surface stub (reexport)
