"""Auto-generated surface skeleton for upstream ``preset/agent-presets/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``preset/agent-presets/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "COMPOSITION_FILE",
    "METADATA_FILE",
    "SETTINGS_NAMESPACE",
    "AgentPreset",
    "AgentPresetSettings",
    "AgentPresetSettingsSchema",
    "AgentPresets",
    "Config",
    "InvalidPresetIdError",
    "JoinedPresetMount",
    "PresetBearingSession",
    "PresetExistsError",
    "PresetMetadata",
    "PresetMount",
    "PresetMountError",
    "PresetNotWritableError",
    "PresetRoot",
    "PresetTrust",
    "UnknownPresetError",
    "copyComposition",
    "deleteComposition",
    "discoverPresets",
    "inactiveRows",
    "leakedServices",
    "livePresetMounts",
    "mountPreset",
    "readComposition",
    "readPresetMetadata",
    "renderPresetMetadata",
    "resolveSessionPreset",
    "scanRoot",
    "serviceForAgent",
    "standingMountFor",
    "writableRoot",
]

AgentPreset: TypeAlias = object  # port: surface stub

Config: TypeAlias = object  # port: surface stub

JoinedPresetMount: TypeAlias = object  # port: surface stub

PresetBearingSession: TypeAlias = object  # port: surface stub

PresetMetadata: TypeAlias = object  # port: surface stub

PresetMount: TypeAlias = object  # port: surface stub

PresetRoot: TypeAlias = object  # port: surface stub

PresetTrust: TypeAlias = object  # port: surface stub

AgentPresetSettingsSchema = None  # port: surface stub

SETTINGS_NAMESPACE = None  # port: surface stub

class AgentPresets:
    """Surface stub for upstream class ``AgentPresets``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AgentPresets.__init__ from preset/agent-presets/src/index.ts")

COMPOSITION_FILE = None  # port: surface stub (reexport)

InvalidPresetIdError = None  # port: surface stub (reexport)

METADATA_FILE = None  # port: surface stub (reexport)

PresetExistsError = None  # port: surface stub (reexport)

PresetMountError = None  # port: surface stub (reexport)

PresetNotWritableError = None  # port: surface stub (reexport)

UnknownPresetError = None  # port: surface stub (reexport)

copyComposition = None  # port: surface stub (reexport)

deleteComposition = None  # port: surface stub (reexport)

discoverPresets = None  # port: surface stub (reexport)

inactiveRows = None  # port: surface stub (reexport)

leakedServices = None  # port: surface stub (reexport)

livePresetMounts = None  # port: surface stub (reexport)

mountPreset = None  # port: surface stub (reexport)

readComposition = None  # port: surface stub (reexport)

readPresetMetadata = None  # port: surface stub (reexport)

renderPresetMetadata = None  # port: surface stub (reexport)

resolveSessionPreset = None  # port: surface stub (reexport)

scanRoot = None  # port: surface stub (reexport)

serviceForAgent = None  # port: surface stub (reexport)

standingMountFor = None  # port: surface stub (reexport)

writableRoot = None  # port: surface stub (reexport)

class AgentPresetSettings(Protocol):
    """Surface stub for upstream interface ``AgentPresetSettings``."""
    pass
