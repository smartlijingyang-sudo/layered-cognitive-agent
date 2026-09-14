# 信息图内核可借鉴设计参考（agent_lab 遗产）

> Status: reference-only。本文描述的机制在当前代码树中**没有实现**：`agent_lab/` 包与
> `lca/plugins/lab/` 插件树已删除。本文不是现行契约，不能被当作实现状态引用。
>
> delete-when: §4 的每一条都被生产图内核吸收（各自附 ADR），或被 ADR 明确否决后，删除本文。

## 1. 范围与所有权

`agent_lab/` 是 [ADR-0206](../adr/0206-information-graph-kernel.md)（可编译信息图认知内核）的
原型：单一可执行图种 `InfoEdgeSpec`，节点是有名有责的工人，六个语义阶段与模型可见构造都是
同一图的嵌套子图。[ADR-0209](../adr/README.md) 规划把它全量收编进 LCA plugin 体系，
PR-A.3 → PR-E.2 落地后停在 P7 阶段闭集迁移，状态始终是 Proposed，前置条件是"等 cordis LCA
runtime 可用"。节点实现层在 PR-D 被删除后，包已不自洽：`agent_lab/` 只剩图内核半边，
工人半边在 `lca/plugins/lab/`（约 96 个 carrier 包 + `internal/{hooks,loader,audit}`）。
两半一起删除。

现行权威契约（本文所有"生产现状"均以这些为准）：

| 关注点 | 权威位置 |
|---|---|
| 生产图 DTO 与遍历 | `lca/contracts/protocols/graph/{plan,node_io,binding,ports,strategy}.py` · `lca/framework/graph/` |
| bundle 图描述 v2 | [ADR-0217](../adr/0217-bundle-graph-schema-v2.md) · `lca/contracts/protocols/declarative/declarative_1/bundle_graph.py` |
| 子图驱动 | [ADR-0218](../adr/0218-bundle-graph-v2-subgraph-driver.md) |
| 图/业务职责切分、typed 端口 | [ADR-0219](../adr/0219-phase-graph-unification.md) |
| 信息图内核设计意图与 C1–C14 不变量表 | [ADR-0206](../adr/0206-information-graph-kernel.md) |
| 阶段级容错 | `declarative_fault_tolerance.py::PhaseExecutionPolicy` |
| plan 指纹与恢复 | `lca/harness/plan.py` |

**读法警告。** 原型的 schema 远大于它的实现。`parallelism`、`Edge.required`、
`EdgeKind.EFFECT`、`EdgeKind.CONTROL`、`InfoGrant.mode`、`discard_sink`、`Port`、`PortTag`、
`Joiner`、`Schedule`、`bindings`、`plan_hash` 都被解析或定义，却没有任何消费者；
没有一份出厂 YAML 用到 `grants` / `borrow` / `effect` / `control` / `on_error` / `discard_sink`。
因此 §2 逐条标注**已接线**与**仅声明**，§4 的每个借鉴项也标注它在原型里是否真的跑过。
把"原型声明过"当成"原型验证过"是这份材料最大的误读风险。

## 2. 本体与精确形态

全部 Pydantic `frozen=True, extra="forbid"`（C13）。

### 2.1 Artifact — 不可变信息载体（已接线）

| 字段 | 类型 | 说明 |
|---|---|---|
| `kind` | `ArtifactKind` | `text` / `message` / `manifest` / `receipt` / `fact` / `intent` / `digest` / `exception` |
| `content` | `Any` | 无类型载荷，见 §5 C-6 |
| `schema_ref` | `str` | 默认 `"raw"`；结构化载体用 `openai.message.v1` / `error.exception.v1` |
| `digest` | `str` | sha256，`Field(default="", validate_default=True)` |

`digest` 由 `mode="before"` 校验器在调用方留空时自动填充，输入是
`repr((schema_ref, content))`，因此 content 必须 repr 稳定（C8）。
`validate_default=True` 是必需的：Pydantic v2 默认跳过省略字段的校验器，否则 digest 永久为空。
`short_id()` = `digest[:12]`。

`make_exception(error_class, message, node_id, transient, detail)` 是失败载体的唯一构造入口，
`schema_ref="error.exception.v1"`。**`transient` 从未被读取**：运行期的可重试判定实际来自
Python 异常类型（`_NonRetryableError`），不是这个字段。生产的
`lca/cognition/body/internal/_retry_classification.py` 是同一职责的正确实现。

### 2.2 Port / PortRef — 端口与跨图寻址

```python
class PortDir(StrEnum):   IN = "in"; OUT = "out"
class PortTag(StrEnum):   FACT / PROJECTION / EFFECT / CONTROL      # 仅声明
class Port:               id; dir; type="Any"; tag=FACT; optional   # 仅声明
class PortRef:            spec_id; node_id; port_id                 # 已接线
                          def label() -> f"{spec_id}/{node_id}.{port_id}"
```

`Port` 与 `PortTag` 在全仓从未被实例化。节点端口实际只是**名字**：`InfoNode.ins` / `outs`
是 `list[str]`，不带类型也不带 tag。`PortRef` 携带 `spec_id`，所以端口能在嵌套图中绝对寻址，
这是 §4.2 跨图许可与 §4.1 端口校验的前提。

`PortTag` 的分类意图（把 [根 AGENTS.md §2.2](../../AGENTS.md) 的事实/投影/回执/许可下沉到
端口类型）本身有价值，但原型没接线；要借用必须从校验器开始，而不是从枚举开始。

### 2.3 Edge — 五类语义边

```python
class EdgeKind(StrEnum):
    DATA = "data"        # 已接线：参与拓扑排序与传播
    PROJECT = "project"  # 已接线：参与拓扑排序与传播
    BORROW = "borrow"    # 已接线：传播时过 grant，但无出厂 YAML 使用
    EFFECT = "effect"    # 仅校验：不传播、不调度
    CONTROL = "control"  # 仅校验：不传播、不调度

class Edge:  id; from_ref: PortRef; to_ref: PortRef
             kind: EdgeKind = DATA; required: bool = True   # required 从未被强制
             grant_id: str | None = None                    # kind=BORROW 时必填
```

`effect` 与 `control` 边只存在于校验器视野里：运行期既不传播值也不产生调度。
所以"五类边"在原型中是**两条真边 + 三类标注**。

### 2.4 InfoNode / InfoEdgeSpec

