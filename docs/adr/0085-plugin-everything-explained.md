# LCA 仓库“插件一切”架构解读

> **结论先行：**“一切皆插件”不是把所有代码都拆成小文件，而是把 Agent 中会变化、需要替换、需要组合、需要授权或需要审计的能力，统一表达成“声明式插件 + capability seam + 注册表 + 编译计划 + 受控运行时”。同时，认知阶段闭集、状态唯一写入者、Journal 事实源、CommandEnvelope 执行窄门等宪法约束并不允许被插件绕开。

本文基于仓库当前工作树源码与配置的静态审读，重点解释 `lca/plugins`、`lca/harness/profile`、`lca/layer2_runtime`、`gateway/runs` 之间的关系。按当前 `lca/plugins` 下含 `@plugin` 的 Python 文件扫描，插件模块规模约为 **125 个**；其中源码声明实际使用了 `SEAM`、`PROVIDER`、`PRIMITIVE`、`BRIDGE` 四种类型，分布在 L0–L4 五个层级。[1][2]

## 1. 先建立正确心智模型：插件不是“功能函数”，而是 Agent 的可治理能力单元

普通插件系统通常只回答一个问题：“如何把一个实现加载进来？”LCA 的插件系统要回答六个问题：这个能力是谁、属于哪一层和哪一类、提供什么、依赖什么、能产生什么副作用、在什么生命周期和权限范围内有效。也就是说，插件既是**实现单元**，又是**架构声明单元**，还是**运行时治理单元**。

可以把一个 LCA 插件抽象为：

```text
Plugin = Setup(ctx, Config)
       + Manifest(id / provides / requires / layer / kind / effects)
       + Optional semantic address
       + Optional control contributions
       + Lifecycle / evidence / verification contract
```

插件的 `setup(ctx, config)` 不应该直接知道整个应用，也不应该随意创建全局单例。它只能通过 `PluginContext` 与声明过的 capability 交互；启动器再把所有插件的声明投影成依赖图、控制计划、作用域计划和最终的 `CompiledRunPlan`。[1][3][4]

因此，“插件化”在这里等价于下面这条工程原则：

> **把变化点外置为 capability，把装配关系外置为 profile/bundle，把治理规则外置为 ControlPlan，把运行边界外置为 ScopePlan，把实际副作用收口到受控执行入口。**

这也是为什么仓库中不能简单地把插件理解成“工具插件”。工具只是 G7 Execution 维度的一部分；LLM、Memory、Sensor、DecisionGate、PhaseExecutor、TeamStrategy、Journal、Tracer、Creator 都可以是插件，只是它们位于 Agent 生命周期的不同位置。

## 2. “一切皆插件”的边界：什么可以替换，什么不能被配置改写

LCA 的关键区别是：插件可以替换**实现**，但不能随意改变**宪法结构**。根级工程说明把六步认知闭环、双平面、Reducer 唯一写 State、Journal 唯一事实源和 capability 衰减列为强约束。[2]

| 可插件化的对象 | 例子 | 插件化带来的能力 |
|---|---|---|
| 基础设施接缝 | `llm`、`tools`、`memory`、`sandbox`、`file_store`、`transport` | 更换后端、部署环境或供应商，不修改上层 Agent |
| 具体认知实现 | Brain、Reasoner、Critic、Synthesizer、RetrievalPolicy | 替换推理、批评、记忆检索策略 |
| 感知与决策贡献 | Sensor、DecisionGate、Hook | 增加上下文来源、循环保护和生命周期观察 |
| 执行能力 | Tool、Body、SafeExecutor、EffectHandler | 控制 Agent 能做什么以及效果如何落地 |
| 运行计划 | PhaseExecutor、phase edge、ControlSlot contribution | 选择阶段实现、边条件和控制投稿 |
| 多 Agent 组织 | Team strategy、RoleProfile、Composer | 选择 lead、pipeline、debate、swarm 等协作形态 |
| 可观测性与证据 | Journal、Tracer、FactReader、Scorer、TraceTool | 记录、重放、诊断和评估 Agent 运行 |
| Creator 能力 | `cordis_control`、ArtifactController | 让 Agent 受治理地创建、验证和发布插件 |
| 不可任意改写的核心 | 六阶段闭集、Reducer 单写、Journal 提交边界、CommandEnvelope 窄门 | 防止“插件”变成绕过架构边界的后门 |

这里尤其要注意 **Gate 的位置**。仓库采用六个语义阶段：`perceive → think → act → reflect → remember → stop`；`think.guard` 是 Think/Gate 内部的控制槽，不是额外的第七个自由阶段。类似地，`journal.commit`、`checkpoint`、`safe-boundary` 是横切控制或证据边界，也不应被扩展成新的认知阶段。[5][6]

## 3. 四种实际插件角色：Seam、Provider、Primitive、Bridge

### 3.1 Seam：先定义“可插拔的接口位置”

`SEAM` 插件不一定提供最终业务能力，它首先提供一个稳定的容器、服务定义或注册表。例如 `lca-llm-service`、`lca-tools-service`、`lca-memory-service`、`lca-state-store-service`。Seam 的职责类似“插座”：它规定 capability key 和注册方式，但不决定具体实现。

