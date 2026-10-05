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
| **Graph** | 协调机制（进阶）：按 ExecutionGraph 拓扑执行（策略键 `graph` → GraphStrategy）；拓扑遍历保持内核闭集，具体节点行为由 `GraphNodeExecutor` 原语注册表选择。 |
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
| **GraphNodeExecutor** | Graph 策略内单一节点类型的可替换行为原语；GraphStrategy 仅负责 DAG 拓扑、边语义与就绪队列，经 `graph_node_executors` registry 解析 Agent、Aggregator 与拓扑节点实现。 |
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
| **StopDecision** / **StopReason** | 循环终结载荷契约：`TerminateStrategy`（`binding: terminate`）据模型 decision / `should_terminate` 端口 / 预算守卫构建的四字段结构；无主机侧 policy 类（StopPolicy 语义缝已退役，见「已废弃主名」）。 |

| **Brain** / **Body** / **MemorySystem** | 想 / 做 / 记 |
| **ModularBrain** | 默认 Brain（reasoner / critic 可替换）；原生 function calling 直接产出 Decision，无需 DecisionParser |
| **Turn** | 单步记录：decision + act result + reflection |
| **Budget** | token / cost / steps / wall_clock 预算 |
| **Hook** / **HookRegistry** / **EventBus** | 生命周期钩子与事件总线。`EventBus`（canonical 名 `EnvelopeBus`，ADR-0183）是进程级实时事件分发机制（publish → hook → sink dispatch），不是事实平面。事实平面 SSOT 是 `Session.append`（ADR-0186/0192）。 |
| **Telemetry** | 业务层唯一发射门面契约：span / event / score，不耦合任何后端 |
| **SpanName** / **EventName** | 封闭遥测词表（span 名 / 业务事件名），配 **VocabDef** 目录登记唯一发射点 |
| **SpanView** | OTel span 的本地投影视图 |
| **AttributePolicy** / **Verbosity** | 属性策略（脱敏/截断，写入期强制）与信息量档位（minimal/standard/verbose） |
| **JournalEvent** / **RuntimeObserved** / **RunScope** / **StampedEvent** | 领域事实事件 / 插件、Hook、工具、LLM、记忆与传输的运行解释事件 / 关联骨架 / 盖章记录 |
| **EventDescriptor** / **EventPlane** / **EventProjection** | 事件的唯一治理描述（受众、敏感性、保留、发射边界）/ 事实、结构、解释三平面 / 已提交事件的只读投影协议 |
| **RunStore** | 运行事件账本：词表校验 → 关联盖章 → 策略强制 → 原子追加 → 提交后投影；查询与洞察不进写路径 |
| **JournalProjector** / **ProjectionRegistry** | 兼容投影契约 / 按装配顺序分发已提交事件并隔离投影故障的注册表 |
| **TraceInspector** / **TraceReport** | 面向 Coding Agent 的只读账本检查器 / 可序列化的因果链、失败、瓶颈、复现与插件交互图报告 |
| **ConsoleJournalProjector** | journal → console 场景卡·叙事·Run Card·序列图投影器；容器事件分派表与 OTel 投影器句柄同构（OtelProjector / JsonlJournalProjector 名已废弃，见「已废弃主名」）。 |
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
| **SimpleSafeExecutor** | SafeExecutor 默认实现 |
| **SimpleToolRegistry** | ToolRegistry 默认实现 |
| **InMemoryStateStore** | StateStore 内存实现 |
| **ArtifactLedger** | 工作区产物账本：路径 → url 映射 + MIME / 大小元数据；Body finalize 写、LobeHub 渲染读 |
| **CLIConfig** / **CLIProvider** | lca-ops CLI 配置 + provider 解析（基于 pydantic-settings） |
| **ChangeReport** | 升级 / patch 应用的结果报告（lobehub stack 部署侧） |
| **ClockSensor** | PerceiveHub 命名工厂 `sensor.clock`：从 journal 上下文读时间戳，避免第三条时钟 |
| **ComputerOps** | ComputerRuntime 协议（命令 + 输出 + 异步等待） |
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


