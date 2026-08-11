"""Argument adaptation strategies — LCA args → LobeHub wire args.

Each function is a pure Strategy that transforms LCA tool arguments into
the JSON shape LobeHub's frontend expects for its plugin cards.

Grouped by tool category for discoverability:
- Skills (activate, exec, read_ref, search, import)
- Web browsing (search)
- User interaction (ask)
- Cloud sandbox (execute_code, run_command, file operations, etc.)
- Local system (write_file)
"""

from __future__ import annotations

from typing import Any

from gateway.lobehub_bridge.lobehub_adapter.json_helpers import (
    copy_fields,
    first_str,
)
from gateway.lobehub_bridge.lobehub_adapter.tool_spec import FieldMapper

# ═══════════════════════════════════════════════════════════
#  Skills
# ═══════════════════════════════════════════════════════════


def adapt_activate_skill(args: dict[str, Any]) -> dict[str, Any]:
    """activate_skill → {name: skill_id}"""
    skill_id = first_str(args, "skill_id", "name", "identifier")
    return {"name": skill_id} if skill_id else {}


def adapt_exec_script(args: dict[str, Any]) -> dict[str, Any]:
    """run_skill_script → {command, skill_id, description}"""
    out = copy_fields(args, [("command", "command"), ("skill_id", "skill_id")])
    command = out.get("command", "")
    if command:
        out["description"] = command[:200]
    return out


# Declarative: read_skill_reference → {id, path}
adapt_read_reference = FieldMapper(
    strings=[("skill_id", "id"), ("path", "path")],
)


def adapt_search_skill(args: dict[str, Any]) -> dict[str, Any]:
    """search_skill → {q, page, pageSize, searchCategories}"""
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
    """import_skill → {identifier} or {type, url}"""
    identifier = first_str(args, "identifier")
    if identifier:
        return {"identifier": identifier}
    url = first_str(args, "url")
    if not url:
        return {}
    kind = first_str(args, "kind") or "auto"
    return {"type": "zip" if kind == "zip" else "url", "url": url}


# ═══════════════════════════════════════════════════════════
#  Web browsing
# ═══════════════════════════════════════════════════════════


def adapt_web_search(args: dict[str, Any]) -> dict[str, Any]:
    """web_search → {query, searchCategories, searchTimeRange}"""
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


# ═══════════════════════════════════════════════════════════
#  User interaction
# ═══════════════════════════════════════════════════════════


def adapt_ask_user(args: dict[str, Any]) -> dict[str, Any]:
    """ask_user_question → {questions}"""
    questions = args.get("questions")
    if isinstance(questions, list) and questions:
        return {"questions": questions}
    return {}


# ═══════════════════════════════════════════════════════════
#  Cloud sandbox — execution
# ═══════════════════════════════════════════════════════════


# Declarative: execute_code → {description, language, code}
adapt_execute_code = FieldMapper(
    strings=[("description", "description"), ("language", "language"), ("code", "code")],
)


def adapt_run_command(args: dict[str, Any]) -> dict[str, Any]:
    """run_command → {command, description, background, timeout}"""
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


# ═══════════════════════════════════════════════════════════
#  Cloud sandbox — file operations
# ═══════════════════════════════════════════════════════════


def adapt_list_files(args: dict[str, Any]) -> dict[str, Any]:
    """list_files → {directoryPath}"""
    path = first_str(args, "directoryPath", "directory_path") or "/mnt/data"
    return {"directoryPath": path}


# Declarative: read_file → {path, startLine, endLine}
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
    """write_file → {path, content, createDirectories}"""
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


# Declarative: edit_file → {path, search, replace, all}
adapt_edit_file = FieldMapper(
    strings=[("path", "path"), ("search", "search"), ("replace", "replace")],
    bools=[("all", "all"), ("replace_all", "all")],
)


# Declarative: search_files → {directory, keyword, fileType, modifiedAfter, modifiedBefore}
adapt_search_files = FieldMapper(
    strings=[
        ("directory", "directory"),
        ("keyword", "keyword"),
        ("fileType", "fileType"),
        ("modifiedAfter", "modifiedAfter"),
        ("modifiedBefore", "modifiedBefore"),
    ],
)


# Declarative: move_files → {operations}
adapt_move_files = FieldMapper(lists=[("operations", "operations")])


# Declarative: grep_content → {pattern, directory, filePattern, recursive}
adapt_grep_content = FieldMapper(
    strings=[("pattern", "pattern"), ("directory", "directory"), ("filePattern", "filePattern")],
    bools=[("recursive", "recursive")],
)


# Declarative: glob_files → {pattern, directory}
adapt_glob_files = FieldMapper(strings=[("pattern", "pattern"), ("directory", "directory")])


# Declarative: get_command_output → {commandId}
adapt_command_id = FieldMapper(strings=[("commandId", "commandId"), ("command_id", "commandId")])


# Declarative: export_file → {path}
adapt_export_file = FieldMapper(strings=[("path", "path")])


# ═══════════════════════════════════════════════════════════
#  Local system
# ═══════════════════════════════════════════════════════════


def adapt_write_file_local(args: dict[str, Any]) -> dict[str, Any]:
    """Local-system writeFile (lobe-local-system plugin)."""
    out: dict[str, Any] = {}
    path = first_str(args, "path", "name", "filename", "file_name")
    if path:
        out["path"] = path
    if isinstance(args.get("content"), str):
        out["content"] = args["content"]
    return out
