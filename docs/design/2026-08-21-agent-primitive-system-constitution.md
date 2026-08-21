# Agent 原语体系宪章

**以一套有限、完备、可组合的概念坐标系，安放所有 Agent 逻辑**

| 字段 | 内容 |
|---|---|
| 版本 | v1.0 |
| 日期 | 2026-08-21 |
| 状态 | Proposed canonical architecture |
| 上位决定 | [ADR-0069：Agent 原语体系与声明组合语法](../adr/0069-agent-primitive-system-and-declarative-grammar.md) |
| 具体化决定 | [ADR-0066](../adr/0066-declarative-atomic-control-plugins.md)、[ADR-0067](../adr/0067-spacetime-runtime-and-governed-creation.md)、[ADR-0068](../adr/0068-compiled-plugin-kernel-and-unified-run-plan.md) |
| 取代的思考方式 | 按目录、框架 API、临时 Hook 或“某处顺手加逻辑”组织系统。 |

> **本宪章的目的不是罗列 Agent 功能，而是回答任何新需求唯一应被放在哪里。一个新逻辑只有在回答了“它改变什么、读取什么、产出什么、可否拒绝、可否产生 effect、属于哪个 scope、由谁证明”之后，才允许进入系统。若这些问题不能被回答，它不是插件，也不应进入生产系统。**

## 1. 第一性原理

Agent 系统不是“LLM 加工具”的集合，而是一个在**部分可观测世界**中，以受限权限为某个主体实现目的，并能解释和恢复其行为的运行系统。行业实践虽使用不同术语，但共同覆盖计划、工具、协作、状态、审批与可观测性；例如 OpenAI 将 agent run、tools、handoffs、guardrails、可恢复 approval 和 tracing 视为同一运行面，Anthropic 将固定工作流、动态 Agent、routing、parallelization、orchestrator-workers 与 evaluator-optimizer 视为可按复杂度组合的模式。[1] [2] 规划研究还将任务分解、计划选择、外部模块、反思与记忆并列为能力维度。[3]

这些概念不能平铺为“很多 plugin”。系统必须先区分七种不同性质的东西：**内核、事实、契约、计划、贡献、工件、投影**。混淆它们是架构腐化的最常见来源：例如把 policy 当 state、把 tool 当 capability、把 runtime object 当 plan、把日志当真相、把动态源码当已授权能力。

| 原语种类 | 定义 | 是否可由普通插件替换 | 例子 |
|---|---|---|---|
| **Kernel** | 维持全局不变量、顺序和提交的最小可信机制。 | 否；可有版本升级但不可被 profile 任意替换。 | PlanCompiler、Reducer、ExecutionKernel、ScopeKernel。 |
| **Fact** | 已发生或已观测、带来源与时间的不可变陈述。 | 不适用；只能追加或投影。 | user input、ToolReceipt、PolicyVerdict、TemporalFact。 |
| **Contract** | 编译或运行前必须成立的结构、类型、权限或所有权约束。 | 合约版本可演进，合约检查不可跳过。 | PluginContract、TaskContract、ToolSchema。 |
| **Plan** | 对某个 scope 在某段时间内有效的 immutable 组合说明。 | 可产生新 revision，不可在原地悄悄修改。 | CapabilityPlan、ControlPlan、ScopePlan。 |
| **Contribution** | 插件对一个已知 slot 的声明性输入。 | 是；这是插件化主要对象。 | sensor、gate、tool provider、memory policy。 |
| **Artifact** | 可审计、可复现、可验证、可提升的能力候选。 | 是；必须经历 lifecycle。 | 动态 plugin、bundle、profile patch。 |
| **Projection** | 从 facts / plans 派生、可丢弃重建的视图。 | 是；不得成为事实源。 | UI、trace、metric、dashboard、prompt rendering。 |

## 2. 全局坐标：所有逻辑都需同时落在六个轴上

“属于哪个插件群”还不够。任何可声明变化必须同时被六条坐标约束；这六条坐标构成一个逻辑的完整地址。

