"""Composition 契约 —— 创造模式（§13.3 Creator）的可替换接口。

设计哲学
--------
创造模式让 agent 通过普通 Tool 调用 ``cordis_control.mount/unmount`` 把自己
写的 plugin 挂到当前 Context。Plugin-thinking 一以贯之：**Composer 自身也
是 plugin**（Tier-1 seam + Tier-2 provider + Tier-3 behavior 三层），不是
游离在 plugin 体系外的单例。

本模块落宪法 §13.3.1 五条硬约束（C3/C4/C5/PR12/§23.2）到协议层：

- **C3 Journal 单一事实源** — mount/unmount/inspect/publish 全部走
  ``JournalBackend.write``；本模块导出 ``ComposerErrorCode`` 让拒绝事件
  携带机器可读错误码。
- **C4 不写 AgentState** — Composer 是群 Composition 唯一组装者；Sensor
  / Gate / Body 不得直接调用 mount。
- **C5 Capability 衰减** — :meth:`Composer.mount` 接 ``caller_grant`` 参数；
  任何超集请求抛 :class:`CapabilityGrantExceeded` 并落 ``PluginMountRejected``
  事件，事件 payload 含 ``capability_grant`` 与 ``requested_capabilities``
  快照供回溯。
- **PR12 PluginMeta TypedDict 强制** — factory 必须声明
  ``factory.plugin_meta: PluginMeta``；缺则 :class:`PluginMetaMissing`。
- **§23.2 Invariant 检查** — Composer 持有 ``InvariantChecker`` Protocol；
  mount 前先调 ``checker.check_mount``，失败抛 :class:`InvariantViolation`。

为什么独立成 ``composition.py`` 而不是塞进 ``seam.py``：seam.py 已收敛为
单函数 ``consume()``（cordis 迁移后），新增契约不动它；composition 是新
concern，独立文件更易回溯 ADR 来源（§13.3）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from lca.contracts.harness.plugin_meta import PluginMeta

if TYPE_CHECKING:
    from lca.contracts.models.observability.journal import StampedEvent


# ── 错误码（机器可读，挂载拒绝事件必填） ────────────────────


class ComposerErrorCode(str, Enum):
    """挂载/卸载/inspect 任一动作被拒时的具名错误码。

    出现在 :class:`PluginMountRejected.reason_code` 字段，供 lca-ops trace /
    单元测试 / 调试回溯按错误码索引，不依赖自然语言匹配。
    """

    CAPABILITY_GRANT_EXCEEDED = "CapabilityGrantExceeded"
    """C5：调用方 grant 不包含 plugin 声明的能力子集。"""
    PLUGIN_META_MISSING = "PluginMetaMissing"
    """PR12：factory 缺少 ``plugin_meta: PluginMeta`` TypedDict。"""
    INVARIANT_VIOLATION = "InvariantViolation"
    """§23.2：invariant 检查失败（plugin 自身或与系统冲突）。"""
    NAME_CONFLICT = "NameConflict"
    """mount 重名：当前 Context 已挂载同名 plugin。"""
    NOT_MOUNTED = "NotMounted"
    """unmount 一个尚未挂载的 plugin。"""
    INVALID_PAYLOAD = "InvalidPayload"
    """参数缺失或类型错误（mount 必填 name/factory 等）。"""


# ── 异常类型（拒绝事件 + 异常双重信号） ─────────────────────


class ComposerError(RuntimeError):
    """Composer 错误的基类（不裸抛 Exception）。"""

    code: ComposerErrorCode

    def __init__(self, message: str, *, code: ComposerErrorCode) -> None:
        super().__init__(message)
        self.code = code


class CapabilityGrantExceededError(ComposerError):
    """C5 失败：调用方 grant 不包含 plugin 声明的能力。

    别名 ``CapabilityGrantExceeded`` 保留以兼容宪法 §13.3.1 描述与现有调用点。
    """

    def __init__(
        self,
        message: str,
        *,
        granted: tuple[str, ...],
        required: tuple[str, ...],
    ) -> None:
        super().__init__(message, code=ComposerErrorCode.CAPABILITY_GRANT_EXCEEDED)
        self.granted = granted
        self.required = required


# 宪法 §13.3.1 / plan 文件里使用的简称；保留为「公开别名」
CapabilityGrantExceeded = CapabilityGrantExceededError


class PluginMetaMissingError(ComposerError):
    """PR12 失败：factory 缺少 plugin_meta。

    别名 ``PluginMetaMissing`` 同上。
    """

    def __init__(self, message: str, *, plugin_name: str) -> None:
        super().__init__(message, code=ComposerErrorCode.PLUGIN_META_MISSING)
        self.plugin_name = plugin_name


PluginMetaMissing = PluginMetaMissingError


class InvariantViolationError(ComposerError):
    """§23.2 失败：invariant 检查器拒绝。

    别名 ``InvariantViolation`` 同上。
    """

    def __init__(self, message: str, *, plugin_name: str, check_name: str) -> None:
        super().__init__(message, code=ComposerErrorCode.INVARIANT_VIOLATION)
        self.plugin_name = plugin_name
        self.check_name = check_name


InvariantViolation = InvariantViolationError


class NameConflictError(ComposerError):
    """重复 mount 同名 plugin。"""

    def __init__(self, message: str, *, plugin_name: str) -> None:
        super().__init__(message, code=ComposerErrorCode.NAME_CONFLICT)
        self.plugin_name = plugin_name


NameConflict = NameConflictError


class NotMountedError(ComposerError):
    """unmount 一个尚未挂载的 plugin。"""

    def __init__(self, message: str, *, plugin_name: str) -> None:
        super().__init__(message, code=ComposerErrorCode.NOT_MOUNTED)
        self.plugin_name = plugin_name


NotMounted = NotMountedError


# ── 数据类（mount/unmount/inspect 的返回值） ────────────────


@dataclass(frozen=True)
class PluginFactory:
    """可被 Composer.mount 接受的 plugin 工厂（闭包 + 元数据）。

    - ``factory``: 接受 0 个必填位置参数的可调用对象，mount 时实例化并
      注入 Context。
    - ``plugin_meta``: :class:`PluginMeta` TypedDict；PR12 强制，缺则拒绝。
    - ``source_path``: 可选，plugin 源码路径；publish 时写入 preset 目录。
    """

    name: str
    factory: Any  # Callable[[], Any] — 实际签名见 mount 处的检查
    plugin_meta: PluginMeta = field(default_factory=lambda: cast("PluginMeta", {}))
    source_path: str = ""


@dataclass(frozen=True)
class MountResult:
    """一次成功 mount 的结果（带已盖章事件 + Context key）。"""

    plugin_name: str
    plugin_id: str
    context_key: str
    capabilities: tuple[str, ...]
    capability_grant: tuple[str, ...]
    meta_snapshot: dict[str, object]
    event: StampedEvent | None = None
    """成功路径发出的 :class:`PluginMounted` 已盖章事件。"""

    @property
    def ok(self) -> bool:
        return self.event is not None


@dataclass(frozen=True)
class UnmountResult:
    """一次成功 unmount 的结果。"""

    plugin_name: str
    context_key: str
    event: StampedEvent | None = None

    @property
    def ok(self) -> bool:
        return self.event is not None


@dataclass(frozen=True)
class InspectEntry:
    """单条已挂载 plugin 的派生能力条目。"""

    name: str
    context_key: str
    plugin_id: str
    meta: dict[str, object]
    implements: tuple[str, ...]
    capabilities: tuple[str, ...]
    policy_class: str
    side_effects: str


@dataclass(frozen=True)
class InspectResult:
    """inspect 动作的返回值（当前 Context 派生能力图）。"""

    entries: tuple[InspectEntry, ...]
    context_keys: tuple[str, ...]
    event: StampedEvent | None = None

    @property
    def mounted_count(self) -> int:
        return len(self.entries)


# ── Invariant 检查器（§23.2） ──────────────────────────────


@runtime_checkable
class InvariantChecker(Protocol):
    """mount 前的轻量 invariant 检查钩子（§23.2）。

    Plugin-thinking 一以贯之：InvariantChecker 也是 plugin；默认实现见
    ``lca/plugins/providers/composition.py::DefaultInvariantChecker``。
    测试可注入 ``AlwaysAllow`` / ``AlwaysDeny`` 实现。
    """

    def check_mount(self, name: str, meta: PluginMeta) -> None:
        """允许时静默通过；拒绝时抛 :class:`InvariantViolation`。"""
        ...

    def check_unmount(self, name: str, meta: PluginMeta) -> None:
        """允许时静默通过；默认实现通常 no-op。"""
        ...


# ── Composer 协议 ────────────────────────────────────────


@runtime_checkable
class Composer(Protocol):
    """群 Composition 唯一组装者（plugin 化）。

    实现由 Tier-2 provider 注入；默认 :class:`CordisComposer` 见
    ``lca/plugins/providers/composition.py``。

    所有动作的硬约束：

    1. mount / unmount 前必跑 C5 / PR12 / §23.2 三道闸；
    2. 成功路径写 :class:`PluginMounted` / :class:`PluginUnmounted` /
       :class:`PluginInspected`；
    3. 拒绝路径写 :class:`PluginMountRejected`，抛带 ``ComposerError.code``
       的具名异常；
    4. inspect 是只读，不写 AgentState（§C4），但允许落
       :class:`PluginInspected` 作 audit 锚点。
    """

    def mount(
        self,
        factory: PluginFactory,
        *,
        caller_grant: tuple[str, ...] = (),
        actor_role: str = "",
        step: int = 0,
    ) -> MountResult:
        """挂载 plugin：grant ⊇ capabilities + meta 存在 + invariant 通过 → 成功。"""
        ...

    def unmount(
        self,
        plugin_name: str,
        *,
        actor_role: str = "",
        step: int = 0,
    ) -> UnmountResult:
        """卸载 plugin：plugin 必须当前挂载；否则 :class:`NotMounted`。"""
        ...

    def inspect(self, *, actor_role: str = "") -> InspectResult:
        """返回当前 Context 派生能力图（§13.3.3 inspect）。"""
        ...

    def list_presets(self) -> tuple[str, ...]:
        """返回当前进程可见的 preset id 列表（§13.3 publish 持久化层）。"""
        ...


__all__ = [
    "CapabilityGrantExceeded",
    "CapabilityGrantExceededError",
    "Composer",
    "ComposerError",
    "ComposerErrorCode",
    "InspectEntry",
    "InspectResult",
    "InvariantChecker",
    "InvariantViolation",
    "InvariantViolationError",
    "MountResult",
    "NameConflict",
    "NameConflictError",
    "NotMounted",
    "NotMountedError",
    "PluginFactory",
    "PluginMetaMissing",
    "PluginMetaMissingError",
    "UnmountResult",
]
