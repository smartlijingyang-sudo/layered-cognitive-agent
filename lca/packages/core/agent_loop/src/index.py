"""Auto-generated surface skeleton for upstream ``core/agent-loop/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/agent-loop/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "AGENT_LOOP_SETTINGS_NAMESPACE",
    "AGENT_LOOP_SETTINGS_SCHEMA",
    "CONFIGURED_AGENT_IDENTITIES_KEY",
    "DEFAULT_MAX_PARALLEL_TOOL_CALLS",
    "AgentLoop",
    "AgentLoopSettings",
    "Config",
    "ConfiguredAgentIdentities",
    "LauncherAgentIdentity",
]

AGENT_LOOP_SETTINGS_NAMESPACE = None  # port: surface stub

AGENT_LOOP_SETTINGS_SCHEMA = None  # port: surface stub

CONFIGURED_AGENT_IDENTITIES_KEY = None  # port: surface stub

class AgentLoop:
    """Surface stub for upstream class ``AgentLoop``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AgentLoop.__init__ from core/agent-loop/src/index.ts")

DEFAULT_MAX_PARALLEL_TOOL_CALLS = None  # port: surface stub (reexport)

class AgentLoopSettings(Protocol):
    """Surface stub for upstream interface ``AgentLoopSettings``."""
    pass

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class ConfiguredAgentIdentities(Protocol):
    """Surface stub for upstream interface ``ConfiguredAgentIdentities``."""
    pass

class LauncherAgentIdentity(Protocol):
    """Surface stub for upstream interface ``LauncherAgentIdentity``."""
    pass
