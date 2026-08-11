"""LCA tool names → LobeHub wire format (``identifier____apiName``).

Single declarative registry for **all** tool wire mappings:
- LobeHub builtin plugins (skills, web-browsing, user-interaction, skill-store)
- LobeHub cloud-sandbox (computer tools)

Each entry is a ``ToolWireSpec`` with:
- ``identifier`` / ``api_name`` — LobeHub plugin coordinates
- ``transform_args`` — LCA args → LobeHub wire args
- ``build_state`` — LCA result → LobeHub plugin state (for tool cards)

Unmapped tools fall back to raw LCA names (no wire translation).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gateway.lobehub_bridge._wire_helpers import (
    add_error_field,
    copy_fields,
    first_str,
    merge_success_state,
    parse_args_json,
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

PLUGIN_SCHEMA_SEPARATOR = "____"

# ── Plugin identifiers ──────────────────────────────────────

LOBE_SKILLS_ID = "lobe-skills"
LOBE_SKILL_STORE_ID = "lobe-skill-store"
LOBE_LOCAL_SYSTEM_ID = "lobe-local-system"
LOBE_WEB_BROWSING_ID = "lobe-web-browsing"
LOBE_USER_INTERACTION_ID = "lobe-user-interaction"
LOBE_CLOUD_SANDBOX_ID = "lobe-cloud-sandbox"

# ── API method names ────────────────────────────────────────

# Skills
SKILLS_API_ACTIVATE = "activateSkill"
SKILLS_API_EXEC = "execScript"
SKILLS_API_READ_REF = "readReference"
# Skill store
SKILL_STORE_API_SEARCH = "searchSkill"
SKILL_STORE_API_IMPORT = "importSkill"
SKILL_STORE_API_IMPORT_MARKET = "importFromMarket"
# Web browsing
WEB_BROWSING_API_SEARCH = "search"
# User interaction
USER_INTERACTION_API_ASK = "askUserQuestion"
# Cloud sandbox
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

# ── Limits ──────────────────────────────────────────────────

SKILL_CONTENT_MAX_LEN = 32_000
TOOL_RESULT_PREVIEW_LIMIT = 500

# ── Types ───────────────────────────────────────────────────

ArgsTransform = Callable[[dict[str, Any]], dict[str, Any]]
StateBuilder = Callable[[dict[str, Any], dict[str, Any], bool, str], dict[str, Any]]


# ── Wire name helpers ───────────────────────────────────────


def wire_tool_name(identifier: str, api_name: str) -> str:
    """OpenAI function.name wire form expected by LobeHub ``ToolNameResolver``."""
    return f"{identifier}{PLUGIN_SCHEMA_SEPARATOR}{api_name}"


def split_wire_name(wire_name: str) -> tuple[str, str]:
    """Split ``identifier____apiName`` back into LobeHub plugin coordinates."""
    if PLUGIN_SCHEMA_SEPARATOR in wire_name:
        identifier, api_name = wire_name.split(PLUGIN_SCHEMA_SEPARATOR, 1)
        return identifier, api_name
    return wire_name, ""


# ── ToolWireSpec ────────────────────────────────────────────


@dataclass(frozen=True)
class ToolWireSpec:
    lca_name: str
    identifier: str
    api_name: str
    transform_args: ArgsTransform
    build_state: StateBuilder

    @property
    def wire_name(self) -> str:
        return wire_tool_name(self.identifier, self.api_name)


def _spec(
    lca_name: str,
    identifier: str,
    api_name: str,
    transform_args: ArgsTransform,
    build_state: StateBuilder | None = None,
) -> ToolWireSpec:
    """Shorthand factory — defaults ``build_state`` to ``merge_success_state``."""
    return ToolWireSpec(
        lca_name=lca_name,
        identifier=identifier,
        api_name=api_name,
        transform_args=transform_args,
        build_state=build_state or merge_success_state,
    )


# ════════════════════════════════════════════════════════════
#  Argument transforms
# ════════════════════════════════════════════════════════════

# ── Skills ──────────────────────────────────────────────────


def _transform_activate_skill(args: dict[str, Any]) -> dict[str, Any]:
    skill_id = first_str(args, "skill_id", "name", "identifier")
    return {"name": skill_id} if skill_id else {}


def _transform_exec_script(args: dict[str, Any]) -> dict[str, Any]:
    out = copy_fields(args, [("command", "command"), ("skill_id", "skill_id")])
    command = out.get("command", "")
    if command:
        out["description"] = command[:200]
    return out


def _transform_read_reference(args: dict[str, Any]) -> dict[str, Any]:
    return copy_fields(args, [("skill_id", "id"), ("path", "path")])


def _transform_search_skill(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    query = first_str(args, "query", "q")
    if query:
        out["q"] = query
    for key in ("page", "page_size", "pageSize"):
        val = args.get(key)
        if isinstance(val, int):
            out["page" if key == "page" else "pageSize"] = val
    return out


def _transform_import_skill(args: dict[str, Any]) -> dict[str, Any]:
    identifier = first_str(args, "identifier")
    if identifier:
        return {"identifier": identifier}
    url = first_str(args, "url")
    if not url:
        return {}
    kind = first_str(args, "kind") or "auto"
    return {"type": "zip" if kind == "zip" else "url", "url": url}


# ── Web browsing ────────────────────────────────────────────


def _transform_web_search(args: dict[str, Any]) -> dict[str, Any]:
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


# ── User interaction ────────────────────────────────────────


def _transform_ask_user(args: dict[str, Any]) -> dict[str, Any]:
    questions = args.get("questions")
    if isinstance(questions, list) and questions:
        return {"questions": questions}
    return {}


# ── Cloud sandbox (computer tools) ──────────────────────────


def _transform_execute_code(args: dict[str, Any]) -> dict[str, Any]:
    return copy_fields(
        args, [("description", "description"), ("language", "language"), ("code", "code")]
    )


def _transform_run_command(args: dict[str, Any]) -> dict[str, Any]:
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


def _transform_list_files(args: dict[str, Any]) -> dict[str, Any]:
    path = first_str(args, "directoryPath", "directory_path") or "/mnt/data"
    return {"directoryPath": path}


def _transform_read_file(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    path = first_str(args, "path")
    if path:
        out["path"] = path
    for src, dst in [
        ("startLine", "startLine"),
        ("start_line", "startLine"),
        ("endLine", "endLine"),
        ("end_line", "endLine"),
    ]:
        val = args.get(src)
        if isinstance(val, (int, float)):
            out[dst] = int(val)
    return out


def _transform_write_file(args: dict[str, Any]) -> dict[str, Any]:
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


def _transform_edit_file(args: dict[str, Any]) -> dict[str, Any]:
    out = copy_fields(args, [("path", "path"), ("search", "search"), ("replace", "replace")])
    if "all" in args or "replace_all" in args:
        out["all"] = bool(args.get("all", args.get("replace_all", False)))
    return out


def _transform_search_files(args: dict[str, Any]) -> dict[str, Any]:
    return copy_fields(
        args,
        [
            ("directory", "directory"),
            ("keyword", "keyword"),
            ("fileType", "fileType"),
            ("modifiedAfter", "modifiedAfter"),
            ("modifiedBefore", "modifiedBefore"),
        ],
    )


def _transform_move_files(args: dict[str, Any]) -> dict[str, Any]:
    ops = args.get("operations")
    return {"operations": ops} if isinstance(ops, list) else {}


def _transform_grep_content(args: dict[str, Any]) -> dict[str, Any]:
    out = copy_fields(
        args, [("pattern", "pattern"), ("directory", "directory"), ("filePattern", "filePattern")]
    )
    if "recursive" in args:
        out["recursive"] = bool(args.get("recursive"))
    return out


def _transform_glob_files(args: dict[str, Any]) -> dict[str, Any]:
    return copy_fields(args, [("pattern", "pattern"), ("directory", "directory")])


def _transform_command_id(args: dict[str, Any]) -> dict[str, Any]:
    command_id = first_str(args, "commandId", "command_id")
    return {"commandId": command_id} if command_id else {}


def _transform_export_file(args: dict[str, Any]) -> dict[str, Any]:
    path = first_str(args, "path")
    return {"path": path} if path else {}


def _transform_write_file_local(args: dict[str, Any]) -> dict[str, Any]:
    """Local-system writeFile (lobe-local-system plugin)."""
    out: dict[str, Any] = {}
    path = first_str(args, "path", "name", "filename", "file_name")
    if path:
        out["path"] = path
    if isinstance(args.get("content"), str):
        out["content"] = args["content"]
    return out


# ════════════════════════════════════════════════════════════
#  State builders (custom — non-default)
# ════════════════════════════════════════════════════════════


def _state_activate_skill(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    name = first_str(args, "name", "skill_id") or first_str(payload, "skill_id")
    skill_id = first_str(payload, "skill_id") or name
    title = name or skill_id
    description = ""
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped[:200]
                break
            if stripped.startswith("# "):
                title = stripped[2:].strip() or title
    state: dict[str, Any] = {
        "hasResources": True,
        "id": skill_id,
        "name": name or skill_id,
        "title": title,
        "source": "agent",
        "success": ok,
    }
    if description:
        state["description"] = description
    return add_error_field(state, ok, error)


def _state_web_search(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    nested = payload.get("state")
    if isinstance(nested, dict):
        state = dict(nested)
        state["success"] = ok
        return add_error_field(state, ok, error, error_key="errorDetail")
    query = first_str(args, "query") or first_str(payload, "query")
    state = {"query": query, "resultNumbers": 0, "results": [], "success": ok}
    return add_error_field(state, ok, error, error_key="errorDetail")


def _state_exec_script(
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
    return add_error_field(state, ok, error)


def _state_run_command(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    command = first_str(args, "command") or first_str(payload, "command")
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
    return add_error_field(state, ok, error)


def _state_execute_code(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "success": ok,
        "language": first_str(args, "language") or str(payload.get("language") or "python"),
        "output": payload.get("output") or payload.get("stdout") or "",
        "stderr": payload.get("stderr") or "",
    }
    exit_code = payload.get("exitCode", payload.get("exit_code"))
    if isinstance(exit_code, int):
        state["exitCode"] = exit_code
    return add_error_field(state, ok, error)


def _state_export_file(
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
    return add_error_field(state, ok, error)


def _state_import_skill(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    skill_id = first_str(payload, "skill_id")
    name = first_str(payload, "name") or skill_id
    state = {
        "skillId": skill_id,
        "name": name,
        "status": "created" if ok else "unchanged",
        "success": ok,
    }
    return add_error_field(state, ok, error)


def _state_write_file(
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
    return add_error_field(state, ok, error)


def _state_ask_user(
    arguments: dict[str, Any], result: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    state: dict[str, Any] = {"success": ok}
    questions = arguments.get("questions")
    if isinstance(questions, list):
        state["questions"] = questions
    return add_error_field(state, ok, error)


# ════════════════════════════════════════════════════════════
#  Unified tool registry
# ════════════════════════════════════════════════════════════

_WireFactory = Callable[[dict[str, Any]], ToolWireSpec]


def _import_skill_spec(args: dict[str, Any]) -> ToolWireSpec:
    """Dynamic: identifier-based import goes to market, URL-based to direct import."""
    if first_str(args, "identifier"):
        return _spec(
            "import_skill",
            LOBE_SKILL_STORE_ID,
            SKILL_STORE_API_IMPORT_MARKET,
            _transform_import_skill,
            _state_import_skill,
        )
    return _spec(
        "import_skill",
        LOBE_SKILL_STORE_ID,
        SKILL_STORE_API_IMPORT,
        _transform_import_skill,
        _state_import_skill,
    )


TOOL_REGISTRY: dict[str, ToolWireSpec | _WireFactory] = {
    # ── Skills ──
    "activate_skill": _spec(
        "activate_skill",
        LOBE_SKILLS_ID,
        SKILLS_API_ACTIVATE,
        _transform_activate_skill,
        _state_activate_skill,
    ),
    "run_skill_script": _spec(
        "run_skill_script",
        LOBE_SKILLS_ID,
        SKILLS_API_EXEC,
        _transform_exec_script,
        _state_exec_script,
    ),
    "read_skill_reference": _spec(
        "read_skill_reference", LOBE_SKILLS_ID, SKILLS_API_READ_REF, _transform_read_reference
    ),
    "search_skill": _spec(
        "search_skill", LOBE_SKILL_STORE_ID, SKILL_STORE_API_SEARCH, _transform_search_skill
    ),
    "import_skill": _import_skill_spec,
    # ── Web browsing ──
    "web_search": _spec(
        "web_search",
        LOBE_WEB_BROWSING_ID,
        WEB_BROWSING_API_SEARCH,
        _transform_web_search,
        _state_web_search,
    ),
    # ── User interaction ──
    "ask_user_question": _spec(
        "ask_user_question",
        LOBE_USER_INTERACTION_ID,
        USER_INTERACTION_API_ASK,
        _transform_ask_user,
        _state_ask_user,
    ),
    # ── Cloud sandbox (computer tools) ──
    EXECUTE_CODE: _spec(
        EXECUTE_CODE,
        LOBE_CLOUD_SANDBOX_ID,
        API_EXECUTE_CODE,
        _transform_execute_code,
        _state_execute_code,
    ),
    RUN_COMMAND: _spec(
        RUN_COMMAND,
        LOBE_CLOUD_SANDBOX_ID,
        API_RUN_COMMAND,
        _transform_run_command,
        _state_run_command,
    ),
    LIST_FILES: _spec(LIST_FILES, LOBE_CLOUD_SANDBOX_ID, API_LIST_FILES, _transform_list_files),
    READ_FILE: _spec(READ_FILE, LOBE_CLOUD_SANDBOX_ID, API_READ_FILE, _transform_read_file),
    WRITE_FILE: _spec(
        WRITE_FILE, LOBE_CLOUD_SANDBOX_ID, API_WRITE_FILE, _transform_write_file, _state_write_file
    ),
    EDIT_FILE: _spec(EDIT_FILE, LOBE_CLOUD_SANDBOX_ID, API_EDIT_FILE, _transform_edit_file),
    SEARCH_FILES: _spec(
        SEARCH_FILES, LOBE_CLOUD_SANDBOX_ID, API_SEARCH_FILES, _transform_search_files
    ),
    MOVE_FILES: _spec(MOVE_FILES, LOBE_CLOUD_SANDBOX_ID, API_MOVE_FILES, _transform_move_files),
    GREP_CONTENT: _spec(
        GREP_CONTENT, LOBE_CLOUD_SANDBOX_ID, API_GREP_CONTENT, _transform_grep_content
    ),
    GLOB_FILES: _spec(GLOB_FILES, LOBE_CLOUD_SANDBOX_ID, API_GLOB_FILES, _transform_glob_files),
    GET_COMMAND_OUTPUT: _spec(
        GET_COMMAND_OUTPUT, LOBE_CLOUD_SANDBOX_ID, API_GET_COMMAND_OUTPUT, _transform_command_id
    ),
    KILL_COMMAND: _spec(
        KILL_COMMAND, LOBE_CLOUD_SANDBOX_ID, API_KILL_COMMAND, _transform_command_id
    ),
    EXPORT_FILE: _spec(
        EXPORT_FILE,
        LOBE_CLOUD_SANDBOX_ID,
        API_EXPORT_FILE,
        _transform_export_file,
        _state_export_file,
    ),
}

# Backward-compatible alias for tests
CLOUD_SANDBOX_WIRE: dict[str, ToolWireSpec] = {
    k: v
    for k, v in TOOL_REGISTRY.items()
    if isinstance(v, ToolWireSpec) and v.identifier == LOBE_CLOUD_SANDBOX_ID
}


# ════════════════════════════════════════════════════════════
#  Public API
# ════════════════════════════════════════════════════════════


def resolve_tool_wire(tool_name: str, arguments_preview: str = "") -> ToolWireSpec | None:
    """Look up the wire spec for an LCA tool name."""
    entry = TOOL_REGISTRY.get(tool_name)
    if entry is None:
        return None
    if callable(entry) and not isinstance(entry, ToolWireSpec):
        return entry(parse_args_json(arguments_preview))
    return entry


def transform_tool_arguments(spec: ToolWireSpec, arguments_preview: str) -> str:
    """Transform LCA arguments JSON → LobeHub wire arguments JSON."""
    args = spec.transform_args(parse_args_json(arguments_preview))
    return json.dumps(args, ensure_ascii=False)


def build_tool_plugin_state(
    spec: ToolWireSpec,
    *,
    arguments_preview: str,
    result_preview: str,
    ok: bool,
    error: str,
) -> dict[str, Any]:
    """Build LobeHub plugin state from LCA tool invocation result."""
    args = spec.transform_args(parse_args_json(arguments_preview))
    payload = parse_args_json(result_preview)
    return spec.build_state(args, payload, ok, error)


def tool_result_content(
    result_preview: str, *, ok: bool, error: str, lca_tool_name: str = ""
) -> str:
    """Extract user-visible text from a tool result for LobeHub display."""
    if ok:
        text = _extract_payload_text(result_preview, lca_tool_name=lca_tool_name)
        return text if text else "ok"
    extracted = _extract_payload_text(result_preview, lca_tool_name=lca_tool_name)
    if extracted:
        return extracted
    return error or "tool failed"


def tool_result_preview_limit(lca_tool_name: str) -> int:
    """Max result length for tool preview (skill content gets a larger limit)."""
    if lca_tool_name in {"activate_skill", "web_search", "read_skill_reference"}:
        return SKILL_CONTENT_MAX_LEN
    return TOOL_RESULT_PREVIEW_LIMIT


# ── Internal helpers ────────────────────────────────────────


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
