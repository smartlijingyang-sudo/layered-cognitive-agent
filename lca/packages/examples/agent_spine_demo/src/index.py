"""Auto-generated surface skeleton for upstream ``examples/agent-spine-demo/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``examples/agent-spine-demo/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "GoalConfig",
    "GoalConfigSchema",
    "JobsConfigSchema",
    "SessionTitleConfigSchema",
    "SkillConfig",
    "SkillConfigSchema",
    "ToolBashConfigSchema",
    "ToolJobsConfigSchema",
    "apply",
    "name",
    "pickSpineConfig",
]

GoalConfigSchema = None  # port: surface stub

JobsConfigSchema = None  # port: surface stub

SessionTitleConfigSchema = None  # port: surface stub

SkillConfigSchema = None  # port: surface stub

ToolBashConfigSchema = None  # port: surface stub

ToolJobsConfigSchema = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from examples/agent-spine-demo/src/index.ts")

def pickSpineConfig(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``pickSpineConfig``."""
    raise NotImplementedError("port pickSpineConfig from examples/agent-spine-demo/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class GoalConfig(Protocol):
    """Surface stub for upstream interface ``GoalConfig``."""
    pass

class SkillConfig(Protocol):
    """Surface stub for upstream interface ``SkillConfig``."""
    pass
