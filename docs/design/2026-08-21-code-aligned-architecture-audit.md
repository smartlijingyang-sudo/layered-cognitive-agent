# 代码对齐的第一性原理架构审计

**从“已有很多可插拔对象”走向“唯一编译内核、唯一运行计划、唯一事实链”**

| 字段 | 内容 |
|---|---|
| 日期 | 2026-08-21 |
| 状态 | Proposed architecture audit |
| 适用范围 | `lca/`、`gateway/` 的认知运行时、Profile Boot、执行管线与 Creator 路径。 |
| 宪法基线 | [声明式插件宪法 v4.0](2026-08-21-declarative-plugin-constitution-v4.md)；[ADR-0066](../adr/0066-declarative-atomic-control-plugins.md)；[ADR-0067](../adr/0067-spacetime-runtime-and-governed-creation.md)。 |
| 后继决定 | [ADR-0068：编译式插件内核与唯一运行计划](../adr/0068-compiled-plugin-kernel-and-unified-run-plan.md)。 |

> **审计结论：当前项目已经拥有正确的原料——Manifest、Profile Resolve、Cordis Fiber、PerceiveHub、Execution Envelope、Journal、Tool Pipeline、Composer 与 Creator 工具——但它们尚未收敛为唯一的“编译期计划”和唯一的“运行期内核”。因此，插件是存在的，控制点也存在，却仍有大量关键语义在 `spawn.py`、`runtime_loop.py`、`ModularBrain`、`ActionCatalog`、`CognitiveAgent` 与 gateway helper 中被重新编排。下一阶段的重点不应是继续增加插件数，而是先消灭这些平行事实源。**

## 1. 审计方法与边界

本审计只以当前源码为事实，不把设计文档当作已经落地的实现。分析顺序从真实网关入口回溯到 L4 组合根、L2 循环、L1 认知与执行、Harness Resolve / Boot，最后检查动态 Creator。每个结论都区分为“已实现”“已具备但未接通”“设计目标但尚未实现”三类，避免把命名上的插件化误判为运行时声明式化。

该审计不主张把所有函数、所有枚举或每一条控制流都抽成插件。第一性原理是：**只有独立变化、可声明、可验证、可组合且有明确 owner 的行为才应成为插件贡献；而时序、状态提交、能力衰减、effect 提交、回滚与证据写入必须由小而稳定的内核拥有。**

## 2. 真实运行路径

当前主路径比文档中的“纯插件图”更具体。gateway 先根据 mode 构造 L4 `Agent` 或 `Team`；L4 `Agent` 以 `AgentSpec` 调用 `spawn_agent`；`spawn_agent` 从一个已经 boot 的 Cordis Context 取能力，再直接创建 memory、safe executor、transport、action registry、brain、body、hooks、PerceiveHub、stop rule 和 `CognitiveRuntime`。[1] [2] 该路径最终进入 `CognitiveAgent.run`，后者绑定可观测性、从运行全局 workspace 补 deadline，然后调用 `CognitiveRuntime.run`。[3]

```text
Gateway mode / session
   → L4 Agent(role, tools, llm, scope)
   → spawn_agent(AgentSpec, booted Context)
   → {memory, executor, registry, brain, body, hooks, perceive, stop}
   → CognitiveRuntime.run
   → perceive → think → act → reflect → remember → checkpoint → stop
```