```python
class NodeRegion(StrEnum):  PHASE / MODEL_VISIBLE / EFFECT / LINEAGE / DIGEST / CONTROL
class ErrorRoute(StrEnum):  FAIL / RETRY / ROUTE            # 仅声明，无出厂 YAML 使用

class InfoNode:
    id: str
    region: NodeRegion = DIGEST
    factory: str = "identity"        # 运行期查注册表
    config: dict[str, Any] = {}
    ins: list[str] = []; outs: list[str] = []     # 端口名，无类型
    on_error: ErrorRoute = FAIL; route_to: str | None = None
    parallelism: int = 1             # 解析后丢弃；运行期无任何并发

class InfoEdgeSpec:                  # 唯一可执行图种
    id; version="0.1.0"; region=DIGEST; description=""
    phase: str = ""                  # 不透明标签，骨架不解释
    nodes; edges; grants; sub_specs; plugins
    discard_sink: str | None = None  # 仅校验用
```

`phase` 与 `region` 分离：`region` 是枚举，`phase` 是名字，完整标签由
`current_region_label(spec)` 组装（§4.5）。`initial_ports()` 返回从合成源节点 `_initial`
接出的端口集合，即调用方必须提供的外部输入（§4.6）。

### 2.5 SubSpecLink / InfoGrant

```python
class SubSpecLink:                   # 已接线
    node_id; sub_spec_id
    input_map:  dict[str, str]       # parent_port -> sub_spec_port
    output_map: dict[str, str]       # sub_spec_port -> parent_port

class InfoGrant:                     # 校验已接线，运行期 grant 已接线，无出厂 YAML 使用
    id; from_spec; to_spec
    ports: list[str]                 # 必须非空
    mode: str = "read"               # read | consume —— 从未被读取
    max_bytes: int = 0               # 0 = 不限
    redact: list[str] = []
```

### 2.6 编译管线（8 段，顺序执行）

| # | 段 | 产出 / 行为 |
|---|---|---|
| 1 | `_resolve_plugins(spec)` | `load_all()` 后逐个 `resolve_plugin(ref)`；返回 `None` 的静默丢弃 |
| 2 | `before_compile` 扇出 + **拓扑守恒守卫** | 见 §4.7 |
| 3 | `validate(spec, sub_registry)` | 错误列表非空 → `ValidationError(errs)`，一次性报全部 |
| 4 | bindings 投影 | 每边一条 `{edge_id, from, to, kind, required}`；**无消费者** |
| 5 | 拓扑分层（Kahn） | 只对 `kind ∈ {data, project}` 的边算入度；跳过 `_initial` 源与跨 spec 边；每层按字母序排序保证确定性。**残余入度 > 0 的节点（即环）被追加成最后一层而不报错**，见 §5 C-2 |
| 6 | subgraph_calls 投影 | 每个 `SubSpecLink` 一条 `{node_id, sub_spec_id, input_map, output_map}` |
| 7 | `plan_hash` + `spec_dump` | sha256 over `{spec_id, version, nodes, edges, sub_specs, grants}`；**含 `config`**，与第 2 段的拓扑签名不同（§4.4） |
| 8 | 返回 `CompiledGraphBundle` | frozen：`spec_id / plan_hash / spec_dump / bindings / layers / subgraph_calls / plugin_instances` |

运行期用 `InfoEdgeSpec.model_validate(bundle.spec_dump)` 复原 spec，所以 dump 才是实际执行契约。
`plan_hash` 被计算、被测试断言非空，但**从未用于恢复拒绝**——ADR-0206 §5.1 的
"plan_hash 不匹配 → 拒绝恢复"没有实现。

### 2.7 运行期执行模型

严格同步、逐层执行，**没有并发**：

1. 播种：`store[("_initial", port)] = artifact`。键在 `_initial` 命名空间下而非 `(node, port)`，
   所以多个节点可以共用一个 IN 端口名而不互相覆盖。
2. `for layer in bundle.layers: for node_id in layer: if node_id not in executed: _run_node(node_id)`。
3. 收尾：按声明顺序遍历 `spec.nodes`，把 store 里存在的 OUT 端口写进 `finals`
   （**跨节点后写覆盖前写**），再 `setdefault` 未被消费的 `initial` 项。

单节点执行：标记已执行 → 发 `node_start` → 收集输入 → 先跑挂在本节点上的所有 `SubSpecLink`
再调 factory（跑完后刷新本 host 的全部 store 项，使后一个兄弟子图能读到前一个的 OUT）→
`_invoke_with_policy` → 写输出 → 沿 `data` / `project` / `borrow` 边传播（`borrow` 过 grant）→
发 `node_end`。

`Joiner`（按 expected 端口集合做 barrier 累加）与 `Schedule` 作为类存在并从
`runtime/__init__.py` 导出，但**运行器从不 import 它们**。barrier 语义完全隐含在拓扑分层里，
ADR-0206 C7 未被强制。

### 2.8 校验器检查清单

`validate(spec, sub_registry) -> list[str]`，空列表 = 合法。**真在跑的检查**：

| 名 | 规则 |
|---|---|
| `C6` 端口已声明 | 每个非 `_initial` 边端点的 `(node_id, port_id)` 必须在 `node.ins`/`outs` 里；端点节点必须存在 |
| `C6` 方向 | `from_ref` 必须是 OUT 端口，`to_ref` 必须是 IN 端口 |
| `N5` 跨 spec 边类型 | 跨 spec 的边只允许 `kind ∈ {project, borrow}` |
| `C2/C3` 回执落点 | 每条 `kind=effect` 边的目标节点 `outs` 必须含字面量 `"receipt"`，或 `spec.discard_sink` 非空 |
| `C12` 子图映射 | `link.node_id` 存在；`input_map` 的键 ∈ `node.ins`；`output_map` 的值 ∈ `node.outs` |
| `N3` 一 host 一子图 | `Counter(link.node_id)` 必须恰为 1 |
| `N4` host factory | host 节点的 `factory` 必须 ∈ `frozenset({"graph.call"})` |
| `C4` grant 端口非空 | 每个 `InfoGrant` 至少声明 1 个端口 |
| `C4` borrow↔grant | `borrow` 边必须有 `grant_id`；grant 必须存在；`from_spec` / `to_spec` / 端口三项都要对得上 |
| `C6.1` 路由目标 | `on_error=route` ⇒ `route_to` 非空、目标节点存在、目标至少有一个 IN 端口能接住 EXCEPTION |
| `C1` 投影闭合 | 触发条件是 `spec.id == "act"` 或存在 effect 边或存在 factory 为 `act.observe` 的节点；要求至少一条从本 spec 出发的 `project` 边。这是"act 有一条出向投影边"，**不是**可达性闭合 |
| `C14` region 闭集 | 只能经 `validate_with_profile` / `validate_subgraph_with_profile` 到达，**`validate()` 不跑它，因此 `compile()` 从不执行 C14** |

