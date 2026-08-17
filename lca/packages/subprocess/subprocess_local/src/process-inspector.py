"""Auto-generated surface skeleton for upstream ``subprocess/subprocess-local/src/process-inspector.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subprocess/subprocess-local/src/process-inspector.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ProcessIdentity",
    "ProcessInspector",
    "ProcessInspectorInternals",
    "createProcessInspector",
    "linuxProcessGroupHasLiveMembers",
    "parseProcStat",
]

def createProcessInspector(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createProcessInspector``."""
    raise NotImplementedError("port createProcessInspector from subprocess/subprocess-local/src/process-inspector.ts")

def linuxProcessGroupHasLiveMembers(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``linuxProcessGroupHasLiveMembers``."""
    raise NotImplementedError("port linuxProcessGroupHasLiveMembers from subprocess/subprocess-local/src/process-inspector.ts")

def parseProcStat(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseProcStat``."""
    raise NotImplementedError("port parseProcStat from subprocess/subprocess-local/src/process-inspector.ts")

class ProcessIdentity(Protocol):
    """Surface stub for upstream interface ``ProcessIdentity``."""
    pass

class ProcessInspector(Protocol):
    """Surface stub for upstream interface ``ProcessInspector``."""
    pass

class ProcessInspectorInternals(Protocol):
    """Surface stub for upstream interface ``ProcessInspectorInternals``."""
    pass
