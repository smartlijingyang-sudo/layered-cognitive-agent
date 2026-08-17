"""Auto-generated surface skeleton for upstream ``client/ui-sidebar/src/client/contract/slots.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-sidebar/src/client/contract/slots.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SidebarFooterActionOwnerProps",
    "SidebarRootComponentProps",
    "SidebarRootInjected",
    "SidebarSectionOwnerProps",
    "SidebarSettingsOwnerProps",
]

SidebarRootComponentProps: TypeAlias = object  # port: surface stub

SidebarRootInjected: TypeAlias = object  # port: surface stub

class SidebarFooterActionOwnerProps(Protocol):
    """Surface stub for upstream interface ``SidebarFooterActionOwnerProps``."""
    pass

class SidebarSectionOwnerProps(Protocol):
    """Surface stub for upstream interface ``SidebarSectionOwnerProps``."""
    pass

class SidebarSettingsOwnerProps(Protocol):
    """Surface stub for upstream interface ``SidebarSettingsOwnerProps``."""
    pass
