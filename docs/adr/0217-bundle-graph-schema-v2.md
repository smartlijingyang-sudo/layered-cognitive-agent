# ADR-0217: Bundle Graph Schema v2 — 纯图描述 + factory→plugin 解析

> **状态:** **Accepted — 2026-09-10**(实施见本 PR commits)
>
> **一句话**: 把 bundle 内的"图描述"职责从 `entries: [{id, name, $module, config}]` 抽离,改为 `nodes: [{id, region, factory, purpose, inputs, outputs, config}]` + `edges: [{from, to, kind, when}]` 的纯图形态;`factory` 字符串由新增的 `FactoryResolver` 按 plugin_id 优先 / region+phase 反查 / fail-loud 三级规则解析到既有 PHASE_EXECUTOR plugin。原 `bundles/think-steps.yaml` 形态替换为 `bundles/think.yaml`,同 PR 删除不留 compat shim,闭环 PG-005 子图解析漏配。
>
> **触发 run:** `run_f01e7e932a0b` — `PG-005: subgraph_resolver returned non-plan value for 'bundles/think-steps.yaml': NoneType`,think.main 节点即失败,24 个事件里 0 个 think/act/llm 事件。
>
> **Agent Note:** [notes/proposed/contract/2026-09-10-bundle-graph-schema-v2.md](../notes/proposed/contract/2026-09-10-bundle-graph-schema-v2.md)
>
> **Review:** 待评审。
>
> **Accepted 闸门:**
> 1. §3 新 schema 字段在 `BundleGraphSpec` Pydantic frozen + `extra="forbid"`;`FactoryResolver` 三级解析规则 + `FactoryResolutionError` 错误码在 contracts 闭集
> 2. §4 `BundleSubgraphResolver.resolve("bundles/think.yaml")` 返回 `CompiledRunPlan.phase_graph` 含 5 节点 + ≥ 4 控制边;走 `PhaseGraphValidator.validate(require_all_semantic_phases=False)`
> 3. §5 `web-standard.yaml` + `think-subgraph-dev.yaml` 通过 `./scripts/lca-ops inspect-tree`,plugin 注册数与改动前一致
> 4. §6 端到端:`run_f01e7e932a0b` 或同语义新 run 重跑,六语义 `perceive → think → act → reflect → remember → stop` 全走通,broken_hop=None
> 5. §7 `Bundles/think-steps.yaml` 删除,`grep -rl "think-steps" profiles/ bundles/ lca/` 仅剩注释级残留;`_PLAN_REF_PROFILES` 不加 `bundles/think-steps.yaml` 映射
> 6. §8 reflect-subgraph / think-orchestrator-graph 维持现状,本 ADR 范围明确不含;`tests/contracts/test_subgraph_reference_contract.py` + `tests/harness/graph/execute/test_interpreter_subgraph.py` + `tests/declarative/test_phase_graph.py` 既有用例全过

**编号:** 0217

**关系:**
- **Builds on**: ADR-0075 (declarative phase graph SSOT) · ADR-0199 (cognitive plugin convergence) · ADR-0210 (stage closure migration P7, P7 region-tag 作 region 字段来源) · [notes/implemented/contract/2026-09-09-phase-node-sub-spec-ref.md](../notes/implemented/contract/2026-09-09-phase-node-sub-spec-ref.md) (节点级 `sub_spec_ref` 作 sub_spec_ref 字段来源)
- **Refines**: `BundleSubgraphResolver`(从单 fixture 映射扩展为新 schema 解析) · `compile_declarative_projection`(新增 factory→plugin 解析层)
- **Supersedes**: 无
- **Reject**: 「在 `_PLAN_REF_PROFILES` 加 `bundles/think-steps.yaml` 映射」(只修 PG-005 不升级 schema,保留双职责错位);「直接搬 agent_lab schema」(违反 ADR-0210 P7 路径边界 + agent_lab port-level edge 与 PhaseEdge node-level 不对齐);「引入独立 graphs/ 目录」(违反 ADR-0195 §4 SSOT 矩阵,引入第三 SSOT)

