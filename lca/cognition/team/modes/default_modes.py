"""Compatibility exports for built-in Gateway mode implementations.

Each default mode owns its builder and adapter in its profile-registerable module:
``solo.py`` / ``team.py`` / ``cordis_creator.py`` under ``lca.plugins.collaboration.modes``.
This facade preserves existing import paths for callers and tests while preventing a
shared module from becoming a second, implicit mode-composition root.
"""

from __future__ import annotations

from lca.plugins.collaboration.modes.cordis_creator import (
    _CordisCreatorModeAdapter,
    build_cordis_creator_agent,
    filter_creator_tools,
)
from lca.plugins.collaboration.modes.solo import _SoloModeAdapter, build_solo_agent
from lca.plugins.collaboration.modes.team import (
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
