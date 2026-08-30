# ADR-0068：编译式插件内核与唯一运行计划

## 状态

**Proposed — 2026-08-21**

Refines: [ADR-0061](0061-plugin-manifest-resolve-boot.md)、[ADR-0062](0062-plugin-runtime-cleanup.md)、[ADR-0066](0066-declarative-atomic-control-plugins.md)、[ADR-0067](0067-spacetime-runtime-and-governed-creation.md)

> **决策：LCA 不再把“Profile 已 boot 的 Cordis Context”视为完整架构事实。Profile、TaskContract 与环境必须先编译为一个不可变 `CompiledRunPlan`，其由 `CapabilityPlan`、`ControlPlan` 与 `ScopePlan` 组成；运行内核只解释这个计划。普通插件只能贡献已声明的 PlanEntry，不能在运行期重新编排核心时序、直接写运行状态、直接提交世界 effect 或借底层 Context 获得未声明能力。**

## 背景

当前项目已经实现了 Manifest、Resolve、AuditedPluginContext、Cordis Fiber、PerceiveHub、Tool Pipeline、Composer 和 Creator 等基础设施。但代码审计显示，核心运行语义仍分散在 L4 spawn、L2 loop、L1 Brain / Body、ActionCatalog、gateway 和 workspace helper 中：Loop 的时序、Brain 的两层 gate、role action map、executor pipeline 的创建、Agent 的 deadline enrichment 与 Creator 的 live mount 都各自持有局部事实。[1]

这使系统有“插件”，却没有单一可检查的运行计划。设计文档所要求的插件群、Control Slot、时空、授权、预算、证据和动态 artifact lifecycle 还未进入 Manifest / Resolver / runtime 的同一数据面。若继续先增加更多插件，只会让编排逻辑从少数类扩散到更多类，而不会提升独立性。

## 决策

### 一、引入 `CompiledRunPlan`，并将它设为运行时唯一语义输入

```text
Profile + Bundle + TaskContract + Environment + Actor
                         │
                         ▼
                    PlanCompiler
                         │
     ┌───────────────────┼───────────────────┐
     ▼                   ▼                   ▼
CapabilityPlan      ControlPlan          ScopePlan
     │                   │                   │
     └───────────────────┴─────────┬─────────┘
                                   ▼
                             CompiledRunPlan
                                   │
                                   ▼
                              RuntimeKernel
```

| 计划 | 唯一职责 | 必含内容 |
|---|---|---|
| `CapabilityPlan` | 描述哪些 provider、tool、sensor、memory、renderer 与 strategy 可用。 | dependency DAG、provider binding、effect class、revision、health policy。 |
| `ControlPlan` | 描述每个固定 Control Slot 的贡献、顺序、条件、聚合与失败语义。 | slot entries、predicate、priority、merge / veto、evidence descriptor。 |
| `ScopePlan` | 描述此 run 的时空、身份、可见性、grant、lease 与执行边界。 | TemporalContext template、ExecutionSpace、ACL、budget、capability ceiling、lifecycle。 |

`CompiledRunPlan` 必须有 canonical hash、version、input provenance 与 `plan_ref`。每一条 Journal fact、Decision、CommandEnvelope、动态 artifact promotion 与 Observation 均必须可关联此 `plan_ref`。现有 `ResolvedProfile.manifest_hash` 保留，但仅代表 profile manifest；它不是 run plan hash。[2]

### 二、插件声明从任意 `meta` 升级为 typed `PluginContract`

当前 `PluginDefinition` 的核心字段继续保留，但增加结构化、必填且可验证的 `PluginContract`。不能再以任意 `meta` 承担 group、role、slot、权限、读写、生命周期和证据等架构语义。[3]

```python
@dataclass(frozen=True)
class PluginContract:
    identity: PluginIdentity
    architecture: ArchitectureContract       # group, role, control slots
    capabilities: CapabilityContract         # provides, requires, effect classes
    ownership: OwnershipContract             # reads, emits, state authority
    authority: AuthorityContract              # grant, risk, approval requirements
    lifecycle: LifecycleContract              # allowed scopes, lease, dispose semantics
    observability: EvidenceContract           # descriptors, privacy, replay requirements
    verification: VerificationContract        # schemas, fixtures, property tests
```

