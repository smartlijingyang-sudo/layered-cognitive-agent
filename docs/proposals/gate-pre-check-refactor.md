# Proposal: DecisionGate pre_check — 消除 supervisor 认知管线空转

## 问题

`ModularBrain.think()` 的当前流程：

```
decompose → generate_candidates(n=len(subtasks)) → parse → evaluate → enforce(gate)
```

对 hierarchical 模式的 supervisor，前四步是空转：

1. `compute_required_action(board)` 是 `member_status` 的纯函数——**不需要 LLM 输入就知道该 delegate 还是 respond**
2. 但当前架构让 LLM 先跑 `generate_candidates`（调 LLM、花 token、花时间），生成候选
3. 然后在 `think()` 末尾用 `MustConsultAllMembers.enforce()` **事后覆写** LLM 的提议
4. 结果：LLM 的候选大概率被丢弃，认知管线（decompose → generate → evaluate）在空转

### 根因

`DecisionGate` 只有 `enforce(state, decision) -> Decision`——**事后纠正**。gate 在 LLM 之后跑，无法在 LLM 之前短路。

### 次要问题：n = len(subtasks)

```python
n = max(1, len(subtasks)) if len(subtasks) > 1 else 1
raw_candidates = await self.reasoner.generate_candidates(state, n=n)
```

`n`（候选采样数）从 `len(subtasks)`（子任务数）推导。这两个概念正交：

- 子任务数是**编排/规划**关注点（一个任务拆几部分）
- 候选采样数是**认知/采样**关注点（生成几个方案选优）

拆 5 个子任务不代表要采样 5 次；1 个任务也可以采样 5 次选优。当前把两者硬绑，没有逻辑依据。

### 对其他 team 模式的影响

| 模式 | supervisor think() 参与编排 | 多候选采样 |
|------|------|------|
| hierarchical | 是——supervisor 每步做路由决策 | 错配——只需 delegate/respond，不需要多方案选优 |
| sequential | 否——外部编排直接调成员 | 合理——成员解题时 best-of-N 有意义 |
| parallel | 否 | 同上 |
| handoff | 否 | 同上 |
| debate | 否 | 同上 |
| graph | 否 | 同上 |

对 choreography 模式（sequential/parallel/handoff/debate/graph），编排是外部声明式的，策略直接调 `invoke_member()`，supervisor 的 `think()` 不参与编排。每个成员用自己的 `brain.think()` 处理收到的子任务——这种场景下认知管线合理。

## 现有代码

### `DecisionGate` Protocol

文件：`lca/contracts/protocols/cognition.py`

```python
@runtime_checkable
class DecisionGate(Protocol):
    """确定性收尾策略：校验候选决策是否可被采纳。"""

    async def enforce(
        self,
        state: AgentState,
        decision: Decision,
    ) -> Decision: ...
```

### `ModularBrain.think()`

文件：`lca/layer1_cognitive/brain/modular_brain.py`

```python
async def think(self, state: AgentState) -> Decision:
    if self.skill_router is not None:
        state.active_template = await self.skill_router.route(state)

    subtasks = await self.evaluation_pipeline.decompose(state)
    if subtasks:
        state.working_memory["subtasks"] = list(subtasks)
    n = max(1, len(subtasks)) if len(subtasks) > 1 else 1
    raw_candidates = await self.reasoner.generate_candidates(state, n=n)
    candidates = [self.decision_parser.parse(rc, state) for rc in raw_candidates]
    decision = await self.evaluation_pipeline.evaluate(state, candidates)

    if self._decision_gate is not None:
        decision = await self._decision_gate.enforce(state, decision)
    return decision
```

### `MustConsultAllMembers.enforce()`

文件：`lca/layer1_cognitive/brain/decision_gates/must_consult_all.py`

```python
class MustConsultAllMembers(DecisionGate):
    async def enforce(
        self,
        state: AgentState,
        decision: Decision,
    ) -> Decision:
        board = state.member_status
        if board is None:
            return decision

        if decision.action_type not in (ActionType.RESPOND, ActionType.DELEGATE):
            return decision

        required = compute_required_action(board)

        if required.kind == "may_respond":
            if decision.action_type == ActionType.DELEGATE:
                return Decision(
                    decision_id=new_id("dec"),
                    action_type=ActionType.RESPOND,
                    rationale="[框架强制] 所有必需角色已结算,无需进一步委派",
                    confidence=1.0,
                )
            return decision

        # required.kind == "must_delegate"
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

### `compute_required_action()`

文件：`lca/layer1_cognitive/member_status/policy.py`

```python
@dataclass(frozen=True)
class RequiredAction:
    kind: Literal["must_delegate", "may_respond"]
    target_role: str | None = None


