"""Employee-machine (box) tools — ADR-0248 §3.2 "我的电脑" surface.

``BoxAccessor`` 是员工电脑文件系统的路径闸：所有文件操作必须落在
``/home/box``（或构造传入的隔离根目录）内。本模块把该访问器包装成
标准 ``Tool``，供 ``concept.tool.fork`` 在 gated 模式追加到模型工具集。

``box_run_command`` 是员工机 Shell。它默认不进入工具集；只有在
``auto_review_mode != "off"``（工具会被 ``AutoReviewWrappedTool`` 包装）
时才暴露，保证 Shell 写操作至少经过 Auto-Review 硬闸（ADR-0248 切片 4）。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any, ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.computer.box_accessor import BoxAccessor


class BoxReadFileTool(Tool):
    """读取员工电脑（我的电脑）上的文件。"""

    name: ClassVar[str] = "box_read_file"
    description: ClassVar[str] = (
        "读取员工电脑（我的电脑）上的文件内容。路径自动锚定在员工电脑沙箱根目录内，"
        "越界访问会被拒绝。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "员工电脑沙箱内的文件路径（相对或绝对）"},
            "start_line": {"type": "integer", "description": "可选起始行号（从 1 开始）"},
            "end_line": {"type": "integer", "description": "可选结束行号（含）"},
        },
        "required": ["path"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, box_accessor: BoxAccessor) -> None:
        self._box = box_accessor

    def validate(self, args: dict[str, Any]) -> str | None:
        path = args.get("path")
        if not path or not isinstance(path, str):
            return "path 必填且为字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return _failure(err, kind=FAILURE_KIND_VALIDATION)
        path = str(args["path"])
        try:
            content = await asyncio.to_thread(self._box.read_text, path)
        except (FileNotFoundError, PermissionError, OSError) as exc:
            return _failure(f"读取员工机文件失败：{exc}")
        lines = content.splitlines(keepends=True)
        start = int(args.get("start_line") or 1)
        end = int(args.get("end_line") or len(lines))
        selected = "".join(lines[start - 1 : end])
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"path": self._box.resolve_path(path).as_posix(), "content": selected},
        )


class BoxWriteFileTool(Tool):
    """写入员工电脑（我的电脑）上的文件。"""

    name: ClassVar[str] = "box_write_file"
    description: ClassVar[str] = (
        "在员工电脑（我的电脑）沙箱内写入文件。会自动创建父目录。"
        "路径锚定在员工电脑沙箱根目录内，越界写入会被拒绝。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "员工电脑沙箱内的目标文件路径"},
            "content": {"type": "string", "description": "要写入的文件内容"},
            "create_directories": {
                "type": "boolean",
                "description": "是否自动创建父目录（默认 true）",
            },
        },
        "required": ["path", "content"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[str] = "persistent"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, box_accessor: BoxAccessor) -> None:
        self._box = box_accessor

    def validate(self, args: dict[str, Any]) -> str | None:
        path = args.get("path")
        if not path or not isinstance(path, str):
            return "path 必填且为字符串"
        if not isinstance(args.get("content"), str):
            return "content 必填且为字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return _failure(err, kind=FAILURE_KIND_VALIDATION)
        path = str(args["path"])
        content = str(args["content"])
        try:
            target = await asyncio.to_thread(self._box.write_text, path, content)
        except (PermissionError, OSError) as exc:
            return _failure(f"写入员工机文件失败：{exc}")
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"path": target.as_posix(), "bytes_written": len(content.encode("utf-8"))},
        )


class BoxListFilesTool(Tool):
    """列出员工电脑（我的电脑）沙箱内的目录内容。"""

    name: ClassVar[str] = "box_list_files"
    description: ClassVar[str] = (
        "列出员工电脑（我的电脑）沙箱内指定目录下的文件和子目录。路径锚定在员工电脑沙箱根目录内。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "directory_path": {
                "type": "string",
                "description": "员工电脑沙箱内的目录路径（默认沙箱根目录）",
                "default": ".",
            },
        },
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, box_accessor: BoxAccessor) -> None:
        self._box = box_accessor

    def validate(self, args: dict[str, Any]) -> str | None:
        directory = args.get("directory_path")
        if directory is not None and not isinstance(directory, str):
            return "directory_path 必须为字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        directory = str(args.get("directory_path") or ".")
        try:
            target = await asyncio.to_thread(self._box.resolve_path, directory)
            entries = await asyncio.to_thread(os.listdir, target)
        except (PermissionError, OSError) as exc:
            return _failure(f"列出员工机目录失败：{exc}")
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"directory": target.as_posix(), "entries": sorted(entries)},
        )


class BoxRunCommandTool(Tool):
    """在员工电脑（我的电脑）沙箱根目录内执行 shell 命令。

    仅在 Auto-Review 开启（``auto_review_mode != "off"``）时由工具装配暴露，
    执行前会被 ``AutoReviewWrappedTool`` 硬闸审查。
    """

    name: ClassVar[str] = "box_run_command"
    description: ClassVar[str] = (
        "在员工电脑（我的电脑）沙箱根目录内执行一条 shell 命令并返回 stdout / stderr。"
        "工作目录固定为员工电脑沙箱根目录。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"},
            "timeout_s": {"type": "integer", "description": "超时秒数（默认 30）"},
        },
        "required": ["command"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[str] = "persistent"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, box_accessor: BoxAccessor) -> None:
        self._box = box_accessor

    def validate(self, args: dict[str, Any]) -> str | None:
        command = args.get("command")
        if not command or not isinstance(command, str):
            return "command 必填且为字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return _failure(err, kind=FAILURE_KIND_VALIDATION)
        command = str(args["command"])
        timeout_s = int(args.get("timeout_s") or 30)

        adapter = getattr(self._box, "adapter", None)
        if adapter is not None and hasattr(adapter, "run_command"):
            try:
                res = await adapter.run_command(command, timeout_s=timeout_s)
            except TimeoutError as exc:
                return _failure(str(exc))
            except PermissionError as exc:
                return _failure(f"安全硬闸拦截：{exc}")
            except Exception as exc:
                return _failure(f"员工机命令执行失败：{exc}")
            return Observation(
                observation_id=new_id("obs"),
                success=res.returncode == 0,
                payload={
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "returncode": res.returncode,
                },
                error="" if res.returncode == 0 else f"exit code {res.returncode}",
            )

        cwd = self._box.root_dir

        def _run() -> subprocess.CompletedProcess[str]:
            # 员工机 Shell 语义需要管道；AutoReviewWrappedTool 在暴露前已保证
            # auto_review_mode != "off"，上层 SafeExecutor 仍会做权限清单闸。
            return subprocess.run(  # noqa: S602
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=cwd,
            )

        try:
            proc = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired as exc:
            stdout_text = (
                exc.stdout
                if isinstance(exc.stdout, str)
                else (exc.stdout or b"").decode("utf-8", errors="replace")
            )
            stderr_text = (
                exc.stderr
                if isinstance(exc.stderr, str)
                else (exc.stderr or b"").decode("utf-8", errors="replace")
            )
            return _failure(
                f"员工机命令超时（>{timeout_s}s）",
                payload={"stdout": stdout_text, "stderr": stderr_text},
            )
        except OSError as exc:
            return _failure(f"员工机命令执行失败：{exc}")
        return Observation(
            observation_id=new_id("obs"),
            success=proc.returncode == 0,
            payload={
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
            },
            error="" if proc.returncode == 0 else f"exit code {proc.returncode}",
        )


def _failure(
    message: str, *, kind: str = FAILURE_KIND_EXECUTION, payload: Any = None
) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=payload,
        error=message,
        extra={FAILURE_KIND: kind},
    )


def build_box_tools(box_accessor: BoxAccessor, *, include_shell: bool = False) -> list[Tool]:
    """Build employee-machine tools consuming ``box_accessor``."""
    tools: list[Tool] = [
        BoxReadFileTool(box_accessor),
        BoxWriteFileTool(box_accessor),
        BoxListFilesTool(box_accessor),
    ]
    if include_shell:
        tools.append(BoxRunCommandTool(box_accessor))
    return tools


__all__ = [
    "BoxListFilesTool",
    "BoxReadFileTool",
    "BoxRunCommandTool",
    "BoxWriteFileTool",
    "build_box_tools",
]
