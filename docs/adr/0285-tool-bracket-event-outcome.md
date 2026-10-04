# ADR-0285：工具括号 EP 的 outcome 真值与双重发射收口

## 状态

**Proposed — 2026-10-04**

> **一句话**：`act.dispatch` / `act.observe.normalize` 节点级 `emit_on_exit` 把 `body.tool.execute.end` / `phase.tool.call.end` 的 `outcome` 恒写 `"success"`，因为 `dispatch_node_emits` 只传 `state`；而同一 EP 名已被决策级发射以真值复用（`wrapper="decision"`）。ADR-0240 预言的「节点级 dispatch 与命令式发射双重发射」已经发生。本 ADR 在「让括号事件携带真实 outcome」「移除括号事件的 outcome 字段」「移除冗余括号事件」三条路之间裁决。

## 0. 接任务前 7 问（精简自检）

1. 谁受益？raw spine 读者、`lca-ops journal trace` 的 footer 计数、未来任何以这些 EP 为输入的消费者。
2. 真实问题？(a) 括号事件的 `outcome="success"` 无条件成立，与 receipt 的事实相反时也成立（`run_56c3352cd22e` 有 2 次 `tool_wire` 失败，括号事件仍报 success）；(b) `lca-ops journal trace` 把 `phase.tool.call.end` 计数成「tool call」，括号事件让计数膨胀（10 次真实调用数成 18）；(c) 同一 EP 名存在两种语义载荷，只能靠 `wrapper` 字段区分。
3. 删掉会坏什么？取决于方案：删字段（D）无行为变化；删事件（E）会移除一组 spine 事件，需要核对依赖测试。
4. 更简单方案？在 backlog 记一笔然后不动。否决：raw spine 里已经躺着 18 个 `phase.tool.call.end`，其中 10 个没有 tool 身份、outcome 恒 success，任何新消费者都会读错。
5. 契约先行？是。实现未动，本 ADR 是纯决策记录。
6. 与现有 ADR 冲突？ADR-0240（node-emit dispatch）是父契约，其 §Risks 显式列出「与命令式 `publish_ep_bound` 双重发射」并标为 out of scope——本 ADR 正是收口那一条。ADR-0282 让被拒调用入 journal，括号事件与被拒路径无关。
7. 状态诚实？Proposed。三条候选路线各有代价，待拍板见 §4。

## 1. 实证（main@2edc98c18）

### 1.1 发射链路

- `lca/loop/emit/node_emitter.py::dispatch_node_emits(node_config, key, state)` 只把 `state` 传给 `emit_for_node`；`emit_for_node(ep_id, state, **kwargs)` 本身有 `**kwargs` 转发能力（:93-99），但没有东西可传。
- `lca/infrastructure/session/emit/cognitive_emit/tool_events.py`：`emit_body_tool_execute_end_for_state(state, *, outcome="success", ...)` 发布 `{"state_id": ..., "outcome": "success"}`；`emit_phase_tool_call_end_for_state` 同构。`outcome` 默认值因此永远生效。
- `bundles/act/act_subgraph.yaml`：`act.validate` `emit_on_enter: [phase.tool.call.start]`；`act.dispatch` `emit_on_enter: [body.tool.execute.start]`、`emit_on_exit: [body.tool.execute.end]`、`outputs: [receipt]`；`act.observe.normalize` `emit_on_exit: [phase.tool.call.end]`、`inputs/outputs: [receipt]`。
- `lca/framework/graph/interpreter.py:244,267`：`dispatch_node_emits(context.node_config, "emit_on_enter"/"emit_on_exit", outer_state)`。退出分支里 `output: NodeOutput = await strategy.execute(...)` 就在作用域内（:263-267），节点输出的 `receipt` 端口当时可得。

### 1.2 同一 EP 名下的两种载荷

`run_56c3352cd22e` 的 `phase.tool.call.end` 共 18 个：

- 10 个节点括号事件，无 `tool_name`，载荷 `{state_id}` + `outcome="success"`；
- 8 个 call 级事件，带 `tool_name` 与 `ok`（真实执行路径）。

`body.tool.execute.end` 同理 18 个：10 个括号事件 + 决策级/调用级 8 个带 `tool_name`、`wrapper="decision"`、`outcome`（`UseToolOperation` 里 `commit_body_tool_decision_end` 的真值）。

### 1.3 没有任何消费者读括号事件的 outcome

- `ToolDeriver` 只读 `step.tool_call.record` / `step.tool_result.record` / `body.sandbox.*` / `runtime.diagnostic`，不读这两个 EP。
- `journal_step_tree.yaml` 的 `tool_result_span_end` 从 `body.tool.execute.end` 提取 `ok`（不是 `outcome`），括号事件不写 `ok`，因此不污染折叠。
- `render.py:168-190` 渲染 `tool_name` / `ok` / `latency_ms`，不渲染 `outcome`。
- `render.py:739` 的 footer 用 `ep_counter.get("phase.tool.call.end")` 当「tool call」计数，括号事件使其膨胀。

