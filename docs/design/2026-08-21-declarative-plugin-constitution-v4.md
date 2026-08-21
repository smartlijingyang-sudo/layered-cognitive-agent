# 声明式插件宪法 v4.0

**认知闭集 · 原语群化 · 原子控制 · 声明式组合 · 可证明治理**

| 字段 | 值 |
|---|---|
| 日期 | 2026-08-21 |
| 状态 | Draft for ADR Review |
| 作者 | LCA Architecture |
| 前序 | [认知原语插件宪法 v3.0](2026-08-19-cognitive-primitive-constitution-v3.md)、[ADR-0066](../adr/0066-declarative-atomic-control-plugins.md) |
| 不替代 | ADR-0001、ADR-0004、ADR-0005、ADR-0037、ADR-0056、ADR-0061、ADR-0065 |
| 本文角色 | **长期插件目录、边界法与填充路线**；它不自行改变既有认知闭集。 |

> **一句话：系统只拥有有限、稳定的认知原语与控制槽位；所有可变能力都以最小、声明式、可验证的插件贡献给某一原语群。读 Profile 看系统形态，读 ControlPlan 看控制逻辑，读 Manifest 看插件边界，读 Journal 看一次运行为什么如此发生。**

## 0. 为什么需要 v4

v3 已经把 LCA 的方向钉在正确的位置：认知循环是封闭的，原语、策略、群三层不能混淆，状态只能由 Reducer 写入，世界副作用必须经过执行窄门，Journal 是事实来源。[1] ADR-0061 又提供了可解析的插件 Manifest、Capability DAG 与 Resolve/Boot 生命周期。[2] ADR-0066 则把预算、授权、约束、审批、停止等原先容易散落在组合根或 Hook 中的逻辑收敛为有限的 Control Slot。[3]

但“方向正确”并不自动等于“可长期填充”。若没有统一目录，团队会继续以两种方式制造复杂度：一是把每一个新需求命名为一个新的大插件，二是为避免新名字而把不相干策略塞回 `Composer`、`Runtime` 或通用 `guard`。二者都会让配置失去解释能力。当前仓库的插件目录已覆盖 sensors、gates、body、brain、providers、strategies、observability seam、loop drivers 等多个区域，说明基础已具备；同时，目录名称、插件粒度和组合责任仍处于重构收敛期。[4]

v4 的任务不是再发明一个框架，而是提供一套**可被未来十年维护的分类学**。它要求每一个新增插件均能回答六个问题：它服务哪个原语群？进入哪个有限槽位？拥有何种输入输出？能影响哪些事实或副作用？如何与同类组合？何时应该被移除、升级或升格为原语？

## 1. 宪法总纲

### 1.1 三条世界观

**第一，原语有限，策略无限。** 原语是系统不可或缺的概念边界，例如感知、思考、判决、执行、记忆、协作、状态、事实账本与组合。策略是原语内部的具体实现，例如 loop breaker、context budgeter、审批规则、sandbox、检索器或合成器。新增策略是正常演进；新增原语必须解释现有原语为何无法容纳它，并经 ADR 审核。[1]

**第二，变化显式，宪法稳定。** 插件可以替换实现、投稿规则、扩展能力、投影事实；配置可以选择、参数化、关闭或叠加插件。插件和配置不能跳过六步循环、直接修改 AgentState、伪造 Journal 事实、扩大 capability grant，或把世界副作用搬到脑平面。[1] [3]

**第三，配置可阅读，运行可证明。** 配置不是第二种编程语言。它只表达可静态检查的身份、依赖、选择、参数、激活条件、排序与授权引用；复杂算法留在受类型约束的插件实现中。Resolve 证明“能否启动”，ControlPlan 证明“哪些控制会生效”，Journal 证明“实际哪些控制已经生效”。

### 1.2 不可谈判的十条不变量

| 编号 | 不变量 | 机械含义 |
|---|---|---|
| **P1** | 认知闭集 | 默认 loop 固定为 `perceive → think → act → reflect → remember → stop`；Gate 属于 Think，ExecutionControl 属于 Act。 |
| **P2** | 原语唯一归属 | 每个运行时插件恰好声明一个主原语群；跨群能力通过 capability 或已定义 control slot，不靠隐式 import。 |
| **P3** | 单一状态写者 | 只有 `JournalReducer` / 明确的 reducer protocol 能从事件和受控 delta 改写状态。 |
| **P4** | 事实先提交 | 任何控制 verdict、授权、预算拒绝、审批、执行结果和停止结果都必须先以已登记事实提交，再被投影或用于后续轮次。 |
| **P5** | 副作用窄门 | 工具、文件、网络、设备、消息与远程调用只可接收已授权、已约束、可审计的 `ExecutionEnvelope`。 |
| **P6** | 权限只衰减 | 子代理、派生 envelope、重写策略和临时 mount 的权限均必须是父权限的子集。 |
| **P7** | 同槽位单调 | 拒绝、停止、预算耗尽与安全约束不能被后续插件放宽；重写只能保持或收紧权限。 |
| **P8** | 观察零控制 | observer / projector 只能读取不可变快照或已提交记录，不能写 State、Decision、Envelope 或 Journal 历史。 |
| **P9** | 组合根闭合 | L4 与 gateway 只请求领域 capability / factory / ControlPlan；不得点名具体策略或创建隐式 fallback。 |
| **P10** | 配置不可执行 | YAML 中不得存在任意表达式、动态 import、网络读取、环境变量散读或未登记事实路径。 |

这些不变量不是文档建议，而是未来架构测试、Manifest Resolver 和 CI 规则的来源。任何不能映射到至少一条不变量的“架构规则”，应先作为团队约定而不是升级为宪法。

## 2. 插件本体论：六层而不是“一层插件”

“一切皆插件”并不等于只有一个 `plugins/` 目录。可长期维护的系统需要区分**概念、能力、实现、组合和实例事实**。v4 使用六层模型；每层只回答一种问题。

| 层 | 名称 | 回答的问题 | 典型对象 | 是否可由用户配置替换 |
|---|---|---|---|---:|
| **L0** | 宪法与协议 | 系统永远如何运作？ | 闭集、Protocol、数据模型、Reducer 权限、effect 规则 | 否；ADR。 |
| **L1** | 原语群与 Seams | 系统有哪些稳定职责域？ | PerceiveService、ExecutionControl、RunLedger、Capability key | 仅可实现，不可任意删除。 |
| **L2** | 原子插件 | 这一项独立变化做什么？ | `sensor.clock`、`control.budget.tool-calls`、`executor.sandbox.local` | 是。 |
| **L3** | Bundle | 一组可复用能力如何协作？ | `safe-tooling`、`human-in-the-loop`、`long-running` | 是。 |
| **L4** | Profile / Role | 某类 Agent 呈现为何种形态？ | coding、research、creator、team-debate | 是。 |
| **L5** | TaskContract / Run facts | 本次运行允许什么、发生了什么？ | grant、预算、风险、审批决定、Observation | 不可被任意配置伪造。 |

