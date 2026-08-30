# Layered Cognitive Agent 架构评估报告

**审查日期：2026-08-24**

**审查对象：** `smartlijingyang-sudo/layered-cognitive-agent`

**审查基线：** `main @ 1808a71f73aadfbe9439189e82c57ec5cf65ede8`

**审查目标：** 判断当前架构是否适合继续演进为灵活、可扩展、可维护的“万能 Agent”，并识别必须优先修复的结构性问题。

## 一、结论摘要

**总体方向是正确的，但当前实现还没有达到可以继续无边界扩展能力的状态。** 项目已经建立了比较先进的目标骨架：Profile/Bundle 配置组合、Cordis 插件树、CompiledRunPlan、六阶段认知循环、Effect Gateway、Reducer、Journal/Projection、Agent/Team 分离，以及可替换的 loop driver。这些选择与“一个稳定内核 + 多种可组合 Agent 形态”的长期目标一致。[1] [2] [3]

但当前仓库仍处于“目标架构已设计、部分核心链路已接入、生产执行语义尚未完全收口”的过渡态。最严重的不是某一个类写得不够漂亮，而是**同一套系统同时存在两套运行模型、两套会话模型和两套扩展语义**：声明式计划已经生成，但部分控制贡献没有进入执行图；新 Session Spine 已有原型，但生产 `/runs` 仍依赖内存 `RunSession` 和 live Python 对象；旧 Hook/Topology 语义仍与 GenericPlanInterpreter 并存；兼容 fallback 仍可能改变生产行为。[4] [5] [6] [7]

本次在当前提交上复核得到：`2785 passed, 29 failed, 18 skipped, 16 deselected`。此外，`lint-imports` 的 5 个分层合同中有 4 个 broken，mypy 报告 166 个错误，ruff 报告 18 个错误；`check_protocol_impl.py` 与 ADR supervision 检查通过，但它们只能说明部分治理门禁有效，不能替代运行闭环验收。[13]

| 维度 | 当前判断 | 结论 |
|---|---:|---|
| 长期架构方向 | **8/10** | 方向值得保留，不建议推倒重来 |
| 当前生产闭环 | **4/10** | 终态、HIL、会话恢复和双轨入口仍有重大断点 |
| 插件替换真实性 | **5/10** | 具备数据结构和注册机制，但部分插件只是可发现，未真正参与执行 |
| 可维护性 | **5/10** | 概念丰富，但边界、契约、兼容路径和类型门禁尚未收敛 |
| 继续扩展“万能能力”的条件 | **不满足** | 应先完成运行语义单一化和生产闭环，再扩展能力面 |

> **核心判断：不要现在继续增加更多 Agent 模式。先把“一个 Turn 到底由谁控制、事实存在哪里、如何暂停/恢复、哪个插件真正生效”这四件事做成唯一答案。**

## 二、当前架构已经做对的部分

### 2.1 以 Profile/Bundle/Plugin 组合能力，而不是在 Composer 中堆叠 if/else

项目已经具备 `resolve_profile → boot_resolved_profile → compile_plan → bind_plan → run` 的主方向。默认 Profile 能解析 118 个插件和 62 条 DAG 边，生成带 `plan_ref` 的 `CompiledRunPlan`，并将 phase graph 固定为 `perceive → think → act → reflect → remember → stop` 六个语义阶段。[14] [15]

这个方向非常适合“万能 Agent”：用户要的是研究 Agent、编码 Agent、浏览器 Agent、团队 Agent、Creator Agent，底层不应该分别复制一套运行时，而应当由**同一内核、不同能力供应者、不同策略和不同 Profile**组合出来。当前的 `CompiledRunPlan` 也已经开始承载 capability、control、scope、phase graph、effect policy 和 action authority，这比让 Composer 直接实例化几十个具体类更容易解释、测试和审计。[10]

### 2.2 六阶段闭集和 Effect Gateway 的原则是对的

保留六步闭集是合理的。Perceive、Think、Act、Reflect、Remember、Stop 足以表达大多数 Agent 行为，研究、规划、代码执行、HITL、团队协作和工作流都可以落到阶段内部的策略、PhaseGraph 边、工具、记忆和协作协议中，不需要不断新增第七步、第八步。[2]