仓库对 seam 的约定是：一个 seam 模块在 Cordis Context 中放入一个空的 `NamedRegistry` 或领域服务；后续 provider 通过 `ctx.inject(...).register(...)` 往里面添加工厂或实现；更上层的认知插件再消费这个 capability。[7]

### 3.2 Provider：向 seam 注入具体实现或工厂

`PROVIDER` 插件实现 seam 所要求的协议，或向已有注册表注册一个实现。例如：

| Provider | 它向哪里注册 | Agent 影响 |
|---|---|---|
| `lca-tools-provider` | `tools` | 注册按 run 物化的工具工厂 |
| `lca-memory-provider` | `memory` | 注册记忆系统实现 |
| `lca-sandbox-provider` | `sandbox` | 注册执行沙箱 |
| `lca-llm-resolver` | `llm_resolver` | 根据 profile 配置解析 LLM |
| `lca-action-handler-provider` | `action_handler_registry` | 为 RESPOND、USE_TOOL、DELEGATE、HANDOFF 提供处理器 |
| `lca-effect-handler-provider` | `effect_handler_registry` | 处理 `body.act`、`memory.update` 等受控效果 |
| `lca-delta-handler-provider` | `delta_handler_registry` | 把 RunDelta 投影到 Reducer 的状态写入口 |
| `lca-event-descriptor-bootstrap` | `event_descriptor_registry` | 注册内建事件描述符 |

Provider 的关键思想是：**上层只依赖协议和 capability，不依赖某个具体实现类**。例如工具 provider 只向 `tools` 注册 `g2a` 工厂，真正的 `file_store`、`sandbox`、`search`、`skill_store` 和 bindings 到具体 run 时再由 `tools_from_scope()` 注入并物化。[8]

### 3.3 Primitive：真正参与 Agent 行为的原语

`PRIMITIVE` 是具体的认知、执行、感知、控制或编排原语。例如 `brain.simple`、`reasoner.prompt`、`sensor.clock`、`gate.repeat-tool-call`、`body.simple`、`stop_rule.default`、`strategy.debate` 和 `phase.think.standard`。

Primitive 通常不是“向一个通用 seam 注册实现”这么简单，而是直接提供一个命名 factory、向 group service `add()` 一个贡献，或实现一个 PhaseExecutor。它们可以替换 Agent 的某个行为，但仍必须遵守所属层级、作用域和副作用规则。

### 3.4 Bridge：把外部或复合能力接入插件世界

当前源码中唯一显式的 `BRIDGE` 是 `lca-coding-agent-tools-bundle`。它把 TraceInspector、故障解释、优化发现、插件图渲染、最小复现、diff context 和 run diff 等七个只读工具作为一组 capability 提供给 Coding Agent。[9]

Bridge 不是“比 Primitive 更强”的等级，而是边界适配角色：它通常把外部工具集、复合工具集或已有系统接入 LCA 的 capability/permission/evidence 体系。

`PluginKind` 枚举还定义了 `COMPOSITE` 和 `DRIVER`，但按当前 `@plugin` 声明扫描，实际插件清单主要使用上面四种类型；例如 loop driver 本身仍以 Primitive 注册到 `run_loop_driver_registry`。因此，阅读一个插件时应以它的 `kind` 和 `provides/requires` 为准，不要只按目录名称推断角色。[1]

## 4. Manifest：插件必须声明哪些 Agent 维度

`@plugin` 是 LCA 插件的统一声明入口。当前强制的核心字段是 `id`、`layer`、`kind`；能力、实现协议、效果、配置、测试、描述等作为元数据声明。插件的 setup 签名必须是 `async def setup(ctx: PluginContext, config: Config) -> None` 这一类可审计形态。[1]

| Manifest 字段 | 它回答的问题 | 对 Agent 的实际意义 |
|---|---|---|
| `id` | 这是谁？ | 稳定身份、profile 引用、plan provenance 和诊断定位 |
| `Config` | 可配置什么？ | 把环境差异和场景差异从代码中拿出来 |
| `provides` | 我提供哪些 capability？ | 让其他插件可以依赖我，并生成 provider binding |
| `requires` | 我依赖哪些 capability？ | 形成 DAG，决定启动顺序并防止隐式依赖 |
| `implements` | 我实现哪个 Protocol？ | 让语义检查知道 capability 的行为类型 |
| `layer` | 我位于哪一层？ | 防止低层反向依赖高层，保持单向架构 |
| `kind` | 我是 seam/provider/primitive/bridge 哪一类？ | 区分接口位置、实现、行为原语和边界适配 |
| `effects` | 我可能造成哪些效果？ | 参与权限、审批、幂等和安全边界判断 |
| `test_suite` | 用什么验证？ | 把插件的验证入口写进 manifest 与诊断输出 |
| `control` | 我向哪些 ControlSlot 投稿？ | 让治理逻辑进入统一控制面 |
| `functional_group` | 我在 Agent 哪个原语群？ | 给插件一个主语义坐标 |
| `logic_address` | 在什么群、槽、作用域、权限、证据和修订下工作？ | 把插件从“代码模块”提升为可定位的治理对象 |
| `contract` | 身份、能力、所有权、权限、生命周期、证据和验证是什么？ | 提供更完整的 typed contract，可渐进填写 |
| `spec` | 如何进入声明式计划？ | 支持 PhaseExecutor、控制贡献、替换关系和验证投影 |