| 坐标轴 | 必答问题 | 枚举值 / 形式 |
|---|---|---|
| **功能轴 `what`** | 它在系统中做什么？ | 见 §4 的 12 个原语群。 |
| **时序轴 `when`** | 它在哪个固定 slot / 生命周期节点生效？ | resolve、boot、run-start、perceive、think、command、execute、commit、stop、retire。 |
| **边界轴 `where`** | 它在哪个时空 / scope 内有效？ | release、profile、agent、run、turn、invocation、experiment、device。 |
| **权力轴 `may`** | 它可读取、写入、拒绝、批准或 effect 什么？ | capability grant、state owner、effect class、visibility / ACL。 |
| **证据轴 `prove`** | 它如何让行为可重放、解释和评估？ | fact descriptor、evidence refs、test fixture、eval criterion。 |
| **演化轴 `change`** | 它如何被配置、替换、升级或撤回？ | config patch、plan revision、artifact lifecycle、release version。 |

> **位置公式：** `LogicAddress = FunctionalGroup × ControlSlot × Scope × Authority × Evidence × Revision`。
>
> 如果一项逻辑不能写出该地址，则它只能处于实验草稿，不得绕过内核直接进入运行时。

## 3. 三层系统形态：语义、运行、演化

十三个原语群不按 Python layer 或目录划分，而按系统中不可混淆的责任划分。它们位于三个形态层中，每层都可被同一套 PluginContract 和 Plan 语言描述。

```text
语义层：主体、目的、时空、事实、知识、能力
                     │ 编译为
运行层：感知、认知、决策、控制、执行、协作、提交
                     │ 产出事实并允许
演化层：观测、评估、创建、发布、回滚、治理
```

| 形态层 | 关注的问题 | 不可混淆的错误 |
|---|---|---|
| **语义层** | 我们为何、为谁、在何时何地、基于哪些事实和知识行动？ | 把 Prompt 字符串当 TaskContract；把 workspace path 当 ExecutionSpace。 |
| **运行层** | 此刻如何感知、思考、限制、执行、协作并提交？ | 把 handler 直接改 state；把 policy 判定隐藏进 tool。 |
| **演化层** | 如何观察质量、测试、创建能力、版本化、发布、撤回？ | 让实验代码直接成为生产 capability；把 dashboard 当事实。 |

## 4. 十三个原语群：覆盖所有独立变化

本节是系统的**概念目录**。目录的目标不是限制创新，而是保证创新找到唯一的第一归属；每一项新逻辑必须先落到其中一个主群，必要时通过有向关系连接其他群，而不是复制责任。

### G0：宪法与内核（Constitution & Kernel）

该群定义不可随 profile 任意变化的系统语义与最小可信面。它不实现业务策略，不拥有模型 prompt，不提供具体工具。

| 子原语 | 责任 | 可变性 | 典型实现 |
|---|---|---|---|
| `SemanticLaw` | ID、事实、effect、authority、scope、revision 的全局不变量。 | 仅 ADR / major version。 | schemas、architecture tests。 |
| `PlanCompiler` | 输入 contracts，输出 immutable plans。 | 可升级，不可被普通 plugin 旁路。 | resolve / compile。 |
| `RuntimeKernel` | 解释固定 control slots 与 safe boundary。 | 可升级，不可被 profile 重新编排。 | run engine。 |
| `Reducer` | 将 ordered facts / deltas 应用为 state projection。 | 可版本化，不能由工具直接替代。 | state applier。 |
| `ScopeKernel` | grant 衰减、lease、visibility、scope opening / closing。 | 可升级。 | scope handle。 |
| `EvidenceLedger` | 事实追加、hash、provenance、重放锚点。 | 可替换 backend，不可绕过追加语义。 | Journal backend。 |

### G1：主体、意图与契约（Identity, Intent & Contract）

此群表达“谁要什么、为何可以做、成功是什么”。它不负责执行，也不负责将自然语言直接翻成工具调用。

| 子原语 | 责任 | 示例 |
|---|---|---|
| `Principal` | 用户、组织、服务账号、Agent、设备的认证身份。 | user / tenant / service identity。 |
| `Role` | 可承担的责任与可见能力边界。 | researcher、creator、approver。 |
| `TaskContract` | 目标、成功条件、deadline、预算、风险、输出承诺。 | research report task。 |
| `DelegationContract` | 任务、grant、预算与责任如何委派。 | lead → worker。 |
| `Consent / ApprovalContract` | 哪些风险必须人或策略批准。 | payment approval、data export consent。 |
| `OutcomeCriterion` | 什么算完成、失败、部分交付或需要澄清。 | acceptance test / rubric。 |

### G2：时空、环境与上下文（Spacetime, Environment & Context）

