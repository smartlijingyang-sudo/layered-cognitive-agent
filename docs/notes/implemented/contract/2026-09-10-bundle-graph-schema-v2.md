# Agent Note: Bundle Graph Schema v2 — 纯图描述 + factory→plugin 解析

Status: implemented

**关联 ADR:** [ADR-0217](../../../../adr/0217-bundle-graph-schema-v2.md)(同 PR 共生)

## Problem

`bundles/think-steps.yaml` 当前只列 5 个 `phase.think.{shortcut,route,reason,classify,gate}` 的 `entries:`,**不是图**,只承担 plugin 注册职责。`web-standard.yaml` 把 `bundles/think-steps.yaml` 同时塞进 `bundles:`(注册 5 个 plugin)和 `sub_spec_ref.plan_ref`(子图解析),两个用途叠在同一个文件上,触发:

1. **`PG-005: subgraph_resolver returned non-plan value for 'bundles/think-steps.yaml': NoneType`** — 真实运行期触发(`run_f01e7e932a0b` 在 `think.main` 即失败)。`BundleSubgraphResolver._PLAN_REF_PROFILES` 只映射 `bundles/reflect-subgraph.yaml` 一个 fixture,`bundles/think-steps.yaml` 漏配,resolver 返回 None。
2. **图语义缺失** — `entries:` 形态无法表达"节点做什么、按什么顺序、可挂什么子图"这种拓扑语义;**节点之间的流向靠 `phase.topology.standard` 嵌在其它 bundle 里**(如 `declarative-phase-graph.yaml`),5 个 think 步没有自己显式的流向声明。
3. **分层职责错位** — `progress.md` Task 3 Ruling #2 说 "think-steps.yaml 只供 fixture 用,生产 profile 通过 auto-discovery 注册 plugin" — 这是迁就现状的妥协,而不是设计目标。生产 profile 应该只需要图描述,plugin 注册是图框架的职责。

`agent_lab/graphs/think/think.yaml` 已经存在一种"纯图描述 + nodes/edges" 形态,但与生产 kernel 解析路径(`BundleSubgraphResolver` → `compile_declarative_projection`)不接。本 Note 提议**借鉴 agent_lab 的节点字段思路,设计一套自有的、适配生产 kernel 的 bundle 图 schema**,把 graph 描述职责从 `entries:` 抽出来。

**设计原则(职责边界硬约束)**:
- **业务 yaml = 业务层** — 描述业务走向(id / purpose / inputs / outputs / config(图级) / edges),**不出现** `plugin_id` / `$module` / `entries:` / plugin 私有参数
- **图框架 = 运行时层** — 读 yaml 字段做事、解析 factory 到 plugin、驱动节点执行、维护图状态、emit 观察面事件
- **业务不懂图框架** — yaml 永远不知道 plugin 长什么样;plugin 重命名 / 命名空间调整 / 拆分合并都不影响 yaml
- **图框架不动业务** — 框架不把自己的内部状态塞回 yaml;plugin 实例化后,运行时配置走 plugin 自己的入口
- **每个 yaml 字段都被框架读、做事,不存在摆设字段** — 无消费者 = 禁止入 schema

## Proposal

