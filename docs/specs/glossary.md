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
| **spawn_agent** / **spawn_team** | L4 组合根函数：从 AgentSpec / TeamSpec 封闭组装 Agent / Team 对象图（ADR-0056）；无 Composer 类 |
| **multi-delegate** | 一步并行委派多个角色（`Decision.delegations` 多条 + DelegateOperation gather） |
| **Result** | 运行最终结果：status / output / budget / error |
| **run** | 全链路唯一生命周期动词（Agent / Team / CognitiveRuntime） |

## L-Team

| 术语 | 定义 |
|---|---|
| **Registries** | 三个发现型注册表的值对象包（components / brain_factories / orchestration），由 `spawn_team` 持有，替代进程级全局单例 |
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

## Gateway 概念（非 LCA 核心）

Gateway 层类名（不要求加粗为术语词条）：
ArgsTransform, Artifact, ArtifactLedger, FieldMapper, GatewayCollector,
IngestCache, LLMResolver, ModeDefinition, ModelDefinition, ParsedMessages

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
| **SpanName** / **EventName** | 封闭遥测词表（span 名 / 业务事件名），配 **VocabDef** 目录登记唯一发射点 |
| **SpanView** | OTel span 的本地投影视图 |
| **AttributePolicy** / **Verbosity** | 属性策略（脱敏/截断，写入期强制）与信息量档位（minimal/standard/verbose） |
| **JournalEvent** / **RuntimeObserved** / **RunScope** / **StampedEvent** | 领域事实事件 / 插件、Hook、工具、LLM、记忆与传输的运行解释事件 / 关联骨架 / 盖章记录 |
| **EventDescriptor** / **EventPlane** / **EventProjection** | 事件的唯一治理描述（受众、敏感性、保留、发射边界）/ 事实、结构、解释三平面 / 已提交事件的只读投影协议 |
| **RunStore** | 运行事件账本：词表校验 → 关联盖章 → 策略强制 → 原子追加 → 提交后投影；查询与洞察不进写路径 |
| **JournalProjector** / **ProjectionRegistry** | 兼容投影契约 / 按装配顺序分发已提交事件并隔离投影故障的注册表 |
| **TraceInspector** / **TraceReport** | 面向 Coding Agent 的只读账本检查器 / 可序列化的因果链、失败、瓶颈、复现与插件交互图报告 |
| **OtelProjector** / **ConsoleJournalProjector** / **JsonlJournalProjector** | journal → OTel span（显式定父）/ console 场景卡·叙事·Run Card·序列图 / jsonl 落盘投影器 |
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
| **ToolManifest** / **ToolApi** | 一组工具的声明式清单（identifier + api surface），对齐 LobeHub BuiltinToolManifest |
| **ExecutionTarget** / **ExecutionPlan** | 执行路由：sandbox / device / auto / none + fallback |
| **GatewayHttpClient** | Layer0 访问 `/api/device/*` 的 HTTP 客户端 |
| **SandboxPolicy** | 沙箱可写根 / 禁写根 / 网络 / 环境白名单 |
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
| **calculator** / **weather** | 内置示例 Tool 模块（manifest + executor） |
| **ArtifactLedger** | 工作区产物账本：路径 → url 映射 + MIME / 大小元数据；Body finalize 写、LobeHub 渲染读 |
| **CLIConfig** / **CLIProvider** | lca-ops CLI 配置 + provider 解析（基于 pydantic-settings） |
| **ChangeReport** | 升级 / patch 应用的结果报告（lobehub stack 部署侧） |
| **ClockSensor** | PerceiveHub 命名工厂 `sensor.clock`：从 journal 上下文读时间戳，避免第三条时钟 |
| **ComputerOps** | ComputerRuntime 协议（命令 + 输出 + 异步等待） |
| **Console** / **ConsoleConfig** | 控制台输出 + 配置（ANSI / 日志级别） |
| **DaemonConfig** / **DaemonService** | lca-ops daemon 进程管理（uptime / health / start-stop） |
| **WorkspaceArtifactsSensor** | PerceiveHub 命名工厂 `sensor.workspace-artifacts`：从 ArtifactLedger 读当前 run 产物 |
| **InboxFactsSensor** | PerceiveHub 命名工厂 `sensor.inbox-facts`：从 journal `InboxFollowupCreated` 读用户输入 |
| **TeamInboxSensor** | PerceiveHub 命名工厂 `sensor.team-inbox`：从 journal `TeamMessagePublished` 读跨 agent 消息 |
| **WorkspaceInstructionsSensor** | PerceiveHub 命名工厂 `sensor.workspace-instructions`：读 AGENTS.md 作为指令通道事实 |
| **SkillCatalogSensor** | PerceiveHub 命名工厂 `sensor.skill-catalog`：从 OperationalSkillRegistry 读当前可见 skill 列表 |
| **Blackboard** / **InMemoryBlackboard** / **BlackboardEntry** / **Lease** | 团队共享工件 + 租约协议与内存实现（v3 §11 / PR9b） |
| **MemoryPolicy** / **CompactionPolicy** / **MemoryWrite** / **MemoryCommitResult** | 记忆策略协议（v3 §8 / PR7）；禁止裸 read/write |
| **RepeatToolCallGate** / **ToolLoopBreakerGate** / **TerminalRespondGate** / **OfficeWorksSealer** / **ArtifactRespondInjector** | 决策出门 Gate（v3 §3.5 / PR4） |
| **GateDecided** / **PolicyFact** | Gate 出门判定事件 + 提示词用政策事实（v3 §3.5 / PR4） |
| **ExecutionEnvelope** / **envelope_from_decision** | Body.act 必须收到的执行包（v3 §9.1 / PR6） |
| **SimpleMemoryPolicy** / **SimpleCompactionPolicy** | MemoryPolicy / CompactionPolicy 默认实现 |
| **DiagnosePattern** / **diagnose_loop_stuck** / **diagnose_model_not_seen** / **diagnose_memory_poisoned** / **diagnose_approval_rejected** | v3 §24.5 诊断模式（CLI `lca-ops diagnose`） |
| **DiagnosisReport** | 诊断模式输出报告（根因 + 修复建议 + 证据链） |
| **FilesInfoDocument** | 文件元数据文档（路径 + mime + 大小 + 校验和） |
| **Finding** | 检索 / 诊断发现的原子单元（source + claim + confidence） |
| **HealthCheck** / **HostEnvironment** / **InfraConfig** / **InfraService** | 基础设施探活 + 主机环境 + 配置（lca-ops heal 子命令） |
| **LLMFace** / **ProductionLLMResolver** | LLM 适配门面 + 解析器（多 backend / 多 mode 路由） |
| **MachineComputer** | ComputerRuntime 协议的具体机器实例（local subprocess / docker / e2b） |
| **ModelDefinition** | LLM 模式定义（model id + adapter + 价格 + 限额） |
| **NullSink** | ManifestSink no-op 实现（测试用） |
| **OpsConfig** | lca-ops 全局配置（基于 pydantic-settings） |
| **PathConfig** / **PathProvider** / **PlaneRequest** / **ResolvedEndpoint** / **WorkspaceProvider** | 路径配置 + provider + 平面请求 + endpoint 解析 + workspace provider |
| **ProgressLoopDetector** | 同名工具调用循环检测（DecisionGate 组件） |
| **Provider** / **ProviderDispatch** | LLM / Tools / Search provider 协议 + 分发 |
| **SearchHit** / **SearchService** | 检索命中 + 检索服务 |
| **Service** / **SkillsService** / **ToolsConfig** / **ToolsProvider** / **ToolsService** / **UserConfig** / **UserProvider** / **VenvConfig** / **VenvProvider** | 平台 service 协议与实现（L4 门面下的服务注册） |
| **Sudo** | 提权操作适配（仅安全操作走；v3 spec 显式约束） |
| **Verbosity** | 日志信息量档位（minimal / standard / verbose） |

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

