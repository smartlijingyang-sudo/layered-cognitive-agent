"""领域枚举集中定义 —— 消除裸字符串字面量。

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


class DecisionGateName(str, Enum):
    """内置收尾策略名称（registry 键；由 LeadMandate 展开，非用户旋钮）。"""

    MUST_CONSULT_ALL = "must_consult_all"
    NONE = "none"


class StreamChannel(str, Enum):
    """StepTextDelta 可见性通道（ADR-0051 Phase 2）。"""

    DECISION = "decision"
    ANSWER = "answer"


class RunActivityPhase(str, Enum):
    """Run 级活动相位 — SSE 心跳 / 进度条（ADR-0051 Phase 2）。"""

    LLM_THINKING = "llm_thinking"
    TOOL_RUNNING = "tool_running"
    SANDBOX_EXEC = "sandbox_exec"


class ActionScope(str, Enum):
    """Which built-in actions a Body may execute (construction-time closed set)."""

    SOLO = "solo"
    MEMBER = "member"
    LEAD = "lead"


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
    """团队委派进度状态。

    ``DONE_PARTIAL``：已收获可用部分证据并终止重试（证据平面 usable，
    控制面终态；与 FAILED 不同——该视角并非完全缺失）。
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    DONE_PARTIAL = "done_partial"
    FAILED = "failed"


class MemoryLayer(str, Enum):
    """多级记忆层级（CoALA 分类）。"""

    WORKING = "working"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


SHAREABLE_LAYERS: frozenset[MemoryLayer] = frozenset({MemoryLayer.SEMANTIC, MemoryLayer.PROCEDURAL})
"""只有 semantic / procedural 两层可跨 Agent 共享（CoALA 语义边界）。"""


class MemoryRecordKind(str, Enum):
    """记忆记录语义分类——观察写入记忆时的类型化标记。

    此前成员委派返回 / 工具结果 / 自身回复都被压扁成 ``TOOL_RESULT:`` 字符串，
    丢失归属。此枚举让写入侧声明语义、渲染侧按类分派，委派结果以
    ``DelegationResult`` 一等事实进入监督者 prompt。
    """

    GENERIC = "generic"
    TOOL_RESULT = "tool_result"
    DELEGATION_RESULT = "delegation_result"
    RESPONSE = "response"


class LLMStreamEventType(str, Enum):
    """LLM 流式事件类型 —— 值与 OpenAI Responses SSE ``type`` 字符串对齐。"""

    OUTPUT_TEXT_DELTA = "response.output_text.delta"
    REASONING_TEXT_DELTA = "response.reasoning_text.delta"
    FUNCTION_CALL_ARGUMENTS_DELTA = "response.function_call_arguments.delta"
    COMPLETED = "response.completed"


class FinishReason(str, Enum):
    """LLM 生成结束原因 —— 归一化各 provider 的 finish/stop/status 信号。

    ``LENGTH`` 表示输出被 max_tokens 截断；与 tool_call 并存时，
    tool arguments 必须视为 **incomplete**（ADR-0047），禁止当完整调用执行。
    """

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
    UNKNOWN = "unknown"


class ComponentKind(str, Enum):
    """组件注册表分类键 —— 值域有限，适用契约 1（值域即类型）。

    对应 ComponentRegistryProtocol.register(category, name, impl) 中的
    category 参数。name 由所属领域的 profile 选择规则定义；注册表只承载
    当前仍需按类别发现的基础设施与策略实现。
    """

    OBSERVABILITY = "observability"
    STATE_STORE = "state_store"
    MEMORY = "memory"
    EVENT_BUS = "event_bus"
    BUDGET_POLICY = "budget_policy"
