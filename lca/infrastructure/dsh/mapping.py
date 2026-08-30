"""DSH model-facing tool name → LCA WIRE name + plugin_state.

Strategy table, not if/else chains. Unknown tools keep their DSH name.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_JSON = dict[str, Any]


@dataclass(frozen=True)
class ToolProjection:
    wire_name: str
    started_state: _JSON
    invoked_state: _JSON


def _parse_args(raw: str) -> _JSON:
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return value if isinstance(value, dict) else {"raw": raw}


def _text_from_result(payload: _JSON) -> tuple[str, bool]:
    message = payload.get("message")
    blocks = message.get("content") if isinstance(message, dict) else payload.get("content")
    if not isinstance(blocks, list):
        return "", False
    texts: list[str] = []
    is_error = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool-result":
            is_error = bool(block.get("isError"))
            inner = block.get("content")
            if isinstance(inner, list):
                for item in inner:
                    if isinstance(item, dict) and item.get("type") == "text":
                        texts.append(str(item.get("text") or ""))
            continue
        if block.get("type") == "text":
            texts.append(str(block.get("text") or ""))
    return "".join(texts), is_error


def _bash_started(args: _JSON) -> _JSON:
    return {
        "command": str(args.get("command") or ""),
        "description": str(args.get("description") or ""),
        "executionEnv": "local",
        "isBackground": bool(args.get("run_in_background", False)),
    }


def _bash_invoked(args: _JSON, text: str, is_error: bool) -> _JSON:
    state = _bash_started(args)
    state["stdout"] = text
    state["output"] = text
    state["success"] = not is_error
    if "[exit code:" in text:
        try:
            tail = text.rsplit("[exit code:", 1)[1]
            state["exitCode"] = int(tail.split("]", 1)[0].strip())
        except (IndexError, ValueError):
            state["exitCode"] = 1 if is_error else 0
    else:
        state["exitCode"] = 1 if is_error else 0
    return state


def _path_started(args: _JSON, extra: _JSON | None = None) -> _JSON:
    path = str(args.get("file_path") or args.get("path") or "")
    state: _JSON = {"path": path, "file_path": path, "executionEnv": "local"}
    if extra:
        state.update(extra)
    return state


def _read_started(args: _JSON) -> _JSON:
    return _path_started(args)


def _read_invoked(args: _JSON, text: str, is_error: bool) -> _JSON:
    state = _path_started(args)
    state["content"] = text
    state["success"] = not is_error
    return state


def _write_started(args: _JSON) -> _JSON:
    return _path_started(args, {"content": str(args.get("content") or "")})


def _write_invoked(args: _JSON, text: str, is_error: bool) -> _JSON:
    state = _write_started(args)
    state["success"] = not is_error
    if text:
        state["output"] = text
    return state


def _edit_started(args: _JSON) -> _JSON:
    return _path_started(
        args,
        {
            "old_string": str(args.get("old_string") or ""),
            "new_string": str(args.get("new_string") or ""),
        },
    )


def _edit_invoked(args: _JSON, text: str, is_error: bool) -> _JSON:
    state = _edit_started(args)
    state["success"] = not is_error
    if text:
        state["output"] = text
    return state


def _generic_started(args: _JSON) -> _JSON:
    return dict(args)


def _generic_invoked(args: _JSON, text: str, is_error: bool) -> _JSON:
    state = dict(args)
    state["content"] = text
    state["success"] = not is_error
    return state


_WIRE: dict[str, str] = {
    "bash": "local_runCommand",
    "read": "local_readFile",
    "write": "local_writeFile",
    "edit": "local_editFile",
}

_STARTED: dict[str, Callable[[_JSON], _JSON]] = {
    "bash": _bash_started,
    "read": _read_started,
    "write": _write_started,
    "edit": _edit_started,
}


def map_dsh_tool(name: str) -> str:
    return _WIRE.get(name, name)


def project_tool_call(name: str, arguments: str) -> ToolProjection:
    args = _parse_args(arguments)
    started = _STARTED.get(name, _generic_started)(args)
    return ToolProjection(wire_name=map_dsh_tool(name), started_state=started, invoked_state={})


def project_tool_result(name: str, arguments: str, payload: _JSON) -> ToolProjection:
    args = _parse_args(arguments)
    text, is_error = _text_from_result(payload)
    builders: dict[str, Callable[[_JSON, str, bool], _JSON]] = {
        "bash": _bash_invoked,
        "read": _read_invoked,
        "write": _write_invoked,
        "edit": _edit_invoked,
    }
    invoked = builders.get(name, _generic_invoked)(args, text, is_error)
    return ToolProjection(
        wire_name=map_dsh_tool(name),
        started_state={},
        invoked_state=invoked,
    )
