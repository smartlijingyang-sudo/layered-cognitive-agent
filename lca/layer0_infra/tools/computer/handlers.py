"""Computer tool operation handlers — map args to sandbox adapter calls."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.sandbox import DEFAULT_SANDBOX_TIMEOUT_S
from lca.layer0_infra.computer.op_result import ComputerOpResult
from lca.layer0_infra.computer.ops import SandboxExecOps


def _str_arg(args: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return default


async def _op_execute_code(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    return await rt.execute_code(
        code=_str_arg(args, "code"),
        language=_str_arg(args, "language", default="python"),
        description=_str_arg(args, "description"),
        timeout_s=int(args.get("timeout_s", DEFAULT_SANDBOX_TIMEOUT_S)),
    )


def _resolve_command_timeout_s(args: dict[str, Any]) -> int:
    """Normalize timeout from tool args.

    LobeHub cloud-sandbox uses ``timeout`` in milliseconds when > 300;
    values <= 300 are treated as seconds (agent often passes 30/60 meaning seconds).
    ``timeout_s`` is always seconds.
    """
    explicit_s = args.get("timeout_s")
    if isinstance(explicit_s, (int, float)) and explicit_s > 0:
        return max(1, int(explicit_s))

    raw = args.get("timeout")
    if isinstance(raw, (int, float)) and raw > 0:
        value = int(raw)
        if value <= 300:
            return max(1, value)
        return max(1, value // 1000)
    return DEFAULT_SANDBOX_TIMEOUT_S


async def _op_run_command(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    timeout_s = _resolve_command_timeout_s(args)
    return await rt.run_command(
        command=_str_arg(args, "command"),
        description=_str_arg(args, "description"),
        background=bool(args.get("background", False)),
        timeout_s=timeout_s,
    )


async def _op_list_files(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    return await rt.list_files(
        directory_path=_str_arg(args, "directoryPath", "directory_path")
    )


async def _op_read_file(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    start_line = args.get("startLine", args.get("start_line"))
    end_line = args.get("endLine", args.get("end_line"))
    return await rt.read_file(
        path=_str_arg(args, "path"),
        start_line=int(start_line) if isinstance(start_line, (int, float)) else None,
        end_line=int(end_line) if isinstance(end_line, (int, float)) else None,
    )


async def _op_write_file(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    content = args.get("content")
    return await rt.write_file(
        path=_str_arg(args, "path"),
        content=str(content) if content is not None else "",
        create_directories=bool(
            args.get("createDirectories", args.get("create_directories", True))
        ),
    )


async def _op_edit_file(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    return await rt.edit_file(
        path=_str_arg(args, "path"),
        search=_str_arg(args, "search"),
        replace=_str_arg(args, "replace"),
        replace_all=bool(args.get("all", args.get("replace_all", False))),
    )


async def _op_search_files(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    return await rt.search_files(
        directory=_str_arg(args, "directory"),
        keyword=_str_arg(args, "keyword"),
        file_type=_str_arg(args, "fileType", "file_type"),
        modified_after=_str_arg(args, "modifiedAfter", "modified_after"),
        modified_before=_str_arg(args, "modifiedBefore", "modified_before"),
    )


async def _op_move_files(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    ops = args.get("operations")
    operations: list[dict[str, str]] = []
    if isinstance(ops, list):
        for item in ops:
            if isinstance(item, dict):
                operations.append(
                    {
                        "source": str(item.get("source", "")),
                        "destination": str(item.get("destination", "")),
                    }
                )
    return await rt.move_files(operations=operations)


async def _op_grep_content(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    return await rt.grep_content(
        pattern=_str_arg(args, "pattern"),
        directory=_str_arg(args, "directory"),
        file_pattern=_str_arg(args, "filePattern", "file_pattern"),
        recursive=bool(args.get("recursive", True)),
    )


async def _op_glob_files(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    return await rt.glob_files(
        pattern=_str_arg(args, "pattern"),
        directory=_str_arg(args, "directory"),
    )


async def _op_get_command_output(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    return await rt.get_command_output(command_id=_str_arg(args, "commandId", "command_id"))


async def _op_kill_command(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    return await rt.kill_command(command_id=_str_arg(args, "commandId", "command_id"))


async def _op_export_file(rt: SandboxExecOps, args: dict[str, Any]) -> ComputerOpResult:
    return await rt.export_file(path=_str_arg(args, "path"))
