"""Auto-generated surface skeleton for upstream ``util/launch-environment/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``util/launch-environment/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DSH_LAUNCH_ENVIRONMENT_KEY",
    "LaunchEnvironmentEntry",
    "LaunchEnvironmentLayerInput",
    "LaunchEnvironmentSnapshot",
    "LaunchEnvironmentSource",
    "createLaunchEnvironmentSnapshot",
    "launchEnvironmentOf",
]

LaunchEnvironmentSource: TypeAlias = object  # port: surface stub

DSH_LAUNCH_ENVIRONMENT_KEY = None  # port: surface stub

def createLaunchEnvironmentSnapshot(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createLaunchEnvironmentSnapshot``."""
    raise NotImplementedError("port createLaunchEnvironmentSnapshot from util/launch-environment/src/index.ts")

def launchEnvironmentOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``launchEnvironmentOf``."""
    raise NotImplementedError("port launchEnvironmentOf from util/launch-environment/src/index.ts")

class LaunchEnvironmentEntry(Protocol):
    """Surface stub for upstream interface ``LaunchEnvironmentEntry``."""
    pass

class LaunchEnvironmentLayerInput(Protocol):
    """Surface stub for upstream interface ``LaunchEnvironmentLayerInput``."""
    pass

class LaunchEnvironmentSnapshot(Protocol):
    """Surface stub for upstream interface ``LaunchEnvironmentSnapshot``."""
    pass
