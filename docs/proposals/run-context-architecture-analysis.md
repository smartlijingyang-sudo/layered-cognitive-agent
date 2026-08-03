# RunContext 架构分析：通用调用参数 vs 团队协调状态的职责边界

> **状态（2026-08-03）**：已被 [ADR-0026](../adr/0026-supervisor-first-class-consultation.md)
> 取代并落地。根因不是「字段平铺」 alone，而是 Supervisor 控制面缺少一等组合边界。
> 实现：`ConsultationState` + `SupervisorReasoner` + 组装期 `_bind_supervisor` 提升；
> 删除 `RoleMode` 与扁平 team 字段。本文档保留作问题考古，勿按方案 A 单独实施。

> **目的（历史）**：本文档为独立评估 agent 提供完整的上下文，分析 `RunContext` 将
> 通用调用元数据与团队协调状态混放在同一扁平 dataclass 中所导致的职责边界
> 模糊问题，并给出可选的架构改进方案及业界参考。
>
> **读者**：架构评审 / 重构评估 agent。不需要先验了解 LCA 代码库——本文档
> 包含全部相关源码和设计决策背景。

---

## 1. 问题陈述

`RunContext` 是 LCA 框架中 Agent / Team 统一 `run()` 入口的类型化上下文
dataclass，替代旧的 `**context: str` 自由字典。当前定义如下：

```python
# lca/contracts/run_context.py
@dataclass
class RunContext:
    """Metadata for a single ``run`` invocation."""

    trace_id: str | None = None  # ← 通用调用元数据
    from_role: str = ""  # ← 团队协调（委派者身份）
    member_status: MemberStatus | None = None  # ← 团队协调（咨询进度）
    teammates: list[RoleProfile] = ...  # ← 团队协调（队友画像）
    role_mode: RoleMode = RoleMode.SOLO  # ← 团队协调（角色模式）
    context_refs: list[str] = ...  # ← 通用调用元数据
    deadline: datetime | None = None  # ← 通用调用元数据
    delegate_max_attempts: int = 3  # ← 团队协调（重试上限）
    extra: dict[str, Any] = ...  # ← 通用扩展点
```

**核心问题**：两种不同生命周期的关注点被压平到同一层级：

| 关注点 | 生命周期 | 可变性 | 当前字段 |
|---|---|---|---|
| **调用元数据** | 一次 `run()` 调用 | 不可变 | `trace_id`, `deadline`, `context_refs` |
| **团队协调状态** | 整个认知循环 | 可变（循环中改） | `member_status`, `teammates`, `role_mode`, `from_role`, `delegate_max_attempts` |

两者都被塞进 `RunContext`（声称不可变 dataclass），然后又被复制进 `AgentState`
（可变容器）。`member_status` 在 `RunContext` 里是一个引用，在循环中
`update_member_status()` 会替换它——这个可变性不在类型签名上可见。

---

## 2. 完整代码上下文

### 2.1 RunContext 定义

```python
# lca/contracts/run_context.py
"""RunContext — typed metadata for one Agent/Team ``run`` call."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from lca.contracts.enums import RoleMode
from lca.contracts.member_status import MemberStatus
from lca.contracts.role_team import RoleProfile


@dataclass
class RunContext:
    """Metadata for a single ``run`` invocation.
    Replaces free-form ``**context: str`` and the old InvocationContext name.
    """

    trace_id: str | None = None
    from_role: str = ""
    member_status: MemberStatus | None = None
    teammates: list[RoleProfile] = field(default_factory=list)
    role_mode: RoleMode = RoleMode.SOLO
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    delegate_max_attempts: int = 3
    extra: dict[str, Any] = field(default_factory=dict)
```

### 2.2 AgentState（循环内部状态容器）

```python
# lca/contracts/state.py
@dataclass
class AgentState:
    """Full state for one agent cognitive loop."""

    trace_id: str
    task: str
    budget: Budget
    schema_version: str = "1.0"
    working_memory: dict[str, Any] = field(default_factory=dict)
    retrieved_context: list[Any] = field(default_factory=list)
    step: int = 0
    checkpoints: list[StateSnapshot] = field(default_factory=list)
    status: TaskStatus = TaskStatus.WORKING
    extra: dict[str, Any] = field(default_factory=dict)
    # ── team 字段散落在通用字段列表中 ──
    agent_role: str = ""
    from_role: str = ""
    member_status: MemberStatus | None = None
    role_mode: RoleMode = RoleMode.SOLO
    teammates: list[RoleProfile] = field(default_factory=list)
    history: list[Turn] = field(default_factory=list)
    delegate_max_attempts: int = 3
    delegate_attempts: dict[str, int] = field(default_factory=dict)
    final_output: Any | None = None
    last_error: str | None = None
    active_template: str | None = None
```

注意：`from_role`、`member_status`、`role_mode`、`teammates`、`delegate_max_attempts`
这 5 个 team 字段与 `trace_id`、`budget`、`history` 等通用字段平铺在同一层级，
没有结构性边界。

### 2.3 AgentUnit / TeamUnit 协议（入口签名）

