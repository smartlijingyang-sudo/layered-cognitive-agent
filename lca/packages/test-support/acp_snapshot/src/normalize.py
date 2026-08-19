"""Auto-generated surface skeleton for upstream ``test-support/acp-snapshot/src/normalize.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/acp-snapshot/src/normalize.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CwdPathMode",
    "NormalizeContext",
    "NormalizeOptions",
    "extractSnapshotSpillPaths",
    "normalizeSessionLog",
    "normalizeStdout",
    "scrubRequestHeaders",
    "scrubSystemPrompts",
    "scrubToolSchemas",
    "tokenizeSessionFixtureCwd",
]

CwdPathMode: TypeAlias = object  # port: surface stub

def extractSnapshotSpillPaths(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``extractSnapshotSpillPaths``."""
    raise NotImplementedError("port extractSnapshotSpillPaths from test-support/acp-snapshot/src/normalize.ts")

def normalizeSessionLog(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``normalizeSessionLog``."""
    raise NotImplementedError("port normalizeSessionLog from test-support/acp-snapshot/src/normalize.ts")

def normalizeStdout(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``normalizeStdout``."""
    raise NotImplementedError("port normalizeStdout from test-support/acp-snapshot/src/normalize.ts")

def scrubRequestHeaders(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scrubRequestHeaders``."""
    raise NotImplementedError("port scrubRequestHeaders from test-support/acp-snapshot/src/normalize.ts")

def scrubSystemPrompts(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scrubSystemPrompts``."""
    raise NotImplementedError("port scrubSystemPrompts from test-support/acp-snapshot/src/normalize.ts")

def scrubToolSchemas(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scrubToolSchemas``."""
    raise NotImplementedError("port scrubToolSchemas from test-support/acp-snapshot/src/normalize.ts")

def tokenizeSessionFixtureCwd(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``tokenizeSessionFixtureCwd``."""
    raise NotImplementedError("port tokenizeSessionFixtureCwd from test-support/acp-snapshot/src/normalize.ts")

class NormalizeContext(Protocol):
    """Surface stub for upstream interface ``NormalizeContext``."""
    pass

class NormalizeOptions(Protocol):
    """Surface stub for upstream interface ``NormalizeOptions``."""
    pass