| 区域 | 现有真实责任 | 已实现强项 | 当前限制 |
|---|---|---|---|
| Resolve | bundle / patch 展开、模块 import、Config 验证、capability DAG、layer edge。 | 有冻结 `ResolvedProfile` 和 Manifest hash。 | import 本身会执行模块顶层代码；输出不是最终运行计划。 |
| Boot | 创建 Cordis Context、建立 Fiber、调用 plugin setup、审计 provide / require、装配 observability。 | 具备 setup interaction 审计和失败清理路径。 | 生命周期与 setup 选择存在双轨风险，详见 §5.2。 |
| Spawn | 将 AgentSpec 闭合为运行对象图。 | 依赖多数来自 booted scope。 | 它仍是包含大量默认值和对象创建规则的事实源。 |
| Runtime | 固定的六步认知闭环与 checkpoint / exception handling。 | 一处集中运行循环，具备 pause / resume。 | 时序与状态更新在循环中硬编码；hooks 仍是过渡路径。 |
| Brain | reasoner、skill routing、LLM decision、两个 gate、critic。 | 已有分层协议与 gate 类型。 | 固定两处 gate 插入点，不能表达完整 Control Slot 计划。 |
| Body / executor | action dispatch、permission、参数校验、retry、cache、Journal。 | 执行细节集中，已有五阶段 pipeline 原料。 | pipeline 每 invocation 临时创建，外部控制贡献无法稳定装配。 |
| Creator | source 读取、动态 import、Composer mount / unmount、preset publish。 | 已有 grant / invariant / audit 基础。 | 动态能力直接影响 live Context，并把实验与发布耦合。 |

## 3. 当前资产的真实成熟度

### 3.1 已经可以作为内核基石的资产

`resolve_profile` 以 plugin Manifest 的 `provides` / `requires` 建立 DAG，拒绝裸模块名、重复 ID、结构字段 patch 与无效 Config；它是良好的静态图解析起点。[4] `AuditedPluginContext` 也已经将 setup 阶段的 `provide`、`require` 与 `register` 和 Manifest 声明比对，阻止未声明 capability interaction。[5]

`SequentialPerceiveHub` 已经把 sensor、memory 和上一轮 gate policy facts 汇成 `ContextManifest`，并在唯一位置记录 `ContextManifested`；这是 ContextManifest 作为模型可见世界投影的正确雏形。[6] Tool pipeline 也具备 pre-execute、monotonic guard、execute middleware、post-execute 和 finalize 五阶段的明确定义。[7]

`Composer` 则已具备 capability grant 子集、typed meta 存在、invariant check 和 inspect / mount / unmount 结果类型；这是未来 Creator Control Plane 的正确种子。[8]

### 3.2 名义已插件化、实际尚未成为声明式系统的资产

当前 `PluginDefinition` 只拥有 `id`、`Config`、`provides`、`requires`、`implements`、`layer`、`kind`、`effects`、`test_suite` 与 description。v4 所定义的 group、role、Control Slot、reads / emits、authority、aggregation、failure mode、lifecycle、evidence policy 等内容只是任意 `meta`，没有进入 `PluginDefinition`，Resolve 也没有验证或编译它们。[5] 因而系统无法从插件声明本身生成完整的控制脉络。

`ModularBrain` 直接规定 `shortcut → skill_router → reasoner → decision_gate → agent_gates`；`ActionCatalog` 直接规定动作宇宙和 role scope 到 handler 的映射；`spawn_agent` 直接选择 simple executor、simple body、default stop rule、PromptReasoner、默认 action registry 和 middleware registry。[1] [9] [10] 这些不是错误的实现，但它们说明“控制面”目前仍是 Python 编排，而不是已解析的 Plan。

## 4. 第一性原理：系统实际需要什么

### 4.1 不变量优先于插件数量

一个 Agent harness 的本质不是调用模型，而是把一个不确定的决策源放入可预测的约束系统。该系统最少必须保证下列六条不变量。

| 不变量 | 含义 | 只能由谁保证 |
|---|---|---|
| **I1：唯一语义计划** | 每次 run 都有一个 immutable plan，能回答哪些能力、slot、顺序、条件和权限生效。 | Resolver / Plan Compiler。 |
| **I2：唯一时序内核** | 感知、决策、授权、执行、事实提交和终止之间没有第二条旁路。 | Runtime Kernel。 |
| **I3：唯一状态提交** | 运行状态只能由 typed facts / delta 经 Reducer 改变，不能由插件任意 mutation。 | Reducer + Journal applier。 |
| **I4：唯一 effect 窄门** | 任何外部世界 effect 都是一个有 envelope、grant、budget、constraint 与 receipt 的 command。 | Execution Kernel。 |
| **I5：能力只能缩小** | 子 scope、动态 artifact 和子 agent 永远不能比其父 grant 更强。 | Scope / Grant kernel。 |
| **I6：每个事实可回溯** | 任何 answer、policy verdict、effect 或动态变更都能反向解释到 plan、revision、evidence 与 actor。 | Journal / Evidence ledger。 |