CommandEnvelope 和 Effect Gateway 也抓住了关键安全边界：模型输出的 Decision 不应直接等价于世界副作用，副作用应该经过权限、预算、审批、幂等、约束和审计后才执行。当前代码已经有 `RuntimeEffectGateway`、effect policy 和 idempotency key 的骨架，说明执行控制的方向是正确的。[11] [18]

### 2.3 Journal、Projection、Session Spine 已具备良好原型

`SessionStore` 已经具备 append-only event log、序列号和 JSONL 持久化；`AgentRegistry` 已具备按 session_id 管理单个 live Agent 的概念；`CommandGateway` 已经把 create/message/cancel/answer/steer/inject 统一为 typed command；`ProjectionRegistry` 已经用 reducer 方式派生 whole-value snapshot。[8] [9]

这套设计正是长期 Agent 所需要的方向。尤其是“Command → durable fact → projection → live execution”比让 HTTP 直接调用某个 Python 对象更适合跨进程、重启、审计、回放和多端订阅。问题不在于这条路错，而在于它还没有接管现有生产 `/runs` 主路径。

## 三、必须优先处理的重大问题

## P0：不修复就不应继续扩展能力

### P0-1：声明式 ControlPlan 已生成，但控制贡献没有真正进入执行图

这是当前最需要优先修复的问题。默认计划的普通 `control` 子计划显示有 12 个控制条目，覆盖 `perceive.context`、`think.guard`、五个 `act.*`、`remember.admit`、`stop.decide` 和两个 observe 槽位；但是同一份默认 Profile 的 declarative projection 中，6 个 phase binding 的 `contributions` 都为空，最终 `control_entries` 也是空数组。[10] [14] [15]

原因在 `compile_declarative_projection()` 的转换链：`_compile_phase_bindings()` 只把 `PluginSpec.contributes` 纳入阶段绑定，而大量旧 `@plugin` 会经过 `_project_definition_to_spec()` 作为迁移载体，并被投影为 `contributes=()`。因此，控制插件可以出现在树里、被 inspect 看到、拥有自己的模块和测试，却不一定参与真正的运行。[10]

这会产生最危险的一类假象：**配置看起来已经声明了安全策略，运行时却没有执行这些策略。** 对万能 Agent 来说，安全、预算、审批和停止规则不能只是 metadata；它们必须成为可证明的执行路径。

**建议：** 立即建立一条强不变量：`CompiledRunPlan.control_entries` 必须与各 phase binding 的 govern/observe contributions 一一对应；任何 control entry 没有 executable binding 时，compile 直接 fail-closed。对 legacy plugin 不要继续静默投影为空，而是建立显式迁移适配器，或者在它没有 native `PluginSpec` 时禁止其进入 declarative production profile。

**跟进：** 本条独立成 ADR draft：`lca/harness/declarative/compiler.py` 把 `_compile_phase_bindings()` 与 legacy `@plugin` 投影接通，强不变量与 fail-closed 收敛为可执行测试与 lint 约束；与 [ADR-0077](0077-terminal-outcome-protocol.md)、[ADR-0078](0078-hil-approval-state-machine.md) 互不覆盖。

### P0-2：终态和最终输出传播断裂，默认 Agent 能启动但不能可靠完成

本次端到端 smoke test 显示：Profile 解析、Boot、CompiledRunPlan、spawn 和 6 个 phase executor 均成功，但 `agent.run()` 最终返回 `FAILED`、output 为空、执行两步后结束。代码中 `_terminal_stop_decision()` 固定生成 `final_output=None`，随后 `DeclarativeRuntimeDriver` 再依赖 `Result.from_state(final_state)` 判断最终状态；这使得 StopDecision、artifact closure、state.final_output 和 Result.output 之间没有形成单一的输出传播协议。[11] [12]

这不是普通的字段遗漏，而是一个核心领域协议不完整：**阶段结果、停止判定、交付物闭合和用户输出到底哪个是最终事实源，没有被明确区分。** 如果未来加入代码产物、文件、图片、结构化 JSON、流式文本和团队汇总，这个问题会进一步放大。

