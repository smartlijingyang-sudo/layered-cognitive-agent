"""Auto-generated surface skeleton for upstream ``client/ui-agent-preset/src/client/settings-store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-agent-preset/src/client/settings-store.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AGENT_PRESET_SETTINGS_NS",
    "AgentPresetOption",
    "AgentPresetSettingsController",
    "AgentPresetSettingsState",
    "RosterPreset",
    "RosterRead",
    "RosterValue",
    "beginRosterRead",
    "messageOf",
    "presetOptions",
    "readRoster",
    "writeDefaultPreset",
]

RosterRead: TypeAlias = object  # port: surface stub

AGENT_PRESET_SETTINGS_NS = None  # port: surface stub

def beginRosterRead(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``beginRosterRead``."""
    raise NotImplementedError("port beginRosterRead from client/ui-agent-preset/src/client/settings-store.ts")

def messageOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``messageOf``."""
    raise NotImplementedError("port messageOf from client/ui-agent-preset/src/client/settings-store.ts")

def presetOptions(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``presetOptions``."""
    raise NotImplementedError("port presetOptions from client/ui-agent-preset/src/client/settings-store.ts")

def readRoster(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readRoster``."""
    raise NotImplementedError("port readRoster from client/ui-agent-preset/src/client/settings-store.ts")

def writeDefaultPreset(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``writeDefaultPreset``."""
    raise NotImplementedError("port writeDefaultPreset from client/ui-agent-preset/src/client/settings-store.ts")

class AgentPresetSettingsController:
    """Surface stub for upstream class ``AgentPresetSettingsController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AgentPresetSettingsController.__init__ from client/ui-agent-preset/src/client/settings-store.ts")

class AgentPresetOption(Protocol):
    """Surface stub for upstream interface ``AgentPresetOption``."""
    pass

class AgentPresetSettingsState(Protocol):
    """Surface stub for upstream interface ``AgentPresetSettingsState``."""
    pass

class RosterPreset(Protocol):
    """Surface stub for upstream interface ``RosterPreset``."""
    pass

class RosterValue(Protocol):
    """Surface stub for upstream interface ``RosterValue``."""
    pass
