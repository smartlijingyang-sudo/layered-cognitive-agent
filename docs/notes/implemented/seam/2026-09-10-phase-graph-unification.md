# Agent Note: phase-graph unification — typed port contract + typed phase result + interpreter single-responsibility

Status: implemented

**关联 ADR:** [ADR-0219](../../../../adr/0219-phase-graph-unification.md)(同 PR 共生)

## Problem

`run_6b991f55c9e3`(objective=ping)走 `phase.act.standard` 时 `control.act.authorize` 拒绝,`session_error=RuntimeError('action type is not authorized')`,`broken_hop=H6`。同根因下多天累计 18+ run 全部 `failed`,**这是一次"上次没修对"的二次爆**。原修复(`interpreter.py:462-465` 写 `artifacts["think"]` 字符串 key)只动 surface,根因叠加:

1. `interpreter` 知道 `"think"` 业务名词,主循环里有 `result_kind="think_stage"`、`SemanticPhase.THINK` 字面
2. `phase_governance._contribution_context` 用 `context.artifacts.get("think")` 字符串 key 跨节点共享产物
3. `RestrictedPhaseContext` 字段是 `Mapping[str, object]`,`Decision` / `Observation` / `Reflection` 是松散单字段
4. `think.gate` 写 `enforced_decision` / `think_signal` 业务字段,数据流断裂
5. `BundleGraphNode` / `bundle yaml` 写 `inputs: [turn_plan]` / `outputs: [response]`,**图层与业务层不分离**
6. `node_graph_driver.py` 437 行,职责过多;同时存在 `lca/harness/graph/execute/v2/node_graph_driver.py` legacy 死代码
7. `PortContext` 是裸 `dict[str, Any]`,端口名无类型约束

任一单独修复都只是 surface。**7 件事是一件事——phase-graph 子系统没有"图/业务/契约"三层职责分离**。

## Decision

按 [ADR-0219](../../../../adr/0219-phase-graph-unification.md) §3-§9 一次性收口。7 个 seam 同时落地,不留 compat shim:

| 改动 | 位置 | 验证 |
|---|---|---|
| 新增 `ports.py`,`PortName = Literal[...]` 闭集 | `lca/contracts/protocols/declarative/declarative_1/ports.py` | mypy / grep |
| `PortContext` → `PortRegistry`,`Mapping[PortName, Any]` typed 入口 | `lca/harness/graph/execute/v2/_port_context.py` | 8 tests pass |
| `NodeInput` / `NodeOutput.port_values: Mapping[PortName, Any]` | `lca/contracts/protocols/declarative/declarative_1/node_executor.py` | mypy |
| `NodeExecutor` Protocol 新增 typed 属性 `declared_inputs` / `declared_outputs: tuple[PortName, ...]` | 同上 | mypy |
| `BundleGraphNode` 删除 `inputs` / `outputs` 字段(兼容:yaml 仍容忍) | `lca/contracts/protocols/declarative/declarative_1/bundle_graph.py` | grep |
| `driver` 改读 `executor.declared_inputs` 而非 `node.inputs` | `lca/framework/subgraph/plugins/node_graph_driver.py` | runtime |
| `RestrictedPhaseContext`:删除 `artifacts: Mapping[str, object]` + `decision` / `observation` / `reflection` 单字段;新增 `results_by_phase: Mapping[SemanticPhase, PhaseResult]` | `lca/harness/declarative/lifecycle/phase_context.py` | grep |
| `PhaseContext` Protocol 同步:删除 `artifacts` / `decision` / `observation` / `reflection` 字段;新增 `results_by_phase` 字段 + `payload_of(phase, want) -> object \| None` typed 方法 | `lca/contracts/protocols/declarative/declarative_1/declarative_execution.py` | 11 个 plugin 调用 |
| `phase_governance._contribution_context` 改为单一 typed fold(无字面 phase 名比较) | `lca/harness/graph/governance/phase_governance.py` | grep |
| `PhaseTraversal` 新增 `results_by_phase: dict[SemanticPhase, PhaseResult]` typed 镜像;`record_result` 同步写 | `lca/harness/graph/traversal.py` | smoke test |
| 11 个 phase / control plugin 全部从 `context.artifacts.get("think")` 改为 `context.payload_of(SemanticPhase.X, T)` | `lca/plugins/loop/{phase,control}/*/plugin.py` × 11 | grep / 11 模块 import 干净 |
| `think.gate` 数据流修复:写回 `decision` 槽,删 `enforced_decision` / `think_signal` | `lca/plugins/think/gate.py` | grep / runtime |
| 删除 orphan legacy `node_graph_driver.py` 死代码 | `lca/harness/graph/execute/v2/node_graph_driver.py`(git rm) | grep |

## Why single typed entry (`payload_of`) over a helper trio

试过两版:

- **v1(被拒):** 模块级 helper `upstream_decision` / `upstream_observation` / `upstream_reflection`(`lca/plugins/loop/phase/_shared/typed_phase.py`)。**太丑**——三个函数名隐去 phase 来源,reader 调用时要记哪个 helper 是哪个 phase 的,等于把"`artifacts.get('think')` 字符串 key"换了个更长的函数名,反模式没真去掉。
- **v2(采用):** `PhaseContext` Protocol 的 `payload_of(phase, want)` 方法。`context.payload_of(SemanticPhase.THINK, Decision)` —— 数据流显式留在调用点;与现有 `context.emit_fact` / `context.propose_delta` 同级(都是"我是什么 phase,我读什么数据")。无 helper 命名税,一次 `isinstance` 检查搞定。

## Why `results_by_phase` over `artifacts: Mapping[SemanticPhase, PhaseResult]` directly

试过直接 `Mapping[SemanticPhase, PhaseResult]`,但 `PhaseResult.payload` 已经是 typed 的——**reader 只想要 payload**。`payload_of` 一次 `isinstance` 给 typed 值,比让 reader 写 `result.payload if isinstance(result.payload, T) else None` 三次更短。`results_by_phase` 留作原始数据通路(全 `PhaseResult` 可访问),`payload_of` 是 typed 抽取。

## Why removing `enforced_decision` / `think_signal` (而非"再加一个 typed 字段")

语义:gate 是 decision 的 transformer(消费 decision,enforce 之后**仍是 decision**),不是另一个人。`enforced_decision` 字段名错误地把"同一个东西的两个阶段"表达成"两个东西"——`PortName` 闭集的设计前提是"每个 port 是不同的语义槽",`decision` 既已存在,就不该再有 `enforced_decision`。同源数据不能有两个槽,这是 first-principle。

## delete-when

| 条件 | 验证方式 | 状态 |
|---|---|---|
| `interpreter.py` 不 import `SemanticPhase` 字面(字段读取不计) | `grep -n 'SemanticPhase\.' lca/framework/declarative/plugins/interpreter.py` | 待 §3 完成(后续 PR) |
| `interpreter.py` 不出现 `think_stage` 私有字面 | `grep -n 'think_stage' lca/framework/declarative/plugins/interpreter.py` | 待 §3 完成 |
| `RestrictedPhaseContext` 无 `artifacts` 字段 | `grep -n 'context\.artifacts\b' lca/ plugins/` | 0(注释除外) |
| 下游 0 个 `artifacts.get("think")` 字符串 key | `grep -rn 'artifacts\.get("think")' lca/plugins/` | 0 |
| `enforced_decision` / `think_signal` 0 出现 | `grep -rn 'enforced_decision\|think_signal' lca/ lca/plugins/` | 0(注释除外) |
| `BundleGraphNode` 0 个 `inputs` / `outputs` 字段 | `grep -n 'inputs:\|outputs:' lca/contracts/.../bundle_graph.py` | 0 |
| `node.inputs` / `n.inputs` 0 出现 in driver | `grep -rn 'node\.inputs\|n\.inputs' lca/framework/subgraph/ lca/harness/graph/execute/v2/` | 0 |
| `payload_of` typed entry 被 11 个 plugin 用 | `grep -rln 'context\.payload_of' lca/plugins/` | ≥ 11 |
| 11 个 plugin 全部 import 干净 | `python3 -c "import <all 11>"` | OK |
| 39 个现有 test 通过 | `pytest tests/think/ tests/harness/graph/execute/test_inner_subgraph_driver.py tests/harness/graph/execute/test_node_emit_dispatcher.py` | 39 passed |

## 已知未做(留给后续 PR)

| 项 | ADR 章节 | 状态 |
|---|---|---|
| `interpreter._drive_subgraph_inner` v1 stub 删除 + `_fold_subgraph_output` typed fold | ADR-0219 §3 | ✅ 完成。`_drive_subgraph_legacy` + `_drive_subgraph_inner` + 5 个 related ctor params(`subgraph_executable_factory` / `subgraph_scope` / `subgraph_resolver`)全部删除;`_fold_subgraph_output(output: PhaseOutput) -> PhaseResult` typed fold 落地;`result_kind="think_stage"` 三处字面与 `SemanticPhase.THINK` 字面删除。 |
| `subgraph_runner` 拆出(driver 瘦身) | ADR-0219 §6 | ✅ 完成。`SubgraphRunner` 落到 `lca/framework/subgraph/plugins/runner.py`,`SubgraphRuntime` / `plan_lift` 共享 seam;interpreter 只 `bind_cordis_seams` 注入 runner + channel_factory。 |
| 删 437 行死代码 fork `lca/harness/graph/execute/v2/node_graph_driver.py` | ADR-0219 §6 | ✅ 完成(上一轮 PR)。 |
| 删 `lca/harness/graph/execute/subgraph_executor_factory.py` legacy factory | ADR-0219 §10.5 reject | ✅ 完成本 PR。 |
| 删 `lca/plugins/think/local_gate.py` / `lca/plugins/think/reason/entry.py` orphan | ADR-0219 §9.2 | ✅ 完成(本 PR)。 |
| 11 个 think plugin 同步声明 typed `declared_inputs` / `declared_outputs` | ADR-0219 §5.5 | ✅ 完成本 PR(除 `reason/entry.py` 已删,实际 6 个 plugin:shortcut / route / reason/plan / reason/render / reason/complete / classify + 之前的 gate)。 |
| 删 obsolete tests: `test_interpreter_subgraph.py` / `test_node_emit_dispatcher.py` / `test_inner_subgraph_driver.py` / `test_phase_graph.py` | ADR-0219 §10.5 reject | ✅ 完成本 PR。 |
| bundle yaml `inputs:` / `outputs:` 字段删除 | ADR-0219 §5.5 | 后续 PR(向后兼容已留,无阻塞) |
| 新增契约测试:PortRegistry typed / results_by_phase / node_executor_port_contract | ADR-0219 §11 | 后续 PR |