**插件是 L2，不是其他五层的代名词。** L0 的固定接口不应被 YAML 改写；L1 的 seam 不应承担业务策略；L3 不应重写控制流；L4 不应直接注册低层对象；L5 是事实，不是“本次随便覆盖的 config”。这一分层让“所有变化都插件化”与“所有边界都清晰”同时成立。

### 2.1 原语、群、插件、策略、实例的定义

| 名称 | 定义 | 例子 | 新增门槛 |
|---|---|---|---|
| **原语** | 不能再被现有原语语义覆盖的稳定职责。 | `Sensor`、`Gate`、`SafeExecutor`、`RunLedger`。 | ADR；需要证明缺口。 |
| **插件群** | 共享输入输出方向、生命周期和所有权的一组原语 / 策略。 | Perceive、Act、Journal。 | 架构评审；通常随原语闭集变化。 |
| **Seam** | 群对外唯一的注册、组装或访问边界。 | `perceive` service、`execution_control_factory`。 | ADR 或契约 PR。 |
| **原子插件** | 只承担一个可独立启停、授权、测试和诊断的变化轴。 | `constraint.network-egress`。 | 普通 PR。 |
| **策略插件** | 向一个控制槽位给出 contribution / verdict 的原子插件。 | `budget.token-limit`。 | 普通 PR；遵守 slot。 |
| **Provider 插件** | 提供可被多个群使用的基础设施实现，不直接定义业务控制。 | LLM、filesystem、sandbox backend。 | 普通 PR。 |
| **Composite / Bundle** | 只声明成员、Patch、依赖和配置；不藏业务判断。 | `safe-network-tool-call`。 | 普通 PR。 |
| **事实** | 一次运行中真实存在、可引用、可审计的输入或结果。 | grant、余额快照、approval resolved。 | Journal descriptor 审核。 |

## 3. 正规范畴图：十二个插件群

v3 的八个概念群是认知语义的核心。为使代码与运维长期可维护，v4 将其展开为十二个**插件群**：八个认知 / 业务群，加四个承重群。承重群不是新认知阶段，也不拥有绕过业务边界的特权。

```text
                 ┌──────────────── Constitution / Contracts ────────────────┐
                 │ L0 protocols · capability keys · schemas · invariants   │
                 └─────────────────────────────────────────────────────────┘

World / User ──> Perceive ──> Think ──> Gate ──> Act ──> Reflect ──> Remember
                     ▲           │           │        │                         │
                     │           └───────────┴────────┴──────> Stop             │
                     │                                                           │
                     └────────── Collaboration / Inbox / Memory retrieval ─────┘

       State / Reducer  <── committed facts ──>  Journal / Evidence
       Context / Budget <── constrained input ─>  Execution / Authorization
       Composition      <── resolved plan ──────>  Environment / Providers
       Observability    <── read-only projection of committed facts ───────────
```

| # | 插件群 | 核心使命 | 主入口 / Seam | 允许的主输出 | 绝对禁止 |
|---:|---|---|---|---|---|
| G0 | **Kernel & Contract** | 定义不变量、Protocol、类型、capability 和解析规则。 | `contracts/`、Manifest resolver | 类型化契约、错误码、解析诊断 | 业务策略、具体 IO。 |
| G1 | **State & Task** | 管理状态、任务契约、目标、预算引用与 reducer。 | `JournalReducer`、`TaskContract` | State delta 应用、不可变 view | 插件任意写状态。 |
| G2 | **Perceive & Context** | 将可信世界事实编排为 ContextManifest。 | `PerceiveService.assemble()` | `PerceptionDelta`、ContextManifest | 工具执行、直接造 Decision。 |
| G3 | **Think & Deliberation** | 从 context 产生候选意图、计划与反思。 | `Brain` / `Reasoner` factory | Decision、Reflection、候选计划 | 写世界、修改 grant。 |
| G4 | **Gate & Policy** | 对候选 Decision 做确定性治理。 | `think.guard` registry | DecisionVerdict、PolicyFact | 工具调用、State mutation。 |
| G5 | **Act & ExecutionControl** | 将合法意图变为受控世界结果。 | `execution_control_factory`、Body | Envelope、Observation | 绕过授权 / 账本。 |
| G6 | **Memory & Knowledge** | 治理跨时间记忆、检索、压缩与写入。 | `MemoryService` / MemoryPolicy | Context contribution、WriteSet、commit receipt | 绕过 policy 直接持久化。 |
| G7 | **Collaboration & Inbox** | 管理代理间通信、委派、共享资源和协调。 | Team / message / delegation seam | Message、delegation result、team observation | 直接写他人私有 State。 |
| G8 | **Journal & Evidence** | 提交事实、保存证据、恢复与物化。 | RunLedger / EvidenceStore | JournalRecord、EvidenceRef | 让视图成为事实。 |
| G9 | **Observability & Evaluation** | 对已提交事实做投影、诊断、评测与告警。 | ProjectionRegistry / FactReader | view、score、diagnostic | 影响业务控制或回写账本。 |
| G10 | **Composition & Lifecycle** | 解析 Profile、装配群服务、闭合对象图、管理生命周期。 | Resolve / Boot / spawn / driver registry | ResolvedProfile、ControlPlan、live graph | 直接硬编码策略名单。 |
| G11 | **Environment & Interop** | 提供 LLM、模型、存储、沙箱、文件、搜索、MCP/A2A 等基础能力。 | provider seams / bridges | capability provider、transport adapter | 认知编排或业务裁决。 |

### 3.1 群关系法：只允许有限方向

下表比“可以互相调用”更重要。每个群只能看到被允许的稳定输入；任何未列出的关系必须经 capability、Journal 事实或新 ADR 显式引入。