```python
# lca/contracts/protocols/agent.py
@runtime_checkable
class AgentUnit(Protocol):
    """Single-agent entry: run / resume / cancel."""

    role_profile: RoleProfile

    async def run(
        self,
        task: str | AgentMessage,
        ctx: RunContext | None = None,
    ) -> Result: ...

    async def resume(
        self, snapshot: StateSnapshot, input: str | AgentMessage | None = None
    ) -> Result: ...

    async def cancel(self) -> None: ...


@runtime_checkable
class TeamUnit(Protocol):
    """Team entry: run an objective end-to-end."""

    async def run(self, objective: str | AgentMessage) -> Result: ...
```

设计约束：`AgentUnit.run` 签名对所有 agent（solo / supervisor / member）
统一。solo agent 传 `ctx=None`；team 中的 agent 传带 team 字段的 ctx。

### 2.4 CognitiveAgent（AgentUnit 实现）

```python
# lca/layer3_agent/simple_agent.py
class CognitiveAgent(AgentUnit):
    """Runtime + RoleProfile as a schedulable unit with run / resume / cancel."""

    def __init__(
        self,
        runtime: Runtime,
        role_profile: RoleProfile,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
    ) -> None:
        self.runtime = runtime
        self.role_profile = role_profile
        self.max_steps = max_steps
        self.max_wall_clock_seconds = max_wall_clock_seconds

    async def run(
        self,
        task: str | AgentMessage,
        ctx: RunContext | None = None,
    ) -> Result:
        text = _task_as_text(task)
        return await self.runtime.run(
            text,
            ctx,
            max_steps=self.max_steps,
            max_wall_clock_seconds=self.max_wall_clock_seconds,
            agent_role=self.role_profile.role,
        )
```

CognitiveAgent 是薄封装——将 `ctx` 透传给 `CognitiveRuntime.run`。

### 2.5 CognitiveRuntime（认知循环，RunContext → AgentState 的解包点）

```python
# lca/layer2_runtime/runtime_loop.py
class CognitiveRuntime(Runtime):
    async def run(
        self,
        task: str,
        ctx: RunContext | None = None,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
        agent_role: str = "",
    ) -> Result:
        state = AgentState(
            trace_id=(ctx.trace_id if ctx and ctx.trace_id else new_id("trace")),
            task=task,
            budget=create_budget(
                max_steps=max_steps, max_wall_clock_seconds=max_wall_clock_seconds
            ),
            agent_role=agent_role,
            from_role=(ctx.from_role if ctx else ""),  # team
            member_status=(ctx.member_status if ctx else None),  # team
            role_mode=(ctx.role_mode if ctx else RoleMode.SOLO),  # team
            teammates=list(ctx.teammates) if ctx else [],  # team
            delegate_max_attempts=(ctx.delegate_max_attempts if ctx else 3),  # team
        )
        await self.hooks.trigger("on_start", state)
        return await self._loop(state, max_steps)

    async def _loop(self, state: AgentState, max_steps: int) -> Result:
        """perceive → think → act → reflect → record → checkpoint → judge"""
        decision = observation = reflection = None
        for step in range(state.step, max_steps):
            state.step = step
            state.budget.used_steps = step
            try:
                # Phase 1: Perceive
                state = await self.memory.perceive(state)
                # Phase 2: Think
                decision = await self.brain.think(state)
                # Phase 3: Act
                observation = await self.body.act(decision, state)
                # Phase 4: Reflect
                reflection = await self.brain.reflect(state, observation)
                # Phase 5: Record
                state.history.append(
                    Turn(decision=decision, observation=observation, reflection=reflection)
                )
                await self.memory.update(state, observation, reflection)
            except ApprovalPendingError:
                await self._checkpoint(state, reason=SnapshotReason.PRE_APPROVAL)
                state.status = TaskStatus.INPUT_REQUIRED
                return Result.from_state(state)
            except Exception as err:
                _log.exception("unexpected_loop_error", step=step, error=str(err))
                state.status = TaskStatus.FAILED
                await self._checkpoint(state, reason=SnapshotReason.ON_ERROR)
                state.last_error = str(err)
                break
            # Phase 6: Checkpoint
            await self._checkpoint(state)
            # Phase 7: Judge
            signal = self.judge.decide(state, decision, observation, reflection)
            if signal.should_stop:
                if signal.reason == StopReason.BUDGET_EXCEEDED:
                    await self.hooks.trigger("on_error", state, error=BudgetExceededError())
                if signal.status is not None:
                    state.status = signal.status
                break
        await self.hooks.trigger("on_complete", state)
        return Result.from_state(state)
```

**关键观察**：`run()` 方法逐字段从 `ctx` 解包到 `AgentState`。5 个 team
字段与 `trace_id` 一起被复制——没有任何结构边界标识"这组字段属于同一关注点"。

### 2.6 TeamOrchestrator（组装阶段）

