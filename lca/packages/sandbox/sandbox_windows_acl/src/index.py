"""Auto-generated surface skeleton for upstream ``sandbox/sandbox-windows-acl/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sandbox/sandbox-windows-acl/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "AclSandbox",
    "AclSandboxChild",
    "AclSandboxChildResult",
    "AclSandboxOptions",
    "AclSandboxSpawnOptions",
    "AclWriteGrant",
    "Win32Error",
    "assertTempRootOutsideWorkspace",
    "quoteArg",
    "tempWriteSid",
    "workspaceWriteSid",
]

class AclSandbox:
    """Surface stub for upstream class ``AclSandbox``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AclSandbox.__init__ from sandbox/sandbox-windows-acl/src/index.ts")

AclWriteGrant = None  # port: surface stub (reexport)

Win32Error = None  # port: surface stub (reexport)

assertTempRootOutsideWorkspace = None  # port: surface stub (reexport)

quoteArg = None  # port: surface stub (reexport)

tempWriteSid = None  # port: surface stub (reexport)

workspaceWriteSid = None  # port: surface stub (reexport)

class AclSandboxChild(Protocol):
    """Surface stub for upstream interface ``AclSandboxChild``."""
    pass

class AclSandboxChildResult(Protocol):
    """Surface stub for upstream interface ``AclSandboxChildResult``."""
    pass

class AclSandboxOptions(Protocol):
    """Surface stub for upstream interface ``AclSandboxOptions``."""
    pass

class AclSandboxSpawnOptions(Protocol):
    """Surface stub for upstream interface ``AclSandboxSpawnOptions``."""
    pass
