# 声明式认知阶段图规范

> **状态：** Proposed
> **拥有决策：** [ADR-0075](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md)
> **适用范围：** 生产 Agent、Team、Creator artifact、Profile、Bundle、插件运行时与 Gateway run path。

## 1. 目的与强制性语言

本规范定义 LCA 的全量声明式插件模型。它使每个可变认知阶段、阶段内策略、控制规则、对象装配、实现选择、替换关系、效果路径和观察逻辑都成为 `CompiledRunPlan` 中可验证的节点或边。

本文中的 **必须**、**不得**、**应当**、**可以** 分别表示强制要求、禁止要求、默认要求和可选能力。任何生产路径与本文冲突时，必须修改实现或更新 ADR；不得通过兼容分支、隐式 Hook 或未声明 Context 访问绕过本规范。

## 2. 架构边界

### 2.1 最小可信内核

最小可信内核（MTK）不是业务插件集合，而是一组必须稳定且可机械验证的通用机制。它不得认识任何具体 plugin ID、插件类名、工具名、默认 factory key 或业务策略。

| MTK 组件 | 必须负责 | 不得负责 |
|---|---|---|
| `PluginSpecValidator` | schema、版本、字段完整性、签名和声明合法性 | 选择某个业务插件 |
| `PlanCompiler` | 解析关系、替换、依赖、scope、grant、效果与图约束 | 通过 Python 分支定义业务顺序 |
| `PhaseGraphValidator` | 六个语义 phase、因果约束、循环界限、终端路径 | 执行阶段业务逻辑 |
| `GraphAssembler` | 解析 capability binding、构造 Protocol 实现、注入声明依赖 | 硬编码 `simple/default` 或 cluster 特例 |
| `GenericPlanInterpreter` | 解释已验证 phase graph、处理标准结果与失败模式 | 按 plugin ID / 类名选择实现 |
| `Reducer` | 将 Journal 中的 `RunDelta` 折叠为 State projection | 读取世界、调用工具、选择策略 |
| `JournalCommitter` | 盖章、顺序、plan_ref、因果与证据引用 | 保存第二事实源 |
| `EffectGateway` | 授权、预算、审批、幂等、执行、receipt | 决定业务意图或绕过 CommandEnvelope |

### 2.2 语义 phase 与插件化 phase

`perceive`、`think`、`act`、`reflect`、`remember`、`stop` 是封闭的**语义 phase key**。它们规定输入、输出和安全因果关系，但不指定任何 Python 类、算法、模型、工具、策略或执行顺序。

每个语义 phase 必须由一个 `PhaseExecutor` capability 绑定。标准、Null、检索增强、审批优先、团队协作、反思重试和自定义实现均是插件替换，不是 Runtime 子类或 Composer 分支。

```text
semantic phase key       phase executor binding
──────────────────       ─────────────────────────────
perceive                 phase.perceive.standard
think                    phase.think.react
act                      phase.act.effect-gateway
reflect                  phase.reflect.critic
remember                 phase.remember.policy
stop                     phase.stop.budget-and-goal
```

### 2.3 不可变因果边界

Phase graph 可以改变边的局部顺序和重入方式，但必须保留以下内核验证的语义关系：

| 规则 ID | 规则 |
|---|---|
| `PG-001` | 每个可执行 plan 必须绑定六个 semantic phase 各一个主 `PhaseExecutor`。 |
| `PG-002` | effectful `act` 之前必须存在同一 causation chain 中的有效 `Decision`。 |
| `PG-003` | `act` 的世界副作用必须由 `EffectGateway` 处理，且需要 `CommandEnvelope`。 |
| `PG-004` | `reflect` 只能消费已 Journal-committed 的 `Observation` 或只读 evidence reference。 |
| `PG-005` | `remember` 只能提交通过准入的 `WriteSet`，并由 Reducer 应用相应 `RunDelta`。 |
| `PG-006` | 每条终端、暂停或失败路径必须产生 `StopDecision` 与 Journal fact。 |
| `PG-007` | 任意有向环必须有静态最大次数、运行期预算来源和明确的 terminal predicate。 |
| `PG-008` | 插件不得绕过 `Reducer`、`JournalCommitter`、`EffectGateway` 或 capability grant。 |