| **AttachmentManifest** | 文件元数据文档（路径 + mime + 大小 + 校验和） |
| **Finding** | 检索 / 诊断发现的原子单元（source + claim + confidence） |
| **HealthCheck** / **HostEnvironment** / **InfraConfig** / **InfraService** | 基础设施探活 + 主机环境 + 配置（lca-ops heal 子命令） |
| **LLMFace** / **ProductionLLMResolver** | LLM 适配门面 + 解析器（多 backend / 多 mode 路由） |
| **MachineComputer** | ComputerRuntime 协议的具体机器实例（local subprocess / docker / e2b） |
| **ModelDefinition** | LLM 模式定义（model id + adapter + 价格 + 限额） |

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

## Phase B batch-1：观测 / 事件 / 持久化 / 语音 / 记忆（ADR-0291）

> ADR-0291 Phase B 第 1 批：`test_glossary_term_coverage`（forward）68 个无匹配词根中的 22 个。
> 定义逐一取自类 docstring / 模块 docstring 实证；后续批次与 reverse 处置见 ADR-0291 §3 Phase B。

| 术语 | 定义 |
|---|---|
| **ActivityFeed** | run 账本的纯折叠视图：按 run 级折叠为 activity 行（`lca.infrastructure.observability.activity_feed`） |
| **SpineEmitter** | 五面矩阵默认 EventEmitter：调用 `EventSpine.append`（ADR-0167 D11） |
| **SpineHandler** | SpineRegistry 登记项：执行点（EP）与其 wrap_fn 的绑定；Handler 为命名宪法 §4.1 合法后缀（ADR-0290 豁免归档） |
| **SpineLike** | SpineEmitter 期望的最小鸭子类型表面（Protocol） |
| **SpineRow** | 单条 spine 行的容错视图（dict 子类；`payload` 为生产者写入的 dict） |
| **NdjsonSerializer** | 五面矩阵默认序列化器：utf-8 ndjson 一行一记录（ADR-0167 D11） |
| **MetricsProjection** | metrics 出口：计数器派生自 spine 事件（`LoopProjectionDefinition`，ADR-0172 D1） |
| **StepGroupedReader** | journal.json 无状态读取器：反序列化 JournalDocument（ADR-0164 草案） |
| **AtomicJsonSnapshot** | 整文件 JSON 快照的待写载荷（write-behind 目标，整文件缓存） |
| **WriteBehindBuffer** | 有界 write-behind 批量写缓冲区（Session persistence 内部基础设施） |
| **WakeClassifier** | 按入站线索与触发方式分类，生成强类型 WakeContext（vocal） |
| **ReplyFirstMiddleware** | Reply-First 承接提醒中间件：用户在场且未 Ack 时提醒模型先发声（vocal） |
| **RenderContract** | 工具数据 → 渲染器期望的映射契约（render 契约定义与注册表） |
| **ConnectionMetadata** | 连接器实例元数据：活跃 / 待建的连接器实例（连接器状态机契约 INV-01/02/03） |
| **ResolvedEndpoint** | 面孔解析后的不可变 LLM 端点（pydantic settings；调用方不得重读 env） |
| **RoomDispatcher** | room 运行时分发器：消息摄取 / run 分发 / 懒复活（room runtime M1 + Phase 2） |
| **DeliveryMaterial** | 控制轮折叠出的用户可见交付材料视图（ADR-0196） |
| **SalienceVerdict** | 显著性门控裁决：记忆候选的新颖性 / 复用价值 / 稳定性（防单次偶发泛化为偏好） |
| **ConsolidationDecider** | consolidation 决策器协议：RuleDecider（确定性规则）/ LayaDecider（模型打分）可互换（ADR-0277 §2.3） |
| **ShadowComparator** | Shadow 模式比较器：双轨并行打分，结果追加写 JSONL（ADR-0277 Phase 3） |
| **SemanticClaim** | 语义记忆：提炼出的事实断言（Tulving semantic；对应 LCA L2 MEMORY.md 层） |
| **SourceVerifier** | 对最终答案做来源感知校验（ProvenanceGuard 思想的结构化实现） |