`PluginContext` 是一个很重要的安全设计。`provide()` 只能提供 manifest 中声明过的 key，`require()` 和 `inject()` 只能读取声明过的依赖，`register()` 只能向声明过的 seam 注册；未声明交互会抛出 `UndeclaredInteractionError`。这使得插件依赖从“代码里偷偷拿东西”变成“manifest 可审计的边”。[1]

## 5. 从目录到 Agent 语义：13 个 Functional Group

`FunctionalGroup` 是插件的主语义坐标。它不是代码目录的别名，而是回答“这个能力在 Agent 认知系统中扮演什么角色”。当前仓库定义 G0–G12 共 13 个群；旧的 v3 9 群仍是认知宪法基础，13 群是更细的工程外化分类。[10]

| 群 | 语义 | 在 Agent 中观察什么 | 典型插件/机制 |
|---|---|---|---|
| G0 | Constitution & Kernel | 哪些规则不可绕过 | contracts、PlanCompiler、Reducer、CommandEnvelope |
| G1 | Identity, Intent & Contract | Agent 是谁、目标是什么、接受什么任务 | RoleProfile、TaskContract、角色权限 |
| G2 | Spacetime, Environment & Context | 当前环境、工作区、时钟和可见上下文 | `sensor.clock`、workspace sensors、device scope |
| G3 | Facts, State & Knowledge | 当前状态、事实、记忆和知识 | StateStore、Memory、Journal facts、RetrievalPolicy |
| G4 | Perception & Grounding | 如何把外部输入转成可信 context | `perceive` seam、PerceiveHub、Sensors |
| G5 | Cognition, Models & Planning | 如何分析、推理、规划和生成候选决策 | Brain、Reasoner、Critic、Synthesizer |
| G6 | Decision, Command & Control | 是否允许、何时停止、如何约束决策 | DecisionGate、StopRule、ControlPlan |
| G7 | Execution, Tools & Operations | 如何把决策变成外部效果 | Body、Tool、SafeExecutor、EffectHandler |
| G8 | Collaboration & Organization | 多 Agent 如何分工、委派、协作 | Team、Blackboard、TeamStrategy、Casting |
| G9 | Interaction, Transport & Interop | 如何与用户、服务和其他 Agent 交互 | Transport、Session、A2A envelope |
| G10 | Composition, Configuration & Runtime Governance | 如何选插件、组装 graph、配置运行 | Bundle、Profile、Composer、CapabilityPlan |
| G11 | Creation, Learning & Evolution | 如何产生新插件、修订 plan、演化能力 | cordis-creator、ArtifactController、PresetAuthoring |
| G12 | Evidence, Evaluation & Operations | 如何记录、重放、评估和运维 | Tracer、Journal、FactReader、Scorer、TraceTool |

**阅读技巧：**看到一个插件时，先问它的 Functional Group，再问它是否还向某个 ControlSlot 投稿。一个 `gate.repeat-tool-call` 主要属于 G6，因为它治理决策；一个 `sensor.workspace-artifacts` 主要属于 G4，因为它把环境内容 grounding 成 context；一个 `lca-fact-reader-jsonl-factory` 更接近 G12，因为它把 Journal 投影成可查询证据。

`functional_group` 当前是可选字段。缺失时 `lca plugin check` 给 warning，严格模式才阻断。这说明仓库正在把“所有插件都具有清晰语义坐标”从软约束逐步收紧为工程门禁，而不是要求一次性给所有旧插件补齐所有元数据。[10][11]

## 6. LogicAddress：把插件放到六维坐标中

如果 FunctionalGroup 只回答“属于哪个群”，`LogicAddress` 则回答“在什么控制和运行条件下属于这个群”。其概念形式是：

```text
LogicAddress = FunctionalGroup
             × ControlSlot
             × Scope
             × Authority
             × Evidence
             × Revision
```

| 维度 | 解释 | 示例问题 |
|---|---|---|
| FunctionalGroup | 主语义群 | 这是 G4 感知，还是 G6 决策治理？ |
| ControlSlot | 介入哪个控制点 | 它在 `think.guard` 还是 `act.authorize` 生效？ |
| Scope | 生存和可见范围 | 是 release、profile、agent、run、turn 还是 experiment？ |
| Authority | 能读取、写入或触发什么 | 它是否拥有 `tool_bash` 或 `memory.update` grant？ |
| Evidence | 产生或依赖哪些事实/事件 | 拒绝一次 tool call 后能否留下可重放的 descriptor？ |
| Revision | 属于哪个计划/版本 | plan 或 artifact 变化后是否应视为新修订？ |

