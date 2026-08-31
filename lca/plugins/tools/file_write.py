"""file_write Tool —— Creator §13.3 流程 Step 5「把 plugin 源码写到磁盘」。

Plugin-thinking
---------------
- Tier-3 behavior tool，挂在 :class:`ToolsService` 注册表。
- ``file_write.write`` 在 ``<workspace>/<name>`` 落文本文件，返回
  ``Observation`` 带 ``path`` 与 ``size_bytes``。
- 每次 invoke 落 :class:`ToolStarted` / :class:`ToolInvoked`（由
  :class:`SimpleSafeExecutor` 自动写入），Tool 自身不写 journal。

为什么单独实现而非复用 :class:`WriteFileExecutor`：creator 场景的
file_write 写的是 *plugin 源码*（一次性，路径在 preset 目录），不需要
``FileStore`` 的产品附件语义；这里给一个最小可用 ``Tool`` 实现。

NOTE: ``pathlib`` 在 async 上下文是 ruff ASYNC240 命中点；本 Tool 接受
这是 Creator Tool 的真实路径（creator session 里写 preset 文件是
本地 fs 的常规操作，不在高性能关键路径）；保留 sync pathlib 调用，
注释豁免 ruff 检查。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.tool import ParameterSpec, ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool

IDENTIFIER = "file-write"


MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="fileWrite",
            description=(
                "把文本内容写到指定路径（相对当前工作目录或绝对路径）。"
                "Creator 流程用它写 plugin 源码文件。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目标文件路径"},
                    "content": {"type": "string", "description": "文本正文"},
                    "mkdir_parents": {
                        "type": "boolean",
                        "description": "是否自动创建父目录（默认 true）",
                    },
                },
                "required": ["path", "content"],
            },
            is_idempotent=True,
            default_timeout_ms=10_000,
        ),
    ),
    meta=ToolMeta(
        avatar="📝",
        title="file_write",
        description="Write text to a path on disk",
    ),
    parameters={
        "path": ParameterSpec(
            type="string",
            required=True,
            ui_hint="path",
            description="目标文件路径",
        ),
        "content": ParameterSpec(
            type="string",
            required=True,
            ui_hint="code",
            description="文本正文",
        ),
        "mkdir_parents": ParameterSpec(
            type="boolean",
            required=False,
            default=True,
            ui_hint="boolean",
            description="是否自动创建父目录（默认 true）",
        ),
    },
)


class FileWriteTool(Tool):
    """file_write Tool 实现。"""

    name: ClassVar[str] = "file_write"
    description: ClassVar[str] = MANIFEST.api[0].description
    parameters: ClassVar[dict[str, Any]] = MANIFEST.api[0].parameters
    is_idempotent: ClassVar[bool] = True
    default_timeout_s: ClassVar[int] = MANIFEST.api[0].default_timeout_ms // 1000

    def validate(self, args: dict[str, Any]) -> str | None:
        path = args.get("path")
        content = args.get("content")
        if not path or not isinstance(path, str):
            return "path 必填且为字符串"
        if not isinstance(content, str):
            return "content 必填且为字符串"
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

        path = Path(args["path"]).expanduser()  # noqa: ASYNC240 — Creator Tool 同步 fs 可接受
        mkdir_parents = bool(args.get("mkdir_parents", True))
        if mkdir_parents and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = args["content"].encode("utf-8")
            path.write_bytes(data)
        except OSError as exc:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"写入失败：{exc}",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"path": str(path), "size_bytes": len(data)},
            latency_ms=latency_ms,
        )


def build_file_write_tool() -> Tool:
    impl = FileWriteTool()
    tool_cls = type(
        "Tool_file_write",
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


__all__ = ["IDENTIFIER", "MANIFEST", "FileWriteTool", "build_file_write_tool"]


# ── Plugin manifest setup ─────────────────────────────────────


from pydantic import BaseModel, ConfigDict  # noqa: E402

from lca.harness.plugin_api import PluginContext, PluginKind, plugin  # noqa: E402
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore")


@plugin(
    id="lca-tool-file-write",
    provides=["tools.file_write"],
    requires=["tools"],
    implements=["Tool"],
    layer="L1",
    effects="tools",
    description="file_write Tool — Creator §13.3 file/shell primitive",
    test_suite="tests/test_cordis_creator_real_scenario.py",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.TURN,
        authority=('tool.invoke',),
        evidence=('lca-tool-file-write.checked', 'lca-tool-file-write.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('tool.invoke', 'tools.file_write'),
        emits=('tools.file_write.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """把 file_write Tool 注册到 tools 服务（供单 port cordis-creator 使用）。

    同 :mod:`lca.plugins.tools.bash` 的 setup 模式。
    """
    tool = build_file_write_tool()
    if tool is not None:
        ctx.require("tools").register(tool)
