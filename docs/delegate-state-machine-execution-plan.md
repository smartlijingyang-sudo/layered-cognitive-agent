# 层次团队委派状态机——根本性重构执行方案（最终版）

> 自包含文档——无需阅读原评审文档、无需任何对话上下文即可执行。
> 供实现 agent 直接落地使用。所有开放问题已通过源码验证解决，无信息盲区。

---

## 0. 本方案定位

层次团队（hierarchical team）委派状态机存在 4 个根因问题（A/B/C/D）。本方案把每个根因分别收敛到**单一事实来源（single source of truth）**，使得同类问题不会在新代码中复发。

**不做的事**：不推倒重来，不改 Protocol 已有方法签名，不引入新的可插拔注册表（YAGNI），不把重试逻辑上 Board Protocol。五层架构、Board=dumb 容器 / tracking=业务逻辑 / gate=控制流的职责分离、ADR-0015 契约层零行为约束全部保留。

---

## 1. 背景（自包含）

### 1.1 涉及的类型定义

```python
# lca/contracts/enums.py
class RoleStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class ComponentKind(str, Enum):
    OBSERVABILITY = "observability"
    STATE_STORE = "state_store"
    MEMORY = "memory"
    EVENT_BUS = "event_bus"
    MEMBER_STATUS = "member_status"
    DECISION_GATE = "decision_gate"
    BUDGET_POLICY = "budget_policy"


class ActionType(str, Enum):
    RESPOND = "respond"
    USE_TOOL = "use_tool"
    DELEGATE = "delegate"
    HANDOFF = "handoff"
    STOP = "stop"
    ASK_HUMAN = "ask_human"


# lca/contracts/lifecycle.py
class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    PAUSED = "paused"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"  # ← 不是 DONE
    FAILED = "failed"
    CANCELED = "canceled"


# lca/contracts/semantic_keys.py
FAILURE_KIND = "failure_kind"
FAILURE_KIND_VALIDATION = "validation"  # 参数/目标不合法,重试无意义
FAILURE_KIND_EXECUTION = "execution"  # 默认 fallback
FAILURE_KIND_TRANSIENT = "transient"  # 瞬时性错误,可重试


# lca/contracts/ids.py（当前只有这两个函数）
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:_ID_SUFFIX_LEN]}"


# lca/contracts/member_status.py
@runtime_checkable
class MemberStatus(Protocol):
    @property
    def required_roles(self) -> frozenset[str]: ...
    @property
    def status(self) -> dict[str, RoleStatus]: ...
    def mark(self, role: str, new_status: RoleStatus) -> "MemberStatus": ...
    def all_done(self) -> bool: ...
    def waiting_roles(self) -> list[str]: ...
    def as_prompt_text(self) -> str: ...


# lca/contracts/role_team.py
@dataclass
class RetryPolicy:  # 工具级重试,用于 SafeExecutor——本方案不复用此类型
    max_retries: int = 3  # 语义:"首次之后的重试次数",即 max_retries=3 → 4 次总尝试
    backoff_base_s: float = 1.0
    backoff_multiplier: float = 2.0
    retryable_errors: list[str] = field(default_factory=list)


@dataclass
class TeamConfig:
    process: TeamProcess
    shared_memory_layers: list[MemoryLayer] = field(default_factory=list)
    max_rounds: int | None = None
    graph_definition_ref: str | None = None
    decision_gate: DecisionGateName = DecisionGateName.MUST_CONSULT_ALL


# lca/contracts/run_context.py
@dataclass
class RunContext:
    trace_id: str | None = None
    from_role: str = ""
    member_status: MemberStatus | None = None
    teammates: list[RoleProfile] = field(default_factory=list)
    role_mode: RoleMode = RoleMode.SOLO
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)
```

### 1.2 四个根因问题

- **问题 A（settled/done 混淆）**：`MemberStatus` 只有一根轴——"是不是 DONE"。`waiting_roles()` 返回所有非 DONE 角色（含 FAILED），导致已 FAILED 的角色被反复委派直到 Budget 耗尽。根因是缺少"已尝试完（settled）"与"成功（done）"的区分。
- **问题 B（时钟域混用）**：`DelegateOperation.execute()` 用 `spec.deadline.timestamp()`（POSIX wall-clock）减 `asyncio.get_running_loop().time()`（monotonic, 任意 epoch），结果无意义，`deadline` 字段实际不生效。
- **问题 C（gate 单向兜底）**：`MustConsultAllMembers.enforce()` 只拦截 `RESPOND`。LLM 主动 `DELEGATE` 给已 DONE 或终态 FAILED 的角色时直接放行，造成重复委派。
- **问题 D（消费顺序不确定）**：`InMemoryMemberStatus.required_roles` 是 `frozenset[str]`，迭代顺序在不同 `PYTHONHASHSEED` 下不同。`waiting_roles()[0]` 选出的"下一个委派角色"不可复现。

### 1.3 关键文件

