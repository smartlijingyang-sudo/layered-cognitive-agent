# Agent Note: AgentState.step 在生产路径上没有写者

Status: proposed

## Problem

`AgentState.step` 与 `AgentState.budget.used_steps` 在一次 run 的全程保持初值 0。三个后果已经可观测:

- **步数预算不生效。** `Budget.exceeded("steps")` 判据是 `_budget_limit_exceeded(used_steps, max_steps)`([state.py:46](../../../../lca/contracts/models/core/state/state.py))。`run_5490e7c8a76c` 的 `think.budget.gate` 跑了 10 次,10 次都返回 `next_hint=budget_ok`。`nodes/act/authorize/authorize.py:93-98` 的同一判据也不触发。工具循环唯一的硬上限因此只剩 `bundles/outer/phase_main.yaml` 的 `maxIterations: 24`;该 yaml 里 `budget: run.steps` 是死标签,`EdgeLoopObligation.budget` 在 [parsers.py:244](../../../../lca/framework/graph/lift/parsers.py) 校验为非空字符串之后再无读者,`select_edge` 只看 `max_iterations`([traversal.py:118-121](../../../../lca/framework/graph/traversal.py))。
- **终局预留封存不触发。** `should_seal = state.step >= max(0, max_steps - TERMINAL_RESERVE_STEPS)`([simple_body.py:355](../../../../lca/cognition/body/executor/simple_body.py)),`works_sealer.py:38` 与 `terminal/respond.py:36` 同判据。
- **事实层的 step 归属恒为 0。** `_phase_tool_context()` 从 `RunScope.step` 取值([tool_journal.py:19-30](../../../../lca/loop/commit/tool_journal.py)),该字段随 run 绑定一次后再不更新([execution_environment.py:115-120](../../../../lca/plugins/transport/webserver/carrier/runs/execute/execution_environment.py))。10 次工具调用全部标 `step: 0`,journal fold 按 step 归位时相互覆盖:`run_5490e7c8a76c` 的 step-003 fork 出 `activate_skill` + `runCommand`,journal 把 runCommand 的 `tool_call` 配上了 activate_skill 的 `tool_result(ok=true)`,而 runCommand 真实失败(`cd: /files: No such file or directory`)。doctor H7 因此报 `tool_total mismatch (9 vs 10)` 且 `forked_tool_calls=false`。

写者缺失的源头是一次已声明未完成的迁移。`63a68a4da`(ADR-0221 P3 切 v2 PlanInterpreter)删除了 `lca/plugins/loop/phase/perceive/standard/plugin.py`,那是 `RunDelta(metadata={"operation": "step"|"perception"})` 唯一的生产构造点;提交信息自述 "Trajectory completion and LLM-call wiring are still TODO under ADR-0221 P3"。替代节点 `nodes/perceive/observe/observe.py` 与 `nodes/perceive/fold/fold.py` 只发 typed port,均声明 `state_mutation="forbidden"`,不调 reducer。

现状普查(可复跑):

| 事实 | 验证 |
|---|---|
| `RunDelta(...)` 生产构造点为 0 | `grep -rn "RunDelta(" lca/` 无命中,3 处命中全在 `tests/` |
| 注册的 delta handler 为 10,消费者为 0 | [handler_registry_provider.py:48-57](../../../../lca/plugins/act/delta/handler_registry_provider.py) |
| reducer 12 个 `@_instrument_apply` 方法中,一次 run 只触发 3 个 | `run_5490e7c8a76c` spine:`runtime.reducer.apply` 仅 `apply_activation` / `apply_stop` / `apply_terminal_outcome` |
| `end_step` 零调用方 | [lifecycle_emit.py:194](../../../../lca/infrastructure/session/emit/lifecycle_emit.py);`step.ended.v1` 的唯一生产者是崩溃修复路径 [repair.py:192](../../../../lca/session/lifecycle/repair.py) |
| `AgentStateProjection.fold`(唯一 `state.step = data["step"] + 1`)零生产调用方 | [agent_state.py:72-75](../../../../lca/harness/projection/agent_state.py),调用方只有 `tests/harness/test_agent_state_projection.py` |
| `StepCoordinator.begin_step` / `end_step` 零生产调用方 | 唯一调用方 `CoordinatorAdapter` 自身零实例化;`LoopCursor` Protocol 把两者列在「不暴露」并注明「确认生产零 caller」 |
| `bump_step()` 不是 Protocol 方法,零实现 | 仅出现在 [loop_cursor.py:73](../../../../lca/contracts/observability/cursor/loop_cursor.py) 的 docstring |