当前评分函数实际按 FunctionalGroup、ControlSlot、Scope、Evidence 四项各 25 分；总分达到 75 才属于“良好”，50–74 为“部分完整”，低于 50 为“缺失严重”。Authority 和 Revision 在地址结构中存在，但当前评分规则没有把它们单独计分，因此不能把“满分”误读成完整的安全审计。[12]

这套模型对 Agent 开发很有用：当你设计一个新插件时，不能只写“它能做什么”，还要写“它在哪个阶段做、影响哪个决策点、作用域多大、凭什么权限做、留下什么证据、版本如何追踪”。

## 7. Scope：插件的生命周期不是一个全局单例

仓库的 `Scope` 枚举实际包含 `release`、`profile`、`agent`、`run`、`turn`、`invocation`、`experiment`、`device` 八个值；其中 `invocation` 在规范化时可以折叠到 `turn`。Scope 决定插件的生命周期、capability grant 衰减、事件可见性和审计边界。[13]

| Scope | Agent 开发中的含义 | 典型对象 |
|---|---|---|
| `release` | 跨 profile 的发布能力 | 已发布 preset、版本化插件 artifact |
| `profile` | 某一套运行配置 | `profiles/web-standard.yaml` 及其 bundle/patch |
| `agent` | 某个 Agent 的身份和能力 | 角色、目标、工具 grant |
| `run` | 一次完整任务执行 | `plan_ref`、run journal、run budget |
| `turn` | 一次模型交互及其工具调用 | 一次 perceive/think/act 循环片段 |
| `invocation` | 单次工具效果边界 | 一次 bash 或 file write 调用；规范上归并到 turn |
| `experiment` | 受限试验/creator staging | fake provider、无副作用验证 |
| `device` | 宿主设备边界 | sandbox、文件系统、运行时进程 |

Scope 不是“给插件贴一个标签”这么简单。它决定子 Agent 能否继承父 Agent 的 grant，也决定一个插件能否从实验环境晋升到 release。LCA 的基本不变量是：子 Agent 的权限必须是父 Agent 权限的子集，不能通过 delegation 获得更大的能力。[14]

## 8. ControlSlot：所有治理投稿进入同一个控制面

ControlSlot 是“插件如何参与 Agent 决策治理”的统一入口。当前共有 11 个槽位：

| ControlSlot | 所属阶段/边界 | 在运行中负责什么 |
|---|---|---|
| `perceive.context` | perceive | 外部事实如何进入可信 context |
| `think.guard` | think/gate | 对决策做确定性治理，例如阻止重复工具调用 |
| `act.authorize` | act | 判断效果是否被授权 |
| `act.budget` | act | 检查 token、步骤、时间或成本预算 |
| `act.constrain` | act | 应用策略约束、scope 和 capability 限制 |
| `act.execute` | act | 进入 Body/SafeExecutor 执行路径 |
| `act.safe-boundary` | act 横切窄门 | effect dispatch 最后的物理/安全隔离 |
| `remember.admit` | remember | 判断哪些内容可以进入记忆 |
| `stop.decide` | stop | 判断本次 run 是否结束 |
| `observe.checkpoint` | 横切观察 | 记录可恢复 checkpoint |
| `observe.*` | 横切观察 | metrics、trace、debug 等观察投稿 |

一个 slot 可以有多个插件投稿，但它们不是任意叠加。每个 entry 可以声明 `order`、`activation`、`aggregation`、`failure_mode`、`authority`、`reads`、`emits` 和 `effect_class`；resolver 会按 `(slot, order, plugin_id)` 稳定排序，并拒绝同一槽位的聚合模式冲突。未被具体插件覆盖的槽位由类型化 no-op 投稿补齐，因此运行时不需要为“这个槽位不存在”写大量分支。[5][15]

例如 `gate.repeat-tool-call` 和 `gate.tool-loop-breaker` 都向 `think.guard` 投稿。它们不是创建两个 Think 阶段，而是在同一个 Think/Gate 控制面中分别提供“重复调用检测”和“工具循环打断”。多个治理结果通常采用 deny-on-any-deny 一类的单调聚合：任何一个安全插件拒绝，整体就不能把拒绝放宽成允许。

## 9. 运行时主链路：从 YAML 到可运行 Agent

一次标准 Agent 启动不是“读取 YAML，然后 import 几个类”，而是下面这条多阶段流水线：

```text
Profile YAML
   ↓
expand bundles + apply config patches
   ↓
import module + extract @plugin Manifest
   ↓
validate id / Config / capability owners / layer edges
   ↓
DAG topological order
   ↓
boot Cordis Context with AuditedPluginContext
   ↓
compile CapabilityPlan + ControlPlan + ScopePlan
   ↓
CompiledRunPlan(plan_ref / phase graph / effect policy)
   ↓
materialize LLM + tools + Brain/Body/Memory/Team
   ↓
run perceive → think → act → reflect → remember → stop
```

### 9.1 Resolve：只解析，不执行 setup

`resolve_profile()` 首先读取 profile，然后展开每个 bundle 的 entries，再应用 profile 的 patch。patch 可以覆盖 config 或 `disabled`，但不能改 `provides`、`requires`、`layer`、`kind` 或 `$module` 等结构字段。之后它会 import 模块、检查 profile 中的 id 是否和插件 manifest id 一致、用 Pydantic 校验 config、校验 capability owner 唯一性，再检查 layer 依赖方向和 capability DAG。[3]

