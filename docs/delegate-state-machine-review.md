# 层次团队委派状态机健壮性方案评审

> 自包含文档——无需任何对话上下文即可阅读。供架构决策分析使用。

---

## 1. 项目上下文

### 1.1 框架概况

LCA（Layered Cognitive Agent）是一个 Python LLM agent 框架，五层严格单向依赖：

```
contracts → layer0_infra → layer1_cognitive → layer2_runtime → layer3_agent → layer4_app
```

- `contracts`：纯类型与接口（Protocol / dataclass），不含行为类
- `layer1_cognitive`：认知循环（Brain/Body/Memory）
- `layer3_agent`：团队编排（TeamOrchestrator, hierarchical strategy）
- `layer4_app`：组合根（Assembly, defaults.py 注册表）

### 1.2 关键架构约束（AGENTS.md）

- 层间依赖只通过 `contracts` 层的 Protocol / dataclass 传递
- `contracts/` 仅保留类型与接口，参考实现必须放在实现层（ADR-0015）
- 同层模块间不直接 import，通过依赖注入获取协作方
- `@runtime_checkable` Protocol 新增方法不破坏 `isinstance` 检查（ADR-0014 前例）
- 新增外部集成必须走适配器，业务代码不直接调用第三方 SDK
- 团队数据流经 `RunContext → AgentState`，不通过组件实例 setter（feedback memory: "data through state, not setters"）

### 1.3 已有 ADR 先例

**ADR-0014：工具错误分类与重试语义**

定义了三种 `failure_kind`：
- `validation`：参数校验失败，重试无意义，fail-fast
- `execution`：工具执行失败，默认 fallback kind
- `transient`：瞬时性错误（网络等），可重试

这些值存在 `contracts/semantic_keys.py`：
```python
FAILURE_KIND = "failure_kind"
FAILURE_KIND_VALIDATION = "validation"
FAILURE_KIND_EXECUTION = "execution"
FAILURE_KIND_TRANSIENT = "transient"
```

`SimpleSafeExecutor`（`layer1_cognitive/body/safe_executor.py`）的 retry 循环只依赖两个信号：
1. `tool.validate(args)` 返回值——前置校验，失败不进入重试循环
2. 异常的 `retryable` 属性——`False` 则 fail-fast

`SimpleCritic`（`layer1_cognitive/brain/critic.py`）读取 `failure_kind` 生成差异化纠正提示。

ADR-0014 的结论之一："`@runtime_checkable` Protocol 新增带默认约定的方法不会破坏现有 isinstance 检查"——但这是针对 `Tool` Protocol 加 `validate()` 的结论。

**ADR-0015：contracts/ 仅保留类型与接口**

核心主张：Protocol 定义留在 `contracts/`，具体实现迁到实现层。禁止在 `contracts/` 内放行为类。非 Protocol 类必须是 `@dataclass` 且不含自定义方法（除 `__post_init__` / dunder）。

门禁：`tests/test_contracts_purity.py` AST 扫描 `lca/contracts/` 下所有类。

---

## 2. 问题陈述

层次团队（hierarchical team）的 Supervisor 通过 `MustConsultAllMembers` 决策门强制咨询所有必需角色后再回应。当前实现存在三个问题：

### 2.1 问题 A：settled/done 混淆（根因）

`MemberStatus` Board 只有一根轴——"是不是 DONE"。`waiting_roles()` 返回所有非 DONE 的角色（包括 PENDING 和 FAILED），`all_done()` 只有全员 DONE 才为 True。

后果：
- 角色失败后标为 `FAILED`，仍出现在 `waiting_roles()` 中
- `MustConsultAllMembers` 拦截 `RESPOND` 时用 `all_done()` 判断，FAILED 角色让 `all_done()` 永远为 False
- 但 gate 又用 `waiting_roles()[0]` 选下一个目标，可能选到已 FAILED 的角色，造成无限重试同一失败角色直到 Budget 耗尽

**本质**：缺少"全部已尝试"（settled）与"全部成功"（done）的区分。

### 2.2 问题 B：deadline 时钟域混用

