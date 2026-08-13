"""Tool wire registry — 注册表 + 参数适配 + 状态构建。

单一文件包含：
  1. adapt_* 函数 — LCA args → LobeHub wire args
  2. build_*_state 函数 — LCA result → LobeHub pluginState
  3. TOOL_REGISTRY — 统一注册表，resolve_tool_wire() 查找
  4. 公共 API — resolve / transform / build / content / limit
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from gateway.lobehub_bridge.lobehub_adapter.tool_spec import (
    API_EDIT_FILE,
    API_EXECUTE_CODE,
    API_EXPORT_FILE,
    API_GET_COMMAND_OUTPUT,
    API_GLOB_FILES,
    API_GREP_CONTENT,
    API_KILL_COMMAND,
    API_LIST_FILES,
    API_MOVE_FILES,
    API_READ_FILE,
    API_RUN_COMMAND,
    API_SEARCH_FILES,
    API_WRITE_FILE,
    LOBE_CLOUD_SANDBOX_ID,
    LOBE_LOCAL_SYSTEM_ID,
    LOBE_SKILL_STORE_ID,
    LOBE_SKILLS_ID,
    LOBE_USER_INTERACTION_ID,
    LOBE_WEB_BROWSING_ID,
    SKILL_CONTENT_MAX_LEN,
    SKILL_STORE_API_IMPORT,
    SKILL_STORE_API_IMPORT_MARKET,
    SKILL_STORE_API_SEARCH,
    SKILLS_API_ACTIVATE,
    SKILLS_API_EXEC,
    SKILLS_API_READ_REF,
    TOOL_RESULT_PREVIEW_LIMIT,
    USER_INTERACTION_API_ASK,
    WEB_BROWSING_API_SEARCH,
    FieldMapper,
    ToolWireSpec,
    _add_error,
    copy_fields,
    first_str,
    make_spec,
    parse_args_json,
)

# ═══════════════════════════════════════════════════════════
#  Argument adaptation — LCA args → LobeHub wire args
# ═══════════════════════════════════════════════════════════

# ── Skills ──


def adapt_activate_skill(args: dict[str, Any]) -> dict[str, Any]:
    skill_id = first_str(args, "skill_id", "name", "identifier")
    return {"name": skill_id} if skill_id else {}


def adapt_exec_script(args: dict[str, Any]) -> dict[str, Any]:
    out = copy_fields(args, [("command", "command"), ("skill_id", "skill_id")])
    command = out.get("command", "")
    if command:
        out["description"] = command[:200]
    return out


adapt_read_reference = FieldMapper(strings=[("skill_id", "id"), ("path", "path")])


def adapt_search_skill(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    query = first_str(args, "query", "q")
    if query:
        out["q"] = query
    for key in ("page", "page_size", "pageSize"):
        val = args.get(key)
        if isinstance(val, int):
            out["page" if key == "page" else "pageSize"] = val
    topic = first_str(args, "topic")
    if topic:
        out["searchCategories"] = [topic]
    return out


def adapt_import_skill(args: dict[str, Any]) -> dict[str, Any]:
    identifier = first_str(args, "identifier")
    if identifier:
        return {"identifier": identifier}
    url = first_str(args, "url")
    if not url:
        return {}
    kind = first_str(args, "kind") or "auto"
    return {"type": "zip" if kind == "zip" else "url", "url": url}


# ── Web browsing ──


def adapt_web_search(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    query = first_str(args, "query", "q")
    if query:
        out["query"] = query
    topic = first_str(args, "topic")
    if topic:
        out["searchCategories"] = [topic]
    time_range = first_str(args, "time_range", "searchTimeRange")
    if time_range:
        out["searchTimeRange"] = time_range
    return out


# ── User interaction ──


def adapt_ask_user(args: dict[str, Any]) -> dict[str, Any]:
    questions = args.get("questions")
    if isinstance(questions, list) and questions:
        return {"questions": questions}
    return {}


# ── Cloud sandbox — execution ──

adapt_execute_code = FieldMapper(
    strings=[("description", "description"), ("language", "language"), ("code", "code")],
)


def adapt_run_command(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    command = first_str(args, "command")
    if command:
        out["command"] = command
        out["description"] = first_str(args, "description") or command[:200]
    if "background" in args:
        out["background"] = bool(args.get("background"))
    timeout = args.get("timeout")
    if isinstance(timeout, (int, float)):
        out["timeout"] = int(timeout)
    return out


# ── Cloud sandbox — file operations ──


def adapt_list_files(args: dict[str, Any]) -> dict[str, Any]:
    path = first_str(args, "directoryPath", "directory_path") or "/mnt/data"
    return {"directoryPath": path}


adapt_read_file = FieldMapper(
    strings=[("path", "path")],
    ints=[
        ("startLine", "startLine"),
        ("start_line", "startLine"),
        ("endLine", "endLine"),
        ("end_line", "endLine"),
    ],
)


def adapt_write_file(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    path = first_str(args, "path")
    if path:
        out["path"] = path
    if "content" in args:
        out["content"] = args.get("content")
    if "createDirectories" in args or "create_directories" in args:
        out["createDirectories"] = bool(
            args.get("createDirectories", args.get("create_directories", True))
        )
    return out


adapt_edit_file = FieldMapper(
    strings=[("path", "path"), ("search", "search"), ("replace", "replace")],
    bools=[("all", "all"), ("replace_all", "all")],
)

adapt_search_files = FieldMapper(
    strings=[
        ("directory", "directory"),
        ("keyword", "keyword"),
        ("fileType", "fileType"),
        ("modifiedAfter", "modifiedAfter"),
        ("modifiedBefore", "modifiedBefore"),
    ],
)

adapt_move_files = FieldMapper(lists=[("operations", "operations")])

adapt_grep_content = FieldMapper(
    strings=[("pattern", "pattern"), ("directory", "directory"), ("filePattern", "filePattern")],
    bools=[("recursive", "recursive")],
)

adapt_glob_files = FieldMapper(strings=[("pattern", "pattern"), ("directory", "directory")])

adapt_command_id = FieldMapper(strings=[("commandId", "commandId"), ("command_id", "commandId")])

adapt_export_file = FieldMapper(strings=[("path", "path")])


# ── Local system ──


def adapt_write_file_local(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    path = first_str(args, "path", "name", "filename", "file_name")
    if path:
        out["path"] = path
    if isinstance(args.get("content"), str):
        out["content"] = args["content"]
    return out


# ═══════════════════════════════════════════════════════════
#  State builders — LCA result → LobeHub pluginState
# ═══════════════════════════════════════════════════════════


def build_activate_skill_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    name = first_str(args, "name", "skill_id") or first_str(payload, "skill_id")
    skill_id = first_str(payload, "skill_id") or name
    title = name or skill_id
    description = ""
    text = payload.get("content")
    if not isinstance(text, str) or not text.strip():
        text = payload.get("text")
    if not isinstance(text, str):
        text = ""
    if text.strip():
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip() or title
                continue
            if stripped and not stripped.startswith("#"):
                description = stripped[:200]
                break
    state: dict[str, Any] = {
        "hasResources": True,
        "id": skill_id,
        "name": name or skill_id,
        "skill_id": skill_id,
        "title": title,
        "source": "agent",
        "success": ok,
    }
    if description:
        state["description"] = description
    if text:
        state["content"] = text
    return _add_error(state, ok, error)


def build_exec_script_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    command = first_str(args, "command") or first_str(payload, "command")
    state: dict[str, Any] = {"command": command, "executionEnv": "sandbox", "success": ok}
    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int):
        state["exitCode"] = exit_code
    elif ok:
        state["exitCode"] = 0
    for key in ("stdout", "stderr"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            state[key] = val
    return _add_error(state, ok, error)


def build_import_skill_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    del args
    skill_id = first_str(payload, "skill_id")
    name = first_str(payload, "name") or skill_id
    state = {
        "skillId": skill_id,
        "name": name,
        "status": "created" if ok else "unchanged",
        "success": ok,
    }
    return _add_error(state, ok, error)


def build_web_search_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    nested = payload.get("state")
    if isinstance(nested, dict):
        state = dict(nested)
        state["success"] = ok
        return _add_error(state, ok, error, key="errorDetail")
    query = first_str(args, "query") or first_str(payload, "query")
    state = {"query": query, "resultNumbers": 0, "results": [], "success": ok}
    return _add_error(state, ok, error, key="errorDetail")


def build_ask_user_state(
    arguments: dict[str, Any], result: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    del result
    state: dict[str, Any] = {"success": ok}
    questions = arguments.get("questions")
    if isinstance(questions, list):
        state["questions"] = questions
    return _add_error(state, ok, error)


def build_run_command_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    command = first_str(args, "command") or first_str(payload, "command")
    state: dict[str, Any] = {
        "command": command,
        "executionEnv": "sandbox",
        "success": ok,
        "isBackground": bool(payload.get("isBackground", args.get("background", False))),
    }
    desc = first_str(args, "description") or first_str(payload, "description")
    if desc:
        state["description"] = desc
    for key in ("stdout", "stderr", "output", "commandId"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            state[key] = val
    exit_code = payload.get("exitCode", payload.get("exit_code"))
    if isinstance(exit_code, int):
        state["exitCode"] = exit_code
    elif ok and not state.get("isBackground"):
        state["exitCode"] = 0
    return _add_error(state, ok, error)


def build_execute_code_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "success": ok,
        "language": first_str(args, "language") or str(payload.get("language") or "python"),
        "output": payload.get("output") or payload.get("stdout") or "",
        "stderr": payload.get("stderr") or "",
        "executionEnv": "sandbox",
    }
    code = first_str(args, "code") or (
        str(payload["code"]) if isinstance(payload.get("code"), str) else ""
    )
    if code:
        state["code"] = code
    desc = first_str(args, "description") or first_str(payload, "description")
    if desc:
        state["description"] = desc
    exit_code = payload.get("exitCode", payload.get("exit_code"))
    if isinstance(exit_code, int):
        state["exitCode"] = exit_code
    return _add_error(state, ok, error)


def build_write_file_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    path = first_str(args, "path") or first_str(payload, "name", "path")
    state: dict[str, Any] = {"path": path, "success": ok}
    url = first_str(payload, "url")
    if url:
        state["url"] = url
    size = payload.get("sizeBytes", payload.get("size_bytes"))
    if isinstance(size, int):
        state["size"] = size
    return _add_error(state, ok, error)


def build_export_file_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "success": ok,
        "path": first_str(args, "path") or first_str(payload, "path"),
        "filename": payload.get("filename") or "",
        "downloadUrl": payload.get("downloadUrl") or payload.get("url") or "",
    }
    size = payload.get("size", payload.get("sizeBytes"))
    if isinstance(size, int):
        state["size"] = size
    return _add_error(state, ok, error)


# ═══════════════════════════════════════════════════════════
#  Registry
# ═══════════════════════════════════════════════════════════

_WireFactory = Callable[[dict[str, Any]], ToolWireSpec]


def _import_skill_spec(args: dict[str, Any]) -> ToolWireSpec:
    if first_str(args, "identifier"):
        return make_spec(
            "import_skill",
            LOBE_SKILL_STORE_ID,
            SKILL_STORE_API_IMPORT_MARKET,
            adapt_import_skill,
            build_import_skill_state,
        )
    return make_spec(
        "import_skill",
        LOBE_SKILL_STORE_ID,
        SKILL_STORE_API_IMPORT,
        adapt_import_skill,
        build_import_skill_state,
    )


TOOL_REGISTRY: dict[str, ToolWireSpec | _WireFactory] = {
    # Skills
    "activate_skill": make_spec(
        "activate_skill",
        LOBE_SKILLS_ID,
        SKILLS_API_ACTIVATE,
        adapt_activate_skill,
        build_activate_skill_state,
    ),
    "run_skill_script": make_spec(
        "run_skill_script",
        LOBE_SKILLS_ID,
        SKILLS_API_EXEC,
        adapt_exec_script,
        build_exec_script_state,
    ),
    "read_skill_reference": make_spec(
        "read_skill_reference", LOBE_SKILLS_ID, SKILLS_API_READ_REF, adapt_read_reference
    ),
    "search_skill": make_spec(
        "search_skill", LOBE_SKILL_STORE_ID, SKILL_STORE_API_SEARCH, adapt_search_skill
    ),
    "import_skill": _import_skill_spec,
    # Web browsing
    "web_search": make_spec(
        "web_search",
        LOBE_WEB_BROWSING_ID,
        WEB_BROWSING_API_SEARCH,
        adapt_web_search,
        build_web_search_state,
    ),
    # User interaction
    "ask_user_question": make_spec(
        "ask_user_question",
        LOBE_USER_INTERACTION_ID,
        USER_INTERACTION_API_ASK,
        adapt_ask_user,
        build_ask_user_state,
    ),
    # Cloud sandbox
    "execute_code": make_spec(
        "execute_code",
        LOBE_CLOUD_SANDBOX_ID,
        API_EXECUTE_CODE,
        adapt_execute_code,
        build_execute_code_state,
    ),
    "run_command": make_spec(
        "run_command",
        LOBE_CLOUD_SANDBOX_ID,
        API_RUN_COMMAND,
        adapt_run_command,
        build_run_command_state,
    ),
    "list_files": make_spec("list_files", LOBE_CLOUD_SANDBOX_ID, API_LIST_FILES, adapt_list_files),
    "read_file": make_spec("read_file", LOBE_CLOUD_SANDBOX_ID, API_READ_FILE, adapt_read_file),
    "write_file": make_spec(
        "write_file",
        LOBE_CLOUD_SANDBOX_ID,
        API_WRITE_FILE,
        adapt_write_file,
        build_write_file_state,
    ),
    "edit_file": make_spec("edit_file", LOBE_CLOUD_SANDBOX_ID, API_EDIT_FILE, adapt_edit_file),
    "search_files": make_spec(
        "search_files", LOBE_CLOUD_SANDBOX_ID, API_SEARCH_FILES, adapt_search_files
    ),
    "move_files": make_spec("move_files", LOBE_CLOUD_SANDBOX_ID, API_MOVE_FILES, adapt_move_files),
    "grep_content": make_spec(
        "grep_content", LOBE_CLOUD_SANDBOX_ID, API_GREP_CONTENT, adapt_grep_content
    ),
    "glob_files": make_spec("glob_files", LOBE_CLOUD_SANDBOX_ID, API_GLOB_FILES, adapt_glob_files),
    "get_command_output": make_spec(
        "get_command_output", LOBE_CLOUD_SANDBOX_ID, API_GET_COMMAND_OUTPUT, adapt_command_id
    ),
    "kill_command": make_spec(
        "kill_command", LOBE_CLOUD_SANDBOX_ID, API_KILL_COMMAND, adapt_command_id
    ),
    "export_file": make_spec(
        "export_file",
        LOBE_CLOUD_SANDBOX_ID,
        API_EXPORT_FILE,
        adapt_export_file,
        build_export_file_state,
    ),
    # Local system
    "write_file_local": make_spec(
        "write_file_local", LOBE_LOCAL_SYSTEM_ID, API_WRITE_FILE, adapt_write_file_local
    ),
}

CLOUD_SANDBOX_WIRE: dict[str, ToolWireSpec] = {
    k: v
    for k, v in TOOL_REGISTRY.items()
    if isinstance(v, ToolWireSpec) and v.identifier == LOBE_CLOUD_SANDBOX_ID
}


# ═══════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════


def resolve_tool_wire(tool_name: str, arguments_preview: str = "") -> ToolWireSpec | None:
    entry = TOOL_REGISTRY.get(tool_name)
    if entry is None:
        return None
    if callable(entry) and not isinstance(entry, ToolWireSpec):
        return entry(parse_args_json(arguments_preview))
    return entry


def transform_tool_arguments(spec: ToolWireSpec, arguments_preview: str) -> str:
    args = spec.transform_args(parse_args_json(arguments_preview))
    return json.dumps(args, ensure_ascii=False)


def build_tool_plugin_state(
    spec: ToolWireSpec, *, arguments_preview: str, result_preview: str, ok: bool, error: str
) -> dict[str, Any]:
    args = spec.transform_args(parse_args_json(arguments_preview))
    payload = parse_args_json(result_preview)
    return spec.build_state(args, payload, ok, error)


def tool_result_content(
    result_preview: str, *, ok: bool, error: str, lca_tool_name: str = ""
) -> str:
    if ok:
        text = _extract_payload_text(result_preview, lca_tool_name=lca_tool_name)
        return text if text else "ok"
    extracted = _extract_payload_text(result_preview, lca_tool_name=lca_tool_name)
    if extracted:
        return extracted
    return error or "tool failed"


def tool_result_preview_limit(lca_tool_name: str) -> int:
    if lca_tool_name in {"activate_skill", "web_search", "read_skill_reference"}:
        return SKILL_CONTENT_MAX_LEN
    return TOOL_RESULT_PREVIEW_LIMIT


def _extract_payload_text(raw: str, *, lca_tool_name: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
    if not isinstance(parsed, dict):
        return text
    body = parsed.get("text")
    if isinstance(body, str) and body.strip():
        return body.strip()
    if lca_tool_name == "web_search" and isinstance(parsed.get("state"), dict):
        return text
    return text