如果任何一条被普通 plugin、helper 或 gateway 临时逻辑绕过，“一切插件”就会退化为“所有代码都有一个名字”，而不是可维护的架构。

### 4.2 正确的核心不是更多类别，而是三个编译产物

Profile 不应直接 boot 成对象图；它应先被编译成三个 immutable artifacts。只有它们可被运行时消费，其他任何请求都必须经由它们的增量修订。

```text
Profile + Bundle + TaskContract + Environment
                 │
                 ▼
            Plan Compiler
                 │
     ┌───────────┼───────────────────┐
     ▼           ▼                   ▼
CapabilityPlan  ControlPlan      ScopePlan
（谁提供什么）  （何时怎么裁决） （在哪、为谁、活多久）
     └───────────┴───────────┬───────┘
                             ▼
                       Runtime Kernel
```

| 编译产物 | 解决的问题 | 最少内容 |
|---|---|---|
| `CapabilityPlan` | capability 的 provider、依赖、版本和 effect 是什么？ | typed provider binding、DAG、revision、health policy。 |
| `ControlPlan` | 在每个控制槽上谁贡献，如何排序、何时启用、如何聚合？ | slot entries、predicate、priority、merge / veto、failure semantics。 |
| `ScopePlan` | 这次 run 在哪个时空、身份、ACL、grant、lease 下发生？ | SpacetimeContext template、ExecutionSpace、Identity / Visibility、grant ceiling、lease。 |

任何已启动对象都应能回答 `plan_ref`；任何 plugin contribution 都必须能回答其来自哪条 PlanEntry。Plan 才是系统的“可读脉络”，不是 Python call graph。

## 5. 代码—宪法差距与根因

### 5.1 Control Slot 尚未成为运行时的一等概念

| 观察 | 代码证据 | 架构后果 | 根因 |
|---|---|---|---|
| 循环顺序写死在 `CognitiveRuntime._loop`。 | perceive / think / act / reflect / remember / checkpoint / stop 直接串行调用。[11] | prestep、预算、审批、策略、终止等只能借 hook、gate 或修改 loop 插入。 | 没有 compiled `ControlPlan`。 |
| Brain 只有两个硬编码 gate 点。 | `decision_gate` 与 `agent_gates` 依次 `enforce`。[9] | 无法声明 gate 是 prepare、veto、transform、advisory、budget 或 stop 类。 | gate 是对象字段，不是 slot contribution。 |
| Action universe与角色权限写在 Python map。 | `BUILTIN_ACTION_SPECS`、`_SCOPE_ACTIONS`、`_operation_for`。[10] | 新 action / scope 需要修改框架代码，无法做 profile diff。 | Command routing 未独立为 CapabilityPlan。 |
| 工具 pipeline 确有 guards，却每次调用新建且只绑定本地 pre-check。 | `_pipeline_for` 重新实例化 pipeline，并只 `add_pre_execute`。[12] | plugin 无法稳定贡献 authorization、budget、constraint、post-effect policy。 | pipeline 未从 ControlPlan 装配。 |

**修正原则：** Runtime 只遍历固定有限 slot；slot 的 entry、排序、聚合与启用条件全由 ControlPlan 给出。`ModularBrain`、ActionCatalog、各类 hooks 最终应降为某个 slot 的标准 plugin implementation，而不再拥有独立编排权。

### 5.2 Boot 当前存在“一个插件、两套启动语义”的高风险

`boot_resolved_profile` 对同一 setup 先执行 `ctx.registry.plugin(item.definition.setup, config=...)`，然后又通过 audited parent context 调用 `_run_setup(item.definition.setup, audited, item.config)`。[13] Cordis 的 `RegistryService.plugin()` 会创建 Fiber 并触发 initial reload；Fiber 的 reload 会执行 `runtime.callback(ctx, config)`。[14] [15] 因此当前实现需要一个明确的回归测试来证明不会出现双 setup，或在特定运行时序下避免第二次执行；否则 setup 内 `provide`、`register`、effect 或外部初始化均可能有重复风险。