`DelegateOperation.execute()` 计算超时：
```python
timeout_s = (
    (spec.deadline.timestamp() - asyncio.get_running_loop().time())
    if (spec := decision.delegate_to) and spec.deadline
    else _DEFAULT_DELEGATE_TIMEOUT_S
)
```

`spec.deadline.timestamp()` 返回 POSIX epoch 秒（wall-clock），`asyncio.get_running_loop().time()` 返回 monotonic clock（任意 epoch）。两者相减结果无意义（可能为负，可能为天文数字）。

对比 `Budget.exceeded()`：
```python
elapsed = (utc_now() - self.started_at).total_seconds()
```
两者都是 timezone-aware `datetime`，同 epoch，正确。

后果：`spec.deadline` 字段实际不生效——传给 `wait_result` 的 `timeout_s` 是垃圾值。

### 2.3 问题 C：决策门单向兜底

`MustConsultAllMembers.enforce()` 只拦截 `RESPOND`：
- LLM 决定 `DELEGATE` 给一个已经 DONE 的角色 → gate 放行，重复委派
- LLM 决定 `DELEGATE` 给一个终态 FAILED 的角色 → gate 放行，重复委派到已知失败的角色

后果：LLM 的原始决策可以直接绕过状态机约束，gate 只做了"防止提前收尾"这一半。

---

## 3. 当前代码实际状态

以下为评审时仓库 `main` 分支的实际代码（非假设）。

### 3.1 MemberStatus Protocol

文件：`lca/contracts/member_status.py`

```python
@runtime_checkable
class MemberStatus(Protocol):
    """Board of required member roles and their consult status."""

    @property
    def required_roles(self) -> frozenset[str]: ...

    @property
    def status(self) -> dict[str, RoleStatus]: ...

    def mark(self, role: str, new_status: RoleStatus) -> MemberStatus: ...

    def all_done(self) -> bool: ...

    def waiting_roles(self) -> list[str]: ...

    def as_prompt_text(self) -> str: ...
```

6 个成员：2 个只读 property（`required_roles`, `status`），4 个方法（`mark`, `all_done`, `waiting_roles`, `as_prompt_text`）。

### 3.2 InMemoryMemberStatus（唯一实现）

文件：`lca/layer1_cognitive/member_status/in_memory.py`

```python
@dataclass(frozen=True)
class InMemoryMemberStatus:
    required_roles: frozenset[str]
    status: dict[str, RoleStatus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 用 object.__setattr__ 在 frozen 实例上补种 PENDING
        for role in self.required_roles:
            if role not in self.status:
                self.status[role] = RoleStatus.PENDING

    def mark(self, role: str, new_status: RoleStatus) -> MemberStatus:
        new_status_dict = {**self.status, role: new_status}
        return InMemoryMemberStatus(self.required_roles, new_status_dict)

    def all_done(self) -> bool:
        return all(self.status.get(r) == RoleStatus.DONE for r in self.required_roles)

    def waiting_roles(self) -> list[str]:
        return [r for r in self.required_roles if self.status.get(r) != RoleStatus.DONE]

    def as_prompt_text(self) -> str:
        waiting = self.waiting_roles()
        if waiting:
            return f"尚未咨询的角色: {', '.join(waiting)}"
        return "所有必需角色均已咨询完毕"
```

关键点：`frozen=True`，`mark()` 返回新实例（不可变模式）。`waiting_roles()` 包含所有非 DONE 角色（PENDING + IN_PROGRESS + FAILED）。

### 3.3 update_member_status（独立函数，非 Protocol 方法）

文件：`lca/layer1_cognitive/member_status/tracking.py`

```python
def update_member_status(state: AgentState, decision: Decision, observation: Observation) -> None:
    """Update the member status board after a delegate action completes."""
    board = state.member_status
    if board is None or decision.delegate_to is None:
        return
    role = decision.delegate_to.target_role
    if role and role in board.required_roles:
        new_status = RoleStatus.DONE if observation.success else RoleStatus.FAILED
        state.member_status = board.mark(role, new_status)
```

简单二元判断：success → DONE，failure → FAILED。无重试逻辑。

模块 docstring 明确：这是"direct state update, not a hook"——由 `DelegateOperation.execute()` 直接调用，不是 POST_ACT hook。