---

## 0. 第一性原理: 问题本质

`bundles/think-steps.yaml` 同时承担两个互斥的职责:**plugin 注册**(生产 profile `bundles:` 列表加载时塞 5 个 plugin)和**子图拓扑**(被 `sub_spec_ref.plan_ref` 引用,期望 resolver 返回含 `phase_graph` 的 `CompiledRunPlan`)。这两个职责的实现路径不同:

- plugin 注册 → `entries:` 形态 → `compile_declarative_projection` 直接吞
- 子图拓扑 → 需要 `phase_graph` + `bindings` + `edges` → 走 `BundleSubgraphResolver` → `_compile_subgraph_profile(relative_profile)` → 返回 `CompiledRunPlan`

只有当 bundle 同时满足两套形态时,两个职责才能共存。`bundles/think-steps.yaml` 只有 entries:,没有 phase_graph,所以 resolver 返回 None,触发 PG-005。

这条 PG-005 不是 bug,是**设计冲突**暴露:想让 `think-steps.yaml` 同时是 plugin 注册表和子图拓扑,语义上做不到。**正确的修法不是给 resolver 打补丁,是拆开两个职责**:

- plugin 注册 → 留在生产 profile 的 `bundles:` 列表(或完全交给 auto-discovery,本次保留显式列)
- 子图拓扑 → 新的 bundle,只描述图,不描述 plugin

拆分后,新 bundle 内的"节点"对应到 plugin,需要一种从"业务节点身份"到"plugin 实现"的解析规则 — 这就是 `factory` 字段。

**职责边界(沿用至全文)**:本 ADR 把 yaml 与运行时拆成两个不相交的层:

| 层 | 写什么 | 不写什么 | 持有 |
|---|---|---|---|
| 业务 yaml(图声明) | 节点 id / purpose / inputs / outputs / config(图级参数) / edges | plugin_id / $module / entries / plugin 私有参数 | 人类作者 |
| 图框架(运行时) | PluginSpec / `semantic_name` / region+phase 反查 / D5 字段消费 | — | 框架代码 |

**「业务不懂图框架」**:yaml 永远不知道 plugin 长什么样。**「图框架不动业务」**:框架读 yaml 字段做事,但不把自己的内部状态塞回 yaml。两层之间唯一的契约是 `factory: <业务语义名>`(如 `think.reason`),其余全部是单向消费 — 框架消费 yaml 字段(yaml 不知道消费结果),plugin 消费 framework 注入的 runtime context(framework 不知道 plugin 内部状态)。

## 1. 决定

| 维度 | 现状 | 新方案 |
|---|---|---|
| bundle 顶层形态 | `entries: [{id, name, $module, config}]` | `nodes: [{id, region, factory, purpose, inputs, outputs, config}]` + `edges: [{from, to, kind, when}]` + 可选 `id`/`region`/`purpose` |
| 节点身份与实现的关系 | `entries[].id` 同时承担 plugin_id | `nodes[].factory` 写**业务语义名**(`think.reason`),`nodes[].id` 写**拓扑身份**(`think.shortcut`),二者解耦;`plugin_id` / `$module` 不出现在 yaml |
| 节点顺序 | 隐式(plugin 注册顺序) | 显式 `edges[]` 控制流;`edges[].when` 表达条件分支 |
| 节点内部细节 | `entries[].config` 透传到 plugin | `nodes[].config` 仅放图级参数(loop 预算 / max_visits / cooldown),plugin 私有配置走 plugin 自己的入口 |
| 节点级配置 | `entries[].config` | `nodes[].config`(同语义,位置换) |
| 嵌套子图 | 边级 `subgraph_ref`(全局) | 节点级 `sub_spec_ref`(per-node,既有 note) |
| 解析路径 | `compile_declarative_projection` 直接吞 entries | 新 `BundleGraphSpec` Pydantic + `FactoryResolver` 三级规则 + 投影到 `CognitivePhaseGraphPlan` |
| 错误语义 | 静默 fallback | fail-loud(`FactoryResolutionError`,PG-005-factory) |

