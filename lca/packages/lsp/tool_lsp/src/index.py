"""Auto-generated surface skeleton for upstream ``lsp/tool-lsp/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/tool-lsp/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "DEFAULT_LSP_TOOL_TIMEOUT_MS",
    "DEFAULT_MAX_LOCATIONS",
    "DEFAULT_MAX_RESULT_CHARS",
    "LSP_OPERATIONS",
    "LSP_PROMPT_TEXT",
    "apply",
    "formatHover",
    "formatLocations",
    "inject",
    "name",
    "parseLspArgs",
    "presentLspCall",
    "renderUri",
    "sessionCwd",
]

DEFAULT_LSP_TOOL_TIMEOUT_MS = None  # port: surface stub

LSP_PROMPT_TEXT = None  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from lsp/tool-lsp/src/index.ts")

DEFAULT_MAX_LOCATIONS = None  # port: surface stub (reexport)

DEFAULT_MAX_RESULT_CHARS = None  # port: surface stub (reexport)

LSP_OPERATIONS = None  # port: surface stub (reexport)

formatHover = None  # port: surface stub (reexport)

formatLocations = None  # port: surface stub (reexport)

parseLspArgs = None  # port: surface stub (reexport)

presentLspCall = None  # port: surface stub (reexport)

renderUri = None  # port: surface stub (reexport)

sessionCwd = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