### 3.4 DelegateOperation

文件：`lca/layer1_cognitive/body/action_handlers.py`

```python
class DelegateOperation(Action):
    """处理 delegate 动作：阻塞式委派，等待目标 Agent 返回结果。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        transport, task_id = await self._send_to_transport(decision, state)

        timeout_s = (
            (spec.deadline.timestamp() - asyncio.get_running_loop().time())
            if (spec := decision.delegate_to) and spec.deadline
            else _DEFAULT_DELEGATE_TIMEOUT_S
        )

        observation = await self._wait_for_result(transport, task_id, timeout_s)
        update_member_status(state, decision, observation)
        observation.extra[OBS_TASK_ID] = task_id
        return observation
```

三个失败路径：
1. **transport.send_task 失败（agent not found）**：`_send_to_transport` 中 `transport.send_task` 异常**不被捕获**，直接传播出 `execute()`。只有缺 `delegate_to` spec 和缺 target 两种情况被显式 `raise ToolExecutionError`。
2. **wait_result 超时**：被 `except TimeoutError` 捕获，转为 `Observation(success=False)`，但 extra 只设 `OBS_TASK_ID`，**不设 `FAILURE_KIND`**。
3. **member 执行失败**：以 `Observation(success=False)` 形式从 `wait_result` 返回。同样**不设 `FAILURE_KIND`**。

### 3.5 _wait_for_result 的 poll 回退路径（疑似 bug）

```python
async def _wait_for_result(self, transport, task_id, timeout_s) -> Observation:
    wait = getattr(transport, "wait_result", None)
    if wait is not None:
        try:
            return await wait(task_id, timeout_s)
        except TimeoutError:
            return Observation(success=False, error=f"delegate 超时: task_id={task_id}", ...)

    # 回退：跨进程 / 旧 transport 轮询
    elapsed = 0.0
    while (await transport.poll_status(task_id)) != TaskStatus.WORKING:
        if elapsed >= timeout_s:
            return Observation(success=False, error=f"delegate 超时: ...", ...)
        await asyncio.sleep(_POLL_INTERVAL_S)
        elapsed += _POLL_INTERVAL_S
    return await transport.receive_result(task_id)
```

轮询条件 `!= TaskStatus.WORKING` 意味着"状态不是 WORKING 时继续轮询，变成 WORKING 就退出并 receive_result"。但 WORKING 意味着"正在执行"而非"已完成"——逻辑疑似反转，应该是 `== WORKING`（等它做完）或 `not in (DONE, FAILED)`。

### 3.6 MustConsultAllMembers

文件：`lca/layer1_cognitive/brain/decision_gates/must_consult_all.py`

```python
class MustConsultAllMembers(DecisionGate):
    """Rewrite early respond into delegate until all required roles are done."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        board = state.member_status
        if board is None:
            return decision

        if decision.action_type == ActionType.RESPOND and not board.all_done():
            waiting = board.waiting_roles()
            next_role = waiting[0]
            return Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.DELEGATE,
                delegate_to=DelegationSpec(
                    target_role=next_role,
                    subtask=_infer_subtask(state.task, next_role),
                ),
                rationale="[框架强制] 尚有必需角色未咨询，禁止提前收尾",
                confidence=1.0,
            )
        return decision
```

只拦 `RESPOND`，`DELEGATE`/`HANDOFF`/`USE_TOOL` 直接放行。`board is None` 时也放行（无 board 配置的场景）。

### 3.7 failure_kind 的产生与消费

**产生**（`SimpleSafeExecutor`）：
- `FAILURE_KIND_VALIDATION`：`tool.validate(args)` 返回错误字符串，直接返回不进重试循环
- `FAILURE_KIND_EXECUTION`：`tool.execute` 抛 `ToolExecutionError` 且 `retryable=False`，fail-fast；也是默认 fallback
- `FAILURE_KIND_TRANSIENT`：`tool.execute` 抛非 `ToolExecutionError` 的异常

**消费**（`SimpleCritic`）：
```python
_FAILURE_KIND_HINT: dict[str, str] = {
    FAILURE_KIND_VALIDATION: "参数不合法，请重复同一动作，须修正参数后重新调用",
    FAILURE_KIND_EXECUTION: "工具执行失败",
    FAILURE_KIND_TRANSIENT: "瞬时性错误，可重试",
}
```