def compute_required_action(board: MemberStatus) -> RequiredAction:
    waiting = board.waiting_roles()
    if waiting:
        return RequiredAction(kind="must_delegate", target_role=waiting[0])
    return RequiredAction(kind="may_respond")
```

## 方案

### 改动 1：`DecisionGate` 加 `pre_check`

```python
@runtime_checkable
class DecisionGate(Protocol):
    """确定性路由 + 事后纠正。"""

    async def pre_check(self, state: AgentState) -> Decision | None:
        """确定性路由：无需 LLM 即可决定时返回 Decision，
        否则 None 交给认知管线。"""

    async def enforce(
        self,
        state: AgentState,
        decision: Decision,
    ) -> Decision:
        """事后兜底：LLM 在认知管线上偏离时纠正。"""
```

`pre_check` 返回 `None` 的语义不是"校验失败"，是"我这层定不了，交给 LLM"——与 `validate() -> None` 不同。

### 改动 2：`think()` 重排——先查 gate，定不了再调 LLM

```python
async def think(self, state: AgentState) -> Decision:
    # 1. 确定性路由——gate 能定的直接返回，不调 LLM
    if self._decision_gate is not None:
        pre = await self._decision_gate.pre_check(state)
        if pre is not None:
            return pre

    # 2. 认知管线——gate 放行后才跑（此时只可能是 respond 路径）
    if self.skill_router is not None:
        state.active_template = await self.skill_router.route(state)
    subtasks = await self.evaluation_pipeline.decompose(state)
    if subtasks:
        state.working_memory["subtasks"] = list(subtasks)
    raw_candidates = await self.reasoner.generate_candidates(state, n=1)
    candidates = [self.decision_parser.parse(rc, state) for rc in raw_candidates]
    decision = await self.evaluation_pipeline.evaluate(state, candidates)

    # 3. 安全网——LLM 在 respond 路径上偏离时纠正
    if self._decision_gate is not None:
        decision = await self._decision_gate.enforce(state, decision)
    return decision
```

### 改动 3：`MustConsultAllMembers` 拆分职责

```python
class MustConsultAllMembers(DecisionGate):
    async def pre_check(self, state: AgentState) -> Decision | None:
        board = state.member_status
        if board is None:
            return None
        required = compute_required_action(board)
        if required.kind == "must_delegate" and required.target_role:
            return Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.DELEGATE,
                delegate_to=DelegationSpec(
                    target_role=required.target_role,
                    subtask=_infer_subtask(state.task, required.target_role),
                ),
                rationale="[gate] 尚有必需角色未结算",
                confidence=1.0,
            )
        return None  # may_respond → 交给 LLM 生成综合回复

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        board = state.member_status
        if board is None:
            return decision
        if decision.action_type != ActionType.DELEGATE:
            return decision
        required = compute_required_action(board)
        if required.kind == "may_respond":
            # 所有人已结算，LLM 却想 delegate → 纠正为 respond
            return Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.RESPOND,
                rationale="[gate] 所有必需角色已结算，阻止冗余委派",
                confidence=1.0,
            )
        return decision