### 1.4 ADR-0240 的预言

ADR-0240 §Risks 原文：act executor 的命令式调用与新 driver-level dispatch 会同时发 `phase.tool.call.start/end`，spec 已将其标为 out of scope。本节给出该 out-of-scope 项的实证：双重发射已发生，且其中一重（节点括号）无业务数据。

## 2. 候选路线

| | 改动 | 括号 outcome | 双重发射 | footer 计数 | 成本 | 架构 |
|---|---|---|---|---|---|---|
| A | `dispatch_node_emits` 增传 `outputs=output.port_values`，`node_emitter` 从 `receipt` 端口读 `EffectOutcome` 映射 | 真实 | 仍双（但两重都真） | 仍膨胀 | 中：interpreter + node_emitter + helper 契约 + spine.yaml 字段 | C14 保持（框架只转不透明端口值），但同一 outcome 真值出现第二个生产者，违反 §2.2「回执/投影单一所有权」 |
| B | `AgentState` 加「最近 receipt outcome」字段 + Reducer `apply_*` + fold mirror（C12） | 真实 | 仍双 | 仍膨胀 | 大 | C4/C7 冲突：State 是业务状态，不是观测总线 |
| C | act 节点 executor 自己 `publish_ep_bound` 发真实 outcome，从 yaml 声明移除 | 真实 | 三发风险 | — | 中 | 违反 ADR-0240「executors MUST NOT import node_emitter」，重开 strategy-skipping bug |
| D | 括号 helper 不再发 `outcome` 字段（纯生命周期标记） | 无 | 仍双（一重无业务数据） | 仍膨胀（另行修） | 最小 | 诚实：不写无法填真的字段；与决策级事件靠 `wrapper` 区分 |
| E | 从 yaml 移除 `act.validate`/`act.dispatch`/`act.observe.normalize` 的 5 条括号 emit 声明 | 移除事件 | 消除 | 正确（`phase.tool.call.end` 只剩 call 级） | 中：删 spine 事件 + 核对依赖测试 | 最净：决策级对（`commit_body_tool_decision_*`）+ call 级对 + ADR-0282 的 step 记录已覆盖全部语义 |

被拒路径的行为：ADR-0282 之后，被拦调用有 `step.tool_call.record(status="wire_blocked")` + `step.tool_result.record(ok=False)`。因此 E 移除括号事件后，被拒调用仍有完整 journal 事实，无空白。

## 3. 推荐

**D 为最小修正，E 为架构收口，A 否决。**

- D：`emit_body_tool_execute_end_for_state` / `emit_phase_tool_call_end_for_state` 不再写 `outcome` 字段。括号回归纯生命周期标记（`state_id` 而已），不留假信号。改 `render.py:739` 的 footer 计数为读 `step.tool_call.record`（该 EP 有 `status` 可区分 wire_blocked），独立可做。
- E：下一步把 5 条括号 emit 从 `bundles/act/act_subgraph.yaml` 移除，并核对 `tests/integration/test_act_dispatch_join_observe_e2e.py` 等测试是否以括号事件为锚。这一步才真正关闭 ADR-0240 的 out-of-scope 风险。
- A 否决理由：让括号携带真实 outcome 等于给 `EffectOutcome` 造第二个事实源，§2.2 要求回执单一所有权。`step.tool_result.record` 已是 receipt 的 journal 真值；括号再加一份，两份漂移时无法裁决。
- B、C 否决理由：分别违反 C4/C7 与 ADR-0240。

## 4. 待拍板（需 arch 轮裁决）

1. **D 还是 E？** 本次只做 D（最小修正）还是连 E（移除冗余括号事件）一起立项？E 会改变 spine 事件体积与若干依赖测试，建议单独一轮。
2. **footer 计数口径**：`lca-ops journal trace` 的「tool call」是否改读 `step.tool_call.record`？被拒调用（`status="wire_blocked"`）是否计入计数？
3. **是否给决策级 `body.tool.execute.*` 增加显式 `wrapper="decision"` 契约**，让 raw spine 消费者能稳定区分两重语义（当前 `wrapper` 字段存在但无契约约束）？

## 5. 验收（给 tests/quality lane）

- 若选 D：`phase.tool.call.end` / `body.tool.execute.end` 的括号载荷不再含 `outcome`；新增/修改 `tests/framework/graph/test_interpreter_node_emit.py` 一类测试断言载荷形状；`lca-ops journal trace` footer 计数不再膨胀。
- 若选 E：`bundles/act/act_subgraph.yaml` 移除 5 条声明；`test_act_dispatch_join_observe_e2e.py` 与任何依赖括号事件的测试同步更新；验证被拒路径仍有完整事实。
- 任一方案：`ruff` + 受影响套件失败集与基线一致，`lint-imports` 无新增。

## 决策记录

- 2026-10-04：ADR-0285 起草（Proposed），证据基于 `run_56c3352cd22e` 与 main@2edc98c18。