Resolve 必须验证每条贡献与 owner、slot、effect、scope、grant、aggregation 的全局相容性；无法在 Resolve 验证的运行时条件由 PlanCompiler 转为明确 predicate，而非留在 plugin 内的隐式 `if`。

### 三、运行内核只保留固定时序，策略只以 slot contribution 变化

`RuntimeKernel` 只运行以下有限时序：

```text
perceive.collect → perceive.admit → perceive.select
think.prepare → think.decide → think.govern
command.plan → act.authorize → act.budget → act.constrain → act.execute → act.observe
reflect.evaluate → remember.admit → remember.commit
stop.decide → journal.commit → checkpoint → safe-boundary
```

现有 `CognitiveRuntime` 的 loop、`ModularBrain` 的 gate chain、ActionCatalog 的动作映射和 Tool Pipeline 的 guard list 将逐步迁移为这些 slot 的标准贡献。[4] [5] [6] 内核的时序、fact commit、scope attenuation、effect dispatch、plan revision safe boundary 不允许被普通插件替换。

### 四、`RunFact` / `RunDelta` 与 Reducer 是唯一状态写入方式

插件、gate、sensor、reasoner、tool provider 和 observer 不得直接写 `AgentState`。它们只能产出 typed `RunFact`、`RunDelta`、`Verdict`、`Decision`、`CommandEnvelope` 或 `Observation`。Reducer 在 Journal 顺序中应用这些输入并产生新的 state projection。

现有直接 state mutation 是迁移对象，不是永久扩展点：包括 loop 对 history / status / budget 的写入、Brain 对 active template 的写入、以及 gateway / Agent 对 deadline 的补入。[7] [8]

### 五、`CommandEnvelope` 是世界 effect 的唯一入口

Decision 不是 command。任何外部 effect 必须经由 `command.plan` 产生 immutable `CommandEnvelope`，再依次经过 authorization、budget、constraint 和 execution slot。工具 pipeline 将在 run scope 中从 `ControlPlan` 一次性装配，而非每次 invocation 临时创建并只绑定局部 pre-check。[9]

`CommandEnvelope` 至少含：`plan_ref`、`scope_ref`、`decision_ref`、selected provider、capability grant、budget reservation、idempotency key、policy verdict refs 与 execution-space ref。任何 effect 必须回写 receipt / evidence。

### 六、Boot 采用唯一 Fiber 生命周期，生产 context 不得透传

当前 Boot 同时 `ctx.registry.plugin(setup)` 和手动调用 audited `setup`，而 Cordis Fiber 会在 reload 时执行 callback；该双轨需要消除。[10] [11] [12] 采纳“Fiber 执行 setup，AuditedPluginContext 注入 Fiber”的模型：

1. Cordis Fiber 是唯一 setup / reload / dispose owner。
2. Fiber child context 暴露 production capability façade，而非 `__getattr__` 透传内层 Context。
3. 运行时 setup / dispose 记录 typed receipt，证明 exactly-once 或明确 retry semantics。
4. migration compatibility context 必须与 production boot path 隔离，并有删除期限。

### 七、Creator 修改 Plan Revision，不直接修改 live Context

现有 source-path dynamic import、`ctx.provide` / `own_bindings` 直接修改及 mount-success auto-publish 迁移为 ArtifactController 的 plan transaction。[13] Creator 只能产生 `CapabilityArtifact` 和 `PlanRevisionRequest`；ArtifactController 负责 `DRAFT → PARSED → DECLARED → VERIFIED → STAGED → ACTIVE → QUIESCING → RETIRED`，并在 RuntimeKernel safe boundary 将通过的 revision 应用到指定 ScopePlan。

`stage` 与 `publish` 分离；实验默认运行在 fake provider 的 experiment scope；unmount 不再等同于 dict pop，而是 lease revoke、quiesce、drain、disposal receipt 与 Journal fact。

