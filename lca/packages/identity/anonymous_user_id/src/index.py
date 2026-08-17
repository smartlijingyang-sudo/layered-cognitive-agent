"""Auto-generated surface skeleton for upstream ``identity/anonymous-user-id/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``identity/anonymous-user-id/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ANONYMOUS_USER_ID_FILE_NAME",
    "AnonymousUserId",
    "AnonymousUserIdOptions",
    "getOrCreateAnonymousUserId",
]

AnonymousUserId: TypeAlias = object  # port: surface stub

ANONYMOUS_USER_ID_FILE_NAME = None  # port: surface stub

def getOrCreateAnonymousUserId(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``getOrCreateAnonymousUserId``."""
    raise NotImplementedError("port getOrCreateAnonymousUserId from identity/anonymous-user-id/src/index.ts")

class AnonymousUserIdOptions(Protocol):
    """Surface stub for upstream interface ``AnonymousUserIdOptions``."""
    pass
