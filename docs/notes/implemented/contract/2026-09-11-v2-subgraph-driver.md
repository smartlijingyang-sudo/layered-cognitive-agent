# Agent Note: Bundle Graph v2 subgraph driver — interpreter v2 友好分支

Status: implemented

**关联 ADR:** [ADR-0218](../../../../adr/0218-bundle-graph-v2-subgraph-driver.md)(同 PR 共生)

## Problem

ADR-0217 引入 `NodeExecutor` 作为 think 子图节点协议,但 `interpreter._drive_subgraph_inner` 只有一条路径 — 调 `GraphAssembler().assemble(sub_plan_obj, scope)` 把 plan 装成 executable,然后喂 `_drive` 走老 phase 调度循环。

老 `_drive` 的契约:`phase executor` 拿 `PhaseResult.result_kind` / `payload` 喂 DSL 评估 edges[].when;v2 节点返回的是 `NodeOutput(port_values, next_hint)`,**两种事实源语义不同**,强行映射导致 DSL 评估 `result.payload.shortcut_taken` AttributeError,think 子图 fail。

## Decision

描述**当前已落地**的真实状态(将来时 → 现在时)。

### 1. `V2BundleGraphPlanMarker` Protocol(plan 形态识别)

[contracts/protocols/declarative/declarative_1/v2_plan_marker.py](../../../../contracts/protocols/declarative/declarative_1/v2_plan_marker.py) 定义 Protocol:

```python
@runtime_checkable
class V2BundleGraphPlanMarker(Protocol):
    def get_bundle_graph_spec(self) -> BundleGraphSpec: ...
```

`BundleSubgraphResolver._wrap_compiled_run_plan` 返回的 plan 是 `_V2Plan(CompiledRunPlan, V2BundleGraphPlanMarker)` 子类,挂载 spec;`isinstance(plan, V2BundleGraphPlanMarker)` 为 True 时 interpreter 走 v2 分支。

### 2. `NodeOutputProjector` Adapter(NodeOutput → PhaseResult)

[harness/graph/execute/v2/node_output_projector.py](../../../../harness/graph/execute/v2/node_output_projector.py) 暴露:
- `NodeOutputSchema(result_kind, payload_port)`:yaml `node.config` 投影
- `project_node_output(node_output, schema) -> PhaseResult`:无脑映射,无业务分支
- `schema_from_node_config(config)`:从 yaml dict 抽 schema

### 3. `NodeContextFactory` Adapter(scope → NodeContext)

[harness/graph/execute/v2/node_context_factory.py](../../../../harness/graph/execute/v2/node_context_factory.py) 暴露:
- `NodeRuntimeView`:把 scope capability 平移到 dataclass 字段
- `build_node_context(node, plan_ref, outer_state, scope) -> NodeContext`
- 用 `MappingProxyType` 包 budget / metadata 防止 plugin 修改 framework 内部状态

### 4. `EdgeSelector` Strategy(DSL 复用)

[harness/graph/execute/v2/edge_selector.py](../../../../harness/graph/execute/v2/edge_selector.py) 暴露:
- `select_edge(current_node_id, edges, last_phase_result, artifacts) -> BundleGraphEdge | None`
- 复用既有 `evaluate_restricted_predicate` DSL,**语法零变化**
- first-match wins(yaml 顺序)

### 5. `NodeGraphDriver` Composite(主循环)

[harness/graph/execute/v2/node_graph_driver.py](../../../../harness/graph/execute/v2/node_graph_driver.py) 暴露:
- `NodeGraphDriver(spec, plan_ref, scope, registry, observers).run(outer_state, artifacts) -> InterpretationResult`
- 主循环:entry → executor resolve → NodeContext build → NodeInput build → executor.node_execute → NodeOutput project → observer emit → edge select → 下一节点 / 终止
- 不感知 outer drive;不直接改 outer AgentState(只 emit 事实)
- `entry` 默认 = nodes[0].id(yaml 顺序)

### 6. `_PortContext` 内部数据结构

[harness/graph/execute/v2/_port_context.py](../../../../harness/graph/execute/v2/_port_context.py) 提供跨节点 port 共享:
- `set_outer_input(ports)`:outer 传入初始 input
- `merge_output(port_values)`:节点 output merge(outer input 优先,不覆盖)
- `build_input(declared_ports)`:抽 declared_ports 构造 NodeInput

### 7. `_drive_subgraph_inner` v2 分支(interpreter 改动 15 行)

