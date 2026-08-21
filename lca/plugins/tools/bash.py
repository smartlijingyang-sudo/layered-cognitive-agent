"""bash Tool —— Creator §13.3 流程里可选用 shell 命令（受 sandbox 控制）。

Plugin-thinking
---------------
- Tier-3 behavior tool，挂在 :class:`ToolsService` 注册表。
- ``bash.run`` 通过 :mod:`subprocess` 执行一条命令并返回 stdout / stderr。
- 默认 ``timeout_s=30``；超时报错而非阻塞。
- 每次 invoke 落 :class:`ToolStarted` / :class:`ToolInvoked`（由
  :class:`SimpleSafeExecutor` 自动写入），Tool 自身不写 journal。

安全：本 Tool 不调用 sandbox；它的设计目标是 creator 在 preset 目录或
workspace 内做轻量自检（ls / cat / pytest）。生产环境的危险命令由
上游 :class:`SafeExecutor` 的 :class:`ToolPermissionManifest` 闸住；
本目标范围内不引入新沙箱能力。

NOTE: 本 Tool 使用 ``subprocess.run`` + ``shell=True``（Creator 流程
需要 shell 语义支持 ``ls | grep`` 等管道）；这是有意为之的 trade-off，
上层 ``SafeExecutor`` 与 role profile 必须 gate 危险命令。
"""

from __future__ import annotations

import subprocess
import time
from typing import Any, ClassVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool

IDENTIFIER = "bash"


MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="bashRun",
            description=(
                "在当前进程的工作目录里执行一条 shell 命令并返回 stdout / stderr。"
                "Creator 流程用它在 preset 目录或 workspace 内做轻量自检。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "shell 命令"},
                    "timeout_s": {
                        "type": "integer",
                        "description": "超时秒数（默认 30）",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "可选工作目录（绝对路径）",
                    },
                },
                "required": ["command"],
            },
            is_idempotent=False,
            default_timeout_ms=30_000,
        ),
    ),
    meta=ToolMeta(
        avatar="🖥️",
        title="bash",
        description="Run a shell command (subprocess)",
    ),
)


class BashTool:
    """bash Tool 实现。"""

    name: ClassVar[str] = "bash"
    description: ClassVar[str] = MANIFEST.api[0].description
    parameters: ClassVar[dict[str, Any]] = MANIFEST.api[0].parameters
    is_idempotent: ClassVar[bool] = False
    default_timeout_s: ClassVar[int] = MANIFEST.api[0].default_timeout_ms // 1000

    def validate(self, args: dict[str, Any]) -> str | None:
        command = args.get("command")
        if not command or not isinstance(command, str):
            return "command 必填且为字符串"
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

        command = args["command"]
        timeout_s = int(args.get("timeout_s") or 30)
        cwd = args.get("cwd") or None
        # Creator 流程需要 shell 语义（ls / cat / grep / pytest 等）；
        # 上层 SafeExecutor 必须 gate 危险命令；timeout_s 强制短时窗口。
        # 用 asyncio.to_thread 包装 subprocess.run 避免阻塞 event loop
        # （ruff ASYNC221 命中点）。
        import asyncio as _asyncio

        def _run() -> subprocess.CompletedProcess[str]:
            # Creator shell 语义有意为之；上层 SafeExecutor 必须 gate。
            return subprocess.run(  # noqa: S602
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=cwd,
            )

        try:
            proc = await _asyncio.to_thread(_run)
        except subprocess.TimeoutExpired as exc:
            stdout_text = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr_text = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload={
                    "stdout": stdout_text,
                    "stderr": stderr_text + f"\n[timeout after {timeout_s}s]",
                },
                error=f"命令超时（>{timeout_s}s）",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except OSError as exc:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"执行失败：{exc}",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=proc.returncode == 0,
            payload={
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
            },
            error="" if proc.returncode == 0 else f"exit code {proc.returncode}",
            latency_ms=latency_ms,
        )


def build_bash_tool() -> Tool:
    impl = BashTool()
    tool_cls = type(
        "Tool_bash",
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


__all__ = ["IDENTIFIER", "MANIFEST", "BashTool", "build_bash_tool"]


# ── Plugin manifest setup ─────────────────────────────────────
# This module is referenced as ``$module: lca.plugins.tools.bash`` by
# ``bundles/scenario-cordis-creator.yaml``；provide a no-op setup that
# registers the tool with the tools service so the resolve path
# finds a callable. The actual tool is consumed via ``build_bash_tool()``
# in the Agent composition path; this setup merely keeps the resolved
# plugin graph well-formed.


from pydantic import BaseModel, ConfigDict  # noqa: E402

from lca.harness.plugin_api import PluginContext, PluginKind, plugin  # noqa: E402


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore")


@plugin(
    id="lca-tool-bash",
    provides=["tools.bash"],
    requires=["tools"],
    implements=["Tool"],
    layer="L1",
    effects="tools",
    description="bash Tool — Creator §13.3 file/shell primitive",
    test_suite="tests/test_cordis_creator_real_scenario.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """把 bash Tool 注册到 tools 服务（供单 port cordis-creator 使用）。

    web-standard profile booted 后，scenario-cordis-creator bundle 激活
    本 plugin；本 setup 把 bash Tool 实例塞进 ``tools.compose_service``，
    让 _build_cordis_creator_agent 通过 materialize() 拿到它。
    """
    tool = build_bash_tool()
    if tool is not None:
        ctx.inject("tools").register(tool)