| 从 | 可以依赖 | 交换方式 | 不可依赖 / 不可交换 |
|---|---|---|---|
| G2 Perceive | G1 StateView、G6 查询、G7 Inbox 事实、G8 已提交记录、G11 受限读取 provider | `ContextCandidate` / `PolicyFact` | G3 Decision、G5 Tool execution、可变 State。 |
| G3 Think | G1 StateView、G2 ContextManifest、G11 LLM / model provider | Decision / Reflection | G5 executor、G8 未提交私有载荷。 |
| G4 Gate | G1 StateView、G3 Candidate Decision、G8 已提交 PolicyFact | DecisionVerdict | G5 executor、G6 memory write、裸世界读取。 |
| G5 Act | G1 StateView、G3 / G4 决策、G7 transport、G8 ledger、G11 provider | Envelope / Observation | 直接 State mutation、未验证 grant。 |
| G6 Memory | G1 StateView、G5 Observation、G3 Reflection、G8 evidence | Context contribution / WriteSet | 直接改 prompt、直接写其他 Agent memory。 |
| G7 Collaboration | G1 TaskContract / grant、G5 受控 transport、G8 facts | Message / delegation request | 跨代理私有 State、绕过 Act 发送。 |
| G8 Journal | 所有群的已登记事实 | append / read / evidence ref | 业务决策、投影反写。 |
| G9 Observe | 仅 G8 已提交事实与不可变 plan | projection / score | any control verdict、状态变更。 |
| G10 Compose | 所有群的 Manifest / capability | Resolve / Boot / factory | 具体业务 if、运行期临时 fallback。 |
| G11 Environment | G10 装配、G5 Act、G2 受限 Perceive、G3 Think | typed provider capability | 对认知策略的反向控制。 |

## 4. 原子插件目录：可填充的正名空间

### 4.1 命名规则

所有 ID 使用 **`<group>.<role>.<subject>[.<variant>]`**。`group` 对应十二个插件群，`role` 描述它是 sensor、policy、provider、executor、projector、registry 或 bridge，而不是模糊的 `utils`、`helpers`、`default`。例如：

```text
perceive.sensor.workspace-instructions
perceive.policy.context-budget
think.renderer.chat
think.reasoner.prompt
policy.gate.repeat-tool-call
act.authorize.capability-grant
act.budget.tool-calls
act.constraint.network-egress
act.executor.safe-tool
memory.policy.retention
collab.policy.message-acl
journal.store.filesystem
observe.projector.otel
compose.driver.cognitive
provider.sandbox.local
```

为兼容既有 `PluginKind`，`kind` 仍只使用 `seam | provider | primitive | composite | driver | bridge`；上面的 `role` 是 Manifest `meta` 中的**语义分类**，不新增平行 Kind 枚举。[2] 这让现有 Resolver 可平滑演进，同时让目录和检查器获得更精确的语义。

### 4.2 每群的正名插件族

下表不是“必须一次性实现的 backlog”。它是未来命名与职责的**允许地址空间**。状态分为：**Now**（优先迁移 / 实现）、**Later**（已定义契约、按产品需要实施）、**Reserved**（只保留名称与边界，禁止空实现或提前接线）。

| 群 | 原子插件族 | 初始成员（示例） | 状态 | 责任边界 |
|---|---|---|---|---|
| G1 State | state.reducer / state.policy / state.goal / state.budget | `state.reducer.journal`、`state.goal.stack`、`state.budget.snapshot`、`state.policy.task-contract` | Now / Later | 唯一拥有 State 演进和任务事实的类型化投影。 |
| G2 Perceive | perceive.sensor / perceive.policy / perceive.resolver | `sensor.clock`、`sensor.inbox-facts`、`sensor.workspace-artifacts`、`sensor.workspace-instructions`、`sensor.skill-catalog`、`sensor.team-inbox`、`policy.context-budget`、`resolver.evidence-conflict` | Now | 只把可信事实贡献给 manifest。 |
| G3 Think | think.reasoner / renderer / critic / router / planner | `reasoner.prompt`、`renderer.chat`、`renderer.code`、`critic.simple`、`router.skill`、`planner.decompose` | Now / Later | 只产生候选意图、反思或受限计划。 |
| G4 Gate | policy.gate / policy.degrade / policy.decide | `gate.repeat-tool-call`、`gate.progress-loop`、`gate.safety`、`gate.action-shape`、`degrade.safe-response` | Now / Later | 确定性裁决，输出 verdict 与 policy fact。 |
| G5 Act | act.authorize / budget / constraint / executor / recovery | `authorize.capability-grant`、`authorize.high-risk-approval`、`budget.tool-calls`、`budget.token-cost`、`constraint.network-egress`、`constraint.fs-scope`、`constraint.idempotency`、`executor.safe-tool`、`recovery.retry` | Now | 决策到 Observation 的唯一副作用路径。 |
| G6 Memory | memory.store / query / policy / compactor / screening | `store.four-layer`、`query.semantic`、`policy.admission`、`policy.retention`、`compact.summary`、`screen.poison` | Later | 检索可贡献 context；写入必须有 policy receipt。 |
| G7 Collab | collab.transport / policy / strategy / synthesizer / delegate | `transport.team-message`、`policy.message-acl`、`policy.delegation-budget`、`strategy.debate`、`strategy.fan-out`、`synthesizer.evidence-weighted` | Now / Later | 以消息 / 委派事实协作，不共享私有可变状态。 |
| G8 Journal | journal.ledger / store / evidence / descriptor / materializer | `ledger.run`、`store.filesystem`、`evidence.filesystem`、`descriptor.registry`、`materializer.manifest` | Now | 唯一事实提交、证据引用和恢复协议。 |
| G9 Observe | observe.projector / exporter / scorer / inspector / alert | `projector.console`、`projector.sse`、`exporter.otel`、`exporter.langfuse`、`scorer.trace`、`inspector.control-explain` | Now / Later | 对已提交事实生成可丢弃视图。 |
| G10 Compose | compose.resolver / registry / factory / driver / bundle | `resolver.profile`、`registry.control-slots`、`factory.agent`、`driver.cognitive`、`driver.dsh`、`bundle.safe-tooling` | Now | 解析、装配、生命周期与整段 loop 选择。 |
| G11 Provider | provider.llm / sandbox / storage / search / tools / interop | `llm.openai-compatible`、`sandbox.local`、`storage.filesystem`、`search.web`、`bridge.mcp`、`bridge.a2a` | Now / Later | 提供环境能力，不拥有认知策略。 |
| Reserved | reserved.* 仅登记、不接线 | 见 §9 | Reserved | 为可预见能力占位，防止未来命名冲突和概念漂移。 |

### 4.3 群内最小粒度判定

