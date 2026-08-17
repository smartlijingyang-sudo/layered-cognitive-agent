"""Auto-generated surface skeleton for upstream ``sandbox/sandbox-windows-acl/src/token.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sandbox/sandbox-windows-acl/src/token.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "RestrictingSidSet",
    "createRestrictedToken",
    "findLogonSid",
    "makeWellKnownSid",
    "openCurrentProcessToken",
    "setTokenDefaultDaclGrant",
]

def createRestrictedToken(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createRestrictedToken``."""
    raise NotImplementedError("port createRestrictedToken from sandbox/sandbox-windows-acl/src/token.ts")

def findLogonSid(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``findLogonSid``."""
    raise NotImplementedError("port findLogonSid from sandbox/sandbox-windows-acl/src/token.ts")

def makeWellKnownSid(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``makeWellKnownSid``."""
    raise NotImplementedError("port makeWellKnownSid from sandbox/sandbox-windows-acl/src/token.ts")

def openCurrentProcessToken(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``openCurrentProcessToken``."""
    raise NotImplementedError("port openCurrentProcessToken from sandbox/sandbox-windows-acl/src/token.ts")

def setTokenDefaultDaclGrant(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``setTokenDefaultDaclGrant``."""
    raise NotImplementedError("port setTokenDefaultDaclGrant from sandbox/sandbox-windows-acl/src/token.ts")

class RestrictingSidSet(Protocol):
    """Surface stub for upstream interface ``RestrictingSidSet``."""
    pass