| **FailureExplainer** (PR-3 + PR-4) | 失败诊断与解释器（lca-ops diagnose 子命令） |
| **HostEnvironment** (PR-12) | 主机环境封装（lca-ops heal 子命令）：uptime + health + start-stop |
| **Lease** (v3 §11 / PR-9b) | Blackboard 共享工件的租约协议（团队协作隔离） |
| **MinimalReproduction** | 最小可复现 bug case 模板（tests/ 辅助） |
| **OptimizationFinder** | Profile 优化发现器（lca-ops optimize 子命令；找重复 plugin / 冲突 capability） |
| **PlaneRequest** | lca.ops 平面请求（路径配置 + endpoint 解析） |
| **PresetAuthoring** | Creator preset 写入层（PR-12 V7 publish） |
| **PresetLayout** | Creator preset 目录布局（PR-12 V7 publish） |
| **ProductionLLMResolver** | 生产环境 LLM 解析器（多 backend 路由 + 限额 + 价格） |

## 已废弃主名（PR-12 整理）

> 这些术语曾在 codebase 中存在，现已删除 / 改名 / 退役。禁止复活
> 为现役主名；新代码请使用替代术语（见上方现役区）。如果旧代码仍
> 引用这些名字，请先迁移再删除本表条目。

| 已废弃术语 | 替代 / 状态 |
|---|---|
| **BindOptions** | 计划绑定兼容选项；已退役 — 替代：严格的 `bind_plan(request, plan, scope)` |
| **DshConfig** | DeepSeek Harness 适配器；v2 遗产，已退役 — 替代：lca-ops daemon / native config |
| **DshNotification** | DSH 桥接；v2 遗产，已退役 — 替代：lca layer0_infra observability |
| **DshProbe** | DSH 桥接；v2 遗产，已退役 — 替代：lca-ops doctor |
| **DshService** | DSH 桥接；v2 遗产，已退役 — 替代：lca-ops daemon |
| **ExporterUnavailableError** | observability exporter fallback；已退役 — 替代：None fallback in facade |
| **LangfuseBridge** | Langfuse 旧版桥接；已退役 — 替代：Layer0 observability 直接 |
| **LocalMirror** | upstream fork 旧版镜像；已退役 — 替代：Layer0 upstream scan |
| **MirrorDiff** | upstream 旧版差异报告；已退役 — 替代：Layer0 upstream scan |
| **ObservabilityHub** | 旧 observability facade 类；改名 — 替代：lca.layer0_infra.observability.facade |
| **ScorerFn** | 旧版评分函数；已退役 — 替代：observability eval pipeline |
| **SpanContext** | 旧 span context 类；改名 — 替代：lca.contracts.atoms.semantic_keys.SpanContext |
| **UpstreamTree** | upstream 仓库目录树；已退役 — 替代：Layer0 upstream patch scan |