真正在数步子的是观察面:`ModelVisibleHook.capture_pre_llm` 自增 `_step_counter` 并派生 `step-{n:03d}`([hook.py:242-243](../../../../lca/plugins/events/hooks/model_visible/hook.py)),journal fold 以 `llm.request.header` 为唯一 step 边界信号([journal_fold.py:477-484](../../../../lca/plugins/session/derivers/step_tree/journal_fold.py))。按 §2.2 分类它是 projection:可重建,不是事实源,且 C4 禁止业务路径据此写 State。

拓扑也已经不匹配任何「perceive = 一步」的假设。`bundles/outer/phase_main.yaml` 里 `perceive.main` 是 `entry: true` 且无任何边回指,循环体是 `act.main → think.main`。把写者放进 perceive 节点等于每次 run 只加一次。

## Proposal

在 `think.budget.gate` 恢复一次 `reducer.apply_step_advanced` 调用,作为循环内唯一的 step 写者,并让该节点能从 runtime carrier 解析到 Reducer。

选 `think.budget.gate` 的理由:它是 think 子图第一个节点,每次迭代恰好执行一次(`run_5490e7c8a76c` 10 次迭代对应 10 次),语义上等价于 ADR-0070 要求的「每轮迭代开头、在 perceive/think/act 之前」;而它本来就要读 `state.budget` 做判据,写者与读者同点,`used_steps` 与 `max_steps` 的比较不会跨节点漂移。

载体一侧沿用既有 seam:`DeclarativeRuntimeBindings` 已持有 `reducer` 字段([runtime_bindings.py:194](../../../../lca/runtime/support/runtime_bindings.py)),`with_extra({"writer": writer})`(同文件 229 行)已是「组合期 closure 不重开、运行期往 `capabilities` 叠值」的既定写法;`NodeRuntimeView.get(key)` 对非 `state` 键委派给 `RuntimePhaseCapabilities.values`([host_wiring.py:220-233](../../../../lca/framework/graph/host_wiring.py))。因此把 reducer 以同一方式贡献进 `capabilities.values`,`context.runtime.get("reducer")` 即可解析,无需新增载体机制。

同一变更内删除无生产者的 `RunDelta` 管道(`RegistryDeltaReducer`、`DeltaHandlerRegistry` Protocol、10 个 handler),或明确记录保留理由与 delete-when。留着它会让下一个读者再次误判「step 由 delta 管道推进」。

ADR 依据:ADR-0070(Accepted)规定 canonical `_loop` 在每轮迭代开头调 `apply_step_advanced`;ADR-0191 §4.2(Accepted)把 `apply_step_advanced` 与 budget 列在「Reducer 保留职责(LCA 控制面)」。恢复写者是执行既有 Accepted 决策,不是改变循环语义;C12 要求 `apply_*` 保持 `@_instrument_apply`,该方法已具备。

## Alternatives considered

### 为什么不删掉 `AgentState.step`,让消费者改读 cursor?

`CursorSnapshot` 没有 step 字段,这是显式决策:「step 边界由 ModelVisibleHook 唯一驱动,不在 cursor snapshot 暴露」([loop_cursor.py:49](../../../../lca/contracts/observability/cursor/loop_cursor.py)),`StdLoopCursor` 记录了曾持有 `step_index` 后砍掉。要消费者改读 cursor,得先把该字段加回去,即推翻 ADR-0169 的既定形状;同时与 ADR-0191 §4.2 的 Reducer 保留职责冲突,并触发 C12(projection fold 同步)与 C1(六 phase 闭集 gate 读 `state.step`)。代价是 15 个消费点全部改依赖注入,换来的仍是一个 projection 当事实源。