```
lca/contracts/enums.py                                — RoleStatus, ComponentKind, ActionType
lca/contracts/lifecycle.py                            — TaskStatus (COMPLETED 非 DONE)
lca/contracts/semantic_keys.py                        — failure_kind 常量
lca/contracts/ids.py                                  — utc_now(), new_id()
lca/contracts/member_status.py                        — MemberStatus Protocol
lca/contracts/state.py                                — AgentState, Budget
lca/contracts/decision.py                             — Decision, DelegationSpec, Observation
lca/contracts/role_team.py                             — RetryPolicy, TeamConfig, CacheConfig
lca/contracts/run_context.py                          — RunContext
lca/contracts/protocols/orchestration.py              — TeamContext
lca/layer1_cognitive/member_status/in_memory.py       — InMemoryMemberStatus (唯一实现)
lca/layer1_cognitive/member_status/tracking.py        — update_member_status()
lca/layer1_cognitive/body/action_handlers.py          — DelegateOperation
lca/layer1_cognitive/body/action_catalog.py           — _operation_for() 构造 DelegateOperation
lca/layer1_cognitive/body/safe_executor.py             — SimpleSafeExecutor (RetryPolicy 消费方)
lca/layer1_cognitive/brain/decision_gates/must_consult_all.py — MustConsultAllMembers
lca/layer1_cognitive/brain/critic.py                  — SimpleCritic (failure_kind 消费方)
lca/layer2_runtime/runtime_loop.py                     — CognitiveRuntime.run (RunContext → AgentState)
lca/layer3_agent/team_orchestrator.py                  — TeamOrchestrator
lca/layer3_agent/orchestration_strategies/hierarchical.py — HierarchicalStrategy (TeamContext → RunContext)
lca/layer0_infra/transport/agent_transport.py         — InternalTransport
lca/layer0_infra/transport/a2a_transport.py            — A2ATransport
lca/layer0_infra/transport/mcp_transport.py            — MCPTransport
lca/layer4_app/assembly.py                             — Assembly.assemble_agent / assemble_team
lca/layer4_app/defaults.py                             — register_defaults()
lca/layer4_app/api.py                                 — Agent / MultiAgentTeam (强制 assemble 顺序)
tests/test_contracts_purity.py                        — ADR-0015 门禁 (Enum 豁免)
```

---

## 2. 设计原则

1. **让非法状态在类型层面不可表达**。问题 B 的修复不是"换正确公式"，而是让 monotonic 时间无法被传进时间计算函数（参数类型是 `datetime`，不是 `float`）。
2. **每一类判定只允许存在一处实现**。settled/done 的判定、gate 该做什么的判定，都收敛为一个纯函数。
3. **保持既有分层不变**。Board 仍然是 dumb 容器，tracking.py 仍然是业务逻辑，gate 仍然是控制流，contracts/ 仍然零行为类。
4. **重试参数走既有 state 管道，不新增构造注入路径**。`delegate_max_attempts` 通过 `TeamConfig → TeamContext → RunContext → AgentState` 传递，与 `member_status`、`teammates`、`role_mode` 走同一条路。

---

## 3. 四个根因级修复

### Fix 1 —— settled/done 分类收敛到单一函数（解决问题 A）

新建文件 `lca/contracts/role_status_rules.py`：

```python
"""RoleStatus 的语义分类——settled(终态) vs done(成功终态)的唯一权威定义。

任何需要判断"某个 RoleStatus 是否终态 / 是否成功终态"的地方,一律引用本文件的
函数,禁止在别处用 == RoleStatus.DONE / != RoleStatus.DONE 重新发明判定逻辑。

契约层合规:本文件只有模块级纯函数,不含类/方法,不受 ADR-0015
"非 Protocol 类须为 dataclass 且无自定义方法"约束——该约束只管类,不管自由函数。
与 contracts/semantic_keys.py(对 failure_kind 字符串值的语义解释)是同一模式。
"""

from lca.contracts.enums import RoleStatus

_TERMINAL_STATUSES: frozenset[RoleStatus] = frozenset({RoleStatus.DONE, RoleStatus.FAILED})


def is_terminal_status(status: RoleStatus) -> bool:
    """是否已"结算"(settled)——状态机不会再处理它,不代表成功。"""
    return status in _TERMINAL_STATUSES


def is_success_status(status: RoleStatus) -> bool:
    """是否成功终态(done)。"""
    return status is RoleStatus.DONE
```

### Fix 2 —— wall-clock 专用时间工具（解决问题 B）

在 `lca/contracts/ids.py` 追加：

```python
def remaining_seconds(deadline: datetime, *, now: datetime | None = None) -> float:
    """deadline 距今剩余的 wall-clock 秒数(可能为负,代表已过期)。

    deadline 与 now 必须是同一 epoch 的 timezone-aware datetime(wall-clock/UTC)。
    禁止把 asyncio.get_running_loop().time() 之类的 monotonic float 传入 ——
    这正是问题 B 的根因。本函数的类型签名(要求 datetime)已经在类型检查层面
    拒绝 monotonic float 混入:不存在"不小心传错"的写法。
    """
    return (deadline - (now or utc_now())).total_seconds()


def elapsed_seconds(started_at: datetime, *, now: datetime | None = None) -> float:
    """自 started_at 起经过的 wall-clock 秒数。"""
    return ((now or utc_now()) - started_at).total_seconds()
```