## 3. 领域模型

### 3.1 `PluginSpec`

`PluginSpec` 是激活插件的唯一结构化架构事实。Python `@plugin` 装饰器、Cordis 注册与 YAML 文件只是此模型的载体；它们不得提供未被 `PluginSpec` 表达的生产行为。

```yaml
apiVersion: lca/plugin-spec/v1
id: control.gate.repeat-tool-call
revision: 1.0.0
kind: contribution
layer: L1
functionalGroup: gate
implementation:
  module: lca.plugins.gates.repeat_tool_call
  setup: setup
configuration:
  schema: lca.plugins.gates.repeat_tool_call.RepeatToolCallConfig
capabilities:
  provides:
    - key: control.executor.repeat-tool-call
      cardinality: one
      protocol: ControlExecutor
  requires:
    - key: state.view
      cardinality: one
    - key: journal.cursor
      cardinality: one
effects:
  classes: [none]
ownership:
  reads: [state.recent_tools, journal.gate_decided]
  emits: [journal.gate_decided]
  stateMutation: forbidden
lifecycle:
  scopes: [run, agent]
  activation: { when: "decision.action == 'use_tool'" }
  disposal: required
contributes:
  - phase: think
    role: govern
    executor: control.executor.repeat-tool-call
    output: control.verdict
    order: 200
    aggregation: deny-on-any-deny
relations:
  - { type: governs, target: phase.think }
  - { type: after, target: control.gate.decision-shape }
  - { type: replaces, target: control.gate.legacy-repeat, mode: exclusive }
evidence:
  emits: [GateDecided]
  replay: required
verification:
  testSuite: tests/plugins/gates/test_repeat_tool_call.py
  fixtures: [tests/fixtures/phase_graphs/repeat-tool-call.yaml]
  properties: [no_state_mutation, deterministic_verdict]
```

### 3.2 必填字段

| 段 | 必填字段 | 编译期用途 |
|---|---|---|
| `identity` | `apiVersion`、`id`、`revision`、`kind`、`layer`、`functionalGroup` | 唯一性、兼容性、架构分组 |
| `implementation` | `module`、`setup` | 绑定运行实现 |
| `configuration` | `schema` | 配置验证与重放 |
| `capabilities` | `provides`、`requires`、`protocol`、`cardinality` | 依赖 DAG 与注入校验 |
| `effects` | `classes` | EffectGateway 和权限校验 |
| `ownership` | `reads`、`emits`、`stateMutation` | 事实、状态与数据所有权校验 |
| `lifecycle` | `scopes`、`activation`、`disposal` | scope、激活和资源释放 |
| `relations` | 关系数组；无关系时显式空数组 | 拓扑、替换、冲突与解释 |
| `evidence` | `emits`、`replay` | Journal 与回放要求 |
| `verification` | `testSuite`、`properties` | CI 追踪和最小性质测试 |

`contributes` 对 `kind: contribution`、`kind: phase-executor`、`kind: effect-handler` 和 `kind: observer` 为必填字段。纯 seam 或 provider 可显式声明 `contributes: []`，但不可借此提供未登记的运行行为。

### 3.3 Kind 与 capability cardinality

| `kind` | 允许职责 | 典型 `provides` | 禁止事项 |
|---|---|---|---|
| `seam` | 定义受类型约束的注入边界 | `journal.store`、`state.view` | 执行业务逻辑 |
| `provider` | 提供外部或基础设施实现 | `llm.client`、`sandbox` | 决定 phase 顺序 |
| `phase-executor` | 实现一个 semantic phase 主执行器 | `phase.think.react` | 直接产生未声明 effect |
| `contribution` | 为一个 phase 增加 prepare/govern/transform/finalize 行为 | `control.executor.*` | 修改其他 phase 的结果 |
| `effect-handler` | 实现受网关管理的命令执行 | `effect.tool.execute` | 直接从 Decision 产生世界 effect |
| `observer` | 只读投影与遥测 | `observer.trace.*` | 影响 State、Decision 或 Verdict |
| `composite` | 打包 Profile/Bundle 的纯声明 | bundle selection | 在 setup 中执行隐式装配 |
| `driver` | 将已编译 plan 接入协议入口 | run driver | 重新解释或修改 plan |

