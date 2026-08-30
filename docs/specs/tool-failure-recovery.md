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
  → reflect
  → remember
  → stop
```

声明式运行路径由 [`CognitiveRuntime`](../../lca/layer2_runtime/runtime_loop.py) 绑定 `CompiledRunPlan`、phase executors、effect handler registry 和 delta handler registry，然后交给 [`DeclarativeRuntimeDriver`](../../lca/layer2_runtime/declarative_runtime.py)。通用解释器位于 [`GenericPlanInterpreter`](../../lca/harness/declarative/interpreter.py)。

## 3. SafeExecutor 的错误分型

[`SimpleSafeExecutor`](../../lca/layer1_cognitive/body/safe_executor.py) 的执行顺序是权限检查、参数校验、`ToolStarted`、缓存检查、局部重试、`ToolInvoked`。默认 [`RetryPolicy`](../../lca/contracts/models/team/role_team.py) 允许最多三次重试，并使用指数退避。

| 错误类型 | `failure_kind` | SafeExecutor 行为 | Agent 是否重新思考 |
|---|---|---|---|
| 未授权工具 | 无 Observation；`ToolDenied(permission)` | 立即拒绝 | 由上层决定，不能靠基础设施重试 |
| 参数校验失败 | `validation` | 返回 `Observation(success=False)`，不重试 | 可以修改参数后重试 |
| 确定性执行错误 | `execution` | 返回失败 Observation，不重复相同参数 | 可以更换方案或工具 |
| 网络超时、资源暂不可用 | `transient` | 按退避策略在同一动作内重试 | 若最终失败，再由 Agent 决定 |
| 人工审批等待 | 不转换为 Observation | 抛出 `ApprovalPendingError`，进入暂停流程 | 等待输入后 resume |

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

工具事件由 [`tool_journal_emit.py`](../../lca/layer1_cognitive/body/tool_journal_emit.py) 统一发射。一次完整的工具动作至少有以下事实：

| 事件 | 时机 | 关键字段 |
|---|---|---|
| `ToolDenied` | 权限或校验阻断 | `tool_name`、`reason` |
| `ToolStarted` | 进入实际执行前 | `tool_name`、`invocation_id`、参数摘要 |
| `ToolInvoked` | 最终执行结果确定后 | `ok`、`attempt`、`error`、`latency_ms`、`invocation_id` |

`ToolInvoked.attempt` 表示同一次 SafeExecutor 调用最终使用的尝试次数；`ok=false` 和 `error` 表示最终失败。工具事件模型见 [`journal.py`](../../lca/contracts/models/observability/journal.py)。

声明式解释器还会通过 [`RuntimeJournalCommitter`](../../lca/layer2_runtime/declarative_runtime.py) 记录 `phase.result` 和 `effect.receipt`，并携带 `plan_ref`、`node_ref` 和 operation。工具 Journal 事实回答“工具发生了什么”，phase 事实回答“执行图走到了哪里”。两者不能互相替代。

## 5. 失败如何进入 Reflect

`ACT` 阶段的 [`StandardPhaseExecutor`](../../lca/plugins/phase_executors/common.py) 只创建 `CommandEnvelope`。[`BodyActEffectHandler`](../../lca/plugins/providers/effect_handlers.py) 调用 Body，返回的 Observation 被解释器放入 `artifact_map["observation"]` 和 `artifact_map["act"]`，然后沿 `act.main → reflect.main` 继续。

如果使用 [`SimpleCritic`](../../lca/layer1_cognitive/brain/critic.py)，它会根据 `failure_kind` 生成可解释的 Reflection：

| 类型 | 反思提示 |
|---|---|
| `validation` | 参数不合法，需要修正参数 |
| `execution` | 工具执行失败，需要检查方案 |
| `transient` | 瞬时性错误，可以考虑重试 |

Reflect 不负责直接修改 State。它产生 Reflection；后续阶段将 Reflection 和 Observation 一起形成 Turn。

## 6. 两种认知恢复路径

### 6.1 标准闭环恢复

默认阶段图由 [`declarative-phase-graph.yaml`](../../bundles/declarative-phase-graph.yaml) 声明：

```text
perceive → think → act → reflect → remember → stop
stop → perceive（当 should_stop=false）
```

失败工具沿标准路径执行时：

```text
act 失败
  → reflect 生成 NEEDS_CORRECTION
  → remember 生成 turn delta
  → Reducer.apply_turn
  → state.history.append(turn)
  → stop 判断继续
  → 下一轮 perceive / think