## Phase B batch-2：调度 / 持久化 / 守卫（ADR-0291）

> ADR-0291 Phase B 第 2 批：`test_glossary_term_coverage`（forward）68 个无匹配词根中的 17 个。
> 定义逐一取自类 docstring 实证；批次划分见 ADR-0291 §3。

| 术语 | 定义 |
|---|---|
| **CronScheduler** | 文件锁互斥的 cron tick 调度器（ADR-0268 §7、§8） |
| **CronWorkerRunner** | 执行一次到期 CronJob occurrence 并报告产出的 worker |
| **ProactiveScheduler** | 文件锁互斥的主动消息 tick 调度器 |
| **ProactiveDeliverer** | 主动消息投递器：session append 是唯一的写路径 |
| **RoutineTickDriver** | 例程单次 tick 驱动：带 C5 故障隔离（ADR-0263 §10） |
| **StandardDriver** | 五面矩阵默认 StepDriver：显式栈（Frame 列表） |
| **PersistenceCoordinator** | 持久化协同器协议（ADR-0169 D8） |
| **PersistenceStats** | 持久化协同器运行时统计（ADR-0169 PR-25 S3 装配） |
| **SessionPersistenceFlushListener** | `Session.register_flush_listener` hook：排空 run write-behind 缓冲区 |
| **SessionLike** | 投递所需的 Session 最小公开接口（避免依赖具体实现类） |
| **DeadLetter** | 重试耗尽的例程（C5；保留 7 天） |
| **RevivalCoordinator** | 后台子代理完成复苏协调器：接收子代理上报并唤醒父进程统一开口交付 |
| **SpendGuard** | 例程消费硬护栏与 Token 熔断器 |
| **VocalSettleGuard** | 声带轮次结算核验硬闸 |
| **StepCoordinator** | 五面矩阵唯一写入口：Agent 调 driver/segment 状态；spine EP 由 cursor 派生 |
| **RuleDecider** | consolidation 确定性编排：encode → link → decay（schema 走离线，不在在线路径） |
| **ProceduralRule** | 程序性记忆：怎么做（Soar procedural；对应 LCA skills 层） |


## Phase B batch-3：感知 / 记忆 / 认知（ADR-0291）

> ADR-0291 Phase B 第 3 批：`test_glossary_term_coverage`（forward）仍无匹配的 21 个词条。
> 定义逐一取自类 docstring 实证（TypeDiagnostic 无 docstring，定义取自字段结构）；
> 批次划分见 ADR-0291 §3。

| 术语 | 定义 |
|---|---|
| **SemanticPercept** | 语义感知：一条被召回的事实断言 |
| **EpisodicPercept** | 情景感知：一次被召回的情景记忆（C1 typed，禁止裸文本） |
| **RelationPercept** | 人物/群组上下文感知（v1：构造时注入的静态映射，接 people/groups） |
| **DialogueScenario** | 单套完整的多轮对话场景用例（eval） |
| **PeopleDirectory** | 人物页目录：contextfiles 服务，一个 assistant home 的 Person pages |
| **GroupsDirectory** | 群组页目录：contextfiles 服务，一个 assistant home 的 Group pages |
| **Deriver** | spine 派生订阅者基类：从每个事件派生次级产物 |
| **WaterfallDeriver** | 累积事件并渲染 HTML 瀑布图（observability） |
| **LayaDecider** | Laya 模型打分版 decider：noul（值得提炼吗）+ choice（冲突三选一） |
| **LayaScoredItem** | Laya 单候选打分明细 |
| **LinkDecider** | link 对账：新 claim 与现有 claim 逐条对账 |
| **KernelServeSpawner** | 启动一次 `lca_kernel serve`；轮询 /health 直到就绪（CLI 服务） |
| **KernelSupervisor** | 受监督的 LCA kernel 子进程（CLI 服务） |
| **TypeDiagnostic** | 类型检查单条诊断记录：`tool/path/line/column/message/code`（frozen dataclass） |
| **StandardCursor** | 默认 ReplayCursor 实现（ADR-0167 D10） |
| **StdCloseBarrier** | CloseBarrier 默认实现（ADR-0169 D5） |
| **StackFrame** | 捕获到的 traceback 的一帧（ADR-0122） |
| **WeightedItem** | 带相关性分数的呈现排序项（presentation） |
| **SqliteLearningReviewTicketDatabase** | review-ticket 操作共享的持久化数据库边界（SQLite） |
| **RuleSchemaExtractor** | v1 规则版 schema 提炼（Letta sleep-time consolidation 的占位实现） |
| **SchemaExtractor** | sleep-time 提炼协议：离线 pass，从 episodic 提炼 semantic |