`cardinality` 只能是 `one`、`optional`、`many` 或 `ordered-many`。PlanCompiler 必须拒绝同一 `one` binding 的多个非替换 provider，拒绝无 provider 的必需 capability，拒绝 `ordered-many` 缺少排序关系的贡献集合。

### 3.4 关系代数

| relation | 语义 | 验证规则 |
|---|---|---|
| `depends_on` | source 依赖 target 可用 | 形成 capability/生命周期 DAG |
| `before` / `after` | 同一 phase 内的执行排序 | 不得形成无界环 |
| `contains` | composite 包含被选插件 | 只用于 provenance，不改变执行顺序 |
| `governs` | contribution 对 phase 或 effect 产生 Verdict | 目标必须接受 `ControlVerdict` |
| `observes` | observer 读取目标输出 | observer 必须无 state/effect authority |
| `replaces` | source 替换 target | 需兼容 Protocol 与 output contract |
| `augments` | source 与 target 共同生效 | 必须给出 `before/after` 或 `order` |
| `conflicts_with` | 两者不可共存 | 共同激活时报编译错误 |
| `scoped_by` | source 受 scope/grant 限制 | source grant 必须为 parent 子集 |
| `emits_to` | 输出进入指定 Journal/effect 边界 | 目标必须是合法 writer/gateway |

`replaces.mode` 必须是 `exclusive` 或 `fallback`。`exclusive` 被选中后 target 不得出现在 active plan；`fallback` 仅可在 source 的 activation predicate 为 false 时选择 target。任何替换决定必须写入 `replacement_map` 与 Journal 的 plan provenance。

## 4. Cognitive Phase Graph

### 4.1 图模型

`CognitivePhaseGraphPlan` 是有向、具名、多重边受限图。节点是 semantic phase 的一个 plan instance；边表示数据因果、控制重入或终止流。节点不可使用任意字符串名称，必须引用 `SemanticPhase` 枚举。

```yaml
phaseGraph:
  nodes:
    - id: perceive.main
      semanticPhase: perceive
      binding: phase.perceive.standard
      maxVisits: 8
    - id: think.main
      semanticPhase: think
      binding: phase.think.react
      maxVisits: 8
    - id: act.main
      semanticPhase: act
      binding: phase.act.effect-gateway
      maxVisits: 8
    - id: reflect.main
      semanticPhase: reflect
      binding: phase.reflect.critic
      maxVisits: 8
    - id: remember.main
      semanticPhase: remember
      binding: phase.remember.policy
      maxVisits: 8
    - id: stop.main
      semanticPhase: stop
      binding: phase.stop.budget-and-goal
      maxVisits: 8
  edges:
    - { from: perceive.main, to: think.main, when: "result.kind == 'context'" }
    - { from: think.main, to: act.main, when: "result.decision.requiresEffect" }
    - { from: think.main, to: reflect.main, when: "not result.decision.requiresEffect" }
    - { from: act.main, to: reflect.main, when: "result.kind == 'observation'" }
    - { from: reflect.main, to: remember.main, when: "result.admitMemory" }
    - { from: remember.main, to: stop.main, when: "true" }
    - { from: stop.main, to: perceive.main, when: "not result.shouldStop", loop: { maxIterations: 8, budget: run.steps } }
```

### 4.2 Phase 输入与标准输出

PhaseExecutor 不得直接接受完整可变 `AgentState` 或未受限 Context。它必须接受 `PhaseContext` 和当前 `PhaseInput`，返回 `PhaseResult`。

