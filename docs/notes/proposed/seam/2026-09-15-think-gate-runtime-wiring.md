# Agent Note: think.gate runtime wiring 未接通

Status: proposed

## Problem

`MultiToolLoopBreakerGate` 文档自陈为 multi-tool loop 的 "primary line of defense"(ADR-0214 PR-B),在单元测试里 trigger 3 拦重复 tool 行为正确(`tests/cognition/test_multi_tool_loop_breaker.py` 16 个 case 全过)。生产路径 `run_255698cfe712` (2026-09-15) 与后续 4 次同 pattern run 仍然发生"LLM 第二次调同 tool"。

binary-search 后排除 trigger 3 判定逻辑(`consecutive_repeat_max` 与 `task_progress_projection`)、ChainedDecisionGate 装配(setup 阶段 composed 7 gates 成功)、plugin 注册三层。**真实断点是 phase graph 节点 `phase.concept.decision_enforce.gate_chain_run` 在生产路径上拿不到 gate chain**。

运行时直接证据(2026-09-15 现场日志):

```
gate.chain.run: gates=0 state=None decision_id=dec_0bf5e5beb4fb
```

链路:

1. `framework/graph/strategies/node_executor_strategy.py:70` 从 `context.node_config["agent_state"]` 拿 AgentState,但 `_build_runtime(agent_state)`(line 119-121)在 `node_runtime_view_factory is None` 时返回空 `{}`。
2. `framework/graph/port_registry.py:99-104` `build_input` 在 port 缺失时返回 `None` 不报错;`gate.chain.run` yaml declare `inputs: [decision, state]`,framework 不填 `state`。
3. `plugins/concept/decision_enforce/chain_run.py:90-106` `_resolve_gates(context)` 读 `context.runtime.decision_gates`,`getattr` 返回 None → `return ()`;`_run_chain`(line 107-125)在 `not gates or state is None` 时直接 `return decision`,Gate chain 形同虚设。
4. 对照: `plugins/loop/control/think_guard/plugin.py:80-91` 走的是 `runtime.get("gates")` + `runtime.get("agent_state")`,key 不一样,逻辑也不一样。两条路径并存,只有 think_guard.enforce 走的是 framework 默认 runtime;gate_chain_run 走的是另一条更窄的 contract,没接 framework 的默认 wire。

**对称失败**:`run_255698cfe712` 同时存在 "model_visible.messages 缺 assistant turn" 现象(projcache `nodes=[8, 144, 252]` 无 assistant seq),但 `assistant.responded.v1` lifecycle emit hook 在 `capture_post_llm` 路径上是有的;具体失效点待另 Note 跟踪。

## Proposal

让 `gate.chain.run` 节点从 `context.runtime` 拿 gates 与 agent_state,yaml contract 与 `think_guard.enforce` 对齐。

### 改动

1. `framework/graph/strategies/node_executor_strategy.py:_build_runtime`:默认情况下把 `agent_state` 直接放到 runtime dict(`{"g = {"agent_state": agent_state}}`),至少让 runtime.get("agent_state") 可读。
2. `plugins/concept/decision_enforce/chain_run.py:_resolve_gates`:从 `context.runtime` 读 `gates`(单一来源),与 `think_guard.enforce` 对齐。
3. `plugins/concept/decision_enforce/chain_run.py:node_execute`:state 缺失时 fallback 到 `context.runtime["agent_state"]`,port 缺失不再报错。
4. `bundles/concept/decision_enforce.yaml`: `gate.chain.run` 的 `inputs` 由 `[decision, state]` 改为 `[decision]`,yaml 与运行时一致。
5. `framework/graph/strategies/node_executor_strategy.py` 顺手把 `node_runtime_view_factory` 默认值改成内置一个最小 view(只暴露 `agent_state` + `gates`),把 framework 默认契约钉死,不依赖外部 factory 注入。

### 验收(可观察状态)

- 重跑 `run_255698cfe712` 同 prompt,spine 出现 `MultiToolLoopBreakerGate` enforcement 事件;`tool_call.record` 计数从 2 降为 1。
- `tests/cognition/test_multi_tool_loop_breaker_consecutive.py` 5 个新 case 持续通过(已通过,作为回归 fixture)。
- 既有 35 个 loop 测试 + `tests/integration/test_loop_cursor_wiring.py` 全过。
- `lca-ops runs create --user-text "echo X" --wait` 不再因 max_visits=2 触发 budget_exceeded。

### 风险

- **framework 默认 runtime 改动** 跨 L0/L1 seam(`framework/graph/strategies/*` 是 L0;`plugins/concept/decision_enforce/*` 是 L2)。所有 `NodeExecutor` 节点实现都受影响,需扫一遍 `context.runtime` 读点。
- **runtime dict vs factory 注入**:framework 当前设计是 `node_runtime_view_factory` 由 caller 注入,默认空是显式选择。改成默认 dict 是改 framework 默认行为,需要 ADR 决议。

## Alternatives considered

### 不修 wiring,只挪 trigger 3

- 现实问题:`gate.chain.run` 形同虚设意味着 `MultiToolLoopBreakerGate` 在生产路径上 0% 命中。挪 trigger 3 顺序只解决单元测试,生产无效。
- 拒绝理由:不解决 wiring = "primary line of defense" 自陈是谎言,留在 ADR-0214 里腐化未来 PR-F 工作。

### 把 gate_chain_run 替换成 think_guard.enforce

- 现实问题:`think_guard.enforce` 走的是同一 framework runtime,但 `gate.chain.run` 多了 emit `enforced_decision` + `decision` 双输出,yaml edge 拓扑不同。
- 拒绝理由:合并两条概念图会破坏 `gate.chain.reject` 这个 reject provenance 节点的存在意义;更深的重写超出 bug-fix 范围。

### 在 framework 层加一个 `RuntimeContextBuilder`,集中装配 runtime + outer ports

- 现实问题:更结构化,但跨 framework + 所有 plugin,变更面比 #5 提议大 5 倍。
- 拒绝理由:不解决当前 bug 的最小变更原则;留作后续 refactor,不开本 PR。

## 不在范围

- `model_visible.messages` 缺 assistant turn 这条独立根因(详见前轮诊断,有独立 Note 待起)。
- ADR-0214 PR-F wiring "complete" 列表里的其他 28+ Decision emit 方 task_progress 显式传值。
- Gate 数量 / 类型 / 阈值的语义变化(本次修复只补连通性,不改业务行为)。