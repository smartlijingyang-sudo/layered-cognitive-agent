"""lca-sandbox — sandbox-only APIs (executeCode, exportFile).

Standalone manifest + executor on top of lca-computer infrastructure.
Aligns with LobeHub ``builtin-tool-cloud-sandbox``.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, cast

from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta
from lca.layer0_infra.tools.lca_computer.apis import execute_code as _execute_code
from lca.layer0_infra.tools.lca_computer.apis import export_file as _export_file
from lca.layer0_infra.tools.lca_computer.executor import LcaSandboxExecutor
from lca.layer0_infra.tools.lca_computer.types import ApiName

IDENTIFIER = "lobe-cloud-sandbox"

SYSTEM_ROLE = (
    "你可以使用云端沙箱执行代码。"
    "用 executeCode 执行 Python/JavaScript/TypeScript 代码。"
    "用 exportFile 将生成的文件分享给用户。"
)

_MANIFEST_META = ToolMeta(
    avatar="📦",
    title="Cloud Sandbox",
    description="在云端沙箱中执行代码并导出文件",
)

_SANDBOX_APIS: tuple[ToolApi, ...] = (
    ToolApi(
        name=ApiName.EXECUTE_CODE,
        description=_execute_code.DESCRIPTION,
        parameters=_execute_code.parameters(),
        is_idempotent=_execute_code.IS_IDEMPOTENT,
    ),
    ToolApi(
        name=ApiName.EXPORT_FILE,
        description=_export_file.DESCRIPTION,
        parameters=_export_file.parameters(),
        is_idempotent=_export_file.IS_IDEMPOTENT,
    ),
)

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=_SANDBOX_APIS,
    executors=("server",),
    meta=_MANIFEST_META,
    system_role=SYSTEM_ROLE,
)


def _sandbox_obs_builder(store: Any) -> Any:
    """Return an observation builder bound to a FileStore."""
    from lca.layer0_infra.computer.op_result import ComputerOpResult
    from lca.layer0_infra.tools.lca_computer.observations import build_computer_observation

    def _build(raw: Any, tool_name: str, start: float) -> Any:
        if isinstance(raw, ComputerOpResult):
            return build_computer_observation(raw, tool_name=tool_name, start=start, store=store)
        return raw

    return _build


def build_sandbox_tools(**kwargs: Any) -> list:
    """Build sandbox-only tools from the standalone manifest + executor."""
    from lca.layer0_infra.tools.builder import build_tools_from_manifest

    store = kwargs.get("file_store")
    if store is None:
        from lca.layer0_infra.file_store import get_default_file_store

        store = get_default_file_store()

    sandbox = kwargs.get("sandbox")
    if sandbox is None:
        return []

    from lca.layer0_infra.computer.sandbox_computer import SandboxComputer
    from lca.layer0_infra.plane.resolve import sandbox_ref_from
    from lca.layer0_infra.tools.lca_computer import _invoke_via_executor

    plane = kwargs.get("plane") or sandbox_ref_from(sandbox)
    computer = SandboxComputer(plane=plane, sandbox=sandbox, store=store)
    executor = LcaSandboxExecutor(computer)

    return build_tools_from_manifest(
        MANIFEST,
        executor,
        invoke_fn=cast("Callable[[object, str, dict[str, Any]], Awaitable[Any]]", _invoke_via_executor),
        observation_builder=_sandbox_obs_builder(store),
    )


__all__ = ["IDENTIFIER", "MANIFEST", "SYSTEM_ROLE", "LcaSandboxExecutor", "build_sandbox_tools"]