### Fix 3 —— gate 裁决收敛到单一纯函数（解决问题 C）

新建文件 `lca/layer1_cognitive/member_status/policy.py`：

```python
"""MustConsultAllMembers 需要做什么裁决,只由这一个纯函数决定。

不放进 contracts/:producer(本文件)和 consumer(must_consult_all.py)
都在 layer1_cognitive 内部,层内私有协作类型不需要上升到 contracts。
"""

from dataclasses import dataclass
from typing import Literal
from lca.contracts.member_status import MemberStatus


@dataclass(frozen=True)
class RequiredAction:
    """给定 board 状态,状态机唯一允许的下一步是什么。

    kind == "must_delegate": 存在尚未结算(non-terminal)的必需角色。
        target_role 给出"如果要改写决策,应该改写成委派给谁"的规范目标。
    kind == "may_respond": 所有必需角色都已结算(DONE 或终态 FAILED)。
        RESPOND 被允许,即便部分角色以 FAILED 结束——这是刻意的降级行为
        (degradation by design),不是 gate 没拦住的 bug。
    """

    kind: Literal["must_delegate", "may_respond"]
    target_role: str | None = None


def compute_required_action(board: MemberStatus) -> RequiredAction:
    waiting = board.waiting_roles()
    if waiting:
        return RequiredAction(kind="must_delegate", target_role=waiting[0])
    return RequiredAction(kind="may_respond")
```

`must_consult_all.py` 重写——两个方向（阻止提前 RESPOND + 阻止重复 DELEGATE）共享同一个 `compute_required_action()`：

```python
from lca.layer1_cognitive.member_status.policy import compute_required_action


class MustConsultAllMembers(DecisionGate):
    """把违反"所有必需角色必须结算后才能收尾"的决策改写为规范动作。

    RESPOND 方向(阻止提前收尾)和 DELEGATE 方向(阻止委派已终态角色/
    全部结算后仍误发 DELEGATE)都经过同一个 compute_required_action()。
    范围限定:只处理 RESPOND 与 DELEGATE,HANDOFF/USE_TOOL 原样放行。
    扩大管辖范围是独立的产品决策,在 ADR 中显式声明为 out-of-scope。
    """

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        board = state.member_status
        if board is None:
            return decision

        if decision.action_type not in (ActionType.RESPOND, ActionType.DELEGATE):
            return decision

        required = compute_required_action(board)

        if required.kind == "may_respond":
            return decision  # 全部角色已结算,任何动作都不需要被本 gate 干预

        # required.kind == "must_delegate"
        waiting_set = set(board.waiting_roles())
        already_correct = (
            decision.action_type == ActionType.DELEGATE
            and decision.delegate_to is not None
            and decision.delegate_to.target_role in waiting_set
        )
        if already_correct:
            return decision  # LLM 选中了某个仍在等待中的角色,合法放行

        target = required.target_role
        return Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.DELEGATE,
            delegate_to=DelegationSpec(
                target_role=target,
                subtask=_infer_subtask(state.task, target),
            ),
            rationale="[框架强制] 尚有必需角色未完成结算,禁止提前收尾或委派已终态角色",
            confidence=1.0,
        )
```

### Fix 4 —— required_roles 消费顺序确定性（解决问题 D）

`InMemoryMemberStatus` 内部改用有序结构，Protocol 暴露的 `required_roles` 签名不变（仍返回 `frozenset[str]`）：

```python
@dataclass(frozen=True)
class InMemoryMemberStatus:
    """纯状态容器(dumb)。不知道 failure_kind、不知道重试策略、不知道 attempts。"""

    role_order: tuple[str, ...]  # 保证消费顺序确定性
    status: dict[str, RoleStatus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(set(self.role_order)) != len(self.role_order):
            raise ValueError(f"role_order 含重复角色: {self.role_order}")
        for role in self.role_order:
            if role not in self.status:
                self.status[role] = RoleStatus.PENDING

    @property
    def required_roles(self) -> frozenset[str]:
        return frozenset(self.role_order)

    def mark(self, role: str, new_status: RoleStatus) -> "InMemoryMemberStatus":
        new_status_dict = {**self.status, role: new_status}
        return InMemoryMemberStatus(self.role_order, new_status_dict)

    def all_done(self) -> bool:
        return all(is_success_status(self.status[r]) for r in self.role_order)

    def all_settled(self) -> bool:
        return all(is_terminal_status(self.status[r]) for r in self.role_order)

    def waiting_roles(self) -> list[str]:
        return [r for r in self.role_order if not is_terminal_status(self.status[r])]

    def as_prompt_text(self) -> str:
        waiting = self.waiting_roles()
        if waiting:
            return f"尚未咨询的角色: {', '.join(waiting)}"
        failed = [r for r in self.role_order if self.status[r] == RoleStatus.FAILED]
        if failed:
            return f"{', '.join(failed)} 角色多次尝试后仍不可用,本次结论不含该视角"
        return "所有必需角色均已咨询完毕"
```