**静默空转的检查**（每个都以 `try: from agent_lab.nodes.base import NodeRegistry` 开头，
`except ImportError: return []`；PR-D 删掉 `agent_lab/nodes/` 后四条不变量全部变成恒真）：

| 名 | 本意的规则 |
|---|---|
| `N1` | YAML 的 `ins`/`outs` ⊆ factory 的 `NodeManifest` 端口集 |
| `N2` | manifest 的每个 `requires` 在本 spec 节点的 `provides` 里有提供者 |
| `C2/C11` emit 对齐 | `kind=effect` 边的源节点必须声明 `emits` |
| `C15` 端口类型兼容 | `data`/`project` 边的源 OUT 端口类型必须在 `_ALLOWED_SOURCES_FOR_TARGET[目标类型]` 内（如目标 `message` 只接受 `{message, text}`，目标 `artifact` 接受全部，目标 `text` 只接受 `text`） |

另外：`validate()` 从不强制 ADR-0206 真正的 **C6 单写**——这里的 `C6` 标签指的是"端口已声明 /
方向正确"。单写在任何地方都没有强制，运行期是 `store[(dst_node, dst_port)] = art`，后写静默覆盖。
标签与 ADR 表冲突，见 §5 C-12。

### 2.9 声明式 YAML 形态

```yaml
id: act
version: 1.0.0
region: phase:act
description: >
  Decision → Intent → grant → EffectReceipt → Observation.

graph:                    # 组织元数据，不是数据流；只被 run.py --describe 消费
  id: act
  layer: effect
  purpose: Body.act(Decision) → Observation, decomposed into five workers.
  members: [shape, authorize, compose, execute, observe]
  references: [model_eye, agent_loop]
  relations:
    - { graph: agent_loop, kind: child_of,  role: act_phase }
    - { graph: model_eye,  kind: writes_to, role: project_observation }
  capabilities:
    provides: [effect_receipt, observation]
    requires: [decision, tool_registry, safe_executor]

nodes:
  - id: shape
    region: phase:act
    factory: lab.act.shape          # 插件 id，运行期查注册表
    config: { from: decision, to: intent }
    ins: [decision]
    outs: [intent]

edges:
  - id: e_init_decision_to_shape    # 外部输入经合成源节点 _initial 进入
    from: { spec: act, node: _initial, port: decision }
    to:   { spec: act, node: shape,    port: decision }
    kind: data

  - id: e_observe_to_model_eye      # 跨 spec 投影：效应 → 模型可见闭包
    from: { spec: act,       node: observe, port: observation }
    to:   { spec: model_eye, node: see,     port: observation }
    kind: project

sub_specs:
  - node_id: perceive_host
    sub_spec_id: perceive
    input_map:  { raw_input: perceive.in_raw }
    output_map: { perceive.out_manifest: manifest }

grants:
  - id: g_act_reads_think
    from_spec: think
    to_spec: act
    ports: [decision]
    mode: read
    max_bytes: 0          # 0 = 不限
    redact: []
```

## 3. 已被生产覆盖（不要重新发明）

| 机制 | 生产所有者 |
|---|---|
| 单一可执行图种，region 是标签不是第二种图 | `lca/contracts/protocols/graph/plan.py` 的单一 `Plan`；`BindingKind` 是闭集派发口（9 值，加值必须同时加 strategy 与注册项，不会静默默认） |
| 从节点挂嵌套子图 | `PlanNode.subgraph_ref` + `lca/framework/graph/strategies/subgraph_strategy.py` |
| 递归深度上界 | `SubgraphStrategy.max_depth=4` + host `depth_counter`；`SubgraphDepthExceededError` / `SubgraphCycleError`（PG-007-cycle） |
| 确定性访问顺序 / cursor / 访问预算 | `lca/framework/graph/traversal.py::PlanTraversal` |
| frozen + `extra="forbid"` + 解析期校验 | `Plan` / `PlanNode` / `PlanEdge` / `BundleGraph*` 全部如此，`__post_init__` 抛 `PG-005-bundle-graph` |
| typed 端口存储 + fail-loud `require()` | `PortRegistry` + `NodeInput.require` / `NodeSchemaError`（携带 producer / consumer / port，调试不依赖 grep 日志） |
| 拒绝未声明的产出端口 | `NodeIOSchema.project_outputs` |
| 冻结、带摘要的模型可见包 | `ContextManifest{items, digest, schema_version}` + `digest_manifest` |
| 非可执行工具清单 vs 执行路径 | `SimpleToolRegistry` + `concept.tool.fork` / `ForkedTools` 提供模型可见 schema，`ToolSchema.from_any/from_openai/from_manifest`，执行走 Body→SafeExecutor→Sandbox 窄门（C10） |
| 图生命周期事件与 EP 映射隔离 | `GraphObservation` + `lca/framework/graph/ep_table.py::GraphEpTable` |
| observer 失败被容纳、不回滚已提交 append | `GraphObserver.observe() -> None`；`fanout_hooks` 逐插件 try/except |
| 六阶段闭集作为 `phase:<name>` region 标签 | ADR-0210（Accepted）· `bundles/phase_main_outer.yaml` |
| 确定性 vs 瞬时错误二分、确定性不重试 | `lca/cognition/body/internal/_retry_classification.py` + SafeExecutor 重试循环 |
| 阶段级重试 / 超时 / 退避 / 耗尽路由 | `phase.execution_policy.resilient`（`bundles/declarative-phase-graph.yaml`），PG-010 校验 |
| factory 名 → executor 解析，miss 即 fail-loud | `FactoryResolver` / `runtime.resolve_factory`（ADR-0217 §3.1）· `PG-005-factory` |
| 条件分支声明在数据里而非节点代码里 | `PlanEdge.when` + `evaluate_restricted_predicate` |
| Gate 是 think 子链而非图节点 | `GateChainStrategy` 复用 cognition 的 `DecisionGate` 协议 |
| 扇出/扇入带 reducer | `ParallelStrategy`（`children` + `reducer`）· `AgentFanoutStrategy` |
| 图与插件的 self-describe CLI | `./scripts/lca-ops plan compile/validate/tree` · `inspect-tree` · `why-plugin` · `lca/harness/diagnostics/{tree,inspect,doctor}` |
| plan 指纹与恢复 | `lca/harness/plan.py`：`canonical_json` / `declarative_plan_hash` / `compiled_run_plan_ref` + capability/control/scope/declarative 分域子哈希。跨进程确定性，强于原型的单个 `_stable_hash` |
| region 闭集可由 profile 扩展 | `ProfileSource.regions_declare` + `profiles/web-assistant.yaml` 的 `regions.declare`。**字段在，校验器不在**，见 §4.5 |
| 由 region 标签合成 phase plan | 已作废：`phase_graph` 字段已从 `CompiledRunPlan` 整体退役（`lca_kernel/plan/plan_compile.py`） |