Critic 读取 `observation.extra.get(FAILURE_KIND)`，缺失则默认 `FAILURE_KIND_EXECUTION`。

**关键事实：delegate 失败路径不设 `FAILURE_KIND`**，所以 Critic 把所有 delegate 失败归类为 `FAILURE_KIND_EXECUTION`。

### 3.8 组件注册表模式

`ComponentKind` 枚举（`contracts/enums.py`）：
```python
class ComponentKind(str, Enum):
    OBSERVABILITY = "observability"
    STATE_STORE = "state_store"
    MEMORY = "memory"
    EVENT_BUS = "event_bus"
    MEMBER_STATUS = "member_status"
    DECISION_GATE = "decision_gate"
    BUDGET_POLICY = "budget_policy"
```

`defaults.py` 注册：
```python
reg.register(ComponentKind.MEMBER_STATUS, "default", InMemoryMemberStatus)
reg.register(ComponentKind.DECISION_GATE, DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers)
reg.register(ComponentKind.BUDGET_POLICY, "supervisor", SupervisorBudgetPolicy)
```

`TeamOrchestrator._create_member_status` 通过 `registries.components.require(ComponentKind.MEMBER_STATUS, "default")` 获取 Board 工厂类。

### 3.9 time 工具

`contracts/ids.py`：
```python
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:_ID_SUFFIX_LEN]}"
```

只有这两个函数。无 `remaining_seconds()` 或类似工具。

---

## 4. 被评审的方案（5 个决定）

### 决定 1：MemberStatus Protocol 新增 `all_settled()`

- `all_settled() -> bool`：PENDING 全部消失即为 settled（不管 DONE 还是终态 FAILED）
- `waiting_roles()` 保持不变
- `all_done()` 保留原语义，职责收窄为"synthesis 阶段判断视角是否齐全"
- 循环能不能停的判据交给 `all_settled()`

声称纯 additive 扩展，但如实承认：第三方 `MemberStatus` 实现需要跟进补 `all_settled()`，不是零风险。

### 决定 2：delegate 失败接入 failure_kind 分类，Board 新增 `record_attempt()`

三种失败路径打标签：
- `transport.send_task` 找不到目标角色 → `FAILURE_KIND_VALIDATION`
- `wait_result` 超时 → `FAILURE_KIND_TRANSIENT`
- member 执行失败 → 默认 `FAILURE_KIND_EXECUTION`

`update_member_status` 改为调用 Board 新方法 `record_attempt(role, observation, max_attempts)`：
- success → DONE（终态）
- `failure_kind == validation` → 立即 FAILED（终态）
- `failure_kind ∈ {transient, execution}` 且 attempts < max_attempts → 保持 PENDING（Board 内部 `attempts: dict[str,int]` +1）
- 超过 max_attempts → FAILED（终态）

`max_attempts` 来源两个选项：
- A（最小改动）：Board 构造函数加 `max_attempts: int = 2`，`TeamOrchestrator` 传入
- B（完全可插拔）：新增 `ComponentKind.MEMBER_RETRY_POLICY`，默认 `FixedRetryPolicy(max_attempts=2)`

### 决定 3：决策门升级为双向仲裁者

两种拦截：
1. `RESPOND` 且 `not all_settled()` → 强制改写为 delegate 给 `waiting_roles()[0]`（判据从 `all_done()` 换成 `all_settled()`）
2. **新增**：`DELEGATE` 且目标角色已 settled → 如果还有别的 `waiting_roles()`，重写 target；如果 `all_settled()` 为真，改写为 `RESPOND`

### 决定 4：deadline 超时复用 wall-clock 约定

`asyncio.get_running_loop().time()` 换成 `contracts.ids.utc_now()`：
```python
timeout_s = (spec.deadline - utc_now()).total_seconds()
```

顺手抽成 `contracts/ids.py` 的纯函数 `remaining_seconds(deadline, default)`，声称 `Budget.exceeded()` 里有"几乎一样"的逻辑可复用。