`all_settled()` 新增到 Protocol 签名。`waiting_roles()` 的判定从 `!= DONE` 改为 `not is_terminal_status()`，即排除 FAILED——这是问题 A 的核心修复：FAILED 角色不再出现在 `waiting_roles()` 中，不会被反复委派。

构造调用点：`TeamOrchestrator._create_member_status`（`team_orchestrator.py:79`）当前传入 `required_roles=frozenset(m.role_profile.role for m in members)`。改为 `role_order=tuple(m.role_profile.role for m in members)`——`members` 是 `list[CognitiveAgent]`，有序，保证构造顺序确定。

---

## 4. 重试逻辑（tracking.py + AgentState）

### 4.1 设计决策：不复用 RetryPolicy

`RetryPolicy`（`contracts/role_team.py`）是工具级重试策略，含 `backoff_base_s`/`backoff_multiplier`（指数退避参数）。delegate 重试不需要退避——失败后角色保持 PENDING，下一轮 ReAct 循环自然再次委派，无 sleep。因此 delegate 重试参数是**一个 int**（总尝试次数上限），不是 RetryPolicy 对象。

### 4.2 wiring：走既有 state 管道

`delegate_max_attempts` 通过 `TeamConfig → TeamContext → RunContext → AgentState` 传递：

```
TeamConfig.delegate_max_attempts (配置层,用户可按团队设置)
  → HierarchicalStrategy.run: ctx = RunContext(..., delegate_max_attempts=context.config.delegate_max_attempts)
    → runtime_loop.py: state = AgentState(..., delegate_max_attempts=ctx.delegate_max_attempts)
      → tracking.py: update_member_status reads state.delegate_max_attempts
```

这是 `member_status`、`teammates`、`role_mode` 走的同一条路。不需要给 `DelegateOperation` 加构造参数——`update_member_status` 已经接收 `state: AgentState`，直接从 state 读。

### 4.3 新增的契约字段

```python
# lca/contracts/role_team.py — TeamConfig 新增字段
@dataclass
class TeamConfig:
    ...
    delegate_max_attempts: int = 3  # 每个角色的最大委派尝试次数(总次数,含首次)


# lca/contracts/run_context.py — RunContext 新增字段
@dataclass
class RunContext:
    ...
    delegate_max_attempts: int = 3  # 从 TeamConfig 传入,成员路径默认不读


# lca/contracts/state.py — AgentState 新增字段
@dataclass
class AgentState:
    ...
    delegate_max_attempts: int = 3  # 从 RunContext 传入
    delegate_attempts: dict[str, int] = field(default_factory=dict)  # 每角色已尝试次数
```

`AgentState.snapshot()` 只存 `state_ref` 指针，不做字段级序列化——新增字段不影响 checkpoint 兼容性。

### 4.4 tracking.py 重写

```python
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_VALIDATION,
)


def _next_role_status(
    *,
    success: bool,
    failure_kind: str,
    attempts_after: int,
    max_attempts: int,
) -> RoleStatus:
    """纯函数:不接触 AgentState/Board,只做分类决策,可穷举测试。"""
    if success:
        return RoleStatus.DONE
    if failure_kind == FAILURE_KIND_VALIDATION:
        return RoleStatus.FAILED
    if attempts_after >= max_attempts:
        return RoleStatus.FAILED
    return RoleStatus.PENDING


def update_member_status(
    state: AgentState,
    decision: Decision,
    observation: Observation,
) -> None:
    """Update the member status board after a delegate action completes.

    签名不变——max_attempts 从 state.delegate_max_attempts 读取,
    不需要新增参数,不需要构造注入。
    """
    board = state.member_status
    if board is None or decision.delegate_to is None:
        return
    role = decision.delegate_to.target_role
    if role is None or role not in board.required_roles:
        return

    if observation.success:
        state.member_status = board.mark(role, RoleStatus.DONE)
        return

    failure_kind = observation.extra.get(FAILURE_KIND, FAILURE_KIND_EXECUTION)
    attempts_after = state.delegate_attempts.get(role, 0) + 1
    state.delegate_attempts[role] = attempts_after

    new_status = _next_role_status(
        success=False,
        failure_kind=failure_kind,
        attempts_after=attempts_after,
        max_attempts=state.delegate_max_attempts,
    )
    state.member_status = board.mark(role, new_status)
```

---

## 5. action_handlers.py 修复

### 5.1 deadline 计算（Fix 2 应用）

