"""State builder strategies — LCA result → LobeHub pluginState.

Each function transforms an LCA tool result into the state shape that
LobeHub's frontend Render components expect.

Design note: computer tools (file operations) produce LobeHub-compatible
state directly from the sandbox guest scripts. Their results flow through
``ToolInvoked.plugin_state`` and bypass these builders entirely. The builders
here serve as fallback for non-computer tools (skills, web search, etc.).
"""

from __future__ import annotations

from typing import Any

from gateway.lobehub_bridge.lobehub_adapter.json_helpers import first_str

# ── Default strategy ────────────────────────────────────────


def merge_success_state(
    _args: dict[str, Any],
    payload: dict[str, Any],
    ok: bool,
    error: str,
) -> dict[str, Any]:
    """Default state builder: shallow-copy payload + success + optional error."""
    state = dict(payload)
    state["success"] = ok
    if not ok and error:
        state["error"] = error
    return state


# ── Error utility ───────────────────────────────────────────


def add_error_field(
    state: dict[str, Any],
    ok: bool,
    error: str,
    *,
    error_key: str = "error",
) -> dict[str, Any]:
    """Append an error field to *state* when the operation failed."""
    if not ok and error:
        state[error_key] = error
    return state


# ═══════════════════════════════════════════════════════════
#  Skills
# ═══════════════════════════════════════════════════════════


def build_activate_skill_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Skill activation card: title, description, full SKILL.md content.

    Fallback for legacy journal events without ``plugin_state``. Live path
    prefers SafeExecutor-produced ``plugin_state`` (full content).
    """
    name = first_str(args, "name", "skill_id") or first_str(payload, "skill_id")
    skill_id = first_str(payload, "skill_id") or name
    title = name or skill_id
    description = ""
    # Prefer full content if already on state-shaped payload; else text body.
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
    return add_error_field(state, ok, error)


def build_exec_script_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Script execution card: command, stdout, stderr, exit code."""
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


def build_import_skill_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Skill import card: skillId, name, status."""
    del args
    skill_id = first_str(payload, "skill_id")
    name = first_str(payload, "name") or skill_id
    state = {
        "skillId": skill_id,
        "name": name,
        "status": "created" if ok else "unchanged",
        "success": ok,
    }
    return add_error_field(state, ok, error)


# ═══════════════════════════════════════════════════════════
#  Web browsing
# ═══════════════════════════════════════════════════════════


def build_web_search_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Web search card: pass through nested state or build from query."""
    nested = payload.get("state")
    if isinstance(nested, dict):
        state = dict(nested)
        state["success"] = ok
        return add_error_field(state, ok, error, error_key="errorDetail")
    query = first_str(args, "query") or first_str(payload, "query")
    state = {"query": query, "resultNumbers": 0, "results": [], "success": ok}
    return add_error_field(state, ok, error, error_key="errorDetail")


# ═══════════════════════════════════════════════════════════
#  User interaction
# ═══════════════════════════════════════════════════════════


def build_ask_user_state(
    arguments: dict[str, Any], result: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """User question card: questions list."""
    del result
    state: dict[str, Any] = {"success": ok}
    questions = arguments.get("questions")
    if isinstance(questions, list):
        state["questions"] = questions
    return add_error_field(state, ok, error)


# ═══════════════════════════════════════════════════════════
#  Cloud sandbox — execution
# ═══════════════════════════════════════════════════════════


def build_run_command_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Command execution card: full command, stdout/stderr, exit code, background flag."""
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
    return add_error_field(state, ok, error)


def build_execute_code_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Code execution card: language, code, description, output, stderr, exit code."""
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
    return add_error_field(state, ok, error)


# ═══════════════════════════════════════════════════════════
#  Cloud sandbox — file operations
# ═══════════════════════════════════════════════════════════


def build_write_file_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Write file card: path, success, size, url."""
    path = first_str(args, "path") or first_str(payload, "name", "path")
    state: dict[str, Any] = {"path": path, "success": ok}
    url = first_str(payload, "url")
    if url:
        state["url"] = url
    size = payload.get("sizeBytes", payload.get("size_bytes"))
    if isinstance(size, int):
        state["size"] = size
    return add_error_field(state, ok, error)


def build_export_file_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Export file card: path, filename, download URL, size."""
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