## 2. Schema 字段(C13 信息血统闭合)

**职责边界硬约束(本 ADR 的设计意图):**
- 图 yaml = **业务层**,描述业务走向(id / purpose / inputs / outputs / edges),不出现任何 plugin 注册细节
- 图框架 = **运行时层**,负责读 yaml 字段、驱动 plugin 执行、维护图状态、emit 观察面事件
- **业务不懂图框架** — yaml 不出现 `plugin_id` / `$module` / `entries:`;plugin 重命名 / 命名空间调整 / 拆分合并都不影响 yaml
- **图框架不动业务** — 框架不向 plugin 注入 yaml 字段;plugin 实例化后,它的运行时配置走 plugin 自己的入口(`Plugin.declare` 或 setup hook),yaml 只描述图级参数

**每个字段都"被读、做事",不存在摆设。** 字段表新增 D5 = "框架读这个字段做什么" 一栏;无 D5 = 摆设字段,禁止入 schema。

| 字段 | D1 定义点 | D2 约束 | D3 转换链 | D4 消费者 | D5 框架读它做什么 |
|---|---|---|---|---|---|
| `id` | `BundleGraphSpec.id: str` | non-empty,bundle 内唯一 | yaml → BundleGraphSpec → CompiledRunPlan.metadata | `BundleSubgraphResolver._compile_bundle_graph` | 用作 `plan_ref` 的解析键;写入 `CompiledRunPlan.metadata` 用于 trace 标签 |
| `region` | `BundleGraphSpec.region: str` | 形如 `phase:<semantic>` 或 `<bare-enum>`(对齐 ADR-0210 §6.4) | yaml → region_label_for_node → SemanticPhase 推断 | `FactoryResolver` 规则 2 | 子图整体的 region 标签;驱动 `FactoryResolver` 反查 plugin 时提供语义上下文 |
| `nodes[].id` | `BundleGraphNode.id: str` | bundle 内唯一;不在 outer graph 中(self-reference 校验 PG-004) | yaml → BundleGraphSpec → CognitivePhaseGraphPlan.nodes[].id | `PhaseGraphValidator` PG-004 | 边的 source/target 锚点;interpreter 运行时作为节点的寻址 key |
| `nodes[].factory` | `BundleGraphNode.factory: str` | non-empty;**业务语义名**(`think.reason`),**不出现 plugin_id**;必须等于某个 `NodeExecutor.semantic_name` | yaml → `FactoryResolver.resolve(factory, region)` → `NodeExecutor` 实例 | `GraphAssembler` 节点 binding | 按 §3.1 三级规则解析到 `NodeExecutor` 实例(think 子图专用协议,见 §3.3);驱动节点实例化 |
| `nodes[].purpose` | `BundleGraphNode.purpose: str` | non-empty;节点语义职责描述 | yaml → BundleGraphSpec → `CompiledRunPlan.metadata.node_purpose[id]` | Trace 观察面 + 红蓝演练 prompt 摘要 | 写入每条 `phase_graph.node.start/end` 事件的 `payload.purpose`,作可观测性锚点 |
| `nodes[].inputs` | `BundleGraphNode.inputs: tuple[str, ...]` | non-empty;节点声明性输入端口 | yaml → BundleGraphSpec → `PhaseNode.inputs` + `CompiledRunPlan.metadata` | subgraph 边缘端口对齐(`sub_spec_ref.entry_node.inputs` ⊆ outer `sub_spec_ref.outputs`) | 子图作为整体被 outer 引用时,做 outer edge 与 inner 节点的端口契约校验 |
| `nodes[].outputs` | `BundleGraphNode.outputs: tuple[str, ...]` | non-empty;节点声明性输出端口 | yaml → BundleGraphSpec → `PhaseNode.outputs` + `CompiledRunPlan.metadata` | 同 `inputs`(反方向) | 同 `inputs`(反方向) |
| `nodes[].config` | `BundleGraphNode.config: dict[str, Any]` | non-empty 字典;**只放图级参数**(loop 预算、节点访问上限、节点级 cooldown),**不向 plugin 注入** | yaml → BundleGraphSpec → `PhaseNode.budget` / `PhaseNode.max_visits` 等图级字段 | `PhaseGraphValidator` + Interpreter | 投影为图运行时参数(非 plugin 注入);plugin 自己的运行时配置走 plugin 自己的入口 |
| `nodes[].sub_spec_ref` | `BundleGraphNode.sub_spec_ref: SubgraphReference \| None` | 既有契约(见 [phase-node-sub-spec-ref.md](../notes/implemented/contract/2026-09-09-phase-node-sub-spec-ref.md)) | 透传 | Interpreter 节点递归 | 节点嵌套子图的入口引用 |
| `edges[].from` | `BundleGraphEdge.source: str` | 必须命中 `nodes[].id`(PG-004 校验) | yaml → BundleGraphEdge → PhaseEdge.source | `PhaseGraphValidator` PG-004 | 控制流/数据流的起点锚点 |
| `edges[].to` | `BundleGraphEdge.target: str` | 必须命中 `nodes[].id`(PG-004 校验) | yaml → BundleGraphEdge → PhaseEdge.target | `PhaseGraphValidator` PG-004 | 控制流/数据流的终点锚点 |
| `edges[].kind` | `BundleGraphEdge.kind: Literal["control", "data"]` | default `control`;`data` 边强制要求 `from_port` + `to_port` | yaml → BundleGraphEdge → PhaseEdge + Interpreter 路由分支 | Interpreter(本期读 `control`;`data` 投影但不消费) | 框架按 kind 决定边解释策略:`control` 走 `when` 判定;`data` 走端口对齐 |
| `edges[].when` | `BundleGraphEdge.when: str` | bool-expr(DSL 复用 `phase.edge.standard.when`) | yaml → BundleGraphEdge → PhaseEdge.when | Interpreter 触发判定 | 框架在 `phase_graph.node.end` 事件后用 `when` 决定下一节点 |