```python
from lca.contracts.ids import remaining_seconds
from lca.contracts.semantic_keys import FAILURE_KIND, FAILURE_KIND_TRANSIENT

spec = decision.delegate_to
if spec and spec.deadline:
    timeout_s = remaining_seconds(spec.deadline)
    if timeout_s <= 0:
        # deadline 已过期,不必等待
        observation = Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=f"delegate 超时(deadline 已过期): task_id=未发起",
            extra={FAILURE_KIND: FAILURE_KIND_TRANSIENT},
        )
        update_member_status(state, decision, observation)
        return observation
else:
    timeout_s = _DEFAULT_DELEGATE_TIMEOUT_S
```

### 5.2 _wait_for_result 简化——删除死代码

当前 `_wait_for_result` 有一个 `wait_result is not None` 分支（所有 transport 都走这条）和一个 poll 回退分支（死代码——三个 transport 都实现 `wait_result`，且 `AgentTransport` Protocol 已声明该方法）。

poll 回退分支还是 A2ATransport.wait_result 正确逻辑的**反转副本**（`while status != WORKING` vs A2A 的 `if status != WORKING: return`）。根因是逻辑重复后一份腐烂，不是"一个条件写反了"。

**修复：删除 poll 回退分支，`_wait_for_result` 收敛为直接调用 `transport.wait_result`**：

```python
async def _wait_for_result(
    self,
    transport: AgentTransport,
    task_id: str,
    timeout_s: float,
) -> Observation:
    try:
        return await transport.wait_result(task_id, timeout_s)
    except TimeoutError:
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=f"delegate 超时: task_id={task_id}",
            extra={OBS_TASK_ID: task_id, FAILURE_KIND: FAILURE_KIND_TRANSIENT},
        )
```

同时删除 `_POLL_INTERVAL_S` 常量（不再使用）。

### 5.3 failure_kind 标注——三个失败路径

| 失败路径 | failure_kind | 实现方式 |
|---------|-------------|---------|
| timeout | `TRANSIENT` | `_wait_for_result` 的 `except TimeoutError` 分支，已在 5.2 中标注 |
| agent-not-found（InternalTransport） | `VALIDATION` | transport 吞为失败 Observation，需在 transport 层标注（见下文） |
| transport config 不可解析（A2A ValueError / MCP ValueError/NotImplementedError） | `VALIDATION` | 在 `_send_to_transport` 外包 try/except |
| member 执行失败 | `EXECUTION`（默认） | 无需显式标注，Critic 的 `_extract_failure_kind` 默认 fallback |

**agent-not-found 路径**：`InternalTransport.send_task` 在 handler 不存在时不抛异常，而是创建一个预解决的失败 Future（`_fail_observation("agent not found in directory")`），通过 `wait_result` 返回。修复方式：让 transport 在构造这个 Observation 时标注 `FAILURE_KIND_VALIDATION`——transport 知道失败性质，是分类的正确位置。

需要修改 `lca/layer0_infra/transport/agent_transport.py` 中的 `_fail_observation` 辅助函数（或其调用点），在 agent-not-found 路径的 extra 中加入 `FAILURE_KIND: FAILURE_KIND_VALIDATION`：

```python
# InternalTransport._fail_observation 或调用点
from lca.contracts.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION

fut.set_result(
    Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error="agent not found in directory",
        extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
    )
)
```

**transport config 不可解析路径**：A2ATransport/MCPTransport 的 `send_task` 在 config 不可解析时 raise `ValueError`（A2A）或 `ValueError`/`NotImplementedError`（MCP）。在 `_send_to_transport` 外包精确捕获：

```python
async def _send_to_transport(
    self, decision: Decision, state: AgentState
) -> tuple[AgentTransport, str]:
    spec = decision.delegate_to
    if spec is None:
        raise ToolExecutionError(f"{decision.action_type} 动作缺少 delegate_to 规格")
    transport = self._transport_registry.resolve(spec.protocol)
    agent_card = spec.target_agent_card or spec.target_agent_id or spec.target_role
    if agent_card is None:
        raise ToolExecutionError("delegate 动作缺少目标")
    try:
        with delegator_scope(state.agent_role):
            task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)
        return transport, task_id
    except (ValueError, NotImplementedError) as exc:
        # transport config 不可解析——配置性错误,重试无意义
        raise ToolExecutionError(f"delegate 传输层配置不可用: {exc}", retryable=False) from exc
```

这里 raise `ToolExecutionError(retryable=False)` 而不是直接返回 Observation——因为 `send_task` 失败意味着没有 `task_id`，`_wait_for_result` 无法执行。让 `ToolExecutionError` 传播出去，由上层（`SimpleBody` 的 action 分发逻辑）处理。这与 ADR-0014 的 `ToolInputError(retryable=False)` 模式一致。

### 5.4 DelegateOperation 不需要新增构造参数

`update_member_status` 的签名不变（仍然只接收 `state, decision, observation`），`max_attempts` 从 `state.delegate_max_attempts` 读取。`DelegateOperation.__init__` 不需要新增 `retry_policy` 参数——这是对原方案"wiring 需要构造注入"的纠正。

---

## 6. 契约层合规自检（ADR-0015）