## 4. 生产未覆盖、值得借鉴

每项标注它在原型里是**已接线**还是**仅声明**——仅声明的项等于设计草稿，借用时要从头实现。

### 4.1 编译期端口接线校验（原型：部分已接线）

**问题。** 生产 `BundleGraphSpec.__post_init__` 只有三条检查：node.id 唯一、edge 端点命中、
entry 命中。它能回答"这是不是一张良构有向图"，不能回答"这张图跑得起来吗"。ADR-0206 的核心
主张——从结构上消灭"工具已执行但下次模型看不见"这类漏洞——需要的正是后者。

**机制。** §2.8 的真跑检查里，与端口接线相关的是：`C6` 端口已声明 + 方向正确、`N5` 跨 spec
边只允许 project/borrow、`C12` 子图 input_map/output_map 必须落在真实父端口上、`C15` 端口类型
兼容矩阵。失败语义是**非 fail-fast**：一次编译报告所有缺陷，而不是修一个再撞下一个。

**生产现状与张力。** ADR-0219 §5.5 刻意让图不再持有 `inputs` / `outputs`（"图不知道业务，
业务不知道图"），端口契约属于 plugin 的 `NodeExecutor.declared_inputs` / `declared_outputs`，
bundle YAML 容忍这两个字段但运行期忽略。所以图层**当前无法**静态校验端口接线。

**落点与成本。** 不要回退 §5.5。让编译器把图的边与插件注册表里的 `declared_inputs` /
`declared_outputs` 做 join，在编译期重建端口视图再跑上述检查。图仍然业务无关，静态校验回来。
落点在 `lca/harness/declarative/compile/subgraph_resolver.py::_compile_bundle_graph`，
它已经能拿到 `FactoryResolver` 的解析结果。前提是先修 §5 C-4：factory 解析不到必须是**错误**，
不能是跳过。错误码沿用生产已有的 `PG-00x` 空间，不要复活 C 编号（§5 C-12）。

### 4.2 跨图读取许可 InfoGrant（原型：校验与运行期已接线，无出厂 YAML 使用）

**问题。** C5 的三维单调能力管的是副作用出口 `CommandEnvelope`。观察面没有对应物：
没有任何东西约束一个子图能从兄弟图读到什么，也没有脱敏与体积上限。

**机制。** `kind=borrow` 的边必须带 `grant_id`；编译期检查 grant 存在且 `from_spec` /
`to_spec` / 端口三项都对得上；运行期在传播时执行 `max_bytes` 截断与 `redact` 字段剥离。
`mode`（read / consume）在原型里从未被读取，借用时需要自己定义语义。

**落点与成本。** 契约在 `lca/contracts/`，执行在跨图边界（`SubgraphStrategy` 调子图处）。
这是把 C5 的思路搬到观察面：许可是数据，越界 fail-loud，而不是靠调用方自律。
依赖 §4.3（先有 `borrow` 这个边类）。

### 4.3 边的语义分类（原型：project/data/borrow 已接线，effect/control 仅校验）

**问题。** 生产 `EdgeKind = Literal["control", "data"]`。一条边无法声明"这次跨越是副作用"、
"这条进入模型可见闭包"、"这是跨图借用"。于是 C2（双平面）与 C7（控制/观察分离）在图里
不可表达，只能靠散文和插件自觉维持。

**机制。** 五类 `EdgeKind`（§2.3）+ 三条编译期规则：`effect` 边的目标必须能接住回执
（或显式落到 `discard_sink`）；`project` 边必须跨越模型可见闭包边界；`borrow` 边必须引用
匹配的 grant。

**注意原型的实现落差。** `effect` 与 `control` 边在运行期既不传播也不调度，只被校验器看见。
也就是说这个分类在原型中是**文档性的**，不是执行性的。真要采用，得决定这两类边在运行期
到底意味着什么，否则会复制同一个落差。

**落点与成本。** `bundle_graph.py` 扩 `EdgeKind` Literal，校验落在
`subgraph_resolver._compile_bundle_graph`。这是闭集变更，按
[根 AGENTS.md §1](../../AGENTS.md) 必须先有 ADR，并同步 whitelist / catalog / 消费方 / 文档。
成本主要在所有现存 bundle YAML 的边都要显式归类。

### 4.4 两个不同的图身份：拓扑签名 vs 完整 plan hash（原型：已接线）

**问题。** "图变了吗"有两个不同的答案。插件在编译期标注了图，算不算图变了？改了 `config`
里的一个阈值，算不算要重新编译？用一个哈希回答两个问题必然有一个是错的。

**机制。** 两个独立的 sha256：

- **拓扑签名** = `{nodes: [(id, factory, ins, outs)], edges, sub_specs, grants}`。
  **刻意排除** `config` / `description` / `plugins` / `region` / `version`。
  用途只有一个：`before_compile` 守卫（§4.7）——插件可以改 config，不能改接线。
- **plan_hash** = `{spec_id, version, nodes(全量 dump), edges, sub_specs, grants}`，
  **包含 `config`**。用途是恢复与缓存失效：config 变了就是另一个计划。

**生产现状。** `lca/harness/plan.py` 有更强的分域子哈希体系，但只有"完整计划"一个粒度，
没有"仅拓扑"这一层，因此无法表达"插件重写了接线"这个失败。

**落点与成本。** 小。采用 §4.7 时几乎免费：守卫需要的正是那个排除了 config 的签名。

### 4.5 region 标签闭集校验 C14（原型：已接线，但 compile 从不调用它）

**问题。** 生产解析 `profiles/*.yaml` 的 `regions.declare` 到 `ProfileSource.regions_declare`，
`BundleGraphNode.region` 用作 `FactoryResolver` 反查提示，但**没有任何代码校验 region 标签合法**。
`profiles/web-assistant.yaml` 声明了 `phase:plan` / `phase:replan` / `control:safety`，无人检查。
`BundleSubgraphResolver.resolve_factory` 的文档字符串自陈是 fail-soft 并 `del factory, region`。