**建议：** 定义唯一的 `TerminalOutcome` 或等价协议，明确区分 `status`、`final_output_ref`、`artifact_refs`、`stop_reason`、`error_ref` 和 `resume_cursor`。Stop phase 只产生 typed outcome；Reducer 负责把 outcome 折叠为状态；Result 只从最终状态/投影读取，不再自行猜测“有没有输出”。为 text、artifact、stream 和 structured output 分别建立契约测试。

**跟进：** 唯一终端事实协议见 [ADR-0077: TerminalOutcome Protocol as Sole Terminal Truth](0077-terminal-outcome-protocol.md)。

### P0-3：HIL/Approval 暂停恢复链路当前不可用或语义不一致

当前 HIL 相关测试中，预期的 `WAITING_INPUT` 实际变成 `FAILED`，run doctor 报告 `tool started without invoked/denied`。这说明 ToolStarted、ToolInvoked/Denied、ApprovalRequested、Paused、Resume 和 Terminalize 之间没有形成完整且一致的事件协议。[13]

同时，`StandardPhaseExecutor` 会产生 CommandEnvelope，`RuntimeEffectGateway` 负责执行和幂等，`GenericPlanInterpreter` 捕获 ApprovalPendingError，但暂停点、cursor、snapshot、approval request 和下一次 resume 的输入契约仍处于多处适配状态。[11] [12] [18]

**建议：** 把 HIL 当作一等状态机而不是异常分支，至少明确以下状态和事实：`approval_requested → waiting_input → approval_resolved → resumed → effect_completed/effect_denied`。每个状态必须可以由 Journal 重建；resume 只能提交 command，不能直接调用旧 live object；工具事件必须满足 started 后必有 completed/denied/uncertain 终态。对 approval、cancel、crash-after-effect、重复 answer 建立 property/e2e 测试。

**跟进：** HIL 一等状态机见 [ADR-0078: HIL/Approval as First-Class State Machine](0078-hil-approval-state-machine.md)。

### P0-4：生产环境仍存在 `/runs` 与 `/v1/sessions` 两条并行主路径

`gateway/app.py` 同时暴露旧的 `/runs/*` 路由和新的 `/v1/sessions/*` 路由。旧路径使用 `RunRegistry/RunSession`；新路径使用 Harness 的 `AgentRegistry/CommandGateway`。这不是仅仅保留 API 兼容，而是两套不同的生命周期和事实流并存于生产应用。[4]

更关键的是，新 `CognitiveLiveAgent` 仍然包裹旧的 `lca.layer4_app.api.Agent.run()` 和 `Agent.resume()`；它不是独立的 session-native runtime。旧 `RunSession` 仍保留 `asyncio.Task`、`snapshot` 和 `runnable` live Python 引用，`resume_run()` 直接执行 `session.runnable.resume(session.snapshot)`。[5] [6] [7]

**建议：** 选定 `/v1/sessions` + CommandGateway + AgentRegistry 为唯一内部主路径。旧 `/runs` 只保留一个薄适配器，把旧请求转换成 typed command，不得再拥有独立 RunRegistry 执行语义。完成迁移后，Gateway 只负责 carrier，不再 import concrete loop、Brain、Body 或旧 runnable。

**当前收敛边界：** 生产应用在未显式注入 `RunRegistry` 时，`POST /runs`、`GET /runs/{run_id}`、`GET /runs/{run_id}/live`、`GET /runs/{run_id}/doctor`、`POST /runs/{run_id}/cancel` 和 `POST /runs/{run_id}/answer` 已通过 `SessionRunAdapter` 转换为 `CommandGateway` 命令或 Session projection；`run_id` 与 durable `session_id` 使用同一标识。`doctor.v2` 的状态、输出和序号一致性来自 Session Spine projection，旧 `RunRegistry` 仅保留给显式注入的 legacy fixture；evidence 运维接口仍待迁移。

## P1：不修复会持续侵蚀可维护性和可替换性

### P1-1：进程重启恢复仍未形成真正闭环

新 SessionStore 的 JSONL 加载和 AgentRegistry.resume 已经存在，但生产旧路径仍依赖内存 `RunRegistry`。新适配层在 `SessionCheckpoint` 中写入 `snapshot_ref=None`，恢复仍依赖 `_last_result` 里的内存 snapshot；ProjectionRegistry 也是 `InMemoryProjectionRegistry`，没有持久化 projection checkpoint、cold read 或跨进程订阅。[6] [7] [8] [9]