不是每个辅助函数都应成为插件。一个候选必须满足至少两项，才值得成为原子插件：可以独立启停、可以独立替换、需要独立参数、需要独立授权 / effect 声明、需要独立审计、需要独立顺序 / 聚合语义、需要独立测试矩阵。否则它应留在所属插件实现内部。

| 候选 | 正确归属 | 是否独立插件 | 理由 |
|---|---|---:|---|
| “本轮最多 20 次工具调用” | `act.budget.tool-calls` | 是 | 独立参数、拒绝语义、审计与测试。 |
| “当模型输出非法 JSON 时重试一次” | `think.reasoner.prompt` 内部 retry policy | 通常否 | 只改变一个 reasoner 实现的局部算法。 |
| “只允许访问 github.com” | `act.constraint.network-egress` | 是 | 独立授权边界与 effect 收紧。 |
| “对 4xx 网络错误做指数退避” | `act.executor.http` 内部 | 通常否 | executor 的传输可靠性细节。 |
| “发生高风险动作必须人工确认” | `act.authorize.high-risk-approval` | 是 | 独立状态机、事实、恢复与 HIL 语义。 |
| “字符串截断到 8K 字符” | renderer / compactor 内部 | 否 | 没有独立领域语义；除非成为 Context Budget 策略。 |
| “将已提交轨迹导出 OTel” | `observe.exporter.otel` | 是 | 独立 lifecycle、外发策略与安全边界。 |

## 5. Control Slot 宪章：控制全面插件化，但控制面有限

Control Slot 是“何处可插入策略”的白名单。它用**类型、聚合器、失败模式和事实记录规则**定义，而不是用 `before_*` / `after_*` 等无限事件名定义。任何新策略都先进入一个现有 slot；如果没有合适 slot，先写问题说明，再决定是扩展原语还是开 ADR。

### 5.1 规范控制槽位

| Slot | 所属群 / 时机 | 输入 | 贡献输出 | 默认聚合 | 初始状态 |
|---|---|---|---|---|---|
| `perceive.collect` | G2；收集世界事实 | `StateView`、JournalCursor | `ContextCandidate[]` | stable merge | Now |
| `perceive.admit` | G2；事实准入 | candidate、authority、classification | Admit / redact / reject | deny-on-reject | Later |
| `perceive.select` | G2；构造 Manifest | candidates、任务预算 | selected manifest items | deterministic budget + resolver | Now |
| `think.prepare` | G3；模型调用前 | manifest、role、task contract | PromptPlan / model route | single renderer + policy chain | Later |
| `think.guard` | G4；候选决策后 | StateView、Decision、PolicyFact | `DecisionVerdict` | `stop > ask_human > deny > rewrite > allow` | Now |
| `act.plan` | G5；Decision 到 Envelope | Decision、grant、tool schema | `ExecutionEnvelope[]` | deterministic expansion | Later |
| `act.authorize` | G5；执行前 | envelope、grant、risk、approval fact | AuthorizationVerdict | deny-on-any-deny | Now |
| `act.budget` | G5；执行前 | envelope、budget snapshot、pricing ref | BudgetVerdict | deny-on-exhausted | Now |
| `act.constrain` | G5；执行前 | envelope、policy fact | ConstraintVerdict / narrowed envelope | meet / only narrow | Now |
| `act.execute` | G5；副作用 | authorized envelope | Observation | executor selected by action kind | Now |
| `act.recover` | G5；失败后 | failure、idempotency、retry policy | retry / stop / observation | explicit retry budget | Later |
| `remember.admit` | G6；写入前 | WriteSet、classification、retention | MemoryVerdict | deny-on-any-deny | Later |
| `remember.commit` | G6；持久化 | admitted WriteSet | commit receipt | transactional / explicit partial | Later |
| `collab.authorize` | G7；发消息 / 委派前 | sender、audience、grant、message | CollaborationVerdict | deny-on-any-deny | Later |
| `collab.route` | G7；通信路由 | approved request | delivery plan | deterministic routing | Later |
| `stop.decide` | G1；一轮结束 | StateView、turn、budget、terminal facts | StopVerdict | stop-on-any-hard-stop | Now |
| `observe.project` | G9；提交后 | committed record | no business output | no aggregation | Now |

**限制**：`act.execute` 是唯一可产生世界副作用的槽位；`observe.project` 永远不是控制槽位；`think.prepare` 不能直接读取未准入事实；`collab.route` 必须经 Act / Transport，而不是成为第七个认知阶段。

### 5.2 Slot 的组合、排序与冲突

每个 slot 都有一个群服务 / registry 作为唯一投稿面。插件通过 `register(slot, id, contribution)` 加入，不得提供 `list[Plugin]`、使用魔法 `ctx` 字段或让 L4 按 ID 手工串联。排序只接受三个来源：DAG 依赖、显式 `before/after` 的同槽位偏序、无关系项的 profile 稳定顺序。

```yaml
id: act.constraint.network-egress
control:
  slot: act.constrain
  order:
    after: [act.authorize.capability-grant]
    before: [act.executor.safe-tool]
  aggregate: narrow_only
  failure_mode: deny
  activation:
    all:
      - fact: execution.action_type
        equals: USE_TOOL
      - fact: execution.tool.tags
        contains: network
```

Resolver 必须拒绝循环顺序、跨 slot 排序、不可比较的聚合器、无事实所有者的 activation path、以及可能扩大 envelope scope 的 rewrite。运行期则记录每个贡献的 `activated | skipped | denied | rewritten | failed` 结果及其 `plan_ref`。

### 5.3 激活 DSL

`activation` 是受限数据，而不是隐藏脚本。它只可以引用已登记的不可变事实，并支持以下运算：`all`、`any`、`not`、`exists`、`equals`、`in`、`contains`、`lt/lte/gt/gte`、`matches-enum`。它不得执行 I/O、读取对象属性链、调用函数、访问环境变量、解密 secret 或引用上一次插件的可变私有变量。

| 事实命名空间 | 事实 owner | 可用于 activation | 示例 |
|---|---|---:|---|
| `task.*` | TaskContract | 是 | `task.risk_level >= HIGH` |
| `state.*` | StateView | 是，仅读 | `state.step >= 20` |
| `execution.*` | ExecutionEnvelope | 是 | `execution.tool.tags contains network` |
| `budget.*` | Budget snapshot | 是 | `budget.remaining_calls <= 0` |
| `approval.*` | 已提交 approval fact | 是 | `approval.status == resolved` |
| `policy.*` | 已提交 PolicyFact | 是 | `policy.loop_risk == high` |
| `env.*` / `secret.*` | 无 | 否 | 必须在 Resolve 的受控 secret ref 机制处理。 |
| `plugin.*` 私有变量 | 无 | 否 | 防止隐式时序和状态泄漏。 |