```python
# lca/layer3_agent/team_orchestrator.py
class TeamOrchestrator(TeamUnit):
    """Resolve process strategy, inject shared memory, bind supervisor setup."""

    def __init__(
        self,
        members: list[CognitiveAgent],
        config: TeamConfig,
        *,
        registries: Registries,
        supervisor: CognitiveAgent | None = None,
        transport: AgentTransport | None = None,
        teammates: list[RoleProfile] | None = None,
        role_mode: RoleMode = RoleMode.SOLO,
        strategy: TeamProcessStrategy | None = None,
        team_id: str = "",
    ) -> None:
        self.members = members
        self.config = config
        self.supervisor = supervisor
        self.transport = transport
        self.teammates = teammates or []
        self.role_mode = role_mode
        self.team_id = team_id or f"team-{config.process}"

        if strategy is not None:
            self._strategy = strategy
        else:
            self._strategy = registries.orchestration.resolve(config.process)

        self._shared_store: SharedMemoryStore | None = None
        if config.shared_memory_layers:
            self._shared_store = TeamSharedMemoryStore(config.shared_memory_layers)
            self._inject_shared_memory()

        member_status: MemberStatus | None = None
        if supervisor is not None:
            member_status = self._create_member_status(members, registries)
            policy = self._resolve_decision_gate(config, registries)
            self._bind_supervisor(supervisor, transport, policy)

        self._context = TeamContext(
            members=members,
            config=config,
            supervisor=supervisor,
            transport=transport,
            teammates=self.teammates,
            role_mode=self.role_mode,
            member_status=member_status,
        )

    @staticmethod
    def _bind_supervisor(
        supervisor: CognitiveAgent,
        transport: AgentTransport | None,
        policy: DecisionGate | None,
    ) -> None:
        """Bind supervisor capabilities at composition time.
        Wires channel and decision gate — the bindings that make an
        agent act as a hierarchical supervisor. Teammates text flows
        through RunContext → AgentState at run time, not here.
        """
        rt = supervisor.runtime
        if not isinstance(rt, HasBrainBodyMemory):
            return
        if transport is not None and isinstance(rt.body, HasChannel):
            rt.body.bind_channel(transport)
        if policy is not None and isinstance(rt.brain, SupportsDecisionGate):
            rt.brain.install_decision_gate(policy)

    async def run(self, objective: str | object) -> Result:
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        return await self._strategy.run(self._context, text)
```

**关键观察**：`TeamOrchestrator` 构造 `TeamContext`（持有 team 信息），
然后委托给 `TeamProcessStrategy.run(context, objective)`。Team 信息在此阶段
**不注入到 agent** —— 策略层在运行时才构造 `RunContext`。

### 2.7 TeamContext（策略层上下文）

```python
# lca/contracts/protocols/orchestration.py
@dataclass
class TeamContext:
    """Strategy runtime context."""

    members: list[AgentUnit] = field(default_factory=list)
    config: TeamConfig | None = None
    supervisor: AgentUnit | None = None
    transport: AgentTransport | None = None
    teammates: list[RoleProfile] = field(default_factory=list)
    role_mode: RoleMode = RoleMode.SOLO
    member_status: MemberStatus | None = None
```

### 2.8 TeamConfig / RoleProfile（配置层）

```python
# lca/contracts/role_team.py
@dataclass
class RoleProfile:
    """Agent 角色画像：goal / backstory / 工具权限 / 语气价值观。"""

    role: str
    goal: str
    backstory: str
    tool_permission_manifest: ToolPermissionManifest
    tone: str | None = None
    values: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamConfig:
    """团队编排配置：过程模式 + 共享记忆层 + 收尾策略。"""

    process: TeamProcess
    shared_memory_layers: list[MemoryLayer] = field(default_factory=list)
    max_rounds: int | None = None
    graph_definition_ref: str | None = None
    decision_gate: DecisionGateName = DecisionGateName.MUST_CONSULT_ALL
    delegate_max_attempts: int = 3
```

### 2.9 HierarchicalStrategy（RunContext 构造点）

```python
# lca/layer3_agent/orchestration_strategies/hierarchical.py
class HierarchicalStrategy(TeamProcessStrategy):
    """Supervisor-only path; member_status carried via RunContext."""

    async def run(self, context: TeamContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        ctx = RunContext(
            member_status=context.member_status,
            teammates=list(context.teammates),
            role_mode=RoleMode.SUPERVISOR,
            delegate_max_attempts=(context.config.delegate_max_attempts if context.config else 3),
        )
        return await context.supervisor.run(objective, ctx)
```

**关键观察**：这是 team 信息进入 `RunContext` 的**唯一入口**——策略层
从 `TeamContext` 提取字段，打包成 `RunContext`，传给 supervisor agent。

### 2.10 ChoreographyStrategy（非 hierarchical 模式的成员调用）

