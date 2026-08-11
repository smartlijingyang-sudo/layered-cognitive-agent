"""Tool wire registry — maps LCA tool names to LobeHub wire specifications.

Central lookup table: given an LCA tool name (e.g. ``execute_code``),
return the ``ToolWireSpec`` that tells the projector how to format
arguments and build state for LobeHub's frontend.

Uses the Registry pattern: specs are registered declaratively at module
load time, and ``resolve_tool_wire()`` provides O(1) lookup with optional
dynamic factory support for context-dependent specs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gateway.lobehub_bridge.lobehub_adapter.adapt_arguments import (
    adapt_activate_skill,
    adapt_ask_user,
    adapt_command_id,
    adapt_edit_file,
    adapt_exec_script,
    adapt_execute_code,
    adapt_export_file,
    adapt_glob_files,
    adapt_grep_content,
    adapt_import_skill,
    adapt_list_files,
    adapt_move_files,
    adapt_read_file,
    adapt_read_reference,
    adapt_run_command,
    adapt_search_files,
    adapt_search_skill,
    adapt_web_search,
    adapt_write_file,
    adapt_write_file_local,
)
from gateway.lobehub_bridge.lobehub_adapter.build_state import (
    build_activate_skill_state,
    build_ask_user_state,
    build_exec_script_state,
    build_execute_code_state,
    build_export_file_state,
    build_import_skill_state,
    build_run_command_state,
    build_web_search_state,
    build_write_file_state,
)
from gateway.lobehub_bridge.lobehub_adapter.json_helpers import (
    first_str,
    parse_args_json,
)
from gateway.lobehub_bridge.lobehub_adapter.protocol import (
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
    SKILL_STORE_API_IMPORT,
    SKILL_STORE_API_IMPORT_MARKET,
    SKILL_STORE_API_SEARCH,
    SKILLS_API_ACTIVATE,
    SKILLS_API_EXEC,
    SKILLS_API_READ_REF,
    USER_INTERACTION_API_ASK,
    WEB_BROWSING_API_SEARCH,
)
from gateway.lobehub_bridge.lobehub_adapter.tool_spec import (
    ToolWireSpec,
    make_spec,
)

# ── Dynamic factory type ────────────────────────────────────

_WireFactory = Callable[[dict[str, Any]], ToolWireSpec]


# ── Dynamic spec: import_skill ──────────────────────────────


def _import_skill_spec(args: dict[str, Any]) -> ToolWireSpec:
    """Dynamic: identifier-based import goes to market, URL-based to direct."""
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


# ═══════════════════════════════════════════════════════════
#  Unified tool registry
# ═══════════════════════════════════════════════════════════

TOOL_REGISTRY: dict[str, ToolWireSpec | _WireFactory] = {
    # ── Skills ──
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
        "read_skill_reference",
        LOBE_SKILLS_ID,
        SKILLS_API_READ_REF,
        adapt_read_reference,
    ),
    "search_skill": make_spec(
        "search_skill",
        LOBE_SKILL_STORE_ID,
        SKILL_STORE_API_SEARCH,
        adapt_search_skill,
    ),
    "import_skill": _import_skill_spec,
    # ── Web browsing ──
    "web_search": make_spec(
        "web_search",
        LOBE_WEB_BROWSING_ID,
        WEB_BROWSING_API_SEARCH,
        adapt_web_search,
        build_web_search_state,
    ),
    # ── User interaction ──
    "ask_user_question": make_spec(
        "ask_user_question",
        LOBE_USER_INTERACTION_ID,
        USER_INTERACTION_API_ASK,
        adapt_ask_user,
        build_ask_user_state,
    ),
    # ── Cloud sandbox (computer tools) ──
    # State builders here are fallbacks — computer tools produce state
    # via ComputerOpResult.state → ToolInvoked.plugin_state directly.
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
    # ── Local system ──
    "write_file_local": make_spec(
        "write_file_local",
        LOBE_LOCAL_SYSTEM_ID,
        API_WRITE_FILE,
        adapt_write_file_local,
    ),
}

# Backward-compatible alias for tests
CLOUD_SANDBOX_WIRE: dict[str, ToolWireSpec] = {
    k: v
    for k, v in TOOL_REGISTRY.items()
    if isinstance(v, ToolWireSpec) and v.identifier == LOBE_CLOUD_SANDBOX_ID
}


# ═══════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════


def resolve_tool_wire(tool_name: str, arguments_preview: str = "") -> ToolWireSpec | None:
    """Look up the wire spec for an LCA tool name.

    Supports both static ``ToolWireSpec`` entries and dynamic factories
    that select the spec based on argument content (e.g. ``import_skill``
    routes to market or direct import depending on args).
    """
    entry = TOOL_REGISTRY.get(tool_name)
    if entry is None:
        return None
    if callable(entry) and not isinstance(entry, ToolWireSpec):
        return entry(parse_args_json(arguments_preview))
    return entry


def transform_tool_arguments(spec: ToolWireSpec, arguments_preview: str) -> str:
    """Transform LCA arguments JSON → LobeHub wire arguments JSON."""
    import json

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
    from gateway.lobehub_bridge.lobehub_adapter.protocol import (
        SKILL_CONTENT_MAX_LEN,
        TOOL_RESULT_PREVIEW_LIMIT,
    )

    if lca_tool_name in {"activate_skill", "web_search", "read_skill_reference"}:
        return SKILL_CONTENT_MAX_LEN
    return TOOL_RESULT_PREVIEW_LIMIT


# ── Internal helpers ────────────────────────────────────────


def _extract_payload_text(raw: str, *, lca_tool_name: str) -> str:
    import json

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