因此当前系统可以做到“同一进程中继续”，但还不能稳定地做到“进程重启后从 durable facts 恢复一个 Agent”。这对长程 Agent、计划执行、定时任务、审批等待、子 Agent 和后台工作流是基础能力，而不是后期优化。

**建议：** 将恢复定义为 `load SessionHeader + replay facts + load immutable plan_ref + materialize projection + recreate loop handle + resume cursor`。Checkpoint 必须保存 durable `state_ref`/`cursor_ref`/`plan_ref`，不能保存只在内存中有效的 Python 对象；外部副作用恢复必须依赖 effect receipt 或 uncertain 状态，不能重复发起。

### P1-2：核心 runtime 仍保留隐式默认和兼容 fallback

`CognitiveRuntime` 在 registry 未注入时会自行构造默认 effect/delta registry；`RuntimeEffectGateway` 也可以内部构造默认 registry；`ReducerDeltaAdapter` 对未知 operation 直接返回原 state；`DeclarativeRuntimeDriver` 仍直接调用 `synthesize_artifact_closure()` 自由函数；runtime factory 对 `stop_rule` 仍保留默认回退；`SimpleBody` 仍可直接构造默认 action registry。[11] [16] [17]

这些 fallback 早期有利于迁移，但在“万能 Agent”目标下会造成严重的不可解释性：同一个 Profile 可能因为调用入口不同而得到不同实现；缺少一个安全组件时系统可能继续运行，而不是在 Boot/Compile 阶段明确失败；未知 delta 被静默忽略会导致状态和 Journal 不一致。

**建议：** 明确区分 `production profile` 与 `test fixture` 两种装配模式。生产模式所有必需 binding 缺失都 fail-closed；测试便利性通过显式 `test_default` profile 获得，而不是在核心 runtime 内部猜测。未知 delta、未知 effect、未知 phase contribution 必须抛稳定错误码并写入失败事实。

### P1-3：contracts 层承载了过多行为和规则引擎

`lca/contracts/protocols/declarative_phase_graph.py` 不仅包含数据结构，还包含 `ValidationReport` 的行为方法、`ActionAuthorityPlan.permits()`、`PluginSpecValidator`、`PhaseGraphValidator`、关系和图校验逻辑以及 canonical hash 相关算法。该文件有效代码量约 926 行，已经明显超出项目自身规定的文件规模和“contracts 纯数据/Protocol”原则。[1] [17]

这会让协议变更变成高 blast-radius 变更，也使 contracts 同时承担 schema、语义校验、编译策略、运行策略和安全策略。最终结果是任何一个小字段变化都可能触发全仓库类型、导入和测试回归。

**建议：** 保留 contracts 中的 frozen dataclass、Enum 和 Protocol；把校验移动到 `lca/harness/declarative/validation.py`，把编译策略保留在 `harness/profile`，把权限推导放到 `harness/policy` 或 plan compiler。`ValidationReport` 可以保留为纯数据结果，`require_valid()` 等行为由 validator/service 提供。

### P1-4：分层合同已经被实际导入路径破坏

当前 `lint-imports` 结果显示：严格分层、L4 组合根隔离、Harness 不依赖 L1–L4、Plugins 不依赖 Gateway 等合同仍有破坏。代表性剩余路径包括 `layer0_infra → lca → layer4_app`、`harness.declarative.interpreter → layer2_runtime.control_runtime` 和 `plugins.loop_drivers.cognitive → gateway`。[1]

这说明当前层级图在文档上很清楚，但代码中仍有公共包 lazy import、运行时 adapter、CLI 和 plugin factory 穿透边界。长期看，这会让任意新插件都需要理解大量隐式导入关系，维护成本会随插件数量非线性增长。

**建议：** 不要先重命名整个目录，而是先切断四条高频边界：公共 `lca` facade 不得被底层模块导入；Gateway-specific driver 放到 adapter 层；Harness declarative interpreter 只依赖 contracts/kernel 协议；LCA plugin 只向 loop registry 注册抽象 factory，不反向 import Gateway。每切断一条边界，增加 import contract 和最小启动测试。

### P1-5：旧 Hook/Topology 语义与新 GenericPlanInterpreter 同时存在

