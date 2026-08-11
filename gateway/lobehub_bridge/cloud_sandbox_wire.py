"""LCA computer tools → LobeHub ``lobe-cloud-sandbox____*`` wire mappings."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gateway.lobehub_bridge.tool_wire import (
    ArgsTransform,
    StateBuilder,
    ToolWireSpec,
    _first_str,
    _parse_args_json,  # noqa: F401 — reserved for wire extension consumers
)
from lca.layer0_infra.tools.computer.specs import (
    EDIT_FILE,
    EXECUTE_CODE,
    EXPORT_FILE,
    GET_COMMAND_OUTPUT,
    GLOB_FILES,
    GREP_CONTENT,
    KILL_COMMAND,
    LIST_FILES,
    MOVE_FILES,
    READ_FILE,
    RUN_COMMAND,
    SEARCH_FILES,
    WRITE_FILE,
)

LOBE_CLOUD_SANDBOX_ID = "lobe-cloud-sandbox"

API_EXECUTE_CODE = "executeCode"
API_RUN_COMMAND = "runCommand"
API_LIST_FILES = "listFiles"
API_READ_FILE = "readFile"
API_WRITE_FILE = "writeFile"
API_EDIT_FILE = "editFile"
API_SEARCH_FILES = "searchFiles"
API_MOVE_FILES = "moveFiles"
API_GREP_CONTENT = "grepContent"
API_GLOB_FILES = "globFiles"
API_GET_COMMAND_OUTPUT = "getCommandOutput"
API_KILL_COMMAND = "killCommand"
API_EXPORT_FILE = "exportFile"


def _state_ok(
    _args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    state = dict(payload)
    state["success"] = ok
    if not ok and error:
        state["error"] = error
    return state


def _transform_execute_code(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("description", "language", "code"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    return out


def _transform_run_command(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    command = _first_str(args, "command")
    if command:
        out["command"] = command
        out["description"] = _first_str(args, "description") or command[:200]
    if "background" in args:
        out["background"] = bool(args.get("background"))
    timeout = args.get("timeout")
    if isinstance(timeout, (int, float)):
        out["timeout"] = int(timeout)
    return out


def _transform_list_files(args: dict[str, Any]) -> dict[str, Any]:
    path = _first_str(args, "directoryPath", "directory_path") or "/mnt/data"
    return {"directoryPath": path}


def _transform_read_file(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    path = _first_str(args, "path")
    if path:
        out["path"] = path
    for src, dst in (
        ("startLine", "startLine"),
        ("start_line", "startLine"),
        ("endLine", "endLine"),
        ("end_line", "endLine"),
    ):
        val = args.get(src)
        if isinstance(val, (int, float)):
            out[dst] = int(val)
    return out


def _transform_write_file(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    path = _first_str(args, "path")
    if path:
        out["path"] = path
    if "content" in args:
        out["content"] = args.get("content")
    if "createDirectories" in args or "create_directories" in args:
        out["createDirectories"] = bool(
            args.get("createDirectories", args.get("create_directories", True))
        )
    return out


def _transform_edit_file(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("path", "search", "replace"):
        val = _first_str(args, key)
        if val:
            out[key] = val
    if "all" in args or "replace_all" in args:
        out["all"] = bool(args.get("all", args.get("replace_all", False)))
    return out


def _transform_search_files(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    directory = _first_str(args, "directory")
    if directory:
        out["directory"] = directory
    keyword = _first_str(args, "keyword")
    if keyword:
        out["keyword"] = keyword
    file_type = _first_str(args, "fileType", "file_type")
    if file_type:
        out["fileType"] = file_type
    modified_after = _first_str(args, "modifiedAfter", "modified_after")
    if modified_after:
        out["modifiedAfter"] = modified_after
    modified_before = _first_str(args, "modifiedBefore", "modified_before")
    if modified_before:
        out["modifiedBefore"] = modified_before
    return out


def _transform_move_files(args: dict[str, Any]) -> dict[str, Any]:
    ops = args.get("operations")
    return {"operations": ops} if isinstance(ops, list) else {}


def _transform_grep_content(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    pattern = _first_str(args, "pattern")
    if pattern:
        out["pattern"] = pattern
    directory = _first_str(args, "directory")
    if directory:
        out["directory"] = directory
    file_pattern = _first_str(args, "filePattern", "file_pattern")
    if file_pattern:
        out["filePattern"] = file_pattern
    if "recursive" in args:
        out["recursive"] = bool(args.get("recursive"))
    return out


def _transform_glob_files(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    pattern = _first_str(args, "pattern")
    if pattern:
        out["pattern"] = pattern
    directory = _first_str(args, "directory")
    if directory:
        out["directory"] = directory
    return out


def _transform_command_id(args: dict[str, Any]) -> dict[str, Any]:
    command_id = _first_str(args, "commandId", "command_id")
    return {"commandId": command_id} if command_id else {}


def _transform_export_file(args: dict[str, Any]) -> dict[str, Any]:
    path = _first_str(args, "path")
    return {"path": path} if path else {}


def _state_run_command(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    command = _first_str(args, "command") or _first_str(payload, "command")
    state: dict[str, Any] = {
        "command": command,
        "executionEnv": "sandbox",
        "success": ok,
        "isBackground": bool(payload.get("isBackground", args.get("background", False))),
    }
    for key in ("stdout", "stderr", "output", "commandId"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            state[key] = val
    exit_code = payload.get("exitCode", payload.get("exit_code"))
    if isinstance(exit_code, int):
        state["exitCode"] = exit_code
    elif ok and not state.get("isBackground"):
        state["exitCode"] = 0
    if not ok and error:
        state["error"] = error
    return state


def _state_execute_code(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "success": ok,
        "language": _first_str(args, "language") or str(payload.get("language") or "python"),
        "output": payload.get("output") or payload.get("stdout") or "",
        "stderr": payload.get("stderr") or "",
    }
    exit_code = payload.get("exitCode", payload.get("exit_code"))
    if isinstance(exit_code, int):
        state["exitCode"] = exit_code
    if not ok and error:
        state["error"] = error
    return state


def _state_export_file(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "success": ok,
        "path": _first_str(args, "path") or _first_str(payload, "path"),
        "filename": payload.get("filename") or "",
        "downloadUrl": payload.get("downloadUrl") or payload.get("url") or "",
    }
    size = payload.get("size", payload.get("sizeBytes"))
    if isinstance(size, int):
        state["size"] = size
    if not ok and error:
        state["error"] = error
    return state


def _wire_spec(
    lca_name: str,
    api_name: str,
    transform_args: ArgsTransform,
    build_state: StateBuilder | None = None,
) -> ToolWireSpec:
    return ToolWireSpec(
        lca_name=lca_name,
        identifier=LOBE_CLOUD_SANDBOX_ID,
        api_name=api_name,
        transform_args=transform_args,
        build_state=build_state or _state_ok,
    )


CLOUD_SANDBOX_WIRE: dict[str, ToolWireSpec] = {
    EXECUTE_CODE: _wire_spec(
        EXECUTE_CODE, API_EXECUTE_CODE, _transform_execute_code, _state_execute_code
    ),
    RUN_COMMAND: _wire_spec(
        RUN_COMMAND, API_RUN_COMMAND, _transform_run_command, _state_run_command
    ),
    LIST_FILES: _wire_spec(LIST_FILES, API_LIST_FILES, _transform_list_files),
    READ_FILE: _wire_spec(READ_FILE, API_READ_FILE, _transform_read_file),
    WRITE_FILE: _wire_spec(WRITE_FILE, API_WRITE_FILE, _transform_write_file),
    EDIT_FILE: _wire_spec(EDIT_FILE, API_EDIT_FILE, _transform_edit_file),
    SEARCH_FILES: _wire_spec(SEARCH_FILES, API_SEARCH_FILES, _transform_search_files),
    MOVE_FILES: _wire_spec(MOVE_FILES, API_MOVE_FILES, _transform_move_files),
    GREP_CONTENT: _wire_spec(GREP_CONTENT, API_GREP_CONTENT, _transform_grep_content),
    GLOB_FILES: _wire_spec(GLOB_FILES, API_GLOB_FILES, _transform_glob_files),
    GET_COMMAND_OUTPUT: _wire_spec(
        GET_COMMAND_OUTPUT, API_GET_COMMAND_OUTPUT, _transform_command_id
    ),
    KILL_COMMAND: _wire_spec(KILL_COMMAND, API_KILL_COMMAND, _transform_command_id),
    EXPORT_FILE: _wire_spec(
        EXPORT_FILE, API_EXPORT_FILE, _transform_export_file, _state_export_file
    ),
}


def merge_cloud_sandbox_wire(
    registry: dict[str, ToolWireSpec | Callable[[dict[str, Any]], ToolWireSpec]],
) -> None:
    registry.update(CLOUD_SANDBOX_WIRE)
