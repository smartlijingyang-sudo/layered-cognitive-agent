"""CLI executeToolCall table — official apiName → local-file-shell.

Mirrors `.lobehub-upstream/apps/cli/src/tools/localSystemRuntime.ts`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from host.local_shell.file.edit import edit_local_file
from host.local_shell.file.glob_files import glob_local_files
from host.local_shell.file.grep import grep_content
from host.local_shell.file.list_files import list_local_files
from host.local_shell.file.move import move_local_files
from host.local_shell.file.read import read_local_file
from host.local_shell.file.rename import rename_local_file
from host.local_shell.file.search import search_local_files
from host.local_shell.file.write import write_local_file
from host.local_shell.shell.runner import process_manager, run_command

LocalOp = Callable[..., dict[str, Any]]

# Official names + ComputerRuntime snake_case + legacy aliases.
_ALIASES: dict[str, str] = {
    "readLocalFile": "readFile",
    "read_file": "readFile",
    "writeLocalFile": "writeFile",
    "write_file": "writeFile",
    "editLocalFile": "editFile",
    "edit_file": "editFile",
    "listLocalFiles": "listFiles",
    "list_files": "listFiles",
    "globLocalFiles": "globFiles",
    "glob_files": "globFiles",
    "searchLocalFiles": "searchFiles",
    "search_files": "searchFiles",
    "grepContent": "grepContent",
    "grep_content": "grepContent",
    "moveLocalFiles": "moveFiles",
    "move_files": "moveFiles",
    "renameLocalFile": "renameFile",
    "rename_file": "renameFile",
    "runCommand": "runCommand",
    "run_command": "runCommand",
    "run_terminal": "runCommand",
    "getCommandOutput": "getCommandOutput",
    "get_command_output": "getCommandOutput",
    "killCommand": "killCommand",
    "kill_command": "killCommand",
}

_HANDLERS: dict[str, LocalOp] = {
    "readFile": read_local_file,
    "writeFile": write_local_file,
    "editFile": edit_local_file,
    "listFiles": list_local_files,
    "globFiles": glob_local_files,
    "grepContent": grep_content,
    "searchFiles": search_local_files,
    "moveFiles": move_local_files,
    "renameFile": rename_local_file,
    "runCommand": run_command,
}

FILE_OPS = frozenset(_ALIASES) | frozenset(_HANDLERS)


def dispatch_local(
    op: str, payload: dict[str, Any], workspace: Path, *, mount: str
) -> dict[str, Any]:
    name = _ALIASES.get(op, op)
    if name == "getCommandOutput":
        return process_manager().get_output(payload)
    if name == "killCommand":
        return process_manager().kill(payload)
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"success": False, "error": f"unknown local op {op}"}
    return handler(payload, workspace, mount=mount)
