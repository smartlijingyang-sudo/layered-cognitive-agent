# ADR-0075: 声明式认知阶段图与最小可信插件内核

## 状态

**Accepted — 2026-08-22**

Refines: [ADR-0061](0061-plugin-manifest-resolve-boot.md)、[ADR-0066](0066-declarative-atomic-control-plugins.md)、[ADR-0068](0068-compiled-plugin-kernel-and-unified-run-plan.md)、[ADR-0069](0069-agent-primitive-system-and-declarative-grammar.md)、[ADR-0074](0074-plugin-everything-trimmed-implementation.md)。

当本 ADR 与 ADR-0068 关于“运行内核固定调用六阶段”的限制冲突时，以本 ADR 为准；本 ADR 保留六个认知语义契约、Reducer 单写 State、Journal 事实边界、能力衰减和效果窄门，但将阶段实现、阶段内控制、阶段连边、装配关系与实现选择纳入声明式插件图。

## 背景

LCA 已具备 Manifest、Profile/Bundle、能力依赖 DAG、ControlPlan 与 Cordis 插件运行时。现有生产路径仍由 `CognitiveRuntime._loop`、`DefaultControlPolicyEngine` 和多个 Composer 直接决定阶段调用、控制分派、默认实现和对象组装。[1] [2] [3]

这种结构使插件成为可插入部件，而不是系统的唯一架构语言。插件关系必须跨越代码、factory key、Profile、ControlSlot 和运行时分支才能理解；新增或替换策略仍可能要求修改 Runtime 或 Composer。由此产生与 DSH 式 Hook 增殖相同的可解释性风险：系统拥有很多插件，却没有一张可编译、可验证、可回放的唯一执行图。

ADR-0068 已要求将 Profile、TaskContract 和环境编译为 `CompiledRunPlan`，并要求运行时解释计划；但其“内核只保留固定时序”的表述仍让 Runtime 直接认识具体阶段、控制槽和部分实现语义。[4] 本 ADR 将该边界进一步收窄：内核只验证和解释**通用计划模型**，不直接点名任何业务插件、具体 phase 实现、具体控制策略、factory key 或 Profile 默认值。

## 决策

### 一、采用“所有可变性声明化，最小可信边界不可变”的架构原则

LCA 的正式原则为：**所有可变能力、策略、认知阶段实现、阶段拓扑、控制规则、实现选择、装配关系、替换关系和观察行为，必须由版本化插件声明表达，并由编译器进入唯一的 `CompiledRunPlan`。**

该原则不意味着把每一行代码动态化。以下内容构成最小可信内核（Minimal Trusted Kernel，MTK），必须保持小、确定、受测试保护，不能由普通插件覆写：

| MTK 不变量 | 保留为内核的理由 | 插件不得做的事 |
|---|---|---|
| Manifest / Plan schema 校验 | 防止不完整或伪造声明进入运行时 | 扩展或绕过 schema 验证器 |
| Capability grant 单调衰减 | 子 scope 的权限不得超过父 scope | 自行扩大 grant 或伪造授权 |
| `Reducer` 唯一 State writer | 保证状态可重放、可归因 | 原地修改 `AgentState` |
| Journal 提交边界 | 保证模型可见事实、控制结论与效果证据可重建 | 写入第二事实源或跳过 Journal |
| Effect Gateway | 防止工具、网络、文件和消息绕过授权、审批、幂等与审计 | 直接执行外部副作用 |
| PhaseGraph / Plan 验证器 | 防止图绕过必要语义、无限循环或不安全效果路径 | 运行未经验证的图或字符串代码 |
| 通用 Plan 解释器 | 保证计划按已验证的顺序、作用域和失败语义运行 | 依赖 plugin ID、类名或 hard-coded factory key 分支 |

除上述不变量外，任何以“默认实现”“特定阶段”“特定插件”“特定工具名”“特定策略名”为条件的运行逻辑都是迁移对象。

### 二、六个认知步骤成为可替换的 Phase Plugin，而非 Runtime 的直接调用

`perceive`、`think`、`act`、`reflect`、`remember`、`stop` 保留为六个**语义 phase contract**，而不再是 `CognitiveRuntime` 的六段硬编码方法调用。每个 phase 均由一个 `PhaseExecutor` 插件实现；Profile 通过 `PhaseBinding` 选择实现，PlanCompiler 通过 capability binding 将其解析到不可变计划节点。

