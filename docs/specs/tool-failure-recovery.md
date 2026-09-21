# 工具调用失败与恢复规范

本文定义 LCA 中工具调用失败后的执行、记录、恢复和重试边界。它描述当前运行时使用的协议，不把工具失败处理隐藏在未声明的 Hook 或异常分支中。

## 1. 核心原则

工具失败处理分为两个层次。`SafeExecutor` 负责同一个工具动作的基础设施级重试；认知循环负责将失败结果交给 `reflect` 和后续 `think`，由 Agent 重新规划。前者不会重新调用 LLM，也不会改变参数；后者可以产生新的 `Decision`。

所有 effectful `act` 都必须经过 `CommandEnvelope` 和 `EffectGateway`。Effect handler 只返回执行结果，不直接修改 `AgentState`。状态变化通过 `RunDelta` 交给 `Reducer`，工具生命周期通过统一的 Journal 发射边界记录。

## 2. 完整调用链

```text
think
  → Decision(USE_TOOL)
  → act PhaseExecutor
  → CommandEnvelope(operation=body.act)
  → EffectGateway
  → BodyActEffectHandler
  → Body / ActionRegistry
  → SafeExecutor
  → ToolStarted
  → _execute_with_retry
  → ToolInvoked
  → Observation
  → act.observe（normalize → commit_fact → terminate_decide）
  → think（USE_TOOL 失败回到 think，不经 reflect / remember）
```

声明式运行路径由 [`CognitiveRuntime`](../../lca/runtime/loop/runtime_loop.py) 绑定 `CompiledRunPlan`、phase executors、effect handler registry 和 delta handler registry，然后交给 [`DeclarativeRuntimeDriver`](../../lca/loop/driver.py)。通用解释器位于 [`PlanInterpreter`](../../lca/framework/graph/interpreter.py)。

## 3. SafeExecutor 的错误分型

[`SimpleSafeExecutor`](../../lca/cognition/body/executor/safe_executor.py) 的执行顺序是权限检查、参数校验、`ToolStarted`、缓存检查、局部重试、`ToolInvoked`。默认 [`RetryPolicy`](../../lca/contracts/models/team/role/team.py) 允许最多三次重试，并使用指数退避。

| 错误类型 | `failure_kind` | SafeExecutor 行为 | Agent 是否重新思考 |
|---|---|---|---|
| 未授权工具 | 无 Observation；`ToolDenied(permission)` | 立即拒绝 | 由上层决定，不能靠基础设施重试 |
| 参数校验失败 | `validation` | 返回 `Observation(success=False)`，不重试 | 可以修改参数后重试 |
| 确定性执行错误 | `execution` | 返回失败 Observation，不重复相同参数 | 可以更换方案或工具 |
| 网络超时、资源暂不可用 | `transient` | 按退避策略在同一动作内重试 | 若最终失败，再由 Agent 决定 |
| 人工审批等待 | 无 Observation；`Decision.needs_approval` 为真 | `act.approve.gate` 路由到 `intervene.interrupt`，写 `approval.persisted.v1` 与 `waiting_input` checkpoint | 等待输入后 resume |
| 机器平面授权拒绝 | `error_kind` 为 `scope_violation` 或 `approval_required` | 返回 `Observation(success=False)`，`state` 平铺 `verdict` 与 `reason` 并携带 `approval_request`，不抛异常 | `scope_violation` 不重试；`approval_required` 应转成一次向用户的询问 |

相同参数的确定性错误不应被重复提交。例如，空表达式、非法路径或不符合工具 schema 的参数，重试不会改变结果。瞬时错误的重试仍属于同一个 `Decision`，不会制造新的认知步骤。

```python
for attempt in range(retry_policy.max_retries + 1):
    obs = await self._execute_once(tool, args, attempt)
    if obs.success:
        return obs
    if obs.extra.get(FAILURE_KIND) != FAILURE_KIND_TRANSIENT:
        return obs
    await asyncio.sleep(delay)
    delay *= retry_policy.backoff_multiplier
```

## 4. Journal 记录边界

工具事件由 [`tool_journal.py`](../../lca/cognition/body/emit/tool_journal.py) 统一发射。一次完整的工具动作至少有以下事实：

| 事件 | 时机 | 关键字段 |
|---|---|---|
| `ToolDenied` | 权限或校验阻断 | `tool_name`、`reason` |
| `ToolStarted` | 进入实际执行前 | `tool_name`、`invocation_id`、参数摘要 |
| `ToolInvoked` | 最终执行结果确定后 | `ok`、`attempt`、`error`、`latency_ms`、`invocation_id` |

