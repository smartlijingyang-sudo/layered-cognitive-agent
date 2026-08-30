"""officecli command plane — classify and normalize, do not invent verbs.

officecli batch speaks JSON BatchItem[] with field ``props``. Models emit
CLI ``--prop`` lines or JSON ``prop``. The plane rewrites that to the real
schema so the Office binary is the contract, not the prompt.
"""

from __future__ import annotations

import json
import re
import shlex
from typing import Any

_HEREDOC_RE = re.compile(
    r"(officecli\b[^\n]*\bbatch\b[^\n]*)<<(?P<q>['\"]?)(?P<tag>\w+)(?P=q)\s*\n"
    r"(?P<body>.*?)\n(?P=tag)\s*$",
    re.DOTALL | re.IGNORECASE,
)


def normalize_officecli_command(command: str) -> str:
    """Rewrite officecli batch bodies to JSON with ``props``. Other commands pass through."""
    text = command or ""
    match = _HEREDOC_RE.search(text)
    if match is None:
        return text
    body = match.group("body").strip()
    if not body:
        return text
    items = _batch_items(body)
    if items is None:
        return text
    rewritten = json.dumps(items, ensure_ascii=False)
    start, end = match.span("body")
    return text[:start] + rewritten + text[end:]


def _batch_items(body: str) -> list[dict[str, Any]] | None:
    if body.startswith("["):
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, list):
            return None
        renamed = _rename_prop_keys(parsed)
        return renamed if isinstance(renamed, list) else None
    items: list[dict[str, Any]] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        item = _cli_line_to_item(line)
        if item is None:
            return None
        items.append(item)
    return items or None


def _rename_prop_keys(value: Any) -> Any:
    if isinstance(value, list):
        return [_rename_prop_keys(item) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            next_key = "props" if key == "prop" else str(key)
            out[next_key] = _rename_prop_keys(item)
        return out
    return value


def _cli_line_to_item(line: str) -> dict[str, Any] | None:
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    item: dict[str, Any] = {"op": tokens[0]}
    index = 1
    if index < len(tokens) and not tokens[index].startswith("-"):
        item["path"] = tokens[index]
        index += 1
    props: dict[str, Any] = {}
    while index < len(tokens):
        flag = tokens[index]
        if flag in {"--type", "--path"} and index + 1 < len(tokens):
            field = "type" if flag == "--type" else "path"
            item[field] = tokens[index + 1]
            index += 2
            continue
        if flag == "--prop" and index + 1 < len(tokens):
            key, sep, raw = tokens[index + 1].partition("=")
            if sep:
                props[key] = _coerce_prop(raw)
            index += 2
            continue
        if flag == "--json":
            index += 1
            continue
        index += 1
    if props:
        item["props"] = props
    return item


def _coerce_prop(raw: str) -> Any:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
            return int(raw)
    except ValueError:
        pass
    return raw
