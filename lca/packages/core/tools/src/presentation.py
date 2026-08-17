"""Auto-generated surface skeleton for upstream ``core/tools/src/presentation.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/tools/src/presentation.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DiffCallView",
    "DiffResultView",
    "FileDiff",
    "FileLocation",
    "GenericCallView",
    "GenericResultView",
    "ReadFileLine",
    "ReadResultView",
    "SearchFileMatches",
    "SearchLineMatch",
    "SearchMatchesResultView",
    "SearchPathsResultView",
    "SearchResultView",
    "TerminalCallView",
    "TerminalResultView",
    "ToolCallKind",
    "ToolCallView",
    "ToolResultView",
    "WebFetchResultView",
    "WebResultView",
    "WebSearchResultView",
    "WebSource",
]

SearchResultView: TypeAlias = object  # port: surface stub

ToolCallKind: TypeAlias = object  # port: surface stub

ToolCallView: TypeAlias = object  # port: surface stub

ToolResultView: TypeAlias = object  # port: surface stub

WebResultView: TypeAlias = object  # port: surface stub

class DiffCallView(Protocol):
    """Surface stub for upstream interface ``DiffCallView``."""
    pass

class DiffResultView(Protocol):
    """Surface stub for upstream interface ``DiffResultView``."""
    pass

class FileDiff(Protocol):
    """Surface stub for upstream interface ``FileDiff``."""
    pass

class FileLocation(Protocol):
    """Surface stub for upstream interface ``FileLocation``."""
    pass

class GenericCallView(Protocol):
    """Surface stub for upstream interface ``GenericCallView``."""
    pass

class GenericResultView(Protocol):
    """Surface stub for upstream interface ``GenericResultView``."""
    pass

class ReadFileLine(Protocol):
    """Surface stub for upstream interface ``ReadFileLine``."""
    pass

class ReadResultView(Protocol):
    """Surface stub for upstream interface ``ReadResultView``."""
    pass

class SearchFileMatches(Protocol):
    """Surface stub for upstream interface ``SearchFileMatches``."""
    pass

class SearchLineMatch(Protocol):
    """Surface stub for upstream interface ``SearchLineMatch``."""
    pass

class SearchMatchesResultView(Protocol):
    """Surface stub for upstream interface ``SearchMatchesResultView``."""
    pass

class SearchPathsResultView(Protocol):
    """Surface stub for upstream interface ``SearchPathsResultView``."""
    pass

class TerminalCallView(Protocol):
    """Surface stub for upstream interface ``TerminalCallView``."""
    pass

class TerminalResultView(Protocol):
    """Surface stub for upstream interface ``TerminalResultView``."""
    pass

class WebFetchResultView(Protocol):
    """Surface stub for upstream interface ``WebFetchResultView``."""
    pass

class WebSearchResultView(Protocol):
    """Surface stub for upstream interface ``WebSearchResultView``."""
    pass

class WebSource(Protocol):
    """Surface stub for upstream interface ``WebSource``."""
    pass