```

[`TurnDeltaHandler`](../../lca/plugins/providers/delta_handlers.py) 将 `decision`、`observation` 和 `reflection` 组成 Turn，并调用 `Reducer.apply_turn`。下一次 Think 由 [`build_tool_history`](../../lca/layer1_cognitive/brain/tool_conversation.py) 将失败结果恢复成模型原生消息：

```text
assistant.tool_calls: file_write(...)
role=tool: permission denied: workspace is read-only
```

这样模型可以修改参数、更换路径、选择其他工具或向用户报告阻塞原因。

### 6.2 显式 Recovery Edge

Recovery profile 可以声明：

```text
reflect.main ── result.next_hints.admit_recovery ──→ think.main
```

[`RecoveryReflectExecutor`](../../lca/plugins/phase_executors/reflect.py) 在 Observation 缺失或 `success=false` 时设置 `admit_recovery=true`。恢复边必须带 `max_iterations` 和预算来源；默认 recovery 插件配置最多允许一次 reflect→think 重入，避免无限自我修正。[`recovery.py`](../../lca/plugins/phase_edges/recovery.py)

Recovery edge 解决的是“是否允许回到 Think”。如果该边跳过 Remember，失败 Turn 必须由额外的 Delta、Contribution 或自定义 Think executor 显式持久化或读取；否则失败 Observation 可能只存在于解释器的 `artifact_map`，尚未进入 `state.history`。标准闭环路径经过 Remember，因此默认情况下更容易保证下一次 Prompt 能看到失败原因。

## 7. StopPolicy 的终止判断

[`DefaultStopPolicy`](../../lca/plugins/state/stop_policy.py) 是 State 群提供给固定 Stop 阶段的局部策略。它只返回 `StopDecision`，由 Reducer 写入状态；完成、预算耗尽与 artifact closure 收口均在该单一深模块内完成。对失败工具的基本规则是：

```text
USE_TOOL + failed Observation → 通常继续
```

如果模型在最近多次工具失败后直接输出“已完成”，策略会检查连续失败窗口，防止把放弃误判为成功。达到 step 或 wall-clock 预算后，系统停止；最后有有效结果或交付物时可以完成，否则标记失败。

## 8. 暂停、恢复和幂等

人工审批不是工具失败。`ApprovalPendingError` 会被解释器捕获为 `paused` outcome，同时保存 `PhaseRunCursor`。Cursor 包含 `plan_ref`、当前 node、访问次数、边访问次数、artifacts、因果引用和预算快照，恢复时必须验证 `plan_ref` 一致。

effectful 操作使用幂等键：

```text
plan_ref + node_ref + decision_id
```

[`RuntimeIdempotencyStore`](../../lca/layer2_runtime/declarative_runtime.py) 的状态语义如下：

| claim 状态 | 语义 | 处理 |
|---|---|---|
| `new` | 尚未执行 | 允许调用 handler |
| `completed` | 已有完成回执 | 返回原 receipt，不重复副作用 |
| `in_progress` | 上次执行中断，结果不确定 | 返回 `RT-003`，不得盲目重发 |

Handler 成功返回后，网关保存统一 receipt；Handler 抛出异常时保留 `in_progress`，这样恢复流程不会把未知状态当作“从未执行”。如果 effect 返回一个明确的失败 Observation，该 effect 本身仍然有确定回执；认知层可以产生新的 Decision，但不应使用同一幂等键重复发起同一外部动作。

当前 `RuntimeIdempotencyStore` 是进程内实现，适合验证协议和同进程去重。跨进程或跨重启的生产恢复必须把 claim/receipt 持久化到 Journal、数据库或其他 durable store；不能把进程内字典误认为持久化事实源。

## 9. 失败结果的统一上层语义

`GenericPlanInterpreter` 将运行结果收敛为 `DeclarativeRunOutcome`：

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

- [`runtime_loop.py`](../../lca/layer2_runtime/runtime_loop.py)
- [`declarative_runtime.py`](../../lca/layer2_runtime/declarative_runtime.py)
- [`interpreter.py`](../../lca/harness/declarative/interpreter.py)
- [`safe_executor.py`](../../lca/layer1_cognitive/body/safe_executor.py)
- [`tool_journal_emit.py`](../../lca/layer1_cognitive/body/tool_journal_emit.py)
- [`declarative-phase-graph.yaml`](../../bundles/declarative-phase-graph.yaml)
