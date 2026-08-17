"""Auto-generated surface skeleton for upstream ``subagent/subagent/src/list-children.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent/src/list-children.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SubagentDescendantListEntry",
    "SubagentListEntry",
    "listChildren",
    "listDescendants",
]

SubagentDescendantListEntry: TypeAlias = object  # port: surface stub

SubagentListEntry: TypeAlias = object  # port: surface stub

def listChildren(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``listChildren``."""
    raise NotImplementedError("port listChildren from subagent/subagent/src/list-children.ts")

def listDescendants(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``listDescendants``."""
    raise NotImplementedError("port listDescendants from subagent/subagent/src/list-children.ts")
