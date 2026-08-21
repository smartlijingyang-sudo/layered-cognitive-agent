"""CordisControlTool —— Creator §13.3 的运行时 plugin 编排入口（Tier-3 behavior）。

Plugin-thinking
---------------
``cordis_control`` 是 **普通 Tool**（非认知 Hook），按宪法 §13.3.2：

- Agent 决策 ``Decision(use_tool, tool=cordis_control)`` → Body.act →
  SafeExecutor → 这里。
- PR-9 后：4 个 action（``inspect`` / ``mount`` / ``unmount`` / ``publish``）
  通过 ``lca.plugins.creator.faces.implementations.dispatch_legacy_action``
  路由到 4 face（``inspect`` / ``author`` / ``validate`` / ``promote``）。
  backward compat 6 个月后删除（PR-9 stage 2 / PR-10 删除）。
- 每次 invoke 必落 :class:`ToolInvoked` + 链式 :class:`PluginMounted` /
  :class:`PluginMountRejected` / :class:`PluginUnmounted` /
  :class:`PresetPublished`，全链路 audit。

挂载入口
--------
本模块暴露 :func:`build_cordis_control_tool`，返回一个
:class:`lca.contracts.protocols.Tool` 实例；该实例在装配期通过
``tools_service.register(tool)`` 注册到 :class:`ToolsService` 注册表。

文件组织
--------
- 本文件聚焦 Tool 类骨架 + validate + execute 入口 + build 工厂。
- 4 个 action 实现（事件落盘 / preset 写入）见 :mod:`actions`。
- plugin 源加载助手见 :mod:`loader`。
- 4 Creator faces 见 :mod:`lca.plugins.creator.faces.implementations`。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.mechanisms.composition import ComposerError
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.plugins.tools.cordis_control import actions_mount, actions_simple

IDENTIFIER = "cordis-control"
ALLOWED_ACTIONS = ("inspect", "mount", "unmount", "publish")

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="cordisControl",
            description=(
                "Composer 控制面：inspect 当前 Context 派生能力图、"
                "mount 临时 plugin、unmount 已挂载 plugin、publish 把"
                "plugin 源码持久化到 preset 目录。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(ALLOWED_ACTIONS),
                        "description": "控制动作；inspect/mount/unmount/publish 四选一",
                    },
                    "name": {"type": "string", "description": "plugin 名；mount/unmount 必填"},
                    "path": {"type": "string", "description": "mount 时 plugin 源码路径"},
                    "preset_id": {"type": "string", "description": "publish 时 preset 目录名"},
                },
                "required": ["action"],
            },
            is_idempotent=False,
            default_timeout_ms=30_000,
        ),
    ),
    meta=ToolMeta(
        avatar="🧬",
        title="cordis_control",
        description="Creator §13.3 Composer control surface",
    ),
)


class CordisControlTool:
    """cordis_control Tool 实现（构造期绑定 Composer 与 caller_grant）。

    实例方法 :meth:`execute` 是 Body.act 唯一调用入口；具体 action 行为
    委派给 :mod:`actions`，本类只负责参数校验 + dispatch + 错误包 Observation。
    """

    name: ClassVar[str] = "cordis_control"
    description: ClassVar[str] = MANIFEST.api[0].description
    parameters: ClassVar[dict[str, Any]] = MANIFEST.api[0].parameters
    is_idempotent: ClassVar[bool] = False
    default_timeout_s: ClassVar[int] = MANIFEST.api[0].default_timeout_ms // 1000

    def __init__(
        self,
        *,
        composer: Any,
        caller_grant: tuple[str, ...] = (),
        actor_role: str = "",
        preset_root: Path | None = None,
        on_mounted: Any | None = None,
    ) -> None:
        """cordis_control Tool 实例。

        ``on_mounted`` 是 mount 成功后的回调（可选）：
        签名 ``(name, instance, meta) -> None``；上层可借此把刚挂载的 plugin
        注册到 ToolsService（mount 后 capability 自动可调用）。
        ``meta`` 是 plugin_meta dict（含 ``implements`` / ``policy_class`` 等）。
        """
        self._composer = composer
        self._caller_grant = tuple(caller_grant)
        self._actor_role = actor_role
        self._preset_root = preset_root
        self._on_mounted = on_mounted

    def validate(self, args: dict[str, Any]) -> str | None:
        action = args.get("action")
        if action not in ALLOWED_ACTIONS:
            return f"action {action!r} 非法；必须是 {list(ALLOWED_ACTIONS)}"
        if action in {"mount", "unmount"} and not args.get("name"):
            return f"action={action!r} 必填 name"
        if action == "mount" and not args.get("path"):
            return "action='mount' 必填 path（plugin 源码路径）"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        validation = self.validate(args)
        if validation is not None:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=validation,
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )

        action = args["action"]
        try:
            if action == "inspect":
                # PR-9: 4 face dispatch — inspect
                payload = actions_simple.do_inspect(self)
            elif action == "mount":
                # PR-9: mount = author + validate + promote (legacy mapping)
                payload = actions_mount.do_mount(
                    self, name=args["name"], path=args["path"]
                )
            elif action == "unmount":
                # PR-9: unmount = promote(rollback=True)
                payload = actions_simple.do_unmount(self, name=args["name"])
            elif action == "publish":
                # PR-9: publish = promote(target_scope=release, preset_id=...)
                payload = actions_simple.do_publish(
                    self,
                    name=args["name"],
                    path=args["path"],
                    preset_id=args.get("preset_id") or args["name"],
                )
            else:  # pragma: no cover — guarded by validate()
                raise ValueError(f"unreachable action={action!r}")
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload=payload,
                latency_ms=latency_ms,
            )
        except ComposerError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"{exc.code.value}: {exc}",
                latency_ms=latency_ms,
                extra={
                    FAILURE_KIND: FAILURE_KIND_VALIDATION,
                    "error_code": exc.code.value,
                },
            )


def build_cordis_control_tool(
    *,
    composer: Any,
    caller_grant: tuple[str, ...] = (),
    actor_role: str = "",
    preset_root: Path | None = None,
    on_mounted: Any | None = None,
) -> Tool:
    """返回 cordis_control Tool 实例（caller 负责 tools_service.register）。

    ``on_mounted``（可选）：挂载成功后回调，签名 ``(name, instance, meta)``，
    上层可借此把新 plugin 注册到 ToolsService（让 agent 的下一次 use_tool 调用
    能命中）。
    """
    tool_impl = CordisControlTool(
        composer=composer,
        caller_grant=caller_grant,
        actor_role=actor_role,
        preset_root=preset_root,
        on_mounted=on_mounted,
    )
    tool_cls = type(
        "Tool_cordis_control",
        (Tool,),
        {
            "name": tool_impl.name,
            "description": tool_impl.description,
            "parameters": tool_impl.parameters,
            "is_idempotent": tool_impl.is_idempotent,
            "default_timeout_s": tool_impl.default_timeout_s,
            "execute": tool_impl.execute,
            "validate": tool_impl.validate,
        },
    )
    return tool_cls()  # type: ignore[no-any-return]


__all__ = [
    "ALLOWED_ACTIONS",
    "IDENTIFIER",
    "MANIFEST",
    "CordisControlTool",
    "build_cordis_control_tool",
]
