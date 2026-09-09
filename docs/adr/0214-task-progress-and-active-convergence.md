# ADR-0214: TaskProgress Projection + Multi-Tool Loop Breaker + PG-007 三件套

> **状态:** **Proposed — 2026-09-09**
>
> **一句话**: 把 think 决策的"我应该停下来"从隐式变量变成一等公民 — Decision DTO 扩 `task_progress` 必填四元组、Reducer 单写 `apply_task_progress`、新增 `TaskProgressProjection` (观察面 fold)、新增 `MultiToolLoopBreakerGate` (整体进度熔断)、PG-007 三件套 (precondition + terminal_predicate + max_visits)、skill 打包契约扩 `references` 必填字段。
>
> **触发 run**: `run_c218d952c6f2` (Q4 pptx 任务) — `PG-007: node visit budget exhausted: perceive.main`,officecli 修复机制全程未被触发。
>
> **Review:** 待评审。
>
> **Accepted 闸门**:
> 1. §3 Decision.task_progress 字段在所有 emit / consume / reasoner / Gate / Projection 处都有显式契约测试,`rg "decision.task_progress" lca/ tests/ | wc -l` ≥ emit 方数
> 2. §4 `TaskProgressProjection` fold 5 种典型序列(`completed` 单调、`remaining` 终态可空、`confidence` 有界、`confidence_history` 长度 == history turn 数)断不变式全过
> 3. §5 `MultiToolLoopBreakerGate` 在双工具交替失败 / 单工具反复失败 / 切换有进展 / stuck-then-progress 5 fixture 行为正确
> 4. §6 PG-007 三件套 schema 升级,`traversal.visit` 与 `advance` 增 precondition / terminal_predicate 路径
> 5. §7 SKILL.md 缺 `references` 字段加载期 fail-loud;`read_skill_reference` 改名 + 节流
> 6. §8 同一份 Q4 pptx 任务真实生产复测: `officecli create` ≥ 1 / `officecli add` ≥ 1 / `officecli validate` ≥ 1 / `office_works_sealer` 触发 1 / run 进入 terminal outcome
> 7. §9 `run_c218d952c6f2` 重放 fixture 断言"在新机制下应在第 6 步前熔断,不依赖 PG-007 max_visits"

**编号**: 0214 (0213 已占用,0214–0222 范围预留)

**关系**:
- **Builds on**: ADR-0158 (StopDecision / TerminalOutcome SSOT) · ADR-0186 (Session SSOT) · ADR-0191 (turn.control.v1 fold) · ADR-0194 (认知 Loop 架构收敛) · ADR-0195 (平台架构收敛 + §1.4 单写矩阵 + §2.5 P5) · ADR-0211 (Worker Contract 收紧) · ADR-0212 (step_tree 派生面 SSOT)
- **Refines**: ADR-0077 (TerminalOutcome 的 "task_progress_complete" 新 stop_reason) · ADR-0051 (tool loop breaker, **不删**, 升级为 multi-tool 视角) · PG-007 (扩展 precondition + terminal_predicate)
- **Supersedes**: 无
- **Reject**: 「在 SkillSet 路由层做熔断」(违反 ADR-0195 §1.4 单一写者矩阵,引入第二事实源);「用更强 LLM 替代」(违反 ADR-0062 G0 机制不可插件化);「把 task_progress 放在 prompt 自由文本里」(违反 C13 信息血统闭合,跨边界必须有 typed Contract);「保留单工具 tool_loop_breaker 同时删 task_progress」(违反 C6 最小化与本 ADR §0.1 第一性原理)

---

## 0. 第一性原理: 问题本质

### 0.1 run_c218d952c6f2 的根因面

