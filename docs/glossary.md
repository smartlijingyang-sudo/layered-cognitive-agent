# 术语表（渐进披露）

> 本表与代码由测试双向守护（`tests/test_code_conventions.py`）：
> 现役区的 CamelCase 术语必须对应 `lca` 包内真实类名（反向校验），
> 源码核心类的词根必须能在本表找到匹配（正向校验）。
> 被删除/改名的概念一律移入「已废弃主名」表，禁止滞留在现役区。

## L-User

团队协作只有一套模型（ADR-0030）：`Team = members + (lead XOR coordination)`。
常用路径是 lead（board/routing）与 `Pipeline` / `FanOut`；
PeerRelay / PeerSwarm / Debate / Graph 为进阶机制。

| 术语 | 定义 |
|---|---|
| **Agent** | L4 门面：显式实现 AgentUnit；持有 AgentSpec + 由它组装的封闭图，`await agent.run(task)` |
| **Team** | L4 团队门面：显式实现 TeamUnit；`members` + 恰好一种协作机制（`lead` XOR `coordination`），`await team.run(objective)` |
| **TeamLead** | 有主导者团队的入口：`TeamLead.routing/consult/board(agent)`，LeadSpec 的门面持有者 |
| **AgentSpec** | Agent 声明式构造规格（frozen 值对象）：RoleProfile + LLM/工具 + 预算 + 组件选择；组合根的唯一声明式输入（ADR-0033） |
| **LeadSpec** | lead 入口规格：AgentSpec + LeadMandate；全层统一表示，取代 tuple 传参（ADR-0033） |
| **LeadMandate** | 主导者授权：routing（自由 PM）/ consult（按需咨询）/ board（全员咨询后收口） |
| **Coordination** | 无主导者协作机制的联合类型（类型别名）：Pipeline / FanOut / PeerRelay / PeerSwarm / Debate / Graph |
| **Pipeline** | 协调机制（常用）：成员按序接力，前者产出进入后者上下文（策略键 `pipeline` → SequentialStrategy） |
| **FanOut** | 协调机制（常用）：全员并行后由 Synthesizer 归并（策略键 `fan_out` → ParallelStrategy） |
| **PeerRelay** | 协调机制（进阶）：成员间交接，首成即返（策略键 `peer_relay` → HandoffStrategy） |
| **PeerSwarm** | 协调机制（进阶）：轮询累积直至轮数上限（策略键 `peer_swarm` → SwarmStrategy） |
| **Debate** | 协调机制（进阶）：多轮辩论收敛（策略键 `debate` → DebateStrategy） |
| **Graph** | 协调机制（进阶）：按 ExecutionGraph 拓扑执行（策略键 `graph` → GraphStrategy） |
| **AgentComposer** / **TeamComposer** | 组合根：从 AgentSpec / TeamSpec 封闭组装 Agent / Team 对象图，无构造后 bind/install（ADR-0030 / ADR-0033 / ADR-0034）；无进程级单例，门面未注入时各自构造默认实例 |
| **multi-delegate** | 一步并行委派多个角色（`Decision.delegations` 多条 + DelegateOperation gather） |
| **Result** | 运行最终结果：status / output / budget / error |
| **run** | 全链路唯一生命周期动词（Agent / Team / CognitiveRuntime） |

## L-Team

