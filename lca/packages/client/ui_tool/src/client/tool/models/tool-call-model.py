"""Auto-generated surface skeleton for upstream ``client/ui-tool/src/client/tool/models/tool-call-model.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-tool/src/client/tool/models/tool-call-model.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "VARIANT_TITLES",
    "ToolCallBlock",
    "ToolRowModel",
    "ToolRowState",
    "ToolRowVariant",
    "classifyTool",
    "relativizeToCwd",
    "resultText",
    "toolRowModel",
]

ToolCallBlock: TypeAlias = object  # port: surface stub

ToolRowState: TypeAlias = object  # port: surface stub

ToolRowVariant: TypeAlias = object  # port: surface stub

VARIANT_TITLES = None  # port: surface stub

def classifyTool(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``classifyTool``."""
    raise NotImplementedError("port classifyTool from client/ui-tool/src/client/tool/models/tool-call-model.ts")

def relativizeToCwd(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``relativizeToCwd``."""
    raise NotImplementedError("port relativizeToCwd from client/ui-tool/src/client/tool/models/tool-call-model.ts")

def resultText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resultText``."""
    raise NotImplementedError("port resultText from client/ui-tool/src/client/tool/models/tool-call-model.ts")

def toolRowModel(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``toolRowModel``."""
    raise NotImplementedError("port toolRowModel from client/ui-tool/src/client/tool/models/tool-call-model.ts")

class ToolRowModel(Protocol):
    """Surface stub for upstream interface ``ToolRowModel``."""
    pass
