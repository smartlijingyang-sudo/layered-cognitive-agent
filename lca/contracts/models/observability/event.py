"""运行事件账本的最小元模型。

事件账本保存运行期间可复查的记录；业务事实、结构性生命周期和运行解释
共享同一个不可变封套。领域 payload 保持在各自模型中，元模型只声明事件
如何被分类、治理和投影。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from lca.contracts.models.observability.journal import JournalEvent


class EventPlane(str, Enum):
    """事件在账本中的语义平面。"""

    SURFACE = "surface"
    """模型或用户可见的输入、输出、工具结果与上下文。"""

    STRUCTURAL = "structural"
    """run、turn、step、调用和协作的生命周期边界。"""

    EXPLANATION = "explanation"
    """插件、Hook、适配器与传输如何完成一次运行的解释记录。"""


class EventAudience(str, Enum):
    """投影读取事件的最低许可受众。"""

    END_USER = "end_user"
    OPERATOR = "operator"
    AUDITOR = "auditor"
    RESTRICTED = "restricted"


class EventSensitivity(str, Enum):
    """事件 payload 的数据敏感等级。"""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"


class EventDurability(str, Enum):
    """账本在资源压力下对事件的持久化承诺。"""

    REQUIRED = "required"
    BEST_EFFORT = "best_effort"


class RuntimeKind(str, Enum):
    """运行解释事件的稳定对象域。"""

    AGENT = "agent"
    PLUGIN = "plugin"
    HOOK = "hook"
    LLM = "llm"
    TOOL = "tool"
    MEMORY = "memory"
    TRANSPORT = "transport"
    CODE = "code"
    PERMISSION = "permission"
    COMPACTION = "compaction"
    ERROR = "error"
    RETRY = "retry"


class OperationOutcome(str, Enum):
    """一次可测操作的结果。"""

    STARTED = "started"
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"
    RETRY = "retry"


@dataclass(frozen=True)
class EventDescriptor:
    """事件类型的唯一注册描述（ADR-0063 PR-7 source inversion 后的单一源）。

    描述符把分类、持久化、可见性、安全治理、领域归属与唯一发射边界放在
    同一注册表中；投影器只能读取描述符，不能自行解释相同的策略。
    """

    type_name: str
    plane: EventPlane
    domain: str
    emitter: str
    durability: EventDurability
    audience: EventAudience
    sensitivity: EventSensitivity
    retention: str = "default"
    required: tuple[str, ...] = ()
    description: str = ""
    otel_kind: Literal["agent", "generation", "tool", "span", "event"] = "event"
    payload_class: type["JournalEvent"] | None = None
    """领域 payload 类；反序列化和 ``EventDescriptor`` 校验依赖此绑定。"""
    extra: Mapping[str, Any] = field(default_factory=dict)
    """插件可扩展字段（不破坏核心元数据）。"""


__all__ = [
    "EventAudience",
    "EventDescriptor",
    "EventDurability",
    "EventPlane",
    "EventSensitivity",
    "OperationOutcome",
    "RuntimeKind",
]