### 决定 5：as_prompt_text() 诚实暴露永久失败

加第三档文案："X 角色多次尝试后仍不可用，本次结论不含该视角"——因为决定 3 会在 `all_settled()`（而非 `all_done()`）为真时放行 `respond`，必须告诉 LLM 有信息缺口。

---

## 5. 逐条评估

### 决定 1 评估：✅ 概念正确

`all_done()` 只有一根轴是根因，加"是否全部已试"的轴是对的。

`all_settled()` 可以从已有 `status` dict 直接派生（无 PENDING/IN_PROGRESS 即 settled），不一定需要上 Protocol。但上 Protocol 也合理——语义明确、防误用、和 `all_done()` 对称。属于 ergonomics 而非 necessity，ADR 里应如实写。

### 决定 2 评估：❌ 结构性问题——Board 职责越界

这是整个方案最大的结构性问题。

**当前架构的职责分离：**

| 角色 | 职责 | 文件 |
|------|------|------|
| Board（MemberStatus） | 纯状态容器（dumb），只存 RoleStatus | `in_memory.py` |
| `update_member_status()` | 翻译 Observation → RoleStatus（logic） | `tracking.py` |
| `MustConsultAllMembers` | 控制流（when to delegate/respond） | `must_consult_all.py` |

方案要把 `record_attempt(role, observation, max_attempts)` 放到 Board Protocol 上，等于让 Board 同时承担**状态容器 + 重试决策**两个职责。

**具体后果：**

1. **Protocol 膨胀**：Board 从 6 个方法变 8 个。`record_attempt` 签名带入 `Observation`、`max_attempts`——Board 要知道 `failure_kind`、重试上限。一个本该只认 `RoleStatus` 枚举的容器，现在要认错误分类体系。

2. **ADR-0015 冲突**：ADR-0015 主张"contracts/ 只保留类型与接口"。`record_attempt()` 携带重试业务逻辑（判 failure_kind、判 max_attempts），把行为知识推到契约层。虽然 Protocol 只有签名、实现在 L1，但签名本身就是行为契约——`max_attempts` 出现在签名里，等于声明"Board 知道重试"。

3. **frozen dataclass + mutable attempts**：`InMemoryMemberStatus` 是 `@dataclass(frozen=True)`，`mark()` 返回新实例。`record_attempt()` 如果遵循不可变模式，需返回带递增 attempts 的新实例——可行但每次 mark/record_attempt 都要 carry over attempts dict，容易遗漏。如果原地 mutate，则破坏 frozen 语义一致性。

4. **max_attempts 作为 Board 构造参数**：把重试策略耦合进状态容器构造。Board 不应该知道"重试几次"——这是策略问题，不是状态问题。

**业界做法对照：**

| 框架 | 重试位置 | Board/状态容器职责 |
|------|---------|-------------------|
| CrewAI | `Task.max_retries`（任务级） | 状态容器只跟踪 task 状态 |
| AutoGen | `max_consecutive_auto_reply`（agent 级） | group chat manager 决定下一步 |
| LangGraph | 状态机 conditional edges（图结构） | 状态容器不负责重试 |
| Google A2A | client 端决定重试 | task status 终态，server 不自动重试 |

**共同模式：重试是编排层/任务层职责，不是状态容器职责。**

### 决定 3 评估：✅ 方向正确

拦截"LLM 主动 delegate 给已 settled 角色"是对的——让 LLM 决策退化为意图信号，真正状态机收敛在代码里，和 gate 的"强制"哲学一致。

**需确认的边界**：`all_settled() && not all_done()` 时放行 `RESPOND`（有角色终态失败，supervisor 带缺口产出综合回复）。这是 **degradation by design**，必须在 ADR 里显式声明为设计意图，不是"gate 没拦住"的 bug。

### 决定 4 评估：✅ 正确且必要

时钟域修复正确。`spec.deadline.timestamp()` 减 `asyncio.get_running_loop().time()` 确实是 wall-clock 减 monotonic，结果无意义。

**一个修正**：`Budget.exceeded()` 算的是 elapsed（now - started），delegate 算的是 remaining（deadline - now），方向相反。抽 `remaining_seconds()` 是好的 DRY，但不会被 Budget 复用——DRY 收益没有声称的那么大。抽取本身没错。