当前 `CognitiveRuntime` 已经不再实现旧 `_loop`，而是委托 GenericPlanInterpreter；但 `ClosedSetTopology` 仍定义 8 个 `agent.before/after_*` hook 和生命周期 seam，HookRegistry 仍然存在，旧测试也继续要求 `CognitiveRuntime._loop` 或 `self.stop_rule.decide`。[11] [13] [17]

这会导致开发者无法回答一个简单问题：控制逻辑应该通过 PhaseGraph contribution、ControlPlan slot、HookRegistry，还是旧的 Topology seam 接入？如果四种入口都合法，系统最终会退化为 hook soup；如果只有一种合法，其他三种就应被明确标记为 adapter 或删除。

**建议：** 选择 `PhaseGraph + typed contribution + ControlPlan` 作为生产控制面的唯一主语义。Hook 只保留纯观察用途，不能修改 State、Decision 或执行路径。旧 Hook/Topology 逐步降级为 compatibility adapter，并设置删除版本和测试迁移计划。

### P1-6：Capability relation/authority 目前更多是计划元数据，尚未完全驱动行为

默认计划 JSON 显示 capability relation count 为 0，尽管 ADR-0069/0074 目标包含 11 种关系代数。与此同时，ActionAuthority 已进入 CompiledRunPlan，但编译器仍保留 `_SCOPE_DEFAULT_ACTIONS` 这样的静态默认集合，且部分 action registry 仍存在旧构造路径。[10] [13]

如果关系、权限和 scope 只用于 inspect，而不参与 provider selection、phase binding、effect authorization、subagent grant 衰减和 projection，那么系统只是“有一层漂亮的声明数据”，并没有真正变成 declarative runtime。

**建议：** 给每一种关系定义明确的运行时消费者：`provides/requires` 用于 binding；`replaces` 用于唯一实现选择；`governs` 用于 control contribution；`executes` 用于 effect gateway；`delegates` 用于 subagent authorization；`projects` 用于 projection registry；`revises/evaluates` 用于 Creator/Eval。没有消费者的关系暂时不要加入生产 schema。

### P1-7：工程质量门禁与架构状态不一致

当前插件树规模已达到 118 个条目，但 plugin shape 覆盖率测试只有 87.0%；全量测试、文件大小、contracts purity、mypy、ruff 和 import-linter 均未全绿。与此同时，部分文档或旧测试仍然把已删除的 `_loop`、旧文件和旧命令当作现行契约。[13]

这会让“通过测试”失去含义：有些测试在验证旧架构，有些测试在验证新架构，有些测试只验证静态元数据。对于万能 Agent，真正需要的是少量高价值的架构不变量，而不是越来越多的相互矛盾的测试。

**建议：** 将 CI 分为四个明确层级：`contract`、`compile`、`runtime e2e`、`compatibility`。每个测试标明自己验证的是 production path 还是 migration path；所有 production gate 必须全绿才能合并。先清理失效测试契约和失效 ADR 路径，再增加新能力。

## 四、面向“万能 Agent”的建议目标蓝图

### 4.1 不建议把“万能”理解为“无限增加插件和步骤”

万能 Agent 的核心不是拥有最多工具，而是能够在不修改内核的前提下，安全地组合不同模型、工具、记忆、工作流、协作、设备和交互能力。建议将目标定义为：

> **固定的可信运行内核 + 可验证的不可变计划 + 可持久化的 Agent Session + 受权限控制的副作用 + 可替换的能力提供者 + 可回放的事实流。**

六步认知闭集应保留。研究、编码、浏览、RAG、HITL、团队、DAG、Self-Improving、Creator 等都应作为 Profile/Bundle/PhaseGraph/Tool/Memory/Collaboration 的组合模板，而不是新增一套平行 runtime。[2] [3]

### 4.2 推荐的稳定内核边界

| 内核组件 | 唯一职责 | 必须禁止 |
|---|---|---|
| `SessionStore` | durable command/fact log、seq、cursor、fork | 保存 live Agent 作为事实 |
| `PlanCompiler` | Profile → immutable plan、校验和、binding | 运行时临时补默认实现 |
| `AgentLoopFactory` | 按 plan 创建/恢复 loop handle | Gateway 直接 new 具体 runtime |
| `GenericPlanInterpreter` | 执行已验证 PhaseGraph | 读取全局变量或未声明服务 |
| `Reducer` | 唯一写 State | Sensor/Gate/Body 原地改 State |
| `EffectGateway` | 统一权限、审批、预算、幂等、审计 | 允许未声明副作用 |
| `ProjectionRegistry` | Journal → whole-value projections | 前端自行 fold raw domain events |
| `PluginHost` | scope、依赖、生命周期、dispose | 允许插件绕过 manifest 访问任意对象 |

