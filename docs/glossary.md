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
| **ModularBrain** | 默认 Brain（reasoner / critic 可替换）；原生 function calling 直接产出 Decision，无需 DecisionParser |
| **Turn** | 单步记录：decision + act result + reflection |
| **Budget** | token / cost / steps / wall_clock 预算 |
| **Hook** / **HookRegistry** / **EventBus** | 生命周期钩子与事件总线（业务事实经遥测桥进入 trace 管道） |
| **Telemetry** | 业务层唯一发射门面契约：span / event / score，不耦合任何后端 |
| **ObservabilityHub** | 可观测性唯一门面对象：OTel 骨干 + 属性策略 + journal + 投影器 fan-out + 生命周期；满足 **ObservabilityBackend** 结构契约 |
| **SpanName** / **EventName** | 封闭遥测词表（span 名 / 业务事件名），配 **VocabDef** 目录登记唯一发射点 |
| **SpanView** / **SpanContext** | OTel span 的本地投影视图 / 当前关联上下文（trace/span id） |
| **AttributePolicy** / **Verbosity** | 属性策略（脱敏/截断，写入期强制）与信息量档位（minimal/standard/verbose） |
| **JournalEvent** / **RunScope** / **StampedEvent** | journal 事件基类 / 关联骨架（trace·run·parent·delegation id）/ 引擎盖章记录（ADR-0037） |
| **ExecutionJournal** | 执行日志引擎：词表校验 → 关联盖章 → 策略强制 → 投影器扇出（Journal-as-Truth 写入端） |
| **JournalProjector** | journal 投影契约：OTel / console / jsonl / 序列图 / 洞察皆为投影 |
| **OtelProjector** / **ConsoleJournalProjector** / **JsonlJournalProjector** | journal → OTel span（显式定父）/ console 场景卡·叙事·Run Card·序列图 / jsonl 落盘投影器 |
| **InsightEngine** | 洞察引擎：聚合 journal 触发规则（冗余调用/循环/关键路径/成本），RunInsight 回注 |
| **LangfuseBridge** / **ExporterUnavailableError** | Langfuse 后端桥接（OTel 原生 SDK 挂接）/ 导出器不可用异常 |
| **LLMResponse** / **TokenUsage** | LLM 结构化返回（文本 + 模型 + token 用量），成本链路单一事实源 |
| **StateStore** / **StateSnapshot** | 状态持久化与快照 |

## L-Plugin / L0

