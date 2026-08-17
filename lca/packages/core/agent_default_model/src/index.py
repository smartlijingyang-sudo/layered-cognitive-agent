"""Auto-generated surface skeleton for upstream ``core/agent-default-model/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/agent-default-model/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AGENT_DEFAULT_MODEL_SETTINGS_NAMESPACE",
    "AGENT_DEFAULT_MODEL_SETTINGS_SCHEMA",
    "AgentDefaultModelConfig",
    "AgentDefaultModelSettings",
    "Config",
]

AGENT_DEFAULT_MODEL_SETTINGS_NAMESPACE = None  # port: surface stub

AGENT_DEFAULT_MODEL_SETTINGS_SCHEMA = None  # port: surface stub

class AgentDefaultModelConfig:
    """Surface stub for upstream class ``AgentDefaultModelConfig``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AgentDefaultModelConfig.__init__ from core/agent-default-model/src/index.ts")

class AgentDefaultModelSettings(Protocol):
    """Surface stub for upstream interface ``AgentDefaultModelSettings``."""
    pass

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