`ToolInvoked.attempt` 表示同一次 SafeExecutor 调用最终使用的尝试次数；`ok=false` 和 `error` 表示最终失败。工具事件模型见 [`journal.py`](../../lca/contracts/models/observability/journal/journal.py)。

声明式解释器还会通过 [`RuntimeJournalCommitter`](../../lca/loop/driver.py) 记录 `phase.result` 和 `effect.receipt`，并携带 `plan_ref`、`node_ref` 和 operation。工具 Journal 事实回答“工具发生了什么”，phase 事实回答“执行图走到了哪里”。两者不能互相替代。

**事实层按 invocation 记，step-tree 投影按 step 记，两者不是一对一。** 一个 `Decision` 可以 fork 出多个并行工具调用（`Decision.tool_calls` 是列表），事实层的 `step.tool_call.record` / `step.tool_result.record` 每个 invocation 一条，完整；但投影侧 [`StepRecord.tool_call`](../../lca/contracts/models/observability/journal/step.py) 是单数，一个 step 只能承载一个 invocation。因此并发工具调用的 run 里，`journal.json` 的 distinct invocation 数会少于事实层，doctor H7 会把这种情况判为 `ok=null`（投影上限）而不是 `ok=false`（事实不一致）。要对账并发调用必须读 spine 事实层，不能读 step-tree。

## 5. 失败如何回到模型

act 子图的 [`act.envelope`](../../lca/nodes/act/envelope/envelope.py) 只创建 `CommandEnvelope`（一个 `Decision.tool_calls[i]` 对应一个 envelope）。[`BodyActEffectHandler`](../../lca/plugins/act/effect/handlers_provider.py) 调用 Body，返回的 Observation 由 [`concept.effect.execute`](../../lca/nodes/concept/effect/execute.py) 折成 `EffectReceipt`，再经 `act.observe.normalize → commit_fact → terminate_decide` 决定回 `think.main` 还是收口（§7）。`decision.action_type == use_tool` 时回 `think.main`，不经 reflect；其余情况才沿 `act.main → reflect.main` 继续。

走 reflect 时，[`SimpleCritic`](../../lca/cognition/brain/reasoner/critic.py) 会根据 `failure_kind` 生成可解释的 Reflection：

| 类型 | 反思提示 |
|---|---|
| `validation` | 参数不合法，需要修正参数 |
| `execution` | 工具执行失败，需要检查方案 |
| `transient` | 瞬时性错误，可以考虑重试 |

Reflect 不负责直接修改 State。它产生 Reflection；后续阶段将 Reflection 和 Observation 一起形成 Turn。

## 6. 两种认知恢复路径

### 6.1 标准闭环恢复

外层计划由 [`phase_main.yaml`](../../bundles/outer/phase_main.yaml) 声明，首个匹配边生效：

```text
perceive → think → act → think            （decision.action_type == use_tool）
                   act → reflect → remember → terminal.commit
                   act → terminal.commit   （should_terminate / approve_rejected）
                   think → terminal.commit （respond 且 response_text 非空 / 预算耗尽）
```

失败工具走的是第一条：`act.main → think.main`，不经 reflect / remember。失败 Observation 因此**不会**经 [`TurnDeltaHandler`](../../lca/plugins/act/delta/handlers_provider.py) 进入 `state.history`，它靠下一次 Think 的 [`think.history.assemble`](../../lca/nodes/think/history/assemble.py) 从 `RunSessionWriter.derive_messages` 恢复成模型原生消息（同一处做 orphan-drop，丢弃没有配对结果的 tool_call）：

```text
assistant.tool_calls: file_write(...)
role=tool: permission denied: workspace is read-only
```

这样模型可以修改参数、更换路径、选择其他工具或向用户报告阻塞原因。

### 6.2 显式 Recovery Edge

外层计划声明的恢复边（[`phase_main.yaml`](../../bundles/outer/phase_main.yaml)）：

```yaml
- from: reflect.main
  to: think.main
  when: { kind: eq, port: { name: routing, field: next_hint }, value: admit_recovery }
  loop:
    maxIterations: 1
    budget: run.steps
    terminalPredicate: { kind: ne, port: { name: routing, field: next_hint }, value: admit_recovery }
```

[`phase.reflect.admit_recovery`](../../lca/nodes/reflect/admit_recovery/admit_recovery.py) 在 Observation 缺失或 `success=false` 时把 `routing.next_hint` 置为 `admit_recovery`；它只做路由判定，不改 `reflection` payload。恢复边必须带 `maxIterations` 与预算来源，默认最多一次 reflect→think 重入（插件默认见 [`recovery/plugin.py`](../../lca/plugins/loop/graph/recovery/plugin.py)）。

