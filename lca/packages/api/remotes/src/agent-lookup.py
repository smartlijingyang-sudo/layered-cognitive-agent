"""Auto-generated surface skeleton for upstream ``api/remotes/src/agent-lookup.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``api/remotes/src/agent-lookup.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ApiRemoteAgentOptions",
    "ApiRemoteAgentResult",
    "ApiRemoteLookupError",
    "ApiRemoteSessionNotFound",
    "ApiRemoteSubagentSessionOwnership",
    "apiRemoteSubagentOwnershipError",
    "createApiRemoteAgentResolver",
    "hasApiRemoteSubagentOwner",
    "inspectApiRemoteSession",
]

ApiRemoteAgentResult: TypeAlias = object  # port: surface stub

ApiRemoteLookupError: TypeAlias = object  # port: surface stub

def apiRemoteSubagentOwnershipError(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apiRemoteSubagentOwnershipError``."""
    raise NotImplementedError("port apiRemoteSubagentOwnershipError from api/remotes/src/agent-lookup.ts")

def createApiRemoteAgentResolver(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createApiRemoteAgentResolver``."""
    raise NotImplementedError("port createApiRemoteAgentResolver from api/remotes/src/agent-lookup.ts")

def hasApiRemoteSubagentOwner(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``hasApiRemoteSubagentOwner``."""
    raise NotImplementedError("port hasApiRemoteSubagentOwner from api/remotes/src/agent-lookup.ts")

def inspectApiRemoteSession(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``inspectApiRemoteSession``."""
    raise NotImplementedError("port inspectApiRemoteSession from api/remotes/src/agent-lookup.ts")

class ApiRemoteSessionNotFound:
    """Surface stub for upstream class ``ApiRemoteSessionNotFound``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ApiRemoteSessionNotFound.__init__ from api/remotes/src/agent-lookup.ts")

class ApiRemoteSubagentSessionOwnership:
    """Surface stub for upstream class ``ApiRemoteSubagentSessionOwnership``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ApiRemoteSubagentSessionOwnership.__init__ from api/remotes/src/agent-lookup.ts")

class ApiRemoteAgentOptions(Protocol):
    """Surface stub for upstream interface ``ApiRemoteAgentOptions``."""
    pass
