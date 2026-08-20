"""全部 49 个事件 EventDescriptor 描述符的单一源声明（ADR-0063 PR-7）。

每个事件类对应一个 ``EventDescriptor``：把 domain / emitter / 必备字段
（来自旧 ``JOURNAL_CATALOG``）与 durability / audience / sensitivity /
retention_class（来自旧 ``JOURNAL_CATALOG_META``）合在同一个 dataclass 里。

新增事件 = journal.py 一个 frozen dataclass + 本文件一行 ``_descriptor(...)`` +
``build_default_registry()`` 末尾追加（无需新建表）；CI 守卫由
``tests/test_observability_boundary.py`` 覆盖。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from lca.contracts.models.observability.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventPlane,
    EventSensitivity,
)
from lca.contracts.models.observability.journal import (
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
    ApprovalRequested,
    ApprovalResolved,
    AttachmentStagingCompleted,
    AttachmentStagingFailed,
    AttachmentStagingStarted,
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    ContextCompacted,
    ContextManifested,
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    GateDecided,
    InboxFollowupCreated,
    LlmCallCompleted,
    LlmCallStarted,
    MemoryCommitted,
    PerceptionMerged,
    ReasoningCompleted,
    ReasoningDelta,
    RunActivity,
    RunPaused,
    RunResumed,
    RuntimeObserved,
    SandboxOutputDelta,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    TeamMessagePublished,
    TeamRunFinished,
    TeamRunStarted,
    ToolCallStreaming,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.contracts.models.observability.telemetry_catalog import VocabDomain
from lca.layer0_infra.observability.event_descriptor_registry import (
    InMemoryEventDescriptorRegistry,
)

if TYPE_CHECKING:
    pass


def _descriptor(
    cls: type,
    *,
    domain: VocabDomain,
    emitter: str,
    required: tuple[str, ...] = (),
    description: str,
    durability: str,
    audience: str,
    sensitivity: str,
    retention: str = "default",
    plane: str | None = None,
) -> EventDescriptor:
    return EventDescriptor(
        type_name=cls.__name__,
        domain=domain.value,
        emitter=emitter,
        plane=EventPlane(plane or _plane(cls.__name__)),
        durability=EventDurability(durability),
        audience=EventAudience(audience),
        sensitivity=EventSensitivity(sensitivity),
        retention=retention,
        required=required,
        description=description,
        otel_kind=_otel_kind(cls.__name__),  # type: ignore[arg-type]
        payload_class=cls,
    )


def _plane(type_name: str) -> str:
    if type_name == "RuntimeObserved":
        return "explanation"
    if type_name in _SURFACE:
        return "surface"
    return "structural"


def _otel_kind(type_name: str) -> str:
    if type_name in {"AgentRunStarted", "AgentRunFinished", "TeamRunStarted", "TeamRunFinished"}:
        return "agent"
    if type_name == "LlmCallCompleted":
        return "generation"
    if type_name in {"ToolStarted", "ToolInvoked", "ToolDenied"}:
        return "tool"
    return "event"


_SURFACE: frozenset[str] = frozenset(
    {
        "StepTextDelta",
        "ReasoningDelta",
        "SandboxOutputDelta",
        "ToolCallStreaming",
        "ToolInvoked",
        "InboxFollowupCreated",
        "TeamMessagePublished",
        "ContextManifested",
    }
)


def build_default_registry() -> InMemoryEventDescriptorRegistry:
    """返回包含全部内置事件描述符的注册中心。

    启动期 bootstrap：``EVENT_DESCRIPTOR_REGISTRY = build_default_registry()``。
    插件可在 boot 后追加自定义描述符；重复登记默认抛错。
    """
    descriptors: list[EventDescriptor] = [
        # ── 容器事件 ──
        _descriptor(
            TeamRunStarted,
            domain=VocabDomain.RUN,
            emitter="lca.layer3_agent.team_handle",
            description="团队 run 开启（场景卡）",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            TeamRunFinished,
            domain=VocabDomain.RUN,
            emitter="lca.layer3_agent.team_handle",
            required=("status",),
            description="团队 run 关闭",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            AgentRunStarted,
            domain=VocabDomain.RUN,
            emitter="lca.layer3_agent.cognitive_agent",
            required=("agent_role",),
            description="agent run 开启",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            AgentRunFinished,
            domain=VocabDomain.RUN,
            emitter="lca.layer3_agent.cognitive_agent",
            required=("status",),
            description="agent run 关闭",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        # ── 选角 ──
        _descriptor(
            CastingStarted,
            domain=VocabDomain.TEAM,
            emitter="gateway.assemble",
            required=("objective_preview",),
            description="自动组队选角开始",
            durability="best_effort",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            CastingCompleted,
            domain=VocabDomain.TEAM,
            emitter="gateway.assemble",
            required=("governance_kind",),
            description="自动组队选角完成",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            CastingFailed,
            domain=VocabDomain.TEAM,
            emitter="gateway.assemble",
            required=("error",),
            description="自动组队选角失败",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        # ── 协作 ──
        _descriptor(
            DelegationIssued,
            domain=VocabDomain.TEAM,
            emitter="lca.layer0_infra.transport.invocation",
            required=("delegation_id", "callee_role"),
            description="委派发起（一等公民）",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            DelegationCompleted,
            domain=VocabDomain.TEAM,
            emitter="lca.layer0_infra.transport.invocation",
            required=("delegation_id",),
            description="委派回执",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            DelegationCacheHit,
            domain=VocabDomain.TEAM,
            emitter="lca.layer1_cognitive.body.delegation_cache",
            required=("callee_role",),
            description="委派幂等短路",
            durability="best_effort",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            SynthesisCompleted,
            domain=VocabDomain.TEAM,
            emitter="lca.layer1_cognitive.body.action_handlers",
            description="收口综合完成",
            durability="required",
            audience="operator",
            sensitivity="internal",
        ),
        # ── 认知事实 ──
        _descriptor(
            DecisionMade,
            domain=VocabDomain.EVENT,
            emitter="lca.layer1_cognitive.body.action_handlers",
            required=("action_type",),
            description="决策事实",
            durability="required",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            StepCompleted,
            domain=VocabDomain.EVENT,
            emitter="lca.layer2_runtime.event_emission",
            required=("step",),
            description="步完成",
            durability="best_effort",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            ActionDegraded,
            domain=VocabDomain.EVENT,
            emitter="lca.layer2_runtime.event_emission",
            description="动作降级",
            durability="required",
            audience="operator",
            sensitivity="internal",
        ),
        # ── 资源事实（高压增量 — best_effort）──
        _descriptor(
            StepTextDelta,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer0_infra.observability.adapters",
            required=("step", "seq"),
            description="认知步 LLM 增量文本（中性）",
            durability="best_effort",
            audience="end_user",
            sensitivity="public",
            retention="short",
        ),
        _descriptor(
            ReasoningDelta,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer0_infra.observability.adapters",
            required=("step", "seq"),
            description="模型思维链增量",
            durability="best_effort",
            audience="restricted",
            sensitivity="confidential",
            retention="short",
        ),
        _descriptor(
            ReasoningCompleted,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer0_infra.observability.adapters",
            required=("step",),
            description="模型思维链段结束",
            durability="best_effort",
            audience="restricted",
            sensitivity="confidential",
            retention="short",
        ),
        _descriptor(
            RunActivity,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer0_infra.observability",
            required=("phase",),
            description="Run 级活动心跳",
            durability="best_effort",
            audience="end_user",
            sensitivity="public",
            retention="short",
        ),
        _descriptor(
            SandboxOutputDelta,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer0_infra.sandbox",
            required=("invocation_id", "stream", "seq"),
            description="沙箱执行增量输出（stdout/stderr）",
            durability="best_effort",
            audience="end_user",
            sensitivity="public",
            retention="short",
        ),
        # ── 资源事实（关键 — required）──
        _descriptor(
            LlmCallStarted,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer0_infra.observability.adapters",
            required=("step",),
            description="LLM 调用开始",
            durability="best_effort",
            audience="operator",
            sensitivity="internal",
            retention="short",
        ),
        _descriptor(
            LlmCallCompleted,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer0_infra.observability.adapters",
            required=("model",),
            description="LLM 调用完成",
            durability="required",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            ToolCallStreaming,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer1_cognitive.brain.llm_turn.executor",
            required=("tool_name",),
            description="LLM 正在流式生成工具调用参数（早期卡片占位，消除思考→执行空白期）",
            durability="best_effort",
            audience="end_user",
            sensitivity="public",
            retention="short",
        ),
        _descriptor(
            ToolStarted,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer1_cognitive.body.tool_journal_emit",
            required=("tool_name", "invocation_id"),
            description="工具调用开始；plugin_state 为 UI 完整初始态（code/command）",
            durability="required",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            ToolInvoked,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer1_cognitive.body.tool_journal_emit",
            required=("tool_name",),
            description="工具调用完成；plugin_state/files 为 UI 一等字段（不截断）",
            durability="required",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            ToolDenied,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer1_cognitive.body.tool_journal_emit",
            required=("tool_name",),
            description="工具调用被拒",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        # ── 附件暂存 ──
        _descriptor(
            AttachmentStagingStarted,
            domain=VocabDomain.RESOURCE,
            emitter="gateway.runs.execute",
            required=("plane_id", "file_count"),
            description="附件暂存开始（host → machine bootstrap channel）",
            durability="best_effort",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            AttachmentStagingCompleted,
            domain=VocabDomain.RESOURCE,
            emitter="gateway.runs.execute",
            required=("plane_id", "file_count"),
            description="附件暂存完成",
            durability="best_effort",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            AttachmentStagingFailed,
            domain=VocabDomain.RESOURCE,
            emitter="gateway.runs.execute",
            required=("plane_id", "error"),
            description="附件暂存失败（路径拒绝、传输超时、IO 错误）",
            durability="required",
            audience="operator",
            sensitivity="internal",
        ),
        # ── 运行解释（替代 RunInsight）──
        _descriptor(
            RuntimeObserved,
            domain=VocabDomain.RESOURCE,
            emitter="lca.layer0_infra.observability.facade",
            required=("operation", "source"),
            description="插件、Hook、适配器与传输的运行解释记录",
            durability="best_effort",
            audience="operator",
            sensitivity="internal",
            retention="short",
        ),
        # ── 控制原语 (PR2 / PR3a / PR4 / PR6 / PR7 / PR8 / PR9) ──
        _descriptor(
            ContextManifested,
            domain=VocabDomain.EVENT,
            emitter="lca.layer1_cognitive.brain.context_manifest",
            required=("digest",),
            description="PerceiveHub 一次性发出当 step 的 ContextManifest",
            durability="required",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            PerceptionMerged,
            domain=VocabDomain.EVENT,
            emitter="lca.layer1_cognitive.perceive_hub",
            required=("delta_ref",),
            description="Hub fold 终态",
            durability="required",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            GateDecided,
            domain=VocabDomain.EVENT,
            emitter="lca.layer1_cognitive.brain.decision_gates",
            required=("gate", "verdict"),
            description="DecisionGate 裁决（warn/rewrite/deny）",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            InboxFollowupCreated,
            domain=VocabDomain.EVENT,
            emitter="lca.harness.session",
            required=("inbox_id",),
            description="用户输入经 Inbox 注入",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            TeamMessagePublished,
            domain=VocabDomain.EVENT,
            emitter="lca.layer3_agent.team_handle",
            required=("team_id", "thread_id"),
            description="Team 消息发布（每 Team 一个 topic）",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            ApprovalRequested,
            domain=VocabDomain.EVENT,
            emitter="lca.layer1_cognitive.body.safe_executor",
            required=("envelope_id", "tool_name"),
            description="执行信封触发审批",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            ApprovalResolved,
            domain=VocabDomain.EVENT,
            emitter="lca.layer1_cognitive.body.safe_executor",
            required=("envelope_id",),
            description="审批决议",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            MemoryCommitted,
            domain=VocabDomain.EVENT,
            emitter="lca.layer1_cognitive.memory.simple_memory",
            required=("layer", "record_id"),
            description="记忆提交",
            durability="best_effort",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            ContextCompacted,
            domain=VocabDomain.EVENT,
            emitter="lca.layer1_cognitive.memory.simple_memory",
            required=("step",),
            description="影子 CompactionPolicy 应用",
            durability="best_effort",
            audience="operator",
            sensitivity="internal",
        ),
        _descriptor(
            RunPaused,
            domain=VocabDomain.EVENT,
            emitter="lca.layer2_runtime.runtime_loop",
            required=("step", "reason"),
            description="Run 暂停（人工审批等）",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
        _descriptor(
            RunResumed,
            domain=VocabDomain.EVENT,
            emitter="lca.layer2_runtime.runtime_loop",
            required=("step", "reason"),
            description="Run 恢复",
            durability="required",
            audience="auditor",
            sensitivity="internal",
        ),
    ]
    return InMemoryEventDescriptorRegistry(descriptors)


def all_builtin_event_classes() -> Iterable[type]:
    """所有内置事件的 payload 类（与 ``JOURNAL_EVENT_CLASSES`` 等价）。"""
    for descriptor in build_default_registry().all():
        if descriptor.payload_class is not None:
            yield descriptor.payload_class