此群描述 Agent 面向的现实和计算环境。它将“时间”“workspace”“设备”“会话”从隐式全局变量变为有来源、有有效期的事实。ADK 对 session / transient state 与跨会话 long-term knowledge 的区分，也支持将运行状态、记忆和环境边界显式建模。[4]

| 子原语 | 责任 | 必须不做 |
|---|---|---|
| `TemporalContext` | 当前时刻、时区来源、logical time、deadline、elapsed、validity。 | 不用自然语言 prompt 偷渡时区。 |
| `ExecutionSpace` | backend、workspace、outputs、device、network zone、capabilities。 | 不用裸路径推断权限。 |
| `IdentitySpace` | tenant、principal、role、agent、session、delegation chain。 | 不让子 agent 自行扩大身份。 |
| `VisibilitySpace` | classification、audience、retention、memory / egress ACL。 | 不让 renderer 决定可见性。 |
| `RunContext` | 当前 run / turn / invocation 的上下文引用。 | 不承载无来源 mutable world fact。 |
| `ContextManifest` | 此刻允许模型与策略消费的有预算上下文投影。 | 不等同于完整 state / database。 |

### G3：事实、状态与知识（Facts, State & Knowledge）

“事实”是发生了什么，“状态”是内核从事实投影出的当前运行图，“知识”是可检索、可压缩、可治理的长期信息。三者必须分离。

| 子原语 | 责任 | 典型变化 |
|---|---|---|
| `RunFact` | input、observation、verdict、receipt、decision 等有序事实。 | append-only。 |
| `RunDelta` | 对 projection 的合法更新建议。 | reducer apply。 |
| `WorkingState` | 当前 run 的短期可恢复投影。 | checkpoint / replay。 |
| `Memory` | episodic、semantic、procedural、preference、team、artifact memory。 | admit / retrieve / forget。 |
| `KnowledgeSource` | 文档、数据库、网页、RAG index、policy corpus。 | ingest / index / cite。 |
| `ContextCompression` | 令 context 在预算内保持任务相关。 | summarize / prune / cache。 |

**归属规则：** 想“记住某事”时，先问它是事实、state projection 还是长期知识。session history 与 long-term memory 具有不同生命周期和检索语义，不能共享同一个无类型列表。[4]

### G4：感知与归因（Perception & Grounding）

此群把世界转为可消费 ContextItems。它包括人类输入、工具结果、文件、网页、传感器、事件流、时间、团队消息和记忆检索；不包括对它们的最终决策。

| 子原语 | 责任 | slot |
|---|---|---|
| `Sensor` | 从一个受限来源读取事实。 | `perceive.collect`。 |
| `Normalizer` | 将原始信号转为 typed fact / context item。 | `perceive.admit`。 |
| `ProvenancePolicy` | 验证来源、freshness、classification、可信度。 | `perceive.admit`。 |
| `Retriever` | 检索 knowledge / memory / tool catalog。 | `perceive.collect`。 |
| `Selector / Budgeter` | 在 token、时间、隐私预算内选择上下文。 | `perceive.select`。 |
| `GroundingChecker` | 评估输出是否被证据支撑。 | `reflect.evaluate` 或 `think.govern`。 |

### G5：认知、模型与规划（Cognition, Models & Planning）

该群负责产生候选理解、计划、决策与反思，但本身没有世界 effect 权力。LLM planning 的任务分解、计划选择、external module、reflection 和 memory 都在此处作为可声明贡献出现。[3]

| 子原语 | 责任 | 典型策略 |
|---|---|---|
| `ModelRoute` | 选择 / 约束 model、provider、reasoning budget、fallback。 | cost / latency routing。 |
| `PromptAssembly` | 从 ContextManifest 和 Role / TaskContract 生成模型输入。 | template / ACI policy。 |
| `Reasoner` | 产生候选 thoughts / plan / action intent。 | ReAct、structured output、code planning。 |
| `Planner` | 分解任务、构建 TaskGraph、重计划。 | HTN、DAG、reactive planning。 |
| `PlanSelector` | 选择候选计划或 route。 | deterministic / LLM / classifier。 |
| `Critic / Evaluator` | 评估 decision、output、tool result、plan quality。 | rubric、self-critique、verifier。 |
| `LearningProposal` | 从 eval / reflection 提出 memory 或 artifact 改进建议。 | post-run proposal。 |

### G6：决策、命令与控制（Decision, Command & Control）

这是“模型想做什么”转成“系统是否允许、如何执行”的桥。它不直接执行 tool；任何需要阻止、收窄、批准、排序、预算或停止的逻辑都应首先在本群定位。