**机制。** 闭集 = 六个阶段 region ∪ 五个裸 enum region ∪ profile 自定义：

```python
BUILTIN_PHASE_REGIONS = ("phase:perceive", "phase:think", "phase:act",
                         "phase:reflect", "phase:remember", "phase:stop")
BUILTIN_BARE_REGIONS  = ("model_visible", "effect", "lineage", "digest", "control")

def build_region_closed_set(profile_regions):
    return set(BUILTIN_PHASE_REGIONS) | set(BUILTIN_BARE_REGIONS) | set(profile_regions or ())

def region_label_for_node(region_enum, phase_name):
    return f"phase:{phase_name}" if region_enum == "phase" and phase_name else region_enum
```

标签构造：`region == PHASE` 且 `phase` 非空 → `phase:<name>`；`PHASE` 但 `phase` 为空 →
`phase:<unnamed>`，这本身是一条违规，因为无法归属的阶段等于没有可观测归属。未绑定的 region
是编译错误。校验要沿 `sub_specs` 递归覆盖整个嵌套图——但原型的递归是坏的（§5 C-13）。

**落点与成本。** 常量与标签函数属 `lca/harness/profile/`（`ProfileSource` 的所有者），
校验属编译路径。约 60 行。成本低，但**会把当前能加载的 profile 变成编译错误**：
落地前必须先审计所有 `profiles/*.yaml` 的 region 标签，否则第一次跑就红。

### 4.6 显式图接口：声明的进口与出口分离（原型：已接线）

**问题。** 生产 `Plan.declared_inputs` 一物两用：它既是外层播种端口表，又在
`_terminal_port_values` 里被用来投影子图的**输出**，为空时回落到整个端口快照。
图的接口因此无法独立于拓扑声明，而且那个回落会把每个内层端口泄漏到外层注册表。

**现存缺陷（已核对）。** `lca/framework/graph/interpreter.py:258-265`：

```python
def _terminal_port_values(ports: PortRegistry, plan: Plan) -> dict[str, Any]:
    """Project the terminal port set onto the plan's declared outputs."""
    if not plan.declared_inputs:          # 文档说 outputs，代码读 declared_inputs
        return dict(ports.snapshot())     # 为空时泄漏全部内层端口
    return ports.exit_subgraph(plan.declared_inputs)
```

**机制。** 两个非对称的显式面：

- **进口**：保留合成源节点 id `_initial`。`from: {node: _initial, port: X}` 声明 X 是外部输入。
  `initial_ports()` 扫这个 id 就回答"调用方必须提供什么"。运行期播种到 `store[("_initial", port)]`
  而不是 `(node, port)`，所以多个节点能共用输入端口名而不互相覆盖。
- **出口**：只有 host 的 `SubSpecLink.output_map` 的**值**，别的都不算。子图返回 finals 后
  `missing = [k for k in output_map if k not in child_outputs]`，非空即抛
  `sub_spec <plan_ref> missing exports <missing>`——**fail-loud 的出口契约**，不是部分合并。
  子图中途失败时，已写出的值留在子图 trace，不经 output_map 渗进父 OUT；父图只看见 host 失败。
- 校验侧：`_initial` 源边豁免"端口必须在节点上声明"检查，也豁免拓扑入度计算。
  一处命名清晰的豁免，而不是散落在调度器里的特例。

**落点与成本。** 契约层加 `declared_outputs`（或把 `output_map` 提到 `Plan` 上），
`_terminal_port_values` 改读它，去掉快照回落。这是 §4.1 的前置：没有分离的进出口，
端口接线校验无从表达。

### 4.7 命名式子图端口映射，取代按位置翻译（原型：已接线）

**问题。** 生产跨子图边界时**按列表下标**改名，长度不一致时有三级回落
（`subgraph_strategy.py` 入向与出向各一套）。

**现存缺陷（已核对）。** `bundles/phase_main_outer.yaml` 的 `act.main` 声明
`declared_outputs: [act_outcome, should_terminate]`（2 项），而内层入口
`bundles/act.yaml` 的 `act.validate` 声明 `outputs: [receipt]`（1 项）。长度不等 →
按下标分支跳过 → 按名分支只匹配上 `should_terminate` → `act_outcome` 取到的是扁平注册表里
恰好存在的东西。再叠加 §4.6 的 `_terminal_port_values` 读错字段，跨子图的输出投影
在两个地方同时不可靠。

**机制。** 子图引用上挂两个字典：

```
input_map:  {outer_port_name: inner_port_name}    # 播种内层注册表
output_map: {inner_port_name: outer_port_name}    # 导出回外层注册表
```

接缝处的算法：① `initial = {inner: outer_ports[outer] for outer, inner in input_map.items() if outer in outer_ports}`；
② 跑内层；③ `missing` 非空即抛（fail-loud 出口契约）；④ 按 `output_map` 逐对写回外层；
⑤ 其余内层端口一律不泄漏。

**不变量。** 每个 `output_map` 的值必须是 host 节点已声明的 OUT 端口，每个 `input_map` 的键
必须是已声明的 IN 端口——这两条正是 §2.8 的 `C12`，编译期可查。

**落点与成本。** `SubgraphReference` 加两个 mapping 字段，`SubgraphStrategy` 的三级回落
换成显式映射 + fail-loud。这会暴露现存的错位（上面那对 2 vs 1），所以要先修 bundle 声明。

### 4.8 before_compile 拓扑守卫（原型：已接线）

**问题。** 能在编译期改写图的插件，可以静默改变实际会跑什么。

**机制。** 插件钩子 `before_compile(spec, sub_registry) -> spec | None`（返回 None 表示不改）。
编译器在改写前后各算一次**拓扑签名**（§4.4，刻意排除 config）。签名变了就抛
`ValidationError(["plugin <name> before_compile rewrote topology; forbidden"])`。
于是插件可以标注、可以填 config，**永远不能重新接线**。

**为什么值得单独留一条。** 原型自己有一个 `ControlSlotsPlugin.before_compile` 真的在改拓扑：
从 Python 接线表注入 `SubSpecLink`、改 host 的 `ins`/`outs`，导致根 YAML 不再是拓扑真值。
团队自己否决了它，理由记录在案："打开 agent_loop.yaml 看不见 stop 从哪根边读 state_ref；
plan_hash 对插件改写敏感却对读者不透明。Observation/Capability 平面混在 hook 里。否决。
插入政策若要换，改父图，不改 Python。" **保留守卫，不要保留改写能力。**

