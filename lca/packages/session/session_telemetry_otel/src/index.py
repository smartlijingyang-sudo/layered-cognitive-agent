"""Auto-generated surface skeleton for upstream ``session/session-telemetry-otel/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-telemetry-otel/src/index.ts``
"""


from __future__ import annotations

import enum
from typing import Protocol

__all__: list[str] = [
    "DEFAULT_SHUTDOWN_TIMEOUT_MILLIS",
    "DEFAULT_TELEMETRY_MODE",
    "Config",
    "OpenTelemetrySessionBackend",
    "SessionTelemetryMode",
]

DEFAULT_SHUTDOWN_TIMEOUT_MILLIS = None  # port: surface stub

DEFAULT_TELEMETRY_MODE = None  # port: surface stub

class OpenTelemetrySessionBackend:
    """Surface stub for upstream class ``OpenTelemetrySessionBackend``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port OpenTelemetrySessionBackend.__init__ from session/session-telemetry-otel/src/index.ts")

class SessionTelemetryMode(enum.Enum):
    """Surface stub for upstream enum ``SessionTelemetryMode``."""
    pass

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