```text
Profile / Bundle / TaskContract / Environment
                     │
                     ▼
              PlanCompiler
                     │
                     ▼
          CognitivePhaseGraphPlan
   ┌──────────┬──────────┬──────────┐
   ▼          ▼          ▼          ▼
perceive    think       act      reflect …
   │          │          │          │
PhaseExecutor capability bindings + contribution DAG
                     │
                     ▼
           GenericPlanInterpreter
                     │
                     ▼
 Journal → Reducer → Effect Gateway → Journal
```

`PhaseExecutor` 是可替换插件。标准实现、ReAct 实现、检索增强实现、审批优先实现、团队协作实现和 Null 实现都只能通过 Manifest/Profile 选择；替换任一实现不得要求改 Runtime、Composer 或 Gateway。

六个语义 phase 的顺序也不再由 Python 代码枚举。`CognitivePhaseGraphPlan` 显式声明节点、边、重入条件、最大次数与终止条件。MTK 的 `PhaseGraphValidator` 必须验证图至少提供每个必需语义 phase 的一个执行路径，并满足以下因果约束：

| 必须成立的关系 | 目的 |
|---|---|
| `perceive` 的成功输出先于依赖其 Context 的 `think` | 决策只能依据已收集且可追溯的事实 |
| `think` 的有效 Decision 先于 effectful `act` | 外部效果不能脱离已记录意图 |
| effectful `act` 必经 Effect Gateway | 授权、预算、审批、幂等与审计不可旁路 |
| `reflect` 只消费已记录 Observation | 反思不得读取未审计的世界结果 |
| `remember` 只提交被准入的 WriteSet | 记忆写入必须可控、可证据化 |
| `stop` 为任一终端路径给出 StopDecision | 运行结束、暂停、失败和继续必须可解释 |
| 任意图循环均有编译期界限与运行期预算 | 防止重入图形成无界执行 |

图可以声明 `reflect → think`、`act → perceive` 等重入边，从而表达修正、重试或工具反馈循环；但这些边必须包含可审计 predicate、最大次数和预算来源。图不得以添加未声明的“第七阶段”规避六个语义契约；新语义 phase 需要新的 ADR 与 schema 版本。

### 三、Phase 由“执行器 + 贡献图 + 标准输出”组成

每个 `PhaseBinding` 指向一个主 `PhaseExecutor`，并关联一组具备显式关系的贡献插件。贡献插件分为 `prepare`、`govern`、`transform`、`observe` 和 `finalize` 五种 execution role；它们只可贡献到所声明的 phase，且必须遵守该 phase 的输入、输出和效果约束。

```text
PhaseExecutor
  ├── prepare contributions     形成受限输入与 Context
  ├── transform contributions   变换候选结果
  ├── govern contributions      产生可聚合 Verdict
  ├── finalize contributions    形成标准 PhaseResult
  └── observe contributions     只读投影，不能改变结果
```

运行时不再将 `ControlSlot` 映射为私有方法，也不再依据 `plugin_id` 或 Gate 类名决定策略。每项可执行控制贡献都声明一个 `executor` capability；通用解释器按计划解析该 capability 并将其标准化输出交给聚合器。默认 no-op 同样必须是具备 Manifest、contract、provenance 和测试的显式插件，而非 Resolver 产生的隐式特判。

### 四、`PluginSpec` 是所有激活插件的唯一结构化架构事实

所有参与生产 `CompiledRunPlan` 的插件必须提供 `PluginSpec`。`@plugin` 可继续作为 Python 绑定语法，但其可运行的架构语义必须来自等价的 typed spec，而不是任意 `meta` 或散落的 Composer 规则。

`PluginSpec` 至少包含：identity、kind、layer、functional group、capability contract、effect contract、phase contributions、关系代数、替换语义、lifecycle、evidence、verification 和 configuration schema。实现纯无状态 seam 的插件可省略不适用的 phase contribution，但不得省略 identity、capability、effect、lifecycle、verification 和 ownership。

