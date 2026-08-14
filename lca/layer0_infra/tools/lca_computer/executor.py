"""lca-computer executor — routes apiName calls to ComputerOps methods."""

from __future__ import annotations

from typing import Any

from lca.layer0_infra.computer.op_result import ComputerOpResult
from lca.layer0_infra.computer.ops import ComputerOps
from lca.layer0_infra.tools.lca_computer.types import ApiName


def _str_arg(args: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return default


def _resolve_timeout_s(args: dict[str, Any], default: int = 60) -> int:
    explicit_s = args.get("timeout_s")
    if isinstance(explicit_s, (int, float)) and explicit_s > 0:
        return max(1, int(explicit_s))
    raw = args.get("timeout")
    if isinstance(raw, (int, float)) and raw > 0:
        value = int(raw)
        if value <= 300:
            return max(1, value)
        return max(1, value // 1000)
    return default


class LcaComputerExecutor:
    """Routes tool calls to a ComputerOps backend."""

    def __init__(self, ops: ComputerOps) -> None:
        self._ops = ops

    async def invoke(self, api_name: str, params: dict[str, Any]) -> ComputerOpResult:
        dispatch = _DISPATCH.get(api_name)
        if dispatch is None:
            return ComputerOpResult(
                success=False,
                content="",
                state={},
                error=f"unknown apiName: {api_name}",
            )
        return await dispatch(self, params)

    async def list_files(self, params: dict[str, Any]) -> ComputerOpResult:
        return await self._ops.list_files(
            directory_path=_str_arg(params, "directoryPath", "directory_path"),
        )

    async def read_file(self, params: dict[str, Any]) -> ComputerOpResult:
        start_line = params.get("startLine", params.get("start_line"))
        end_line = params.get("endLine", params.get("end_line"))
        return await self._ops.read_file(
            path=_str_arg(params, "path"),
            start_line=int(start_line) if isinstance(start_line, (int, float)) else None,
            end_line=int(end_line) if isinstance(end_line, (int, float)) else None,
        )

    async def write_file(self, params: dict[str, Any]) -> ComputerOpResult:
        content = params.get("content")
        return await self._ops.write_file(
            path=_str_arg(params, "path"),
            content=str(content) if content is not None else "",
            create_directories=bool(
                params.get("createDirectories", params.get("create_directories", True))
            ),
        )

    async def edit_file(self, params: dict[str, Any]) -> ComputerOpResult:
        return await self._ops.edit_file(
            path=_str_arg(params, "path"),
            search=_str_arg(params, "search"),
            replace=_str_arg(params, "replace"),
            replace_all=bool(params.get("all", params.get("replace_all", False))),
        )

    async def search_files(self, params: dict[str, Any]) -> ComputerOpResult:
        return await self._ops.search_files(
            directory=_str_arg(params, "directory"),
            keyword=_str_arg(params, "keyword", "file_type"),
            file_type=_str_arg(params, "fileType", "file_type"),
        )

    async def move_files(self, params: dict[str, Any]) -> ComputerOpResult:
        ops_raw = params.get("operations")
        operations: list[dict[str, str]] = []
        if isinstance(ops_raw, list):
            for item in ops_raw:
                if isinstance(item, dict):
                    operations.append(
                        {
                            "source": str(item.get("source", "")),
                            "destination": str(item.get("destination", "")),
                        }
                    )
        return await self._ops.move_files(operations=operations)

    async def grep_content(self, params: dict[str, Any]) -> ComputerOpResult:
        return await self._ops.grep_content(
            pattern=_str_arg(params, "pattern"),
            directory=_str_arg(params, "directory"),
            file_pattern=_str_arg(params, "filePattern", "file_pattern"),
            recursive=bool(params.get("recursive", True)),
        )

    async def glob_files(self, params: dict[str, Any]) -> ComputerOpResult:
        return await self._ops.glob_files(
            pattern=_str_arg(params, "pattern"),
            directory=_str_arg(params, "directory"),
        )

    async def run_command(self, params: dict[str, Any]) -> ComputerOpResult:
        timeout_s = _resolve_timeout_s(params)
        return await self._ops.run_command(
            command=_str_arg(params, "command"),
            description=_str_arg(params, "description"),
            background=bool(params.get("background", False)),
            timeout_s=timeout_s,
        )

    async def get_command_output(self, params: dict[str, Any]) -> ComputerOpResult:
        return await self._ops.get_command_output(
            command_id=_str_arg(params, "commandId", "command_id"),
        )

    async def kill_command(self, params: dict[str, Any]) -> ComputerOpResult:
        return await self._ops.kill_command(
            command_id=_str_arg(params, "commandId", "command_id"),
        )


class LcaSandboxExecutor(LcaComputerExecutor):
    """Extends computer executor with sandbox-only APIs (executeCode, exportFile)."""

    def __init__(self, ops: ComputerOps) -> None:
        super().__init__(ops)
        self._sandbox_ops = ops

    async def invoke(self, api_name: str, params: dict[str, Any]) -> ComputerOpResult:
        if api_name == ApiName.EXECUTE_CODE:
            return await self.execute_code(params)
        if api_name == ApiName.EXPORT_FILE:
            return await self.export_file(params)
        return await super().invoke(api_name, params)

    async def execute_code(self, params: dict[str, Any]) -> ComputerOpResult:
        from lca.contracts.models.core.sandbox import DEFAULT_SANDBOX_TIMEOUT_S

        return await self._sandbox_ops.execute_code(
            code=_str_arg(params, "code"),
            language=_str_arg(params, "language", default="python"),
            description=_str_arg(params, "description"),
            timeout_s=int(params.get("timeout_s", DEFAULT_SANDBOX_TIMEOUT_S)),
        )

    async def export_file(self, params: dict[str, Any]) -> ComputerOpResult:
        return await self._sandbox_ops.export_file(
            path=_str_arg(params, "path"),
        )


_DISPATCH: dict[str, Any] = {
    ApiName.LIST_FILES: LcaComputerExecutor.list_files,
    ApiName.READ_FILE: LcaComputerExecutor.read_file,
    ApiName.WRITE_FILE: LcaComputerExecutor.write_file,
    ApiName.EDIT_FILE: LcaComputerExecutor.edit_file,
    ApiName.SEARCH_FILES: LcaComputerExecutor.search_files,
    ApiName.MOVE_FILES: LcaComputerExecutor.move_files,
    ApiName.GREP_CONTENT: LcaComputerExecutor.grep_content,
    ApiName.GLOB_FILES: LcaComputerExecutor.glob_files,
    ApiName.RUN_COMMAND: LcaComputerExecutor.run_command,
    ApiName.GET_COMMAND_OUTPUT: LcaComputerExecutor.get_command_output,
    ApiName.KILL_COMMAND: LcaComputerExecutor.kill_command,
}
