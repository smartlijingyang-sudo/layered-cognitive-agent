"""执行日志（journal）词表 —— 叙事平面事件的单一事实源（ADR-0037）。

Journal-as-Truth：协作运行时的语义边界发射 ``JournalEvent``，span 树只是
日志的一个投影。本模块定义：

- **关联骨架** ``RunScope``：trace_id / run_id / parent_run_id /
  delegation_id / agent_role —— 父子关系由显式 ID 构造，不依赖 ambient
  OTel context（0 秒化石 span 与错挂父子链在构造上不可能）。
- **事件词表**：容器事件（Team/Agent run 开闭）、协作事件（Delegation
  一等公民 + Synthesis 收口）、资源事实（Llm/Tool/Step/Decision）、
  洞察由只读 TraceInspector 从事件账本派生，不回写事实流。

事件是纯 frozen dataclass（ADR-0015）；关联骨架不在事件本体上——由引擎在
record 时盖章进 ``StampedEvent.scope``，事件字段只承载领域语义。
发射点登记与守卫见 ``journal_catalog.py``；事件经包根 ``record(...)`` 发射。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from importlib import import_module
from typing import Any, Literal

from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.models.observability.event import OperationOutcome, RuntimeKind
from lca.contracts.observability.evidence import (
    EvidenceRef,
)
from lca.contracts.observability.evidence import (
    EvidenceRef as _EvidenceRef,  # alias for JournalRecord.evidence compat
)

# ── 关联骨架 ─────────────────────────────────────────────


@dataclass(frozen=True)
class RunScope:
    """当前 run 的关联身份（journal 事件的关联骨架）。

    - ``run_id``：一个 agent run 容器的 id（团队根、lead、成员各一个）；
    - ``parent_run_id``：生成此 run 的 run id（根为 None）；
    - ``delegation_id``：生成此 run 的委派 id（无则 None）；
    - ``agent_role``：当前 run 的角色（委派发射点用作 caller_role）。

    品牌化 ID：trace_id/run_id 在类型层面不可互换，
    防止关联骨架 ID 混传。运行时零成本。
    """

    trace_id: TraceId = ""  # type: ignore[assignment]
    run_id: RunId = ""  # type: ignore[assignment]
    parent_run_id: RunId | None = None
    parent_trace_id: TraceId | None = None
    delegation_id: str | None = None
    agent_role: str = ""
    # Per-step counter inside the agent loop turn; sensors use it to
    # bound re-reads (e.g. only events at step >= N).
    step: int = 0


# ── 事件基类与盖章记录 ──────────────────────────────────


@dataclass(frozen=True)
class JournalEvent:
    """journal 事件基类（纯标记；领域字段在子类，关联骨架在 StampedEvent）。"""


@dataclass(frozen=True)
class RuntimeObserved(JournalEvent):
    """插件和运行边界的解释记录。

    此事件不改变领域状态，也不参与 reducer；它与事实和生命周期事件共享
    ``StampedEvent`` 的序列和因果链，因而可由 Agent 在同一轨迹中解释插件、
    Hook、LLM、工具、传输、权限和代码执行行为。``operation`` 使用稳定的
    点分命名，例如 ``plugin.interaction``、``context.injected`` 或
    ``transport.receive``。
    """

    kind: RuntimeKind = RuntimeKind.PLUGIN
    operation: str = ""
    source: str = ""
    outcome: OperationOutcome = OperationOutcome.OK
    duration_ms: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    retryable: bool = False
    causation_refs: tuple[int, ...] = ()


@dataclass(frozen=True)
class StampedEvent:
    """引擎盖章后的日志记录：序号 + 时间戳 + 关联骨架 + 事件本体。

    Spec §24.5 / Phase J + ADR-0074 PR-6: every stamped event carries:

    - ``seq``  — sequential log index (ADR-0055 N2)
    - ``ts``   — monotonic timestamp
    - ``scope`` — correlation skeleton (trace_id / parent_trace_id / run_id /
      delegation_id / agent_role / step)
    - ``plan_ref`` — CompiledRunPlan canonical hash (PR-6 V5); auto-stamped
      from ``lca_run_plan_ref`` ContextVar at append time. Empty string
      ``""`` for legacy code paths without plan binding (tests, projector
      previews). V5 acceptance: replay test 守护每条 fact 携带 plan_ref。
    - ``event_type`` — class name of the payload (auto-stamped by ``RunStore.append``)
    - ``data``  — optional dict carrying the raw payload for downstream
      consumers (mirrors ``event.__dict__``; auto-populated when the engine
      stamps it).
    - ``parent_seq`` — immediate causal parent seq (None for root events).
    - ``correlation_ids`` — reserved for future multi-trace joining; never written.
    - ``event`` — the typed payload (frozen dataclass).
    - ``event_id`` — global unique id (ADR-0065 §三 / L3); computed by engine
      at append time, propagated to ``JournalRecord.event_id`` in the v2
      envelope. ``""`` for events constructed outside the ledger (tests,
      projector previews).
    - ``parent_event_id`` — global id of the immediate causal parent
      (ADR-0065 §三 / causation); engine looks up from seq→event_id map at
      append. ``""`` for root events or pre-flip replays.
    """

    seq: int
    ts: float
    scope: RunScope
    event: JournalEvent
    event_type: str = ""
    data: dict[str, object] = field(default_factory=dict)
    parent_seq: int | None = None
    correlation_ids: tuple[str, ...] = ()
    event_id: str = ""
    parent_event_id: str = ""
    plan_ref: str = ""
    """CompiledRunPlan canonical hash (PR-6 V5)；auto-stamped by RunStore."""


class DelegationMechanism(str, Enum):
    """委派发起机制（封闭词表）。"""

    DELEGATE = "delegate"
    """lead 决策驱动（Decision.delegations，阻塞等待回执）。"""
    HANDOFF = "handoff"
    """非阻塞控制权移交（发完即返回）。"""
    MEMBER_INVOKE = "member_invoke"
    """编排策略驱动（Pipeline/FanOut/Debate 等经 MemberInvoker）。"""


# ── 容器事件（run 开闭 + 场景卡）────────────────────────


@dataclass(frozen=True)
class TeamRunStarted(JournalEvent):
    """团队 run 容器开启（兼场景卡：成员/mandate/计划一步到位）。"""

    team_id: str = ""
    strategy_key: str = ""
    mandate: str = ""
    lead_role: str = ""
    members: tuple[str, ...] = ()
    objective: str = ""
    objective_preview: str = ""
    plan_steps: str = ""


@dataclass(frozen=True)
class TeamRunFinished(JournalEvent):
    """团队 run 容器关闭；投影器和轨迹检查器据此完成其只读视图。"""

    status: str = ""
    output_text: str = field(default="", metadata={"journal_kind": "content"})
    output_truncated: bool = False
    steps: int = 0
    error: str = ""


@dataclass(frozen=True)
class CastingStarted(JournalEvent):
    """自动组队选角开始（auto 模式在 Team 编译前的一次 LLM 调用）。"""

    objective_preview: str = ""


@dataclass(frozen=True)
class CastingCompleted(JournalEvent):
    """自动组队选角完成 —— 白名单校验后的 CastingPlan 快照（可回放）。"""

    governance_kind: str = ""
    lead_role: str = ""
    selected_roles: tuple[str, ...] = ()
    rationale: str = field(default="", metadata={"journal_kind": "content"})


@dataclass(frozen=True)
class CastingFailed(JournalEvent):
    """自动组队选角失败（解析/白名单/重试耗尽）。"""

    error: str = ""


@dataclass(frozen=True)
class AgentRunStarted(JournalEvent):
    """agent run 容器开启（根 run 时兼 solo 场景卡）。"""

    agent_role: str = ""
    strategy_key: str = ""
    objective: str = ""
    objective_preview: str = ""
    from_role: str = ""


@dataclass(frozen=True)
class AgentRunFinished(JournalEvent):
    """agent run 容器关闭。"""

    status: str = ""
    output_text: str = field(default="", metadata={"journal_kind": "content"})
    output_truncated: bool = False
    steps: int = 0
    error: str = ""


# ── 协作事件（委派 / 综合 —— 一等公民）──────────────────


@dataclass(frozen=True)
class DelegationIssued(JournalEvent):
    """委派发起：协作叙事的核心动作（span 投影包住成员全程）。"""

    delegation_id: str = ""
    caller_role: str = ""
    callee_role: str = ""
    subtask_preview: str = ""
    mechanism: DelegationMechanism = DelegationMechanism.DELEGATE
    parallel_group: str = ""


@dataclass(frozen=True)
class DelegationCompleted(JournalEvent):
    """委派回执到达。"""

    delegation_id: str = ""
    ok: bool = True
    status: str = ""
    output_text: str = field(default="", metadata={"journal_kind": "content"})
    output_truncated: bool = False
    task_id: str = ""


@dataclass(frozen=True)
class DelegationCacheHit(JournalEvent):
    """委派幂等短路（无传输往返）。"""

    callee_role: str = ""
    subtask_preview: str = ""
    step: int = 0


@dataclass(frozen=True)
class SynthesisCompleted(JournalEvent):
    """收口综合完成（board mandate 下 lead 汇总全员意见产出终版）。"""

    method: str = ""
    candidate_count: int = 0
    output_text: str = field(default="", metadata={"journal_kind": "content"})
    output_truncated: bool = False


# ── 认知事实（决策 / 步 / 降级）─────────────────────────


@dataclass(frozen=True)
class DecisionMade(JournalEvent):
    """决策事实（think 相位产出）。

    ``response_text`` 为防腐层归一后的用户可见正文（仅终态 respond 等有值）；
    投影层提交对话主线时以此为权威源（ADR-0045），勿再解析原始 LLM JSON。
    """

    step: int = 0
    action_type: str = ""
    rationale_preview: str = ""
    delegate_target: str = ""
    delegate_count: int = 0
    tool_name: str = ""
    confidence: float = 0.0
    response_text: str = field(default="", metadata={"journal_kind": "content"})
    output_truncated: bool = False


@dataclass(frozen=True)
class StepCompleted(JournalEvent):
    """步生命周期完成（reflect 之后）。"""

    step: int = 0
    status: str = ""
    action_type: str = ""


@dataclass(frozen=True)
class ActionDegraded(JournalEvent):
    """动作降级（原动作不可执行 → 改写）。"""

    original_action_type: str = ""
    degraded_to: str = ""
    step: int = 0


# ── 资源事实（LLM / 工具）───────────────────────────────


@dataclass(frozen=True)
class StepTextDelta(JournalEvent):
    """某认知步 LLM 生成的原始增量文本（中性，不预判终态归属）。"""

    step: int = 0
    text_delta: str = field(default="", metadata={"journal_kind": "content"})
    seq: int = 0
    channel: str = "decision"  # StreamChannel: decision | answer


@dataclass(frozen=True)
class LlmCallStarted(JournalEvent):
    """LLM 调用开始 — 供 SSE 活动心跳锚点（ADR-0051 Phase 2）。"""

    step: int = 0
    model: str = ""


@dataclass(frozen=True)
class RunActivity(JournalEvent):
    """Run 级活动心跳 — LLM 等待 / 工具执行中的进度信号。"""

    phase: str = ""  # RunActivityPhase value
    step: int = 0
    detail: str = ""
    seq: int = 0


@dataclass(frozen=True)
class ReasoningDelta(JournalEvent):
    """模型思维链/reasoning 增量（与 StepTextDelta 分离，供 Thinking 面板投影）。"""

    step: int = 0
    text_delta: str = field(default="", metadata={"journal_kind": "content"})
    seq: int = 0


@dataclass(frozen=True)
class ReasoningCompleted(JournalEvent):
    """单次 LLM 调用的 reasoning 段结束（携带累计时长，供「已深度思考」标题）。"""

    step: int = 0
    duration_ms: int = 0
    content_preview: str = field(default="", metadata={"journal_kind": "content"})


@dataclass(frozen=True)
class SandboxOutputDelta(JournalEvent):
    """沙箱执行期的原始增量输出行（stdout/stderr 各自成流，seq 跨流全局单调）。"""

    invocation_id: str = ""
    stream: str = "stdout"  # "stdout" | "stderr"
    text_delta: str = field(default="", metadata={"journal_kind": "content"})
    seq: int = 0


@dataclass(frozen=True)
class LlmCallCompleted(JournalEvent):
    """LLM 调用完成（OTel 投影为 generation，gen_ai 语义约定）。"""

    model: str = ""
    ok: bool = True
    latency_ms: int = 0
    prompt_preview: str = ""
    response_preview: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    stream: bool = False


@dataclass(frozen=True)
class ToolCallStreaming(JournalEvent):
    """LLM 正在流式生成工具调用参数（tool call arguments still streaming）。

    在 LLM 响应完成前发出，让前端尽早渲染工具卡片占位——消除思考结束到
    工具执行之间的空白期。与 ``ToolStarted``（执行前、参数完整）互补。
    ``tool_call_id`` 即后续 ToolStarted/Invoked 的 ``invocation_id``（同一张卡）。

    ADR-0065 §四 typed UI state: ``code`` / ``command`` / ``language`` /
    ``skill_id`` 替代 ``plugin_state`` dict 逃逸口;``state_ref`` 指向大对象。
    """

    tool_name: str = ""
    tool_call_id: str = ""
    arguments_preview: str = ""
    # typed UI state (ADR-0065 §四 —— 替代 plugin_state 逃逸口)
    code: str = ""
    language: str = ""
    command: str = ""
    skill_id: str = ""
    skill_inputs: Mapping[str, object] = field(default_factory=dict)
    description: str = ""
    state_ref: EvidenceRef | None = None
    # view-only 字段(emit 时剥离)
    plugin_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolStarted(JournalEvent):
    """工具调用开始（执行前；与 ToolInvoked 经 invocation_id 关联）。

    ADR-0065 §四 typed UI state: ``code`` / ``command`` / ``language`` /
    ``skill_id`` / ``skill_inputs`` / ``description`` / ``execution_env``
    替代 ``plugin_state`` dict 逃逸口;``state_ref`` 指向大对象。

    ``idempotency_key`` (PR6) 由 ExecutionEnvelope 注入；为空表示工具未声明幂等。
    """

    tool_name: str = ""
    arguments_preview: str = ""
    invocation_id: str = ""
    idempotency_key: str = ""
    # typed UI state (ADR-0065 §四 —— 替代 plugin_state 逃逸口)
    code: str = ""
    language: str = ""
    command: str = ""
    skill_id: str = ""
    skill_inputs: Mapping[str, object] = field(default_factory=dict)
    description: str = ""
    execution_env: str = ""
    state_ref: EvidenceRef | None = None
    # view-only 字段(emit 时剥离)
    plugin_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolInvoked(JournalEvent):
    """工具调用完成。

    ADR-0065 §四 typed UI state: ``code`` / ``command`` / ``language`` /
    ``skill_id`` / ``execution_env`` 替代 ``plugin_state`` dict;``files``
    已是 typed 字段。``state_ref`` 指向大 state 对象(EvidenceStore)。
    ``arguments_preview`` / ``result_preview`` / ``plugin_state`` /
    ``output_truncated`` 保留为 view-only,emit 时 journal_io 不写入 disk。

    Live SSE 必须抹掉两个 preview,浏览器不得读到(plugin_state 也需
    在 live SSE 中脱敏——见 sse_frames._LIVE_REDACT_KEYS)。

    ``idempotency_key`` (PR6) 与 ``ToolStarted`` 同步；用于 resume dedupe
    via ``RunStore.find_terminal_tool_invoked``。
    """

    tool_name: str = ""
    ok: bool = True
    latency_ms: int = 0
    attempt: int = 1
    error: str = ""
    invocation_id: str = ""  # optional link to in-flight streaming deltas
    idempotency_key: str = ""
    files: tuple[dict[str, Any], ...] = ()
    # typed UI state (ADR-0065 §四)
    code: str = ""
    language: str = ""
    command: str = ""
    skill_id: str = ""
    skill_inputs: Mapping[str, object] = field(default_factory=dict)
    description: str = ""
    execution_env: str = ""
    state_ref: EvidenceRef | None = None
    # typed 主体 (与 preview 区分)
    output_text: str = ""
    # view-only 字段(emit 时剥离)
    arguments_preview: str = ""
    result_preview: str = ""
    output_truncated: bool = False
    plugin_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolDenied(JournalEvent):
    """工具调用被拒（权限/校验）。"""

    tool_name: str = ""
    reason: str = ""


# ── 基础设施事件（附件暂存 / bootstrap）───────────────────


@dataclass(frozen=True)
class AttachmentStagingStarted(JournalEvent):
    """附件暂存开始（host → machine bootstrap channel）。"""

    plane_id: str = ""
    file_count: int = 0
    total_bytes: int = 0
    run_id: str = ""


@dataclass(frozen=True)
class AttachmentStagingCompleted(JournalEvent):
    """附件暂存完成。"""

    plane_id: str = ""
    file_count: int = 0
    total_bytes: int = 0
    duration_ms: float = 0


@dataclass(frozen=True)
class AttachmentStagingFailed(JournalEvent):
    """附件暂存失败（路径拒绝、传输超时、IO 错误）。"""

    plane_id: str = ""
    error: str = ""
    failed_paths: tuple[str, ...] = ()
    run_id: str = ""


# ── 认知控制原语（PR2 / PR3a / PR4）─────────────────────


@dataclass(frozen=True)
class ContextManifested(JournalEvent):
    """PerceiveHub emitted a curated ContextManifest for this step (PR2).

    The ``item_refs`` are seq numbers into the journal that carry the
    full payloads (clock, workspace_artifacts, etc.).  ``digest`` is the
    canonical hash of the manifest for replay-side verification.

    The Reasoner never reads ``prompt_preview``; the manifest is the only
    source of truth.
    """

    step: int = 0
    item_refs: tuple[int, ...] = ()
    item_kinds: tuple[str, ...] = ()
    digest: str = ""
    persist_full_prompt: bool = False


@dataclass(frozen=True)
class PerceptionMerged(JournalEvent):
    """Hub fold result — final state of the receive phase for this step."""

    step: int = 0
    delta_ref: int = 0
    item_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateDecided(JournalEvent):
    """DecisionGate verdict (PR4 / v3 §3.5).

    The journal record IS the canonical event surface.  ``allow`` is
    intentionally NOT recorded (allow 默认不记).  Only ``warn`` /
    ``rewrite`` / ``deny`` are emitted.
    """

    gate: str = ""
    verdict: str = ""  # "warn" | "rewrite" | "deny"
    is_rewritten: bool = False
    tool_name: str = ""
    policy_fact_kind: str = ""
    policy_fact_message: str = field(default="", metadata={"journal_kind": "content"})
    step: int = 0


@dataclass(frozen=True)
class InboxFollowupCreated(JournalEvent):
    """A user message was injected via the Inbox (PR8 / D24).

    All user input flows Inbox → journal → inbox-facts sensor → Perceive.
    ``payload_preview`` carries a (lossy) preview of the user message
    so the journal itself is the single source of truth (per ADR-0037);
    the full text stays on the originating ``Session.user_text``.
    """

    inbox_id: str = ""
    actor: str = ""
    target: str = ""
    priority: str = ""
    step: int = 0
    payload_preview: str = field(default="", metadata={"journal_kind": "content"})


@dataclass(frozen=True)
class TeamMessagePublished(JournalEvent):
    """TeamMessage MVP (PR9 / D25).  One topic per team; ``thread_id`` for
    delegation sub-threads.  No CRDT — see PR9b for the blackboard lease
    that complements this channel.
    """

    team_id: str = ""
    thread_id: str = ""
    sender_role: str = ""
    recipient_role: str = ""
    step: int = 0
    body_preview: str = field(default="", metadata={"journal_kind": "content"})


@dataclass(frozen=True)
class ApprovalRequested(JournalEvent):
    """PR6: an ExecutionEnvelope flagged ``approval_requirement`` and the
    approval was queued.
    """

    envelope_id: str = ""
    tool_name: str = ""
    capability_grant: str = ""
    risk_level: str = ""


@dataclass(frozen=True)
class ApprovalResolved(JournalEvent):
    """PR6: a queued approval was resolved (approved / denied)."""

    envelope_id: str = ""
    resolver: str = ""
    approved: bool = False


@dataclass(frozen=True)
class MemoryCommitted(JournalEvent):
    """PR7: a MemorySystem.committed event for observability."""

    layer: str = ""
    record_kind: str = ""
    record_id: str = ""


@dataclass(frozen=True)
class ContextCompacted(JournalEvent):
    """PR7: a CompactionPolicy was applied and the manifest was compacted."""

    step: int = 0
    original_kinds: tuple[str, ...] = ()
    kept_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunPaused(JournalEvent):
    """PR2: emitted on the ``_loop`` boundary when the run is paused."""

    step: int = 0
    reason: str = ""


@dataclass(frozen=True)
class RunResumed(JournalEvent):
    """PR2: emitted on the ``_loop`` boundary when the run is resumed."""

    step: int = 0
    reason: str = ""


# ── 创造模式（§13.3 Creator）─────────────────────────────────
#
# PluginAuthored / PluginMounted / PluginUnmounted / PresetPublished 是
# 宪法 §13.3.1 五条硬约束（C3/C4/C5/PR12/§23.2）的可审计事实：每一笔 plugin
# 的「创作→挂载→卸载→发布」必有一条对应事件，trace_id/run_id/step 自动盖章。
#
# Payload 设计原则：
# - capability_grant 字段一律序列化为 tuple[str, ...] —— 与 CapabilityGrant 原子值
#   体系保持一致，方便按子集校验。
# - plugin_meta 字段保存 PluginMeta TypedDict 关键字段的 snapshot 而非引用：
#   后续即使插件代码改了 meta，历史 journal 仍能如实回放挂载时声明的能力。
# - rejection 字段统一为具名错误码（CapabilityGrantExceeded / PluginMetaMissing /
#   InvariantViolation / NameConflict / NotMounted），禁止裸字符串。


@dataclass(frozen=True)
class PluginAuthored(JournalEvent):
    """创造模式：agent 把一份 plugin 源码写到磁盘。

    Step 5 / §13.3.4 流程的「写文件」动作；ToolInvoked 之外另发一条 Creator
    专用事件，用于按 actor_role 把"我写了一个插件"与通用工具事件区分开。
    """

    plugin_name: str = ""
    path: str = ""
    language: str = ""
    size_bytes: int = 0
    actor_role: str = ""
    step: int = 0


@dataclass(frozen=True)
class PluginMounted(JournalEvent):
    """创造模式：plugin 已通过 Composer.mount 挂入 Context（C3 单一事实源）。

    §13.3.1 C5：挂载时调用方 capability_grant 与插件声明 capabilities 子集校验，
    超集 → CapabilityGrantExceeded 拒绝并落拒绝事件。拒绝路径不发本事件，
    改发 PluginMountRejected。
    """

    plugin_name: str = ""
    plugin_id: str = ""
    capabilities: tuple[str, ...] = ()
    capability_grant: tuple[str, ...] = ()
    meta: dict[str, object] = field(default_factory=dict)
    actor_role: str = ""
    step: int = 0


@dataclass(frozen=True)
class PluginMountRejected(JournalEvent):
    """挂载被拒（C5 / PR12 / §23.2 三道闸任一失败）。

    ``reason_code`` 取值见 ``composition.py::ComposerErrorCode``；
    本事件是失败事实的唯一来源，PluginMounted 与之互斥。
    """

    plugin_name: str = ""
    reason_code: str = ""
    reason_message: str = ""
    plugin_meta_present: bool = False
    capability_grant: tuple[str, ...] = ()
    requested_capabilities: tuple[str, ...] = ()
    actor_role: str = ""
    step: int = 0


@dataclass(frozen=True)
class PluginUnmounted(JournalEvent):
    """创造模式：plugin 已通过 Composer.unmount 退出 Context。"""

    plugin_name: str = ""
    plugin_id: str = ""
    actor_role: str = ""
    step: int = 0


@dataclass(frozen=True)
class PluginInspected(JournalEvent):
    """创造模式：CordisControlTool(inspect) 已返回当前能力图 snapshot。

    每条记录带 ``mounted_count`` 与 ``plugins_summary``（name + implements +
    policy_class + side_effects 派生键），便于 lca-ops trace 子命令按 seq
    回放「运行时的能力图长什么样」。
    """

    actor_role: str = ""
    mounted_count: int = 0
    plugin_names: tuple[str, ...] = ()
    plugins_summary: tuple[dict[str, object], ...] = ()
    step: int = 0


@dataclass(frozen=True)
class PresetPublished(JournalEvent):
    """创造模式：mount 成功后 PluginAuthoring 把 plugin 落盘到 preset 目录。

    §13.3.4 流程的 Step 6：plugin 源码 + bundle YAML 写入
    ``$LCA_AGENT_PRESETS_HOME/<preset_id>/``。下一次 boot 加载该 bundle
    时 plugin 自动挂入 Context，无需任何 cordis_control 调用。

    ``bundle_path`` / ``plugin_path`` 是相对 preset root 的 POSIX 路径，
    不带环境变量前缀（避免 journal 含敏感信息）。
    """

    preset_id: str = ""
    plugin_name: str = ""
    plugin_id: str = ""
    preset_root: str = ""
    bundle_path: str = ""
    plugin_path: str = ""
    actor_role: str = ""
    step: int = 0


# ── ADR-0065 §三 / PR-3: JournalRecord v2 envelope ──────────────────
#
# 引入 JournalRecord 作为 StampedEvent 的下替代身;不立即删除 StampedEvent。
# 字段语义变化:
# - schema 必填 "lca.journal/2"
# - event_id 全局唯一(ULID),与 seq 不同
# - occurred_at vs committed_at 显式区分(0065 §三)
# - causation.parent_event_id / causation.links 替代 parent_seq(0065 §三)
# - evidence: tuple[EvidenceRef, ...] 引用受治理证据(0065 §四)
# - 不再有 *_preview 字段;plugin_state 字段;output_truncated 字段
#   (迁移完成后由后续 PR 强制删除)
#
# PR-3 不删除 StampedEvent / *_preview / plugin_state;消费方迁移完成后再
# 单独 PR 走删除路径。本文件只新增类型 + 工厂方法。


@dataclass(frozen=True, slots=True)
class Causation:
    """事件因果关系(ADR-0065 §三)。

    - ``parent_event_id``: 直接因果(替代 StampedEvent.parent_seq)。
    - ``links``: 非树形关联 —— 重试 / 并行委派 / 外部 trace / 跨 run 证据。
    """

    parent_event_id: str = ""
    links: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "parent_event_id": self.parent_event_id,
            "links": [dict(link) for link in self.links],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Causation:
        links_raw = payload.get("links", ()) or ()
        links: tuple[dict[str, str], ...] = tuple(
            dict(item) for item in links_raw if isinstance(item, Mapping)
        )
        return cls(
            parent_event_id=str(payload.get("parent_event_id", "")),
            links=links,
        )


@dataclass(frozen=True, slots=True)
class DescriptorRef:
    """事件描述符引用(ADR-0065 §三 / L4)。

    - type: 与 EventDescriptor.type_name 对应;
    - version: 描述符自身版本号;
    - payload_schema_version: payload dataclass schema 版本。
    """

    type: str = ""
    version: int = 1
    payload_schema_version: int = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "version": self.version,
            "payload_schema_version": self.payload_schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> DescriptorRef:
        return cls(
            type=str(payload.get("type", "")),
            version=int(payload.get("version", 1)),
            payload_schema_version=int(payload.get("payload_schema_version", 1)),
        )


@dataclass(frozen=True, slots=True)
class JournalRecord:
    """Journal v2 envelope(ADR-0065 §三)。

    字段:
    - schema: 必填 "lca.journal/2";L4 fail-fast 校验入口。
    - event_id: 全局唯一(ULID);L3 身份不可重铸的稳定句柄。
    - run_id / run_seq: 连续唯一;L1/L3 强约束。
    - occurred_at: 源认定的发生时间(可能落后于 committed_at)。
    - committed_at: 账本接受该记录的时间(L2 "提交先于观察")。
    - scope: RunScope —— 与 StampedEvent.scope 等价。
    - causation: Causation —— 替代 parent_seq;支持跨 run 关联。
    - descriptor: DescriptorRef —— L4 fail-fast 校验目标。
    - data: 类型化 payload 规范化序列化;不再是自由 dict 逃逸口。
    - evidence: 受治理证据引用(L5 / §四);完整载荷走 EvidenceStore。
    - plan_ref: ADR-0074 PR-6 —— CompiledRunPlan canonical hash (V5 硬约束);
      auto-stamped from ``lca_run_plan_ref`` ContextVar. 空字符串 ``""`` for
      legacy code paths without plan binding (tests, projector previews)。
    """

    schema: Literal["lca.journal/2"] = "lca.journal/2"
    event_id: str = ""
    run_id: str = ""
    run_seq: int = 0
    occurred_at: float = 0.0
    committed_at: float = 0.0
    scope: RunScope = field(default_factory=RunScope)
    causation: Causation = field(default_factory=Causation)
    descriptor: DescriptorRef = field(default_factory=DescriptorRef)
    data: Mapping[str, object] = field(default_factory=dict)
    evidence: tuple[_EvidenceRef, ...] = ()
    plan_ref: str = ""
    """CompiledRunPlan canonical hash (PR-6 V5); empty = no plan binding."""

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "run_seq": self.run_seq,
            "occurred_at": self.occurred_at,
            "committed_at": self.committed_at,
            "scope": _scope_to_dict(self.scope),
            "causation": self.causation.to_dict(),
            "descriptor": self.descriptor.to_dict(),
            "data": dict(self.data),
            "evidence": [ref.to_dict() for ref in self.evidence],
            "plan_ref": self.plan_ref,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> JournalRecord:
        from lca.contracts.observability.evidence import EvidenceRef as _EvidenceRef

        scope_raw = payload.get("scope", {}) or {}
        scope = _scope_from_dict(scope_raw)
        causation = Causation.from_dict(payload.get("causation", {}) or {})
        descriptor = DescriptorRef.from_dict(payload.get("descriptor", {}) or {})
        evidence_raw = payload.get("evidence", ()) or ()
        evidence = tuple(
            _EvidenceRef.from_dict(item) for item in evidence_raw if isinstance(item, Mapping)
        )
        return cls(
            schema="lca.journal/2",
            event_id=str(payload.get("event_id", "")),
            run_id=str(payload.get("run_id", "")),
            run_seq=int(payload.get("run_seq", 0)),
            occurred_at=float(payload.get("occurred_at", 0.0)),
            committed_at=float(payload.get("committed_at", 0.0)),
            scope=scope,
            causation=causation,
            descriptor=descriptor,
            data=dict(payload.get("data", {}) or {}),
            evidence=evidence,
            plan_ref=str(payload.get("plan_ref", "")),
        )


def _scope_to_dict(scope: RunScope) -> dict[str, object]:
    """RunScope 不依赖 dataclasses.asdict(因为字段是 brand-typed)。"""
    return {
        "trace_id": str(scope.trace_id),
        "run_id": str(scope.run_id),
        "parent_run_id": str(scope.parent_run_id) if scope.parent_run_id else None,
        "parent_trace_id": str(scope.parent_trace_id) if scope.parent_trace_id else None,
        "delegation_id": scope.delegation_id,
        "agent_role": scope.agent_role,
        "step": scope.step,
    }


def _scope_from_dict(payload: Mapping[str, object]) -> RunScope:
    """从 dict 重建 RunScope;brand-typed 字段转回 str,None 原样保留。"""

    def _opt_str(key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        return str(value)

    return RunScope(
        trace_id=str(payload.get("trace_id", "")),
        run_id=str(payload.get("run_id", "")),
        parent_run_id=_opt_str("parent_run_id"),
        parent_trace_id=_opt_str("parent_trace_id"),
        delegation_id=_opt_str("delegation_id"),
        agent_role=str(payload.get("agent_role", "")),
        step=int(payload.get("step", 0)),
    )


def run_scope(scope: RunScope):
    """兼容导出：经 observability 包根转发唯一 RunScope 实现。"""

    facade = import_module("lca.layer0_infra.observability")
    return facade.run_scope(scope)


def get_current_run_scope() -> RunScope | None:
    """兼容导出：读取当前环境的唯一 RunScope。"""

    facade = import_module("lca.layer0_infra.observability")
    return facade.get_current_run_scope()


def stamped_to_journal_record(
    stamped: StampedEvent,
    **kwargs: object,
) -> JournalRecord:
    """兼容导出：将 Journal 账本事件投影为 v2 JournalRecord。"""

    facade = import_module("lca.layer0_infra.observability")
    return facade.stamped_to_journal_record(stamped, **kwargs)


__all__ = [
    "Causation",
    "DescriptorRef",
    "JournalRecord",
    "get_current_run_scope",
    "run_scope",
    "stamped_to_journal_record",
]