**落点与成本。** 编译路径，几十行。这是 C1（认知闭集）在图层的执行形式：闭集不靠约定，
靠一个会失败的签名比较。

### 4.9 subgraph_path：每条嵌套观测都带完整路径（原型：已接线）

**问题。** 生产 `GraphObservation` 带 `depth: int` + `plan_ref` + `node_id`，不带路径。
三层嵌套且同一个 bundle 被引用两次时，`depth=3, node_id=act.observe` 无法指出是**哪一个**
`act.observe`。ADR-0206 C13 要求子图内的边点火事件必须携带 `subgraph_path`，
§5.7 E7 要求从最终产物反查 manifest → 模型请求 → 工具调用 → 审批 → 回执，
这需要一个稳定的位置键，不是深度计数器。

**机制。** 一个字符串，在递归接缝处拼接，穿进每个子事件：root 是 `spec.id`；
child 是 `f"{parent_path}/{sub_spec_id}"`。每个 trace 事件都带它，于是 `edge_fire` /
`node_start` / `node_end` / `subgraph_enter` / `subgraph_exit` 全部可按位置寻址。
`subgraph_enter` 的 payload 额外带 `subgraph_path_child`，让 enter 事件在子图发出任何东西
之前就命名子图的路径。与 plan_hash 合起来构成幂等键：同一
`(plan_hash, subgraph_path, node_id)` 一次 Run 只 invoke 一次。

**落点与成本。** `GraphObservation` 加一个字段，`SubgraphStrategy` 在递归处拼接并下传。
小改动，直接提升 journal 的可反查性（C3 事实可追溯）。

### 4.10 全树闭包加载 + 启动期校验（原型：已接线）

**问题。** 生产**在 run 期间、在 `SubgraphStrategy.execute` 内部**才懒加载内层 bundle。
文件缺失在 run 中途抛 `FileNotFoundError`，格式错误也在中途抛。更糟的是
`lca/framework/graph/lifter.py:215-216`：

```python
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return NodeIOSchema()
```

内层 plan 加载失败被吞成空 schema，这是
[根 AGENTS.md §4](../../AGENTS.md) 明确禁止的"用异常吞没、空 catch、隐式 fallback 掩盖契约缺失"，
并且直接造成 §4.7 的按位置翻译歧义。

**机制。** ① `load_registry(*ids)` 把图 id 解析成文件（先查图目录，再查一级子目录）；
② `load_closure(root_id)` 以 `sub_specs` 做 worklist BFS，产出
`dict[spec_id, spec]`，含 root 与全部传递引用的图；③ 把该 registry 传给闭包里**每一个** spec 的
`compile(spec, sub_registry)`，于是每条跨 spec 边、grant、`sub_spec_ref` 都是对着真实目标校验，
不是对着一个名字；④ 在 boot 失败，不在 run 失败。门禁形态：加载闭包 → 逐个编译 →
断言 `bundle.spec_id == id`、`plan_hash` 非空、`layers` 非空。

**落点与成本。** 生产 `lca-ops plan tree` 已经能展开树，缺的是"展开后逐个编译并作为 boot 门禁"。
先把 lifter 的 except 收窄成 fail-loud，否则闭包加载只是把同一个静默回落搬到更早。

### 4.11 图节点代码的静态纯度门禁（原型：已接线，随 lab 一起删除）

**问题。** 生产 v2 图有 `when` DSL 表达分支，但没有任何东西阻止一个 `NodeExecutor` 插件
在内部按数据分支——那会让 YAML 拓扑变成控制流的部分描述，声明边就失去意义。
`docs/architecture/checks.md` 列了约 24 个门禁，没有一个检查图节点代码。

**机制。三条可分离的门禁：**

1. **节点内不得按数据分支。** 逐行扫描节点插件文件，标记任何以 `if ` / `elif ` / `else:`
   开头的行，只放行两种形态：(a) 行内含 `isinstance(`（类型判别是合法的）；
   (b) 行匹配空值/空集合守卫正则。失败信息给出文件、行号与 offending 文本。
   理由要说清：真正的类型判别是合法的，不该为了过 grep 而重构；门禁针对的是**业务**分支，
   业务分支属于 `edges[].when`。
2. **节点之间不得互相 import（N7）。** 工人插件不得 import 另一个工人插件、不得在注册表里
   查兄弟、不得读父图端口存储、不得读模块级 Body/Session 全局。
   注意：这条法律写下来了，但命名的门禁脚本 `scripts/check_agent_lab_node_imports.py`
   **从未存在**——法律没有执行体。
3. **W-1…W-10 工人契约规则**（ADR-0211）：`execute` 签名形状、错误三态、
   禁止在节点体内构造装配根等。唯一实现是 `lca/plugins/lab/internal/audit/`
   （`signature_rules.py` / `body_rules.py` / `errors.py`），已随 lab 树删除。

**落点与成本。** 这三条与 agent_lab 无耦合，本质是 AST/grep 门禁，落点是 `scripts/` +
`docs/architecture/checks.md`。要恢复就得重写；本文保留规则形状，不保留实现。

### 4.12 图级能力声明，与 Profile 闭集对账（原型：仅声明，只被 --describe 消费）

**问题。** 生产图 DTO 只有 `id` / `region` / `purpose`。无法回答"哪些图写 model_eye"、
"这张图提供/要求什么"，只能读插件 manifest 加 grep。

**机制。** §2.9 的 `graph:` 块：`layer` / `purpose` / `members[]` / `references[]` /
`relations[{graph, kind, role}]` / `capabilities{provides[], requires[]}`。
`relations.kind` 是闭集（`child_of` / `contains` / `writes_to`），`role` 说明本图在这条关系里
承担什么职责。因为它不参与执行，可以独立校验一致性：members 是否都在 nodes 里、
relations 指向的图是否存在、provides/requires 是否与插件 manifest 相符、
`capabilities.requires` 是否被 Profile 的能力闭集覆盖。

**价值。** 让 `why-plugin` 一类查询在图粒度上成立，嵌套图森林可导航。

**落点与成本。** DTO 加字段 + 一个 diagnostics/inspect 消费者。属观察面（C7）：
不得影响执行，否则就成了第二个事实源。原型只把它接到 `run.py --describe`，
从未对账过 Profile 闭集——那一步才是价值所在。

