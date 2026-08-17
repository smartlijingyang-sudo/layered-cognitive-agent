"""Auto-generated surface skeleton for upstream ``client/ui-settings-general/src/client/settings-document-store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-settings-general/src/client/settings-document-store.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SettingsDocumentState",
    "SettingsDocumentStore",
    "refreshDocumentIfLoaded",
]

def refreshDocumentIfLoaded(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``refreshDocumentIfLoaded``."""
    raise NotImplementedError("port refreshDocumentIfLoaded from client/ui-settings-general/src/client/settings-document-store.ts")

class SettingsDocumentStore:
    """Surface stub for upstream class ``SettingsDocumentStore``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SettingsDocumentStore.__init__ from client/ui-settings-general/src/client/settings-document-store.ts")

class SettingsDocumentState(Protocol):
    """Surface stub for upstream interface ``SettingsDocumentState``."""
    pass
