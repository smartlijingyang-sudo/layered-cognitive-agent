"""1:1 port of ``@deepseek-ai/dsh-tools/presentation.ts``.

Tool render-intent vocabulary: the provider-neutral types a tool
declares via ``ToolDefinition.present_call`` /
``ToolDefinition.present_result`` to say how one of its calls renders
in a UI (an editor's tool-call card, a CLI log line).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Union

from lca.layer0_infra.dsh_core.tools.types import ContentBlock

# ---------------------------------------------------------------------------
# ToolCallKind
# ---------------------------------------------------------------------------

ToolCallKind = Literal[
    "read", "edit", "delete", "move", "search", "execute", "fetch", "other",
]
"""Category of a tool call, used by a UI to pick an icon or treatment.

The provider-neutral vocabulary lets tools describe themselves without
depending on a particular client; ``other`` is the default.
"""


# ---------------------------------------------------------------------------
# FileLocation / FileDiff
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileLocation:
    """A file location a tool reads or modifies."""

    path: str
    line: int | None = None


@dataclass(frozen=True)
class FileDiff:
    """A single-file change a tool is about to make, for inline diff rendering.

    ``old_text`` is ``None`` for a new-file create or overwrite (no prior
    content available at call time).
    """

    path: str
    old_text: str | None
    new_text: str


# ---------------------------------------------------------------------------
# Call views
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GenericCallView:
    """The default card: a titled tool-call row with optional icon."""

    card: Literal["generic"] = "generic"
    title: str = ""
    kind: ToolCallKind | None = None
    raw_input: Any = None
    content: list[ContentBlock] | None = None
    locations: list[FileLocation] | None = None


@dataclass(frozen=True)
class TerminalCallView:
    """A call that IS a shell command running in a working directory."""

    card: Literal["terminal"] = "terminal"
    title: str = ""
    description: str | None = None
    cwd: str | None = None


@dataclass(frozen=True)
class DiffCallView:
    """A call that creates or modifies files, rendered as an inline diff card."""

    card: Literal["diff"] = "diff"
    title: str = ""
    diffs: list[FileDiff] = field(default_factory=list)
    locations: list[FileLocation] | None = None


ToolCallView = Union[GenericCallView, TerminalCallView, DiffCallView]
"""Provider-neutral pending-call presentation."""


# ---------------------------------------------------------------------------
# ReadFileLine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReadFileLine:
    """One numbered line of a file, carried by a ReadResultView."""

    number: int
    text: str


# ---------------------------------------------------------------------------
# Result views
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GenericResultView:
    """The default completed card."""

    card: Literal["generic"] = "generic"
    title: str | None = None
    content: list[ContentBlock] | None = None


@dataclass(frozen=True)
class TerminalResultView:
    """The completed state of a TerminalCallView."""

    card: Literal["terminal"] = "terminal"
    title: str | None = None
    output: str | None = None
    exit_code: int | None = None
    signal: str | None = None


@dataclass(frozen=True)
class DiffResultView:
    """A completed file mutation rendered as an inline diff card."""

    card: Literal["diff"] = "diff"
    title: str | None = None
    diffs: list[FileDiff] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Search result views
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SearchLineMatch:
    """One matched line inside a SearchFileMatches group."""

    line_number: int
    line: str


@dataclass(frozen=True)
class SearchFileMatches:
    """One file's grouped content matches."""

    path: str
    matches: list[SearchLineMatch] = field(default_factory=list)


@dataclass(frozen=True)
class SearchMatchesResultView:
    """A completed content search rendered as grouped-by-file matches."""

    card: Literal["search"] = "search"
    shape: Literal["matches"] = "matches"
    title: str | None = None
    files: list[SearchFileMatches] = field(default_factory=list)
    truncated: bool = False
    total: int = 0


@dataclass(frozen=True)
class SearchPathsResultView:
    """A completed path search rendered as a flat path list."""

    card: Literal["search"] = "search"
    shape: Literal["paths"] = "paths"
    title: str | None = None
    paths: list[str] = field(default_factory=list)
    truncated: bool = False
    total: int = 0


SearchResultView = Union[SearchMatchesResultView, SearchPathsResultView]


# ---------------------------------------------------------------------------
# ReadResultView
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReadResultView:
    """A completed file read rendered as a line-numbered code view."""

    card: Literal["read"] = "read"
    path: str = ""
    offset: int = 0
    lines: list[ReadFileLine] = field(default_factory=list)
    total_lines: int = 0
    title: str | None = None
    lang: str | None = None
    content: list[ContentBlock] | None = None


# ---------------------------------------------------------------------------
# Web result views
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WebSource:
    """One citeable source in a completed WebSearchResultView."""

    url: str
    title: str | None = None
    snippet: str | None = None
    published_at: str | None = None


@dataclass(frozen=True)
class WebSearchResultView:
    """The completed state of a ``web_search`` call."""

    card: Literal["web"] = "web"
    kind: Literal["search"] = "search"
    sources: list[WebSource] = field(default_factory=list)
    title: str | None = None
    answer: str | None = None
    truncated: bool = False


@dataclass(frozen=True)
class WebFetchResultView:
    """The completed state of a ``web_fetch`` call."""

    card: Literal["web"] = "web"
    kind: Literal["fetch"] = "fetch"
    url: str = ""
    status_code: int = 0
    title: str | None = None
    truncated: bool = False


WebResultView = Union[WebSearchResultView, WebFetchResultView]

ToolResultView = Union[
    GenericResultView,
    TerminalResultView,
    DiffResultView,
    SearchMatchesResultView,
    SearchPathsResultView,
    ReadResultView,
    WebSearchResultView,
    WebFetchResultView,
]
"""How a tool wants the COMPLETED call shown."""