```python
# lca/layer3_agent/orchestration_strategies/choreography.py
class ChoreographyStrategy(TeamProcessStrategy):
    """External choreography with a topology dispatch table.
    Topologies: sequential / parallel / handoff / debate
    """

    async def run(self, context: TeamContext, objective: str) -> Result:
        runner = _DISPATCH.get(self._topology)
        return await runner(self, context, objective)

    @staticmethod
    async def _run_sequential(
        _self: ChoreographyStrategy, context: TeamContext, objective: str
    ) -> Result:
        return await invoke_members_sequential(
            context, objective, pass_output_as_next_task=True, stop_on_first_completed=False
        )

    @staticmethod
    async def _run_parallel(
        self: ChoreographyStrategy, context: TeamContext, objective: str
    ) -> Result:
        results = await asyncio.gather(
            *[invoke_member(context, m, objective) for m in context.members]
        )
        ...


# lca/layer3_agent/member_invoke.py
async def invoke_member(
    context: TeamContext,
    member: AgentUnit,
    objective: str,
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> Result:
    transport = context.transport
    if transport is not None:
        role = member.role_profile.role
        task_id = await transport.send_task(role, objective, [])
        observation = await transport.wait_result(task_id, timeout_s)
        return Result.from_observation(observation, task_id)
    return await _call_local(member, objective)  # member.run(objective), 无 ctx
```

**关键观察**：Choreography 模式（sequential/parallel/handoff/debate）调用
`invoke_member` 时**不传 RunContext**——`member.run(objective)` 无 ctx。
这些模式是外部编排，agent 不感知 team。只有 hierarchical 模式让 supervisor
agent 内部做委派决策，需要 team 信息进入认知循环。

### 2.11 SimpleReasoner（team 字段的消费方）

```python
# lca/layer1_cognitive/brain/reasoner.py
class SimpleReasoner(Reasoner):
    async def generate_candidates(self, state: AgentState, n: int = 1) -> list[str]:
        context_lines = (
            "\n".join(f"- [{r.memory_type.value}] {r.content}" for r in state.retrieved_context)
            or "(无历史上下文)"
        )
        base_vars = {
            "role": self.role_profile.role,
            "goal": self.role_profile.goal,
            "backstory": self.role_profile.backstory,
            "tools": self.tools_desc,
            "task": state.task,
            "context": context_lines,
            "allowed_actions": self.allowed_actions_desc,
        }
        template_name = self._resolve_template(state)
        if state.role_mode != RoleMode.SOLO:  # ← 散读 team 字段
            teammates_text = build_teammates_text(state.teammates)
            status_text = (
                state.member_status.as_prompt_text() if state.member_status is not None else ""
            )
            base_vars["teammates"] = teammates_text
            base_vars["member_status_text"] = status_text
        prompt = self._templates[template_name].format(**base_vars)
        ...

    def _resolve_template(self, state: AgentState) -> str:
        if state.active_template:
            return state.active_template
        if state.role_mode != RoleMode.SOLO:  # ← 又一次散读
            return _HIERARCHICAL_TEMPLATE
        return _DEFAULT_TEMPLATE
```

**关键观察**：Reasoner（L1 认知组件）直接读 `state.role_mode`、
`state.teammates`、`state.member_status`——这三个字段在 `AgentState`
的 20+ 字段里混在一起。如果未来新增 `debate_round` 或 `handoff_chain`，
Reasoner 要继续往 `if` 里加字段判断。

### 2.12 MemberStatus（团队咨询进度追踪）

```python
# lca/contracts/member_status.py
@runtime_checkable
class MemberStatus(Protocol):
    """Board of required member roles and their consult status."""

    @property
    def required_roles(self) -> frozenset[str]: ...
    @property
    def status(self) -> dict[str, RoleStatus]: ...
    def mark(self, role: str, new_status: RoleStatus) -> MemberStatus: ...
    def all_done(self) -> bool: ...
    def all_settled(self) -> bool: ...
    def waiting_roles(self) -> list[str]: ...
    def as_prompt_text(self) -> str: ...
```

### 2.13 update_member_status（循环内的可变操作）

