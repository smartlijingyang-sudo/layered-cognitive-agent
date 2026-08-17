"""Auto-generated surface skeleton for upstream ``sdk/client/src/client.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sdk/client/src/client.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "HarnessClient",
    "NotificationSubscription",
    "RequestTimeoutError",
    "SdkProtocolError",
    "TransportClosedError",
    "isRecord",
]

def isRecord(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isRecord``."""
    raise NotImplementedError("port isRecord from sdk/client/src/client.ts")

class HarnessClient:
    """Surface stub for upstream class ``HarnessClient``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port HarnessClient.__init__ from sdk/client/src/client.ts")

class RequestTimeoutError:
    """Surface stub for upstream class ``RequestTimeoutError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port RequestTimeoutError.__init__ from sdk/client/src/client.ts")

class SdkProtocolError:
    """Surface stub for upstream class ``SdkProtocolError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SdkProtocolError.__init__ from sdk/client/src/client.ts")

class TransportClosedError:
    """Surface stub for upstream class ``TransportClosedError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TransportClosedError.__init__ from sdk/client/src/client.ts")

class NotificationSubscription(Protocol):
    """Surface stub for upstream interface ``NotificationSubscription``."""
    pass