### 4.13 变异式负面编译测试（原型：已接线）

**问题。** 一个从未被观察到失败的校验器，与一个不存在的校验器无法区分。原型的
N1/N2/C2-emits/C15 就是这样静默空转的（§5 C-4）。生产的 bundle-graph 校验器有同样暴露面：
CI 里没有任何东西删掉一条边然后断言特定错误码。

**机制。** 一个自足的负面夹具：① 读一份真实出厂图文件；② 用**字符串替换**移除一个结构元素
（`outs: [receipt]` → `outs: []`）；③ 替换没生效就 `sys.exit(2)` 报 "FAILED to mutate …"，
于是夹具漂移时门禁自己会失败，不会静默腐烂；④ 写到同目录 `.broken.yaml`，加载、编译；
⑤ 期望 `ValidationError`，打印违规数与前 5 条消息；若干净编译通过则 `sys.exit(2)` 报
"broken act compiled cleanly (this is wrong)"；⑥ `finally` 删除临时文件。

配套的每不变量夹具形态：构造只违反一条规则的最小 spec，断言
`any(e.startswith("N3:"))` / `("N4:")` / `("C4:")` …，每条不变量一个 canary，
并且都配一个"接受合法形态"的对照测试，防止检查靠"拒绝一切"通过。

ADR-0206 §5.7 E8 是这条的通则："删除配置、绕过节点、修改参数、直接调工具、用过期 approval、
跨租户读、超预算调用——必须失败……缺少任一条即视为覆盖不成立"；§9.1 canary-G 把它变成 CI 门禁。

**落点与成本。** 这是本文里性价比最高的一条：不改生产架构，只加测试。
采用 §4.1 时应当同 PR 落地，否则新校验器和旧的一样无法证明自己在工作。

### 4.14 跨观测边界的端口值摘要（原型：已接线）

**问题。** 生产把活的业务 DTO 写进 `PortRegistry`，再为事实面序列化，其中 `_json_safe`
把任何不可序列化的东西**降级成 `repr(value)`**。结果是 `visit_end` 记录里可能出现
`"<ForkedTools object at 0x…>"` 而那里本该是工具列表，且无法判断两次 run 看到的是不是同一份输入。
ADR-0206 §5.7 E7 的反向溯源需要每个端口值有一个内容地址。

**机制（窄且不侵入的形式）。** **不要**把端口值包进 `Artifact`（§5 C-6）。在已经存在的那一个
接缝上，在值旁边计算并记录内容摘要：

- `digest = canonical_digest(canonical_json(value))`，直接复用生产已有的
  `lca/contracts/observability/canonical_digest.py`（`declarative_plan_hash` 已在用）；
  不可规范化时退到 `sha256(repr(value))`。注意 §2.1 的 `validate_default=True` 教训。
- 在 `GraphObservation` 里按端口记录 `short_id = digest[:12]`
  （一个与 `inputs`/`outputs` 并列的 `digests: tuple[tuple[str,str],...]`），`VisitRecord` 同理。
- 于是边点火事件带上摘要，"哪些字节过了这条边"可以从 journal 回答而不必保留字节本身，
  两次 run 可以按摘要比对。
- `schema_ref`（每个载体一个便宜、可 grep 的出处字符串）作为**元数据**保留即可，
  不要连带引入无类型 `content` 包装。

**落点与成本。** 观察面改动，不碰控制面。与 §4.9 的 `subgraph_path` 合起来才构成
可反查的谱系键。

## 5. 反模式：不要复制