| 子原语 | 责任 | 固定 slot |
|---|---|---|
| `Decision` | 模型 / workflow 的候选意图。 | `think.decide` 输出。 |
| `DecisionGovernor` | 结构校验、transform、veto、clarification、policy facts。 | `think.govern`。 |
| `CommandPlanner` | 将允许的 decision 变为 CommandEnvelope。 | `command.plan`。 |
| `AuthorizationPolicy` | capability、consent、role、delegation 审批。 | `act.authorize`。 |
| `BudgetPolicy` | cost、tokens、steps、wall-clock、concurrency reservation。 | `act.budget`。 |
| `ConstraintPolicy` | data egress、schema、rate, sandbox, safety, idempotency。 | `act.constrain`。 |
| `StopPolicy` | success、failure、deadline、budget、human wait、quiesce。 | `stop.decide`。 |

### G7：执行、工具与操作（Execution, Tools & Operations）

该群是唯一接触外部世界的地方。工具不是“任意函数”，而是由 declaration、provider、execution policy、receipt 和 renderer 分离的 capability。Anthropic 对清晰 tool definition、格式、边界和测试的强调，正是该群的接口原则。[2]

| 子原语 | 责任 | 不变量 |
|---|---|---|
| `ToolDeclaration` | 模型 / UI 可见的 name、schema、description、examples、risk。 | identity 不随 provider 漂移。 |
| `Operation` | 执行一个受 CommandEnvelope 约束的动作。 | 不直接读全局 grant。 |
| `Provider` | 工具、模型、文件、浏览器、sandbox、MCP、A2A 的具体后端。 | 可替换，不改 declaration。 |
| `Executor` | timeout、retry、cache、idempotency、cancel、receipt。 | 所有 effect 有 receipt。 |
| `AsyncJob` | 长任务的 start、status、logs、cancel、result。 | 不阻塞 run loop。 |
| `ArtifactDelivery` | 产物落盘、链接、校验、交付。 | outputs owner 明确。 |

### G8：协作、组织与分布式工作（Collaboration & Organization）

多智能体不是“多几个 LLM”。它是 delegation、role、topology、共享资源、协议和结果合成的独立系统。OpenAI 的 agents-as-tools / handoffs 与 Anthropic 的 orchestrator-workers 都应表达为该群的组合模式，而非新框架分支。[1] [2]

| 子原语 | 责任 | 典型拓扑 |
|---|---|---|
| `Team` | member、shared contract、shared / private space。 | fixed team。 |
| `RoleLibrary` | 角色能力、边界、persona、default grant。 | research / coding / reviewer。 |
| `Delegator` | 产生 DelegationContract 并分配预算 / grant。 | lead → worker。 |
| `Coordinator` | routing、pipeline、fan-out、debate、swarm、graph。 | static workflow。 |
| `Handoff` | 转移 reply ownership / active agent。 | specialist handoff。 |
| `Synthesizer` | 合并独立结果、证据和冲突。 | map-reduce / lead synthesis。 |
| `SharedBoard` | 显式共享 facts、tasks、artifacts、leases。 | blackboard / task board。 |

### G9：交互、协议与边缘（Interaction, Transport & Interop）

此群处理人、应用、设备和外部 Agent 系统如何进入 / 离开核心。它只转换协议，不能在边缘私自改变任务语义或 policy。

| 子原语 | 责任 | 例子 |
|---|---|---|
| `Channel` | text、voice、image、UI、API、event / webhook 输入输出。 | chat、realtime voice、CLI。 |
| `TransportAdapter` | 内外消息与 event 的 anti-corruption translation。 | HTTP、WebSocket、A2A。 |
| `InteractionPolicy` | confirmation、progress、streaming、question / answer、interrupt。 | human approval UI。 |
| `Presentation` | 将 facts / results 投影为用户或机器可读界面。 | cards、Markdown、JSON。 |
| `Connector` | MCP、OpenAPI、database、cloud service 等受控集成。 | MCP client / server。 |

### G10：组合、配置与运行治理（Composition, Configuration & Runtime Governance）

该群将 contracts 编译为 plans、将 plans boot 为 scoped instances，并管理 rollout、health、config、feature selection 和生命周期。它不应与动态创造群混淆：组合选择已存在能力，创造产生新能力。

