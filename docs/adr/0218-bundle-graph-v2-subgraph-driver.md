# ADR-0218: Bundle Graph v2 subgraph driver — interpreter v2 友好分支

> **状态:** **Accepted — 2026-09-10**(实施见本 PR)
>
> **一句话**: 在 `GenericPlanInterpreter._drive_subgraph_inner` 加 v2 plan 识别分支,把 `NodeExecutor` 调起、`NodeOutput → PhaseResult` 投影、edge DSL 路由、跨节点 port 上下文合并,统一封装到独立模块 `lca.harness.graph.execute.v2.NodeGraphDriver`;老 declarative 路径(`GraphAssembler().assemble()` → `_drive`)完全不动。闭环 ADR-0217 留下的"端到端六语义跑通"卡点。
>
> **触发**:ADR-0217 实施后,`run_7559c96beacd` 已能走进 think.shortcut(fold_hits=2, total_steps=2),但 `interpreter._drive_subgraph_inner` 把 v2 plan 当老 declarative plan 喂给 `GraphAssembler`,NodeOutput 与 PhaseResult 不同形导致 DSL 评估 `result.payload.shortcut_taken` AttributeError。
>
> **Agent Note**(实施时): `docs/notes/implemented/contract/2026-09-11-v2-subgraph-driver.md`
>
> **Review:** 待评审。
>
> **Accepted 闸门**:
> 1. §3 模块分层单文件 ≤ 150 行,职责单一,4 个模块 + 1 个 Driver
> 2. §4 `NodeGraphDriver.run()` 返回 `InterpretationResult`,与 `_drive` 同形
> 3. §5 `NodeOutputProjector` 把 `NodeOutput` 投影成 `PhaseResult`,所有 think 5 步 node 投影后 DSL 评估 `when` 全过
> 4. §6 `_drive_subgraph_inner` 老路径(`GraphAssembler().assemble()` → `_drive`)完全不动,新路径仅在 `isinstance(sub_plan, V2BundleGraphPlanMarker)` 时激活
> 5. §7 端到端:`run_f01e7e932a0b` 同语义新 run 跑通六语义 `perceive → think → act → reflect → remember → stop`,broken_hop=None
> 6. §8 既有测试全过:`tests/think/` 21 + `tests/harness/graph/execute/test_interpreter_subgraph.py` + `tests/contracts/test_subgraph_reference_contract.py` + `tests/declarative/test_phase_graph.py` 共 56 不退化
> 7. §9 清理 `_wrap_compiled_run_plan` 临时兜底(PhaseBinding/CapabilityPlan/ValidationReport/PlanProvenance),v2 plan 走纯 v2 路径,不再伪装成老 plan

**编号:** 0218

**关系:**
- **Builds on**: ADR-0217(BundleGraphSpec + NodeExecutor + FactoryRegistry)· ADR-0075(declarative phase graph 根)· ADR-0199(cognitive plugin convergence)· ADR-0210(P7 region-tag)
- **Refines**: `GenericPlanInterpreter._drive_subgraph_inner`(`isinstance` v2 marker 识别 + 委派 NodeGraphDriver)
- **Supersedes**: 无
- **Reject**: 「把 v2 plan 永远走老 GraphAssembler 路径」(违反职责清晰:NodeExecutor 是节点级,与 PhaseExecutor 是 phase 级,共享调度循环会污染边界);「在 interpreter 里直接写 v2 调度循环」(违反模块化,interpreter 已有 1100+ 行);「开独立 interpreter_v2.py 完全替代」(违反 C6 最小化,老 declarative 路径 95% 通用)

---

## 0. 第一性原理: 问题本质

ADR-0217 引入 `NodeExecutor` 作为 think 子图节点协议,但 `interpreter._drive_subgraph_inner` 只有一条路径 — 调 `GraphAssembler().assemble(sub_plan_obj, scope)` 把 plan 装成 executable,然后喂 `_drive` 走老 phase 调度循环。

**老 `_drive` 循环的契约**(从 `interpreter.py:347` 一带):
```
phase node → 调用 phase executor → 拿到 PhaseResult →
  result_kind / payload 喂 DSL 评估 edges[].when →
  选下一节点 → PhaseTraversal 推进
```

**v2 节点的现实**:
- executor 接口是 `NodeExecutor.node_execute(ctx, inp) -> NodeOutput`(端口数据流,不是 phase result)
- 没有 `result_kind` / `payload` 字段(`NodeOutput` 只有 `port_values` + `next_hint`)
- 没有 PhaseTraversal 的 cursor / visit budget 概念(节点级循环由 yaml `max_visits` 配置)

