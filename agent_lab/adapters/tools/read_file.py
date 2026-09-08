"""read_file Tool —— agent_lab 自带的 LCA-风格 Tool(同 BashTool/FileWriteTool 形状)。

读取 host 进程 CWD 下的一个文本文件,返回 ``Observation`` 带 ``path``
与 ``content``。Creator/agent 场景用来读取上一轮写下的文件、上游产物、
或仅做"看一眼"自检。

安全:本 Tool 不调用 sandbox,只走 :class:`validate_writable_file` 的
path policy 兄弟(实际上读只需要确认文件存在且可读);上层
:class:`SimpleSafeExecutor` + :class:`ToolPermissionManifest` 负责 gate
危险路径(例如禁止读 ``.env``、``/etc/passwd`` 等)。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.tool import ParameterSpec, ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool

IDENTIFIER = "read_file"

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="readFile",
            description=(
                "读取 host 进程 CWD 下的一个文本文件,返回 path/content/size_bytes。"
                "用于读取上一轮写下的文件、上游产物,或 '看一眼' 自检。"
                "不递归,不列目录;Solo / 通用场景请改用 sandbox 的 computer 目录工具。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目标文件路径"},
                    "max_bytes": {
                        "type": "integer",
                        "description": "读取上限(默认 1 MiB)",
                    },
                },
                "required": ["path"],
            },
            is_idempotent=True,
            default_timeout_ms=10_000,
        ),
    ),
    meta=ToolMeta(
        avatar="📄",
        title="read_file",
        description="Read a text file from disk",
    ),
    parameters={
        "path": ParameterSpec(
            type="string",
            required=True,
            ui_hint="path",
            description="目标文件路径",
        ),
        "max_bytes": ParameterSpec(
            type="integer",
            required=False,
            default=1_048_576,
            ui_hint="number",
            description="读取上限(默认 1 MiB)",
        ),
    },
)


class ReadFileTool(Tool):
    """read_file Tool 实现。"""

    name = "read_file"
    description = MANIFEST.api[0].description
    parameters: ClassVar[dict[str, Any]] = MANIFEST.api[0].parameters
    is_idempotent = True
    default_timeout_s = MANIFEST.api[0].default_timeout_ms // 1000

    def validate(self, args: dict[str, Any]) -> str | None:
        path = args.get("path")
        if not path or not isinstance(path, str):
            return "path 必填且为字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        err = self.validate(args)
        if err is not None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=err,
                latency_ms=int((time.monotonic() - start) * 1000),
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )

        path = Path(args["path"]).expanduser()  # noqa: ASYNC240 — agent_lab Tool, sync fs OK
        max_bytes = int(args.get("max_bytes") or 1_048_576)

        if not path.exists():
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"文件不存在: {path}",
                latency_ms=int((time.monotonic() - start) * 1000),
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        if path.is_dir():
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"目标是目录,不是文件: {path}",
                latency_ms=int((time.monotonic() - start) * 1000),
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )

        try:
            data = path.read_bytes()
        except OSError as exc:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"读取失败: {exc}",
                latency_ms=int((time.monotonic() - start) * 1000),
                extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
            )

        truncated = len(data) > max_bytes
        if truncated:
            data = data[:max_bytes]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")

        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "path": str(path),
                "content": text,
                "size_bytes": len(data),
                "truncated": truncated,
            },
            latency_ms=latency_ms,
        )


def build_read_file_tool() -> Tool:
    impl = ReadFileTool()
    tool_cls = type(
        "Tool_read_file",
        (Tool,),
        {
            "name": impl.name,
            "description": impl.description,
            "parameters": impl.parameters,
            "is_idempotent": impl.is_idempotent,
            "default_timeout_s": impl.default_timeout_s,
            "execute": impl.execute,
            "validate": impl.validate,
        },
    )
    return tool_cls()  # type: ignore[no-any-return]


__all__ = ["IDENTIFIER", "MANIFEST", "ReadFileTool", "build_read_file_tool"]
