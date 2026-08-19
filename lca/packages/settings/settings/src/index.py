"""Auto-generated surface skeleton for upstream ``settings/settings/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``settings/settings/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "RedactedSecret",
    "RedactedValue",
    "SettingsApplies",
    "SettingsConflictError",
    "SettingsDescribeOptions",
    "SettingsDescriptor",
    "SettingsNamespace",
    "SettingsPathOp",
    "SettingsProvider",
    "SettingsRegisterOptions",
    "SettingsScope",
    "SettingsSectionHooks",
    "SettingsUpdateSource",
    "deepEqualJson",
    "installSettingsSection",
    "redactSecrets",
    "settingsNamespace",
]

RedactedSecret: TypeAlias = object  # port: surface stub

RedactedValue: TypeAlias = object  # port: surface stub

SettingsApplies: TypeAlias = object  # port: surface stub

SettingsNamespace: TypeAlias = object  # port: surface stub

SettingsPathOp: TypeAlias = object  # port: surface stub

SettingsUpdateSource: TypeAlias = object  # port: surface stub

def deepEqualJson(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deepEqualJson``."""
    raise NotImplementedError("port deepEqualJson from settings/settings/src/index.ts")

def installSettingsSection(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``installSettingsSection``."""
    raise NotImplementedError("port installSettingsSection from settings/settings/src/index.ts")

def settingsNamespace(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``settingsNamespace``."""
    raise NotImplementedError("port settingsNamespace from settings/settings/src/index.ts")

class SettingsConflictError:
    """Surface stub for upstream class ``SettingsConflictError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SettingsConflictError.__init__ from settings/settings/src/index.ts")

class SettingsProvider:
    """Surface stub for upstream class ``SettingsProvider``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SettingsProvider.__init__ from settings/settings/src/index.ts")

redactSecrets = None  # port: surface stub (reexport)

class SettingsDescribeOptions(Protocol):
    """Surface stub for upstream interface ``SettingsDescribeOptions``."""
    pass

class SettingsDescriptor(Protocol):
    """Surface stub for upstream interface ``SettingsDescriptor``."""
    pass

class SettingsRegisterOptions(Protocol):
    """Surface stub for upstream interface ``SettingsRegisterOptions``."""
    pass

class SettingsScope(Protocol):
    """Surface stub for upstream interface ``SettingsScope``."""
    pass

class SettingsSectionHooks(Protocol):
    """Surface stub for upstream interface ``SettingsSectionHooks``."""
    pass