## 6. 契约：插件之间如何只通过清晰关系协作

### 6.1 扩展现有 Manifest，而不新建平行 schema

现有 `PluginDefinition` 已承载 ID、Config、capability、层、kind、effect 与测试身份。[2] v4 在该 Manifest 的 `meta` 中增加一个**可选但严格校验的** `architecture` 区段；不引入第二套 `PrimitiveManifest`，也不在 YAML 再重复业务事实。

```yaml
id: act.budget.tool-calls
$module: lca.plugins.act.budget_tool_calls
architecture:
  group: act
  role: budget
  primary_slot: act.budget
  ownership:
    reads: [task.contract, budget.snapshot, execution.envelope]
    emits: [policy.budget.checked, policy.budget.denied]
    writes: []
  authority:
    requires: [budget.read]
    grants: []
  control:
    activation: { fact: execution.action_type, in: [USE_TOOL, DELEGATE] }
    aggregate: deny_on_exhausted
    failure_mode: deny
    monotonicity: deny_only
  lifecycle:
    scope: run
    concurrency: serialized-per-run
  compatibility:
    contract_version: "1"
    replaces: []
```

| Manifest 项 | 规则 | Resolve 校验 | Run 校验 |
|---|---|---:|---:|
| `group` / `role` | 一个主群、一个语义角色。 | 合法枚举、目录与 role 一致。 | 用于 inspect / audit。 |
| `primary_slot` | 控制插件必须恰有一个；provider / observer 可为空。 | slot 存在、输入输出契约相容。 | registry 只调用该契约。 |
| `ownership.reads/emits/writes` | 宣称其读取与产生的事实。 | descriptor / fact path 已登记。 | 记录实际访问审计。 |
| `authority` | 声明所需、可衰减的 capability。 | grant 与 effects 不冲突。 | envelope / provider 再强制。 |
| `control` | 激活、聚合、失败与单调性。 | DSL、合并、排序、fail mode 合法。 | 记录 verdict。 |
| `lifecycle` | boot/run/agent/turn 范围与并发语义。 | 资源 scope 相容。 | disposer / locks 可验证。 |
| `compatibility` | 版本、替代与迁移路径。 | 版本政策和弃用引用。 | 诊断与 migration 选择。 |

### 6.2 四种契约，四种问题

| 契约 | 问题 | 所在位置 | 示例 |
|---|---|---|---|
| **Type Contract** | 输入输出的类型和不变量是什么？ | `contracts.protocols` | `Gate.enforce(StateView, Decision) -> DecisionVerdict`。 |
| **Capability Contract** | 谁提供 / 消费什么能力？ | `Capability[T]` + Manifest | `requires=[RUN_LEDGER, BUDGET_SNAPSHOT]`。 |
| **Control Contract** | 在哪里激活、怎样组合、失败如何处理？ | Control Slot schema | `act.budget` + deny-on-exhausted。 |
| **Evidence Contract** | 要记录哪些原因、结果与证据？ | EventDescriptor / Evidence policy | `PolicyBudgetDenied(plugin_id, plan_ref, ...)`。 |

任何插件只声明 Type 与 Capability 而没有 Control / Evidence 的，不得进入影响决策、授权、预算、停止或副作用的控制路径。任何 observer 只可拥有 Type、Capability 与 Evidence contract，不能拥有 Control contract。

### 6.3 所有权矩阵

| 资源 | 唯一 owner | 可读者 | 可写者 | 禁止者 |
|---|---|---|---|---|
| `AgentState` | G1 Reducer | 所有阶段经 `StateView` | Reducer | Sensor、Gate、Body、Observer、Tool。 |
| `ContextManifest` | G2 PerceiveHub | G3 Think | G2 组装者 | Tool、observer。 |
| `Decision` | G3 Think + G4 Gate verdict | G5 Act、G1 Stop | Think 产生；Gate 仅受限 rewrite | Body、Memory、Observer。 |
| `ExecutionEnvelope` | G5 ExecutionControl | authorize / budget / constrain / executor | Act 的单调 pipeline | Think、observer。 |
| `Observation` | G5 executor | Reflect、Memory、Stop、Journal | executor | Gate、observer 伪造。 |
| `MemoryWriteSet` | G6 Memory | MemoryPolicy、Journal | MemoryPolicy commit | Body、Team transport。 |
| `CapabilityGrant` | TaskContract / authenticated principal | all enforcement points | authorized grant resolver | 子代理、普通策略插件。 |
| `JournalRecord` | G8 RunLedger | all readers | RunLedger append only | Projector、gateway 私有写入。 |
| `EvidenceRef` | G8 EvidenceStore | authorized readers | EvidenceStore prepare/commit | direct filesystem path consumers。 |

### 6.4 生命周期与资源作用域

| Scope | 适用插件 | 创建时机 | 释放时机 | 示例 |
|---|---|---|---|---|
| `process` | immutable descriptor / static provider registry | Boot | process stop | event descriptor registry。 |
| `profile` | immutable plan template / bundle registry | Resolve / Boot | profile scope dispose | ControlPlan template。 |
| `agent` | role-bound brain / memory service | agent spawn | agent dispose | modular brain、role renderer。 |
| `run` | ledger、budget snapshot、approval state | run start | terminal materialization | RunLedgerHandle。 |
| `turn` | manifest / transient plan | turn start | turn end | ContextManifest、prompt plan。 |
| `invocation` | envelope / retry context | action invoke | observation / terminal fail | idempotency key。 |

插件不得把较短 scope 的对象缓存到较长 scope，也不得通过 global singleton 偷渡 run 或 agent 的私有事实。`Resolve → Boot → Run → Dispose` 的既有生命周期仍是总框架；v4 只将作用域语义显式化。[2]

## 7. 配置宪章：读 Profile 即读系统

### 7.1 六层优先级与禁止覆盖

配置合并按照下面的单向优先级进行。低层只提供可复用声明，高层只选择或收紧；任何层都不能扩大任务 grant、绕开 effect policy 或改变协议闭集。

```text
Null Baseline
  < Base Bundle
  < Domain / Safety Bundle
  < Profile Patch
  < Role Selection
  < TaskContract + authenticated Grant
  < approved Runtime Override (最窄、可审计、短生命周期)
```