PluginSpec 的 `relations` 是除 `requires/provides` 以外的唯一组合语言，支持 `before`、`after`、`contains`、`governs`、`observes`、`replaces`、`augments`、`conflicts_with`、`depends_on`、`scoped_by` 和 `emits_to`。PlanCompiler 必须将关系解析为有向图、排序约束、独占选择或拒绝诊断；不得保留由 Python `if/else` 选择的未声明关系。

### 五、Profile 只选择和组合；GraphAssembler 只解释绑定

Profile、Bundle 和 TaskContract 是唯一允许选择插件、配置插件、声明替换、设置 activation predicate 和限定 scope 的输入层。生产路径不得在 Composer 中硬编码 `"simple"`、`"default"`、固定 composer 集合、特定 factory key 或特定插件名称。

原有 Composer 的职责迁移为通用 `GraphAssembler`：它只读取 `CompiledRunPlan.capability_bindings`、`phase_bindings` 和依赖边，按 Protocol 创建节点、注入声明依赖、验证 cardinality，并返回受限执行 scope。GraphAssembler 不得拥有业务策略、默认 profile 或按对象类别进行分支。

### 六、PlanCompiler 必须一次性编译并解释完整的认知图

`PlanCompiler` 的输入是已解析 Profile、Bundle、TaskContract、EnvironmentSnapshot、ActorGrant 和已验证 PluginSpec 集合。它必须产出不可变、可序列化、带 provenance 的 `CompiledRunPlan`，至少包含：

| Plan 区域 | 责任 |
|---|---|
| `capability_bindings` | capability 到 provider 的选择、cardinality、scope 与 grant |
| `phase_graph` | 六个 semantic phase、边、重入、终止和预算界限 |
| `phase_bindings` | phase 到 `PhaseExecutor` 与 contribution DAG 的绑定 |
| `control_entries` | 每个 govern contribution 的 executor、predicate、聚合与 evidence 要求 |
| `replacement_map` | 被替换项、生效项、选择理由和 exclusive / augment 模式 |
| `effect_policy` | effect class 到授权、审批、幂等、执行与审计路径 |
| `provenance` | profile、bundle、plugin revision、TaskContract 和环境输入 |
| `validation_report` | schema、依赖、图、权限、效果、冲突和兼容性验证结果 |

任何运行时可见行为都必须可从 `CompiledRunPlan`、Journal 和 artifact revision 重建。热更新只能生成新的 Plan revision，并且只可在安全边界应用；普通插件不得直接修改 live Context、计划对象或其他插件的绑定。

### 七、所有插件执行经受限 `PhaseContext` 与 `EffectContext`

插件不得获取可透传的 Cordis Context。PhaseExecutor 只接收由 MTK 构造的 `PhaseContext`；该上下文按声明给出只读 StateView、JournalCursor、已授予 capability façade、输入 artifact、deadline、budget 和 tracing handle。Effectful 插件只能在持有由 Effect Gateway 签发的 `EffectContext` 时产生 `CommandEnvelope` 或执行批准后的 command。

插件的可执行输出受限于 `PhaseResult`、`RunFact`、`RunDelta`、`ControlVerdict`、`Decision`、`CommandEnvelope`、`Observation`、`Reflection`、`WriteSet` 与 `StopDecision`。所有 State 更改仍由 Reducer 在 Journal 顺序中应用；所有世界副作用仍通过 Effect Gateway 获得 receipt。

### 八、引入可解释性、替换性和硬编码消除门禁

CI 必须将以下规则作为架构门禁：

| 规则 | 通过标准 |
|---|---|
| Manifest 完整性 | 每个激活生产插件通过 `lca-ops plugin check --strict`；所有必填 `PluginSpec` 段存在 |
| Phase 图闭合 | `lca-ops plan validate` 验证六个 semantic phase、因果约束、循环界限和终端路径 |
| 替换性 | 对任一 `PhaseExecutor` 或贡献 executor，替换 Profile 绑定可改变 plan hash 与行为，但 Runtime/Composer/Gateway 零代码改动 |
| 禁止业务分派 | MTK 与 GraphAssembler 不得根据 plugin ID、类名、`"simple"`、`"default"`、工具名或策略名选择执行逻辑 |
| 状态单写 | 除 Reducer 外，生产源码无 `AgentState` 原地写入；例外必须由特定测试和 ADR 批准 |
| 效果唯一入口 | 任一文件/网络/工具/消息效果均可追溯到 CommandEnvelope、Effect Gateway 与 Journal receipt |
| 图可解释 | `inspect-tree`、`graph`、`explain plan` 输出每个 binding、关系、替换赢家、scope、grant、顺序和 provenance |
| 禁止双轨 | 旧 `meta` 回退、隐式 no-op、固定 composer 选择和 legacy control map 不存在于生产路径 |

