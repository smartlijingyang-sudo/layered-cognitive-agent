"""Auto-generated surface skeleton for upstream ``llm/token-meter/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/token-meter/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ContextBreakdownProjection",
    "ContextPressureProjection",
    "TokenMeasurement",
    "TokenMeasurementBaseline",
    "TokenMeterConfig",
    "TokenSurfaceNode",
    "TokenUsageProjection",
]

ContextBreakdownProjection: TypeAlias = object  # port: surface stub

ContextPressureProjection: TypeAlias = object  # port: surface stub

TokenMeasurementBaseline: TypeAlias = object  # port: surface stub

TokenMeterConfig: TypeAlias = object  # port: surface stub

TokenUsageProjection: TypeAlias = object  # port: surface stub

class TokenMeasurement(Protocol):
    """Surface stub for upstream interface ``TokenMeasurement``."""
    pass

class TokenSurfaceNode(Protocol):
    """Surface stub for upstream interface ``TokenSurfaceNode``."""
    pass