这不是“在代码里再加一个布尔开关”能解决的问题，而是必须选择**唯一生命周期模型**：

| 选择 | 结论 | 说明 |
|---|---|---|
| 让 Fiber 执行 setup，并把 AuditedPluginContext 注入 child Fiber。 | **采纳。** | Cordis 是唯一 lifecycle owner；audit 包装进入其真实执行面。 |
| 手动执行 audited setup，并只把 Fiber 当 disposer 容器。 | 否决。 | Fiber 已有 callback / reload 语义；双轨容易重入。 |
| 保留两者并依赖 setup 幂等。 | 否决。 | 幂等不等于正确，且无法证明所有第三方 / 动态插件幂等。 |

### 5.3 “审计上下文”仍可被透传旁路

`AuditedPluginContext.__getattr__` 将未知属性直接转发给内层 Context。[5] 这对兼容便利，但意味着 plugin 可以触及底层 API、Fiber、registry 或其他未建模 surface；`emit()` 也未和 Manifest event declaration 比对。审计系统因此只能证明“走过包装器的 interaction”，而不能证明“全部 interaction”。

**修正原则：** 生产 PluginContext 应是 capability façade，不应有透传 `__getattr__`。确需使用的 framework primitive 必须成为显式、受审计的方法，例如 `effect(DisposalPlan)`、`observe(EventFact)`、`register(Contribution)`；测试 / migration 可使用受限 compatibility context，但不得与 production Boot 混用。

### 5.4 State 与时空仍有多条写入 / 读取通道

`CognitiveRuntime` 直接修改 `state.step`、`budget.used_steps`、history、status、final output、working memory 和 activated skills；它也保留 `_emit` hook middleware 的过渡桥。[11] `ModularBrain` 直接写 `state.active_template`。[9] `CognitiveAgent` 则从 `get_run_workspace()` 读取 deadline 并补入 `RunContext`，形成 ScopePlan 之外的全局时间 / 空间入口。[3]

这些局部 mutation 在系统早期是务实选择，但与“Journal 是事实源、SpacetimeContext 是一等事实”的目标冲突。正确方向不是立刻把 `AgentState` 变不可变而破坏全部代码，而是先引入 `RunFact` / `RunDelta`，让 kernel 成为唯一 applier；再逐步把直接字段写入改为 reducer calls，并以 lint / architecture test 禁止新的写入点。

### 5.5 Creator 现有路径把实验、激活与发布粘在一起

当前 mount action 会读取 source、动态 import、取 factory、调用 Composer、回调注册 tool，然后立即尝试 `PresetAuthoring.publish`。[16] `CordisComposer.mount` 只校验 `plugin_meta`、capability 子集、一个默认 invariant，然后将 instance 放入 `ctx.provide` / `own_bindings`；unmount 直接删除 binding，没有 Fiber disposal、drain、lease、revision 或 rollback plan。[8]

因此 Creator 目前是“受一点约束的 live object injection”，还不是 ADR-0067 所定义的 artifact lifecycle。它最先应该改造成**Plan transaction**：`author → parse → declare → verify → stage → promote → retire → publish`；只有 PromotionController 可以请求 ScopePlan revision，只有 Runtime Kernel 在 safe boundary apply revision。

## 6. 目标架构：小内核、声明性外环

### 6.1 内核只保留七项不可插件化职责