| 层 | 可做 | 不可做 |
|---|---|---|
| Null Baseline | 明示每个原语的 no-op / deny-by-default 行为。 | 偷装“默认便利插件”。 |
| Base Bundle | 提供标准实现与必须的 seam。 | 注入产品场景或秘密。 |
| Domain / Safety Bundle | 组合领域策略，如 coding、research、HIL。 | 重写其他 Bundle 的控制流程。 |
| Profile Patch | 选择成员、调参数、禁用非必需能力。 | 扩大 effect / grant。 |
| Role | 指定 persona、专业能力、渲染方式。 | 成为工具授权旁路。 |
| TaskContract + Grant | 指定本 run 目标、预算、风险、允许动作。 | 覆盖系统安全下限。 |
| Runtime Override | 处理受控 debug / operator 事件。 | 持久化、匿名、无 Journal 记录。 |

### 7.2 Bundle 是装箱单，不是微型框架

Bundle 只能包含：插件成员、严格 Patch、显式依赖、可见的默认策略、兼容声明和测试场景。它不能注册隐藏 hook、导入未声明模块、根据环境暗中选择成员，或用一个 `apply()` 执行整段业务流程。

```yaml
id: bundle.safe-network-tooling
kind: composite
requires: [bundle.base-cognitive]
members:
  - act.authorize.capability-grant
  - act.authorize.high-risk-approval
  - act.budget.tool-calls
  - act.constraint.network-egress
  - act.constraint.idempotency
  - act.executor.safe-tool
patch:
  - id: act.budget.tool-calls
    config: { limit: 20 }
  - id: act.constraint.network-egress
    config: { allow_domains: [api.github.com, docs.python.org] }
verification:
  golden_profile: fixtures/profiles/safe-network-tooling.yaml
  expected_slots: [act.authorize, act.budget, act.constrain, act.execute]
```

### 7.3 Canonical Profile 阅读顺序

一个 Profile 必须以如下顺序回答问题：**我是谁、做什么、看到什么、能决定什么、能做什么、花多少、什么时候要人、如何停止、如何留下证据、如何与他人协作。** 对应块顺序为 `profile → role → task_contract → bundles → control_overrides → grants → collaboration → observability`。字段顺序也成为信息架构的一部分，避免“控制逻辑散落在 12 个 YAML 文件”。

## 8. 目录与包边界

目标目录按群组织，按 role 再细分。这里是**目标路径**，不要求一次性移动当前文件；迁移必须通过 compatibility import、manifest audit 与小 PR 完成。

```text
lca/
├── contracts/                         # G0：纯类型、Protocol、Capability、schema
├── plugins/
│   ├── state/                         # G1：reducer、task、goal、budget policy
│   ├── perceive/                      # G2：sensors、context policy、resolver
│   ├── think/                         # G3：brain、reasoner、renderer、critic、router
│   ├── gate/                          # G4：deterministic decision policies
│   ├── act/                           # G5：authorize、budget、constraint、executor、recovery
│   ├── memory/                        # G6：store、query、admission、retention、compact
│   ├── collaboration/                 # G7：transport、policy、strategy、synthesizer
│   ├── journal/                       # G8：ledger、store、evidence、descriptor
│   ├── observe/                       # G9：projector、exporter、scorer、inspector
│   ├── compose/                       # G10：resolver、registry、factory、driver、bundles
│   ├── provider/                      # G11：llm、sandbox、storage、search、tools
│   └── bridge/                        # G11：mcp、a2a、dsh、external transports
├── bundles/                           # 声明性装箱单
├── profiles/                          # 用户 / 部署选择
├── roles/                             # persona 与专业化数据
├── schemas/                           # profile、bundle、control DSL schema
└── tests/
    ├── contracts/
    ├── architecture/
    ├── plugins/<group>/
    ├── golden_profiles/
    └── traces/
```

目录迁移映射如下。它承认当前仓库已有模块，不把重命名当作架构进展；真正的完成标准是所有者、slot、契约与组合根已迁移。

| 当前区域 | 目标群 | 迁移动作 |
|---|---|---|
| `plugins/sensors`、`plugins/perceive` | `plugins/perceive` | 合并为 sensor / policy / resolver 子域。 |
| `plugins/brain`、`reasoner`、`critic` | `plugins/think` | 以 Think 语义统一，不把内部工厂散在三处。 |
| `plugins/gates`、`guards` | `plugins/gate` | 清楚区分 `think.guard` 与 `act.constraint`；不能所有 guard 都放在 Gate。 |
| `plugins/body`、部分 `tools` | `plugins/act` + `plugins/provider` | control 与工具 provider 分离。 |
| `plugins/runtime` | `plugins/state` / `plugins/compose` | StopRule 归 State；loop driver 归 Compose。 |
| `plugins/strategies`、`synthesizer`、`team_lead` | `plugins/collaboration` | 明确 TeamStrategy、transport policy、synthesizer。 |
| `seam_definitions`、observability 子树 | `plugins/journal`、`observe`、`provider` | 按事实、投影、基础 provider 三分。 |
| `providers`、`registries` | `plugins/provider`、`plugins/compose` | 只有群装配注册表留在 Compose。 |
| `dsh`、外部协议接入 | `plugins/bridge` | 明确这是边界适配，不是认知策略。 |

## 9. 预留扩展位：占概念，不占实现

预留位的目的是避免未来功能被塞进错误群，而不是提前建立空壳。Reserved 项只能拥有本文档中的概念注册、拟议的 Type / Evidence boundary 与 ADR 触发条件；不得创建无行为 plugin、加入默认 Bundle 或对外宣称可用。