所有字段 `extra="forbid"` 。Pydantic frozen。

**D5 列为硬约束** — 每个 yaml 字段必须在 `interpreter` / `validator` / `trace` 中有**至少一个**消费点;新增字段必须填 D5。无 D5 = 摆设字段,禁止入 schema。

## 3. Decision

**§3.0 职责边界硬约束(沿用 §2 设计意图,可执行化)**

| 边界 | 业务层(yaml)允许 | 业务层(yaml)禁止 | 框架层(运行时)负责 |
|---|---|---|---|
| 业务写 plugin 实现细节 | `factory: <业务语义名>`(如 `think.reason`) | 写 `plugin_id`、`$module`、`entries:`、plugin 装饰器全名 | 持有 plugin registry,按 factory 解析到 plugin |
| 业务写 plugin 内部配置 | — | 写 `phase.think.reason.temperature` 这类 plugin 私有参数 | plugin 私有参数走 plugin 自己的入口(setup hook / `Plugin.declare`) |
| 业务写图级参数 | `config: { max_visits: 8, cooldown_ms: 200 }` | 写 framework 内部开关(如 `__skip_validate`) | 把 `config` 投影为 `PhaseNode.budget` / `PhaseNode.max_visits` 等图级字段 |
| 业务写端口语义 | `inputs: [messages, tools]` / `outputs: [decision]` | — | subgraph 边缘端口对齐校验;interpreter 路由选择 |
| 业务写边逻辑 | `edges[].when: <bool-expr>`(复用 phase.edge.standard DSL) | — | interpreter 在 `phase_graph.node.end` 事件后跑 `when` |

**违反任一边界 = reject PR。**

### §3.1 FactoryResolver 三级规则(全部基于业务语义名,**不读 plugin_id**)

`factory` 是业务语义名(如 `think.reason`),框架按以下顺序解析到 `NodeExecutor`(think 子图专用,见 §3.3)。**任何一级命中即返回;都不命中 fail-loud。**

