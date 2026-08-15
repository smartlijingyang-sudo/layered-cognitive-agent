"""API name enum — camelCase to match LobeHub wire convention."""

from __future__ import annotations

from enum import Enum


class ApiName(str, Enum):
    LIST_FILES = "listFiles"
    READ_FILE = "readFile"
    WRITE_FILE = "writeFile"
    EDIT_FILE = "editFile"
    SEARCH_FILES = "searchFiles"
    MOVE_FILES = "moveFiles"
    GREP_CONTENT = "grepContent"
    GLOB_FILES = "globFiles"
    RUN_COMMAND = "runCommand"
    GET_COMMAND_OUTPUT = "getCommandOutput"
    KILL_COMMAND = "killCommand"
    EXECUTE_CODE = "executeCode"
    EXPORT_FILE = "exportFile"

    def __str__(self) -> str:
        return self.value


# exportFile is sandbox-only (file download mechanism is specific to sandbox).
# executeCode is now available on both machine and sandbox backends.
SANDBOX_ONLY_APIS: frozenset[ApiName] = frozenset({ApiName.EXPORT_FILE})

COMPUTER_APIS: frozenset[ApiName] = frozenset(ApiName)

MACHINE_APIS: frozenset[ApiName] = COMPUTER_APIS - SANDBOX_ONLY_APIS

CLOUD_SANDBOX_APIS: frozenset[ApiName] = COMPUTER_APIS