## 后果

| 维度 | 收益 | 成本 |
|---|---|---|
| 可解释性 | 读取一个 `CompiledRunPlan` 即可理解真实运行逻辑，而不是追踪多个 Python helper。 | 需要为 plan、slot、predicate、verdict 建 schema 与 compiler。 |
| 插件独立性 | 新策略以 contract / contribution 加入，而不是编辑 loop、spawn 或 action map。 | 需要删除隐式 convenience APIs。 |
| 安全性 | Context、state 与 effect 的旁路被收敛到小内核。 | 早期迁移会暴露现有测试 / plugin 的隐藏耦合。 |
| 动态创造 | 能安全试验并提升能力，且 revision 可回滚。 | Creator 的即时自由度低于直接 dynamic import。 |
| 可靠性 | 单一 Fiber 生命周期、scope lease 和 receipt 使 cleanup 可证明。 | 需要投入 lifecycle / failure / replay tests。 |

## 迁移顺序

| 阶段 | 目标 | 删除目标 |
|---|---|---|
| 0 | topology snapshots、state writer inventory、setup callback count tests。 | 无。 |
| 1 | `PluginContract`、architecture schema、ControlPlan compiler。 | 关键 architecture 任意 `meta`。 |
| 2 | Fiber-only Boot、audited child façade、dispose receipts。 | manual setup 双轨与 production `__getattr__` passthrough。 |
| 3 | `CompiledRunPlan`，让 spawn 只 bind plan。 | spawn / gateway 中重复的 control selection。 |
| 4 | RunFact / Reducer、TemporalContext / ExecutionSpace。 | 直接 AgentState mutation 和 global deadline enrichment。 |
| 5 | CommandEnvelope 与 run-scoped ExecutionPlan。 | Body 现场 envelope mint、per-call 临时 pipeline。 |
| 6 | ArtifactController / PlanRevision safe boundary。 | source-path live import、dict-pop unmount、auto publish。 |
| 7 | 删除 hook bridge、legacy action map 与其他兼容旁路。 | 双事实源。 |

## 反对的替代方案

| 方案 | 结论 | 原因 |
|---|---|---|
| 只继续扩充 HookRegistry / middleware | 否决 | 只能增加插入点，不能形成统一 plan、owner、grant 与证据模型。 |
| 所有顺序都由 YAML 任意编排 | 否决 | 会使核心因果与安全不变量也可变，难以证明。 |
| 保留现有 spawn 硬编码，插件只增加可选能力 | 否决 | 主路径仍是隐式架构，插件无法成为系统语言。 |
| 直接让动态 plugin 拿 live Context | 否决 | 无法保证 scope、effect、状态与生命周期边界。 |
| 小内核解释 immutable plan，插件贡献有限 slot | **采纳** | 在可扩展性与可验证性之间保持最小可信面。 |

## 参考

[1]: ../design/2026-08-21-code-aligned-architecture-audit.md "代码对齐的第一性原理架构审计"
[2]: ../../lca/harness/profile/resolve.py "ResolvedProfile"
[3]: ../../lca/harness/plugin_api.py "PluginDefinition 与 AuditedPluginContext"
[4]: ../../lca/layer2_runtime/runtime_loop.py "CognitiveRuntime"
[5]: ../../lca/layer1_cognitive/brain/modular_brain.py "ModularBrain"
[6]: ../../lca/layer1_cognitive/body/action_catalog.py "ActionCatalog"
[7]: ../../lca/layer3_agent/cognitive_agent.py "CognitiveAgent"
[8]: ../../lca/layer4_app/spawn.py "spawn_agent"
[9]: ../../lca/layer1_cognitive/body/pipeline_safe_executor.py "PipelineSafeExecutor"
[10]: ../../lca/harness/profile/boot.py "boot_resolved_profile"
[11]: ../../vendor/cordis/src/cordis/registry.py "RegistryService.plugin"
[12]: ../../vendor/cordis/src/cordis/fiber.py "Fiber reload"
[13]: ../../lca/plugins/tools/cordis_control/actions_mount.py "Creator mount action"
