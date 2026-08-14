"""Python port of @lobechat/local-file-shell.

Call chain (official):
  Agent tool_call → executeToolCall(apiName) → runLocalSystemTool
    → LocalSystemExecutionRuntime → readLocalFile / runCommand / …
  CLI tools/file.ts and tools/shell.ts are thin re-exports of this package.

Here: ComputerRuntime.computer_op → HostSandbox.exec_call → handle_exec
  → dispatch_local → the same functions.
"""

from host.local_shell.dispatch import FILE_OPS, dispatch_local
from host.local_shell.file import (
    edit_local_file,
    expand_tilde,
    glob_local_files,
    grep_content,
    list_local_files,
    move_local_files,
    read_local_file,
    rename_local_file,
    resolve_against_cwd,
    search_local_files,
    write_local_file,
)
from host.local_shell.shell import ShellProcessManager, run_command

__all__ = [
    "FILE_OPS",
    "ShellProcessManager",
    "dispatch_local",
    "edit_local_file",
    "expand_tilde",
    "glob_local_files",
    "grep_content",
    "list_local_files",
    "move_local_files",
    "read_local_file",
    "rename_local_file",
    "resolve_against_cwd",
    "run_command",
    "search_local_files",
    "write_local_file",
]