| 新增/修改内容 | 位置 | 是否含类 | 合规 |
|---|---|---|---|
| `is_terminal_status` / `is_success_status` | `contracts/role_status_rules.py` | 否,纯函数 | ✅ 不受"非 Protocol 类"约束 |
| `remaining_seconds` / `elapsed_seconds` | `contracts/ids.py` | 否,纯函数 | ✅ 与已有 `utc_now`/`new_id` 同模式 |
| `all_settled()` | `contracts/member_status.py` | Protocol 方法签名 | ✅ Protocol 允许方法签名 |
| `delegate_max_attempts` | `contracts/role_team.py` 的 `TeamConfig` | dataclass 新增字段 | ✅ |
| `delegate_max_attempts` | `contracts/run_context.py` 的 `RunContext` | dataclass 新增字段 | ✅ |
| `delegate_max_attempts` + `delegate_attempts` | `contracts/state.py` 的 `AgentState` | dataclass 新增字段 | ✅ |
| `RequiredAction` + `compute_required_action` | `layer1_cognitive/member_status/policy.py` | dataclass,无自定义方法 | 不在 contracts/,不受约束 ✅ |

**purity gate 验证**：`tests/test_contracts_purity.py` 的 `_is_enum_class` 检查在 dataclass 检查之前 return，Enum 类被完全豁免。给 `RoleStatus` 加方法不会触发门禁——但本方案仍选择模块级函数（`role_status_rules.py`），因为更清晰、不改 Enum、与 `semantic_keys.py` 模式一致。

---

## 7. 依赖注入 / wiring 变更

| 变更 | 方式 |
|------|------|
| `delegate_max_attempts` 到达 `update_member_status` | `TeamConfig → TeamContext → RunContext → AgentState`（既有管道路径，只加字段） |
| `delegate_max_attempts` 到达 transport | 不需要——transport 不读重试参数 |
| `DelegateOperation` 构造参数 | **不变**——不需要新增 `retry_policy` 参数 |

需要修改的 wiring 点（仅 3 处，全是字段复制）：

1. `HierarchicalStrategy.run`（`hierarchical.py`）：`RunContext(..., delegate_max_attempts=context.config.delegate_max_attempts)`
2. `CognitiveRuntime.run`（`runtime_loop.py`）：`AgentState(..., delegate_max_attempts=ctx.delegate_max_attempts if ctx else 3, delegate_attempts={})`
3. `TeamOrchestrator._create_member_status`（`team_orchestrator.py`）：`role_order=tuple(m.role_profile.role for m in members)` 替代 `required_roles=frozenset(...)`

---

## 8. 明确排除范围（non-goals）

- **不引入** `ComponentKind.MEMBER_RETRY_POLICY` 可插拔注册表——`delegate_max_attempts` 是一个 int 配置值，不是策略对象。等真正出现"角色 A 必须成功、角色 B 允许跳过"差异化需求时再升级。
- **不复用** `RetryPolicy`——其 `backoff_base_s`/`backoff_multiplier` 对 delegate 无意义（无 sleep 重试），`max_retries` 语义是"首次之后"（需 +1 换算），不如直接用 `delegate_max_attempts`（总次数）清晰。
- **不改变** Protocol 已有方法签名（`all_done`/`waiting_roles`/`mark`/`as_prompt_text` 全部兼容，只新增 `all_settled()`）。
- **不扩大** gate 管辖范围到 `HANDOFF`/`USE_TOOL`——显式声明为 out-of-scope。
- `Budget.exceeded()` 是否复用 `elapsed_seconds()` 是可选 polish（语义方向相反，DRY 收益有限）。
- 不给 `MemberStatus` Protocol 加 `record_attempt()`——Board 保持 dumb 容器。

---

## 9. 测试计划

| 测试对象 | 用例 |
|---------|------|
| `is_terminal_status` / `is_success_status` | 穷举 `RoleStatus` 全部 4 个值 |
| `_next_role_status` | 表驱动：`success × failure_kind × (attempts_after < / == / > max_attempts)` 全组合 |
| `InMemoryMemberStatus.waiting_roles()` 顺序 | 相同 `role_order` 反复构造，断言返回顺序恒等于传入顺序（回归 Fix 4） |
| `InMemoryMemberStatus` 状态组合 | 全 PENDING / 部分 DONE / 全 DONE / 含 FAILED 全结算——分别验证 `all_settled`/`all_done`/`as_prompt_text` |
| `compute_required_action` | 全部 waiting / 部分 waiting / 全部 settled(含 FAILED) 三种 board，分别配 RESPOND / DELEGATE(目标=waiting) / DELEGATE(目标=已终态) 三种 decision |
| `remaining_seconds` | deadline 未来 / 过去(负值) / 恰好等于 now(零值) |
| `DelegateOperation` deadline 短路 | deadline 已过期时，断言不发起 `wait_for_result`，直接返回超时 Observation 且带 `FAILURE_KIND_TRANSIENT` |
| `_wait_for_result` 简化后 | mock transport.wait_result 正常返回 / raise TimeoutError——两个分支覆盖 |
| `update_member_status` 重试流转 | transient 失败在 max_attempts 内保持 PENDING；超限后 FAILED 且 `all_settled()` 为 True；validation 类一次即 FAILED |
| 端到端有界性 | 构造"目标角色不在 transport 目录"场景，断言 Supervisor 总步数 ≤ `len(required_roles) × delegate_max_attempts + 常量`，不吃满 `max_steps` |
| 契约纯度门禁回归 | 新增 `contracts/role_status_rules.py`、修改 `contracts/ids.py`/`role_team.py`/`run_context.py`/`state.py` 后，`tests/test_contracts_purity.py` 仍通过 |

