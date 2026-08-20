"""Back-compat shim — moved to ``gateway.runs.loop_drivers``.

The factory helpers used to live here; they are now private (``_build_*``)
with public aliases in ``gateway.runs.loop_drivers`` so tests that still
``from gateway.assemble import …`` continue to work. This file will be
removed once the test suite migrates.
"""
from __future__ import annotations

from gateway.runs.loop_drivers import build_runnable_team, build_solo_agent

__all__ = ["build_runnable_team", "build_solo_agent"]
