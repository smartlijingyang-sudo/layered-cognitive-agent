"""Sandbox runtime tools — inspect / execute (ADR-0050)."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SANDBOX_PREINSTALLED_PYTHON_PACKAGES,
)
from lca.contracts.protocols import Sandbox, Tool
from lca.layer0_infra.file_store import FileStore, LocalFileStore
from lca.layer0_infra.sandbox.runtime_scope import ensure_sandbox_runtime
from lca.layer0_infra.tools.run_attachment_scope import get_current_run_attachment_ids
from lca.layer0_infra.tools.sandbox_exec_observation import (
    build_exec_observation,
    build_inspect_observation,
)
from lca.layer0_infra.tools.tool_invocation_scope import get_current_tool_invocation_id

SANDBOX_INSPECT_TOOL_NAME = "sandbox_inspect"
SANDBOX_EXECUTE_TOOL_NAME = "sandbox_execute"

_PACKAGES_HINT = ", ".join(SANDBOX_PREINSTALLED_PYTHON_PACKAGES)


class SandboxInspectTool(Tool):
    """Structured probe of the sandbox workspace — files, sheets, columns, NaN counts."""

    name = SANDBOX_INSPECT_TOOL_NAME
    description = (
        "探查沙箱工作根已挂载文件的结构化 profile（路径、sheets、columns、NaN 计数）。"
        "分析 Excel/CSV 前应先调用；run 首触沙箱时会自动 inspect，可跳过重复调用。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "force": {
                "type": "boolean",
                "description": "强制重新探查（默认使用缓存）",
                "default": False,
            },
        },
    }
    is_idempotent = True
    default_timeout_s = DEFAULT_SANDBOX_TIMEOUT_S

    def __init__(
        self,
        sandbox: Sandbox,
        store: FileStore | LocalFileStore,
    ) -> None:
        self._sandbox = sandbox
        self._store = store

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        invocation_id = get_current_tool_invocation_id() or "sbx_inspect"
        runtime = await ensure_sandbox_runtime(self._sandbox, self._store)
        force = bool(args.get("force", False))
        result = await runtime.inspect(force=force)
        return build_inspect_observation(result, invocation_id, start)


class SandboxExecuteTool(Tool):
    """Execute Python in the run-bound sandbox."""

    name = SANDBOX_EXECUTE_TOOL_NAME
    description = (
        "在 run 绑定的隔离沙箱中执行 Python。环境已挂载 run 附件到工作根/<文件名>；"
        "产出写到 outputs/ 自动收集。\n"
        f"预装包: {_PACKAGES_HINT}\n"
        "先 sandbox_inspect 了解列名与 NaN；字符串操作前 dropna().astype(str)。"
        "画图中文：已预置 WenQuanYi/CJK 字体。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要在沙箱中执行的源代码"},
            "language": {
                "type": "string",
                "description": "语言，MVP 仅 python",
                "default": "python",
            },
            "attachment_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "额外挂载附件；run 级附件已自动挂载",
            },
            "timeout_s": {
                "type": "integer",
                "description": f"执行超时秒数，默认 {DEFAULT_SANDBOX_TIMEOUT_S}",
            },
        },
        "required": ["code"],
    }
    is_idempotent = False
    default_timeout_s = DEFAULT_SANDBOX_TIMEOUT_S

    def __init__(
        self,
        sandbox: Sandbox,
        store: FileStore | LocalFileStore,
    ) -> None:
        self._sandbox = sandbox
        self._store = store

    def validate(self, args: dict[str, Any]) -> str | None:
        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            return "code 必须是非空字符串"
        for item in args.get("attachment_ids") or []:
            if not isinstance(item, str) or not item.strip():
                return "attachment_ids 各项必须是非空字符串"
            if not self._store.exists(item.strip()):
                return f"附件不存在: {item}"
        for aid in get_current_run_attachment_ids():
            if not self._store.exists(aid):
                return f"run 附件不存在: {aid}"
        if args.get("timeout_s") is not None and not isinstance(
            args.get("timeout_s"), (int, float)
        ):
            return "timeout_s 必须是数字"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        code = str(args["code"])
        language = str(args.get("language") or "python").strip() or "python"
        explicit_ids = [
            str(i).strip() for i in (args.get("attachment_ids") or []) if str(i).strip()
        ]
        try:
            timeout_s = int(args.get("timeout_s", DEFAULT_SANDBOX_TIMEOUT_S))
        except (TypeError, ValueError):
            timeout_s = DEFAULT_SANDBOX_TIMEOUT_S

        invocation_id = get_current_tool_invocation_id() or "sbx_exec"
        runtime = await ensure_sandbox_runtime(
            self._sandbox,
            self._store,
            attachment_ids=get_current_run_attachment_ids(),
        )
        result = await runtime.execute(
            code,
            language=language,
            timeout_s=timeout_s,
            invocation_id=invocation_id,
            explicit_attachment_ids=explicit_ids or None,
        )
        return build_exec_observation(self._store, result, invocation_id, start)
