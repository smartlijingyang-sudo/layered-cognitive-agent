"""Auto-generated surface skeleton for upstream ``credentials/credentials-local/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``credentials/credentials-local/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "CREDENTIALS_FILENAME",
    "Config",
    "LocalCredentialProvider",
    "parseCredentialsDocument",
    "resolveSpec",
]

CREDENTIALS_FILENAME = None  # port: surface stub

def parseCredentialsDocument(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseCredentialsDocument``."""
    raise NotImplementedError("port parseCredentialsDocument from credentials/credentials-local/src/index.ts")

def resolveSpec(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveSpec``."""
    raise NotImplementedError("port resolveSpec from credentials/credentials-local/src/index.ts")

class LocalCredentialProvider:
    """Surface stub for upstream class ``LocalCredentialProvider``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LocalCredentialProvider.__init__ from credentials/credentials-local/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
