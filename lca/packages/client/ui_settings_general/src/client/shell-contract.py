"""Auto-generated surface skeleton for upstream ``client/ui-settings-general/src/client/shell-contract.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-settings-general/src/client/shell-contract.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SettingsOnboardingStep",
    "SettingsRootComponentProps",
    "SettingsRootInjected",
    "SettingsSectionRow",
]

SettingsRootComponentProps: TypeAlias = object  # port: surface stub

SettingsRootInjected: TypeAlias = object  # port: surface stub

class SettingsOnboardingStep(Protocol):
    """Surface stub for upstream interface ``SettingsOnboardingStep``."""
    pass

class SettingsSectionRow(Protocol):
    """Surface stub for upstream interface ``SettingsSectionRow``."""
    pass