```

`enforce` 只剩一个分支——原来的 "must_delegate" 整段移到 `pre_check`，`enforce` 不再需要处理它（因为 `pre_check` 返回 non-None 时 `think()` 直接返回，不会走到 `enforce`）。

### 改动 4：删除 `n = len(subtasks)` 推导

`think()` 中删除：

```python
n = max(1, len(subtasks)) if len(subtasks) > 1 else 1
```

改为直接 `generate_candidates(state, n=1)`。多候选采样如果以后需要，是 reasoner 自己的配置，不该由 brain 从子任务数推导。

## 改动范围

| 文件 | 改动 |
|------|------|
| `lca/contracts/protocols/cognition.py` | `DecisionGate` 加 `pre_check` 方法 |
| `lca/layer1_cognitive/brain/modular_brain.py` | `think()` 重排：pre_check → 认知管线 → enforce |
| `lca/layer1_cognitive/brain/decision_gates/must_consult_all.py` | 拆 `pre_check` + 精简 `enforce` |
| `lca/contracts/protocols/cognition.py` | `DecisionGate` Protocol docstring 更新 |
| 测试 | 所有 gate 相关测试需要覆盖 `pre_check` 路径 |

## 设计原则吻合度

| 原则 | 说明 |
|------|------|
| 不加新概念 | `DecisionGate` 还是那个 gate，只多一个方法，不新增 Protocol/类型 |
| 不按角色区分类型 | 没有 `if role_mode == SUPERVISOR`，gate 是组合时注入的 |
| 不 dissolve 抽象 | `DecisionGate` 是合法策略（不同 team 类型需要不同 gate），修形状不杀概念 |
| policy resolve 不 validate | `pre_check` 返回 Decision（resolve）或 None（defer），不是校验失败 |
| 高内聚低耦合 | 路由逻辑在 gate，认知逻辑在 brain，各管各的 |

## 改动后的流程

```
think():
  1. gate.pre_check(state)
     ├── 返回 Decision (must_delegate) → 直接返回，不调 LLM ✓
     └── 返回 None (may_respond) → 继续 ↓

  2. 认知管线（只在 respond 路径跑）
     skill_route → decompose → generate_candidates(n=1) → parse → evaluate

  3. gate.enforce(state, decision)
     └── 安全网：LLM 偏离时纠正（如 all_settled 但 LLM 试图 delegate）
```

对比改前：

```
think():
  1. skill_route → decompose → generate_candidates(n=len(subtasks)) → parse → evaluate
  2. gate.enforce(state, decision)  ← 这里才真正决策，前面的 LLM 调用大概率白做
```

## 风险与权衡

### 向后兼容

- `DecisionGate` Protocol 加方法：现有的 `DecisionGate` 实现需要补 `pre_check`。当前只有一个实现 `MustConsultAllMembers`，改动范围小。
- `pre_check` 的默认语义是 `return None`（defer to LLM）——对不需要 pre-check 的 gate 实现，一行 `return None` 即可。
- `enforce` 签名不变，现有调用方不受影响。

### `enforce` 还需要吗？

需要。`pre_check` 处理 "must_delegate"（确定性路由），`enforce` 处理 "may_respond 但 LLM 偏离"（安全网）。两者职责不重叠：
- `pre_check` 返回 non-None → `think()` 直接返回，不走 `enforce`
- `pre_check` 返回 None → LLM 跑，`enforce` 兜底

### LLM 的 delegate 提议还有用吗？

在改前的架构里，LLM 可以提议 delegate 给某个角色，gate 检查是否正确。改后，delegate 决策完全由 `pre_check` 确定性决定——LLM 不再参与 delegate 路由。

这损失了"LLM 基于上下文智能选择 delegate 目标"的能力。但当前 `compute_required_action` 已经用 `waiting_roles()[0]` 确定了目标——LLM 的提议大概率被覆写。如果以后需要"LLM 选择更好的 delegate 目标"，可以让 `pre_check` 在多个 waiting 角色时返回 None 交给 LLM 决策，只在 0 个或 1 个 waiting 角色时短路。这是一个可扩展点，不是设计缺陷。

### 对 choreography 模式的影响

无影响。sequential/parallel/handoff/debate/graph 的 supervisor 不参与编排，成员的 `brain.think()` 没有 gate（`self._decision_gate is None`），`pre_check` 不执行，认知管线正常跑。

## 未解决的问题（不在本次范围）

- `SimpleReasoner.generate_candidates` 的 `n` 参数仍然存在于 Protocol 签名中。如果以后需要多候选采样，应该是 reasoner 级别的配置（如 `SimpleReasoner(n_samples=3)`），不是 brain 从子任务数推导。
- `SimpleCandidateEvaluationPipeline.decompose` 默认返回 `[state.task]`（不分解）。如果有自定义 pipeline 真的分解任务，`generate_candidates` 收到 `n=1`——这意味着分解出的多个子任务不在一次 think 里处理，而是通过 loop 多次 think 串行解决。这是合理的（ReAct 循环本就是多步的），但需要确认不影响已有行为。