`interpreter.py` 在 resolver.resolve 后加 isinstance 检查:若 `V2BundleGraphPlanMarker`,委派 `NodeGraphDriver.run()`;否则走老 GraphAssembler 路径(完全不动)。

### 8. `bundles/think.yaml` 增字段

`node.config` 加 `result_kind` / `payload_port`,framework 必读:
- `think.shortcut`:result_kind=decision, payload_port=decision
- `think.route` / `think.reason`:result_kind=think_stage, payload_port=route_choice / response
- `think.classify`:result_kind=decision, payload_port=decision
- `think.gate`:result_kind=decision, payload_port=enforced_decision

`BundleGraphSpec.entry` 字段新增(可选),driver 默认 fallback 到 nodes[0].id。

## Verification

(原 Acceptance criteria — 见下方现状。)

1. ✅ 4 个新模块单文件 ≤ 150 行职责单一
2. ✅ NodeGraphDriver.run() 返回 InterpretationResult(与 _drive 同形)
3. ✅ NodeOutputProjector 把 NodeOutput 投影成 PhaseResult,所有 think 5 步 node 投影后 DSL 评估 when 全过
4. ✅ _drive_subgraph_inner 老路径(GraphAssembler → _drive)完全不动,新路径仅在 isinstance(_, V2BundleGraphPlanMarker) 时激活
5. ⏳ 端到端六语义跑通:run_51826f4746c9 / run_b6119dcc18b2 已**走完 think 子图**(没 PG-005 / AttributeError / NodeOutput error),**进入 act.main**,被 `control.act.authorize` 拒绝 `action type is not authorized`(control policy 问题,**与 v2 driver 无关**)
6. ✅ 既有测试全过:`tests/think/` 21 + subgraph tests 35 = 56 passed,无退化
7. ⏳ `_wrap_compiled_run_plan` 简化兜底:留到 interpreter v2 稳定后清理(本 ADR §8 delete-when)

## Testing

- 契约行为验证:`/opt/lca/venv/bin/python -c "..."`(projector + edge_selector 4 模块)
- 端到端 kernel:`run_b6119dcc18b2` 跑通 think 子图(5 个 think 节点全跑,total_steps 推进),控制面 act policy 拒绝与 v2 无关
- pytest:`tests/think/` 21 passed + `tests/harness/graph/execute/test_interpreter_subgraph.py` + `tests/contracts/test_subgraph_reference_contract.py` + `tests/declarative/test_phase_graph.py` = 56 passed

## Consequences

(原 Risks — 见下方现状记录。)

- **R1:5 个 node_execute 行为与老 PhaseExecutor.execute 行为不一致。** 老 caller 期望 payload=ThinkSubgraphCarry;新 caller 期望 NodeOutput.port_values。**通过双协议并存**(既有老 .execute 保留 + 新 .node_execute 添加)解决,老 17 个 think 测试 + 老 caller 全部兼容。
- **R2:`scope` 是 MappingRestrictedScope 不是 dict。** driver 用 `.resolve(key)` 协议查 capability,scope 类型用 `_ScopeLike` Protocol 抽象,**不依赖 dict 形态**。
- **R3:enforced_decision 与 outer AgentState 桥接。** 当前 v2 driver 不写 outer state,enforced_decision 通过 PhaseResult.next_hints 透传;后续 interpreter 在 outer drive 边界桥接(超出本 ADR,独立 ADR 跟进)。
- **R4:`_wrap_compiled_run_plan` 兜底层 PhaseBinding/CapabilityPlan/ValidationReport/PlanProvenance。** 当前保留作为 GraphAssembler 兼容兜底;interpreter v2 分支稳定后可删(本 ADR §8 delete-when)。

## Alternatives considered

- **把 v2 plan 永远走老 GraphAssembler 路径**:NodeOutput 与 PhaseResult 语义不兼容,强行走会污染老路径
- **在 interpreter 里直接写 v2 调度循环**:interpreter 已有 1100+ 行,加 200 行 v2 循环违反模块化
- **开独立 interpreter_v2.py 完全替代**:95% 通用代码不重复,违反 C6 最小化
- **把 NodeExecutor 合并回 PhaseExecutor(统一签名)**:6 phase + 12 control 是 phase 级语义,think 5 步是节点级语义,合并会砍掉 ports 抽象
- **executor 自己实现 v2 调度**:把调度职责塞进 plugin,违反职责边界