### 为什么不把写者放进 perceive 节点?

`perceive.main` 是 entry-only,没有边回指它。放那里等于整次 run 只推进一次,预算依旧不生效。ADR-0161 §1 声称的「每次 perceive → think → reflect 完成 step +1」描述的拓扑已不存在,且其指认的生产者 `plugins/phase_graph/perceive.py` 早在 `74e827d9a` 被删。

### 为什么不复活 `end_step` / `StepCoordinator` 作为写者?

两者都在 `LoopCursor` Protocol 的「不暴露」清单里并注明生产零 caller,其 docstring 亦写明「业务路径必须走 hook」。ADR-0176 D1 §2 禁止新增 `writable.step.*` 发射点(C1 词表)。复活它等于在观察面重开一条已被收口的第二轨。

### 为什么不只修 `_phase_tool_context()`,让它从 journal step_id 取真实步号?

那能修好事实层的 step 归属,但 `used_steps` 仍为 0,预算与封存两个安全判据继续失效;而且要解析 `step-{n:03d}` 字符串,把事实层耦合到一个显示格式上。它治的是 12 个症状里的 4 个。

### 什么都不做

工具循环的硬上限退化为 `maxIterations: 24`,与 Profile 声明的 `max_steps` 无关;`state_store` 的 `state_ref` 以 step 为键,所有 checkpoint 落在 `.../0` 相互碰撞;事实层继续按 step 归位失败,fork 场景下 journal 会把失败的工具结果替换成同批兄弟调用的成功结果。

## Acceptance criteria

- 一次含 N 轮工具迭代的 run,spine 里 `runtime.reducer.apply` 出现 `method=apply_step_advanced` 恰好 N 次,且 `state.step` 与 journal `step_index` 同步。
- 同一 run 的 `phase.tool.call.*` / `step.tool_call.record` / `step.tool_result.record` payload 的 `step` 取值互不相同且与所属 step 对应,不再恒为 0。
- 把 Profile 的 `max_steps` 设为小于迭代需求值时,`think.budget.gate` 返回 `should_terminate=True`、`next_hint=budget_exceeded_steps`,run 以可见收口文本结束,而不是撞到 `maxIterations`。
- 一次 fork 出两个工具调用的 run,journal 不再把 A 调用的 `tool_call` 与 B 调用的 `tool_result` 配对;doctor H7 的 `tool_total` 与 spine 一致或正确标注为投影上限。
- 一轮内的重试不推进 step(ADR-0162:`phase_retry` 不动 `state.step`)。
- `grep -rn "RunDelta(" lca/` 为空,或保留处有 owner 与 delete-when。

## Risks

`_step_counter` 是 hook 实例级且从不重置,`forget_run`([hook.py:178](../../../../lca/plugins/events/hooks/model_visible/hook.py))零调用方,因此观察面的 `step-003..step-012` 相对 journal 的 `step_index 1..10` 有偏移。恢复控制面写者后,两个 step 序号会同时可见且不相等,需要明确哪一个对外呈现,否则新的对账差异会盖住本次修复。

`subgraph_run.py:53-56` 在载体未持 `AgentState` 时替换一个临时 `AgentState(trace_id="", budget=_empty_budget())`。写进该替身的 step 推进对 run 不可见且不报错,属 §4 禁止的隐式 fallback;写者落地前需要确认生产路径不会走到这个分支。

`host_wiring.py:84` 的 `_DepthCarrier` 对 `AgentState` 是死代码(守卫 `not hasattr(outer_state, "graph_depth")`,而 86 行会在首次子图进入时把该属性写上去)。若 `AgentState` 将来变 frozen 或 `slots=True`,该 wrapper 会生效:读委派给 `_base`、写落在 wrapper 上,子图内的 `state.step` 推进将静默丢失。