| 术语 | 定义 |
|---|---|
| **Reasoner** / **Critic** | 候选生成 / 自省 |
| **Action** / **ActionRegistry** / **ActionType** | 行动能力与路由（内置行动类型：respond / use_tool / delegate / handoff / stop / ask_human） |
| **RespondOperation** / **UseToolOperation** / **DelegateOperation** / **HandoffOperation** | 内置行动实现（delegate/handoff 行动 ≠ PeerRelay 协调机制） |
| **SafeExecutor** | 权限 + 重试 + 缓存后执行工具 |
| **ToolRegistry** / **Tool** / **ToolPermissionManifest** | 工具注册与权限 |
| **Sandbox** / **SandboxResult** / **SandboxFile** | 隔离代码执行协议与终态结果（ADR-0044） |
| **OnlyboxesSandboxAdapter** | Onlyboxes console `pythonExec`（需 `ONLYBOXES_BASE_URL` + `ONLYBOXES_ACCESS_TOKEN`） |
| **SandboxExecuteTool** (`sandbox_execute`) | 沙箱代码执行工具（内部/测试）：挂载附件、多文件产物、铸造 invocation_id；预装包见 `SANDBOX_PREINSTALLED_PYTHON_PACKAGES` / `deploy/onlyboxes`。Agent 面使用 computer tools（`execute_code` 等） |
| **run_attachment_scope** | 本 run 用户附件 id 的 ambient 作用域；Gateway CreateRun → execute_run 绑定，沙箱工具自动挂载到 `/mnt/data/<name>`（ADR-0046） |
| **SANDBOX_PREINSTALLED_PYTHON_PACKAGES** | Onlyboxes pythonExec 镜像 baseline 预装包清单（与 `deploy/onlyboxes/requirements-python.txt` 对齐） |
| **SandboxOutputDelta** | 沙箱执行期 stdout/stderr 增量 journal 事件（standard 可见，进 trace 不进 chat 答案） |
| **LCA_SANDBOX_BACKEND** | 可选；仅 `onlyboxes` 受支持。缺省时只要 Onlyboxes 凭证齐全即挂载沙箱工具 |
| **RetryPolicy** / **CacheConfig** | 重试与缓存配置 |
| **BrainFactory** / **SimpleBrainFactory** | Brain 工厂（注册表用 NamedRegistry） |
| **Synthesizer** / **ConcatSynthesizer** | 并行结果聚合协议 / 默认拼接实现 |
| **LLMAdapter** / **OpenAICompatAdapter** / **MockLLMAdapter** / **TelemetryLLMAdapter** | 多厂商 LLM 适配协议与实现（Telemetry 为装饰器）；gateway 装配侧含 production resolver、mode definition、gateway collector |
| **LLMSettings** | LLM 生成参数配置（pydantic-settings，`LLM_*` env；含 temperature / max_tokens / thinking） |
| **LLMStreamEvent** / **LLMStreamEventType** | provider-neutral 流式事件契约；``COMPLETED.response`` 与同次 ``complete()`` 返回值一致 |
| **LLMApiStyle** | OpenAICompatAdapter 内部 wire-protocol 选择（Responses 默认 / Chat Completions opt-in） |
| **FinishReason** | LLM 生成结束原因归一（stop / length / tool_calls …）；`length` + tool_call → incomplete（ADR-0047） |
| **ToolArgumentsOutcome** | 工具 arguments wire 三态：Ok / Incomplete / Invalid（ADR-0047） |
| **tool_wire_status** / **tool_wire_gate** | Decision.extra 工具 wire 状态与 Body 执行闸门；incomplete 禁止执行、软失败回灌 loop（ADR-0047） |
| **AgentTransport** / **TransportRegistry** / **InternalTransport** / **A2ATransport** / **MCPTransport** | 传输协议、注册与实现 |
| **ComponentRegistry** / **NamedRegistry** | DI / 按名注册表（ComponentRegistry 是 category → NamedRegistry 的组合器） |
| **RegistryKeyError** | 注册表硬查询失败异常（继承 ValueError） |
| **team_wiring** / **build_team_transport** | L4 团队 channel 接线（与 agent 组装决策分离） |
| **SkillRouter** / **KeywordSkillRouter** / **StaticSkillRouter** | 运行时动态选择 Prompt 模板 / 工具子集（关键词 / 静态映射） |
| **load_builtin_prompt** | 从 ``brain/prompts/*.md`` 加载内置模板 |
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
| **Intent Shape / normalize_intent_shape** | 决策意图形状归一（伪工具→行动、response_text 提升；ADR-0045 Canonical Model） |
| **SimpleEventBus** | EventBus 默认实现 |
| **SimpleHookRegistry** | HookRegistry 默认实现 |
| **SimpleSafeExecutor** | SafeExecutor 默认实现 |
| **SimpleToolRegistry** | ToolRegistry 默认实现 |
| **InMemoryStateStore** | StateStore 内存实现 |
| **CalculatorTool** / **WeatherTool** | 内置示例 Tool |

## L-Casting（自动组队，ADR-0042）

| 术语 | 定义 |
|---|---|
| **RoleLibrary** | 角色库抽象（Protocol）：index() 产精简目录供选角，get() 取完整角色卡；文件实现 FileRoleLibrary 在 gateway 扫描 AGENCY_ROLES_DIR（默认仓库 roles/） |
| **RoleIndexEntry** | 精简索引条目：role_id / title / department / summary，只进组队提示词，控制 token 成本 |
| **RoleCard** | 单个角色的完整声明式定义：字段对齐 AgentSpec.profile（title→role，summary→goal 基底，backstory→角色卡全文） |
| **SelectedRole** | 一次选角中的单个角色：role_id + 可选 task_hint（该角色在本次任务中的分工） |
| **CastingPlan** | 一次 casting 的产物：白名单校验过的选角 + 治理方式（既有九词表），编译成 TeamSpec 前的声明式中间形态 |
| **TeamCaster** | 选角抽象（Protocol）：cast(objective, library, llm) → CastingPlan；自动组队中唯一异步、不确定的步骤 |
| **LLMTeamCaster** | 默认 TeamCaster：一次结构化 LLM 调用 + 白名单校验 + 一次纠正重试，失败抛 CastingError |
| **CastingError** | 自动组队判定失败：解析 / 白名单校验 / 纠正重试全部失败 |
| **RoleNotFoundError** | role_id 不存在于角色库 |


