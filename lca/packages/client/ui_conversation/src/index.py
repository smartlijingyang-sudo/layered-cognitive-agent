"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "BUSY_ENTER_BEHAVIORS",
    "BUSY_ENTER_FIELD",
    "CONVERSATION_SETTINGS_NAMESPACE",
    "DEFAULT_BUSY_ENTER_BEHAVIOR",
    "BusyEnterBehavior",
    "ConversationSettings",
    "apply",
]

BusyEnterBehavior: TypeAlias = object  # port: surface stub

ConversationSettings: TypeAlias = object  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/ui-conversation/src/index.ts")

BUSY_ENTER_BEHAVIORS = None  # port: surface stub (reexport)

BUSY_ENTER_FIELD = None  # port: surface stub (reexport)

CONVERSATION_SETTINGS_NAMESPACE = None  # port: surface stub (reexport)

DEFAULT_BUSY_ENTER_BEHAVIOR = None  # port: surface stub (reexport)