```python
# lca/layer1_cognitive/member_status/tracking.py
def update_member_status(state: AgentState, decision: Decision, observation: Observation) -> None:
    """Update the member status board after a delegate action completes."""
    board = state.member_status  # ← 从 state 读
    if board is None or decision.delegate_to is None:
        return
    role = decision.delegate_to.target_role
    if role is None or role not in board.required_roles:
        return

    if observation.success:
        state.member_status = board.mark(role, RoleStatus.DONE)  # ← 写回 state
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

**关键观察**：`state.member_status` 在循环中被替换（`state.member_status = board.mark(...)`)。
`member_status` 是可变状态，但它的初始值通过 `RunContext`（不可变 dataclass）传入。

### 2.14 DelegateOperation（委派执行 + from_role 注入）

```python
# lca/layer1_cognitive/body/action_handlers.py
class DelegateOperation(Action):
    """处理 delegate 动作：阻塞式委派，等待目标 Agent 返回结果。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        transport, task_id = await self._send_to_transport(decision, state)
        spec = decision.delegate_to
        if spec and spec.deadline:
            timeout_s = remaining_seconds(spec.deadline)
            if timeout_s <= 0:
                observation = Observation(...)
                update_member_status(state, decision, observation)
                return observation
        else:
            timeout_s = _DEFAULT_DELEGATE_TIMEOUT_S
        observation = await self._wait_for_result(transport, task_id, timeout_s)
        update_member_status(state, decision, observation)
        observation.extra[OBS_TASK_ID] = task_id
        return observation

    async def _send_to_transport(self, decision: Decision, state: AgentState) -> ...:
        spec = decision.delegate_to
        transport = self._transport_registry.resolve(spec.protocol)
        agent_card = spec.target_agent_card or spec.target_agent_id or spec.target_role
        with delegator_scope(state.agent_role):  # ← from_role 的注入点
            task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)
        return transport, task_id
```

### 2.15 delegation_context.py（跨异步边界的委派者身份传播）

```python
# lca/contracts/delegation_context.py
"""跨异步边界传递"当前委派者角色"的显式上下文原语（ADR-0017）。
背景：AgentTransport.send_task 的签名要与 Google A2A 的 AgentCard 模型
保持一致，不能塞入 LCA 内部专用的委派身份字段；同时 send_task 内部用
asyncio.create_task 异步调度，调用点与 handler 执行点不在同一次 await 里，
无法用普通参数直接传递。因此选择 contextvars。
"""

from contextvars import ContextVar
from contextlib import contextmanager

_delegator: ContextVar[str] = ContextVar("current_delegator", default="")


def get_current_delegator() -> str:
    return _delegator.get()


@contextmanager
def delegator_scope(role: str):
    token = _delegator.set(role)
    try:
        yield
    finally:
        _delegator.reset(token)
```

### 2.16 assembly.py 中的 from_role 注入（channel 路径）

```python
# lca/layer4_app/assembly.py
async def _call_member_for_channel(member: CognitiveAgent, subtask: str) -> Observation:
    """Invoke a member for InternalTransport."""
    from lca.contracts.delegation_context import get_current_delegator
    from lca.contracts.run_context import RunContext

    from_role = get_current_delegator()  # ← 从 ContextVar 读取
    result = await member.run(subtask, RunContext(from_role=from_role))
    return Observation.from_result(result)
```

**关键观察**：`from_role` 的传播路径与其他 team 字段不同——它不通过
策略层构造，而是通过 `contextvars.ContextVar` 跨异步边界传递。这表明
`from_role` 的生命周期和注入机制与 `teammates`/`member_status` 不同，
但它们在 `RunContext` 中平铺在一起。

### 2.17 DecisionGate（MustConsultAllMembers）

```python
# lca/layer1_cognitive/brain/decision_gates/must_consult_all.py
class MustConsultAllMembers(DecisionGate):
    """Rewrite decisions that violate the 'all required roles must settle' invariant."""

    async def try_shortcut(self, state: AgentState) -> Decision | None:
        board = state.member_status  # ← 从 state 读 team 字段
        if board is None:
            return None
        waiting = board.waiting_roles()
        if len(waiting) != 1:
            return None
        return _delegate_decision(state.task, waiting[0], ...)

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        board = state.member_status  # ← 又一次从 state 读
        if board is None:
            return decision
        if decision.action_type not in (ActionType.RESPOND, ActionType.DELEGATE):
            return decision
        required = compute_required_action(board)
        if required.kind == "may_respond":
            if decision.action_type == ActionType.DELEGATE:
                return _respond_override("[框架强制] 所有必需角色已结算")
            return decision
        waiting_set = set(board.waiting_roles())
        already_correct = (
            decision.action_type == ActionType.DELEGATE
            and decision.delegate_to is not None
            and decision.delegate_to.target_role in waiting_set
        )
        if already_correct:
            return decision
        target = required.target_role
        if target is None:
            return decision
        return _delegate_decision(state.task, target, ...)
```

### 2.18 相关枚举

```python
# lca/contracts/enums.py
class RoleMode(str, Enum):
    """Agent 在团队中的角色模式——决定 prompt 模板和队友信息渲染。"""

    SOLO = "solo"
    SUPERVISOR = "supervisor"
    MEMBER = "member"


class RoleStatus(str, Enum):
    """团队委派进度状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class TeamProcess(str, Enum):
    HIERARCHICAL = "hierarchical"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    GRAPH = "graph"
    DEBATE = "debate"
    HANDOFF = "handoff"
```

---

## 3. 完整数据流图

### 3.1 Team 信息传递管道（hierarchical 模式）

```
TeamConfig (contracts, 配置层)
  │  delegate_max_attempts, decision_gate, shared_memory_layers, ...
  │
  ▼  TeamOrchestrator.__init__ 构造时读取
TeamContext (protocols/orchestration.py, 策略层运行时上下文)
  │  teammates, role_mode, member_status, supervisor, transport, members
  │
  ▼  HierarchicalStrategy.run() 构造 RunContext
RunContext (contracts/run_context.py, 一次 run 调用的元数据)
  │  member_status, teammates, role_mode, delegate_max_attempts
  │
  ▼  CognitiveAgent.run(task, ctx) → CognitiveRuntime.run(task, ctx)
AgentState (contracts/state.py, 认知循环内部状态)
  │  member_status, teammates, role_mode, delegate_max_attempts, delegate_attempts
  │
  ▼  贯穿 perceive → think → act → reflect → record → checkpoint → judge
  │
  ├─→ SimpleReasoner.generate_candidates: 读 role_mode/teammates/member_status 构建 prompt
  ├─→ MustConsultAllMembers.enforce/try_shortcut: 读 member_status 决策门裁决
  ├─→ DelegateOperation.execute: 读 agent_role 做 delegator_scope，写 member_status
  └─→ update_member_status: 读 delegate_max_attempts/delegate_attempts，写 member_status