| Reserved ID / 家族 | 未来能力 | 正确群 / Slot | 启用条件 | 不可误归属 |
|---|---|---|---|---|
| `perceive.sensor.device-state` | 屏幕、设备、浏览器状态的受控感知 | G2 `perceive.collect` | 设备 plane 具备 provenance / privacy policy。 | 不能让 Think 直接读设备。 |
| `perceive.policy.provenance` | 输入溯源、可信级别、投毒筛查 | G2 `perceive.admit` | 有统一 AttributePolicy 与证据分类。 | 不是 Memory 的通用过滤器。 |
| `think.planner.goal-stack` | 显式计划与子目标 | G3 `think.prepare` | GoalStack 事实与 reducer 语义稳定。 | 不是第七 loop step。 |
| `think.router.model` | 多模型路由 | G3 `think.prepare` | 价格、能力、数据驻留策略可审计。 | 不得藏在 LLM provider。 |
| `act.budget.concurrency` | 并发、队列和租约预算 | G5 `act.budget` | 并发资源有可恢复 lease 事实。 | 不是 gateway 限流 hack。 |
| `act.constraint.data-egress` | 数据分类、跨境 / 外发约束 | G5 `act.constrain` | classification、audience、export policy 已稳定。 | 不能仅在 exporter 检查。 |
| `act.recovery.compensation` | 不可逆副作用的补偿 | G5 `act.recover` | executor 提供 compensation protocol。 | 不能由 observer 自动补偿。 |
| `memory.policy.forgetting` | 受治理遗忘、保留期与删除证明 | G6 `remember.admit/commit` | Evidence / retention policy 已支持。 | 不是直接删数据库。 |
| `collab.policy.lease` | 委派 lease、超时、孤儿任务回收 | G7 `collab.authorize/route` | Team message 和 run resume 可恢复。 | 不得进入 StopRule。 |
| `collab.blackboard.*` | 共享黑板与冲突协议 | G7 | ACL、事务、治理模型经 ADR 批准。 | 不能是共享 `dict`。 |
| `observe.scorer.policy-regression` | 基于 golden traces 的策略回归 | G9 | stable descriptor 与 trace fixture 成熟。 | 不得影响生产 verdict。 |
| `compose.driver.graph` | 以图实现的整段 loop / workflow | G10 `driver` | 对闭集整体替换、可解释 / 恢复语义完成。 | 不能在默认 loop 旁加阶段。 |
| `bridge.acp` / `bridge.agent-protocol` | 新外部 Agent 协议 | G11 `bridge` | 认证、授权、因果和证据映射可证明。 | 不得成为新的 Team 原语。 |
| `provider.scheduler` | 长期计划、定时与后台触发 | G11 provider + G10 orchestration | 任务生命周期、ownership、重试与身份已清楚。 | 不得在 CognitiveRuntime 中启动 daemon。 |

## 10. 插件治理：如何让系统越长越清晰

### 10.1 新需求的归属判定树

```text
新需求
  │
  ├─ 它改变认知阶段、ActionType、数据核心模型或权限基本法？
  │     └─ 是：ADR；默认否决，先证明现有闭集不能容纳。
  │
  ├─ 它只是一个已存在原语的可替换实现或控制规则？
  │     └─ 是：定位群 → 定位 Control Slot → 写原子插件。
  │
  ├─ 它需要世界副作用？
  │     └─ 是：只能在 G5 `act.execute`，并受 authorize / budget / constrain。
  │
  ├─ 它只是读取已提交事实生成可丢弃产物？
  │     └─ 是：G9 observer / projector；禁止控制输出。
  │
  ├─ 它只是组合一批已有插件？
  │     └─ 是：Bundle / Profile；不得新增流程代码。
  │
  └─ 它是新的模型、存储、工具协议或外部服务？
        └─ G11 provider / bridge；不能反向拥有业务策略。
```

### 10.2 ADR、普通 PR 与配置变更的边界

| 变更 | 审批级别 | 必需材料 |
|---|---|---|
| 新原语群、闭集成员、ActionType、核心数据 owner | ADR | 语义缺口、替代方案、迁移、trace 对比、安全评估、回滚。 |
| 新 Control Slot、聚合规则、effect class、grant 基本语义 | ADR 或 ADR 修订 | 单调性证明、失败语义、事实 descriptor、组合测试。 |
| 新原子策略 / provider / observer | 普通 PR | Manifest、Config schema、slot 归属、契约测试、golden profile。 |
| 新 Bundle / Profile | 普通 PR | diff、ControlPlan 快照、expected capabilities、blast radius。 |
| 参数变化 | 配置 PR | 影响范围、预算 / 安全变更审查、resolved diff。 |
| 临时 run override | 受控操作 | 身份、理由、有效期、Journal 事实、自动过期。 |

### 10.3 每个插件的 Definition of Done

| 项目 | 必需条件 |
|---|---|
| 身份 | 稳定 ID、中文 / 英文可读 description、owner group、role、kind。 |
| 契约 | Config `extra="forbid"`、输入输出 Protocol、capability requires / provides。 |
| 控制 | 若影响控制，必须有一个 slot、activation、aggregate、failure 与 monotonicity。 |
| 权限 | effects、authority、scope、concurrency 已声明且通过 resolver。 |
| 证据 | emits 事件已登记；拒绝 / rewrite / failure 可解释。 |
| 测试 | 单元、契约、architecture、profile / golden trace 测试路径在 Manifest 声明。 |
| 组合 | 至少一个最小 Profile 能启用它；禁用后有可预期的 no-op / deny 行为。 |
| 演进 | `contract_version`、兼容 / 替换说明；没有永久 migration shim。 |

### 10.4 CI 硬门禁

| 门禁 | 拒绝的错误 |
|---|---|
| Manifest lint | 无 group / role / test suite、未知 slot、错误 kind、未声明 effect。 |
| Resolver graph | capability 循环、层级反向、重复 provider、缺失 grant、跨 slot order。 |
| Ownership scan | 直接 State mutation、observer 控制、Body 绕过 envelope、projector append。 |
| DSL validation | 可执行表达式、未知事实、secret / env 读取、动态属性链。 |
| Monotonicity property tests | deny 被 allow 覆盖、envelope scope 被放大、child grant 扩大。 |
| Journal descriptor test | 控制 verdict 没有 descriptor、缺 `plugin_id` / `slot` / `plan_ref`。 |
| Composition purity | `spawn` / gateway 点名具体策略、默默 `new` 标准实现、隐式 fallback。 |
| Golden profile diff | Profile 改动但 ControlPlan / capability / effects 差异未被审阅。 |
| Trace replay | 相同输入、Plan 和可恢复事实得到等价的控制结论。 |

## 11. 交付路线：从当前重构到长期宪法

### 阶段 0：清点与冻结（现在）

建立插件清单、Manifest 完整度报告、当前组合根硬编码报告和 profile capability snapshot。冻结新的自由 `agent.*` 控制 hook、裸 `ctx` service locator、无 Manifest provider 与 `working_memory` 控制旁路。此阶段不需要大规模移动文件。

### 阶段 1：统一词汇与元数据

为现有 plugin 填充 `architecture.group`、`role`、`ownership` 和 `lifecycle`，先生成审计报告而不改变行为。确定标准 ID 与目录迁移映射，建立 `reserved.*` 注册表。最重要的验收物是：对每个已装载插件，`inspect-tree` 能显示它属于哪个群、提供 / 依赖什么、影响哪个 slot。

### 阶段 2：ControlPlan 与 Control Slot Registry