| 症状 | 表面错误 | 真正机制 | 类别 |
|---|---|---|---|
| 8 次 `read_skill_reference` 失败 | skill 白名单拒 | 模型**误用** `activate_skill` 当"读数据"(读 SKILL.md 子文档) | 观察面/控制面退化合并 |
| 4 次 `activate_skill` 反复 | 反复激活 | `activate_skill` 返回的 `observation_payload` 是 activation 当时的 SKILL.md 快照;模型**不去读已有 payload**, 重复切换状态 | 同上 |
| `read_skill_reference` 失败 ≥ 8 未熔断 | `ToolLoopBreakerGate` 失效 | 工具交替失败打破单工具连续计数;`_consecutive_failures` 在 `read_skill_reference ↔ runCommand` 切换时被 `tool_name` 不匹配截断 | 单工具熔断盲点 |
| think 决策永不 RESPOND | 模型一直选 `USE_TOOL` | 没有"我应该停下来"的内在信号源;模型靠 prompt 里的"<thinking>"推测, hidden state 不可审计 | 决策终止理论缺失 |
| perceive.main 被访问 8 次后 PG-007 截止 | `RuntimeError('PG-007: node visit budget exhausted: perceive.main')` | PG-007 只有 `max_visits`, 缺 `precondition` (入口校验) 与 `terminal_predicate` (出口谓词);只能"被动硬截止", 不能"主动软收敛" | 计划图硬截止 |
| `duplicate step_id: ['step-001']` | doctor H3 failed | StepTreeAccumulator 在 0212 中已删, 但本 run 是 0212 之前触发, 残留 — 0212 PR 验证时可一并关闭 | (非本 ADR 范畴, 提及供关联) |

**第一性**: 4 个独立 bug 是**同一根因的不同投影** — think 决策没有"任务进度观察面"。**修法杠杆**: 一个 `TaskProgressProjection` 一次性收口 4 个症状。

### 0.2 三个不动的不变量

| ID | 内容 | 本 ADR 如何兑现 |
|---|---|---|
| **C4 Reducer single-write** | 业务路径不直接写 State; projection 不得成为新事实源 | `apply_task_progress` 是唯一写 `state.task_progress` 入口; `TaskProgressProjection` 是观察面 fold, 不反向写 |
| **C5 能力单调** | capability/scope/effects ⊆ grant; CommandEnvelope 是副作用唯一出口 | task_progress 是观察面信号, **不引入新 capability**; Gate rewrite 仍走现有 CapabilityGrant |
| **C8 确定性** | Profile resolve / fold / projection 必须确定 | fingerprint 规范化纯函数, 时间戳不参与; confidence 量化算法确定 |
| **C9 幂等/重入** | append / fold / observer / teardown 必须幂等 | Session fold 天然幂等; resume 不重算 task_progress |
| **C11 事件闭集** | 新事件必须加入白名单 + 注册 SpineHandler + 测试 + ADR | `task_progress.commit.v1` 与 `terminal_predicate_satisfied` 两个新事件同 PR 加入 |
| **C12 Reducer 合约** | `apply_*` 必须 `@_instrument_apply`; `apply_stop` 先于 `apply_terminal_outcome` | `apply_task_progress` 与 `apply_stop` 同优先级 (但**独立**, 不嵌入 apply_stop); 新方法同步更新 AgentStateProjection fold |
| **C13 信息血统闭合** | 跨边界必须 typed Contract | `TaskProgress` 是 `@dataclass(frozen=True, slots=True)` + `__post_init__` extra 校验 (LCA contracts 默认 dataclass); `TaskProgressCommitted` 事件 Pydantic frozen `extra="forbid"` (跨 Session 边界, 必须严格); `Decision.task_progress` 必填; no-Contract 跨边界 = fail-loud |

### 0.3 第一性原理 (机制层)

LCA 当前 think 决策的语义是:

```
state, observation → Decision (action_type ∈ {USE_TOOL, RESPOND, STOP, ASK_HUMAN, HANDOFF})
```

这是个**无记忆**函数 — 模型靠 hidden state (chat history) 推测"我做过什么 / 还该做什么"。这在 LLM hidden state 里不可审计、不可 Gate 干预。

业界范式 (Reflexion / BDI / Voyager) 给出的**第一性原理**: 决策必须显式携带**任务进度观察面**。本 ADR 把这条作为 Decision 的 typed 字段:

```
state, observation → Decision {
    action_type: ...
    task_progress: TaskProgress {
        completed: tuple[str, ...]
        remaining: tuple[str, ...]
        confidence: float ∈ [0, 1]
        termination_reason: str | None
    }
}
```