| Semantic phase | 必需输入 | 可产生的标准输出 | 禁止输出 |
|---|---|---|---|
| `perceive` | `StateView`、`JournalCursor`、受限读取 capability | `ContextManifest`、`RunFact`、`RunDelta` | `Decision`、世界 effect |
| `think` | `StateView`、`ContextManifest`、已授权 reasoning capability | `Decision`、`ControlVerdict`、`RunFact` | `CommandEnvelope`、直接 effect |
| `act` | 已验证 `Decision`、`EffectContext`、授权 provider | `CommandEnvelope`、`Observation`、receipt fact | 原地 State 写入 |
| `reflect` | Journal-committed `Observation`、`StateView` | `Reflection`、`RunFact`、`RunDelta` | 未引用 evidence 的世界读取 |
| `remember` | `Reflection`、`Observation`、`MemoryPolicy` | `WriteSet`、commit fact、`RunDelta` | 未准入的直接存储写入 |
| `stop` | 当前事实、预算、目标与 phase visit 计数 | `StopDecision`、`RunFact`、`RunDelta` | 直接终止进程或跳过 Journal |

`PhaseResult` 必须包含 `resultKind`、`facts`、`deltas`、`evidenceRefs`、`nextHints` 与可选的 phase-specific payload。通用解释器只根据 `resultKind`、已验证 edge predicate 和图约束推进；不得访问实现私有字段来决定下一节点。

### 4.3 Phase 内贡献执行

每个 PhaseBinding 将贡献编译为以下五段，任一段的内容和顺序来自 relation graph，而不是 Runtime 私有方法：

```text
prepare → transform* → govern* → finalize → observe*
```

`prepare` 产生受限输入；`transform` 变换候选结果；`govern` 产生可聚合的 `ControlVerdict`；`finalize` 将输出归一为 `PhaseResult`；`observe` 只接收不可变快照。`govern` 可产生 `allow`、`deny`、`rewrite`、`pause`、`stop` 和 `defer`，其聚合模式必须显式声明为 `all-allow`、`deny-on-any-deny`、`first-terminal` 或 `ordered-rewrite`。

同一 phase 中的 `transform` 与 `govern` 贡献必须有确定顺序；缺少 `before/after/order` 约束的并列可写输出必须被 PlanCompiler 拒绝。`observe` 不参与结果聚合，因此不得注册为 `before/after` 的控制依赖。

## 5. 编译、组装与执行

### 5.1 编译流程

PlanCompiler 必须按以下固定算法编译，不得在运行期补充隐式 binding：

1. 验证 Profile、Bundle、TaskContract 和所有候选 `PluginSpec` 的 schema。
2. 解析 bundle 展开、activation predicate 和 scope inheritance。
3. 解析 `requires/provides` 并生成 capability bindings。
4. 解析 `replaces/conflicts_with/augments`，生成 replacement map 与 active set。
5. 构建 phase graph，绑定每个 semantic phase 的主 executor。
6. 将 phase contributions 按 relation algebra 编译为有向无环的 phase-local graph。
7. 验证 grant 单调性、effect policy、ownership、Journal evidence 与 lifecycle。
8. 验证图因果、循环界限、终端路径和 output contract 相容性。
9. 对 canonicalized plan 序列化、计算 `plan_hash` 并写入 provenance。
10. 生成 `ValidationReport`；任一 error 不得启动 run。

### 5.2 `CompiledRunPlan` 最小结构

```python
@dataclass(frozen=True, slots=True)
class CompiledRunPlan:
    schema_version: str
    plan_hash: str
    provenance: PlanProvenance
    capability_bindings: tuple[CapabilityBinding, ...]
    phase_graph: CognitivePhaseGraphPlan
    phase_bindings: tuple[PhaseBinding, ...]
    control_entries: tuple[ControlEntry, ...]
    replacement_map: tuple[ReplacementDecision, ...]
    effect_policy: EffectPolicyPlan
    scope_plan: ScopePlan
    validation_report: ValidationReport
```

`plan_hash` 必须由 canonical JSON 计算，输入包括所有激活 PluginSpec revision、配置、关系、TaskContract、EnvironmentSnapshot、ActorGrant 和 schema version。相同输入必须得到相同 hash；任何生效替换、顺序、配置、grant 或 effect policy 改动必须改变 hash。

### 5.3 `GraphAssembler`

GraphAssembler 的唯一公开入口是 `assemble(plan: CompiledRunPlan, scope: RestrictedScope) -> ExecutablePlan`。它必须仅按 `capability_bindings` 解析 provider，并把每个 phase binding 装配为 Protocol 实例。