### 决定 5 评估：✅ 必要

`all_settled() && not all_done()` 时必须告诉 LLM 有视角缺失，否则 LLM 误以为团队意见完整，产出"看起来完整实则有缺口"的回复。

---

## 6. 方案遗漏的问题

### 6.1 poll 回退路径逻辑反转

`_wait_for_result` 的 poll 路径（无 `wait_result` 方法的 transport）：
```python
while (await transport.poll_status(task_id)) != TaskStatus.WORKING:
    ...
return await transport.receive_result(task_id)
```
循环在 `!= WORKING` 时继续，变成 WORKING 就退出并 `receive_result`。但 WORKING = "正在执行"非"已完成"。疑似应该是 `== WORKING` 或 `not in (DONE, FAILED)`。方案未覆盖此 bug。

### 6.2 agent-not-found 异常路径

方案说"`transport.send_task` 找不到目标角色 → `FAILURE_KIND_VALIDATION`"，但当前代码中 `_send_to_transport` 的 `transport.send_task` 失败是**不被捕获的异常**，直接传播出 `execute()`。要打 `FAILURE_KIND` 标签，需在 `_send_to_transport` 或 `execute` 外层包 try/except，把异常转成 Observation。方案暗示了但未显式描述。

---

## 7. 建议的修正方案

保持原方案 5 个决定的框架不变，只改决定 2 的实现位置：

### 7.1 Board Protocol

只加 `all_settled()`（如觉得有必要），**不加 `record_attempt()`**。

### 7.2 重试逻辑

留在 `update_member_status()`（tracking.py），签名加 `retry_policy` 参数：

```python
def update_member_status(
    state: AgentState,
    decision: Decision,
    observation: Observation,
    retry_policy: RetryPolicy,  # 新增
) -> None:
    board = state.member_status
    if board is None or decision.delegate_to is None:
        return
    role = decision.delegate_to.target_role
    if role not in board.required_roles:
        return

    if observation.success:
        state.member_status = board.mark(role, RoleStatus.DONE)
        return

    failure_kind = observation.extra.get(FAILURE_KIND, FAILURE_KIND_EXECUTION)
    if failure_kind == FAILURE_KIND_VALIDATION:
        state.member_status = board.mark(role, RoleStatus.FAILED)
        return

    # transient / execution — 检查重试次数
    attempts = state.delegate_attempts.get(role, 0) + 1
    state.delegate_attempts[role] = attempts
    if attempts >= retry_policy.max_attempts:
        state.member_status = board.mark(role, RoleStatus.FAILED)
    else:
        state.member_status = board.mark(role, RoleStatus.PENDING)
```

### 7.3 attempts 计数器

放 `AgentState.delegate_attempts: dict[str, int]`，和 `member_status` 平行。符合项目 feedback memory："data through state, not setters"——team 级数据流经 AgentState，不通过组件实例 setter。

### 7.4 RetryPolicy

`contracts/role_team.py` 已有 `RetryPolicy` 类（`max_retries`/`backoff_base_s`/`backoff_multiplier`）。可复用或新建 `MemberRetryPolicy`。

推迟到真有"角色 A 必须成功、角色 B 允许跳过"差异化需求时，再升级为 `ComponentKind.MEMBER_RETRY_POLICY` 注册表策略（方案的选项 B）。现在做 B 是过度设计。

### 7.5 failure_kind 标注

在 `DelegateOperation.execute()` 的 timeout/agent-not-found 路径上打标签（改 `action_handlers.py`，不碰 Board）：

- timeout → `extra={OBS_TASK_ID: task_id, FAILURE_KIND: FAILURE_KIND_TRANSIENT}`
- agent-not-found → 需先在 `_send_to_transport` 包 try/except，转成 `Observation(success=False, extra={FAILURE_KIND: FAILURE_KIND_VALIDATION})`

### 7.6 修正前后对比