(本节已折叠入 ## Decision;此处保留章节以维持 Note 模板结构。)

## Decision

本节描述 **当前已落地** 的真实状态(将来时 → 现在时)。

### 1. `bundles/think.yaml` 是 think 子图唯一纯图描述源

`bundles/think.yaml` 含 5 节点 + 5 边的图描述,`factory` 字段写业务语义名(`think.shortcut` / `think.route` / `think.reason` / `think.classify` / `think.gate`)。**不出现** `plugin_id` / `$module` / `entries:`。每个字段都被 framework 消费(D5 列见 [ADR-0217 §2](../../../../adr/0217-bundle-graph-schema-v2.md))。

### 2. `bundles/think-cordis.yaml` 专管 think 5 步 plugin 注册

为遵守"yaml 不写 plugin 注册"的职责边界,把 plugin 注册职责从 `think.yaml` 抽到独立的 `bundles/think-cordis.yaml`(entries 形态)。`web-standard.yaml` 与 `think-subgraph-dev.yaml` 同时引用两者。**职责分离**:
- `think.yaml`:图描述
- `think-cordis.yaml`:plugin 注册

### 3. `BundleGraphSpec` DTO 三个 dataclass

[contracts/protocols/declarative/declarative_1/bundle_graph.py](../../../../contracts/protocols/declarative/declarative_1/bundle_graph.py) 定义 `BundleGraphNode` / `BundleGraphEdge` / `BundleGraphSpec`,`dataclass(frozen=True, slots=True)`,字段校验在 `__post_init__`,PG-005-bundle-graph 错误码。`FactoryResolutionError` PG-005-factory 错误码。

### 4. `NodeExecutor` 协议(think 子图专用)

[contracts/protocols/declarative/declarative_1/node_executor.py](../../../../contracts/protocols/declarative/declarative_1/node_executor.py) 定义 `NodeContext` / `NodeInput` / `NodeOutput` / `NodeExecutor(Protocol)`。Plugin 不感知 phase、不感知 graph,只接 `port_values` 字典。`@runtime_checkable`,duck typing 可直接 `isinstance(_, NodeExecutor)`。

### 5. `FactoryRegistry` 三级规则

[contracts/protocols/declarative/declarative_1/factory_resolver.py](../../../../contracts/protocols/declarative/declarative_1/factory_resolver.py) 提供 `FactoryRegistry`:
- 规则 1:`(semantic_name, region)` 二元组精确匹配
- 规则 2:`(semantic_name, None)` 兜底匹配
- fail-loud:`FactoryResolutionError`(PG-005-factory),**不静默 fallback**

进程级单例 `get_default_registry()`,plugin 的 `setup()` 里调用 `register(executor, semantic_name=..., region=...)`。

### 6. `BundleSubgraphResolver` 双路径

[harness/declarative/compile/subgraph_resolver.py](../../../../harness/declarative/compile/subgraph_resolver.py) 扩展 `_is_bundle_graph_v2` sniff:
- `_PLAN_REF_PROFILES` 命中 → 走 fixture profile(legacy,reflect-subgraph 用)
- 文件存在 + 顶层含 `nodes:` → 走 v2 新路径:`_load_bundle_graph_spec` → `_project_to_phase_graph` → `_wrap_compiled_run_plan`

`_wrap_compiled_run_plan` 为兼容 GraphAssembler 喂入最小合法 `PhaseBinding` + `CapabilityPlan` + `ValidationReport` + `PlanProvenance`(interpreter 内部消费 contract 不变)。

### 7. 5 个 think plugin 双注册

`lca/plugins/think/{shortcut,route,reason,classify,gate}/plugin.py` 每个 plugin:
- 老 `execute(ctx, inp) -> PhaseResult` 方法保留,`payload=ThinkSubgraphCarry` 兼容老 consumer 与 17 个老测试
- 新 `node_execute(ctx, inp) -> NodeOutput` 方法,`semantic_name` 属性
- `setup()` 双注册:`ctx.provide(cordis)` + `get_default_registry().register(NodeExecutor)`

### 8. 删除 `bundles/think-steps.yaml`(COMPAT shim 不留)

同 PR 删除。无 `_PLAN_REF_PROFILES` 加 `bundles/think-steps.yaml` 映射(走 v2 路径),无兼容 shim。`bundles/think.yaml` 注释里保留一行"迁移历史:本文件替换 bundles/think-steps.yaml"作为历史溯源。

### 1. 新增 `bundles/think.yaml`(原 `bundles/think-steps.yaml` 形态替换)

从"5 个 plugin entries" 改为"5 个节点的纯图描述"。**不写 `$module`,不写 `entries:`,不写 plugin_id**;节点实现由框架按 `factory` 业务语义名解析到 `NodeExecutor`(think 子图专用协议,见 §3a)。形态:

```yaml
# think — think phase subgraph (5 步子图)
# 业务层:只声明节点身份、职责、端口、拓扑、图级参数
# 框架层:按 factory 解析到 NodeExecutor;按 inputs/outputs 投影端口;按 edges 驱动
id: think.subgraph
region: phase:think
purpose: think 5 步执行 — shortcut 可 short-circuit,route → reason → classify → gate 收敛

nodes:
  - id: think.shortcut
    region: phase:think
    factory: think.shortcut          # 业务语义名;NodeExecutor.semantic_name
    purpose: 模型能直接给最终决策时短路返回
    inputs: [in_assembled_manifest]
    outputs: [decision]
    config:                            # 仅图级参数,plugin 私有参数走 plugin 自己入口
      confidence_threshold: 0.85
      max_visits: 1

  - id: think.route
    region: phase:think
    factory: think.route
    purpose: 选择路由(skill_route / llm / direct)
    inputs: [in_assembled_manifest]
    outputs: [route_choice]
    config:
      max_visits: 1

  - id: think.reason
    region: phase:think
    factory: think.reason
    purpose: 调 LLM 生成候选 Decision
    inputs: [messages, tools]
    outputs: [response]
    config:
      max_visits: 3                    # reason 可重试 3 次

  - id: think.classify
    region: phase:think
    factory: think.classify
    purpose: 把 response 归类为 Decision
    inputs: [response]
    outputs: [decision]
    config:
      max_visits: 1

  - id: think.gate
    region: phase:think
    factory: think.gate
    purpose: DecisionGate — 决策合规与 gate 收敛
    inputs: [decision, in_state]
    outputs: [enforced_decision, think_signal]
    config:
      max_visits: 8                    # gate 可在多 turn 收敛

edges:
  - from: think.shortcut
    to: think.route
    when: result.payload.shortcut_taken == false
    kind: control
  - from: think.route
    to: think.reason
    when: result.payload.route == "reason"
    kind: control
  - from: think.route
    to: think.classify
    when: result.payload.route == "direct"
    kind: control
  - from: think.reason
    to: think.classify
    when: true
    kind: control
  - from: think.classify
    to: think.gate
    when: true
    kind: control
  # terminal: think.gate 直接回 outer graph(binding_edge=think.main),无需显式返回边
```

**对照 §0 职责边界硬约束**:
- 不出现 `plugin_id` / `$module` / `entries:` ✓
- `factory: think.shortcut` 是业务语义名,等于 `NodeExecutor.semantic_name` ✓
- `inputs` / `outputs` 是 yaml 声明,框架对齐端口 ✓
- `config` 仅图级参数(`confidence_threshold` 走 think 子图语义、`max_visits` 走图运行时),plugin 私有参数不出现 ✓
- `purpose` 是 yaml 声明,框架写入 trace ✓
- `edges[].when` 是 yaml 声明,interpreter 在 `node.end` 后跑 ✓
- `edges[].kind: control` 默认值,框架解释为走 `when` 判定 ✓

### 2. 新 schema 字段语义(C13 信息血统闭合)

| 字段 | 类型 | 含义 | 来源 |
|---|---|---|---|
| `id` | str | bundle 内唯一 ID;`plan_ref` 用它;写入 `CompiledRunPlan.metadata` 作 trace 标签 | 新 |
| `region` | str | region 标签(对齐 ADR-0210 §6.4 P7 路径);驱动 factory 反查 | 借鉴 agent_lab |
| `factory` | str | **业务语义名**(`think.reason`);框架按规则解析到 `NodeExecutor`(think 子图专用);不出现 plugin_id | 新 |
| `purpose` | str | 节点语义职责描述;写入 `phase_graph.node.start/end` 事件的 `payload.purpose`,作可观测性锚点 | 借鉴 agent_lab |
| `inputs` | tuple[str, ...] | 节点声明性输入端口;非空;框架用作 subgraph 边缘端口对齐 | 借鉴 agent_lab |
| `outputs` | tuple[str, ...] | 节点声明性输出端口;非空;框架用作 subgraph 边缘端口对齐 | 借鉴 agent_lab |
| `config` | dict | 节点级配置;**只放图级参数**(loop 预算 / max_visits / cooldown);不向 plugin 注入 | 既有 `entries[].config` 的位置 |
| `edges[].kind` | enum | `control` (默认) \| `data` (端口数据流,强制配 `from_port`/`to_port`) | 借鉴 agent_lab |
| `edges[].when` | bool-expr | 控制边触发条件(DSL 复用 `phase.edge.standard.when`) | 既有 |
| sub_spec_ref(节点级) | object | 每节点可挂子 spec,递归入口 | 既有 [2026-09-09-phase-node-sub-spec-ref.md](../../implemented/contract/2026-09-09-phase-node-sub-spec-ref.md) |

### 3. factory → NodeExecutor 解析规则(think 子图专用协议)

**`factory` 是业务语义名,不出现 plugin_id。** 框架按以下顺序解析到 `NodeExecutor`(think 子图专用 plugin 协议,见 ADR §3.3)。**任何一级命中即返回;都不命中 fail-loud。**

1. **业务语义名直接匹配 `NodeExecutor.semantic_name`** — 每个 think 子图 plugin 实现 `NodeExecutor` 协议,`semantic_name` 是 protocol 必填属性(如 `think.reason`)。`FactoryResolver` 按 `(semantic_name, region)` 二元组精确匹配。Plugin 改名 / 命名空间调整不影响 yaml。
2. **`region + <phase>.<action>` 反查 think 子图 plugin** — 规则 1 未命中时,框架扫 `region` 下所有 think 子图 plugin,按 `plugin.spec.semantic_phase + plugin.spec.action` 拼成 `<phase>.<action>`,与 factory 字符串相等即命中。`action` 字段由 `Plugin.spec.action` 给出(如 `reason`)。
3. **fail-loud** — 抛 `FactoryResolutionError`(新增,位于 `lca/contracts/exceptions/factory_resolution.py`),`PG-005-factory` 错误码。**不静默 fallback**。

**注意**:perceive / act / reflect / remember / stop 仍用 `PhaseExecutor.execute(context, input) -> PhaseResult` 旧签名,本 ADR **不动**。只有 think 子图的 5 步 plugin 用新的 `NodeExecutor.execute(context: NodeContext, input: NodeInput) -> NodeOutput`(ADR §3.3)。

### 3a. think 子图 plugin 通用化(ADR §3.3 落地细节)

5 个 think 子图 plugin 实现新协议:

```python
# lca/contracts/protocols/declarative/declarative_1/node_executor.py
class NodeContext(Protocol):
    runtime: NodeRuntime        # 框架注入的 LlmResolver / MemoryRead 等(只读)
    budget: NodeBudget          # yaml config 投影:max_visits / cooldown_ms(只读)
    metadata: Mapping[str, Any] # 节点 purpose + subgraph metadata(只读)

class NodeInput(Protocol):
    port_values: Mapping[str, Any]   # {"messages": [...], "tools": [...]}

class NodeOutput(Protocol):
    port_values: Mapping[str, Any]   # {"decision": Decision(...)}
    next_hint: str | None = None     # 可选:节点建议下一节点

class NodeExecutor(Protocol):
    @property
    def semantic_name(self) -> str: ...

    async def execute(self, context: NodeContext, input: NodeInput) -> NodeOutput: ...
```

**plugin 不感知 phase、不感知 graph** — 只接 `NodeInput.port_values` 字典,吐 `NodeOutput.port_values` 字典。框架负责:
- 把 yaml 的 `inputs: [messages, tools]` 投影成 `port_values`
- 把 plugin 输出的 `port_values` 与 yaml 的 `outputs: [decision]` 对齐校验
- 框架的 `interpreter` 按 `edges[].when` 选下一节点,`NodeOutput.next_hint` 仅是建议

### 4. `BundleSubgraphResolver` 扩展

新增对新 schema 的识别:

```python
def resolve(self, plan_ref: str) -> CompiledRunPlan | None:
    if plan_ref in _PLAN_REF_PROFILES:
        return _compile_subgraph_profile(_PLAN_REF_PROFILES[plan_ref])
    if plan_ref.startswith("bundles/") and plan_ref.endswith(".yaml"):
        return _compile_bundle_graph(plan_ref)  # 新增:解析新 schema
    return None
```

`_compile_bundle_graph` 调用一个新函数 `_compile_bundle_graph_plan(plan_ref)`,流程:
- 读 yaml → 解析为 `BundleGraphSpec`(新 DTO,Pydantic frozen,`extra="forbid"`)
- 对每个 `nodes[].factory` 调 `FactoryResolver.resolve(factory, region)` → 拿到 `plugin_spec`
- 把 `BundleGraphSpec` 投影成 `CognitivePhaseGraphPlan`(既有 Pydantic,填 `nodes`/`edges`)
- `CompiledRunPlan.phase_graph = 投影结果`,走 `PhaseGraphValidator.validate(require_all_semantic_phases=False)`(与现有 subgraph fixture 路径对齐)

### 5. 删除 `bundles/think-steps.yaml`

同 PR 闭环。**不留 compat shim** — AGENTS.md §4 强约束。`_PLAN_REF_PROFILES` 里不加 `bundles/think-steps.yaml` 映射(走新路径),老文件直接删。

### 6. 迁移路径(同 PR)

1. 新 `bundles/think.yaml`(按 §1 形态写)
2. `profiles/web-standard.yaml` 与 `profiles/think-subgraph-dev.yaml`:把 `bundles/think-steps.yaml` 从 `bundles:` 列表移除;`sub_spec_ref.plan_ref` 改成 `bundles/think.yaml`
3. `bundles/declarative-phase-graph.yaml` 第 70 行:`plan_ref: bundles/think-steps.yaml` → `bundles/think.yaml`
4. `lca/application/api/default_context.py:33` 的注释更新
5. 删 `bundles/think-steps.yaml`

### 7. 对其它 subgraph 的影响

`bundles/reflect-subgraph.yaml` 保持现状(entries: 形态),**本 PR 不动**。后续可走另一条 Note 迁移到新 schema,保持 diff 可控。`bundles/think-orchestrator-graph.yaml` 同理,本 PR 不动。

## Alternatives considered

### Why not 维持 entries: 形态 + 在 _PLAN_REF_PROFILES 加映射?

保留 think-steps.yaml,补 `profiles/fixtures/think-subgraph-compile.yaml` 一个 4 行 fixture,在 `_PLAN_REF_PROFILES` 加 `"bundles/think-steps.yaml": "profiles/fixtures/think-subgraph-compile.yaml"`。修 PG-005 但不升级 schema。

**否决**:这是修 bug,不是修设计。entries: 形态本身就不能表达节点顺序(5 个 plugin 之间没边、没节点身份、没 ports),而 think 5 步恰好是"顺序+条件分支"语义最强的场景。维持现状等于把"为什么 think 5 步要按这个顺序"的知识永远埋在 5 个独立 plugin 的 `setup()` 里;新增/调换一个 step 就要改 5 个文件,违反 C6 最小化。

### Why not 直接接 agent_lab schema?

把 `agent_lab/graphs/think/think.yaml` 的 nodes/edges 形态直接搬过来,`BundleSubgraphResolver` 调 `agent_lab.profile_loader.build_region_only_phase_graph` 把 agent_lab plan 转成 kernel plan。

**否决**:agent_lab schema 与生产 kernel 有 3 处不可对齐的分歧:
1. agent_lab 的 `factory: think.expose` 没有 `@plugin(...)` 装饰器与之对应,需要新加 `lca.plugins.think.expose` plugin + `phase.think.expose` capability key(改 PluginSpec 闭集)
2. agent_lab 的 `edges[].from/to` 是 port-level(节点内端口),kernel `PhaseEdge` 是 node-level,转换需要补 port-aware edge schema(超出本次改动范围)
3. agent_lab 的 `region: phase:think` 是 ADR-0210 P7 路径专属字段;接进来等于强制生产 profile 走 P7,与 ADR-0075 legacy 路径冲突

借鉴节点字段思路(`region`/`factory`/`inputs`/`outputs`),但 schema 独立定义 + 走 `compile_declarative_projection` 而不是 agent_lab 解析路径。

### Why not 把"图描述"职责从 bundle 抽到独立 layer(类似 DAG 文件)?

引入 `graphs/` 顶层目录,bundle 只放 plugin 注册,图描述全部进 `graphs/think.yaml`,profile 同时引用 `bundles:` 和 `graphs:`。

**否决**:增加新的"图文件"目录等于引入第三个 SSOT(profile / bundle / graph),与 ADR-0195 §4 SSOT 矩阵冲突。bundle 本身就是 phase_graph 编译的输入单元,把图描述职责放在 bundle 内最自然(同一个 plan_ref 解析就能同时拿到 plugin + 拓扑,不需要双源)。

## Verification

(原 Acceptance criteria — 见下方现状。)

1. ✅ `BundleSubgraphResolver.resolve("bundles/think.yaml")` 返回 `CompiledRunPlan`,`phase_graph.nodes` 长度为 5,`phase_graph.edges` 长度为 5。
2. ⏳ `web-standard.yaml` / `think-subgraph-dev.yaml` 通过 `./scripts/lca-ops inspect-tree` — 待 8 步(interpreter v2 友好分支)落地后跑完整 inspect-tree。Plugin 注册数与改动前一致(5 个 `phase.think.*` step plugin + 既有 phase executor)已通过 setup 双注册验证。
3. ⏳ `run_f01e7e932a0b` 同语义新 run 端到端跑通六语义 `perceive → think → act → reflect → remember → stop`,broken_hop=None — 已在 `run_7559c96beacd` 看到 total_steps=2, totals_phases=2, fold_hits=2,**走进 think 节点内部**;broken_hop=H3 待 8 步(interpreter v2 友好分支)闭环。
4. ✅ `PhaseGraphValidator` 在新 schema 上跑通;**非命中 factory 抛 `FactoryResolutionError`**(PG-005-factory),已在契约行为测试中验证。
5. ✅ `_PLAN_REF_PROFILES` 不再加 `bundles/think-steps.yaml` 映射(走新解析路径);`bundles/think-steps.yaml` 已删除;`grep "think-steps" profiles/ bundles/ lca/` 只剩 `bundles/think.yaml` 注释里的历史溯源一行。
6. ✅ ADR-0217 升 Accepted,本 Note 升 implemented/。

## Testing

- `tests/think/test_{shortcut,route,reason,classify,gate}_phase_plugin.py`:17 个老测试全过(plugin 双协议签名 + payload=ThinkSubgraphCarry 兼容)
- `tests/harness/graph/execute/test_interpreter_subgraph.py` + `tests/contracts/test_subgraph_reference_contract.py` + `tests/declarative/test_phase_graph.py`:35 个测试全过(subgraph 既有契约不退化)
- 端到端契约行为验证脚本(本 Note 实施时随附):
  - `BundleGraphSpec` DTO 校验(节点/边合法 + 缺失 target → PG-005-bundle-graph)
  - `FactoryRegistry` 命中 / PG-005-factory / 重复注册 / region=None 兜底
  - `NodeExecutor` protocol `@runtime_checkable` + `isinstance` 通过
  - `BundleSubgraphResolver._is_bundle_graph_v2` sniff:legacy reflect + v2 think + nonexistent 路径分流

## Consequences

(原 Risks — 见下方现状记录。)

- **R1:factory 命名冲突。** 业务语义名不与 plugin_id 冲突:yaml 不写 plugin_id,plugin_id 是框架内部命名空间。**已通过"业务不懂图框架"边界阻断**(ADR-0217 §0 职责边界硬约束)。
- **R2:对 plugin 注册的隐式假设。** 5 个 think plugin 已在 setup() 双注册;非 think 子图 plugin 不在本 ADR 范围,继续走老 PhaseExecutor。
- **R3:对 reflect-subgraph.yaml 的连锁反应。** 本 ADR 明确不动 reflect-subgraph;`Bundles/reflect-subgraph.yaml` 仍走 `_PLAN_REF_PROFILES` legacy 路径。后续独立 ADR 跟进。
- **R4:迁移期双写法窗口。** `bundles/think-steps.yaml` 已删,无窗口。`kernel-restart` 已经是常规操作。
