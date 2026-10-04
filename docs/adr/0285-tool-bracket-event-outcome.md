# ADR-0285：工具调用结局的单一所有权与括号事件收口

## 状态

**Proposed — 2026-10-04**

本 ADR 从第一原理推导工具调用结局应如何落盘，裁决「节点级工具括号事件」的去留。第一次起草采用实证+候选表结构；2026-10-04 按第一原理重写：先定行为要求与不变量，再从零设计推导出目标，最后把现状差距和决策作为推导结论呈现。arch 轮裁决记录保留在 §决策记录。

## 1. 第一原理

**每次工具调用尝试的结局必须可从运行记录判定，且任何运行记录不得声称与权威结局相反的事实。**

「尝试」包含三类：成功执行、派发后失败、派发前被拒。这三类都必须让读者（机器或人）判定结局。任何记录如果带有结局字段，其值不得与权威结局矛盾；如果该记录无法取得权威结局，它就不带结局字段。

## 2. 不变量（非协商项）

- **回执单一所有权（AGENTS.md §2.2）**：`EffectReceipt` 是执行边界产生的权威结局；`step.tool_result.record` 是它在 journal 的单一真值。任何对象不能同时承担事实源和投影职责，因此同一结局事实不允许有第二个生产者。
- **C11 事件闭集**：`EXECUTION_POINTS` 是白名单，每个 EP 名必须有一个注册的语义、一个注册的生产者集合。
- **C14 图与业务隔离**：图框架不知道业务，业务不感知图框架。
- **ADR-0240 节点 emit 契约**：`emit_on_enter` / `emit_on_exit` 是 yaml 声明的生命周期触发器；节点 executor 不得 import `node_emitter`。其 Risks 节已预言「节点级 dispatch 与命令式发射双重发射」并标为 out of scope。
- **ADR-0282 派发前拒绝写实**：被拒调用必须留下 `step.tool_call.record(status="wire_blocked")` + `step.tool_result.record(ok=False)`。
- **控制/观察分离（C7）**：`AgentState` 是业务状态，不是观测总线。

## 3. 从零设计

以第一原理为唯一要求重新设计工具调用观测词表，得到的答案不含节点级括号事件：

- `step.tool_call.record`：尝试身份（tool / invocation_id / arguments / status）。
- `step.tool_result.record`：结局真值（ok / outcome / error / failure_kind）。
- `body.tool.execute.start|end`：一次 `use_tool` 决策的括号，带 `wrapper="decision"` 与真实结局，用于包住多 call 批次。
- `phase.tool.call.start|end`：每个派发到执行器的 call 的相位标记。
- 节点访问本身由 `phase_graph.node.*` 观测，其结局（策略执行成功或抛异常）已经在那条事实里。

工具结局真值只存在于 `step.tool_result.record`。任何节点生命周期标记都不携带工具结局字段，因为节点访问没有权威结局，只有回执有。

## 4. 现状与差距

现状在从零设计的目标之外多出一组「节点括号事件」：

- `bundles/act/act_subgraph.yaml`：`act.validate` `emit_on_enter: [phase.tool.call.start]`；`act.dispatch` `emit_on_enter: [body.tool.execute.start]`、`emit_on_exit: [body.tool.execute.end]`；`act.observe.normalize` `emit_on_exit: [phase.tool.call.end]`。
- `lca/loop/emit/node_emitter.py::dispatch_node_emits` 只把 `state` 传给 emitter，于是 `emit_phase_tool_call_end_for_state` / `emit_body_tool_execute_end_for_state` 的 `outcome="success"` 默认值永远生效（`tool_events.py:41,110`）。
- 结果：`body.tool.execute.end` 与 `phase.tool.call.end` 各自有两种载荷——括号事件只有 `state_id` + `outcome="success"`，决策级/调用级事件带 `tool_name` 与真实结局（`wrapper="decision"`）。`run_56c3352cd22e` 中 `phase.tool.call.end` 共 18 个，10 个是没有工具身份、结局恒 success 的括号事件。

差距由两个独立缺陷组成：

1. **类别错误**：节点访问的结局（控制面）被写成了工具结局（业务面）。回执失败时，括号事件仍报 success，违反第一原理。
2. **结构冗余**：节点括号与决策级 `wrapper="decision"` 括号功能相同（都是「一次 use_tool 决策的起止」），ADR-0240 预言的重复发射已经发生。

## 5. 决策

