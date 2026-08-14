"""User-visible products vs workspace working copies.

LobeHub Works register a resource at completion (one card, versions), not on
every mutation. officecli's resident session is a dirty tree in
the outputs directory — create/add/set/batch are not deliverables.

Images, PDF, and HTML are FileViewer-native products and publish incrementally.
Office binaries publish only on export / close / save / run-end seal.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

_CMD_SPLIT_RE = re.compile(r"&&|\|\||;|\n")

_OFFICE_SUFFIXES = (
    ".pptx",
    ".ppt",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".odt",
    ".odp",
    ".ods",
)
_IMMEDIATE_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".pdf",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
    ".csv",
    ".json",
    ".xml",
)
_PUBLISH_TOOLS = frozenset({"exportFile", "writeFile", "write_file_local"})
_PUBLISH_VERBS = frozenset({"close", "save"})


def is_office_name(name: str) -> bool:
    """True for Office binaries — not FileViewer-native."""
    return PurePosixPath(name).suffix.lower() in _OFFICE_SUFFIXES


def is_immediate_product_name(name: str) -> bool:
    """True for types LobeHub FileViewer can preview in-app."""
    return PurePosixPath(name).suffix.lower() in _IMMEDIATE_SUFFIXES


def is_office_publish_intent(
    *,
    tool_name: str = "",
    command: str = "",
) -> bool:
    """export_file / write_file / officecli close|save are explicit publishes."""
    if (tool_name or "").strip() in _PUBLISH_TOOLS:
        return True
    return officecli_verb(command) in _PUBLISH_VERBS


def officecli_verb(command: str) -> str | None:
    """First officecli subcommand in a shell line, or None."""
    for chunk in _CMD_SPLIT_RE.split(command or ""):
        tokens = chunk.split()
        for index, token in enumerate(tokens):
            if PurePosixPath(token).name.lower() != "officecli":
                continue
            for next_token in tokens[index + 1 :]:
                if next_token.startswith("-"):
                    continue
                return next_token.lower()
    return None


def visible_generated_files(
    files: Any,
    *,
    tool_name: str = "",
    command: str = "",
) -> tuple[Any, ...]:
    """Sandbox files that may enter FileStore / fileList for this invocation."""
    publish_office = is_office_publish_intent(tool_name=tool_name, command=command)
    out: list[Any] = []
    for item in files or ():
        name = str(getattr(item, "name", "") or "")
        if is_office_name(name) and not publish_office:
            continue
        out.append(item)
    return tuple(out)


def publishable_file_parts(
    parts: list[dict[str, Any]],
    *,
    stdout: str = "",
    tool_name: str = "",
    command: str = "",
) -> list[dict[str, Any]]:
    """Keep immediate products; keep Office only on publish intent."""
    del stdout
    if not parts:
        return []
    publish_office = is_office_publish_intent(tool_name=tool_name, command=command)
    visible: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        name = str(part.get("name") or part.get("filename") or "")
        if is_office_name(name) and not publish_office:
            continue
        visible.append(part)
    return visible