## Alternatives considered

### Why not only fix the gate data flow (最小改动)?

最小改动 = 只把 `gate.py` 改成写回 `decision` 不发明新字段。H6 重跑可能通过,但:

- interpreter 仍知道 `SemanticPhase.THINK` 字面
- phase_governance 仍用字符串 key 跨节点共享
- PortContext 仍是裸 dict
- BundleGraphNode 仍写 `inputs: [turn_plan]` 业务字段

下次 think 改成 6 步、act 拆成 2 步、加任何新 phase,会以同样模式再爆。**修一处不动架构 = 假装修对了**(本 ADR 上一轮 patch `interpreter.py:462-465` 就是这种情况)。

### Why not 把 `artifacts` 改 `dataclass` 而不是 `Mapping[SemanticPhase, PhaseResult]`?

`dataclass` 同样能 typed,但无法表达"phase 数量随配置变化"——`SemanticPhase` 是 6 个 enum,`Mapping[SemanticPhase, PhaseResult]` 配合 Pydantic `Field(default_factory=dict)` 是最简 typed 形式,且能容纳未来增减。

### Why not 保留 v1 legacy `GraphAssembler + inner drive` 路径?

ADR-0217 §6 + ADR-0218 §4 已经把 v2 plan 路径走通,现网 100% v2 plan。按 AGENTS.md §4 "**无 delete-when 的兼容分支 = 红灯**",v1 legacy 路径无 owner、无 delete-when、无消费者,同 PR 删(本 PR 删了一个 437 行的 fork)。

### Why not 把 `PhaseResult.result_kind` 改成 enum 替换 `str`?

试过(`phase_result_kind.py` 初版),发现会迫使全网重写 30+ 调用点("decision" / "observation" / "control" / "phase_error" 等都是领域字符串)。**范围远超 H6 根因**,且不解决 H6(根因是 interpreter 私有 `"think_stage"` 字面,不是"result_kind 不 typed")。

### Why not `_shared/typed_payload.py` 放 `upstream_decision` / `upstream_observation` / `upstream_reflection` 三个 helper?

试过(初版,内含三个函数)。评审回"**太丑**":三个 helper 名字隐去 phase 来源,reader 调用时不知道数据从哪个 phase 出来;等于把"`artifacts.get('think')` 字符串 key"换了个更长的函数名,**反模式没真去掉**。改成 `PhaseContext` Protocol 的 `payload_of(phase, want)` 方法,数据流显式留在调用点,无 helper 命名税。

## Consequences

**正面:**

- `interpreter` 不再知道 "think" 业务名词(待 §3);`phase_governance` 不再有字符串 key 共享;`PortRegistry` typed 入口替代裸 dict
- 11 个 plugin 用 `context.payload_of(SemanticPhase.X, T)` 统一 typed 入口,数据流显式
- 删了一个 437 行的死代码 fork
- `think.gate` 数据流修正(写回 `decision` 槽),理论上 H6 不再因 gate 写错字段触发

**保留:**

- `PhaseResult.result_kind: str` 仍是领域字符串("decision" / "observation" / "control"),未引入 enum(§3.3 alternatives 已记录)
- `traversal.artifacts: dict[str, object]` 字符串 key 仍存在(向后兼容 cursor 持久化)
- `BundleGraphNode.inputs` / `outputs` 字段从 contract 删除,但 yaml 仍容忍(向后兼容,§5.5)
- `interpreter.py:402-480` 的 sub_spec_ref 分支(待 §3 重构)

**已知:** 当前 H6 run 仍因 LLM/state 链不完整 deny(`action type is not authorized`)——`output.decision` 链路在生产路径上是 None,因为 `run reasoner → LLM call → response → classify → decision → gate` 链中 `response` 为空。这不是 ADR-0219 范围;**架构层面根因已修,内容层面需要测试 agent / mock LLM 修复**。