生产源码中，GraphAssembler、Runtime、Gateway、Composer 和 Driver 不得出现下列模式：

```text
create("simple")
create("default")
if plugin_id == ...
if tool_name == ...
if type(component) is ...
固定的 brain/body/perceive composer key 元组
```

性能优化可以把 binding 编译为调用表，但调用表的 key 必须是 plan node id 或 capability key，不得是具体实现身份。

### 5.4 `GenericPlanInterpreter`

通用解释器执行 `ExecutablePlan`，维护不可变 phase visit trace、当前 artifact、budget snapshot 和 causation chain。它的最小伪代码如下：

```text
node = plan.phase_graph.entry
while node is not terminal:
  ensure visit budget(node)
  context = MTK.make_phase_context(plan, node, state_view, journal_cursor, grants)
  result = await node.executor.execute(context, current_input)
  validate PhaseResult against node contract
  commit facts and evidence through JournalCommitter
  state_view = Reducer.apply(result.deltas, state_view)
  if result contains CommandEnvelope:
    observation = await EffectGateway.execute(result.envelope, plan.effect_policy)
    commit observation receipt
  node = select_validated_edge(node, result, plan.phase_graph)
```

解释器不得调用 `brain.think`、`body.act`、`memory.update`、`stop_rule.decide` 等旧具体入口；这些调用必须位于对应 PhaseExecutor 的插件实现中。解释器也不得忽略 contribution 的失败模式、evidence requirement 或 grant。

## 6. 受限上下文与效果边界

### 6.1 `PhaseContext`

```python
class PhaseContext(Protocol):
    plan_ref: str
    node_ref: str
    state: StateView
    journal: JournalCursor
    budget: BudgetView
    artifacts: ArtifactView
    capabilities: CapabilityFacade
    tracing: TraceHandle

    def emit_fact(self, fact: RunFact) -> EvidenceRef: ...
    def propose_delta(self, delta: RunDelta) -> None: ...
```

`CapabilityFacade` 只暴露当前 PluginSpec 声明的 capability，并在每次解析时校验 scope、grant 与 cardinality。PhaseContext 不提供 Cordis Context、裸 Service Locator、可变 `AgentState`、直接 StateStore 写入或未审计环境变量。

### 6.2 `EffectContext` 与 CommandEnvelope

任何 effect class 不为 `none` 的插件必须声明 EffectGateway 支持的 handler capability。插件先产生 immutable `CommandEnvelope`，网关按 `effect_policy` 执行以下不可跳过路径：

```text
shape validation → grant verification → authorization → budget reservation
→ approval → idempotency → handler execution → receipt → Journal commit
```

CommandEnvelope 必须包含 `plan_ref`、`node_ref`、`decision_ref`、`scope_ref`、selected handler、effect class、grant proof、budget reservation、idempotency key 和 policy verdict references。Handler 的返回值必须归一为 `Observation` 与 receipt evidence。

## 7. 激活、配置与替换

### 7.1 激活表达式

`activation.when` 和 phase edge `when` 使用受限 DSL，不执行任意 Python。允许的根变量只有 `task`、`state`、`decision`、`observation`、`reflection`、`budget`、`environment`、`scope` 和 `result`。表达式只能使用布尔、比较、集合成员、存在性、数值预算比较和声明的 pure function。

表达式不得读取工作区、网络、时钟、环境变量或未声明 capability。任何需要世界读取的判断必须由 `perceive` 插件先写为 Journal fact，再由 activation 读取该 fact 的投影。

### 7.2 配置

每个 PluginSpec 配置必须由 Pydantic schema 验证、canonicalize 并纳入 `plan_hash`。敏感值不进入 plan 序列化；Profile 只可引用由受控 resolver 提供的 secret binding，插件不得自行读取 `os.environ`。

### 7.3 替换

Profile 使用 `select`、`replace` 和 `disable` 声明 active set。`disable` 只能关闭可选 contribution 或以兼容 Null phase 替代的 capability；它不得关闭 MTK 不变量或造成 `PG-001` 至 `PG-008` 失效。

```yaml
profile:
  select:
    - phase.think.react
    - phase.think.plan-and-execute
  replace:
    - target: phase.think.react
      with: phase.think.plan-and-execute
      mode: exclusive
  disable:
    - observer.debug.prompt
```

