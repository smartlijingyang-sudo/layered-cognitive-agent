"""Auto-generated surface skeleton for upstream ``fs/tool-fs-search/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/tool-fs-search/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "GLOB_MAX_RESULTS",
    "GLOB_VCS_EXCLUDES",
    "GREP_MAX_LINE_BYTES",
    "GREP_MAX_MATCHES",
    "GlobInput",
    "GlobSample",
    "GlobToolCaps",
    "GrepInput",
    "GrepMatch",
    "GrepToolCaps",
    "RAW_OUTPUT_MAX_BYTES",
    "RipgrepRun",
    "SEARCH_GRACE_MS",
    "SEARCH_META_MAX_BYTES",
    "SEARCH_STDERR_MAX_BYTES",
    "SEARCH_TIMEOUT_MS",
    "SearchError",
    "SearchErrorCode",
    "apply",
    "applyGlobTool",
    "applyGrepTool",
    "buildGlobCommand",
    "buildGrepCommand",
    "formatGlobOutput",
    "formatGrepMatches",
    "formatGrepOutput",
    "inject",
    "name",
    "parseGlobArgs",
    "parseGrepArgs",
    "parseGrepMatches",
    "presentGlobCall",
    "presentGlobResult",
    "presentGrepCall",
    "presentGrepResult",
    "previewLine",
    "resolveRgPath",
    "runRipgrep",
    "sampleAcrossTopLevel",
    "toWorkdirRelative",
    "trySaveFormattedResult",
]

GlobInput: TypeAlias = object  # port: surface stub

GlobSample: TypeAlias = object  # port: surface stub

GlobToolCaps: TypeAlias = object  # port: surface stub

GrepInput: TypeAlias = object  # port: surface stub

GrepMatch: TypeAlias = object  # port: surface stub

GrepToolCaps: TypeAlias = object  # port: surface stub

RipgrepRun: TypeAlias = object  # port: surface stub

SearchErrorCode: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from fs/tool-fs-search/src/index.ts")

GLOB_MAX_RESULTS = None  # port: surface stub (reexport)

GLOB_VCS_EXCLUDES = None  # port: surface stub (reexport)

GREP_MAX_LINE_BYTES = None  # port: surface stub (reexport)

GREP_MAX_MATCHES = None  # port: surface stub (reexport)

RAW_OUTPUT_MAX_BYTES = None  # port: surface stub (reexport)

SEARCH_GRACE_MS = None  # port: surface stub (reexport)

SEARCH_META_MAX_BYTES = None  # port: surface stub (reexport)

SEARCH_STDERR_MAX_BYTES = None  # port: surface stub (reexport)

SEARCH_TIMEOUT_MS = None  # port: surface stub (reexport)

SearchError = None  # port: surface stub (reexport)

applyGlobTool = None  # port: surface stub (reexport)

applyGrepTool = None  # port: surface stub (reexport)

buildGlobCommand = None  # port: surface stub (reexport)

buildGrepCommand = None  # port: surface stub (reexport)

formatGlobOutput = None  # port: surface stub (reexport)

formatGrepMatches = None  # port: surface stub (reexport)

formatGrepOutput = None  # port: surface stub (reexport)

parseGlobArgs = None  # port: surface stub (reexport)

parseGrepArgs = None  # port: surface stub (reexport)

parseGrepMatches = None  # port: surface stub (reexport)

presentGlobCall = None  # port: surface stub (reexport)

presentGlobResult = None  # port: surface stub (reexport)

presentGrepCall = None  # port: surface stub (reexport)

presentGrepResult = None  # port: surface stub (reexport)

previewLine = None  # port: surface stub (reexport)

resolveRgPath = None  # port: surface stub (reexport)

runRipgrep = None  # port: surface stub (reexport)

sampleAcrossTopLevel = None  # port: surface stub (reexport)

toWorkdirRelative = None  # port: surface stub (reexport)

trySaveFormattedResult = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