| 内核职责 | 绝不可由普通 plugin 取代的原因 | 对外唯一接口 |
|---|---|---|
| `PlanCompiler` | 需要一次性验证全局依赖、slot、grant、scope 与版本。 | `compile(input) -> CompiledRunPlan`。 |
| `ScopeKernel` | 负责衰减、lease、identity / visibility 与 child scope。 | `open(scope_plan) -> ScopeHandle`。 |
| `RuntimeKernel` | 保持六阶段固定因果顺序与 safe boundary。 | `advance(run, plan) -> RunDelta`。 |
| `Reducer` | 保证 state / Journal 原子地从 fact / delta 派生。 | `apply(state, facts) -> state`。 |
| `ExecutionKernel` | 确保所有世界 effect 经 command envelope 和 receipts。 | `execute(command, policy) -> Observation`。 |
| `ArtifactController` | 保证动态 revision 的 gate、stage、promotion、quiesce 与 rollback。 | `transition(artifact, target) -> Receipt`。 |
| `EvidenceLedger` | 维持事实顺序、hash、provenance 与重放。 | `append(fact) -> EvidenceRef`。 |

其余全部——sensor、reasoner、skill selector、critic、action handler、tool provider、authorization、budget、constraint、retry、memory admission、stop policy、team strategy、renderer、Creator UI——均以 plugin contribution 进入这七项内核的明确 slot。

### 6.2 固定时序、可变策略

运行内核不再接受“任意 hook”；它只识别有限 slot，并通过 ControlPlan 调度贡献。

```text
RunStart
  ├─ perceive.collect → perceive.admit → perceive.select
  ├─ think.prepare    → think.decide  → think.govern
  ├─ command.plan     → act.authorize → act.budget → act.constrain
  ├─ act.execute      → act.observe   → reflect.evaluate
  ├─ remember.admit   → remember.commit
  ├─ stop.decide      → journal.commit → checkpoint
  └─ safe-boundary: apply pending PlanRevision / retire leases
```

这条时序不是要将每一步拆成微小复杂框架，而是约束可变性的位置。每个 Control Entry 必须声明 input / output type、pure 或 effect、allow / deny / transform 语义、优先级、failure mode、evidence descriptor 和 scope。内核按 slot 运行 reducer：例如 `act.authorize` 使用 deny-wins；`perceive.select` 使用 budgeted merge；`think.govern` 可 transform 后必须重新验证 Decision；`stop.decide` 使用 terminal-wins。

### 6.3 CommandEnvelope 取代“Decision 直接进 Body”

`SimpleBody.act` 虽接受可选 envelope，却在 envelope 缺失时从 Decision 临时创建，并继续把 `decision, state` 传给 handler；这说明 envelope 还不是唯一执行事实。[17] 目标中，Decision 不可直接触达 ActionRegistry，必须先由 `command.plan` 变为 `CommandEnvelope`。

```python
@dataclass(frozen=True)
class CommandEnvelope:
    command_id: str
    decision_ref: EvidenceRef
    plan_ref: PlanRef
    scope_ref: ScopeRef
    capability_grant: CapabilityGrant
    execution_space: ExecutionSpaceRef
    idempotency: IdempotencyKey
    budget_reservation: BudgetReservation
    policy_verdicts: tuple[VerdictRef, ...]
    selected_provider: ProviderRef
```

`act.authorize`、`act.budget`、`act.constrain` 都只能追加 Verdict 或收窄该 envelope，不能写 AgentState。`act.execute` 是唯一能将 envelope 交给 provider 的 slot，且必须写开始 / 结束 / 失败 receipt。这样工具 pipeline 不再在每次 invocation 现场创建，而是由 PlanCompiler 装配为 run-scoped `ExecutionPlan`。

## 7. 最小可行对齐路线

路线按“先建立事实源，再迁移行为，最后删除旁路”排序。禁止把所有现有模块一次性重写。