```

### 3.2 from_role 的特殊路径

```
DelegateOperation._send_to_transport
  │  with delegator_scope(state.agent_role):  # 写 ContextVar
  │      transport.send_task(...)
  │
  ▼  asyncio.create_task 拷贝 Context
InternalTransport handler (assembly.py)
  │  from_role = get_current_delegator()      # 读 ContextVar
  │  member.run(subtask, RunContext(from_role=from_role))
  │
  ▼
AgentState.from_role = ctx.from_role
```

### 3.3 Choreography 模式（不注入 team 信息）

```
ChoreographyStrategy.run(context, objective)
  │
  ├─→ invoke_member(context, member, objective)
  │     └─→ member.run(objective)            # 无 RunContext，agent 不知道 team
  │
  └─→ invoke_members_sequential(context, objective, ...)
        └─→ invoke_member(...) → member.run(output_of_previous)
```

---

## 4. 设计决策历史

### 4.1 glossary.md 中的定义

> **RunContext** — 一次 `run` 的类型化上下文（from_role / member_status / trace_id）

> **禁止复活**：
> - Agent 入口签名带 `**context: str`（用 `RunContext` 类型化上下文替代）
> - progress-text 字段 + 注入 hook 三件套（用 `MemberStatus` 替代）

### 4.2 ADR-0024（Registries 值对象）

> Teammates text flows through RunContext → AgentState at run time, not here.

——supervisor 绑定 channel 和 decision gate 在构造时，但 teammates 文本
在运行时通过 RunContext 注入。

### 4.3 ADR-0025（角色结算状态、委派重试与 deadline）

> `delegate_max_attempts` 通过 `TeamConfig → TeamContext → RunContext → AgentState`
> 既有管道传递，与 `member_status`、`teammates`、`role_mode` 走同一条路。

设计约束：重试参数走既有 state 管道，不新增构造注入路径。

> `TeamConfig`/`RunContext`/`AgentState` 各新增一个带默认值的字段，向后兼容。

---

## 5. 问题分析

### 5.1 职责边界不可见

`RunContext` 的 docstring 声称自己是 "Metadata for a single `run` invocation"，
但实际包含 5 个 team 字段。阅读者无法从类型签名判断哪些字段是通用的、
哪些是 team 专有的。

### 5.2 AgentState 字段膨胀且无结构

`AgentState` 有 20+ 个字段，其中 5 个是 team 字段，散落在 `trace_id`、
`budget`、`history` 之间。认知循环的每个消费方（Reasoner、DecisionGate、
DelegateOperation、tracking.py）都在 `AgentState` 上做 **散点读取**——
各取所需，但没有统一的 "if this agent is in a team" 守卫。

### 5.3 可变性语义不一致

- `teammates`: 不可变（构造后不改）
- `member_status`: 可变（`update_member_status` 在循环中替换）
- `delegate_attempts`: 可变（在循环中递增）
- `from_role`: 不可变（一次性设置）
- `role_mode`: 不可变
- `delegate_max_attempts`: 不可变

5 个 team 字段有 3 种可变性语义，但都在同一个 dataclass 里，类型签名
不区分。

### 5.4 扩展时的传染性

如果未来新增一个 team 协调字段（如 `debate_round: int` 或
`handoff_chain: list[str]`），需要：
1. `TeamConfig` 加字段
2. `TeamContext` 加字段
3. `RunContext` 加字段
4. `AgentState` 加字段
5. `CognitiveRuntime.run` 加一行解包
6. 消费方（Reasoner/Gate/tracking）加读取逻辑

前 4 步是机械复制，第 5 步是 `run()` 方法里又一个 `if ctx` 行——
`run()` 会变成一个不断增长的解包列表。

### 5.5 from_role 的注入路径与其他 team 字段不同

`from_role` 通过 `contextvars.ContextVar` 跨异步边界传播（见
`delegation_context.py`），而 `teammates`/`member_status`/`role_mode`
通过策略层构造 `RunContext` 传入。两种注入机制在 `RunContext` 中被压平
到同一层级，掩盖了它们不同的生命周期。

---

## 6. 业界参考

### 6.1 外部编排模式（CrewAI / AutoGen / LangGraph）

最常见的做法是 **agent 不感知 team**：

- **CrewAI**: `Crew.run()` 调度 `Agent.execute_task()`，agent 收到 task +
  可选 context，不知道 crew 结构
- **AutoGen**: `GroupChatManager` 管理发言权，`ConversableAgent` 只看到消息
- **LangGraph**: 状态图携带所有 state，node 函数访问 state 字段，但 state
  是扁平 dict

**LCA 不能走这条路**：supervisor agent 的 Brain 需要 think→delegate→reflect，
需要知道"有哪些队友""谁还没被咨询"。这是 LCA 的刻意设计选择——supervisor
IS an agent that reasons about delegation——但它引入了协调状态必须在认知循环
内可见的需求。

### 6.2 Context 传播模式（OpenTelemetry / gRPC）

通用上下文对象携带跨切面数据，每个子系统拥有自己的条目类型。核心原则：
**context 是通用载体，但每个子系统只读写自己拥有的 key**。

### 6.3 环境/能力注入模式（Actor Model / Spring DI / Temporal）

把"我是谁"和"我周围有什么"与"我要做什么"分离：
- **Akka**: Actor 在构造时拿到 self 和 context（parent/sender），消息只携带 task
- **Temporal**: Workflow context（持久、可重放）与 Activity context（短暂）分离
- **Spring**: Bean 在构造时注入依赖，方法只接收调用参数

---

## 7. 可选改进方案

### 方案 A：嵌套组合 + 显式命名空间（推荐，最小改动）

把 5 个 team 字段收进一个独立类型，`RunContext` 用一个 nullable 字段引用：

```python
# contracts/coordination.py（新文件）
@dataclass
class TeamCoordination:
    """团队协调上下文——仅在 agent 运行于团队中时存在。

    与 RunContext（调用元数据）和 AgentState（循环状态）并列，
    通过 nullable 字段注入，边界在类型层面可见。
    """

    from_role: str = ""
    member_status: MemberStatus | None = None
    teammates: list[RoleProfile] = field(default_factory=list)
    role_mode: RoleMode = RoleMode.SOLO
    delegate_max_attempts: int = 3