四个字段共同定义**主动收敛**:
- `remaining == ()` → 必须 RESPOND (Gate rewrite)
- `confidence < 0.2` 连续 N 步 → MultiToolLoopBreaker 熔断
- `termination_reason != None` → 跳过 execute, 直接进入 TerminalOutcome
- `completed` 单调递增 → fold 不变式, 防止回退

---

## 1. 目标

| ID | 内容 | 验证 |
|---|---|---|
| G1 | Decision.task_progress 必填 typed Contract | schema 测试 + 所有 emit/consumer 同步改 |
| G2 | `apply_task_progress` Reducer 单写, `@_instrument_apply` | reducer 单测 + 不变量断 |
| G3 | `TaskProgressProjection` Session fold, 观察面 SSOT | fold 5 fixture 不变式 |
| G4 | `MultiToolLoopBreakerGate` 整体进度熔断, 与 `ToolLoopBreakerGate` 并存 | 5 fixture 行为 |
| G5 | PG-007 三件套 (precondition / terminal_predicate / max_visits) | precondition 失败 / 满足 / 缺失; terminal_predicate 强制 stop |
| G6 | SKILL.md frontmatter `references` 必填; `read_skill_reference_once` 节流 | 加载期 + 运行期 |
| G7 | Q4 pptx 真实生产复测成功 | run 完成 / officecli add ≥ 1 / sealer 触发 |
| G8 | run_c218d952c6f2 fixture: 新机制下应在第 6 步前熔断 | integration test |

---

## 2. 整体数据流

```
┌──────────────────────────────────────────────────────────────┐
│ Per-step Reasoning Contract (强制, 注入 prompt)              │
│ 模型必须输出:                                                  │
│   <task_progress>: {completed, remaining, confidence, term}   │
│   <next_action>:    {tool+args} | {respond_with: text}       │
│   <reflection>:     "我刚才做错了什么 / 学到了什么"            │
│   <termination_check>: "为什么现在不能 RESPOND"                │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│ Cognition 解析 → Decision.task_progress (typed Contract)     │
│   ↓ Session.append(task_progress.commit.v1) — 单轨 SSOT      │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│ TaskProgressProjection.fold(events) — 观察面 fold            │
│   → AgentState.task_progress (TaskProgressField, frozen)     │
│   → confidence_history (deque, 长度 = 窗口 K)                │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│ Gate 决策 (Think plane)                                       │
│   1. TaskProgressGate:                                        │
│      - remaining=[] + confidence≥0.8 → rewrite to RESPOND    │
│      - termination_reason != None → 强制 STOP                │
│   2. MultiToolLoopBreakerGate:                                │
│      - 滑动窗口 K=5 指纹方差 < 阈值 + confidence 连续下降     │
│        → rewrite to RESPOND                                  │
│   3. ToolLoopBreakerGate (defense-in-depth, 不删)            │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│ Plan Graph (结构层)                                          │
│   PG-007 三件套:                                              │
│     precondition(state) → bool  (入口, 不满足不计数)          │
│     terminal_predicate(state) → bool  (出口, 满足强制 stop)   │
│     max_visits (兜底, 不变)                                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. PR-A: Decision.task_progress 契约

### 3.1 新增 typed Contract

`lca/contracts/models/core/execution/task_progress.py` (新文件):

```python
@dataclass(frozen=True, slots=True)
class TaskProgress:
    """Task progress observation — Decision 的 typed Contract 一部分。

    frozen=True + slots=True + __post_init__ extra 检查 = dataclass 形态的
    ``extra="forbid"`` 等价物。LCA contracts 默认 dataclass, 不引 Pydantic。
    """
    completed: tuple[str, ...] = ()
    remaining: tuple[str, ...] = ()
    confidence: float = 0.0
    termination_reason: str | None = None

    def __post_init__(self) -> None:
        # frozen dataclass 不允许运行时校验 → 用 __post_init__ 显式断言
        if not 0.0 <= self.confidence <= 1.0:
            raise ContractViolation(
                f"confidence must be in [0, 1], got {self.confidence}"
            )

    def is_terminal(self) -> bool:
        return len(self.remaining) == 0 and self.confidence >= 0.8