这里最重要的设计是：**YAML 行顺序不是启动顺序**。启动顺序来自 `provides → requires` 的 DAG 拓扑排序。比如 `lca-tools-service` 必须先提供 `tools` seam，`lca-tools-provider` 才能向它注册工厂，上层工具物化又必须等 `file_store`、`sandbox`、`search` 和 `skills` 可用。

### 9.2 Boot：在一个受生命周期管理的 Context 中启动

`boot_resolved_profile()` 按 resolve 得到的拓扑顺序启动插件。每个插件通过 Cordis 注册为 Fiber，插件 setup 实际收到的是父 Context 上包裹过的 `AuditedPluginContext`。如果 setup 抛错，启动器会销毁部分 Context；正常退出时由 Context 统一按生命周期反向清理，而不是由 LCA 自己维护一套 `started[]` 和 disposer 列表。[4]

因此，插件开发者需要把资源生命周期写清楚：连接、后台任务、临时注册和 observer 都应有可清理路径。一个只在 setup 中“偷偷启动线程”却没有 disposer 的插件，在概念上就没有完成 LCA 的生命周期契约。

### 9.3 Compile：把“插件树”变成“本次运行计划”

`PlanCompiler` 把已解析 profile 投影成三个子计划：`CapabilityPlan`、`ControlPlan` 和 `ScopePlan`，然后形成不可变 `CompiledRunPlan`。其中 CapabilityPlan 保存 provider bindings 和关系，ControlPlan 保存 11 个控制槽位的 entries，ScopePlan 保存 lifecycle、visibility、ACL grants 和 budget ceiling；最终通过稳定输入计算 `plan_ref`/plan hash。[16]

这一步把“加载了哪些插件”提升为“本次 run 被允许以什么方式运行”。也就是说，Agent 的行为不只由 LLM prompt 决定，还由编译后的 capability、control、scope 和 effect policy 共同决定。

### 9.4 Assemble：同一插件树可以组装成不同 Agent

`CognitiveRunnableAssembler` 先从 booted scope 解析 LLM 和 tools，再根据 `mode` 选择 Solo、Cordis Creator 或 Team adapter。工具并不是 `Agent` 构造函数里的硬编码列表，而是从 `tools` seam 结合本次 run 的 file store、sandbox、search、skill store 和 bindings 物化。[17]

这带来一个关键结果：**Profile 决定能力池，Mode 决定能力如何被授予和组装。**同一个 web-standard profile 可以构造一个单 Agent，也可以通过 Team casting 构造一个多 Agent Team；Creator 模式还会进一步缩小工具集合并加上受权限约束的 `cordis_control`。

## 10. 一次 Agent turn 到底发生什么

标准声明式阶段执行器把一次任务循环拆成六个语义阶段。阶段之间的产物是 `PhaseResult`、`RunDelta`、`RunFact`、`Decision`、`Observation` 和 `CommandEnvelope` 等受类型约束的数据，而不是任意共享可变对象。[6]

| 阶段 | 读取什么 | 产生什么 | 插件维度 |
|---|---|---|---|
| perceive | Sensor、workspace、inbox、clock、已有 state | context manifest、perception delta | G2/G4，`perceive.context` |
| think | Brain、Reasoner、Critic、Memory context | Decision、tool call、delegation 或 respond 意图 | G5，受 G6 `think.guard` 约束 |
| act | Decision、Body、SafeExecutor、工具注册表 | CommandEnvelope 或 observation | G7，经过 authorize/budget/constrain/execute/safe-boundary |
| reflect | observation、Brain/Critic | reflection/verdict | G5/G6 |
| remember | decision、observation、reflection、Memory | write set、memory effect、RunDelta | G3/G6，受 `remember.admit` 约束 |
| stop | state、decision、observation、reflection、StopRule | stop decision | G6，受 `stop.decide` 约束 |

真正的世界效果必须由 `CommandEnvelope` 携带 grant、scope、effect class、idempotency key 和 metadata，然后交给 effect handler registry。`filesystem`、`network`、`world` 等效果还会受到审批策略限制；同一个 idempotency key 在同一个 plan_ref 下不能重复执行。[6][18]

状态也不能由 Sensor、Gate 或 Body 直接改写。阶段执行器返回 `RunDelta`，再由 DeltaHandler/Reducer 统一投影到 AgentState。这样做的价值是：可以重放、审计、比较和恢复；如果每个插件都直接改 state，就无法判断状态来自哪个决策、哪个 plan 和哪个效果。[2][6]

## 11. 把所有插件放回 Agent 生命周期中理解

### 11.1 启动前：Identity、Composition 和 Environment

Agent 尚未运行时，最重要的不是 Brain，而是 G1 Identity、G2 Environment 和 G10 Composition。Profile 确定要启用哪些 bundle；bundle 选择 seam/provider/primitive；patch 注入模型名、超时和环境参数；LLM resolver 负责唯一的模型解析入口；scope 和 ACL 决定本次 Agent 允许看到什么。