| 方面 | 原方案 | 修正方案 |
|------|--------|---------|
| Board Protocol 方法数 | 6 → 8 (+all_settled +record_attempt) | 6 → 7 (+all_settled) |
| Board 知道 failure_kind | 是 | 否 |
| Board 知道 max_attempts | 是（构造参数） | 否 |
| 重试逻辑位置 | Board.record_attempt() | tracking.py update_member_status() |
| attempts 存储 | Board 内部 dict | AgentState.delegate_attempts |
| frozen 模式 | 被 mutable attempts 破坏 | 保持（mark 返回新实例） |
| ADR-0015 兼容 | 违反（行为知识入契约） | 兼容 |
| 职责分离 | 破坏（Board 兼状态+重试） | 保持（Board=dumb, tracking=logic, gate=control） |

---

## 8. 结论

| 问题 | 回答 |
|------|------|
| 合理不 | 根因分析合理，5 个决定中 4 个方向对（1/3/4/5）。决定 2 的 `record_attempt()` 上 Protocol 是过度设计，有更简单替代。 |
| 架构优雅不 | 整体思路优雅（一个问题一个方案），但决定 2 破坏了仓库自己建立的 Board=dumb / tracking=logic / gate=control 三层分离。 |
| 业界是这个思路吗 | "settled vs done 区分"是对的，业界都做。但"重试逻辑放 board 上"不是业界做法——CrewAI/AutoGen/LangGraph/A2A 都把重试放编排层或任务层。 |
| 能彻底稳定解决问题吗 | 修掉决定 2 后能。当前方案下 `record_attempt()` 引入新职责混淆，可能在后续迭代产生新维护问题。 |
| 架构可维护长远吗 | 取决于决定 2 修正。如果重试留 tracking.py + AgentState、Board 保持 dumb，则可维护。如果 record_attempt 上 Protocol，Protocol 随重试策略演进持续膨胀。 |

**核心修正**：保持 Board 为 dumb 状态容器，重试逻辑留 `tracking.py`，attempts 放 `AgentState`。保留方案的所有正面价值（settled/done 解耦、failure_kind 复用、gate 双向化、deadline 修复、prompt 诚实），不引入 Protocol 膨胀和职责混淆。

---

## 附录 A：关键文件路径

```
lca/contracts/member_status.py              — MemberStatus Protocol
lca/contracts/semantic_keys.py              — failure_kind 常量
lca/contracts/state.py                      — AgentState, Budget
lca/contracts/ids.py                        — utc_now(), new_id()
lca/contracts/enums.py                      — RoleStatus, ComponentKind, ActionType
lca/contracts/decision.py                   — Decision, DelegationSpec, Observation
lca/contracts/role_team.py                  — RetryPolicy, CacheConfig
lca/layer1_cognitive/member_status/in_memory.py    — InMemoryMemberStatus
lca/layer1_cognitive/member_status/tracking.py      — update_member_status()
lca/layer1_cognitive/body/action_handlers.py        — DelegateOperation
lca/layer1_cognitive/body/safe_executor.py          — SimpleSafeExecutor
lca/layer1_cognitive/brain/decision_gates/must_consult_all.py — MustConsultAllMembers
lca/layer1_cognitive/brain/critic.py                — SimpleCritic
lca/layer3_agent/team_orchestrator.py               — TeamOrchestrator
lca/layer4_app/defaults.py                          — register_defaults()
docs/adr/0014-error-classification-and-retry-semantics.md
docs/adr/0015-contracts-no-behavior-classes.md
```

## 附录 B：RoleStatus 枚举

```python
class RoleStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
```

## 附录 C：Budget.exceeded()（对照参考）

```python
@dataclass
class Budget:
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_steps: int | None = None
    max_wall_clock_seconds: int | None = None
    used_tokens: int = 0
    used_cost_usd: float = 0.0
    used_steps: int = 0
    started_at: datetime = field(default_factory=utc_now)

    def exceeded(self) -> bool:
        if self.max_steps is not None and self.used_steps > self.max_steps:
            return True
        if self.max_wall_clock_seconds is not None:
            elapsed = (utc_now() - self.started_at).total_seconds()
            if elapsed > self.max_wall_clock_seconds:
                return True
        return False
```

注意：`exceeded()` 只检查 steps 和 wall-clock，不检查 tokens/cost。delegate 路径完全不咨询 `Budget.exceeded()`。