## Phase B batch-4：连接器 / 商用（ADR-0291）

> ADR-0291 Phase B 第 4 批（收官）：连接器与商用域 8 个核心类。forward 测试已在 batch-3 后
> 转绿（词根级匹配 ≤10 门限），本批为词条级补齐；定义逐一取自类 docstring 实证。

| 术语 | 定义 |
|---|---|
| **ConnectorVault** | 按用户隔离安全地管理连接器连接（vault） |
| **ConnectorPermissionEngine** | 连接器操作的双层权限矩阵求值器 |
| **ComposioIntegration** | LCA 原生 Composio 运行时（连接 SSOT 为本地连接存储） |
| **GmailConnectorCLI** | Gmail 连接器命令的 CLI 执行器 |
| **BrowserSubagent** | 自动化浏览器执行子代理 |
| **WechatChannelWorker** | 微信通道 worker：为一个 Assistant 处理长轮询循环与消息分发 |
| **CommercialEvalSuite** | 商用评测全量剧本集容器 |
| **DegradationKind** | 工具失败降级分类 |


## ADR-0292 授权语义隔离机制词条（2026-10-05）

> ADR-0292（已 Accepted）C1 落地的新机制词条补录：实现已在
> `lca/contracts/models/core/execution/external_content.py`、
> `lca/contracts/runtime/trust.py`、`lca/cognition/body/emit/observation_surface.py`
> 落盘，词表滞后；定义逐一取自源码 docstring 实证。

| 术语 | 定义 |
|---|---|
| **ContentOrigin** | 内容段来源标记（StrEnum：EXTERNAL/INTERNAL，ADR-0292 C1）；EXTERNAL=工具结果/网页抓取/文件读取/子 agent 或 peer 报告——不带指令权 |
| **fence_external_content** | 把文本包进外部内容围栏的函数；ContentOrigin.EXTERNAL 的模型可见呈现（一源两呈现）；语义标签非安全边界，防不住恶意生产者自伪造标记 |
| **Observation.content_origin** | Observation 的来源字段，fail-closed 默认 EXTERNAL；鸭子类型旧对象走 getattr 兼容 |
| **TrustEnvelope** | frozen dataclass：单次 run 的插件来源闭集 + 权限天花板（ADR-0199 §3.4），ADR-0292 的权限唯一来源载体之一 |
| **observation_content** | 提示词渲染落点：Observation.payload → surface/tool_result 字符串；EXTERNAL payload 围栏、INTERNAL 直通（ADR-0292 C1） |


## 已废弃主名（PR-12 整理）

> 这些术语曾在 codebase 中存在，现已删除 / 改名 / 退役。禁止复活
> 为现役主名；新代码请使用替代术语（见上方现役区）。如果旧代码仍
> 引用这些名字，请先迁移再删除本表条目。

