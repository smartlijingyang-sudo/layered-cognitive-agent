"""Auto-generated surface skeleton for upstream ``client/ui-primitives/src/markdown/plain-text.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-primitives/src/markdown/plain-text.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "MarkdownPlainTextMode",
    "MarkdownPlainTextOptions",
    "extractMarkdownPlainText",
]

MarkdownPlainTextMode: TypeAlias = object  # port: surface stub

def extractMarkdownPlainText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``extractMarkdownPlainText``."""
    raise NotImplementedError("port extractMarkdownPlainText from client/ui-primitives/src/markdown/plain-text.ts")

class MarkdownPlainTextOptions(Protocol):
    """Surface stub for upstream interface ``MarkdownPlainTextOptions``."""
    pass