**问题本质**:NodeOutput 是新事实源,PhaseResult 是老事实源,两者语义不同。强行把 NodeOutput 当 PhaseResult 用 = 违反 C13 信息血统闭合 — 没有 typed Contract 桥接两层。

**正确路径**:**Adapter 模式** — 在 v2 调度循环里把 NodeOutput 投影成 PhaseResult,让老 DSL 评估 / `_drive` 路径**完全不知道 NodeOutput 存在**。

---

## 1. 设计原则

| 原则 | 在 v2 分支里怎么落 |
|---|---|
| 职责单一 | 4 个独立模块(Adapter ×2, Strategy, Composite),每个 ≤ 150 行 |
| 模块化 | v2 模块放独立子包 `lca.harness.graph.execute.v2`,与 interpreter 解耦 |
| 边界清晰 | interpreter 只识别 plan 形态 + 委派;v2 Driver 不感知 outer drive;老 declarative 路径完全不动 |
| 优雅 | 4 个设计模式对应 4 个职责边界(Adapter / Strategy / Composite / Template) |
| 第一性原理 | NodeOutput → PhaseResult 是新事实源到老事实源的桥,显式 Contract,不隐式映射 |

---

## 2. 架构: 5 个模块

```
lca/harness/graph/execute/v2/                  ← 新建独立子包
├── __init__.py
├── node_graph_driver.py        (Composite: 跑 5 节点顺序循环) ← ~150 行
├── node_output_projector.py    (Adapter: NodeOutput → PhaseResult) ← ~80 行
├── node_context_factory.py     (Adapter: scope + plan → NodeContext) ← ~100 行
├── edge_selector.py            (Strategy: 复用 DSL 评估 edges[].when) ← ~80 行
└── _port_context.py            (内部数据结构: 跨节点 port 合并) ← ~60 行

lca/contracts/protocols/declarative/declarative_1/v2_plan_marker.py  (新增 ~30 行)
   V2BundleGraphPlanMarker Protocol: 标记 plan 是 v2 形态

interpreter.py 修改:
   _drive_subgraph_inner: 仅在 isinstance(sub_plan, V2BundleGraphPlanMarker) 时
     委派 NodeGraphDriver,其它情况走原 GraphAssembler().assemble() 路径
```

---

## 3. 模块分层与设计模式

### 3.1 `V2BundleGraphPlanMarker`(Protocol — 识别)

```python
@runtime_checkable
class V2BundleGraphPlanMarker(Protocol):
    """v2 plan 标记。

    BundleSubgraphResolver 在 v2 路径返回 CompiledRunPlan 时同时实现本 Protocol;
    interpreter 用 isinstance(_ , V2BundleGraphPlanMarker) 识别 v2 分支。
    """
    def get_bundle_graph_spec(self) -> BundleGraphSpec: ...
```

**职责**:plan 形态识别,**仅此而已**。不存数据,不做事。
**D5 消费点**:`interpreter._drive_subgraph_inner` 的 isinstance 检查。
**为什么用 Protocol 不用字段**:`CompiledRunPlan` 是 frozen dataclass,加 Protocol 不侵入字段;provenance 字符串是观察面,不应承担控制面路由。

### 3.2 `NodeOutputProjector`(Adapter — 事实源桥接)

```python
@dataclass(frozen=True, slots=True)
class NodeOutputSchema:
    """yaml `node.config.result_kind` / `payload_port` 投影。
    
    D5 消费点:
      - result_kind:PhaseResult.result_kind(DSL 评估能区分 stage/decision/failed)
      - payload_port:NodeOutput.port_values 中哪个 key 映射到 PhaseResult.payload
    """
    result_kind: str = "think_stage"
    payload_port: str | None = None

class NodeOutputProjector:
    """NodeOutput → PhaseResult 投影。"""
    def project(self, node_output: NodeOutput, schema: NodeOutputSchema) -> PhaseResult:
        payload = node_output.port_values.get(schema.payload_port) if schema.payload_port else None
        return PhaseResult(
            result_kind=schema.result_kind,
            payload=payload,
            next_hints={"next_hint": node_output.next_hint} if node_output.next_hint else {},
        )
```

**职责**:无脑映射。无业务逻辑,无 if 分支(除 None 兜底)。
**D5 消费点**:`NodeGraphDriver.run()` 每个节点跑完调一次。

### 3.3 `NodeContextFactory`(Adapter — framework ↔ plugin 适配)

