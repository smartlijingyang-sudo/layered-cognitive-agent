"""Auto-generated surface skeleton for upstream ``fs/tool-fs-search/src/search-core.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/tool-fs-search/src/search-core.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "RAW_OUTPUT_MAX_BYTES",
    "SEARCH_GRACE_MS",
    "SEARCH_META_MAX_BYTES",
    "SEARCH_STDERR_MAX_BYTES",
    "SEARCH_TIMEOUT_MS",
    "GrepMatch",
    "RipgrepRun",
    "SearchError",
    "SearchErrorCode",
    "previewLine",
    "resolveRgPath",
    "retainGlobPaths",
    "retainGrepMatches",
    "runRipgrep",
    "toWorkdirRelative",
    "trySaveFormattedResult",
]

SearchErrorCode: TypeAlias = object  # port: surface stub

RAW_OUTPUT_MAX_BYTES = None  # port: surface stub

SEARCH_GRACE_MS = None  # port: surface stub

SEARCH_META_MAX_BYTES = None  # port: surface stub

SEARCH_STDERR_MAX_BYTES = None  # port: surface stub

SEARCH_TIMEOUT_MS = None  # port: surface stub

def previewLine(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``previewLine``."""
    raise NotImplementedError("port previewLine from fs/tool-fs-search/src/search-core.ts")

def resolveRgPath(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveRgPath``."""
    raise NotImplementedError("port resolveRgPath from fs/tool-fs-search/src/search-core.ts")

def retainGlobPaths(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``retainGlobPaths``."""
    raise NotImplementedError("port retainGlobPaths from fs/tool-fs-search/src/search-core.ts")

def retainGrepMatches(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``retainGrepMatches``."""
    raise NotImplementedError("port retainGrepMatches from fs/tool-fs-search/src/search-core.ts")

def runRipgrep(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``runRipgrep``."""
    raise NotImplementedError("port runRipgrep from fs/tool-fs-search/src/search-core.ts")

def toWorkdirRelative(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``toWorkdirRelative``."""
    raise NotImplementedError("port toWorkdirRelative from fs/tool-fs-search/src/search-core.ts")

def trySaveFormattedResult(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``trySaveFormattedResult``."""
    raise NotImplementedError("port trySaveFormattedResult from fs/tool-fs-search/src/search-core.ts")

class SearchError:
    """Surface stub for upstream class ``SearchError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SearchError.__init__ from fs/tool-fs-search/src/search-core.ts")

class GrepMatch(Protocol):
    """Surface stub for upstream interface ``GrepMatch``."""
    pass

class RipgrepRun(Protocol):
    """Surface stub for upstream interface ``RipgrepRun``."""
    pass