Compiler 必须记录每项选择或替换的来源、predicate、候选集合、赢家和淘汰理由。`lca-ops explain plan <plan-ref>` 必须可输出这份解释。

## 8. 验证与错误

### 8.1 验证器错误码

| 错误码 | 触发条件 | 处理 |
|---|---|---|
| `PS-001` | PluginSpec 缺失必填字段或 schema 不兼容 | 拒绝编译 |
| `PS-002` | capability cardinality 冲突或缺少 provider | 拒绝编译 |
| `PS-003` | relation target 不存在或类型不兼容 | 拒绝编译 |
| `PS-004` | `replaces` 的 Protocol/output contract 不兼容 | 拒绝编译 |
| `PS-005` | grant 超过 parent scope | 拒绝编译 |
| `PS-006` | effect class 未声明或无网关路径 | 拒绝编译 |
| `PG-001` | 缺少六个 semantic phase binding | 拒绝编译 |
| `PG-002` | effectful act 无 Decision 因果前驱 | 拒绝编译 |
| `PG-003` | act 绕过 EffectGateway | 拒绝编译 |
| `PG-004` | reflect/remember 读取未记录结果 | 拒绝编译 |
| `PG-007` | 环缺少 maxIterations、budget 或 terminal predicate | 拒绝编译 |
| `PG-009` | phase-local contribution 图有不可解排序环 | 拒绝编译 |
| `RT-001` | PluginSpec 声明与实际 capability interaction 不一致 | 终止当前 run，记录 security fact |
| `RT-002` | PhaseResult 不符合 node output contract | 终止当前 run，记录 contract violation |
| `RT-003` | handler receipt 与 CommandEnvelope 不匹配 | 标记 effect 不确定，进入恢复流程 |

### 8.2 CLI

以下命令必须成为生产 CLI 的一部分：

| 命令 | 责任 |
|---|---|
| `lca-ops plugin check [--strict] <profile>` | 校验激活 PluginSpec 完整性、ownership、effect 和 verification 段 |
| `lca-ops plan compile <profile> --task-contract <file>` | 产出 canonical `CompiledRunPlan` 与 plan hash |
| `lca-ops plan validate <plan-file>` | 运行 capability、关系、phase graph、grant、effect 与 evidence 验证 |
| `lca-ops graph <profile>` | 输出 capability / relation / phase graph 及替换边 |
| `lca-ops explain plan <plan-ref>` | 输出 binding、顺序、替换、activation、scope 和 provenance |
| `lca-ops audit declarative-boundaries` | 扫描 hard-coded plugin identity、factory key、direct State write、direct effect 和 legacy fallback |

`plugin check --strict` 不得是文档占位命令。若实现尚未提供该命令，验收状态必须为失败。

## 9. 实施迁移

### 9.1 迁移顺序

| 阶段 | 交付物 | 删除项 | 通过条件 |
|---|---|---|---|
| M0 | 修复可运行基线；冻结当前 path snapshot | 无 | 聚焦测试能收集；现有架构审计有基线 |
| M1 | `PluginSpec v1`、strict CLI、全插件清单 | optional metadata、任意 meta 架构语义 | 标准 Profile 100% strict 通过 |
| M2 | `PhaseExecutor` / `PhaseContext` / `PhaseResult` Protocol | Runtime 直接调用具体 phase 能力 | 单个 phase 可用 fake executor 替换 |
| M3 | PhaseGraph / GraphValidator / generic interpreter | `_loop` 的固定 phase 调用序列 | 六 phase graph property tests 通过 |
| M4 | contribution executor 与 relation graph | `ControlSlot → method` 和 `plugin_id → gate` map | Gate/Stop 更换无需改 Runtime |
| M5 | GraphAssembler 与 binding-only Composer | `simple/default`、固定 composer 集合 | 替换 Body/Stop/Think 无 production Python 改动 |
| M6 | EffectGateway-only act path 与 plan revision safe boundary | legacy direct effect、live Context 修改 | effect/replay/rollback tests 通过 |
| M7 | 删除 compatibility path | meta fallback、隐式 no-op、旧 control plan 分支 | `audit declarative-boundaries` 零违规 |