```python
@dataclass(frozen=True, slots=True)
class NodeRuntime:
    """NodeContext.runtime 投影。
    
    把 cordis scope 的 capability 集合(LLM / memory / state / reducer / etc.)
    平移进 dict,key=业务语义名(如 'reasoner', 'state', 'decision_gate')。
    """
    state: Any                          # AgentState 投影(只读)
    reasoner: Reasoner | None = None
    decision_gate: DecisionGate | None = None
    decision_classifier: DecisionClassifier | None = None
    skill_router: SkillRouter | None = None
    supports_shortcut: SupportsShortcut | None = None
    agent_gates: DecisionGate | None = None
    reducer: Any | None = None

class NodeContextFactory:
    """从 cordis scope + yaml node 投影出 NodeContext。"""
    def build(
        self,
        *,
        node: BundleGraphNode,
        plan_ref: str,
        outer_state: AgentState,
        scope: Mapping[str, Any],
    ) -> NodeContext:
        runtime = NodeRuntime(state=outer_state, **scope)
        budget = MappingProxyType(dict(node.config))  # frozen view
        metadata = MappingProxyType({
            "purpose": node.purpose,
            "plan_ref": plan_ref,
            "node_id": node.id,
        })
        return NodeContext(runtime=runtime, budget=budget, metadata=metadata)
```

