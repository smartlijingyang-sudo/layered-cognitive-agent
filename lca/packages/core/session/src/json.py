"""Auto-generated surface skeleton for upstream ``core/session/src/json.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/session/src/json.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "JsonValue",
    "isJsonValue",
    "snapshotJsonValue",
]

JsonValue: TypeAlias = object  # port: surface stub

def isJsonValue(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isJsonValue``."""
    raise NotImplementedError("port isJsonValue from core/session/src/json.ts")

def snapshotJsonValue(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``snapshotJsonValue``."""
    raise NotImplementedError("port snapshotJsonValue from core/session/src/json.ts")