| 术语 | 定义 |
|---|---|
| **Registries** | 三个发现型注册表的值对象包（components / brain_factories / orchestration），由 TeamComposer 私有持有，替代进程级全局单例 |
| **CognitiveAgent** | L3 可调度单元：CognitiveRuntime + RoleProfile |
| **TeamHandle** | 封闭团队的运行句柄：持有闭合 TeamStrategy + TeamTraceProfile，run 只做 trace 边缘 + 委派，不做编排（ADR-0034） |
| **TeamSpec** | 团队声明式构造规格：成员 + Governance，团队组合根的唯一事实来源（ADR-0034） |
| **Governance** | 团队治理方式 = LeadSpec \| Coordination：谁来决定下一步；XOR 由类型槽位表达，lead 与 coordination 同为治理方式（ADR-0034） |
| **TeamStrategy** | 团队协作策略协议：构造期闭合，运行期只 `run(objective)`；每种 Governance 经注册表工厂闭合为一个实现（ADR-0034） |
| **TeamStrategyRegistry** | TeamStrategy 的 NamedRegistry（策略键 → 工厂）；工厂签名 `(TeamAssembly) -> TeamStrategy`，所有治理方式（含 lead）走同一条注册表路径（ADR-0034） |
| **TeamAssembly** | 策略工厂 resolve 期的只读装配视图（governance / stage / lead）；仅存在于组合期的布线类型（ADR-0034） |
| **TeamStage** | 协调型策略的行动舞台：成员 + MemberInvoker；布线类型，非运行期领域概念（ADR-0034） |
| **MemberInvoker** / **TransportMemberInvoker** | 策略调用成员的唯一通道协议 / 绑定 transport 的默认实现（组合期闭合，运行期零防御校验）（ADR-0034） |
| **TeamTraceProfile** | 团队级静态 span 档案（team_id / strategy_key / mandate / 角色名）；组合期派生，遥测与行为分离（ADR-0034） |
| **TeamUnit** | 团队入口协议 |
| **AgentUnit** | 单体入口协议 |
| **TeamAwareness** | lead 一次 run 的团队实时认知：teammates + 委派回报记录（results）+ 可选 ConsultDuty；仅 lead run 持有，solo/member 为 None；不按 mandate 分裂类型（ADR-0035 / ADR-0036） |
| **ConsultDuty** | 咨询义务（consult / board 授权专属）：必问成员状态板 + 重试计数；TeamAwareness 的可选组件，None 即自由 routing（ADR-0035 / ADR-0036） |
| **teammates_text** | 写进提示词的「队友是谁」（由 `build_teammates_text` 从 TeamAwareness.teammates 渲染） |
| **DecisionGate**（配置） | 咨询合规强度：由 LeadMandate 展开——routing → `none`（自由经理），board → `must_consult_all`（咨询合规） |
| **DecisionGate**（组件） | 决策出/入门硬规则（`enforce` 必选出门校验，`SupportsShortcut` 可选入门快速路径） |
| **SupportsShortcut** | 可选能力：DecisionGate 在 LLM 之前提供确定性快速路径（`try_shortcut`） |
| **MustConsultAllMembers** | 未咨询完所有必需角色时禁止 respond |
| **MemberStatus** | 必问成员是否已咨询完毕的 board |
| **InMemoryMemberStatus** | MemberStatus 默认不可变实现 |
| **AgentTransport** / **send_and_wait** | 成员间任务通道与统一调用端口；内置 Internal / A2A / MCP |
| **SharedMemoryStore** / **TeamSharedMemoryStore** | 共享记忆存储协议 / 团队按 MemoryLayer 分层的默认实现 |
| **RunContext** | 一次 `run` 的调用元数据（trace_id / from_role / deadline；可选 team_awareness） |
| **PromptReasoner** | Reasoner 唯一实现（ADR-0035）：渲染模板并调 LLM；携带 TeamAwareness 时并入 awareness 变量与默认模板，统一覆盖 solo / member / lead，不按 mandate 分裂类型 |
| **LeadBudgetPolicy** | lead 预算提升策略（compose_as_lead 时经 ComponentRegistry 解析） |
| **RoleProfile** | 角色画像 |
| **TeamMessage** / **TeamAssignment** | 跨 Agent 消息 / 分工单元 |

## L-Loop

| 术语 | 定义 |
|---|---|
| **L0–L4** | 框架五层：基础设施 / 认知组件 / 认知运行时 / Agent 抽象 / 应用编排 |
| **CognitiveRuntime** | 认知闭环 perceive → think → act → reflect → stop 的承载者（「CognitiveLoop」是该模式的概念名，不是类） |
| **AgentState** | 循环状态容器 |
| **Decision** | 一步行动决策；委派目标仅存于 `delegations` |
| **Observation** | 行动结果 |
| **Reflection** | 自省判定 |
| **StopRule** / **StopDecision** / **StopReason** | 是否结束循环 |
| **DefaultStopRule** | 默认终止裁判（``default_stop_rule.py``）；内部可组合 StopOutcomePolicy |
| **StopOutcome** / **StopOutcomePolicy** / **DefaultStopOutcomePolicy** | 单步结果判定（DefaultStopRule 内部使用） |
| **Brain** / **Body** / **MemorySystem** | 想 / 做 / 记 |
| **ModularBrain** | 默认 Brain（reasoner / critic / decision_parser 可替换）；CandidateEvaluationPipeline 做 decompose → evaluate |
| **Turn** | 单步记录：decision + act result + reflection |
| **Budget** | token / cost / steps / wall_clock 预算 |
| **Hook** / **HookRegistry** / **EventBus** / **Event** | 生命周期钩子与事件 |
| **Observability** / **TraceSpan** / **ConsoleObservability** / **JSONLFileObservability** | 可观测性（console 打印 / JSONL 落盘） |
| **StateStore** / **StateSnapshot** | 状态持久化与快照 |

## L-Plugin / L0