| 子原语 | 责任 | 典型形式 |
|---|---|---|
| `Profile / Bundle` | 声明静态组合候选。 | YAML / typed config。 |
| `Resolver` | 解析依赖、config、schema、compatibility。 | DAG resolver。 |
| `PlanCompiler` | 生成 Capability / Control / Scope plans。 | immutable plan hash。 |
| `Bootstrapper` | 按 plan 创建 scope、provider、fiber、health checks。 | boot lifecycle。 |
| `LeaseManager` | 生命周期、drain、quiesce、dispose。 | scopes / jobs / plugins。 |
| `RuntimePolicy` | concurrency、backpressure、recovery、circuit breaker。 | run governor。 |

### G11：创造、学习与发布（Creation, Learning & Evolution）

创造群让系统安全演化。它不会直接给 Agent“任意代码执行”权，而是将新能力变成带 provenance、tests、policy 和 revision 的 Artifact。该群覆盖 self-improvement、tool authoring、prompt evolution、skill packaging、config generation 和 release governance。

| 子原语 | 责任 | 生命周期 |
|---|---|---|
| `CapabilityArtifact` | immutable source + contract + dependency lock + evidence。 | draft → verified。 |
| `ArtifactValidator` | parse、schema、static analysis、contract / effect checks。 | declared → verified。 |
| `Experiment` | fake provider、fixture、shadow replay、HMR。 | verified → staged。 |
| `PromotionController` | 将 artifact 变为 plan revision。 | staged → active。 |
| `ReleaseManager` | version、approval、catalog、deprecation、rollback。 | active → release / retire。 |
| `LearningPolicy` | 何时产生 / 接受 memory 或 artifact proposal。 | evidence-driven。 |

### G12：证据、评估与运营（Evidence, Evaluation & Operations）

此群使系统可解释、可测试、可改进；它不能反向成为核心 truth source。行业框架普遍把 traces、evaluation、guardrail observations 作为独立运行关注面；LCA 将它们约束为 Facts 的投影与验证。[1] [2]

| 子原语 | 责任 | 样例 |
|---|---|---|
| `Journal / Ledger` | append-only facts、provenance、hash、replay。 | run trace。 |
| `EvidenceStore` | 支撑 fact 的大对象、文件、screenshots、retrieval snippets。 | content-addressed evidence。 |
| `TraceProjection` | 时间线、topology、span、cost、decision graph。 | developer trace。 |
| `Metric / SLO` | latency、cost、success、tool error、safety rate。 | operational dashboard。 |
| `Evaluation` | criteria、dataset、simulation、grader、regression test。 | golden trace / scenario eval。 |
| `Incident / Replay` | 故障定位、deterministic replay、postmortem。 | failed run review。 |

## 5. 关系代数：群之间只能用有限关系连接

系统不是由目录邻接组成，而是由可审计的边连接。允许的关系种类必须有限；任何新 relation 都需要 ADR，因为它意味着新的耦合方式。

| 关系 | `A → B` 的意义 | 允许方向 | 禁止的误用 |
|---|---|---|---|
| `provides` | A 为 B 或某 capability 提供实现。 | G10 / provider → consumer。 | 业务 plugin 直接替换 kernel。 |
| `requires` | A 在其 contract 中消费 B 的 capability。 | 按 DAG。 | 通过 global / service locator 隐式读取。 |
| `contributes_to` | A 向 B 的 Control Slot 提供条目。 | any contribution → G0 slot。 | plugin 自己调用下一个 phase。 |
| `reads_fact` | A 读取 typed fact / projection。 | fact → consumer。 | 读取未授权 state 或 live object。 |
| `emits_fact` | A 产生可追加事实。 | contribution → G12 ledger。 | 直接修改历史。 |
| `governs` | A 对 B 的 candidate 产生 allow / deny / transform / ask。 | G6 → Decision / Command。 | policy 执行 world effect。 |
| `executes` | A 代表已通过 command 触达外部世界。 | G7 provider → environment。 | Reasoner 直接调用 tool。 |
| `delegates` | A 将 Contract 子集交给 B。 | G8 role / agent → child scope。 | grant / budget 扩大。 |
| `projects` | A 将 facts / plans 转为 view。 | source → G9 / G12 projection。 | view 反写事实。 |
| `revises` | A 提出下一个 immutable Plan / Artifact version。 | G11 → G10 safe boundary。 | 运行中就地修改 active plan。 |
| `evaluates` | A 对 artifact / run / result 产生 criterion evidence。 | G12 → G11 / G6。 | evaluator 静默改变业务结果。 |

