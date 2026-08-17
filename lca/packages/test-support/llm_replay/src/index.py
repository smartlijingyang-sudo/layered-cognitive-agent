"""Auto-generated surface skeleton for upstream ``test-support/llm-replay/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/llm-replay/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "ReplayConfig",
    "ReplayEntry",
    "ReplayHandle",
    "ReplayModelConfig",
    "ReplayOverrideDoc",
    "ReplayOverridePatch",
    "ReplayProviderConfig",
    "SessionScript",
    "apply",
    "deriveReplayScript",
    "inject",
    "installLlmReplay",
    "loadReplayScript",
    "loadSessionScripts",
    "name",
    "parseSessionHeader",
    "parseSessionLog",
    "resolveScriptedEntry",
]

ReplayEntry: TypeAlias = object  # port: surface stub

ReplayOverrideDoc: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from test-support/llm-replay/src/index.ts")

def deriveReplayScript(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveReplayScript``."""
    raise NotImplementedError("port deriveReplayScript from test-support/llm-replay/src/index.ts")

def installLlmReplay(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``installLlmReplay``."""
    raise NotImplementedError("port installLlmReplay from test-support/llm-replay/src/index.ts")

def loadReplayScript(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``loadReplayScript``."""
    raise NotImplementedError("port loadReplayScript from test-support/llm-replay/src/index.ts")

def loadSessionScripts(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``loadSessionScripts``."""
    raise NotImplementedError("port loadSessionScripts from test-support/llm-replay/src/index.ts")

def parseSessionHeader(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseSessionHeader``."""
    raise NotImplementedError("port parseSessionHeader from test-support/llm-replay/src/index.ts")

def parseSessionLog(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseSessionLog``."""
    raise NotImplementedError("port parseSessionLog from test-support/llm-replay/src/index.ts")

def resolveScriptedEntry(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveScriptedEntry``."""
    raise NotImplementedError("port resolveScriptedEntry from test-support/llm-replay/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class ReplayConfig(Protocol):
    """Surface stub for upstream interface ``ReplayConfig``."""
    pass

class ReplayHandle(Protocol):
    """Surface stub for upstream interface ``ReplayHandle``."""
    pass

class ReplayModelConfig(Protocol):
    """Surface stub for upstream interface ``ReplayModelConfig``."""
    pass

class ReplayOverridePatch(Protocol):
    """Surface stub for upstream interface ``ReplayOverridePatch``."""
    pass

class ReplayProviderConfig(Protocol):
    """Surface stub for upstream interface ``ReplayProviderConfig``."""
    pass

class SessionScript(Protocol):
    """Surface stub for upstream interface ``SessionScript``."""
    pass