1. **业务语义名直接匹配 `NodeExecutor.semantic_name` 属性**(本 ADR 引入) — 每个 think 子图 plugin 实现 `NodeExecutor` 协议,`semantic_name` 是 protocol 必填属性(如 `think.reason`),`FactoryResolver` 按 `(semantic_name, region)` 二元组精确匹配。Plugin 改名 / 命名空间调整不影响 yaml(只要 `semantic_name` 不变)。
2. **`region + <phase>.<action>` 反查 think 子图 plugin** — 若规则 1 未命中,框架扫 `region` 下所有声明 think 适配的 plugin,按 `plugin.spec.semantic_phase + plugin.spec.action` 拼成 `<phase>.<action>`,与 factory 字符串相等即命中。`action` 字段由 `Plugin.spec.action` 给出(如 `reason`)。
3. **fail-loud** — 抛 `FactoryResolutionError`(PG-005-factory 错误码,**不静默 fallback**)。**禁止**默认放行到任何 plugin。

yaml 不出现 `plugin_id` 字符串 = 业务不懂图框架。Plugin 改名 / 拆分 / 合并 → 改 plugin 的 `semantic_name`,不改 yaml。

**§3.1 与 §3.3 关系**:§3.1 解析到 `NodeExecutor` 实例(不是 `PhaseExecutor`)— think 子图的 factory 解析结果是 node 级 protocol,不是 phase 级 protocol。perceive/act/reflect/remember/stop 这套仍走 `PhaseExecutor`(本 ADR 不动)。

### §3.2 其它 Decision

1. **新 schema 文件** `lca/contracts/protocols/declarative/declarative_1/bundle_graph.py` 定义 `BundleGraphSpec` / `BundleGraphNode` / `BundleGraphEdge` / `FactoryResolutionError`。frozen + `extra="forbid"`。`@plugin(...)` 装饰器新增 `semantic_name` 必填参数(在 `lca/contracts/plugins/plugin_spec.py`)。
2. **`FactoryResolver`** `lca/contracts/protocols/declarative/declarative_1/factory_resolver.py` 实现 §3.1 三级解析。
3. **`BundleSubgraphResolver`** `lca/harness/declarative/compile/subgraph_resolver.py` 扩展:`plan_ref` 以 `bundles/` 开头 + 文件存在 + 解析为新 schema,走 `_compile_bundle_graph(plan_ref)` 新路径。`_PLAN_REF_PROFILES` 保留但只装 fixture 形态 bundle(如 `bundles/reflect-subgraph.yaml`),不装走新 schema 的 bundle。
4. **`_compile_bundle_graph`** 流程:读 yaml → `BundleGraphSpec.model_validate` → 对每个 `nodes[].factory` 调 `FactoryResolver.resolve(factory, region)` → 校验 `nodes[].id` 在 `CognitivePhaseGraphPlan` 内唯一 + 无 self-reference → 投影成 `CognitivePhaseGraphPlan` → 走 `PhaseGraphValidator.validate(require_all_semantic_phases=False)` → 包装 `CompiledRunPlan`(同 `_compile_subgraph_fixture`)。
5. **`Bundles/think.yaml`** 新建(按 Note §1 形态)。`bundles/think-steps.yaml` 同 PR 删除。
6. **profile 切换** `profiles/web-standard.yaml` + `profiles/think-subgraph-dev.yaml`:`bundles:` 列表中 `bundles/think-steps.yaml` 移除(`lca/application/api/default_context.py:33` 注释更新);`sub_spec_ref.plan_ref` 改 `bundles/think.yaml`。
7. **`Bundles/declarative-phase-graph.yaml:70`** `plan_ref: bundles/think-steps.yaml` → `bundles/think.yaml`。

### §3.3 think 专用通用化 plugin 协议(只动 think 子图,perceive/act/reflect/remember/stop 不动)

**问题**:现有 `PhaseExecutor.execute(context, input) -> PhaseResult` 签名是 18 个 plugin(6 phase + 12 control)的统一入口。但 think 子图内的 5 步(shortcut/route/reason/classify/gate)是**节点级**(node-level)的图节点,职责是"按 yaml 声明的 inputs 拿数据、按 outputs 吐结果",**与 control plugin 的"对 phase 决策拦截 / 收口"语义不同**。两类 plugin 强行共用一个 Protocol,职责边界模糊。

