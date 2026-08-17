"""Auto-generated surface skeleton for upstream ``api/remotes/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``api/remotes/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "API_REMOTE_FORWARDED_EVENTS",
    "ApiRemoteAgentOptions",
    "ApiRemoteAgentResult",
    "ApiRemoteForwardedEvent",
    "ApiRemoteLookupError",
    "ApiRemoteSessionNotFound",
    "ApiRemoteSubagentSessionOwnership",
    "apiRemoteSubagentOwnershipError",
    "apply",
    "createApiRemoteAgentResolver",
    "hasApiRemoteSubagentOwner",
    "inspectApiRemoteSession",
]

ApiRemoteAgentOptions: TypeAlias = object  # port: surface stub

ApiRemoteAgentResult: TypeAlias = object  # port: surface stub

ApiRemoteForwardedEvent: TypeAlias = object  # port: surface stub

ApiRemoteLookupError: TypeAlias = object  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from api/remotes/src/index.ts")

API_REMOTE_FORWARDED_EVENTS = None  # port: surface stub (reexport)

ApiRemoteSessionNotFound = None  # port: surface stub (reexport)

ApiRemoteSubagentSessionOwnership = None  # port: surface stub (reexport)

apiRemoteSubagentOwnershipError = None  # port: surface stub (reexport)

createApiRemoteAgentResolver = None  # port: surface stub (reexport)

hasApiRemoteSubagentOwner = None  # port: surface stub (reexport)

inspectApiRemoteSession = None  # port: surface stub (reexport)