| 已废弃术语 | 替代 / 状态 |
|---|---|
| **BindOptions** | 计划绑定兼容选项；已退役 — 替代：严格的 `bind_plan(request, plan, scope)` |
| **Console** / **ConsoleConfig** | 旧 observability 控制台 facade；已退役 — 替代：layer0 observability facade + projector |
| **ExporterUnavailableError** | observability exporter fallback；已退役 — 替代：None fallback in facade |
| **LangfuseBridge** | Langfuse 旧版桥接；已退役 — 替代：Layer0 observability 直接 |
| **LocalMirror** | upstream fork 旧版镜像；已退役 — 替代：Layer0 upstream scan |
| **MirrorDiff** | upstream 旧版差异报告；已退役 — 替代：Layer0 upstream scan |
| **ObservabilityHub** | 旧 observability facade 类；改名 — 替代：lca.infrastructure.observability.facade |
| **ScorerFn** | 旧版评分函数；已退役 — 替代：observability eval pipeline |
| **SimpleEventBus** | 本地事件分发兼容实现；已退役 — 替代：`EnvelopeBus`（ADR-0183） |
| **SimpleHookRegistry** | 本地钩子分发兼容实现；已退役 — 替代：由 booted Cordis Context 持有的 `CordisHookRegistry` |
| **SpanContext** | 旧 span context 类；改名 — 替代：lca.contracts.atoms.semantic_keys.SpanContext |
| **UpstreamTree** | upstream 仓库目录树；已退役 — 替代：Layer0 upstream patch scan |
| **StopPolicy** | Stop 阶段状态群策略语义缝；已退役 — 替代：`TerminateStrategy`（`binding: terminate`）+ `StopDecision` / `StopReason` 契约（`docs/plans/2026-09-14-stop-decision-retirement.md`） |
| **DefaultStopPolicy** | `plugins/state/stop_policy.py` 默认终止判定；已退役 — 替代：同 StopPolicy |
| **JsonlJournalProjector** | journal jsonl 落盘投影器名；从未落地为类 — 替代：`ConsoleJournalProjector` |
| **OtelProjector** | journal → OTel span 投影器名；从未落地为类 — 替代：Layer0 observability 直接 |
| **GatewayHttpClient** | Layer0 访问 `/api/device/*` 的 HTTP 客户端名；legacy 别名，从未落地为类 — 替代：`device_hub` client |
| **DiagnosePattern** | v3 §24.5 诊断模式名（CLI `lca-ops diagnose`）；无类定义 — 替代：现行 diagnose 诊断实现 |
| **DiagnosisReport** | 诊断模式输出报告名（根因 + 修复建议 + 证据链）；无类定义 — 替代：同 DiagnosePattern |
| **NullSink** | ManifestSink no-op 实现名（测试用）；代码中零引用 — 替代：测试内联 no-op |
| **CandidateEvaluationPipeline** | 候选评估流水线；已删除 — 替代：无（ADR-0291 Phase B 移入废弃表） |
| **DecisionParser** | 决策解析器；已删除 — 替代：原生 function calling 直接产出 Decision（`ModularBrain`） |
| **DegradationPolicy** | 降级策略；已删除 — 替代：无（ADR-0291 Phase B 移入废弃表） |
| **GracefulDegradation** | 优雅降级；已删除 — 替代：无（ADR-0291 Phase B 移入废弃表） |
| **SimpleDecisionParser** | 决策解析器简单实现；已删除 — 替代：同 DecisionParser |



## Bulk-port additions (2026-08-30)

Classes brought over from main's bulk port (commit 46094979 + follow-ups).
Some are existing concepts with new names; some are entirely new.

| 术语 | 定义 |
|---|---|
| **CausationEnricher** | JournalRecord Causation 字段的丰富器（主路径 → daemon 端 fallback） |
| **DeclarativeCheckpoint** | 声明式 checkpoint：阶段图节点冻结点（resume 时从 checkpoint 续跑） |
| **DocumentEnricher** | tool 观察 document 字段的丰富器 |
| **EvidenceBinding** | Evidence store binding：tool 观察引用 → content-addressed payload 的桥 |
| **LLMFailoverCandidate** | LLM failover 候选：resolver 选不到主模型时的备用 backend |
| **LiveGap** | SSE StreamEvents 心跳帧：长空闲期保持连接 |
| **LiveTail** | gateway 实时流：JSONL → SSE 帧的转换 |
| **NarrativeSidecar** | narrative journal 与 RunLocator 的 sidecar 索引（PR-6 plan_ref × Journal） |
| **OrderedContribution** | 阶段图节点贡献值的有序枚举 |
| **PhaseLiftingEnricher** | phase JSONL → UI state 的提升丰富器 |
