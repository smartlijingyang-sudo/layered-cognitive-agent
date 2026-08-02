"""领域枚举集中定义 —— 消除裸字符串字面量（ADR-0017）。

所有 str Enum 值与原始字符串一致，保证序列化 / 反序列化兼容。
比较时 ``ActionType.RESPOND == "respond"`` 为 True（str Enum 特性）。
"""

from __future__ import annotations

from enum import Enum


class ActionType(str, Enum):
    """Agent 决策行动类型。"""

    RESPOND = "respond"
    USE_TOOL = "use_tool"
    DELEGATE = "delegate"
    HANDOFF = "handoff"
    STOP = "stop"
    ASK_HUMAN = "ask_human"


class TeamProcess(str, Enum):
    """团队编排模式。"""

    HIERARCHICAL = "hierarchical"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    GRAPH = "graph"
    DEBATE = "debate"
    HANDOFF = "handoff"


class DecisionGateName(str, Enum):
    """内置收尾策略名称。"""

    MUST_CONSULT_ALL = "must_consult_all"
    NONE = "none"


class HookEvent(str, Enum):
    """认知循环生命周期钩子事件名。"""

    ON_START = "on_start"
    PRE_PERCEIVE = "pre_perceive"
    POST_PERCEIVE = "post_perceive"
    PRE_THINK = "pre_think"
    POST_THINK = "post_think"
    PRE_ACT = "pre_act"
    POST_ACT = "post_act"
    PRE_REFLECT = "pre_reflect"
    POST_REFLECT = "post_reflect"
    ON_ERROR = "on_error"
    ON_PAUSE = "on_pause"
    ON_COMPLETE = "on_complete"


class SpanStatus(str, Enum):
    """TraceSpan 执行状态。"""

    OK = "ok"
    ERROR = "error"


class SnapshotReason(str, Enum):
    """StateSnapshot 快照触发原因。"""

    PERIODIC = "periodic"
    PRE_APPROVAL = "pre_approval"
    MANUAL = "manual"
    ON_ERROR = "on_error"


class DelegationProtocol(str, Enum):
    """委派传输协议。"""

    INTERNAL = "internal"
    A2A = "a2a"
    MCP = "mcp"


class ContentType(str, Enum):
    """Observation 载荷内容类型。"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    STRUCTURED = "structured"


class ReflectionVerdict(str, Enum):
    """自省判定结果。"""

    ON_TRACK = "on_track"
    NEEDS_CORRECTION = "needs_correction"
    BLOCKED = "blocked"
    DEGRADED_BUT_COMPLETED = "degraded_but_completed"


class MessageKind(str, Enum):
    """AgentMessage Part 种类。"""

    TEXT = "text"
    DATA = "data"
    FILE = "file"


class MessageRole(str, Enum):
    """消息发送方角色。"""

    USER = "user"
    AGENT = "agent"


class RoleStatus(str, Enum):
    """团队委派进度状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class MemoryLayer(str, Enum):
    """多级记忆层级（CoALA 分类）。"""

    WORKING = "working"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


SHAREABLE_LAYERS: frozenset[MemoryLayer] = frozenset({MemoryLayer.SEMANTIC, MemoryLayer.PROCEDURAL})
"""只有 semantic / procedural 两层可跨 Agent 共享（CoALA 语义边界）。"""


class ComponentKind(str, Enum):
    """组件注册表分类键 —— 值域有限，适用契约 1（值域即类型）。

    对应 ComponentRegistryProtocol.register(category, name, impl) 中的
    category 参数。name 参数视情况使用已有枚举（如 DecisionGateName）
    或保留字符串（如角色名，来自配置）。
    """

    OBSERVABILITY = "observability"
    STATE_STORE = "state_store"
    MEMORY = "memory"
    EVENT_BUS = "event_bus"
    MEMBER_STATUS = "member_status"
    DECISION_GATE = "decision_gate"
    BUDGET_POLICY = "budget_policy"


class RoleMode(str, Enum):
    """Agent 在团队中的角色模式 —— 决定 prompt 模板和队友信息渲染。"""

    SOLO = "solo"
    SUPERVISOR = "supervisor"
    MEMBER = "member"
