"""Auto-generated surface skeleton for upstream ``client/connection/src/client/fixture.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/connection/src/client/fixture.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "FixtureApiClient",
    "FixtureOptions",
    "FixtureWorld",
    "createFixtureApi",
    "createFixtureFaces",
]

def createFixtureApi(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createFixtureApi``."""
    raise NotImplementedError("port createFixtureApi from client/connection/src/client/fixture.ts")

def createFixtureFaces(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createFixtureFaces``."""
    raise NotImplementedError("port createFixtureFaces from client/connection/src/client/fixture.ts")

class FixtureApiClient:
    """Surface stub for upstream class ``FixtureApiClient``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port FixtureApiClient.__init__ from client/connection/src/client/fixture.ts")

class FixtureOptions(Protocol):
    """Surface stub for upstream interface ``FixtureOptions``."""
    pass

class FixtureWorld(Protocol):
    """Surface stub for upstream interface ``FixtureWorld``."""
    pass