# contracts/run_context.py（改后）
@dataclass
class RunContext:
    """Per-invocation metadata — generic for all agents, no team fields."""

    trace_id: str | None = None
    deadline: datetime | None = None
    context_refs: list[str] = field(default_factory=list)
    coordination: TeamCoordination | None = None  # ← 显式 nullable 命名空间
    extra: dict[str, Any] = field(default_factory=dict)


# contracts/state.py（改后）
@dataclass
class AgentState:
    trace_id: str
    task: str
    budget: Budget
    agent_role: str = ""
    coordination: TeamCoordination | None = None  # ← 一个字段替代 5 个散落字段
    history: list[Turn] = field(default_factory=list)
    working_memory: dict[str, Any] = field(default_factory=dict)
    delegate_attempts: dict[str, int] = field(default_factory=dict)
    # ... 其他通用字段


# runtime_loop.py — 从 ctx 解包到 state 的地方
state = AgentState(
    trace_id=...,
    task=task,
    budget=...,
    agent_role=agent_role,
    coordination=ctx.coordination if ctx else None,  # ← 一行，边界清晰
)
```

**消费方改动示例**：

```python
# reasoner.py — 改前
if state.role_mode != RoleMode.SOLO:
    teammates_text = build_teammates_text(state.teammates)
    status_text = state.member_status.as_prompt_text() if state.member_status ...

# reasoner.py — 改后
coord = state.coordination
if coord is not None and coord.role_mode != RoleMode.SOLO:
    teammates_text = build_teammates_text(coord.teammates)
    status_text = coord.member_status.as_prompt_text() if coord.member_status ...

# tracking.py — 改前
board = state.member_status
max_attempts = state.delegate_max_attempts

# tracking.py — 改后
coord = state.coordination
if coord is None:
    return
board = coord.member_status
max_attempts = coord.delegate_max_attempts

# must_consult_all.py — 改前
board = state.member_status