这个阶段最像“编译一个 Agent 产品”，而不是“调用一个 Agent 类”。Agent 的身份、工具集合、memory 后端、transport、观察后端和默认 loop driver 都在这里被确定。

### 11.2 感知阶段：让外部世界成为可引用事实

`perceive` 是一个 group service，具体 sensor 作为贡献加入。`sensor.clock` 提供时间，workspace sensors 提供制品和指令，inbox sensors 提供消息和事实，skill catalog 提供可用技能目录。它们不应该直接把任意内容塞进 Brain，而应该经由 PerceiveHub/manifest 形成可审计的 context。

从 Agent 维度看，感知至少同时涉及 G2 环境、G4 grounding、G3 facts 和 G12 evidence。一个文件读取插件不仅是 G7 tool；它还会影响哪些事实进入上下文、这些事实是否能在 Journal 中重建。

### 11.3 思考与治理阶段：Brain 负责提出，Gate 负责约束

Brain、Reasoner、Critic 和 Synthesizer 负责生成或评估决策，属于 G5 Cognition。DecisionGate、StopRule 和 ControlPlan 属于 G6 Decision/Control。这个分离意味着“模型想做什么”和“系统允许做什么”不是同一件事。

例如 Brain 可以提出连续调用同一个工具，但 `gate.repeat-tool-call` 可以拒绝；Brain 可以提前响应，但 `gate.must-consult-all` 可以要求 lead 先咨询所有成员；循环达到预算后，`stop_rule.default` 可以终止 run。治理逻辑不应埋在 prompt 里，因为 prompt 不是确定性的安全边界。

### 11.4 执行阶段：从意图到可验证效果

Body 不等于工具本身。Brain 产生 Decision，Body/ActionHandler 把 Decision 变成操作意图，ControlPlan 依次执行 authorize、budget、constrain、execute 和 safe-boundary，最后由工具或 effect handler产生 Observation。任何真正改变文件、网络或外部世界的动作，都必须带有 capability grant、scope、effect class 和幂等信息。

因此，新增一个 bash 工具至少要回答四个问题：工具在哪里注册；谁能看到它；它的 effect class 是什么；失败和重复执行如何留下证据。只写一个 `subprocess` 调用并把它放进 prompt，不符合 LCA 的插件思维。

### 11.5 反思、记忆和停止：把一次 turn 变成可恢复历史

Reflect 评估结果是否符合目标，Remember 决定哪些内容进入长期或分层记忆，StopRule 决定是否结束。Journal 和 Trace 负责把关键事实、事件、receipt 和 plan_ref 关联起来。这样，Agent 不只返回一段文本，而是产生一条可重放的运行历史。

在这个模型中，Memory plugin 不是“给模型加一个向量数据库”这么简单。它同时要声明读取哪些事实、允许什么写入、写入作用域是什么、失败时如何处理，以及是否可以在新的 plan_ref 下重放。

## 12. 四个典型场景

### 场景 A：web-standard 单 Agent

`profiles/web-standard.yaml` 组合 `base.yaml`、`web-app.yaml`、`scenario-cordis-creator.yaml` 和 `declarative-phase-graph.yaml`，并通过 patch 配置 LLM resolver。这个 profile 的意义不是“启动一个固定 Agent”，而是把 L0 基础设施、L1 认知行为、L2 声明式阶段图和 Creator 工具能力组合成一个可编译 profile。[19]

运行时，base 提供 LLM、tools、transport、memory、sandbox、search、skills、state store、journal 和 observability 等 seam/provider；web-app 加入 sensors、gates、brain、body、runtime、strategies 和 composer；phase graph 选择六个 PhaseExecutor 和标准边。最终 Solo adapter 从 tools seam 物化工具，生成一个单角色 Agent。

### 场景 B：Team Agent

Team 模式复用同一套 profile context，但不直接创建一个固定成员列表，而是通过 role library 和 TeamCaster 选择角色，再由策略插件形成 lead、pipeline、fan-out、peer relay、peer swarm、debate 或 graph 等协作结构。`lead` 与无 lead 的 coordination 机制是互斥的类型语义；Team 的核心变化发生在 G8 Collaboration 和 G10 Composition，不需要复制一整套 Brain/Body/Memory 实现。[2][17]

这体现了“插件组合优于继承层级”：Solo、Creator、Team 是不同的运行适配器，但底层 LLM、工具、观察、phase graph 和 control plan 仍可以复用。

### 场景 C：cordis-creator 作为“创建 Agent 的 Agent”

Creator 模式不是普通的高权限 Agent。它获得一个缩小后的工具集合，并通过 `cordis_control` 暴露四个治理动作：`inspect`、`author`、`validate`、`promote`。Creator 需要先读取现有插件树，再从源码提取工厂和 metadata，之后通过四状态 Artifact 生命周期完成创建流程。[17][20]

