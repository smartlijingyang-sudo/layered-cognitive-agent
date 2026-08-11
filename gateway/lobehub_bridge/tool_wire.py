"""LCA tool names → LobeHub builtin wire format (identifier____apiName).

Registry + strategy transforms keep ``journal_openai_projector`` free of
per-tool branching. Unmapped tools fall back to raw LCA names.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PLUGIN_SCHEMA_SEPARATOR = "____"

LOBE_SKILLS_ID = "lobe-skills"
LOBE_SKILL_STORE_ID = "lobe-skill-store"
LOBE_LOCAL_SYSTEM_ID = "lobe-local-system"
LOBE_WEB_BROWSING_ID = "lobe-web-browsing"
LOBE_USER_INTERACTION_ID = "lobe-user-interaction"

SKILLS_API_ACTIVATE = "activateSkill"
SKILLS_API_EXEC = "execScript"
SKILLS_API_READ_REF = "readReference"
SKILL_STORE_API_SEARCH = "searchSkill"
SKILL_STORE_API_IMPORT = "importSkill"
SKILL_STORE_API_IMPORT_MARKET = "importFromMarket"
LOCAL_SYSTEM_API_WRITE = "writeFile"
WEB_BROWSING_API_SEARCH = "search"
USER_INTERACTION_API_ASK = "askUserQuestion"

# Skill markdown can exceed generic tool preview cap — LobeHub renders full content.
_SKILL_CONTENT_MAX_LEN = 32_000

ArgsTransform = Callable[[dict[str, Any]], dict[str, Any]]
StateBuilder = Callable[[dict[str, Any], dict[str, Any], bool, str], dict[str, Any]]


def wire_tool_name(identifier: str, api_name: str) -> str:
    """OpenAI function.name wire form expected by LobeHub ``ToolNameResolver``."""
    return f"{identifier}{PLUGIN_SCHEMA_SEPARATOR}{api_name}"


def split_wire_name(wire_name: str) -> tuple[str, str]:
    """Split ``identifier____apiName`` back into LobeHub plugin coordinates."""
    if PLUGIN_SCHEMA_SEPARATOR in wire_name:
        identifier, api_name = wire_name.split(PLUGIN_SCHEMA_SEPARATOR, 1)
        return identifier, api_name
    return wire_name, ""


def _parse_args_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_str(args: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _transform_web_search(args: dict[str, Any]) -> dict[str, Any]:
    query = _first_str(args, "query", "q")
    out: dict[str, Any] = {}
    if query:
        out["query"] = query
    topic = _first_str(args, "topic")
    if topic:
        out["searchCategories"] = [topic]
    time_range = _first_str(args, "time_range", "searchTimeRange")
    if time_range:
        out["searchTimeRange"] = time_range
    return out


def _transform_activate_skill(args: dict[str, Any]) -> dict[str, Any]:
    skill_id = _first_str(args, "skill_id", "name", "identifier")
    return {"name": skill_id} if skill_id else {}


def _transform_exec_script(args: dict[str, Any]) -> dict[str, Any]:
    command = _first_str(args, "command")
    out: dict[str, Any] = {}
    if command:
        out["command"] = command
        out["description"] = command[:200]
    skill_id = _first_str(args, "skill_id")
    if skill_id:
        out["skill_id"] = skill_id
    return out


def _transform_read_reference(args: dict[str, Any]) -> dict[str, Any]:
    skill_id = _first_str(args, "skill_id", "id")
    path = _first_str(args, "path")
    out: dict[str, Any] = {}
    if skill_id:
        out["id"] = skill_id
    if path:
        out["path"] = path
    return out


def _transform_search_skill(args: dict[str, Any]) -> dict[str, Any]:
    query = _first_str(args, "query", "q")
    out: dict[str, Any] = {}
    if query:
        out["q"] = query
    page = args.get("page")
    if isinstance(page, int):
        out["page"] = page
    page_size = args.get("page_size", args.get("pageSize"))
    if isinstance(page_size, int):
        out["pageSize"] = page_size
    return out


def _transform_import_skill(args: dict[str, Any]) -> dict[str, Any]:
    identifier = _first_str(args, "identifier")
    if identifier:
        return {"identifier": identifier}
    url = _first_str(args, "url")
    if not url:
        return {}
    kind = _first_str(args, "kind") or "auto"
    import_type = "zip" if kind == "zip" else "url"
    return {"type": import_type, "url": url}


def _transform_write_file(args: dict[str, Any]) -> dict[str, Any]:
    path = _first_str(args, "path", "name", "filename", "file_name")
    content = args.get("content")
    out: dict[str, Any] = {}
    if path:
        out["path"] = path
    if isinstance(content, str):
        out["content"] = content
    return out


def _state_activate_skill(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    name = _first_str(args, "name", "skill_id") or _first_str(payload, "skill_id")
    skill_id = _first_str(payload, "skill_id") or name
    title = name or skill_id
    text = payload.get("text")
    description = ""
    if isinstance(text, str) and text.strip():
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped[:200]
                break
            if stripped.startswith("# "):
                title = stripped[2:].strip() or title
    return {
        "hasResources": True,
        "id": skill_id,
        "name": name or skill_id,
        "title": title,
        **({"description": description} if description else {}),
        "source": "agent",
        "success": ok,
        **({"error": error} if not ok and error else {}),
    }


def _state_web_search(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    nested = payload.get("state")
    if isinstance(nested, dict):
        state = dict(nested)
        state["success"] = ok
        if not ok and error:
            state["errorDetail"] = error
        return state
    query = _first_str(args, "query") or _first_str(payload, "query")
    return {
        "query": query,
        "resultNumbers": 0,
        "results": [],
        "success": ok,
        **({"errorDetail": error} if not ok and error else {}),
    }


def _state_exec_script(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    command = _first_str(args, "command") or _first_str(payload, "command")
    exit_code = payload.get("exit_code")
    state: dict[str, Any] = {
        "command": command,
        "executionEnv": "sandbox",
        "success": ok,
    }
    if isinstance(exit_code, int):
        state["exitCode"] = exit_code
    elif ok:
        state["exitCode"] = 0
    if not ok and error:
        state["error"] = error
    stdout = payload.get("stdout")
    stderr = payload.get("stderr")
    if isinstance(stdout, str) and stdout:
        state["stdout"] = stdout
    if isinstance(stderr, str) and stderr:
        state["stderr"] = stderr
    return state


def _state_read_reference(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    path = _first_str(args, "path") or _first_str(payload, "path")
    text = payload.get("text")
    size = len(text) if isinstance(text, str) else 0
    state: dict[str, Any] = {
        "encoding": "utf8",
        "fileType": "text",
        "path": path,
        "size": size,
        "success": ok,
    }
    if not ok and error:
        state["error"] = error
    return state


def _state_search_skill(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    state: dict[str, Any] = {"success": ok}
    if not ok and error:
        state["error"] = error
    query = _first_str(args, "q", "query")
    if query:
        state["query"] = query
    return state


def _state_import_skill(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    skill_id = _first_str(payload, "skill_id")
    name = _first_str(payload, "name") or skill_id
    state: dict[str, Any] = {
        "skillId": skill_id,
        "name": name,
        "status": "created" if ok else "unchanged",
        "success": ok,
    }
    if not ok and error:
        state["error"] = error
    return state


def _state_write_file(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    path = _first_str(args, "path") or _first_str(payload, "name", "path")
    state: dict[str, Any] = {"path": path, "success": ok}
    if not ok and error:
        state["error"] = error
    url = _first_str(payload, "url")
    if url:
        state["url"] = url
    size = payload.get("sizeBytes", payload.get("size_bytes"))
    if isinstance(size, int):
        state["size"] = size
    return state


def _transform_ask_user(args: dict[str, Any]) -> dict[str, Any]:
    questions = args.get("questions")
    if isinstance(questions, list) and questions:
        return {"questions": questions}
    return {}


def _state_ask_user(
    arguments: dict[str, Any],
    result: dict[str, Any],
    ok: bool,
    error: str,
) -> dict[str, Any]:
    state: dict[str, Any] = {"success": ok}
    questions = arguments.get("questions")
    if isinstance(questions, list):
        state["questions"] = questions
    if not ok and error:
        state["error"] = error
    return state


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


def _import_spec(args: dict[str, Any]) -> ToolWireSpec:
    if _first_str(args, "identifier"):
        return ToolWireSpec(
            lca_name="import_skill",
            identifier=LOBE_SKILL_STORE_ID,
            api_name=SKILL_STORE_API_IMPORT_MARKET,
            transform_args=_transform_import_skill,
            build_state=_state_import_skill,
        )
    return ToolWireSpec(
        lca_name="import_skill",
        identifier=LOBE_SKILL_STORE_ID,
        api_name=SKILL_STORE_API_IMPORT,
        transform_args=_transform_import_skill,
        build_state=_state_import_skill,
    )


_TOOL_REGISTRY: dict[str, ToolWireSpec | Callable[[dict[str, Any]], ToolWireSpec]] = {
    "activate_skill": ToolWireSpec(
        lca_name="activate_skill",
        identifier=LOBE_SKILLS_ID,
        api_name=SKILLS_API_ACTIVATE,
        transform_args=_transform_activate_skill,
        build_state=_state_activate_skill,
    ),
    "run_skill_script": ToolWireSpec(
        lca_name="run_skill_script",
        identifier=LOBE_SKILLS_ID,
        api_name=SKILLS_API_EXEC,
        transform_args=_transform_exec_script,
        build_state=_state_exec_script,
    ),
    "read_skill_reference": ToolWireSpec(
        lca_name="read_skill_reference",
        identifier=LOBE_SKILLS_ID,
        api_name=SKILLS_API_READ_REF,
        transform_args=_transform_read_reference,
        build_state=_state_read_reference,
    ),
    "search_skill": ToolWireSpec(
        lca_name="search_skill",
        identifier=LOBE_SKILL_STORE_ID,
        api_name=SKILL_STORE_API_SEARCH,
        transform_args=_transform_search_skill,
        build_state=_state_search_skill,
    ),
    "import_skill": _import_spec,
    "web_search": ToolWireSpec(
        lca_name="web_search",
        identifier=LOBE_WEB_BROWSING_ID,
        api_name=WEB_BROWSING_API_SEARCH,
        transform_args=_transform_web_search,
        build_state=_state_web_search,
    ),
    "ask_user_question": ToolWireSpec(
        lca_name="ask_user_question",
        identifier=LOBE_USER_INTERACTION_ID,
        api_name=USER_INTERACTION_API_ASK,
        transform_args=_transform_ask_user,
        build_state=_state_ask_user,
    ),
}


def _merged_registry() -> dict[str, ToolWireSpec | Callable[[dict[str, Any]], ToolWireSpec]]:
    from gateway.lobehub_bridge.cloud_sandbox_wire import merge_cloud_sandbox_wire

    registry = dict(_TOOL_REGISTRY)
    merge_cloud_sandbox_wire(registry)
    return registry


def resolve_tool_wire(tool_name: str, arguments_preview: str = "") -> ToolWireSpec | None:
    entry = _merged_registry().get(tool_name)
    if entry is None:
        return None
    if callable(entry):
        return entry(_parse_args_json(arguments_preview))
    return entry


def transform_tool_arguments(spec: ToolWireSpec, arguments_preview: str) -> str:
    args = spec.transform_args(_parse_args_json(arguments_preview))
    return json.dumps(args, ensure_ascii=False)


def build_tool_plugin_state(
    spec: ToolWireSpec,
    *,
    arguments_preview: str,
    result_preview: str,
    ok: bool,
    error: str,
) -> dict[str, Any]:
    args = spec.transform_args(_parse_args_json(arguments_preview))
    payload = _parse_args_json(result_preview)
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
        return _SKILL_CONTENT_MAX_LEN
    return 500


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