### 9.2 当前组件映射

| 当前组件 | 目标归属 | 迁移要求 |
|---|---|---|
| `CognitiveRuntime._loop` | `GenericPlanInterpreter` | 保留为过渡适配器；删除具体 phase 调用与固定 Slot 列表 |
| `DefaultControlPolicyEngine` | contribution `ControlExecutor` plugins | 删除私有 handler map 和 plugin-id gate map |
| `BrainComposer/BodyComposer/PerceiveComposer/TeamComposer` | `GraphAssembler` + PluginSpec bindings | 删除固定 factory key 和 cluster 分支 |
| `ControlPlanResolver` | `PlanCompiler` 的 control compilation pass | 迁移为 PluginSpec contribution/relations 的强类型解析 |
| `@plugin` / `PluginDefinition` | PluginSpec carrier | 逐项实现必填字段，禁止任意 meta 语义 |
| `CognitiveRunDriver` | 仅启动 compiled executable plan | 不得选择业务 phase 或补齐 binding |

### 9.3 兼容性纪律

迁移适配器必须具有唯一 owner、明确删除版本、覆盖测试和 `legacy` 标记。适配器不得在生产默认 Profile 自动启用。新功能只能进入 `PluginSpec v1` 与 PhaseGraph 路径，不得向旧 Runtime、Composer 或 Meta fallback 添加行为。

## 10. 验收测试

| 验收编号 | 性质 | 最小自动化证据 |
|---|---|---|
| `A1` | 完整 PluginSpec | 标准 Profile 中每个激活插件均通过 `plugin check --strict` |
| `A2` | 确定性计划 | 相同输入随机执行 100 次得到相同 `plan_hash` |
| `A3` | 六 phase 闭合 | 缺任一 semantic phase、无终端路径、无界环均被拒绝 |
| `A4` | phase 可替换 | 将 `phase.think.react` 换为 fixture executor，Runtime/Assembler/Gateway 文件零改动，plan hash 与 trace 均变化 |
| `A5` | control 可替换 | 新增 Govern contribution 不修改解释器、ControlSlot enum 或 handler map |
| `A6` | 无硬编码身份 | AST 审计拒绝 MTK/Assembler 中的 plugin ID、工具名、`simple/default` 与固定 composer 集合分支 |
| `A7` | State 单写 | AST + mutation tests 证明只有 Reducer 应用 State delta |
| `A8` | Effect 受控 | 每个 effectful handler 均有 CommandEnvelope、gateway receipt、Journal fact 和 idempotency test |
| `A9` | 关系可解释 | `explain plan` 输出每项 binding、relation、winner、scope 和 provenance |
| `A10` | 失败可恢复 | handler 失败、approval pause、循环预算耗尽和 plan revision rollback 均有可回放 Journal 结果 |
| `A11` | Capability 单调 | property tests 覆盖 agent、team、scope 和 artifact 的子 grant 为父 grant 子集 |
| `A12` | 旧路径已删除 | `audit declarative-boundaries` 对 production path 输出零违规 |

## 11. 安全与治理

新增 semantic phase、放宽 `PG-001` 至 `PG-008`、允许新的 effect class、允许插件写 State、允许绕过 EffectGateway、改变 Journal 事实边界或扩大 capability grant，均属于 MTK 变更，必须创建 ADR 并新增 property test。

新增 PluginSpec、PhaseExecutor、contribution、relation、Profile 组合或 implementation revision 属于插件扩展；只要通过本规范验证且不改变 MTK，不需要改变 phase graph schema 或新增 Runtime 分支。

任何 Creator 产生的动态 artifact 必须先生成 `PluginSpec`、通过相同 compiler/validator、进入 `DRAFT → VERIFIED → ACTIVE` 生命周期，再在 `safe-boundary` 形成新的 plan revision。Creator 不得 mount 未验证 Python 模块或直接修改 live Context。

## 12. 参考

[1]: ../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md "ADR-0075"
[2]: harness-spine-spec.md "Harness 执行规约"
[3]: glossary.md "领域术语表"
