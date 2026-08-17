"""Auto-generated surface skeleton for upstream ``credentials/credentials/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``credentials/credentials/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CredentialInfo",
    "CredentialProvider",
    "CredentialRef",
    "ResolvedCredential",
    "credentialRef",
]

CredentialRef: TypeAlias = object  # port: surface stub

def credentialRef(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``credentialRef``."""
    raise NotImplementedError("port credentialRef from credentials/credentials/src/index.ts")

class CredentialProvider:
    """Surface stub for upstream class ``CredentialProvider``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CredentialProvider.__init__ from credentials/credentials/src/index.ts")

class CredentialInfo(Protocol):
    """Surface stub for upstream interface ``CredentialInfo``."""
    pass

class ResolvedCredential(Protocol):
    """Surface stub for upstream interface ``ResolvedCredential``."""
    pass