| Creator 动作 | Artifact 状态 | 语义 |
|---|---|---|
| `inspect` | 不改变状态 | 查看已有插件、能力、上下文和 artifact |
| `author` | `DRAFT` | 从源码产生一个候选插件 artifact |
| `validate` | `DRAFT → VERIFIED` | 检查 source、metadata 和 factory 是否可提取 |
| `promote` | `VERIFIED → ACTIVE` | 经 Composer 边界挂载到目标 scope |
| rollback | `ACTIVE → RETIRED` | 卸载并结束该 artifact 生命周期 |

Creator 的 caller grant 只包含四个 control 动作以及受限的文件读写和 bash 能力；它不能因为“自己是 Agent”就获得任意插件挂载权限。实验 scope 还要求插件没有世界副作用；发布到 release 则要经过 preset authoring。这是 G11 Creation、G6 Control、G10 Composition、G12 Evidence 的交叉场景。[20]

### 场景 D：Coding Agent 诊断与优化

Coding Agent profile 叠加 observability-default 和 `coding-agent-tools` bridge，向 Agent 暴露 TraceInspector、failure explainer、optimization finder、plugin graph renderer、minimal reproduction、diff context 和 run diff 等只读工具。这些工具不改变被诊断的 Agent 状态，而是把 G12 Evidence/Operations 能力作为另一组受控 capability 暴露出来。[9]

这说明插件化并不只用于“让 Agent 更强”，也用于“让 Agent 可解释、可复现、可运维”。一个好的 Agent 平台应该能把运行、诊断、评估和开发工具放在同一套 capability/权限/evidence 语言里。

### 场景 E：有界恢复

`web-standard-recovery.yaml` 可以增加 reflect→think 的恢复边，并用 loop guard 限制恢复次数。恢复是 phase graph 的边和条件变化，不是新增一个 `self_reflect` 阶段；它仍然运行在六阶段闭集之内。这种设计把“重试一次后升级或停止”表达为可验证的图约束，而不是散落在业务 if/else 中。[5][19]

## 13. 新增一个插件时，按什么开发流程做

### 第一步：先确定变化点，而不是先写类

先问：你是在提供一个新的接口位置、实现已有接口、增加一个认知原语、增加一个控制投稿，还是接入外部工具？如果是新的可替换后端，先有 seam；如果只是替换实现，使用 provider；如果是 Agent 行为，使用 primitive；如果是外部/复合能力接入，使用 bridge。不要因为“方便”把所有逻辑写在一个大插件里。

### 第二步：定义 capability 和 Protocol 边界

确定 `provides`、`requires`、`implements` 和 effect class。多个实现需要通过 Protocol 加注册表表达；跨层协作通过 capability 注入，不通过反向 import 或全局单例。层级方向必须保持低层提供、高层消费。[2][3]

### 第三步：写 typed setup 和 Config

典型骨架如下：

```python
class Config(BaseModel):
    model_config = {"extra": "forbid"}
    enabled: bool = True


@plugin(
    id="example.tool",
    requires=("tools",),
    implements=(Tool,),
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.TOOLS,
    test_suite="tests/test_example_tool.py",
    description="Register one governed tool.",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    if config.enabled:
        ctx.inject("tools").register_factory("example", build_example_tool)
```

这里的关键不是语法，而是四个不变量：setup 的交互必须被 manifest 声明；Config 拒绝未知字段；副作用显式声明；资源应有 disposer。密钥不要由插件自行读取 `os.environ`，应由 profile 的 `{from_env: ...}` 进入配置，再由唯一的 resolver 或基础设施 seam 消费。[2][3]

### 第四步：加入 bundle，而不是在组合根硬编码

将插件写入合适的 bundle，再由 profile 组合 bundle。profile patch 只做场景配置，不应替换结构性依赖。一个 bundle 可以表示基础设施、web 行为、research 工具、coding 工具、Creator 场景或 declarative phase graph；这使“产品形态”成为配置组合，而不是一串 Python if/else。

### 第五步：经过 Resolve、Boot 和 Compile 三道检查

Resolve 阶段检查 id、module、Config、duplicate provider、missing capability、layer violation 和 dependency cycle；Boot 阶段检查实际 setup 是否越权交互；Compile 阶段检查 ControlPlan、ScopePlan、PhaseGraph、effect policy 和 plan_ref。任何一个阶段失败，都应让 Agent 在启动前失败，而不是等到某个 turn 中出现隐晦错误。[3][4][16]

### 第六步：为运行时行为写场景测试

测试不能只断言“模块能 import”。至少要覆盖 capability 注册、缺失依赖、越权注入、控制槽位排序、effect policy、幂等 key、Reducer 单写、plan_ref 重放、artifact 状态迁移和具体 Agent mode 的工具集合。仓库已有 `check_plugin_typing.py`、`check_plugin_capability.py`、`check_protocol_impl.py` 等门禁，说明插件质量本身就是架构的一部分。[2]

## 14. 最容易误解的五件事

**第一，插件不是动态 if/else。** 动态行为是通过 capability registry、bundle/profile、DAG、ControlPlan 和 adapter 组合出来的；插件本身不能随意改变宿主控制流。

**第二，provides/requires 不等于 Python import。** Python import 只是加载模块，`provides/requires` 才是运行时依赖图。一个模块可以被 import，但没有被 profile 选中，或没有通过 capability validation，就不代表它已成为 Agent 能力。

