"""AssistantToolOverlay Protocol —— 助理域 tool overlay（ADR-0243 D4）。

薄门面：仅暴露 create / update / remove / list_installed 四个动作。约束：

1. **只写本助理 ``{home}/tools/``**；禁止写全局工具注册表。
2. **tool.json 必须通过 ``ToolSpec`` schema 校验**（frozen，未知字段
   fail-closed）；未通过不落盘、不发 EP。
3. **不因新增工具扩权**：``builtin_preset`` 包装的内置工具仍受其自身
   grant 约束；``required_grant`` 只声明，运行时仍走 C5 衰减。
4. **配置面变更统一留痕**：写盘后更新 manifest ``tools`` 索引 +
   ``revision_seq++`` + ``revisions/`` 快照 + ``assistant.profile.revised`` EP。

与 ``AssistantSkillOverlay`` 同构；单类不得同时实现两者（沿用
ADR-0187「无 God Catalog」纪律）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.models.assistant.tool_spec import ToolSpec

__all__ = [
    "AssistantToolOverlay",
    "ToolInstallReceipt",
    "ToolNotInstalled",
]


@dataclass(frozen=True)
class ToolInstallReceipt:
    """``create`` / ``update`` 的不可变回执（与 skill 回执同构）。"""

    assistant_id: str
    tool_id: str
    digest: str
    """``tool.json`` 内容的 sha256 摘要（``sha256:<hex>``）。"""
    installed_at: str
    """ISO-8601 UTC。"""
    revision_seq: int
    manifest_digest: str
    actor: str
    install_path: str
    """``{home}/tools/<tool_id>/`` 绝对路径。"""

    def __post_init__(self) -> None:
        if not self.assistant_id or not self.assistant_id.strip():
            raise ValueError("assistant_id 必为非空字符串")
        if not self.tool_id or not self.tool_id.strip():
            raise ValueError("tool_id 必为非空字符串")
        if not self.digest or not self.digest.strip():
            raise ValueError("digest 必为非空内容摘要")
        if self.revision_seq < 0:
            raise ValueError(f"revision_seq 必为非负整数,得到 {self.revision_seq!r}")
        if not self.manifest_digest or not self.manifest_digest.strip():
            raise ValueError("manifest_digest 必为非空字符串")
        if not self.actor or not self.actor.strip():
            raise ValueError("actor 必为非空字符串")
        if not self.install_path or not self.install_path.strip():
            raise ValueError("install_path 必为非空路径")


class ToolNotInstalled(LookupError):  # noqa: N818
    """``remove`` 找不到 ``{home}/tools/<tool_id>/`` 落盘定义。"""


@runtime_checkable
class AssistantToolOverlay(Protocol):
    """助理域 tool overlay —— create / update / remove / list_installed。

    写路径 ⊆ ``{home}/tools/``；全局工具注册表只读不写。
    """

    async def create(
        self,
        assistant_id: str,
        spec: ToolSpec,
        *,
        actor: str = "system",
    ) -> ToolInstallReceipt:
        """在 ``{home}/tools/<tool_id>/`` 写入 tool.json 并发 EP。

        失败语义：
        - ``assistant_id`` 不存在 / digest 不匹配 ⇒ Catalog 异常透传；
        - ``ToolSpec`` 校验失败 ⇒ ValueError，不写盘、不发 EP；
        - 工具已存在 ⇒ 先删后写（覆盖式创建）。
        """
        ...

    async def update(
        self,
        assistant_id: str,
        tool_id: str,
        spec: ToolSpec,
        *,
        actor: str = "system",
    ) -> ToolInstallReceipt:
        """覆盖 ``{home}/tools/<tool_id>/tool.json`` 并发 EP。

        失败语义同 ``create``；``tool_id`` 与 ``spec.name`` 必须一致。
        """
        ...

    async def remove(
        self,
        assistant_id: str,
        tool_id: str,
        *,
        actor: str = "system",
    ) -> None:
        """删除 ``{home}/tools/<tool_id>/`` 并发 ``assistant.profile.revised`` EP。

        失败语义：``tool_id`` 未落盘 ⇒ ``ToolNotInstalled``（不删盘、不发 EP）。
        """
        ...

    def list_installed(self, assistant_id: str) -> tuple[ToolInstallReceipt, ...]:
        """扫 ``{home}/tools/`` 列已定义工具（``tool_id`` 升序）。

        跨助理隔离：只读本助理 Home，不触达全局注册表或其他助理。
        """
        ...