这条边只在 `decision.action_type != use_tool` 时才可能到达（USE_TOOL 失败在 §6.1 已直接回 think），因此它覆盖的是「模型已经收尾、但 Observation 说明没收尾成功」这一类。两条路径都跳过 Remember，失败 Observation 都不进 `state.history`；下一次 Prompt 能看到失败原因，靠的是 §6.1 的 `derive_messages`，不是 Turn 持久化。新增恢复路径时若依赖 `state.history`，必须自己显式写入。

## 7. 终止判断

`StopPolicy` / `DefaultStopPolicy` 已按 ADR-0230 删除。终止不再由 host 侧策略类判断模型输出，而是 [`terminal.commit`](../../bundles/outer/phase_main.yaml) 节点收口：边谓词决定谁能到达它，[`TerminateStrategy`](../../lca/framework/graph/strategies/terminate_strategy.py) 由 `decision` / `act_outcome` 端口构造 `StopPayload`，driver 的 `_stop_from_interpretation_output` 把它提升为 `StopDecision`，再由 Reducer 依 C12 顺序 `apply_stop` → `apply_terminal_outcome`。

到达 `terminal.commit` 的边只有五条：

| 来源 | 条件 | 语义 |
|---|---|---|
| `think.main` | `decision.action_type == respond` 且 `response_text != ""` | 模型自己收尾（不再发 tool call），唯一的成功出口 |
| `think.main` | `routing.should_terminate == true`（`think.budget.threshold_gate`） | 预算耗尽 |
| `act.main` | `should_terminate == true`（`act.observe.terminate_decide`） | host 侧派发失败：receipt 无 `failure_kind`，说明没有工具报告过任何结果 |
| `act.main` | `approval_routing.next_hint == approve_rejected` | 审批被拒 |
| `remember.main` | 无条件 | 闭环收口 |

对失败工具的基本规则是：

```text
USE_TOOL + failed Observation → 继续（act.main → think.main）
```

带 `failure_kind` 标签的失败（`execution` / `transient` / `validation` / `tool_wire`）都是工具对*自己标的物*的报告，必须回到模型手里；`execution` 的含义是「同样参数重试无意义」（基础设施级不重试由 `SafeExecutor` 保证），不是「run 不能继续」。

**一个 turn 只产出一张 receipt，所以聚合必须保住分量的分类。** `act.envelope` 为每个 `tool_calls[i]` 铸一个 envelope，但 1:1 wiring 只派发第一个，Body 按整个 `decision.tool_calls` 批执行（[`ToolBatchExecutor`](../../lca/cognition/body/tools/tool_batch_executor.py)），N 条 per-call Observation 折成一条聚合体。聚合体的 `failure_kind` 由 [`fold_failure_kinds`](../../lca/contracts/atoms/semantic/keys.py) 从失败分量里取优先级最高者（`tool_wire` > `validation` > `execution` > `transient`，与 emit 顺序和并发分段无关，C8）；委派聚合 [`_aggregate_observations`](../../lca/cognition/body/actions/action_handlers.py) 同规则。这是上表「receipt 无 `failure_kind` ⇒ 没有工具报告过任何结果」在批次上仍然成立的前提——折叠丢掉分类，就会把一次普通工具失败读成 host 派发失败并收口 run（ADR-0230 Amendment，`run_136671e2ff8a`）。所有分量都未分类时聚合体也未分类，host 派发失败分支照旧可达。每调用明细仍在 `extra[OBS_TOOL_RESULTS]`，`concept.effect.execute._batch_rows` 与 `SimpleCritic._partial_batch_reflection` 读它，聚合分类不替代它。

兜住卡死循环的是 [`think.budget.gate`](../../lca/nodes/think/budget/threshold_gate.py)：它每轮 think 都执行，`Budget.exceeded()` 为真就发 `should_terminate=true` 收口。[`create_budget`](../../lca/contracts/models/core/policy/budget.py) 默认 `max_steps=50`、`max_wall_clock_seconds=300`。ADR-0225 已删除 per-node `max_visits`。

另外两道界**目前在所有 run 上都失效**：[`ToolLoopBreakerGate`](../../lca/cognition/brain/decision_gates/tool/loop_breaker.py)（同一工具连续失败 3 次阻断）与 [`ProgressLoopDetector`](../../lca/cognition/brain/decision_gates/progress/loop_detector.py)（连续 6 步无进展强制 RESPOND）都读 `control_turns(state)`。该 reader 优先取 durable `turn.control.v1` 折叠，回退到 `state.control_turns`（由 `Reducer.apply_turn` 写）。生产里通往 `apply_turn` 的唯一路径是 `TurnDeltaHandler.apply` → `Reducer.commit_turn`，而 `lca/` 下没有任何一处构造 `RunDelta`，这条链从不执行。两个 gate 因此每次都读到 0 条 turn。两个实盘工具循环 run 实测：`remember` 与 `reflect` 节点访问各 0 次，账本里没有 `turn.*` 事实。这是既有缺陷，详见 ADR-0230 Amendment。