| # | 原型做了什么 | 为什么错 |
|---|---|---|
| **C-1** | **缺输入时静默用空载体兜底。** `_run_node` 用一个共享的 `Artifact(TEXT,"")` 哨兵填补缺失端口，再靠身份比较回落到 `_initial` 命名空间。上游从未点火的节点照样跑，跑在空字符串上。`Edge.required` 在 schema 里，从未被强制。 | AGENTS.md §4 禁止"隐式 fallback 掩盖契约缺失"。原型自己的组合法律写着相反的结论（"缺 required IN 在运行时仍缺 = 解释器 bug，编译期应已失败"）。生产这里是对的：`NodeInput.require` 抛 `NodeSchemaError` |
| **C-2** | **环被调度而不是被拒绝。** Kahn 之后把残余入度 > 0 的节点追加成一层。环图"编译成功"，环上每个节点按字母序各跑一次。 | §1 优先级"不变量与契约正确"；C8 确定性；C9 幂等/重入。生产的 `SubgraphCycleError`（PG-007-cycle）是正确形状 |
| **C-3** | **未知枚举值默认而不报错。** `_to_region` 返回 `DIGEST`、`_to_edge_kind` 返回 `DATA`、`_to_error_route` 返回 `FAIL`。`kind: projeck` 这种拼写错误静默变成 data 边。 | §4 同条；C13"无 Contract 跨边界 = fail-loud"。注意 Pydantic 模型本身是 `extra="forbid"` 的——是 loader 手写的强制转换把它们废掉了。教训：边界上的手写 coercion 会绕过下游的 typed 校验 |
| **C-4** | **静默空转的校验。** N1、N2、C2-emits、C15 都以 `try: from agent_lab.nodes.base import NodeRegistry / except ImportError: return []` 开头。PR-D 删掉 `agent_lab/nodes/` 后，四条不变量变成恒真，没有任何东西报告这件事。 | §4 禁止隐式 fallback；§6"只有退出码为 0 的命令才能写为『通过』"——同一条纪律适用于检查本身：**跑不起来的检查必须失败，不能算通过**。采用 §4.1 时，factory 解析不到必须是错误 |
| **C-5** | **模块级可变全局注册表 + 反射式工人发现。** `_LAB_HOOKS: dict[str, Any] = {}` 由 `load_all()` 导入约 96 个硬编码模块路径填充；`discover_worker` 取"本模块里第一个名字与包 basename 匹配的 keyword-only 函数"；元数据从**模块 docstring** 解析（且在两处重复实现）。`invoke.py` 先查 `factory`，查不到再查 `f"lab.{factory}"`。 | §4 禁止"用动态 import、全局注册、反射字符串或 context 属性绕过 import 边界"——这一条同时踩了四种。也违反 C13 D1（定义点无法静态回答）与 C8（解析结果依赖 import 顺序与文件系统扫描）。生产的 `NodeExecutor.semantic_name` + `FactoryResolver` + `@plugin` manifest 是正确形式：显式、typed、可静态 grep |
| **C-6** | **与 typed 业务 DTO 平行的第二套数据模型。** `Artifact{kind, content: Any, schema_ref, digest}`，`content` 是无类型袋子，外加 `_dataclass_to_dict` 递归把工人返回的任何东西压平再重新包成 `Artifact(FACT, {...})` 或 `{"value": v}`。 | §1.5"一个概念一个抽象"；C13（每个边界一个 typed Contract，`content: Any` 就是没有 Contract）。生产选了相反方向并写明了理由：`PortName` Literal + typed DTO + `CloseOutAdapter` 作为唯一命名桥。**留下摘要（§4.14），丢掉包装** |
| **C-7** | **解释器里用墙上时钟。** `_emit` 直接 `time.time() * 1000.0`。 | C8 确定性："时间/随机/PID/env 通过 seam 注入"。生产把 `clock: Clock` 注入 `PlanInterpreter` 与 `SubgraphStrategy` |
| **C-8** | **第二个 Session / 事件入口。** `event_log.yaml` 把 `Session.append` 与 `Session.snapshot_events` 包成图节点；`_ensure_framework_emitter` 把 `session_log_emitter` 插件插到插件链的 0 位；`ensure_act_runtime` 持有 `global _PUBLISH_TOKEN`；默认构造 `session_id="agent_lab_default"`。 | C3/C4（Session 是 `Session.append` 唯一事实生产者）；§4"业务路径直接写 Journal/Spine/Session 后端"。ADR-0209 §0.1 把这条列为收编必须发生的四个理由之一 |
| **C-9** | **节点代码里的第二个组合根。** `act.execute.body.build_body()` 在调用时构造 `SimpleBody` + `PipelineSafeExecutor` + `InternalTransport`；后来 `act.compose` 作为图节点产出 `body_handle`，但图里仍然带着 `provider_ref: agent_lab.adapters.X:Y` 字符串。 | C5（能力单调，`CommandEnvelope` 是唯一副作用出口）、C10（执行窄门）、§4"绕过 Body 执行副作用"。正确形式是"组合根唯一 = Profile/Bundle → Cordis Context → `ctx.require`"；生产经 `StrategyContext.node_config` + host 构造的 runtime view + `MappingProxyType` 只读包装注入 |
| **C-10** | **编译期插件改写图拓扑。** `ControlSlotsPlugin.before_compile` 改 host 的 `ins`/`outs` 并从 Python 接线表注入 `SubSpecLink`，于是根 YAML 不再是拓扑真值。 | C1/C11 与 §2.3（控制面必须留下可追溯事实，图文件就是那个事实）。团队自己否决并记录了理由（见 §4.8）。**保留守卫，不要保留改写能力** |
| **C-11** | **能改写节点输出的 hook。** `semantic_router` 在边传播前按 `schema_ref` 重写 `outputs`。事后加的 `_apply_output_hooks` 只能靠身份比较**检测并回滚**替换、打一条 warning——用一个运行期守卫去管一个本不该存在的设计。 | C7（控制/观察分离）、§2.3"观察面不得触发控制面副作用"。生产靠构造保证安全：`GraphObserver.observe(event) -> None`。**不要先加可变 hook 再去管它** |
| **C-12** | **不变量编号漂移。** `validate.py` 把端口声明与方向检查标为 `C6`，而 ADR-0206 的 C6 是**单写**（原型从不检查）。它的 `C1` 是"存在一条边"，不是 ADR-0206 的可达性闭合。它的 `C2/C3` 是字符串启发式 `"receipt" in target.outs`。读者无法把一条错误消息映射回 ADR 表。 | C13 D2（约束可追溯）与 §1.5"名字承载职责"。采用 §4.1 / §4.3 时沿用生产已有的 `PG-00x` 错误码空间（ADR-0217/0218/0219 一直在一致地扩展它），不要复活 C 编号 |
| **C-13** | **死 schema 面。** `parallelism`、`Edge.required`、`EdgeKind.EFFECT`、`EdgeKind.CONTROL`、`InfoGrant.mode`、`discard_sink`、`Port`、`PortTag`、`Joiner`、`Schedule`、`_declared_sub_spec_inputs`、`bindings` 全部被解析或定义却无消费者；`walk_sub_specs` 被硬编码的 `registry=None` 废掉——公共包装器永远只返回 `[root]`，而 `validate_subgraph_with_profile` 以为自己遍历了整棵树，其实没有。没有一份出厂 YAML 用到 `grants` / `borrow` / `effect` / `control` / `on_error` / `discard_sink`。 | §1.5/§5"每个新依赖、抽象、配置项必有 owner + delete-when，无 owner = 永久债"；§4"离开前死代码/死 import 已清"；ADR-0217 §2 D5"无 D5 = 摆设字段，禁止入 schema"。生产严格执行 D5——这正是 `BundleGraphNode.inputs/outputs` 被删掉而不是"留着以后用"的原因 |
| **C-14** | **无界子图递归。** `_run_subgraph` 递归时既无深度计数器也无 plan_ref 在栈检查，且每次进入都重新 `compile()`，于是还是二次的。 | C9（幂等/重入边界必须定义）。生产的 `max_depth=4` 与 `SubgraphDepthExceededError` / `SubgraphCycleError` 是对的，采用那个 |
| **C-15** | **自己那套密钥加载 bootstrap。** `run._bootstrap()` 在 `except Exception: pass` 里调 `dotenv.load_dotenv(<repo>/.env)`，README 把 `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` 记成由图直接读 env。 | §3 扩展路径"密钥只能经 Profile `{from_env: …}` 进入；插件不得自行读取 `os.environ`"；§4 env 三层白名单。双挂 note 早已为桥接路径禁止过这件事，独立 CLI 违反了自己的规则 |
| **C-16** | **断言代码并不具备的行为的过期测试。** `test_error_routing.py` 断言被路由的工人不会执行，而运行器会执行它；另有测试 import 已删除的 `agent_lab.nodes.base` / `agent_lab.adapters.*` / `lca.plugins.lab.internal.worker`。 | §5"每个 bugfix 至少一个回归测试"与 §6 验证矩阵——**无法 import 的测试套件不是门禁**。这是具体证据：原型宣称的验证结果早于那些删除，且此后从未重跑 |

**贯穿性教训。** C-1 / C-3 / C-4 / C-13 / C-16 是同一个根因的五次出现：
schema 与检查的增长快于接线，而"跑不起来"与"通过"在门禁里长得一样。
采用本文任何一条时，先采用 §4.13（变异式负面测试），否则无法区分这两者。