---

## 10. 已确认事项（原开放问题全部解决）

| # | 问题 | 结论 | 验证来源 |
|---|------|------|---------|
| 1 | `TaskStatus` 枚举成员 | `SUBMITTED/WORKING/PAUSED/INPUT_REQUIRED/COMPLETED/FAILED/CANCELED`——没有 `DONE` | `contracts/lifecycle.py` |
| 2 | `transport.send_task` 是否抛异常 | InternalTransport 吞为失败 Observation；A2A/MCP 只在 config 不可解析时 raise `ValueError`/`NotImplementedError` | `layer0_infra/transport/agent_transport.py`/`a2a_transport.py`/`mcp_transport.py` |
| 3 | poll 回退路径 | 死代码（三个 transport 都实现 `wait_result`）；且是 A2ATransport 正确逻辑的反转副本。修复方式：删除 | `action_handlers.py:86` + `a2a_transport.py:92` |
| 4 | `RetryPolicy.max_retries` 语义 | "首次之后的重试次数"（`safe_executor.py: for attempt in range(max_retries + 1)`）。本方案不复用 RetryPolicy，用 `delegate_max_attempts: int`（总次数），无换算问题 | `safe_executor.py` |
| 5 | `DelegateOperation` 构造调用点 | `action_catalog.py:90`，在 `assembly.py:231` 的 `assemble_agent()` 内调用，先于 `assemble_team()`。不需要构造注入 `retry_policy`——走 state 管道 | `action_catalog.py`/`assembly.py`/`api.py` |
| 6 | `AgentState` 序列化 | `snapshot()` 只存 `state_ref` 指针，无字段级序列化。新增字段不影响 checkpoint | `contracts/state.py` |
| 7 | ADR-0015 purity gate | `_is_enum_class` 检查在 dataclass 检查前 return，Enum 完全豁免。但本方案仍选模块级函数（不改 Enum） | `tests/test_contracts_purity.py` |
| 8 | member_status wiring 路径 | `TeamOrchestrator._create_member_status → TeamContext → HierarchicalStrategy → RunContext → runtime_loop → AgentState`。`TeamConfig` 本身没有 `member_status` 字段 | `team_orchestrator.py`/`hierarchical.py`/`runtime_loop.py` |
| 9 | `InMemoryMemberStatus` 构造点 | `TeamOrchestrator._create_member_status`（`team_orchestrator.py:79`），传入 `frozenset(m.role_profile.role for m in members)`。`members` 是 `list[CognitiveAgent]`，有序 | `team_orchestrator.py` |

---

## 11. 落地执行顺序

1. 新建 `contracts/role_status_rules.py`，写穷举单元测试。跑 `tests/test_contracts_purity.py` 确认门禁通过。
2. `contracts/ids.py` 追加 `remaining_seconds`/`elapsed_seconds`，写边界单元测试。
3. `contracts/member_status.py` Protocol 新增 `all_settled() -> bool` 签名。
4. `contracts/role_team.py` 的 `TeamConfig` 新增 `delegate_max_attempts: int = 3`。
5. `contracts/run_context.py` 的 `RunContext` 新增 `delegate_max_attempts: int = 3`。
6. `contracts/state.py` 的 `AgentState` 新增 `delegate_max_attempts: int = 3` 和 `delegate_attempts: dict[str, int] = field(default_factory=dict)`。
7. 改造 `layer1_cognitive/member_status/in_memory.py`（Fix 4 + Fix 1 + `all_settled`），更新构造调用点 `team_orchestrator.py:79`（`frozenset(...)` → `tuple(...)`），补齐对应测试。
8. 新建 `layer1_cognitive/member_status/policy.py`（`RequiredAction` + `compute_required_action`），写单元测试。
9. 改造 `layer1_cognitive/member_status/tracking.py`（拆出 `_next_role_status`，从 `state.delegate_max_attempts` 读上限），写单元测试。
10. 改造 `layer1_cognitive/brain/decision_gates/must_consult_all.py`（用 `compute_required_action` 重写 `enforce()`），写单元测试。
11. 改造 `layer1_cognitive/body/action_handlers.py`：
    - deadline 计算（Fix 2 + 提前短路）
    - `_wait_for_result` 删除 poll 回退，收敛为 `transport.wait_result` 直接调用 + TimeoutError 分支
    - `_send_to_transport` 包 `except (ValueError, NotImplementedError)` → `ToolExecutionError(retryable=False)`
    - 删除 `_POLL_INTERVAL_S` 常量