四条全局边约束必须永远成立：**authority 只能向下衰减；effect 只能向外穿过 ExecutionKernel；facts 只能追加；plan revision 只能在 safe boundary 生效。**

## 6. 组合语法：从声明到一个可解释 run

### 6.1 组合输入与编译输出

```text
Identity + TaskContract + Profile + Environment + Available Artifacts
                              │
                              ▼
                         Resolve / Validate
                              │
                              ▼
        CapabilityPlan + ControlPlan + ScopePlan = CompiledRunPlan
                              │
                              ▼
               Boot scoped instances / run RuntimeKernel
                              │
                              ▼
        Facts → projections → evidence → optional PlanRevision
```

| 输入 | 负责回答 | 不得包含 |
|---|---|---|
| `Profile` | 选择哪些 release capabilities 和 config。 | runtime state、secret plaintext、任意 Python expression。 |
| `TaskContract` | 目标、outcome、budget、deadline、risk、approval。 | provider implementation details。 |
| `Environment` | ExecutionSpace、device、network、workspace、available capability。 | policy bypass。 |
| `Artifact` | 可验证候选能力及其 revision。 | 活的 ctx / closure / mutable state。 |
| `CompiledRunPlan` | 真实生效的 provider、slots、scope 和 plan hash。 | unresolved alternatives。 |

### 6.2 PluginContract 的最小完整语法

任何插件只有在以下结构齐全时才属于生产系统。字段可随 group 扩展，但不得删除其语义。

```yaml
id: act.constraint.network-egress
contract:
  identity:
    group: act
    role: constraint
    version: 1
  contribution:
    slot: act.constrain
    operation: veto                 # collect | select | transform | veto | execute | project
    priority: 220
    activation: "task.effects contains network"
    merge: deny_wins
  consumes:
    facts: [command.envelope, task.contract, execution.space]
    capabilities: [network.policy.read]
  produces:
    facts: [policy.verdict]
    capabilities: []
  authority:
    grant: [network.policy.read]
    effects: [none]
    state_owner: none
  scope:
    allowed: [run, invocation]
    visibility: internal
  lifecycle:
    lease: invocation
    dispose: none
  evidence:
    descriptors: [policy.egress.checked, policy.egress.denied]
    replay: deterministic
  verification:
    fixtures: [network-egress-allow, network-egress-deny]
    properties: [never_expands_grant]
```

**声明不允许包含 `next_phase`、`call_runtime_loop`、任意 `ctx`、裸 secret、无类型 state mutation 或未声明 effect。** 这些是内核语义，不是贡献属性。

### 6.3 六类 contribution operation

| operation | 能做什么 | 不能做什么 | 常见归属 |
|---|---|---|---|
| `collect` | 收集候选 facts / capabilities。 | 选择最终模型上下文。 | sensor、retriever。 |
| `select` | 按预算、相关性或确定性规则选取集合。 | 产生 world effect。 | context selector、model router。 |
| `transform` | 将 typed input 变为 typed output。 | 提升 grant、删除 evidence。 | normalizer、prompt renderer、decision governor。 |
| `veto` | 只允许 deny / ask / narrow。 | allow 超出默认上限。 | authorization、budget、constraint、stop。 |
| `execute` | 在已授权 envelope 下执行操作。 | 自己生成 / 扩大 envelope。 | tool provider、job executor。 |
| `project` | 从 facts / plan 派生外部视图。 | 修改 truth。 | UI、trace、metric、report renderer。 |

这六类操作比“before / after hook”更强，因为每一类可推导静态限制、排序、失败语义和测试要求。

## 7. 填空决策树：新逻辑到底坐在哪里