## 后果

此决策使系统的可变部分形成一个可读、可编译、可验证和可回放的架构语言。开发者应能仅通过 Profile 和 `CompiledRunPlan` 回答“启用了什么、依赖什么、在何时运行、能读什么、能写什么、能产生哪些效果、替换了谁、为何生效”。

代价是 Manifest、PlanCompiler、GraphValidator、受限 Context、关系代数和测试矩阵将显著增加；新增功能必须先写 contract 和声明，再写实现。该成本是有意的：它把隐式耦合从运行时故障提前为编译期诊断。

此 ADR 不允许以“方便”为由恢复任意 Hook、运行期隐式装配、live Context 透传或 `if plugin_id == ...` 分支。对性能敏感的 built-in 实现可以编译为直接调用，但优化后的执行路径必须由同一 `CompiledRunPlan` 生成，不能成为第二套语义。

## 实施后果

实现必须遵守 [`../specs/declarative-phase-graph-spec.md`](../specs/declarative-phase-graph-spec.md)。该规范定义 `PluginSpec`、`PhaseGraph`、PlanCompiler、通用解释器、协议、错误分类、CLI、迁移和验收测试。

迁移的第一步是修复现有运行范围导入断裂并恢复聚焦测试收集；随后将现有 phase、gate、body、memory 和 stop 路径映射为 explicit PluginSpec。不得以新增平行的第三套 Manifest 或运行计划逃避现有 `CompiledRunPlan`，而应演进其 schema 版本。

**实施状态（2026-08-22 完成）：**

核心声明式路径已完全上线：`CompiledRunPlan` → `GraphAssembler` → `GenericPlanInterpreter` → `RuntimeEffectGateway` 为默认生产路径。Legacy runtime loop、control_policies engine、v1 composer fallback、dual-write 已从生产代码中移除（Tasks 1-6）。Effect idempotency 通过 `RuntimeIdempotencyStore` 实现 at-most-once 语义（Task 7）。Recovery profile 配置为设计文档（`profiles/web-standard-recovery.yaml`），完整 plugin 实现延迟。

验收矩阵已通过 68+ 项测试；Ruff、Mypy、`plugin check --strict`、`plan validate` 与 `audit declarative-boundaries` 均通过。架构守护测试 `test_production_sources_do_not_reference_removed_runtime_modules()` 验证无 legacy 引用。详见 [`0075-implementation-audit.md`](0075-implementation-audit.md)。

## 替代方案

| 方案 | 结论 | 原因 |
|---|---|---|
| 保留固定六步 Runtime，仅允许替换阶段内部实现 | 否决 | 阶段选择、重入和阶段内关系仍无法由 Profile/Plan 完整表达。 |
| 全部使用 Hook / middleware 扩展 | 否决 | 插入点可增长但不存在全局拓扑、权限和替换真相。 |
| 允许 YAML 任意执行 Python / 任意动态导入 | 否决 | 失去类型、效果、权限、可回放和生命周期验证。 |
| 把所有安全校验也实现为普通插件 | 否决 | 普通插件可移除或替换安全约束，破坏最小可信边界。 |
| 固定语义契约，插件化阶段与图，内核验证并解释计划 | 采纳 | 在“六步骤可替换、编排可声明”与安全可证明之间取得最小边界。 |

## 参考

[1]: ../../lca/layer2_runtime/runtime_loop.py "当前生产认知循环"
[2]: ../../lca/layer2_runtime/control_policies.py "当前控制策略执行器"
[3]: ../../lca/plugins/composer/plan_composers.py "当前生产对象图装配"
[4]: 0068-compiled-plugin-kernel-and-unified-run-plan.md "编译式插件内核与统一运行计划"
[5]: 0069-agent-primitive-system-and-declarative-grammar.md "Agent 原语体系与声明组合语法"
[6]: 0070-reducer-as-plugin.md "Reducer-as-Plugin"
[7]: 0072-null-default-discipline.md "Null 默认纪律"