```

### 3.2 Decision DTO 扩字段

`lca/contracts/models/core/execution/decision.py`:

```python
@dataclass(frozen=True, slots=True)
class Decision:
    # ... 现有字段 ...
    task_progress: TaskProgress = field(default_factory=TaskProgress)
    # 注: 默认值仅用于既有测试/兼容路径; cognition emit 方必须显式传
```

### 3.3 emit / consume 同步 (同 PR 闭环)

- `lca/cognition/brain/reasoner.py` — 解析 `<task_progress>` 段
- `lca/cognition/brain/llm_result.py` — 解析 LLM 输出
- `lca/cognition/brain/prompts/*` — 注入四元组契约
- 所有 `Decision(...)` 构造点 — 必传 `task_progress=...`
- 所有 `decision.task_progress` 读取点 — 类型断言

### 3.4 Reducer 单写

`lca/plugins/loop/reducer/plugin.py`:

```python
@_instrument_apply
def apply_task_progress(
    self,
    state: AgentState,
    progress: TaskProgress,
) -> AgentState:
    """Fold a TaskProgress fact into state.task_progress (C4 单写).

    Invariants:
    - completed 单调递增 (新 completed ⊇ 旧 completed)
    - confidence 有界 [0, 1]
    - remaining 终态可空 (中途可减可加, 但 fold 后必须满足 schema)
    """
    state.task_progress = progress  # AgentState.task_progress 字段
    return state
```

### 3.5 AgentState 字段

`lca/contracts/models/core/state/state.py`:

```python
@dataclass
class AgentState:
    # ... 现有字段 ...
    task_progress: TaskProgress = field(default_factory=lambda: TaskProgress(
        completed=(), remaining=(), confidence=0.0
    ))
```

### 3.6 测试

- `tests/contracts/test_decision_task_progress.py` — Pydantic frozen + extra=forbid
- `tests/contracts/test_task_progress_invariants.py` — completed 单调、confidence 有界
- `tests/reducer/test_apply_task_progress.py` — Reducer 单测
- `tests/integration/test_decision_emit_consume.py` — 所有 Decision 构造点同步改

---

## 4. PR-A (续): TaskProgressProjection 观察面 fold

### 4.1 Session 单轨事实 + **append 时机契约 (C9 兜底)**

`lca/contracts/harness/memory/events.py` (扩):

```python
class TaskProgressCommitted(AdrBaseModel):
    """事实面: 一个 think step 提交 task_progress 状态。

    每个 think step 必须至少一条;append 必须**先于 execute_tool** 完成
    (durability 优先于动作)。失败/中断下,resume 从 Session fold 还原
    最近一条, 模型从该点继续。
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    step_id: str
    completed: tuple[str, ...]
    remaining: tuple[str, ...]
    confidence: float
    termination_reason: str | None
```

`lca_kernel/events/config/catalog.yaml` 加 `task_progress.commit.v1` 到白名单 (C11)。

#### 4.1.1 Append 时机契约 (核心 — 回应"中断后模型怎么知道中间发生了什么")

| 时点 | 事件 | 谁负责 | 失败语义 |
|---|---|---|---|
| **T0** cognition 解析出 Decision.task_progress | `task_progress.commit.v1` (step_id=N, 上一决策点) | `FactGateway.emit()` via `Session.append` | append 失败 → 抛 `FactGatewayError`,**不进入 T1**;模型拿不到该决策的下游执行 |
| **T1** Gate 决策前 | (读 AgentState.task_progress) | Reducer.apply_task_progress 已 fold 入 state | (无 append, 只读) |
| **T2** tool 执行前 | (无 append) | — | — |
| **T3** tool observation 落地 | `turn.control.v1` (既有) | 既有 append 路径 | 既有语义, 不动 |
| **T4** reducer apply_turn 后, reflect 阶段 | `task_progress.commit.v1` (step_id=N+1, **本步反思**) | cognition/reflect | append 失败 → reflect 失败, run 标 degraded 但不丢事实 |

**关键不变量**:
- **T0 先于 execute**: append 必须 fsync(flush)后,才把 Decision 转给 Body。这确保中断时, 已 commit 的 task_progress 一定在 Session 里。
- **T4 强约束**: 每个 think step **最多 2 条 task_progress 事件**(T0 决策时 + T4 反思时),但**至少 1 条**(T0)。模型跳步 = T4 缺失 = run degraded。

#### 4.1.2 中断恢复语义 (C9 兑现)

```
resume 流程:
1. 加载 Session (durable facts, 单轨 SSOT)
2. TaskProgressProjection.fold(events) → 还原最近 task_progress 状态
3. StepTreeProjection.fold(events) → 还原 step cursor
4. 注入 prompt 头:
     "<recovered_from_step>: {step_id}"
     "<task_progress_resumed>: {completed, remaining, confidence, last_reflection}"
5. 模型从该 step 继续
```

**回答"模型怎么知道中间发生了什么"**: 注入的 `<task_progress_resumed>` 四元组就是模型"中间发生了什么"的 SSOT 来源。它不是从 prompt history 推测, 是从 Session fold 出来的事实。**每次 resume 注入一次**, 不靠 chat history。

#### 4.1.3 append 失败 vs 中断的区分

| 场景 | 现象 | 处理 |
|---|---|---|
| append 调用返回 False (写盘失败) | `FactGatewayError` | 抛到 cognition 层, Decision 不下发, run 进入 degraded |
| append 调用后未 fsync, 进程 SIGKILL | T0 事件可能在写盘缓冲 | Session 默认 fsync 策略 (写盘前 fsync);**同 PR 验证 fsync 行为**, 不在 T0 之前 yield 控制权 |
| 中断在 T0 与 T1 之间 | T0 已 fsync, Gate 未跑 | resume 时 Gate 从 state.task_progress 出发重判, 行为一致 |
| 中断在 T1 与 T2 之间 | T0 已 fsync, Decision 已 rewrite | resume 时复跑 Gate (幂等), 决定一致 |
| 中断在 T2 与 T3 之间 | tool 部分执行 | 既有的 tool resume 语义, 不在本 ADR 范畴 |
| 中断在 T3 与 T4 之间 | turn 已 commit, 但 reflect 未跑 | resume 时进入 reflect, T4 事件补 append |

### 4.2 Projection fold

`lca/plugins/session/task_progress/projection.py` (新文件):

```python
class TaskProgressProjection:
    """观察面: Session events → 当前 task_progress 状态 + 历史。

    C4 兑现: 只读 Session, 不反向写事实。
    C9 兑现: fold 幂等, resume 重放结果一致。
    """

    def __init__(self) -> None:
        self._state: TaskProgress | None = None
        self._confidence_history: deque[float] = deque(maxlen=10)

    def apply(self, event: TaskProgressCommitted) -> None:
        # 不变式: completed 单调
        prev = self._state.completed if self._state else ()
        new_completed = tuple(sorted(set(prev) | set(event.completed)))
        self._state = TaskProgress(
            completed=new_completed,
            remaining=event.remaining,
            confidence=event.confidence,
            termination_reason=event.termination_reason,
        )
        self._confidence_history.append(event.confidence)

    @property
    def current(self) -> TaskProgress:
        if self._state is None:
            return TaskProgress()
        return self._state

    @property
    def confidence_history(self) -> tuple[float, ...]:
        return tuple(self._confidence_history)

    def is_stuck(self, window: int = 5, threshold: float = 0.1) -> bool:
        """最近 K 步 confidence 下降 > threshold → stuck。"""
        h = self.confidence_history
        if len(h) < window: return False
        delta = h[-1] - h[-window]
        return delta < -threshold
```

### 4.3 测试

- `tests/session/test_task_progress_projection.py` — 5 fixture:
  1. 空 events → default
  2. 单调递增 completed → 不变式
  3. confidence 历史 → 长度 + 顺序
  4. resume fold 幂等
  5. is_stuck 判定 (窗口不够 / 下降 / 上升)

---

## 5. PR-B: MultiToolLoopBreakerGate

### 5.1 新 Gate

`lca/cognition/brain/decision_gates/loop/multi_tool_breaker.py` (新文件):

```python
class MultiToolLoopBreakerGate(DecisionGate):
    """整体进度视角的循环熔断器 — 替代/补充单工具 tool_loop_breaker。

    触发条件 (任一):
    1. 最近 K=5 步 (tool_name, normalized_args, normalized_observation) 指纹方差 < 阈值
       且 confidence 连续下降 (TaskProgressProjection.is_stuck)
    2. completed 集合在最近 K 步无新增
    3. 任一 tool 失败 ≥ break_failures 但工具名切换 (单工具 breaker 的盲点)

    不删除 ToolLoopBreakerGate — defense-in-depth, 评估去留留给后续 ADR。
    """

    def __init__(
        self,
        *,
        window: int = 5,
        variance_threshold: float = 0.05,
        stuck_threshold: float = 0.1,
    ) -> None:
        self._window = window
        self._variance_threshold = variance_threshold
        self._stuck_threshold = stuck_threshold

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        projection = state.task_progress_projection  # AgentState 持引用
        if projection is None:
            return decision

        if projection.is_stuck(window=self._window, threshold=self._stuck_threshold):
            return self._force_respond(
                decision,
                rationale=(
                    f"最近 {self._window} 步 confidence 连续下降, "
                    f"任务进度无进展, 熔断。"
                ),
            )

        recent_progress = projection.confidence_history[-self._window:]
        if len(recent_progress) >= self._window:
            # 指纹方差: 用 tuple[tool, normalized_args] 作为离散指纹
            fingerprints = self._recent_fingerprints(state, window=self._window)
            variance = self._fingerprint_variance(fingerprints)
            if variance < self._variance_threshold and projection.is_stuck(...):
                return self._force_respond(...)

        return decision
```

### 5.2 测试

`tests/cognition/test_multi_tool_loop_breaker.py`:

1. 双工具交替失败 → 触发
2. 单工具反复失败 → 触发 (单工具 breaker 也应触发, 验证两者并存)
3. 工具切换 + observation 不同 → 不触发
4. stuck 后实际取得进展 → 不触发 (confidence 回升)
5. TaskProgressProjection 缺失 → 失败开放 (return decision 不变)

---

## 6. PR-C: PG-007 三件套

### 6.1 PhaseNode schema 扩字段

`lca/contracts/protocols/declarative/declarative_1/declarative_graph.py`:

```python
class PhaseNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    phase: str
    binding: str
    max_visits: int = 8
    entry: bool = False
    terminal: bool = False
    # 新增:
    precondition: str | None = None     # Callable 名字, 由 harness 注册表解析
    terminal_predicate: str | None = None  # Callable 名字, 同上
```

**为什么用 string 而不是 Callable**: Plan 是声明式 YAML, 序列化必须纯文本; Callable 名字注册到 harness。

### 6.2 traversal 行为升级

`lca/harness/graph/traversal.py`:

```python
def visit(self, *, node_id: str, max_visits: int, precondition: Callable | None = None) -> int:
    if precondition is not None and not precondition(self._artifact_state()):
        # precondition 不满足: 不计数, 允许重试到 max_visits
        return -1  # 标识"未访问, 但已尝试"
    self.current_node_id = node_id
    count = self.visit_counts.get(node_id, 0) + 1
    self.visit_counts[node_id] = count
    if count > max_visits:
        raise DeclarativeValidationError("PG-007", f"node visit budget exhausted: {node_id}")
    return count

def advance(self, *, edge, payload, causation_refs, terminal_predicate: Callable | None = None):
    # ... 现有 edge budget 检查 ...
    if edge.target_node.terminal_predicate is not None:
        pred = resolve_predicate(edge.target_node.terminal_predicate)
        if pred(self._artifact_state()):
            # 满足终止谓词: 强制 advance 到 stop.main, 即使模型想继续
            self._force_to_stop()
    # ...
```

### 6.3 profile/web-standard.yaml 升级

```yaml
- id: perceive.main
  phase: perceive
  binding: phase.perceive.standard
  max_visits: 8
  entry: true
  precondition: perceive.has_minimum_context   # 至少要有 user_text 或 attachment
  terminal_predicate: perceive.context_complete  # context 完整则可跳过 perceive
```

### 6.4 测试

- `tests/harness/test_traversal_precondition.py`
- `tests/harness/test_traversal_terminal_predicate.py`
- `tests/profile/test_web_standard_schema.py` — YAML 解析

---

## 7. PR-D: Skill 打包契约 + read_skill_reference_once 节流

### 7.1 SKILL.md frontmatter

```yaml
---
name: officecli
description: ...
version: 1.0.0
references:                    # 必填, 列表
  - references/REFERENCE.md    # 路径相对 SKILL.md
  - references/SCHEMAS.md
---
```

### 7.2 加载期 fail-loud

`lca/layer0_infra/skills/bundled.py` (新加路径) 或 `lca/layer0_infra/skills/factory.py`:

```python
def load_skill(skill_id: str) -> Skill:
    fm = parse_frontmatter(skill_id)
    if "references" not in fm:
        raise SkillContractError(
            f"SKILL.md frontmatter missing 'references' field: {skill_id}"
        )
    # 把 references 索引注入 prompt
    return Skill(
        ...,
        references=fm["references"],
    )
```

### 7.3 read_skill_reference_once 节流

`lca/layer0_infra/tools/read_skill_reference.py` (改名):

```python
class ReadSkillReferenceThrottle:
    """同一 (skill_id, path) 在 5 步内失败 ≥ 2 → fail-loud."""
    def __init__(self, window: int = 5, threshold: int = 2):
        self._window = window
        self._threshold = threshold
        self._fail_history: dict[tuple[str, str], deque[bool]] = {}

    def check(self, skill_id: str, path: str) -> None:
        key = (skill_id, path)
        if key not in self._fail_history:
            self._fail_history[key] = deque(maxlen=self._window)
        h = self._fail_history[key]
        recent_fails = sum(1 for x in h if x)
        if recent_fails >= self._threshold:
            raise SkillContractError(
                f"read_skill_reference({skill_id}, {path}) "
                f"在最近 {self._window} 步内失败 ≥ {self._threshold}, 节流"
            )
        # 调用方实际执行后, 反馈 ok / fail
```

### 7.4 activate_skill 注入 references

`lca/layer0_infra/tools/activate_skill.py`:

```python
async def activate(skill_id: str) -> ActivationResult:
    skill = load_skill(skill_id)
    return ActivationResult(
        skill_id=skill_id,
        skill_md_content=skill.body,           # 现有
        references_index=skill.references,     # 新增
        # prompt 注入时显式声明:
        #   "你已激活 officecli v1.0.0。SKILL.md 内容已注入 <skill_knowledge>。
        #    references 索引已注入 <skill_references>。
        #    read_skill_reference(path) 仅用于冷门子文档, 不要重复读。"
    )
```

### 7.5 测试

- `tests/skills/test_skill_loading.py` — 缺 references 字段 → fail-loud
- `tests/skills/test_read_skill_reference_throttle.py` — 5 fixture
- `tests/skills/test_activate_skill_prompt.py` — references 索引注入

---

## 8. PR-E: 真实生产复测

### 8.1 触发

```bash
./scripts/lca-ops runs create --user-text '<Q4 pptx 任务同 run_c218d952c6f2>' --wait
```

### 8.2 断言

- `officecli create` ≥ 1 次
- `officecli add` ≥ 1 次 (最少 5 页 slide)
- `officecli validate` ≥ 1 次
- `office_works_sealer` 触发 1 次 (close/run-end)
- run 进入 terminal outcome (status: completed)

### 8.3 doctor

`./scripts/lca-ops debug-run <new_run_id>` 期望 H1-H12 全 ok, status: completed。

---

## 9. PR-E (续): run_c218d952c6f2 反例 fixture

### 9.1 replay fixture

```python
# tests/integration/test_run_c218d952c6f2_regression.py
def test_run_c218d952c6f2_should_break_under_new_gates():
    """该 run 在新机制下应在第 6 步前熔断, 不依赖 PG-007 max_visits。"""
    events = load_spine_events("run_c218d952c6f2")
    simulated = simulate_with_new_gates(events)
    assert simulated["breaker_trigger_step"] <= 6
    assert simulated["breaker_kind"] == "multi_tool_loop_break"
    # 新机制不依赖 PG-007 硬截止
    assert simulated["max_visits_triggered"] is False
```

### 9.2 invariant

```python
def test_no_officecli_loop_pattern_in_session_events():
    """任何 run 出现 read_skill_reference 失败 5 步 + activate_skill 反复 3 步 →
    MultiToolLoopBreaker 必须在 confidence 下降 ≤0.1 时熔断."""
    ...
```

---

## 10. 实施顺序与依赖

```
PR-A (Decision.task_progress + TaskProgressProjection + apply_task_progress)
   ↓
   ├── PR-B (MultiToolLoopBreakerGate) — 依赖 PR-A 的 projection
   └── PR-C (PG-007 三件套) — 依赖 PR-A 的 projection 作为 terminal_predicate 输入
PR-D (Skill 打包契约 + read_skill_reference_once) — 独立可并行
   ↓
PR-E (真实生产复测 + regression fixture) — 依赖 A+B+C+D
```

**并行策略**: PR-A 与 PR-D 可由独立 subagent 同时开工; PR-B 与 PR-C 在 PR-A 落地后开工。

---

## 11. 验证矩阵

| 变更 | 最低验证 | 必须追加 |
|---|---|---|
| Decision schema (PR-A) | `ruff check` + `ruff format` + 相关 pytest | contract test + 所有 emit/consume 同步测试 + mypy |
| TaskProgressProjection (PR-A) | 同上 | fold 5 fixture + 不变式测试 |
| apply_task_progress reducer (PR-A) | 同上 | 单测 + AgentStateProjection fold 更新 |
| MultiToolLoopBreakerGate (PR-B) | 同上 | 5 fixture + 与 ToolLoopBreakerGate 共存测试 |
| PG-007 三件套 (PR-C) | `ruff check` + `pytest tests/harness/` | precondition 失败/满足/缺失 + terminal_predicate 强制 stop + profile YAML 解析 |
| SKILL.md 契约 (PR-D) | 同上 | 加载期 fail-loud + 节流 + prompt 注入 |
| 真实生产复测 (PR-E) | `./scripts/lca-ops runs create ...` | officecli add ≥ 1 + sealer 触发 + terminal outcome |

---

## 12. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Decision.task_progress 必填破坏现有 reasoner | 同 PR 改所有 emit 方 + 集成测试 |
| TaskProgressProjection fold 性能 | confidence_history 用 deque(maxlen), O(1) append |
| MultiToolLoopBreakerGate 误熔断 (低进展但仍有效) | 5 fixture 测试覆盖 + 失败开放 (projection=None 时 return decision) |
| PG-007 三件套让老 profile YAML 失效 | 默认 `precondition=None` / `terminal_predicate=None`, 行为等价于今天 |
| SKILL.md 缺 references 导致所有 skill 加载失败 | PR-D 同 PR 内 fix 所有已有 SKILL.md (`skills/*/SKILL.md` 全扫, 加 `references: []` 占位) |
| 真实复测仍失败 | §9 fixture 把"在第 6 步前熔断"做成 integration test, 即使 run 失败也能验证新机制 |
| Session.append 在 T0 之前没 fsync 导致中断后丢事实 | §4.1.1 显式约定"append fsync 后才 yield"; 同 PR 写 `tests/integration/test_session_append_fsync.py` 模拟 SIGKILL 中断, 验证 T0 事件可恢复 |

---

## 13. 离开前卫生

- 无新增无期限 TODO
- 死代码 / 死 import 已清 (`ToolLoopBreakerGate` 保留, 但 docstring 注明"评估去留给后续 ADR")
- `ruff check --fix` 通过
- `git diff --check` 通过
- 提交信息: `<type>(<scope>): <subject>` — "做了什么 / 为什么"

---

## 14. ADR 编号备注

0214–0222 预留为本次收敛 (本 ADR + 未来 PR-D / PR-E 衍生 ADR)。如冲突, 取 0223 起。
