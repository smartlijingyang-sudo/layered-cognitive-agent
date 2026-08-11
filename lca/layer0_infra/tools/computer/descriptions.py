"""LobeHub cloud-sandbox API descriptions — parity with ``manifest.ts``."""

from __future__ import annotations

from lca.layer0_infra.sandbox.bootstrap import sandbox_output_path

_OUTPUTS = sandbox_output_path()
_PACKAGES = (
    "numpy, pandas, scipy, matplotlib, plotly, openpyxl, python-docx, reportlab, pypdf, Pillow"
)

EXECUTE_CODE_DESCRIPTION = (
    "Execute code in the isolated cloud sandbox. Workspace: /mnt/data. "
    f"Write deliverables to {_OUTPUTS}/ (auto-collected after run). "
    f"Pre-installed: {_PACKAGES}. "
    "Parameters: description, language (python/javascript/typescript), code."
)

RUN_COMMAND_DESCRIPTION = (
    "Execute a shell command in the sandbox with timeout control. "
    "Default shell is /bin/sh; use bash -c for bash features. "
    "Supports background execution (background: true → commandId). "
    f"Deliverables written under {_OUTPUTS}/ are auto-collected after the "
    "command (same as execute_code) — no separate export_file required for "
    "new/changed files. Background commands do not auto-harvest until "
    "completion is polled. "
    "Parameters: description, command, background, timeout."
)

LIST_FILES_DESCRIPTION = (
    "List files and directories at directoryPath (default /mnt/data). "
    "Use before assuming file paths."
)

READ_FILE_DESCRIPTION = (
    "Read a sandbox file. Parameters: path, optional startLine/endLine (1-based)."
)

WRITE_FILE_DESCRIPTION = (
    "Write content to a file. Set createDirectories: true to create parent dirs. "
    f"For user deliverables prefer {_OUTPUTS}/. Parameters: path, content, createDirectories."
)

EDIT_FILE_DESCRIPTION = (
    "Exact string replacement in a file. Read the file first. "
    "Parameters: path, search, replace, all."
)

SEARCH_FILES_DESCRIPTION = (
    "Search filenames under directory. Parameters: directory, keyword, fileType."
)

MOVE_FILES_DESCRIPTION = "Move or rename files. Parameters: operations[{source, destination}]."

GREP_CONTENT_DESCRIPTION = (
    "Regex search in file contents. Parameters: pattern, directory, filePattern, recursive."
)

GLOB_FILES_DESCRIPTION = "Glob match files. Parameters: pattern, directory."

GET_COMMAND_OUTPUT_DESCRIPTION = "Poll output from a background run_command. Parameters: commandId."

KILL_COMMAND_DESCRIPTION = "Kill a background command. Parameters: commandId."

EXPORT_FILE_DESCRIPTION = (
    "Export a sandbox file for user download (call after creating deliverables). "
    f"Works for binary files (PDF, images). Prefer paths under {_OUTPUTS}/. "
    "Parameters: path."
)

DESCRIPTIONS: dict[str, str] = {
    "execute_code": EXECUTE_CODE_DESCRIPTION,
    "run_command": RUN_COMMAND_DESCRIPTION,
    "list_files": LIST_FILES_DESCRIPTION,
    "read_file": READ_FILE_DESCRIPTION,
    "write_file": WRITE_FILE_DESCRIPTION,
    "edit_file": EDIT_FILE_DESCRIPTION,
    "search_files": SEARCH_FILES_DESCRIPTION,
    "move_files": MOVE_FILES_DESCRIPTION,
    "grep_content": GREP_CONTENT_DESCRIPTION,
    "glob_files": GLOB_FILES_DESCRIPTION,
    "get_command_output": GET_COMMAND_OUTPUT_DESCRIPTION,
    "kill_command": KILL_COMMAND_DESCRIPTION,
    "export_file": EXPORT_FILE_DESCRIPTION,
}