| 先问的问题 | 若答案为“是” | 应放置的位置 | 反例 |
|---|---|---|---|
| 它维持所有 profile 都必须成立的因果 / 安全不变量吗？ | 是 | G0 Kernel，需 ADR。 | 不把“预算绝不能被绕过”做成普通 plugin。 |
| 它描述谁、目标、成功标准、风险或授权前提吗？ | 是 | G1 Contract。 | 不把退款审批只放在 tool docstring。 |
| 它描述当前何时何地、谁可见、能访问什么环境吗？ | 是 | G2 Spacetime。 | 不从 global workspace 偷读 deadline。 |
| 它是已发生事实、当前投影还是跨 run 知识？ | 是 | G3；按事实 / state / memory 分类。 | 不把 Journal event 写进 working memory。 |
| 它把外部信号变成 context / evidence 吗？ | 是 | G4 Sensor / Retriever / Provenance。 | 不在 Reasoner 内直接请求网页。 |
| 它生成或评价候选理解、计划、答案吗？ | 是 | G5 Cognition。 | 不让 Critic 直接调用 tool 修复。 |
| 它允许、拒绝、收窄、审批、计费、停止或重试吗？ | 是 | G6 Control Slot。 | 不把 auth 隐藏在某一个 provider。 |
| 它改变外部世界、运行任务、写文件、发消息、调用 API 吗？ | 是 | G7 Operation / Provider，必须接 CommandEnvelope。 | 不在 policy 中执行退款。 |
| 它把工作分给别的 Agent 或合并其结果吗？ | 是 | G8 Collaboration。 | 不以普通 tool call 传递未缩减 grant。 |
| 它把输入输出翻译为 API、UI、voice、MCP、A2A 吗？ | 是 | G9 Interaction / Interop。 | 不在 HTTP controller 改业务 policy。 |
| 它选择、安装、编译、启动、升级或关闭已有能力吗？ | 是 | G10 Composition。 | 不在 Agent 逻辑里手工 `new` service。 |
| 它发明、测试、升级或发布新能力吗？ | 是 | G11 Evolution。 | 不把 source import 当作发布。 |
| 它解释、测试、评价、监控或回放已发生行为吗？ | 是 | G12 Evidence / Evaluation。 | 不让 dashboard 反写 truth。 |

## 8. 模式目录：业界 Agent 模式只是 Plan 模板

一个模式不是新的框架，也不是新的顶层目录；它是由上述群与关系编译出的 `PlanTemplate`。这让系统既能覆盖行业概念，又避免“每看到一种模式就新建一套 Agent”。

| 模式 | 组成 | 适用条件 | 关键约束 |
|---|---|---|---|
| **单次增强 LLM** | G4 context + G5 prompt / reasoner + G9 presentation。 | 确定性问题、无需多步行动。 | 不伪装成 agent loop。 |
| **RAG / grounded answer** | G3 knowledge + G4 retrieve / select + G5 reason + G12 citation evaluation。 | 主要难题是检索与引用。 | evidence / freshness 必须可见。 |
| **固定工作流 / prompt chain** | G5 TaskGraph + G6 gate + G7 optional operations。 | 子任务顺序已知。 | 使用静态 WorkflowPlan，不需要自由 planner。 |
| **Routing** | G5 classifier / selector + G8 handoff / route。 | 输入类型可分、专家边界明确。 | route 是 Decision fact，不是 if scattered in UI。 |
| **Parallel / voting** | G8 fan-out + G12 evaluator / synthesizer。 | 子任务独立或需要多视角置信度。 | budget、merge、failure quorum 明确。 |
| **Orchestrator-workers** | G5 planner + G8 delegation + G8 synthesis。 | 子任务数量 / 结构未知。 | DelegationContract 衰减 grant 和 budget。 |
| **Evaluator-optimizer** | G5 generator + critic + replan；G12 criteria。 | 有清晰可测改进标准。 | 必有 stop / diminishing-return budget。 |
| **Tool-using autonomous loop** | G4 observe + G5 decide + G6 control + G7 execute。 | 步数未知且需环境反馈。 | command envelope、approval、stop policy。 |
| **Human-in-the-loop transaction** | G1 approval + G6 ask / veto + G9 interaction + G7 resume。 | 高风险、歧义、不可逆 effect。 | pause 与 resume 是 fact / scope transition。 |
| **Multi-agent team** | G8 team / coordinator + G3 shared board + G6 delegation control。 | 角色可分、并行有收益。 | 不共享隐式 AgentState。 |
| **Long-running / scheduled agent** | G10 scheduler / lease + G7 async jobs + G2 temporal facts。 | 任务跨 turn / process / event。 | 需要 idempotency、checkpoint、recovery。 |
| **Realtime / voice / device agent** | G9 channel + G2 device space + G7 streaming executor。 | 多模态、低延迟交互。 | UI / device permission 与 cognition 分离。 |
| **Self-evolving agent** | G11 artifact lifecycle + G12 eval + G10 PlanRevision。 | 有安全测试环境与提升审查。 | 不能把 runtime experiment 直接发布。 |

## 9. 反垃圾守则：不在补丁上继续补丁