### 4.3 推荐的运行链路

```text
Typed Command
  → authorize command
  → append durable fact
  → resolve/reuse Session + immutable CompiledRunPlan
  → AgentLoopFactory.create/resume
  → GenericPlanInterpreter
       perceive → think → act → reflect → remember → stop
       phase result → reducer / effect gateway / journal
  → TerminalOutcome or WaitingInput
  → ProjectionRegistry
  → HTTP/SSE/WebSocket carrier
```

在这条链路中，Gateway 不知道 Brain、Body、Memory 或具体 loop；Agent 不把 `asyncio.Task` 当作持久化事实；所有用户可见状态从 projection 获取；所有世界副作用有可审计 receipt；所有 resume 只从 session facts、checkpoint 和 plan_ref 重建。

### 4.4 推荐的插件分类

建议把插件分成四类，而不是让每个新增类都成为新的“架构概念”：

| 类型 | 示例 | 运行时约束 |
|---|---|---|
| Provider | LLM、Memory、Tool、Sandbox、Transport、Storage | 实现稳定 Protocol，不能改变控制流 |
| Phase Executor | Perceive、Think、Act、Reflect、Remember、Stop | 返回 typed `PhaseResult`，不直接写 State |
| Policy/Contribution | Safety、Budget、Approval、LoopBreaker、MemoryAdmission | 输出 typed verdict/fact，不能隐式 mutation |
| Projection/Observer | UI、Trace、Metrics、Eval、Audit | 只消费事实，不改变执行结果 |

`Bundle` 和 `Profile` 负责组合这些类型；`Role` 与 `TaskContract` 负责实例化个性和任务约束；它们不应各自再发明一套插件 schema。

## 五、建议的实施优先级

### 阶段 0：冻结扩展面并建立唯一生产基线

这一阶段不新增 Agent 能力。先把当前提交作为基线，建立 `production profile`、`test fixture profile` 和 `compatibility profile` 三种明确模式；标记所有 fallback、legacy facade 和旧测试契约；定义 10 条不可违反的架构不变量，包括 control binding 完整、未知 delta fail-closed、工具事件终态完整、终态输出可重建、plan_ref 一致、Journal seq 连续、resume 不依赖 live object、Gateway 不依赖 concrete loop、contracts 无行为实现、生产 profile 无隐式 fallback。

### 阶段 1：修复一次 Turn 的执行闭环

优先修复 ControlPlan 到 PhaseGraph 的绑定、Stop/final output 传播、artifact closure seam、HIL 状态机和未知 delta fail-closed。阶段完成标准不是“若干单测通过”，而是默认 solo profile 完成以下脚本：启动、模型响应、工具调用、工具拒绝、审批暂停、审批恢复、取消、失败、最终输出、产物引用和 journal replay 全部通过。

### 阶段 2：收敛 Session Spine，消除生产双轨

让 `/v1/sessions` 成为唯一内部实现，把 `/runs` 降级为请求兼容适配器。生产请求统一走 `TypedCommand → SessionStore → AgentRegistry → AgentLoopFactory`；实现 durable checkpoint、cold resume、fork、idempotency receipt 和 projection rebuild。此阶段完成前，不建议上线长时间后台任务、复杂子 Agent 或自动化定时工作流。

### 阶段 3：删除隐式 fallback，恢复边界和类型门禁

删除或隔离 `RuntimeEffectGateway`、`ReducerDeltaAdapter`、旧 action registry、旧 Gate builder 和 artifact closure 自由函数等兼容入口。将 contracts 中的 validator 和算法下沉到 harness；修复 import-linter、mypy、ruff、plugin shape 和文件大小门禁。所有 legacy path 必须有明确迁移期限，而不是永久共存。

### 阶段 4：建立真实插件替换性测试

