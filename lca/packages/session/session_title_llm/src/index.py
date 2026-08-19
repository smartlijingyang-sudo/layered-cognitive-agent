"""Auto-generated surface skeleton for upstream ``session/session-title-llm/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-title-llm/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SESSION_TITLE_TIMEOUT_CODE",
    "ResolvedSessionTitleLlmConfig",
    "SessionTitleLlmConfig",
    "SessionTitleLlmConfigFields",
    "SessionTitleLlmConfigSchema",
    "SessionTitleLlmMessageSelector",
    "SessionTitleLlmRequestEventData",
    "generateSessionTitleWithLlm",
    "registerSessionTitleLlmProvider",
    "resolveSessionTitleLlmConfig",
]

SessionTitleLlmMessageSelector: TypeAlias = object  # port: surface stub

SESSION_TITLE_TIMEOUT_CODE = None  # port: surface stub

SessionTitleLlmConfigFields = None  # port: surface stub

SessionTitleLlmConfigSchema = None  # port: surface stub

def generateSessionTitleWithLlm(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``generateSessionTitleWithLlm``."""
    raise NotImplementedError("port generateSessionTitleWithLlm from session/session-title-llm/src/index.ts")

def registerSessionTitleLlmProvider(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``registerSessionTitleLlmProvider``."""
    raise NotImplementedError("port registerSessionTitleLlmProvider from session/session-title-llm/src/index.ts")

def resolveSessionTitleLlmConfig(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveSessionTitleLlmConfig``."""
    raise NotImplementedError("port resolveSessionTitleLlmConfig from session/session-title-llm/src/index.ts")

class ResolvedSessionTitleLlmConfig(Protocol):
    """Surface stub for upstream interface ``ResolvedSessionTitleLlmConfig``."""
    pass

class SessionTitleLlmConfig(Protocol):
    """Surface stub for upstream interface ``SessionTitleLlmConfig``."""
    pass

class SessionTitleLlmRequestEventData(Protocol):
    """Surface stub for upstream interface ``SessionTitleLlmRequestEventData``."""
    pass