**新协议 `NodeExecutor`**(`lca/contracts/protocols/declarative/declarative_1/node_executor.py`),**只服务 think 子图**;perceive/act/reflect/remember/stop 仍用 `PhaseExecutor`,本 ADR **不动**。

```python
class NodeContext(Protocol):
    """节点级执行上下文:框架注入,不暴露 framework 内部状态。"""
    runtime: NodeRuntime          # 框架提供的执行器(LlmResolver / MemoryRead / 等)
    budget: NodeBudget            # yaml config 投影:max_visits / cooldown_ms
    metadata: Mapping[str, Any]   # 节点 purpose + subgraph metadata(只读)

class NodeInput(Protocol):
    """节点级输入:严格对应 yaml 声明的 inputs 端口。"""
    port_values: Mapping[str, Any]   # {"messages": [...], "tools": [...]}

class NodeOutput(Protocol):
    """节点级输出:严格对应 yaml 声明的 outputs 端口。"""
    port_values: Mapping[str, Any]   # {"decision": Decision(...)}
    next_hint: str | None = None     # 可选:节点建议下一节点(框架优先按 edges[].when 走)

class NodeExecutor(Protocol):
    """think 子图节点协议。

    签名比 PhaseExecutor 更窄:不再吃"phase context + phase input + phase result"
    这个通用语义,只接 yaml 声明的 ports。Plugin 内部不感知 phase、不感知 graph。
    """
    @property
    def semantic_name(self) -> str: ...   # 对应 yaml factory: think.reason 等

    async def execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput: ...
```

**职责边界对比**:

| 维度 | 现有 `PhaseExecutor` | 新 `NodeExecutor`(think 专用) |
|---|---|---|
| 适配图节点类型 | 6 phase + 12 control 全部 | 只适配 think 子图内的节点 |
| 输入来源 | phase 框架注入的 `PhaseInput.artifact` | yaml 声明的 `inputs:` 端口映射 |
| 输出目标 | phase 框架消费的 `PhaseResult.outcome` | yaml 声明的 `outputs:` 端口映射 |
| 感知 phase 概念 | 是 | 否(plugin 不感知 phase) |
| 感知 graph | 是(通过 outcome / cursor) | 否(plugin 只接 ports) |
| 失败表达 | `PhaseErrorKind` 枚举 | 标准 Exception(框架 catch 后映射为 node_failure) |

**为什么 think 专用、不全局替换**:
- perceive/act/reflect/remember/stop 这 5 个 phase 的 plugin 是"执行一个 phase",它们需要 `PhaseInput.artifact` 这个 phase 级 artifact,不是 port-mapped。强行换成 NodeExecutor 会让 `artifacts_to_inputs` 投影变成新一层,**扩散面太大**。
- control 类 plugin(think_guard / act_authorize / 等)的语义是"对 phase 决策收口",输入是 phase result,不是外部 ports。换成 NodeExecutor 等于砍掉它们的输入。
- **think 子图是唯一的"业务把节点当数据流节点用"的场景**,只在这套上做通用化,职责最清晰。

**think 5 步 plugin 改造范围**(同 PR 闭环):
- `lca/plugins/think/shortcut/plugin.py`
- `lca/plugins/think/route/plugin.py`
- `lca/plugins/think/reason/plugin.py`
- `lca/plugins/think/classify/plugin.py`
- `lca/plugins/think/gate/plugin.py`
- 5 个 plugin 签名 `async def execute(self, context, input)` → `async def execute(self, context: NodeContext, input: NodeInput) -> NodeOutput`
- 加 `semantic_name` 属性(对应 yaml factory)
- 删 `_shared.py` / `_carry(context)` 这类 phase 隐式耦合(本次为新协议收口)
- PluginSpec 注册从 `phase.think.shortcut` → `think.shortcut`(业务语义名)