12. 改造 `layer0_infra/transport/agent_transport.py`：`_fail_observation` 在 agent-not-found 路径标注 `FAILURE_KIND_VALIDATION`。
13. 改造 wiring（3 处字段复制）：
    - `hierarchical.py`：`RunContext(..., delegate_max_attempts=context.config.delegate_max_attempts)`
    - `runtime_loop.py`：`AgentState(..., delegate_max_attempts=ctx.delegate_max_attempts if ctx else 3)`
14. 全量跑 `ruff check --fix && ruff format && lint-imports && mypy lca && pytest && vulture lca --min-confidence 80`。
15. 撰写 ADR-0025，归档。

---

## 12. ADR 骨架

`docs/adr/0025-role-settlement-retry-and-deadline-clock-domain.md`

```markdown
# ADR-0025: 角色结算状态、委派重试与 deadline 时钟域

## Status
Proposed

## Context
- MemberStatus 只有 DONE/非DONE 一根轴,FAILED 角色被反复委派(问题A)。
- delegate 超时计算混用 wall-clock 与 monotonic 时钟(问题B)。
- MustConsultAllMembers 只单向拦截 RESPOND,DELEGATE 可绕过(问题C)。
- InMemoryMemberStatus.required_roles 用 frozenset,消费顺序不确定(问题D)。
- _wait_for_result 的 poll 回退是死代码且为 A2ATransport 正确逻辑的反转副本。

## Decision
- 新增 all_settled(),settled/done 分类收敛到 contracts/role_status_rules.py。
- 新增 contracts/ids.py: remaining_seconds/elapsed_seconds,类型安全 wall-clock。
- gate 裁决收敛到 layer1_cognitive/member_status/policy.py 的 compute_required_action()。
- InMemoryMemberStatus 内部改用 role_order: tuple[str,...] 保证顺序确定性。
- 重试逻辑保留在 tracking.py + AgentState.delegate_attempts,不上 Board Protocol。
- delegate_max_attempts 通过 TeamConfig → RunContext → AgentState 管道传递。
- 删除 _wait_for_result 的 poll 回退分支(死代码 + 反转副本)。
- delegate 失败路径统一产出 failure_kind:
  - timeout → TRANSIENT
  - agent-not-found → VALIDATION(transport 层标注)
  - transport config 不可解析 → ToolExecutionError(retryable=False)
  - member 执行失败 → EXECUTION(默认 fallback)
- gate 范围限定为 RESPOND/DELEGATE,HANDOFF/USE_TOOL 显式 out-of-scope。

## Consequences
- Board Protocol 从 6 方法增至 7(+all_settled),向后兼容。
- 第三方 MemberStatus 实现需补 all_settled()。
- TeamConfig/RunContext/AgentState 各新增一个 int 字段(带默认值,向后兼容)。
- InMemoryMemberStatus 构造参数从 required_roles:frozenset 改为 role_order:tuple
  (Protocol 签名不变,实现变了)。
- delegate 失败路径统一产出 failure_kind,Critic 可正确区分。
- _wait_for_result 不再有 poll 回退;若第三方 transport 不实现 wait_result,
  属于 Protocol 不合规,框架不再兜底。
```

---

## 附录：新增/修改文件一览

```
新增:
  lca/contracts/role_status_rules.py
  lca/layer1_cognitive/member_status/policy.py
  docs/adr/0025-role-settlement-retry-and-deadline-clock-domain.md

修改:
  lca/contracts/ids.py                                   — +remaining_seconds, +elapsed_seconds
  lca/contracts/member_status.py                         — +all_settled() 签名
  lca/contracts/role_team.py                             — TeamConfig +delegate_max_attempts
  lca/contracts/run_context.py                           — RunContext +delegate_max_attempts
  lca/contracts/state.py                                 — AgentState +delegate_max_attempts, +delegate_attempts
  lca/layer1_cognitive/member_status/in_memory.py        — role_order 替代 frozenset 迭代,判据改用 role_status_rules,+all_settled
  lca/layer1_cognitive/member_status/tracking.py         — 拆出 _next_role_status,从 state 读 max_attempts
  lca/layer1_cognitive/brain/decision_gates/must_consult_all.py — 用 compute_required_action 重写 enforce()
  lca/layer1_cognitive/body/action_handlers.py            — deadline 短路/FAILURE_KIND 标注/删除 poll 回退/删除 _POLL_INTERVAL_S
  lca/layer0_infra/transport/agent_transport.py           — _fail_observation 标注 FAILURE_KIND_VALIDATION
  lca/layer3_agent/orchestration_strategies/hierarchical.py — RunContext 传入 delegate_max_attempts
  lca/layer2_runtime/runtime_loop.py                      — AgentState 传入 delegate_max_attempts
  lca/layer3_agent/team_orchestrator.py                   — _create_member_status 传 role_order 替代 required_roles
```
