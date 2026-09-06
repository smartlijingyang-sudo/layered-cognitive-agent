"""Producer tool registry — single SSOT for convergence gates (ADR-0196)."""

from __future__ import annotations

PRODUCER_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "editFile",
        "executeCode",
        "execute_code",
        "exportFile",
        "runCommand",
        "sandbox_execute",
        "writeFile",
        "write_file_local",
        "local_runCommand",
        "local_writeFile",
        "local_editFile",
        "local_executeCode",
        "local_readFile",
    }
)


def is_producer_tool(tool_name: str | None) -> bool:
    return bool(tool_name) and tool_name in PRODUCER_TOOL_NAMES


__all__ = ["PRODUCER_TOOL_NAMES", "is_producer_tool"]
