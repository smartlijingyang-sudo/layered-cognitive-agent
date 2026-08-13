"""Tool UI state builders — Strategy functions for started/invoked plugin_state.

Separated from the registry so each file stays under the 250-line effective
code limit. The registry lives in ``tool_ui_state``.
"""

from __future__ import annotations

from typing import Any

_COMPUTER_STATE_KEYS = frozenset(
    {
        "code",
        "command",
        "commandId",
        "executionEnv",
        "exitCode",
        "exit_code",
        "error",
        "errorDetail",
        "files",
        "isBackground",
        "language",
        "output",
        "stderr",
        "stdout",
        "success",
    }
)


# ── Markdown helpers ────────────────────────────────────────


def _title_from_markdown(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _description_from_markdown(text: str, *, max_len: int = 200) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped[:max_len]
    return ""


# ── Started builders ────────────────────────────────────────


def _started_execute_code(args: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "executionEnv": "sandbox",
        "language": str(args.get("language") or "python"),
    }
    for key in ("code", "description"):
        val = args.get(key)
        if isinstance(val, str):
            trimmed = val.strip() if key == "description" else val
            if trimmed:
                state[key] = trimmed
    return state


def _started_run_command(args: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "executionEnv": "sandbox",
        "isBackground": bool(args.get("background", False)),
    }
    for key in ("command", "description"):
        val = args.get(key)
        if isinstance(val, str):
            trimmed = val.strip() if key == "description" else val
            if trimmed:
                state[key] = trimmed
    return state


def _started_activate_skill(args: dict[str, Any]) -> dict[str, Any]:
    skill_id = str(args.get("skill_id") or args.get("name") or "").strip()
    state: dict[str, Any] = {"hasResources": False, "source": "agent"}
    if skill_id:
        state["id"] = skill_id
        state["name"] = skill_id
        state["skill_id"] = skill_id
        state["title"] = skill_id
    return state


def _started_web_search(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    state: dict[str, Any] = {"resultNumbers": 0, "results": []}
    if query:
        state["query"] = query
    return state


def _started_default(args: dict[str, Any]) -> dict[str, Any]:
    """Shallow copy of small primitive args for generic tools."""
    out: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and len(value) > 2_000:
                continue
            out[key] = value
    return out


# ── Invoked builders ────────────────────────────────────────


def _invoked_activate_skill(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Full SKILL.md body in ``content`` (plugin_state SSOT)."""
    skill_id = str(
        payload.get("skill_id") or args.get("skill_id") or args.get("name") or ""
    ).strip()
    text = payload.get("text")
    if not isinstance(text, str):
        text = ""
    title = _title_from_markdown(text) or skill_id
    state: dict[str, Any] = {
        "success": ok,
        "hasResources": False,
        "source": "agent",
        "id": skill_id,
        "name": skill_id,
        "skill_id": skill_id,
        "title": title,
    }
    if text:
        state["content"] = text
        desc = _description_from_markdown(text)
        if desc:
            state["description"] = desc
    resources = payload.get("resources")
    if isinstance(resources, (list, tuple)):
        paths = [str(item) for item in resources if str(item).strip()]
        if paths:
            state["resources"] = paths
            state["hasResources"] = True
    if error:
        state["error"] = error
    return state


def _invoked_from_payload_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Computer / search tools: prefer nested state, then top-level computer keys."""
    del args
    nested = payload.get("state")
    if isinstance(nested, dict):
        state = dict(nested)
        state["success"] = ok
        if error and not ok:
            state.setdefault("error", error)
            state.setdefault("errorDetail", error)
        return state
    if any(key in payload for key in _COMPUTER_STATE_KEYS):
        state = {
            key: payload[key]
            for key in _COMPUTER_STATE_KEYS
            if key in payload and payload[key] is not None
        }
        state["success"] = ok
        if error and not ok:
            state.setdefault("error", error)
        return state
    return {"success": ok, **({"error": error} if error and not ok else {})}


def _invoked_default(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    del args
    state: dict[str, Any] = {"success": ok}
    for key in ("output", "result", "data", "text", "content", "summary"):
        if key in payload and payload[key] is not None:
            state[key] = payload[key]
    if error and not ok:
        state["error"] = error
    return state