| Wave | 目标 | 主要改动 | 删除 / 禁止的旧行为 | 验收条件 |
|---|---|---|---|---|
| **0：冻结事实** | 建立可测基线。 | topology snapshot、Boot callback-count tests、spawn graph snapshot、state writer inventory。 | 不新增裸 hooks、global workspace reads、direct ctx mutation。 | 每个 profile 可导出 Capability / runtime topology。 |
| **1：Typed PluginContract** | 让宪法字段真正进入解析面。 | `ArchitectureContract`、ControlContribution、Authority、Lifecycle、Evidence schema；Manifest validation。 | 自由 `meta` 承担核心结构。 | invalid group / slot / merge / effect profile resolve fail。 |
| **2：唯一 Boot 生命周期** | 移除 setup 双轨。 | Fiber 内注入 audited façade；await fiber state；setup / dispose receipt。 | `registry.plugin + manual _run_setup` 并存。 | setup exactly once；dispose exactly once；失败不残留 provider。 |
| **3：CompiledRunPlan** | 让 spawn 变为 plan interpreter。 | compiler 输出 CapabilityPlan、ControlPlan、ScopePlan；`spawn_agent` 只 bind plan。 | ActionCatalog / gate / defaults 作为 L4 事实源。 | 同一 input 得到 canonical plan hash；diff 可解释。 |
| **4：Reducer + Spacetime** | 收敛状态与环境读取。 | RunFact / RunDelta、TemporalContext、ExecutionSpace、single applier。 | runtime / brain / agent 直接写 state 或读取 global workspace。 | replay 重建 state；time / deadline 有 evidence provenance。 |
| **5：ExecutionPlan** | 收敛所有 world effect。 | run-scoped pipeline、CommandEnvelope、slot contributions、receipt ledger。 | per-invocation ephemeral pipeline、Body 现场 mint envelope。 | every tool effect has envelope, verdict chain, receipt。 |
| **6：Creator Plan Transaction** | 动态能力安全进入系统。 | artifact registry、experiment scope、promotion controller、revision at safe boundary。 | source-path live import、mount success auto publish、own_bindings delete unmount。 | stage 不影响 live run；promotion / rollback 可 replay。 |
| **7：移除兼容面** | 让内核真正单一。 | 删除 HookRegistry bridge、legacy action maps、untyped meta、default ctx fallback。 | “先兼容后收敛”的永久分叉。 | architecture tests 无旁路；旧 API 仅在明确 deprecated adapter。 |

## 8. 不应做的事情

系统在这次重构中最容易犯的四个错误是：以“更多抽象”代替“更少事实源”；把所有内容塞进 YAML 而失去类型、可测试性和 IDE 支持；让动态 artifact 的 `meta` 比静态 plugin 更强；以及为了去硬编码而把内核的关键不变量也变成可替换对象。

特别是，不要将任何动态插件直接赋予 `Context`、`Registry`、全局 workspace、secret store 或 Journal backend。动态能力的最强权限也必须来自一个受限 ScopeHandle；允许它做什么，必须在 Plan 中显示，而不取决于它“知道如何调用哪个内部对象”。

## 参考

[1]: ../../lca/layer4_app/spawn.py "当前 L4 组合根"
[2]: ../../gateway/runs/loop_drivers.py "当前 gateway 驱动与 Creator 现场注入"
[3]: ../../lca/layer3_agent/cognitive_agent.py "当前 Agent run 与 workspace deadline enrichment"
[4]: ../../lca/harness/profile/resolve.py "Profile Resolve"
[5]: ../../lca/harness/plugin_api.py "PluginDefinition 与 AuditedPluginContext"
[6]: ../../lca/layer1_cognitive/perceive_hub.py "SequentialPerceiveHub"
[7]: ../../lca/layer0_infra/tool_pipeline.py "五阶段工具执行管线"
[8]: ../../lca/contracts/mechanisms/composition.py "Composer 协议"
[9]: ../../lca/layer1_cognitive/brain/modular_brain.py "ModularBrain"
[10]: ../../lca/layer1_cognitive/body/action_catalog.py "ActionCatalog"
[11]: ../../lca/layer2_runtime/runtime_loop.py "CognitiveRuntime"
[12]: ../../lca/layer1_cognitive/body/pipeline_safe_executor.py "PipelineSafeExecutor"
[13]: ../../lca/harness/profile/boot.py "Profile Boot"
[14]: ../../vendor/cordis/src/cordis/registry.py "Cordis Registry.plugin"
[15]: ../../vendor/cordis/src/cordis/fiber.py "Cordis Fiber reload callback execution"
[16]: ../../lca/plugins/tools/cordis_control/actions_mount.py "当前 Creator mount + auto publish"
[17]: ../../lca/layer1_cognitive/body/simple_body.py "SimpleBody"