## 8. 暂停、恢复和幂等

人工审批不是工具失败。同意走图上通道：`Decision.needs_approval` 为真时 `act.approve.gate` 路由到 `intervene.interrupt`，写 `approval.persisted.v1` 与 `waiting_input` checkpoint，见 [HIL 审批状态机](../adr/0078-hil-approval-state-machine.md) 与 [graph HITL 暂停未被执行](../notes/implemented/seam/2026-09-18-graph-hitl-pause-not-honored.md)。[`ResultFinalizer`](../../lca/runtime/projection/result_finalizer.py) 对 paused 的 declarative run 强制要求 approval request 与非空 `approval_id`。

`ApprovalPendingError` 仍是 contracts 导出的暂停信号，两个 SafeExecutor 都原样向上传播它，`lca/` 下已无生产抛出点。机器平面的授权判定返回带类型的 Observation，见 [机器平面路径授权归 CapabilityGrant](../notes/implemented/seam/2026-09-21-machine-path-authorization-belongs-to-capability-grant.md)。

暂停保存 `PhaseRunCursor`。Cursor 包含 `plan_ref`、当前 node、访问次数、边访问次数、artifacts、因果引用和预算快照，恢复时必须验证 `plan_ref` 一致。

effectful 操作使用幂等键：

```text
plan_ref + node_ref + decision_id
```

[`RuntimeIdempotencyStore`](../../lca/loop/driver.py) 的状态语义如下：

| claim 状态 | 语义 | 处理 |
|---|---|---|
| `new` | 尚未执行 | 允许调用 handler |
| `completed` | 已有完成回执 | 返回原 receipt，不重复副作用 |
| `in_progress` | 上次执行中断，结果不确定 | 返回 `RT-003`，不得盲目重发 |

Handler 成功返回后，网关保存统一 receipt；Handler 抛出异常时保留 `in_progress`，这样恢复流程不会把未知状态当作“从未执行”。如果 effect 返回一个明确的失败 Observation，该 effect 本身仍然有确定回执；认知层可以产生新的 Decision，但不应使用同一幂等键重复发起同一外部动作。

当前 `RuntimeIdempotencyStore` 是进程内实现，适合验证协议和同进程去重。跨进程或跨重启的生产恢复必须把 claim/receipt 持久化到 Journal、数据库或其他 durable store；不能把进程内字典误认为持久化事实源。

## 9. 失败结果的统一上层语义

`PlanInterpreter` 将运行结果收敛为 `DeclarativeRunOutcome`：

```text
completed
paused
failed
effect_uncertain
```

对于计划校验错误或未处理执行异常，解释器会捕获异常，生成 `run.failed` 事实并保存失败点 Cursor，而不是让 Gateway 自己猜测异常发生的位置。Effect 未知状态应当保持 `effect_uncertain` 语义，等待人工或外部系统确认。

## 10. 代码审查要点

实现新的失败处理时，应检查以下约束：

1. 是否区分基础设施重试和认知重试。
2. 是否把工具失败转换为带 `failure_kind` 的 Observation。
3. 是否发出了唯一的 `ToolStarted` / `ToolInvoked` / `ToolDenied` 事实。
4. 是否通过 `RunDelta` 和 Reducer 更新 AgentState。
5. 是否保证下一次 Think 能读取失败 Observation。
6. 是否为 recovery edge 声明 predicate、最大迭代次数和预算。
7. 是否使用幂等键避免恢复时重复世界副作用。
8. 是否把不确定 effect 与普通失败区分开。

## 参考

- [`runtime_loop.py`](../../lca/runtime/loop/runtime_loop.py)
- [`driver.py`](../../lca/loop/driver.py)
- [`interpreter.py`](../../lca/framework/graph/interpreter.py)
- [`safe_executor.py`](../../lca/cognition/body/executor/safe_executor.py)
- [`tool_journal.py`](../../lca/cognition/body/emit/tool_journal.py)
- [`phase_main.yaml`](../../bundles/outer/phase_main.yaml)
- [`terminate_decide.py`](../../lca/nodes/act/observe/terminate_decide.py)
- [`terminate_strategy.py`](../../lca/framework/graph/strategies/terminate_strategy.py)
- [`loop_detector.py`](../../lca/cognition/brain/decision_gates/progress/loop_detector.py)