**职责**:framework 边界,**单点**把 cordis capability 投影给 plugin。
**D5 消费点**:`NodeGraphDriver.run()` 每个节点跑前调一次。
**关键**:用 `MappingProxyType` 包 dict,plugin 只能读,不能改(防止 framework 内部状态被 plugin 污染 — 修 5-Why #5 提的问题)。

### 3.4 `EdgeSelector`(Strategy — DSL 复用)

```python
class EdgeSelector:
    """从节点出发选下一节点的边。

    复用既有 `evaluate_restricted_predicate` DSL,不变语法;只换输入。
    """
    def select(
        self,
        *,
        current_node_id: str,
        edges: tuple[BundleGraphEdge, ...],
        last_phase_result: PhaseResult,
        artifacts: Mapping[str, object],
    ) -> BundleGraphEdge | None:
        for edge in edges:
            if edge.source != current_node_id:
                continue
            if evaluate_restricted_predicate(
                edge.when, result=last_phase_result, artifacts=artifacts
            ):
                return edge
        return None  # 终止
```

**职责**:边选择,**仅此而已**。不调 executor,不 emit 事件。
**D5 消费点**:`NodeGraphDriver.run()` 主循环每轮调一次。
**关键**:DSL 不动 — projector 解决了所有语义桥接。

### 3.5 `NodeGraphDriver`(Composite — 调度主循环)

```python
class NodeGraphDriver:
    """v2 plan 调度循环。

    流程:NodeGraphSpec → 主循环:
      1. 拿当前 node
      2. executor = FactoryRegistry.resolve(node.factory, region)
      3. ctx = NodeContextFactory.build(node, plan_ref, state, scope)
      4. inp = NodeInput(port_context.get_input(node.id))
      5. out = await executor.node_execute(ctx, inp)
      6. phase_result = NodeOutputProjector.project(out, node.config)
      7. emit phase_graph.node.start / node.end (C11 复用)
      8. facts.extend(phase_result.facts)  # 不调 reducer,只 emit
      9. edge = EdgeSelector.select(node.id, plan.edges, phase_result, artifacts)
      10. if edge is None: terminate
      11. current_node = edge.target
      12. port_context.merge(node.id, out.port_values)
    """
    def __init__(
        self,
        *,
        spec: BundleGraphSpec,
        plan_ref: str,
        scope: Mapping[str, Any],
        registry: FactoryRegistry,
        observers: tuple[Callable[[str, dict], Awaitable[None]], ...] = (),
    ) -> None: ...

    async def run(
        self,
        *,
        outer_state: AgentState,
        artifacts: Mapping[str, object],
        budget: Budget | None = None,
    ) -> InterpretationResult: ...
```

**职责**:Composite — 5 节点顺序循环,**不感知 outer drive**。
**输入**:`BundleGraphSpec` + outer state + scope(注入 dependency,**不直接读 cordis**)
**输出**:`InterpretationResult`(与 `_drive` 同形,outer drive 无感)
**D5 消费点**:`interpreter._drive_subgraph_inner` v2 分支。
**关键**:`scope` 注入让 driver 不感知 cordis,可独立单元测试。

---

## 4. `interpreter._drive_subgraph_inner` 改动(最小化)

```python
# interpreter.py:826 附近,新增约 15 行
async def _drive_subgraph_inner(self, *, ref, outer_state, current_node_id, depth, edge_id):
    resolver = self._subgraph_resolver
    if resolver is None:
        raise DeclarativeValidationError(...)
    sub_plan_obj = resolver.resolve(ref.plan_ref)
    if not isinstance(sub_plan_obj, CompiledRunPlan):
        raise DeclarativeValidationError(...)

    # v2 分支:Bundle Graph Schema v2 plan(ADR-0218)
    if isinstance(sub_plan_obj, V2BundleGraphPlanMarker):
        from lca.harness.graph.execute.v2.node_graph_driver import NodeGraphDriver
        spec = sub_plan_obj.get_bundle_graph_spec()
        driver = NodeGraphDriver(
            spec=spec,
            plan_ref=ref.plan_ref,
            scope=self._subgraph_scope or {},
            registry=get_default_registry(),
        )
        sub_result = await driver.run(
            outer_state=outer_state,
            artifacts=self._active_artifacts or {},
        )
        # 失败传播(与老路径一致)
        if sub_result.outcome is not None and sub_result.outcome.kind.name == "FAILED":
            raise RuntimeError(...)
        return sub_result.state

    # 老路径(完全不动):GraphAssembler().assemble() → _drive
    factory = self._subgraph_executable_factory
    scope = self._subgraph_scope
    if scope is not None:
        ...
```

**关键边界**:
- 老路径(`scope is not None` → GraphAssembler + factory 兜底) — **完全不动**
- v2 分支只在 `isinstance(_, V2BundleGraphPlanMarker)` 时激活
- 两个分支互不干扰

---

## 5. dataflow 端到端

```
outer drive (interpreter._drive)
  → think.main 节点, sub_spec_ref = {plan_ref: bundles/think.yaml}
  → _drive_subgraph_ref(...)
    → resolver.resolve("bundles/think.yaml")
      → BundleSubgraphResolver._compile_bundle_graph
        → BundleGraphSpec(5 nodes + 5 edges)
        → _wrap_compiled_run_plan(含 V2BundleGraphPlanMarker 标记)
        → CompiledRunPlan(phase_graph=...)
    → sub_plan_obj.isinstance(_, V2BundleGraphPlanMarker) = True ✓
    → NodeGraphDriver(spec, plan_ref, scope).run(outer_state, artifacts)
      ┌─ 主循环 ──────────────────────────────────────────────┐
      │ current_node = spec.nodes[0] = think.shortcut         │
      │ executor = FactoryRegistry.resolve("think.shortcut",  │
      │                                    "phase:think")      │
      │ ctx = NodeContextFactory.build(node, scope, state)    │
      │ inp = NodeInput(port_context.get_input(node.id))      │
      │ out = await executor.node_execute(ctx, inp)           │
      │   ↓ ThinkShortcutExecutor.node_execute                │
      │   ↓ 拿 SupportsShortcut, 调 try_shortcut(state)      │
      │   ↓ NodeOutput(port_values={"decision": Decision()},  │
      │   ↓            next_hint="shortcut_taken")           │
      │ phase_result = NodeOutputProjector.project(           │
      │     out, NodeOutputSchema(result_kind="decision",     │
      │                          payload_port="decision"))    │
      │   ↓ PhaseResult(result_kind="decision",               │
      │   ↓             payload=Decision())                  │
      │ emit("phase_graph.node.start", purpose="shortcut...") │
      │ emit("phase_graph.node.end", purpose="shortcut...")   │
      │ edge = EdgeSelector.select(                           │
      │     current_node.id, plan.edges, phase_result, {})   │
      │   ↓ evaluate_restricted_predicate("result.payload != None") = True
      │   ↓ 选 think.shortcut → think.gate                  │
      │ current_node = think.gate                             │
      │ port_context.merge("think.shortcut", out.port_values) │
      │                                                       │
      │ (重复) current_node = think.gate                      │
      │ ... DecisionGate.enforce(state, decision)            │
      │ ... PhaseResult(result_kind="decision",               │
      │                  payload=enforced_decision)           │
      │ edge = EdgeSelector.select("think.gate", ...)        │
      │   ↓ no edges from think.gate (terminal)              │
      │   ↓ return None                                       │
      │ → 终止                                                │
      └───────────────────────────────────────────────────────┘
    → return InterpretationResult(
          state=outer_state,  # 节点不直接改 outer state;reducer 经事实路径改
          visits=(...),
          facts=(...),
          terminal_node="think.gate",
          outcome=None,
      )
  → outer drive 拿回 state + facts;reducer 经事实路径 commit 到 spine
  → outer drive 继续 walk think.main → act.main 边
```

**关键事实**:
- `NodeGraphDriver` **不直接写 outer state**,只 emit 事实(events + facts);reducer 经既有路径 commit
- 老 reducer 路径完全不动(C12 合约保留)
- DSL 完全不动(`evaluate_restricted_predicate` 复用)

---

## 6. 职责边界与禁止事项

| 边界 | 允许 | 禁止 |
|---|---|---|
| `NodeGraphDriver` 感知 phase / outer drive | 否 | 改 outer AgentState;调 Reducer;emit `kernel.run.*` |
| `NodeExecutor` 感知 graph / driver | 否 | 读 yaml;调 interpreter 任何 API |
| `NodeContext` 跨节点共享 | 否(MappingProxyType) | 任意 dict setitem |
| 老 declarative 路径(_drive + GraphAssembler) | 不动 | 重构;加 v2 字段 |
| 新 EP 词表 | 不引入 | 复用现有 phase_graph.node.start/end |

---

## 7. 实施步骤(同 PR 闭环)

| # | 步骤 | 产出 |
|---|---|---|
| 1 | ADR-0218 Accepted + Note 升 implemented/ | 文档 |
| 2 | `v2_plan_marker.py`(Protocol,30 行) | `V2BundleGraphPlanMarker` |
| 3 | `BundleSubgraphResolver._wrap_compiled_run_plan` 加 marker mixin | resolver |
| 4 | 4 个新模块(`v2/` 子包,~370 行总) | Driver / Projector / Factory / Selector |
| 5 | `interpreter._drive_subgraph_inner` 加 v2 分支(15 行新增) | interpreter |
| 6 | `bundles/think.yaml` 加 `result_kind` / `payload_port` 配置 | yaml |
| 7 | 简化 `_wrap_compiled_run_plan`:删 PhaseBinding/CapabilityPlan/ValidationReport/PlanProvenance 兜底(走纯 v2 路径) | resolver |
| 8 | 单元测试 ×4(每个新模块一个测试文件) | tests/v2/ |
| 9 | interpreter 集成测试:`test_interpreter_v2_subgraph.py`(走 v2 分支) | tests/harness/graph/execute/ |
| 10 | 端到端:`run_f01e7e932a0b` 同语义 run 跑通六语义 | kernel + e2e |
| 11 | 既有测试全过(56 个不退化) | pytest |
| 12 | `MappingProxyType` 应用到 `NodeContextFactory.build` 的 budget/metadata 字段 | factory |

---

## 8. delete-when

本 ADR 实施完成 + 上述 §7 全闭环后升 Archived:
- `_wrap_compiled_run_plan` 临时兜底层已删
- v2 plan 走纯 v2 路径,不再伪装成老 plan
- v2 调度循环在生产稳定运行 ≥ 4 周
- 反映 sub-decision(如 `_drive_subgraph_inner` v2 分支行数 ≤ 30 行)已成 SSOT

---

## 9. 范围外(明确不做)

- `bundles/reflect-subgraph.yaml` 迁 v2 — 独立 ADR(ADR-0217 §7 已声明)
- `agent_lab/graphs/*` 与生产 kernel 对齐 — 独立 ADR(ADR-0217 §7)
- `NodeExecutor` 用于 think 之外的 phase(perceive / act / reflect / remember / stop) — 本 ADR 不动 PhaseExecutor
- 节点动态并发(并行 / 合并节点) — `edges[].kind: data` 字段已预留,本 ADR 不实现并行调度,留后续 ADR
- 节点故障恢复(checkpoint / resume) — v2 plan 不走 Session checkpoint,留后续

---

## 10. 备选决策链

| 备选 | 否决理由 |
|---|---|
| 把 v2 plan 永远走老 GraphAssembler 路径(不写本 ADR) | NodeOutput 与 PhaseResult 语义不兼容,强行走会污染老路径,违反职责边界 |
| 在 interpreter 里直接写 v2 调度循环(不开新模块) | interpreter 已有 1100+ 行,再加 200 行 v2 循环会让文件膨胀到 1300+ 行,违反模块化 |
| 开独立 `interpreter_v2.py` 完全替代 | 95% 通用代码(declarative 路径 / DSL / Reducer)不重复,违反 C6 最小化 |
| 把 NodeExecutor 合并回 PhaseExecutor(统一签名) | 6 phase + 12 control 的"phase 级"语义与 think 5 步的"节点级"语义不同,合并会砍掉 NodeContext 的 ports 抽象 |
| 用 executor 自己实现 v2 调度(每个 think 节点内置"下一步"逻辑) | 把调度职责塞进 plugin,违反职责边界,且 yaml 拓扑成为装饰 |