每一个可替换面都应有最小 substitution fixture：替换 LLM、Memory、Tool、Body、PhaseExecutor、Policy、Projection、Transport、Loop Driver 后，核心 runtime 不改代码即可运行。测试不仅检查“能注入”，还要检查替换实现真的被调用、结果真的影响执行、Journal 中有对应事实、恢复时 plan_ref 和版本正确。

### 阶段 5：在稳定内核上扩展万能能力

只有前四阶段完成后，才扩展 RAG、Browser、Computer Use、Code Interpreter、Subagent、Team、DAG Workflow、Voice/Realtime、Multimodal、Self-Improving 和 Creator。每个能力都必须回答四个问题：属于哪个能力类别；输入/输出 Protocol 是什么；副作用经过哪个 Effect Gateway；恢复和 Journal 如何重建。回答不清楚时，不应直接新增插件。

## 六、建议暂缓或禁止的事项

第一，暂缓继续增加新的 primitive group、新的 loop stage、第四套事件词表和第五套 plugin manifest。当前问题不是表达能力不足，而是已有语义没有唯一执行路径。

第二，不要把 118 个插件继续全部堆进一个默认 Profile。应拆成 `minimal`、`standard`、`coding`、`research`、`team`、`creator` 等小而可解释的 Profile，并让每个 Profile 的 plan、权限、工具、记忆和恢复能力都能被 inspect 和 replay。

第三，不要通过放宽类型、增加 `Any`、扩大 fallback 或继续保留旧测试来制造绿色。对于万能 Agent，**fail-closed 比“尽量跑起来”更重要**；否则一旦进入真实工具、文件、网络、设备和子 Agent 场景，系统会变得不可审计。

## 七、最终判断

**项目架构方向对，且有值得保留的长期资产；当前重大问题在于架构收口不足，而不是设计方向根本错误。** 建议保留六步闭集、双平面、Profile/Bundle、CompiledRunPlan、PluginHost、Effect Gateway、Reducer、Journal/Projection 和 Agent/Team 分离这些核心决策。

但在下一阶段必须从“继续插件化”转向“验证插件确实接入执行”。最优先的工作顺序是：**控制面真正接线 → 终态/输出和 HIL 修复 → Session Spine 接管生产 → 消除 fallback 与双轨 → 恢复分层/类型/测试门禁 → 再扩展万能能力。**

如果按照这个顺序推进，当前项目可以演进成一个真正可组合的 Agent Runtime；如果继续在现有双轨和兼容回退之上增加更多工具、策略和 Agent 模式，最终很可能得到的是“插件数量很多、行为来源不清、恢复不可证明、测试互相冲突”的复杂系统，而不是万能 Agent。

## References

[1]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/AGENTS.md "Repository architecture and engineering constraints"
[2]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/docs/design/2026-08-19-cognitive-primitive-constitution-v3.md "Cognitive Primitive Constitution v3"
[3]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/docs/specs/harness-spine-spec.md "Harness Spine Specification"
[4]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/gateway/app.py "Starlette application and dual route paths"
[5]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/gateway/runs/execute.py "Production run and resume execution path"
[6]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/gateway/runs/session.py "RunSession and in-memory RunRegistry"
[7]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/lca/layer4_app/harness_live.py "Harness LiveAgent adapter"
[8]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/lca/harness/session/store.py "Durable SessionStore prototype"
[9]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/lca/harness/projection/registry.py "In-memory projection registry"
[10]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/lca/harness/declarative/compiler.py "Declarative plan compiler and phase/control binding"
[11]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/lca/layer2_runtime/declarative_runtime.py "Declarative runtime bridge"
[12]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/lca/harness/declarative/interpreter.py "Generic phase graph interpreter"
[13]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/ADR_66_69_74_75_76_IMPLEMENTATION_AUDIT.md "Current ADR implementation audit"
[14]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/profiles/web-standard.yaml "Default production profile"
[15]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/bundles/declarative-phase-graph.yaml "Declarative phase graph bundle"
[16]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/lca/plugins/composer/runtime_factory.py "Runtime dependency factory and fallback policy"
[17]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/lca/contracts/protocols/declarative_phase_graph.py "Declarative contracts, validators and plan rules"
[18]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/1808a71f73aadfbe9439189e82c57ec5cf65ede8/lca/plugins/phase_executors/common.py "Standard phase executor and effect envelope"
