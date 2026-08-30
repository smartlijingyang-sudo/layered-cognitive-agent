"""Register RenderContracts for dynamically-built sandbox, search, and interaction tools.

Importing this module populates REGISTRY with contracts for tools created via
``build_tools_from_manifest`` (cloud sandbox, local system, web search, ask user).

ADR-0102: each tool declares its own per-tool state contract that exactly
matches the keys the runtime puts in ``Observation.payload``.  Earlier
versions shared one generic contract across all 13 sandbox tools, which
silently dropped fields whose names didn't match the generic shape
(``readFile`` never had ``stdout``, ``listFiles`` never had ``exit_code``,
etc.).  Per-tool contracts close that gap; the projection reader simply
walks the declared keys.
"""

from __future__ import annotations

from lca.infrastructure.tools.contract.render import REGISTRY, FieldSpec, RenderContract
from lca.infrastructure.tools.contract.schema import COMMON

_CLOUD = "lobe-cloud-sandbox"
_LOCAL = "lobe-local-system"


# ── shared state tuple builders ──────────────────────────────────────
# Tools that produce stdout/stderr-style output share the same shape
# (runCommand, executeCode, getCommandOutput).  File ops differ and have
# their own tuples below.

_SHELL_STATE: tuple[FieldSpec, ...] = (
    COMMON["stdout"],
    COMMON["stderr"],
    COMMON["files"],
    COMMON["exit_code"],
    COMMON["execution_env"],
    COMMON["error_summary"],
    COMMON["error_kind"],
)

_SHELL_STATE_PARTIAL: tuple[FieldSpec, ...] = (*_SHELL_STATE, COMMON["partial"])


# Tool-specific state tuples — python keys match what the runtime emits
# after ``runtime_exec._normalize_guest_state``.
_LIST_FILES_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("files", "files", "json", "observation"),
    FieldSpec("total_count", "totalCount", "int", "observation", required=False),
    FieldSpec("directory_path", "directoryPath", "string", "observation", required=False),
)

_READ_FILE_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("path", "path", "string", "observation"),
    FieldSpec("content", "content", "string", "observation"),
    FieldSpec("filename", "filename", "string", "observation"),
    FieldSpec("start_line", "startLine", "int", "observation", required=False),
    FieldSpec("end_line", "endLine", "int", "observation", required=False),
    FieldSpec("total_lines", "totalLines", "int", "observation", required=False),
    FieldSpec("char_count", "charCount", "int", "observation", required=False),
    FieldSpec("file_type", "fileType", "string", "observation", required=False),
)

_WRITE_FILE_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("path", "path", "string", "observation"),
    FieldSpec("bytes_written", "bytesWritten", "int", "observation"),
)

_EDIT_FILE_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("path", "path", "string", "observation"),
    FieldSpec("replacements", "replacements", "int", "observation"),
    FieldSpec("lines_added", "linesAdded", "int", "observation", required=False),
    FieldSpec("lines_deleted", "linesDeleted", "int", "observation", required=False),
)

_SEARCH_FILES_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("results", "results", "json", "observation"),
    FieldSpec("total_count", "totalCount", "int", "observation", required=False),
)

_MOVE_FILES_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("results", "results", "json", "observation"),
    FieldSpec("success_count", "successCount", "int", "observation"),
    FieldSpec("total_count", "totalCount", "int", "observation"),
)

_GREP_CONTENT_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("matches", "matches", "json", "observation"),
    FieldSpec("total_matches", "totalMatches", "int", "observation"),
    FieldSpec("pattern", "pattern", "string", "observation", required=False),
)

_GLOB_FILES_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("files", "files", "json", "observation"),
    FieldSpec("total_count", "totalCount", "int", "observation", required=False),
    FieldSpec("pattern", "pattern", "string", "observation", required=False),
)

_GET_COMMAND_OUTPUT_STATE: tuple[FieldSpec, ...] = (
    COMMON["stdout"],
    COMMON["stderr"],
    COMMON["files"],
    COMMON["exit_code"],
    FieldSpec("command_id", "commandId", "string", "observation"),
    FieldSpec("running", "running", "bool", "observation", required=False),
    FieldSpec("partial", "partial", "bool", "observation", required=False),
    COMMON["error_summary"],
    COMMON["error_kind"],
)

_KILL_COMMAND_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("command_id", "commandId", "string", "observation"),
    FieldSpec("killed", "killed", "bool", "observation"),
)

_EXPORT_FILE_STATE: tuple[FieldSpec, ...] = (
    FieldSpec("path", "path", "string", "observation"),
    FieldSpec("filename", "filename", "string", "observation"),
    FieldSpec("mime_type", "mimeType", "string", "observation"),
    FieldSpec("size", "size", "int", "observation"),
    FieldSpec("download_url", "downloadUrl", "string", "observation", required=False),
)


# ── cloud sandbox API contracts ──────────────────────────────────────

