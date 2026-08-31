"""Compatibility exports for built-in Gateway mode implementations.

Each default mode owns its builder and adapter in its profile-registerable module:
``solo_mode``, ``team_mode``, and ``cordis_creator_mode``.  This facade preserves
existing import paths for callers and tests while preventing a shared module from
becoming a second, implicit mode-composition root.
"""

from __future__ import annotations

from lca.cognition.team.modes.cordis_creator_mode import (
    _CordisCreatorModeAdapter,
    build_cordis_creator_agent,
    filter_creator_tools,
)
from lca.cognition.team.modes.solo_mode import _SoloModeAdapter, build_solo_agent
from lca.cognition.team.modes.team_mode import (
    _TeamModeAdapter,
    build_runnable_team,
    resolve_team_casting_dependencies,
)

__all__ = [
    "_CordisCreatorModeAdapter",
    "_SoloModeAdapter",
    "_TeamModeAdapter",
    "build_cordis_creator_agent",
    "build_runnable_team",
    "build_solo_agent",
    "filter_creator_tools",
    "resolve_team_casting_dependencies",
]