**第三，Tool 不是 Agent 的全部能力。** Tool 只是 G7 Execution；Brain/Reasoner 是 G5，Gate/Stop 是 G6，Memory/Journal 是 G3/G12，Team 是 G8，Profile/Composer 是 G10，Creator 是 G11。

**第四，ControlSlot 不是新的 phase。** 它是某个阶段内的治理投稿点。把每个 slot 都升级成 phase，会破坏六阶段闭集和统一的运行语义。

**第五，配置可组合不等于权限可扩大。** 子 Agent、子 scope 和子 artifact 的 grant 必须单调收紧；Creator 的 promote 也必须经过 artifact 状态机、Composer 边界和 actor grant 检查。

## 15. 当前源码审读得到的实现注意事项

第一，`functional_group`、`logic_address` 和 `PluginContract` 都是可选声明段。它们已经有数据结构、解析和 check 机制，但并非所有内建插件都完整填写。因此目前应把它们理解为“渐进增强的语义与治理元数据”，不能假设每一个插件都已达到六维地址完整度。[1][10][11][12]

第二，CapabilityPlan 已经支持 11 种关系：`provides`、`requires`、`contributes_to`、`reads_fact`、`emits_fact`，以及 `governs`、`executes`、`delegates`、`projects`、`revises`、`evaluates`。不过，标准 profile 的额外关系声明仍可能很少；关系代数的容器已存在，不代表每个插件都已经把所有语义关系标注完整。[21]

第三，按当前源码直读，`DeclarativeRuntimeDriver` 的构造函数声明需要 `effect_handler_registry` 和 `delta_handler_registry`，而 `lca/layer2_runtime/runtime_loop.py` 中两个构造调用没有显式传入这两个参数。如果没有其他未显示的默认注入或分支适配，这会在实际运行声明式 Agent 时形成参数接线风险，建议优先用声明式 runtime 测试覆盖并修正。这是一个运行时接线问题，不改变“插件一切”的总体架构判断。[6][22]

## 16. 用一句话总结每一层

| 层/对象 | 一句话理解 |
|---|---|
| `contracts` | 定义什么是合法能力、事实、决策、效果和关系 |
| L0 插件 | 把外部世界、后端和可观测性接进来 |
| L1 插件 | 提供 Brain、Sensor、Gate、Body、Memory 等认知原语 |
| L2 插件 | 把六阶段、控制面、Reducer、Effect 和 Journal 组织成运行时 |
| L3 插件 | 把单 Agent、Team、Role、Strategy 和运维工具组织成主体能力 |
| L4 插件/组合根 | 根据 profile 和 plan 把所有能力组装成一个可运行 Agent/Team |
| `bundle` | 一组可复用的能力配方 |
| `profile` | 某个产品/部署/场景对能力配方的选择和配置 |
| `CompiledRunPlan` | 某次 Agent run 真正被允许执行的不可变合同 |
| `ControlSlot` | 插件参与治理决策的统一插槽 |
| `ArtifactController` | Agent 创建和演化插件时的生命周期闸门 |

最终，LCA 的 Agent 不是“LLM + tools + 一个循环”，而是：

```text
Agent
= Identity
+ Environment / Perception
+ Cognition
+ Decision Governance
+ Execution Boundary
+ Memory / Facts
+ Collaboration
+ Interaction
+ Composition Plan
+ Evidence / Evaluation
+ Governed Evolution
```

“插件一切”的真正价值，是让上式中的每一项都能被独立声明、替换、组合、授权、审计和重放；而不是让每一项都可以绕过核心约束、任意增加一个新的隐藏分支。

## References

[1][ref-plugin-api]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/harness/plugin_api.py

[2][ref-agents]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/AGENTS.md

[3][ref-resolve]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/harness/profile/resolve.py

[4][ref-boot]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/harness/profile/boot.py

[5][ref-control-slot]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/contracts/atoms/control_slot.py

[6][ref-phase-runtime]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/layer2_runtime/declarative_runtime.py

[7][ref-seams]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/seam_definitions/__init__.py

[8][ref-tools-provider]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/providers/tools.py

[9][ref-coding-bundle]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/bundles/coding_agent_tools.py

[10][ref-functional-group]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/contracts/atoms/functional_group.py

[11][ref-plugin-contract]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/contracts/harness/plugin_contract.py

[12][ref-logic-address]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/contracts/protocols/logic_address.py

[13][ref-scope]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/contracts/atoms/scope.py

[14][ref-relation]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/contracts/atoms/relation.py

[15][ref-control-resolver]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/harness/profile/control_plan_resolver.py

[16][ref-plan-compiler]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/harness/profile/plan_compiler.py

[17][ref-runnable-assembly]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/gateway/runs/runnable_assembly.py

[18][ref-phase-common]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/phase_executors/common.py

[19][ref-web-profile]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/profiles/web-standard.yaml

[20][ref-creator-promotion]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/tools/cordis_control/creator_promotion.py

[21][ref-capability-resolver]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/harness/profile/capability_plan_resolver.py

[22][ref-runtime-loop]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/layer2_runtime/runtime_loop.py
