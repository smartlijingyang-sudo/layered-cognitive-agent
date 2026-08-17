"""Auto-generated surface skeleton for upstream ``util/output-retention/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``util/output-retention/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ItemRetainer",
    "ItemRetentionStrategy",
    "Omitted",
    "PushDecision",
    "RetainedItems",
    "RetainedText",
    "RetentionNotice",
    "TextRetainer",
    "TextRetentionStrategy",
    "describeOmitted",
    "formatRetentionNotice",
]

ItemRetentionStrategy: TypeAlias = object  # port: surface stub

Omitted: TypeAlias = object  # port: surface stub

TextRetentionStrategy: TypeAlias = object  # port: surface stub

def describeOmitted(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``describeOmitted``."""
    raise NotImplementedError("port describeOmitted from util/output-retention/src/index.ts")

def formatRetentionNotice(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatRetentionNotice``."""
    raise NotImplementedError("port formatRetentionNotice from util/output-retention/src/index.ts")

class ItemRetainer:
    """Surface stub for upstream class ``ItemRetainer``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ItemRetainer.__init__ from util/output-retention/src/index.ts")

class TextRetainer:
    """Surface stub for upstream class ``TextRetainer``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TextRetainer.__init__ from util/output-retention/src/index.ts")

class PushDecision(Protocol):
    """Surface stub for upstream interface ``PushDecision``."""
    pass

class RetainedItems(Protocol):
    """Surface stub for upstream interface ``RetainedItems``."""
    pass

class RetainedText(Protocol):
    """Surface stub for upstream interface ``RetainedText``."""
    pass

class RetentionNotice(Protocol):
    """Surface stub for upstream interface ``RetentionNotice``."""
    pass