在现有 `ResolvedProfile` 上建立不可变 `ControlPlan` 投影，先实现并验证 `think.guard`、`act.authorize`、`act.budget`、`act.constrain`、`act.execute` 与 `stop.decide`。这一步不重写所有原语，而是先解决最影响独立性和安全性的硬编码控制流。

### 阶段 3：ExecutionControl 收口

迁移工具权限、人工审批、调用次数 / 成本预算、网络与文件范围、幂等和 retry。`spawn_agent()` 不再选择具体授权器、预算器和约束器；它只请求已解析的 ExecutionControl factory。每次拒绝 / 审批 / 降级均可回链到 ControlPlan 与 Journal。

### 阶段 4：认知群与状态收口

迁移 loop breaker、progress detector、context budget、evidence conflict、GoalStack 和 StopRule，删除 Gate 直接写 `working_memory` 的过渡路径。PerceiveHub、Brain、Gate、Memory、Reducer 的所有权矩阵成为真实测试边界，而不只是设计文档。

### 阶段 5：协作、记忆与长程运行

在前四阶段稳定后，实施 team ACL、delegation budget、lease、memory admission / retention / poison screening 和长程 scheduler provider。Blackboard、compensation 与 graph driver 仍保持 Reserved，直到它们的事实模型与恢复语义可被验证。

### 阶段 6：可解释性与 Creator

提供 `explain-control`、ControlPlan graph、profile diff、run causal view、插件 blast-radius 分析与 golden trace 回归。Creator 只能经受控 `compose` capability mount / unmount / inspect 插件；其新建插件必须通过同样的 Manifest、grant、slot 与测试门禁。

### 阶段 7：删除兼容与基线固化

删除 legacy hook、direct `new`、隐式 default、重复 registry 和过渡 adapter。`null-baseline` 成为唯一显式无行为基线，标准场景均以 Bundle 表达。此时“读配置 = 理解系统”应成为自动化验收：配置、ControlPlan 和 run evidence 之间不存在未登记的行为缝隙。

## 12. 最终验收：什么叫“插件宪法已经成立”

| 维度 | 可观察验收标准 |
|---|---|
| 概念清晰 | 任何新需求可在五分钟内定位到唯一插件群、原语、slot 或明确 ADR 缺口。 |
| 目录清晰 | 不存在 `misc`、`common`、`helpers`、万能 `guard`、跨群业务实现或来源不明的 provider。 |
| 配置清晰 | 仅阅读 Profile + Bundle + ControlPlan，即可列出 Agent 可见事实、可执行动作、授权、预算、约束、审批、停止与协作边界。 |
| 运行清晰 | 任意拒绝、降级、审批、预算耗尽、重试、停止和副作用均可定位到 plugin ID、slot、config 来源、事实输入与 Journal 证据。 |
| 安全清晰 | 任一插件无法通过排序、rewrite、child agent、observer、fallback 或 runtime override 扩大权限或绕过执行窄门。 |
| 演进清晰 | 新策略只需普通 PR；改变原语、slot、数据 owner 或闭集时必须触发 ADR；弃用有明确删除期。 |
| 维护清晰 | 每个插件有 owner、contract version、测试、profile fixture、替换 / 废弃关系；已移除插件不留隐式兼容路径。 |

> **终态不是“插件数量很多”，而是“任何行为都有唯一概念地址，任何地址都有稳定契约，任何组合都能在运行前解释、运行中约束、运行后证明”。**

## 13. 时空与受治理创造增补

v4 的“Environment & Interop”“Composition & Lifecycle”“Perceive & Context”三群在 [ADR-0067](../adr/0067-spacetime-runtime-and-governed-creation.md) 中得到进一步收敛：时间成为带来源、时区、逻辑顺序和有效期的 `TemporalContext`；空间成为带 workspace、backend、identity、visibility、scope 与 lease 的 `ExecutionSpace` / `ScopeGraph`；动态插件先作为不可变 `CapabilityArtifact` 进入 `DRAFT → PARSED → DECLARED → VERIFIED → STAGED → ACTIVE → QUIESCING → RETIRED` 生命周期，而非直接以运行时代码取得生产能力。

这不是第十三个插件群，也不是第七个认知阶段。TemporalContext 属于 G2 Perceive 的事实贡献，ExecutionSpace 是 G5 / G11 的受限环境契约，artifact lifecycle 归属 G10 Composition。动态创造的完整实施方案、开发体验、Promotion、HMR、回滚、发布和安全边界见《[时空与受治理创造运行时设计](2026-08-21-spacetime-governed-creator-runtime.md)》。

## 14. 代码对齐与唯一运行计划

v4 的最终可读性不以目录结构或 Python 插件数量为准，而以一次 run 是否可被一个不可变计划解释为准。[ADR-0068](../adr/0068-compiled-plugin-kernel-and-unified-run-plan.md) 将此落实为 `CompiledRunPlan = CapabilityPlan + ControlPlan + ScopePlan`：Profile Resolve / Boot、AgentSpec、TaskContract 与环境必须先被编译为唯一计划，Runtime Kernel 只解释计划，普通插件只贡献被类型化的 PlanEntry。具体代码断裂、内核边界、Boot 生命周期收敛、RunFact / Reducer、CommandEnvelope 与动态 PlanRevision 的迁移顺序见《[代码对齐的第一性原理架构审计](2026-08-21-code-aligned-architecture-audit.md)》。

这条增补同样明确一个反直觉边界：**不是一切东西都可替换，而是一切独立变化都可声明；不可替换的是使声明保持可信的最小内核。** 因此 Runtime 时序、状态提交、effect 窄门、scope 衰减、artifact transition 与 Evidence Ledger 属于内核；sensor、gate、action、policy、tool、memory、strategy 与 renderer 属于插件贡献。

## 参考

[1]: 2026-08-19-cognitive-primitive-constitution-v3.md "认知原语插件宪法 v3.0"
[2]: ../adr/0061-plugin-manifest-resolve-boot.md "ADR-0061：声明式插件 Manifest —— Resolve/Boot 与依赖图"
[3]: ../adr/0066-declarative-atomic-control-plugins.md "ADR-0066：声明式原子控制插件——认知闭集内的可组合治理"
[4]: ../../lca/plugins/ "当前插件目录树"
[5]: ../adr/0056-plugin-group-contribution.md "ADR-0056：群服务投稿 —— 签名即依赖，配置即装箱单"
[6]: ../adr/0065-recoverable-evidence-ledger.md "ADR-0065：可恢复的证据保真运行账本"
