"""执行日志（journal）词表 —— 叙事平面事件的单一事实源（ADR-0037）。

Journal-as-Truth：协作运行时的语义边界发射 ``JournalEvent``，span 树只是
日志的一个投影。本模块定义：

- **关联骨架** ``RunScope``：trace_id / run_id / parent_run_id /
  delegation_id / agent_role —— 父子关系由显式 ID 构造，不依赖 ambient
  OTel context（0 秒化石 span 与错挂父子链在构造上不可能）。
- **事件词表**：容器事件（Team/Agent run 开闭）、协作事件（Delegation
  一等公民 + Synthesis 收口）、资源事实（Llm/Tool/Step/Decision）、
  洞察事件（RunInsight 由 InsightEngine 回注）。

事件是纯 frozen dataclass（ADR-0015）；关联骨架不在事件本体上——由引擎在
record 时盖章进 ``StampedEvent.scope``，事件字段只承载领域语义。
发射点登记与守卫见 ``journal_catalog.py``；事件经包根 ``record(...)`` 发射。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum

# ── 关联骨架 ─────────────────────────────────────────────


@dataclass(frozen=True)
class RunScope:
    """当前 run 的关联身份（journal 事件的关联骨架）。

    - ``run_id``：一个 agent run 容器的 id（团队根、lead、成员各一个）；
    - ``parent_run_id``：生成此 run 的 run id（根为 None）；
    - ``delegation_id``：生成此 run 的委派 id（无则 None）；
    - ``agent_role``：当前 run 的角色（委派发射点用作 caller_role）。
    """

    trace_id: str = ""
    run_id: str = ""
    parent_run_id: str | None = None
    delegation_id: str | None = None
    agent_role: str = ""


_run_scope: ContextVar[RunScope | None] = ContextVar("lca_run_scope", default=None)


def get_current_run_scope() -> RunScope | None:
    """读取当前 run 关联身份；未设置返回 None（solo 且未入 run 边界）。"""
    return _run_scope.get()


@contextmanager
def run_scope(scope: RunScope) -> Iterator[None]:
    """在 run 边界包裹此上下文：asyncio.create_task 拷贝 Context 后，
    成员任务读到的是发起方的关联身份（与 delegator_scope 同一机制）。"""
    token = _run_scope.set(scope)
    try:
        yield
    finally:
        _run_scope.reset(token)


# ── 事件基类与盖章记录 ──────────────────────────────────


@dataclass(frozen=True)
class JournalEvent:
    """journal 事件基类（纯标记；领域字段在子类，关联骨架在 StampedEvent）。"""


@dataclass(frozen=True)
class StampedEvent:
    """引擎盖章后的日志记录：序号 + 时间戳 + 关联骨架 + 事件本体。"""

    seq: int
    ts: float
    scope: RunScope
    event: JournalEvent


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
    """团队 run 容器关闭（触发 Run Card / 序列图 / InsightEngine）。"""

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
    """决策事实（think 相位产出）。"""

    step: int = 0
    action_type: str = ""
    rationale_preview: str = ""
    delegate_target: str = ""
    delegate_count: int = 0
    tool_name: str = ""
    confidence: float = 0.0


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
class ToolInvoked(JournalEvent):
    """工具调用完成。"""

    tool_name: str = ""
    arguments_preview: str = ""
    result_preview: str = ""
    ok: bool = True
    latency_ms: int = 0
    attempt: int = 1
    error: str = ""


@dataclass(frozen=True)
class ToolDenied(JournalEvent):
    """工具调用被拒（权限/校验）。"""

    tool_name: str = ""
    reason: str = ""


# ── 洞察事件（InsightEngine 回注）───────────────────────


@dataclass(frozen=True)
class RunInsight(JournalEvent):
    """计算洞察（冗余调用/关键路径/成本/循环等，引擎回注日志）。"""

    kind: str = ""
    summary: str = ""
    detail: str = ""