| 术语 | 定义 |
|---|---|
| **Reasoner** / **Critic** / **DecisionParser** | 候选生成 / 自省 / 解析 |
| **Action** / **ActionRegistry** / **ActionType** | 行动能力与路由（内置行动类型：respond / use_tool / delegate / handoff / stop / ask_human） |
| **RespondOperation** / **UseToolOperation** / **DelegateOperation** / **HandoffOperation** | 内置行动实现（delegate/handoff 行动 ≠ PeerRelay 协调机制） |
| **SafeExecutor** | 权限 + 重试 + 缓存后执行工具 |
| **ToolRegistry** / **Tool** / **ToolPermissionManifest** | 工具注册与权限 |
| **RetryPolicy** / **CacheConfig** | 重试与缓存配置 |
| **BrainFactory** / **SimpleBrainFactory** | Brain 工厂（注册表用 NamedRegistry） |
| **Synthesizer** / **ConcatSynthesizer** | 并行结果聚合协议 / 默认拼接实现 |
| **LLMAdapter** / **OpenAICompatAdapter** / **MockLLMAdapter** / **TelemetryLLMAdapter** | 多厂商 LLM 适配协议与实现（Telemetry 为装饰器） |
| **AgentTransport** / **TransportRegistry** / **InternalTransport** / **A2ATransport** / **MCPTransport** | 传输协议、注册与实现 |
| **ComponentRegistry** / **NamedRegistry** | DI / 按名注册表（ComponentRegistry 是 category → NamedRegistry 的组合器） |
| **RegistryKeyError** | 注册表硬查询失败异常（继承 ValueError） |
| **team_wiring** / **build_team_transport** | L4 团队 channel 接线（与 agent 组装决策分离） |
| **SkillRouter** / **KeywordSkillRouter** / **StaticSkillRouter** | 运行时动态选择 Prompt 模板 / 工具子集（关键词 / 静态映射） |
| **load_builtin_prompt** | 从 ``brain/prompts/*.md`` 加载内置模板 |
| **DegradationPolicy** / **GracefulDegradation** | 越界 action 优雅降级（防腐层归一化：解析期改写为词表内等价行动，经 Decision.degraded_from 溯源） |
| **DelegationSpec** / **AgentCard** / **TaskStatus** | 委派规格 / 能力名片 / 任务状态机 |
| **ApprovalPendingError** / **BudgetExceededError** / **ToolExecutionError** | 运行时异常 |
| **MemoryRecord** / **MemoryLayer** | 记忆契约（分层参考 CoALA：working / semantic / episodic / procedural） |
| **ExecutionGraph** / **GraphNode** / **GraphEdge** / **GraphStrategy** | 图编排 |
| **LeadStrategy** | lead 路径的 TeamStrategy（策略键 `lead`） |
| **ParallelStrategy** | FanOut 协调的 TeamStrategy（策略键 `fan_out`） |
| **SequentialStrategy** | Pipeline 协调的 TeamStrategy（策略键 `pipeline`） |
| **DebateStrategy** | Debate 协调的 TeamStrategy（策略键 `debate`） |
| **HandoffStrategy** | PeerRelay 协调的 TeamStrategy（策略键 `peer_relay`） |
| **SwarmStrategy** | PeerSwarm 协调的 TeamStrategy（策略键 `peer_swarm`） |
| **SimpleBody** | Body 默认实现 |
| **SimpleMemorySystem** | MemorySystem 默认实现 |
| **PromptReasoner** | Reasoner 默认实现（team-shape agnostic，solo/member/lead 统一） |
| **SimpleCritic** | Critic 默认实现 |
| **SimpleDecisionParser** | DecisionParser 默认实现 |
| **SimpleEventBus** | EventBus 默认实现 |
| **SimpleHookRegistry** | HookRegistry 默认实现 |
| **SimpleSafeExecutor** | SafeExecutor 默认实现 |
| **SimpleToolRegistry** | ToolRegistry 默认实现 |
| **CandidateEvaluationPipeline** | 候选评估管线协议（SimpleCandidateEvaluationPipeline 为默认实现） |
| **InMemoryStateStore** | StateStore 内存实现 |
| **CalculatorTool** / **WeatherTool** | 内置示例 Tool |

## 已废弃主名（仅允许过渡别名，见 contracts 内注释）

| 旧名 | 新名 |
|---|---|
| MultiAgentTeam | Team |
| TeamOrchestrator | TeamHandle（编排决策全部闭合进 TeamStrategy，句柄只是 trace 边缘；ADR-0034） |
| TeamContext | 已删除；策略构造期闭合，运行期无上下文包（ADR-0034） |
| TeamConfig | 已删除；strategy_key 仅作注册表键/遥测标签，max_rounds/mandate 为策略构造参数，共享记忆层归组合期布线（ADR-0034） |
| TeamProcess | LeadMandate + Coordination（一元的 lead XOR coordination，ADR-0030） |
| OrchestrationFamily / SupervisorMode / Recipe | 已删除，无替代概念（ADR-0030） |
| Assembly / assemble_agent | AgentComposer / TeamComposer |
| TeamProcessStrategy | TeamStrategy |
| HierarchicalStrategy | LeadStrategy |
| SupervisorPlane | 已删除；会话分裂（RoutingState / ConsultationState）亦已统一为 TeamAwareness（ADR-0035） |
| SupervisorBinder | 已删除；绑定逻辑并入 TeamComposer.compose_as_lead |
| ConsultationState / RoutingState / ControlSession | TeamAwareness（咨询义务收敛为可选 ConsultDuty 组件，不再按 mandate 分裂会话类型；ADR-0035 / ADR-0036） |
| SimpleReasoner / SupervisorReasoner | PromptReasoner（单一 Reasoner；lead 提示词差异由 TeamAwareness 自渲染表达，组合期不再"升级" reasoner；ADR-0035） |
| generate_candidates | generate_thoughts（Reasoner 协议方法；候选竞争语义早已不存在，化石名废除；ADR-0035） |
| mandate_uses_consultation_session / as_consultation / as_routing | 已删除；组合期决定 ConsultDuty 是否挂载，运行期无类型窄化（ADR-0035） |
| AgentState.session / RunContext.session | AgentState.team_awareness / RunContext.team_awareness（ADR-0035） |
| OpenAICompatLLM | OpenAICompatAdapter |
| SharedMemoryTool / SkillRecord / KGTriple | 已删除（共享记忆经 SharedMemoryStore；记忆契约收敛为 MemoryRecord） |
| StructuredDecision | Decision |
| TypedState | AgentState |
| ActResult | Observation |
| DelegationLedger / team_progress | MemberStatus / member_status |
| ledger / 账本 / settlement（措辞） | 已废除（ADR-0036）；统一为「委派回报记录」（TeamAwareness.results）与「咨询义务」（ConsultDuty） |
| roster / roster_desc | teammates_text |
| AgentEntrypoint / TeamEntrypoint | AgentUnit / TeamUnit |
| SimpleAgent / BaseAgent | CognitiveAgent |
| assemble_base_agent | assemble_agent |
| execute（Agent 入口） | run |
| CompletionPolicy / RosterCoverage | DecisionGate / MustConsultAllMembers |
| LoopJudge / TerminationSignal（对外） | StopRule / StopDecision |
| judge（CognitiveRuntime 参数/字段） | stop_rule |
| default_loop_judge.py | default_stop_rule.py |
| brain_strategy（Agent/Assembly 参数） | brain |
| BrainStrategy | Brain |
| PromptManager / SimplePromptManager | Reasoner 内建模板字典（已溶解） |
| member_status/policy.py | member_status/required_action.py |
| FallbackPolicy / FallbackActionPolicy / FallbackDecoratedBody | DegradationPolicy / GracefulDegradation（降级前移至防腐层解析期，Body 不再承载异常驱动的降级装饰） |

## 禁止复活

除上述废弃名外，以下设计模式同样禁止重新引入：

- 三维旋钮（Family / Plane / Mode）与 Recipe / TeamProcess 公共面（ADR-0030）
- 运行期团队上下文包 / 配置袋（TeamContext / TeamConfig）：团队形态只由 TeamSpec.governance 表达，策略构造期闭合（ADR-0034）
- 编排器概念（TeamOrchestrator）：编排决策在组合期烘焙进策略，运行期句柄不编排（ADR-0034）
- strategy_key 字符串在运行期流转：仅组合期派生一次，作注册表分发键与遥测标签（ADR-0034）
- 双重公开 stop 类型（对外只保留 `StopRule` / `StopDecision` 单通道）
- Agent 入口签名带 `**context: str`（用 `RunContext` 类型化上下文替代）
- progress-text 字段 + 注入 hook 三件套（用 `MemberStatus` 替代）
- lead 会话分裂（ConsultationState / RoutingState 联合 + `as_*` 窄化 + mandate→会话类型映射函数）：团队认知是单一 `TeamAwareness`，咨询义务是其可选 `ConsultDuty` 组件（ADR-0035 / ADR-0036）
- 按 mandate 升级/替换 Reasoner（`from_simple` 之类的 promotion）：Reasoner 单一实现，团队差异经 `AgentState.team_awareness` 数据注入（ADR-0035）
- 字段白名单断言看守会话 dataclass：概念统一后无裂缝可守，纯净门禁（ADR-0015）兜底（ADR-0035）
