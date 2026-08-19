"""Auto-generated surface skeleton for upstream ``client/ui-agent-preset/src/client/locales.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-agent-preset/src/client/locales.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentPresetSettingsKey",
    "PresetDisplaySource",
    "PresetDisplayText",
    "en",
    "presetDisplayText",
    "zh",
]

AgentPresetSettingsKey: TypeAlias = object  # port: surface stub

en = None  # port: surface stub

zh = None  # port: surface stub

def presetDisplayText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``presetDisplayText``."""
    raise NotImplementedError("port presetDisplayText from client/ui-agent-preset/src/client/locales.ts")

class PresetDisplaySource(Protocol):
    """Surface stub for upstream interface ``PresetDisplaySource``."""
    pass

class PresetDisplayText(Protocol):
    """Surface stub for upstream interface ``PresetDisplayText``."""
    pass