_CLOUD_CONTRACTS: dict[str, RenderContract] = {
    "executeCode": RenderContract(
        tool_name="executeCode",
        identifier=_CLOUD,
        api_name="executeCode",
        args=(COMMON["description"], COMMON["language"], COMMON["code"]),
        state=_SHELL_STATE,
    ),
    "runCommand": RenderContract(
        tool_name="runCommand",
        identifier=_CLOUD,
        api_name="runCommand",
        args=(
            COMMON["description"],
            COMMON["command"],
            COMMON["background"],
            COMMON["timeout"],
        ),
        state=_SHELL_STATE,
    ),
    "listFiles": RenderContract(
        tool_name="listFiles",
        identifier=_CLOUD,
        api_name="listFiles",
        args=(COMMON["directory_path"],),
        state=_LIST_FILES_STATE,
    ),
    "readFile": RenderContract(
        tool_name="readFile",
        identifier=_CLOUD,
        api_name="readFile",
        args=(COMMON["path"],),
        state=_READ_FILE_STATE,
    ),
    "writeFile": RenderContract(
        tool_name="writeFile",
        identifier=_CLOUD,
        api_name="writeFile",
        args=(
            COMMON["path"],
            COMMON["content_arg"],
            COMMON["create_directories"],
        ),
        state=_WRITE_FILE_STATE,
    ),
    "editFile": RenderContract(
        tool_name="editFile",
        identifier=_CLOUD,
        api_name="editFile",
        args=(
            COMMON["path"],
            COMMON["search"],
            COMMON["replace"],
            COMMON["replace_all"],
        ),
        state=_EDIT_FILE_STATE,
    ),
    "searchFiles": RenderContract(
        tool_name="searchFiles",
        identifier=_CLOUD,
        api_name="searchFiles",
        args=(COMMON["directory"], COMMON["keyword"], COMMON["file_type"]),
        state=_SEARCH_FILES_STATE,
    ),
    "moveFiles": RenderContract(
        tool_name="moveFiles",
        identifier=_CLOUD,
        api_name="moveFiles",
        args=(COMMON["operations"],),
        state=_MOVE_FILES_STATE,
    ),
    "grepContent": RenderContract(
        tool_name="grepContent",
        identifier=_CLOUD,
        api_name="grepContent",
        args=(
            COMMON["pattern"],
            COMMON["directory"],
            COMMON["file_pattern"],
            COMMON["recursive"],
        ),
        state=_GREP_CONTENT_STATE,
    ),
    "globFiles": RenderContract(
        tool_name="globFiles",
        identifier=_CLOUD,
        api_name="globFiles",
        args=(COMMON["pattern"], COMMON["directory"]),
        state=_GLOB_FILES_STATE,
    ),
    "getCommandOutput": RenderContract(
        tool_name="getCommandOutput",
        identifier=_CLOUD,
        api_name="getCommandOutput",
        args=(COMMON["command_id"],),
        state=_GET_COMMAND_OUTPUT_STATE,
    ),
    "killCommand": RenderContract(
        tool_name="killCommand",
        identifier=_CLOUD,
        api_name="killCommand",
        args=(COMMON["command_id"],),
        state=_KILL_COMMAND_STATE,
    ),
    "exportFile": RenderContract(
        tool_name="exportFile",
        identifier=_CLOUD,
        api_name="exportFile",
        args=(COMMON["path"],),
        state=_EXPORT_FILE_STATE,
    ),
}


def _local_contract(cloud_contract: RenderContract) -> RenderContract:
    """Build a local-system sibling for a cloud sandbox contract.

    The local tools share the same wire shape (per-tool state), so we
    reuse the cloud contract's args/state.  Only ``identifier`` and
    ``tool_name`` change.
    """
    return RenderContract(
        tool_name=f"local_{cloud_contract.api_name}",
        identifier=_LOCAL,
        api_name=cloud_contract.api_name,
        args=cloud_contract.args,
        state=cloud_contract.state,
    )


# ── local system contracts (same APIs, no exportFile) ────────────────

_LOCAL_CONTRACTS: dict[str, RenderContract] = {
    f"local_{name}": _local_contract(c)
    for name, c in _CLOUD_CONTRACTS.items()
    if name != "exportFile"
}


# ── web search ───────────────────────────────────────────────────────

_WEB_CONTRACTS: dict[str, RenderContract] = {
    "search": RenderContract(
        tool_name="search",
        identifier="lobe-web-browsing",
        api_name="search",
        args=(COMMON["query"], COMMON["topic"], COMMON["time_range"]),
        state=(),
    ),
}


# ── user interaction ─────────────────────────────────────────────────

_USER_CONTRACTS: dict[str, RenderContract] = {
    "askUserQuestion": RenderContract(
        tool_name="askUserQuestion",
        identifier="lobe-user-interaction",
        api_name="askUserQuestion",
        args=(COMMON["questions"],),
        state=(),
    ),
}


# ── populate registry ────────────────────────────────────────────────

_ALL: dict[str, RenderContract] = {
    **_CLOUD_CONTRACTS,
    **_LOCAL_CONTRACTS,
    **_WEB_CONTRACTS,
    **_USER_CONTRACTS,
}

for _name, _c in _ALL.items():
    if _name not in REGISTRY:
        REGISTRY[_name] = _c
