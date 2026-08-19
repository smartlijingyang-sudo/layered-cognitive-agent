"""Auto-generated surface skeleton for upstream ``client/ui-settings-models/src/client/store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-settings-models/src/client/store.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ModelsSettingsState",
    "ModelsSettingsStore",
    "OnboardingReadiness",
    "ProviderRow",
    "deriveKeyRef",
    "messageOf",
    "onboardingReadiness",
    "protocolChoices",
    "providerUsable",
]

OnboardingReadiness: TypeAlias = object  # port: surface stub

def deriveKeyRef(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveKeyRef``."""
    raise NotImplementedError("port deriveKeyRef from client/ui-settings-models/src/client/store.ts")

def messageOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``messageOf``."""
    raise NotImplementedError("port messageOf from client/ui-settings-models/src/client/store.ts")

def onboardingReadiness(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``onboardingReadiness``."""
    raise NotImplementedError("port onboardingReadiness from client/ui-settings-models/src/client/store.ts")

def protocolChoices(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``protocolChoices``."""
    raise NotImplementedError("port protocolChoices from client/ui-settings-models/src/client/store.ts")

def providerUsable(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``providerUsable``."""
    raise NotImplementedError("port providerUsable from client/ui-settings-models/src/client/store.ts")

class ModelsSettingsStore:
    """Surface stub for upstream class ``ModelsSettingsStore``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ModelsSettingsStore.__init__ from client/ui-settings-models/src/client/store.ts")

class ModelsSettingsState(Protocol):
    """Surface stub for upstream interface ``ModelsSettingsState``."""
    pass

class ProviderRow(Protocol):
    """Surface stub for upstream interface ``ProviderRow``."""
    pass
