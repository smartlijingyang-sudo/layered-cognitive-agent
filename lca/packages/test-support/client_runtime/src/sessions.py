"""Auto-generated surface skeleton for upstream ``test-support/client-runtime/src/sessions.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/client-runtime/src/sessions.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "FixtureSession",
    "TestSessionBinding",
    "TestSessions",
]

class FixtureSession:
    """Surface stub for upstream class ``FixtureSession``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port FixtureSession.__init__ from test-support/client-runtime/src/sessions.ts")

class TestSessions:
    """Surface stub for upstream class ``TestSessions``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TestSessions.__init__ from test-support/client-runtime/src/sessions.ts")

class TestSessionBinding(Protocol):
    """Surface stub for upstream interface ``TestSessionBinding``."""
    pass
