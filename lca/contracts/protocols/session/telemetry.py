"""Session 遥测契约 —— 捕获缝的类型面（对齐 DSH ``session-telemetry``）。

对齐 deepseek-harness ``packages/session/session-telemetry/src/index.ts`` 的
Service Definition：本模块只声明遥测捕获缝的数据形态与协议，不含捕获、
队列、导出等任何实现 —— 那是 ``lca.plugins.session.telemetry_capture``
（捕获协调器）与 ``lca.plugins.session.telemetry_otel``（OTel 后端）的事。

契约边界（AGENTS.md §2.3 观察面、§3 C7/C8）：

- 遥测是观察面派生物：只读 Session 已提交事件，投影为出站记录；
  不写回任何事实源，canonical 日志永不被改写。
- 本模块属 ``contracts`` 层：纯标准库类型，无 I/O、无第三方依赖 ——
  OTel SDK 类型不进契约，后端实现自带其依赖。
- ``emit`` 的非阻塞入队是契约要求而非建议：捕获侧在 ``Session.append``
  的 observer fire 热路径同步调用它，慢于一次入队即违约。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "CHANNEL_LEDGER",
    "CHANNEL_OPS",
    "SEVERITIES",
    "RedactionHook",
    "SessionTelemetryBackend",
    "SessionTelemetrySink",
    "SharingPolicy",
    "TelemetryRecord",
]

CHANNEL_LEDGER: str = "ledger"
"""账本通道：session 日志事件的一对一镜像记录。"""

CHANNEL_OPS: str = "ops"
"""运维通道：无日志归宿的运行期信号（对齐 DSH ``agent-error`` / ``shutdown``）。"""

SEVERITIES: frozenset[str] = frozenset({"info", "warn", "error"})
"""捕获期预映射的告警严重度闭集（对齐 DSH ``SessionTelemetrySeverity``）。"""


@dataclass(frozen=True, slots=True)
class TelemetryRecord:
    """交给后端的一条逻辑记录 —— 捕获契约的全部出站词汇。

    对齐 DSH ``SessionTelemetryRecord``；与其差异：``body`` 收窄为 ``str``
    （LCA 捕获侧以事件 type 为 body；后端序列化无需任意值域），
    ``attributes`` 保持最小身份属性集（``session.id`` / ``event.type`` /
    ``event.seq``），可从 body 恢复的事实不在此重复。

    - ``channel`` — ``"ledger"``（日志镜像）或 ``"ops"``（运维信号）
    - ``time`` — Unix epoch 毫秒；账本记录取源事件 append 时刻
    - ``severity`` — ``"info"`` / ``"warn"`` / ``"error"`` 之一
    - ``attributes`` — 最小身份属性；交付后不得变更
    - ``body`` — 完整载荷的字符串形态；交付后不得变更
    """

    channel: str
    time: int
    severity: str
    attributes: Mapping[str, Any]
    body: str


class SharingPolicy(StrEnum):
    """部署选定的会话共享策略 —— 披露面词汇（对齐 DSH sharing status）。

    每个后端必须披露其策略；消费面只在无遥测服务装载时渲染
    「未配置」。词汇归本缝所有，披露与具体后端解耦。
    """

    FULL = "full"
    FEEDBACK_ONLY = "feedback_only"
    DISABLED = "disabled"


@runtime_checkable
class SessionTelemetrySink(Protocol):
    """协调器要求的最小后端契约（对齐 DSH ``SessionTelemetrySink``）。

    三成员语义：

    - ``emit`` 必须是一次非阻塞入队 —— 协调器在 ``Session.append`` 热路径
      或显式 canonical 日志捕获中同步调用它；慢于入队即拖垮 agent 循环。
      此处抛错由协调器 contained，永不回灌日志。
    - ``flush`` 是可选的轮次结束提示；缺省空实现，多数后端应让自身
      批处理节奏决定导出时机（DSH OTel 后端正是因此不实现它）。
    - ``shutdown`` 排空至静止：此前已 ``emit`` 的记录必须仍被投递；
      失败由协调器记 warning，不让应用停机失败。
    """

    def emit(self, record: TelemetryRecord) -> None:
        """把一条记录交给后端管线；调用后记录归后端所有。"""
        ...

    def flush(self) -> None:
        """可选的排空提示；缺省空实现（不阻塞、不应抛错）。"""

    def shutdown(self) -> None:
        """排空队列至静止；返回时后端管线已静止。"""
        ...


@runtime_checkable
class SessionTelemetryBackend(SessionTelemetrySink, Protocol):
    """服务注册形态的后端契约：sink 语义 + 共享策略披露。

    ``sharing`` 是只读属性：部署选定的会话共享策略，供反馈确认等
    披露面展示；消费者据此渲染当前策略（而非投递/保留承诺）。
    """

    @property
    def sharing(self) -> SharingPolicy:
        """部署选定的共享策略；词汇归 :class:`SharingPolicy`。"""
        ...


RedactionHook = Callable[[TelemetryRecord], TelemetryRecord | None]
"""脱敏钩子：出站前变换记录。

返回变换后的记录（不得原地变更入参）；返回 ``None`` 或抛错 = 扣下
该条记录（fail-closed），其余记录不受影响。钩子只对导出副本生效，
canonical 日志永不被改写。
"""