# must_consult_all.py — 改后
coord = state.coordination
board = coord.member_status if coord else None
```

**HierarchicalStrategy 改动**：

```python
# hierarchical.py — 改后
ctx = RunContext(
    coordination=TeamCoordination(
        member_status=context.member_status,
        teammates=list(context.teammates),
        role_mode=RoleMode.SUPERVISOR,
        delegate_max_attempts=(context.config.delegate_max_attempts if context.config else 3),
    ),
)
return await context.supervisor.run(objective, ctx)
```

**assembly.py 的 channel 路径改动**：

```python
# assembly.py — 改后
result = await member.run(subtask, RunContext(coordination=TeamCoordination(from_role=from_role)))
```

**影响矩阵**：

| 文件 | 改动量 | 改动内容 |
|---|---|---|
| `contracts/coordination.py` | 新文件 | `TeamCoordination` dataclass |
| `contracts/run_context.py` | 删 5 字段 + 加 1 | `coordination: TeamCoordination \| None` |
| `contracts/state.py` | 删 5 字段 + 加 1 | `coordination: TeamCoordination \| None` |
| `runtime_loop.py` | 1 行 | `coordination=ctx.coordination if ctx else None` |
| `hierarchical.py` | 包一层 | `RunContext(coordination=TeamCoordination(...))` |
| `reasoner.py` | 3 行 | `coord = state.coordination; if coord is not None:` |
| `tracking.py` | 2 行 | `coord = state.coordination; if coord is None: return` |
| `must_consult_all.py` | 2 行 | `coord = state.coordination; board = coord.member_status if coord else None` |
| `assembly.py` | 1 行 | `RunContext(coordination=TeamCoordination(from_role=from_role))` |
| 测试文件 | ~10 处 | `RunContext(role_mode=...)` → `RunContext(coordination=TeamCoordination(role_mode=...))` |

**优势**：
- 边界在类型签名上可见
- solo agent: `coordination=None`，语义是"无团队上下文"
- 消费方统一入口：`state.coordination`，grep 一次找到所有 team 依赖
- 新增 team 字段只改 `TeamCoordination`，不碰 `RunContext`/`AgentState`
- `AgentUnit.run` 签名不变
- `from_role` 的不同注入路径仍然统一在 `TeamCoordination` 下

**代价**：
- 测试文件需要批量调整构造方式
- `TeamCoordination` 是新类型，增加了一层间接

### 方案 B：分离参数（Protocol 签名变更）

在 `AgentUnit.run` 签名中增加 keyword-only 参数：

```python
async def run(
    self,
    task: str | AgentMessage,
    ctx: RunContext | None = None,
    *,
    coordination: TeamCoordination | None = None,
) -> Result: ...
```

**优势**：RunContext 完全不含 team 字段
**代价**：Protocol 签名变更，所有 `Runtime.run` 实现也要加参数
**适用**：如果团队认为 RunContext 必须绝对纯净

### 方案 C：ContextVar 环境上下文（不推荐）

所有 team 字段放 ContextVar，类似 `delegation_context.py` 已做的 `from_role`。

**不推荐原因**：
- `member_status`、`teammates` 是结构化可变对象，ContextVar 让依赖隐式化
- `resume()` 恢复状态时 ContextVar 不会自动恢复
- 测试困难（需要 set/reset token）
- `from_role` 用 ContextVar 是因为跨 asyncio.create_task 边界（ADR-0017），
  其他 team 字段没有这个需求

### 方案 D：继承分叉（不推荐）

```python
@dataclass
class RunContext: ...  # 通用


@dataclass
class TeamRunContext(RunContext): ...  # 加 team 字段
```

**不推荐原因**：
- Python dataclass 继承 + 默认值组合有已知陷阱（字段顺序约束）
- `AgentUnit.run` 签名变 `RunContext | TeamRunContext`，类型检查复杂

---

## 8. 评估维度

评估 agent 请从以下维度分析：

1. **职责清晰性**：改后 RunContext/AgentState 的字段是否属于同一关注点层？
2. **边界可见性**：新 reader 能否从类型签名判断 team 字段的存在和范围？
3. **扩展成本**：未来新增 team 协调字段时，需要改几个文件？
4. **可变性语义**：可变/不可变字段是否在结构上可区分？
5. **向后兼容**：改动是否破坏现有 API 消费方（AgentUnit.run 签名、测试）？
6. **from_role 特殊性**：from_role 的 ContextVar 路径与其他 team 字段不同，
   改后是否仍然合理？
7. **resume() 兼容**：`CognitiveRuntime.resume()` 从 StateStore 加载
   AgentState——coordination 字段是否需要特殊处理？
8. **与 ADR-0025 的兼容**：ADR-0025 说 `delegate_max_attempts` 走
   `TeamConfig → TeamContext → RunContext → AgentState` 管道。改后管道变成
   `TeamConfig → TeamContext → RunContext.coordination → AgentState.coordination`——
   是否需要更新 ADR？
9. **业界对齐度**：方案与业界主流模式（OpenTelemetry context、Actor model、
   DI 框架）的对齐程度如何？

---

## 附录 A：所有 team 字段的消费方汇总

| 字段 | 写入方 | 读取方 | 可变性 |
|---|---|---|---|
| `from_role` | `assembly.py` via ContextVar | (未在循环内消费，用于 tracing) | 不可变 |
| `member_status` | `HierarchicalStrategy` 初始注入; `tracking.py` 循环中替换 | `SimpleReasoner`; `MustConsultAllMembers`; `tracking.py` | **可变** |
| `teammates` | `HierarchicalStrategy` 初始注入 | `SimpleReasoner` (build_teammates_text) | 不可变 |
| `role_mode` | `HierarchicalStrategy` 初始注入 | `SimpleReasoner` (template 选择) | 不可变 |
| `delegate_max_attempts` | `HierarchicalStrategy` 从 TeamConfig 注入 | `tracking.py` (_next_role_status) | 不可变 |
| `delegate_attempts` | `tracking.py` 循环中递增 | `tracking.py` | **可变** |

## 附录 B：五层架构依赖约束

```
contracts → layer0_infra → layer1_cognitive → layer2_runtime → layer3_agent → layer4_app
```

- `RunContext` 在 contracts 层
- `TeamCoordination`（方案 A）也在 contracts 层
- `TeamContext` 在 contracts/protocols 层
- 消费方 `SimpleReasoner`/`MustConsultAllMembers` 在 layer1_cognitive
- `CognitiveRuntime` 在 layer2_runtime
- `HierarchicalStrategy`/`TeamOrchestrator` 在 layer3_agent
- `assembly.py` 在 layer4_app（组合根）

约束：下层不能 import 上层。`contracts` 层不能 import `layer1_cognitive`
或更高层。