1. **立即（D）**：`emit_phase_tool_call_end_for_state` 与 `emit_body_tool_execute_end_for_state` 不再写 `outcome` 字段。括号事件回归纯生命周期标记（`state_id`），消除违反第一原理的假字段。这是过渡步骤，不是终态。
2. **收口（E）**：从 `bundles/act/act_subgraph.yaml` 移除上述 5 条括号 emit 声明，关闭 ADR-0240 的 out-of-scope 风险，使 `body.tool.execute.*` / `phase.tool.call.*` 回归单一语义。移除后被拒路径仍有完整事实（ADR-0282 的 step 记录），成功/失败路径仍有决策级与调用级事件，无空白。
3. **计数口径**：`lca-ops journal trace` 的「tool call」改读 `step.tool_call.record`（它统计每次尝试并带 status）；`status="wire_blocked"` 不计入执行数，被拒数以独立计数保持可见。
4. **契约钉住区分键**：决策级 `body.tool.execute.*` 的 `wrapper="decision"` 写入 spine 事件目录，成为该 EP 的显式区分字段，防止 raw 消费者把两种语义读混。

## 6. 备选方案与不变量评估

| 选项 | 满足第一原理 | C11 单一语义 | §2.2 单一所有权 | C14 | ADR-0240 | 结论 |
|---|---|---|---|---|---|---|
| A 括号携带真实 outcome（driver 转发输出） | 是 | 否（EP 仍双语义） | 违反：第二个结局生产者 | 通过 | 通过 | 否决 |
| B AgentState 承载结局 | 是 | 否 | 违反 C7（State 当观测总线） | — | 通过 | 否决 |
| C 节点 executor 自发射 | 是 | 是 | 是 | 违反 | 违反 | 否决 |
| D 移除 outcome 字段 | 是 | 否（过渡态） | 通过 | 通过 | 通过 | **先行** |
| E 移除括号事件 | 是 | 是 | 通过 | 通过 | 通过 | **收口** |
| 什么都不做 | 否 | 否 | 违反 | — | — | 否决 |

否决理由均来自不变量，不是成本偏好：A 给回执结局制造第二个生产者，两份漂移时无法裁决；B 让业务状态承载观测值；C 重开 ADR-0240 关掉的 strategy-skipping bug；什么都不做保持恒假的 `outcome`。

## 7. 后果

- **类型与失败语义**：工具结局事实唯一在 `step.tool_result.record`；`body.tool.execute.*` / `phase.tool.call.*` 只承担身份与相位，不再声称结局。被拒调用由 `status="wire_blocked"` 区分，失败调用由 `ok=False` 区分。
- **时序**：决策级 `body.tool.execute.end` 仍在工具执行后由 `UseToolOperation` 的 finally 写；括号事件移除不影响它。
- **所有权**：工具结局单一生产者 = `step.tool_result.record`；节点生命周期观测 = `phase_graph.node.*`；EP 语义单一。
- **外部后果**：raw spine 里不再出现无身份、恒 success 的工具事件；`lca-ops journal trace` 计数恢复真实；`run_56c3352cd22e` 这类「10 次尝试被拒 2 次仍读 ok」的 run 在 ADR-0282 落地后健康判定已正确，本 ADR 进一步消除计数与 raw 数据里的残余误导。
- **兼容**：D 与 E 都是删除性变更。E 会减少 spine 事件体积，需要盘点以括号事件为锚的测试（如 `tests/integration/test_act_dispatch_join_observe_e2e.py`）。

## 8. 相关

- [ADR-0240](0240-node-emit-dispatch-whitelist-additions.md) — 节点 emit 调度契约；§Risks 预言本 ADR 收口的双重发射。
- [ADR-0282](0282-blocked-tool-call-journal.md) — 派发前拒绝写实；被拒路径的事实来源。
- AGENTS.md §2.2（回执/投影单一所有权）、§3 C7/C11/C14。
- 关联缺口（不在本 ADR 范围）：`body.tool.execute.start` 存在调用级事件（按 `toolu_*` 键）但没有配对的调用级 end，属既有的 start/end 计数不对称问题，另立议题。

## 决策记录

- 2026-10-04：ADR-0285 第一次起草（Proposed），实证基于 `run_56c3352cd22e` 与 main@2edc98c18。
- 2026-10-04：arch 轮裁决（记录于第一次起草后）：① D 先行、E 另立一轮；② footer 计数改读 `step.tool_call.record`，`wire_blocked` 不计执行数；③ `wrapper="decision"` 显式契约采纳。裁决依据与 §5 一致。
- 2026-10-04：按第一原理重写（本版本）：引入 §1-3 的推导链，把 D/E/计数/wrapper 作为推导结论而非候选偏好呈现。