下列十条是所有新 PR 的架构门禁。任何一条被违反，必须先修正基础关系，而不是继续加 adapter。

| 编号 | 门禁 |
|---|---|
| **AG1** | 不新增无 group / slot / scope / effect / evidence 的生产逻辑。 |
| **AG2** | 不新增全局 service locator、global workspace read 或 hidden Context mutation。 |
| **AG3** | 不新增 `before_*` / `after_*` Hook；新控制逻辑必须进入有限 Control Slot。 |
| **AG4** | 不新增第二个 state truth source；所有可恢复状态由 facts / reducer 导出。 |
| **AG5** | 不新增 tool / provider 对 policy、grant、budget 的私有解释；统一经 CommandEnvelope。 |
| **AG6** | 不新增为一个模式特设的 top-level Agent loop；优先写 PlanTemplate。 |
| **AG7** | 不允许 dynamic code 直接拿 live Context、Journal、secret 或生产 provider。 |
| **AG8** | 不允许 profile config 改内核时序、authority ceiling 或事实提交语义。 |
| **AG9** | 不允许 observability projection、UI 或 dashboard 回写 business truth。 |
| **AG10** | 新概念必须指定替代 / 合并 / 删除的旧概念；不保留永久 parallel track。 |

## 10. 代码与目录的目标映射

现有目录不是失败，而是迁移输入。未来迁移以概念归属为依据，而不是将所有文件机械移动。

| 现有家族 | 目标主群 | 迁移方向 |
|---|---|---|
| `plugins/sensors`, `perceive` | G4 | 转为 `collect / admit / select` contributions。 |
| `plugins/reasoner`, `brain`, `critic` | G5 | 转为 model / prompt / planner / critic contributions。 |
| `gates`, `guards`, `runtime` | G6 | 将固定 gate / hook 收敛为 typed ControlPlan entries。 |
| `body`, `tools`, `providers` | G7 | declaration / provider / executor 分离，统一 envelope。 |
| `memory`, `skills`, `workspace` | G3 / G4 | 区分 knowledge、memory、context、environment。 |
| `collaboration`, `strategies`, `team_lead`, `synthesizer` | G8 | 转为 topology / delegation / synthesis plan templates。 |
| `gateway`, transport, MCP / A2A | G9 | 仅做 anti-corruption 与 interaction policy。 |
| `bundles`, `compose`, `registries`, `loop_drivers` | G10 | Resolver / Compiler / Bootstrap / lease。 |
| `cordis_control`, preset authoring | G11 | Artifact / experiment / promotion / release。 |
| `observability`, `journal`, `evaluation` | G12 | ledger、evidence、projection、eval 分离。 |

## 11. 实施优先级：先坐标，后填空

| 阶段 | 完成标志 | 不应先做的事 |
|---|---|---|
| **A：命名与 schema** | `PluginContract`、LogicAddress、relation algebra、PlanTemplate schema 可校验。 | 再增加一个 hook / gate service。 |
| **B：编译与解释** | CapabilityPlan、ControlPlan、ScopePlan 和 canonical plan hash 落地。 | 继续在 spawn / gateway 写选择逻辑。 |
| **C：唯一内核** | Fiber-only boot、Reducer、CommandEnvelope、run-scoped execution plan。 | 新增动态 Creator feature。 |
| **D：迁移群体** | Perceive、Think、Control、Act、Memory、Collaboration 分批进入 slots。 | 同时重写全部 plugin。 |
| **E：演化系统** | Artifact lifecycle、experiment、promotion、release 完整闭环。 | 允许 model 直接 import source。 |
| **F：删除垃圾** | hooks、legacy maps、untyped meta、global fallbacks 被移除。 | 永久保留 compatibility path。 |

## 参考

[1]: https://developers.openai.com/api/docs/guides/agents "OpenAI Agents SDK guide"
[2]: https://www.anthropic.com/engineering/building-effective-agents "Anthropic: Building effective agents"
[3]: https://arxiv.org/abs/2402.02716 "Understanding the planning of LLM agents: A survey"
[4]: https://adk.dev/sessions/memory/ "Google ADK Memory"
[5]: 2026-08-21-declarative-plugin-constitution-v4.md "声明式插件宪法 v4.0"
[6]: 2026-08-21-code-aligned-architecture-audit.md "代码对齐的第一性原理架构审计"
[7]: ../adr/0068-compiled-plugin-kernel-and-unified-run-plan.md "ADR-0068"