**PhaseExecutor 仍然存在**,perceive/act/reflect/remember/stop/control 共用,**本 ADR 不动**。`_shared.py` 之类仅 think 私有的辅助不删;只删 think 5 步 plugin 与 phase 框架的耦合。


## 4. alternative 决策链

| 备选 | 否决理由 | 备选成本(将来复用价值) |
|---|---|---|
| `entries:` 形态 + 加 `_PLAN_REF_PROFILES` 映射 | 修 PG-005 不升级 schema,保留双职责错位;5 步顺序语义继续散落在 5 个 plugin `setup()` | 零(且被本 ADR 取代) |
| 直接接 `agent_lab/graphs/think/think.yaml` | agent_lab port-level edge 与 kernel PhaseEdge node-level 不对齐;`factory: think.expose` 没有对应 `@plugin` 装饰器;agent_lab `region` 是 P7 专属,接进来强制生产走 P7 违 ADR-0075 兼容路径 | 零(agent_lab 自留) |
| 引入独立 `graphs/` 目录 | 违反 ADR-0195 §4 SSOT 矩阵,新增第三 SSOT(profile / bundle / graph) | 零 |
| 用 JSON Schema / Pydantic extra="allow" 保留向后兼容 | 违反 AGENTS.md §4 COMPAT shim 原则 + C13 信息血统闭合;新旧两套 schema 长期共存 = 必然漂移 | 零 |

## 5. 验证矩阵

| 改动类型 | 命令 | 期望结果 |
|---|---|---|
| 新 Pydantic dataclass 闭集 | `uv run ruff check lca/contracts/protocols/declarative/declarative_1/bundle_graph.py` | exit 0 |
| FactoryResolver 三级规则 | `uv run pytest tests/contracts/test_factory_resolver.py -v` | 命中/反查/fail-loud 三类 fixture 全过 |
| BundleSubgraphResolver 新路径 | `uv run pytest tests/harness/declarative/compile/test_subgraph_resolver.py -v` | 新增 5 节点 fixture,`resolve("bundles/think.yaml")` 返回 `CompiledRunPlan` |
| PhaseGraphValidator 投影 | `uv run pytest tests/declarative/test_bundle_graph_spec.py -v` | 节点/边/嵌套 + PG-004 self-reference + region 不匹配 fail-loud |
| profile 切换 | `./scripts/lca-ops inspect-tree profiles/web-standard.yaml` | exit 0,plugin 注册数与改动前一致 |
| 端到端 | `./scripts/lca-ops runs create --user-text "<同 run_f01e7e932a0b 语义>"` + `./scripts/lca-ops journal logs -r <new_run_id>` | 六语义事件链完整,broken_hop=None |
| COMPAT 闭环 | `grep -rl "think-steps" profiles/ bundles/ lca/` | 仅注释级残留;`bundles/think-steps.yaml` 不存在 |

## 6. delete-when

本 ADR 在以下**全部**满足时升 Archived / 删 ADR:
1. `bundles/think.yaml` 在所有引用它的 profile 中稳定运行 ≥ 4 周,无 factory 解析回退
2. `tests/contracts/test_subgraph_reference_contract.py` 中 `plan_ref="bundles/think-steps.yaml"` 三处 fixture 已迁移到 `bundles/think.yaml`
3. `Bundles/reflect-subgraph.yaml` 与 `bundles/think-orchestrator-graph.yaml` 迁到新 schema(独立 ADR 跟进,不在本 ADR 范围)

## 7. 范围外(明确不做)

- `bundles/reflect-subgraph.yaml` 改造 — 独立 ADR/Note
- `bundles/think-orchestrator-graph.yaml` 改造 — 独立 ADR/Note(已被 8d2a67b5 删,无需处理)
- `agent_lab/graphs/think/think.yaml` 与生产 kernel 的对齐 — 独立 ADR(可能涉及 ADR-0210 P7 强制路径)
- `nodes[].inputs/outputs` port-aware edge 校验 — 字段投影本期不启用校验,留接口给后续
- `edges[].kind: data` 数据流调度 — 投影本期只接受,解释器不区分 control/data 边,后续 Note
