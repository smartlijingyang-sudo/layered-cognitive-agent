"""Backward-compatible alias for ``sandbox_execute`` (ADR-0050)."""

from __future__ import annotations

from typing import Any, ClassVar

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SANDBOX_PREINSTALLED_PYTHON_PACKAGES,
)
from lca.contracts.protocols import Sandbox, Tool
from lca.layer0_infra.file_store import FileStore, LocalFileStore
from lca.layer0_infra.tools.sandbox_runtime_tools import SandboxExecuteTool

SANDBOX_TOOL_NAME = "run_sandbox_code"


class SandboxCodeTool(Tool):
    """Alias of ``sandbox_execute`` — kept for wire / UI compatibility."""

    name = SANDBOX_TOOL_NAME
    description = (
        "（兼容别名 → sandbox_execute）在 run 绑定沙箱中执行 Python。"
        "附件已挂载 /mnt/data/<文件名>；产出 /mnt/data/outputs/。\n"
        "预装包: " + ", ".join(SANDBOX_PREINSTALLED_PYTHON_PACKAGES) + "\n"
        "分析前先 sandbox_inspect；字符串操作前 dropna().astype(str)。"
    )
    parameters: ClassVar[dict[str, Any]] = SandboxExecuteTool.parameters
    is_idempotent = False
    default_timeout_s = DEFAULT_SANDBOX_TIMEOUT_S

    def __init__(
        self,
        sandbox: Sandbox,
        store: FileStore | LocalFileStore | None = None,
    ) -> None:
        self._delegate = SandboxExecuteTool(sandbox=sandbox, store=store)

    def validate(self, args: dict[str, Any]) -> str | None:
        return self._delegate.validate(args)

    async def execute(self, args: dict[str, Any]) -> Observation:
        return await self._delegate.execute(args)
