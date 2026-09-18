# Agent Note: graph HITL 暂停未被执行(should_terminate 无消费方)

Status: implemented

> 根决策: [ADR-0228](../../../adr/0228-plan-intervene-delegate-subgraphs.md) §Decision 4(interrupt 暂停) / §2.6(gate 语义);[2026-09-16-resume-askuser-flow-audit.md](../../plans/2026-09-16-resume-askuser-flow-audit.md) Gap B/G(干预走 HTTP + journal，不走 WS)。本 note 登记 e2e 实证的最后一公里缺口：暂停意图已能正确发出，但执行层不停住。

## Problem

`intervene.interrupt` 返回 `RoutingDecision(should_terminate=True)` 后，live run 不暂停：

- `PlanInterpreter.run` 主循环(`lca/framework/graph/interpreter.py:195-383)只认 `terminal_predicate` 与 edge 穷尽；`routing.should_terminate` 无任何消费方(`rg should_terminate` 仅命中注释与 loop 控制插件)。
- `bundles/outer/phase_main.yaml:342-343` 把 `intervene.interrupt → intervene.resume` 写成 `when: true` 无条件边，于是暂停后当场 inline resume：`intervene.resume` 用刚发出的 Command(无人工答案)合成 respond decision → `act.fanout` 空 envelope → `apply_error` → run FAILED。
- 同一条路上先前已修三处(同 PR 闭环)：`think.decision.parse` / `DefaultDecisionClassifier` 漏置 `needs_approval`(与 `decision.compose.action` 不一致)；`AskUserExecutor` 抛 `ApprovalPendingError` 被 `_dispatch` 折成 FAILED；`intervene.interrupt` 的 `spine_seq` 端口无生产者且 kind 按 `action_type == "ask_user"` 推导(生产者实际发 USE_TOOL)。三处均有回归测试，见 Decision criteria。

e2e 证据(`run_d4c49698eb53`，kernel 重启后)：journal 含 `Command(kind='approve', issued_at_seq=95)`，`needs_approval: true`，但无 `session.checkpoint.v1{waiting_input}` / `approval.persisted.v1` 事实；trajectory 为 `... act.approve.gate → intervene.interrupt → intervene.resume → act.approve.gate(respond) → act.envelope → act.fanout(terminal)`，全程约 4s，无人工介入。

## Proposal

暂停语义在现有 seam 内闭环，不新增事件词表(C11)与阶段(C1)：

1. **遍历 honor 中止** — 主循环在 visit 成功后检查 `output.port_values["routing"]` / `approval_routing` 的 `should_terminate`；为真则停住遍历并返回 terminal(terminal_node = interrupt 节点)，不再 `select_edge`。
2. **暂停事实** — 停住时走现有 `emit_approval_pause_from_result` 等价路径写 `approval.persisted.v1` + `session.checkpoint.v1{waiting_input}`(复用 `lca/infrastructure/session/emit/lifecycle_emit.py`)，run 状态置 WAITING_INPUT；WS 侧已有 `step_start{human_approval} → agent_runtime_end{waiting_for_human}` 双事件(`EventTranslator._spine_close` + coordinator 多发表)。
3. **恢复重入** — `POST /answer → resume_approval` 已有；恢复时以人工 `Command(kind=approve)` 经 `act.resume → act.approve.gate` 重入(现有边)，不再 inline 合成。

## Decision criteria(可观察)

- e2e：同样 prompt 的 run 在 `intervene.interrupt` 后停住；`session.status == waiting_input`；journal 含 `approval.persisted.v1` + `session.checkpoint.v1{waiting_input}`；WS 流含 `step_start{human_approval}` 先于 `agent_runtime_end{waiting_for_human}`。
- e2e：`POST /answer` 后 run 恢复并执行到 `completed`，同一 `run_id`，`tool_call_id` 稳定。
- 回归：`tests/intervene/`、`tests/runtime/coordinator/`、`tests/think/test_decision_repair_phase_plugin.py`、`tests/contracts/test_decision_needs_approval_typed.py` 全绿；`should_terminate=True` 的非 interrupt 节点行为不变(遍历中止语义只新增一种 terminal 原因，不改变 edge 选择)。

## 落地记录(e2e: run_ea969a410ae3 completed)

除 Proposal 三条外，e2e 还逼出三处同根修复：

1. **double-emit** — `RuntimeResultFinalizer` 与 `runtime_loop` 各调一次 `emit_approval_pause_from_result`，暂停事实写两遍，WS 出现 4 对相同 pause pair。留 finalizer(与 PAUSED outcome 同处)，删 runtime_loop 侧。
2. **WS 只认 checkpoint** — `approval.persisted.v1` 不再映射 WS(恢复 SSOT 仍读 journal)，pause pair 唯一来源 `session.checkpoint.v1`。
3. **`kernel.run.stop` 不再翻译成 completed** — task 结束≠run 结束；暂停 run 会谎报 completed，自然完成本就有 `SpineClose` + coordinator watchdog 兜底。
4. **恢复重入点** — 暂停 cursor 指向外层入口 `perceive.main`(declared inputs 为空)，带答案的 state 重开一 turn；mid-graph 重入所需 Command/原 decision 重建无人实现，不做。`runtime_loop` 另修一处 cursor 形状错配(declarative_1 喂给声明 adapter 形状的 `DeclarativeCheckpoint`)。
5. **恢复 ambient** — resume 新 task 无 execution environment，按 P3-06 先例把 `capability_bindings` / `tools_service` 热缓存在 `RunSession`，resume 时重发布。

## Alternatives considered

### Why not 在 yaml 删掉 interrupt→resume 无条件边？

该边是恢复重入的合法路径(人工 answer 后 `intervene.resume → act.resume`)；删边会同时关掉恢复。缺的是"暂停时停住"，不是边本身。

### Why not 让 interrupt 节点自己写 journal 暂停事实？

认知节点写世界违反 C2(认知不直接写世界)与 C7(控制/观察分离)；暂停事实的唯一生产入口是 Session 追加，由执行边界在停住时写。

## Related

- `lca/nodes/intervene/interrupt.py:107-139`、`lca/nodes/intervene/approve_gate.py:143-160`
- `lca/framework/graph/interpreter.py:195-383`(遍历循环)、`lca/loop/driver.py:123-232`(执行收口)
- `docs/specs/2026-09-07-lca-p1-agent-gateway-bridge.md` §4.2/§5.2(WS 双事件顺序)
