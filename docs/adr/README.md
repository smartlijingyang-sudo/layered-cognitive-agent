# ADR

本目录只收录架构决策；过程文档不在此。
**元 ADR**（如 ADR-0074）记录跨 ADR 接受/裁剪链，是例外。

| ADR | 标题 | 核心决定 |
|---|---|---|
| [0001](0001-five-layer-separation.md) | 五层单向依赖分层 | Accepted |
| [0002](0002-cognitive-loop.md) | 认知闭环 6 步循环 | Superseded |
| [0004](0004-protocol-first-pluggability.md) | Protocol-First 可插拔设计 | Accepted |
| [0005](0005-composition-root-l4.md) | L4 组合根三职责模式 | Accepted |
| [0007](0007-interop-mcp-a2a.md) | 原生互操作协议层（MCP / A2A） | Accepted |
| [0008](0008-framework-positioning.md) | 框架定位与差异化 | Accepted |
| [0015](0015-contracts-no-behavior-classes.md) | contracts/ 仅类型与接口 | Accepted |
| [0030](0030-team-domain-language.md) | Team 领域语言（Lead / Coordination） | Accepted |
| [0033](0033-declarative-agent-spec.md) | 声明式 AgentSpec 与协议化门面 | Accepted |
| [0034](0034-closed-team-strategy.md) | 封闭 TeamStrategy 与 TeamSpec 单一事实来源 | Accepted |
| [0035](0035-team-awareness-unified-session.md) | TeamAwareness — 统一 lead 团队认知 | Accepted |
| [0036](0036-retire-financial-metaphor.md) | 废除金融隐喻—团队认知词汇统一为「回报记录 / 咨询义务」 | Accepted |
| [0037](0037-journal-as-truth.md) | Journal-as-Truth — span 降级为投影 | Accepted |
| [0038](0038-llm-stream-event-contract.md) | LLMAdapter 流式事件契约 | Accepted |
| [0040](0040-gateway-mode-catalog-contracts.md) | 协作模式契约 SSOT — gateway/mode_catalog → TS 生成 | Accepted |
| [0041](0041-prompt-reasoner-stream-text-delta.md) | PromptReasoner 流式增量文本；answer-delta 归属前端投影 | Proposed |
| [0042](0042-role-library-and-auto-casting.md) | 角色库与自动组队 | Accepted |
| [0043](0043-markdown-files-charts-without-lobehub-ui.md) | Markdown/文件产物/图表能力扩展；不引入 @lobehub/ui | Accepted |
| [0044](0044-code-sandbox-adapters.md) | 代码沙箱适配器 — Onlyboxes（退役 E2B） | Accepted |
| [0045](0045-decision-canonical-intent-shape.md) | Decision 意图形状归一 — Canonical Model | Accepted |
| [0046](0046-sandbox-file-roundtrip-contract.md) | 沙箱文件往返契约 — `/mnt/data` 输入 + `/mnt/data/outputs` 产出 | Accepted |
| [0047](0047-tool-call-wire-anticorruption.md) | 工具调用 Wire 防腐 — finish_reason + 三态 Outcome | Accepted |
| [0048](0048-operational-skill-library.md) | 操作技能库（Role/Skill 分离） | Accepted |
| [0049](0049-consultation-resource-and-evidence-planes.md) | 咨询资源 + 证据平面 — 闭合 board 协作 | Accepted |
| [0050](0050-run-bound-sandbox-runtime.md) | Run-Bound Sandbox Runtime — 单一执行平面 | Accepted |
| [0051](0051-run-workspace-plane.md) | Run Workspace Plane — 统一运行平面（Artifact/Deadline/Completion/Gate） | Accepted |
| [0052](0052-unified-dynamic-casting.md) | 统一动态选角 — 退役静态模式目录，solo/team 收成同一套 casting | Proposed |
| [0053](0053-unified-search-plane.md) | Unified Search Plane — Tavily + web_search + LLM 兜底 | Accepted |
| [0054](0054-officecli-office-plane.md) | OfficeCLI Office 平面 — 沙箱二进制 + Bundled Skill + 路由 | Accepted |
| [0055](0055-run-fact-store.md) | Run Fact Store — 不可变事件为遥测与证据平台 | Accepted |
| [0056](0056-plugin-group-contribution.md) | 群服务投稿 — 签名即依赖，配置即装箱单 | Accepted |
| [0061](0061-plugin-manifest-resolve-boot.md) | 声明式插件 Manifest（Resolve/Boot） | Accepted |
| [0062](0062-plugin-runtime-cleanup.md) | 插件运行时收口 — 单一事实源 + Cordis Fiber Boot + L4 严格闭合 | Accepted |
| [0063](0063-run-trace-ssot.md) | 运行事件账本 SSOT — Journal 事实流 + 插件化投影 | Accepted |
| [0065](0065-recoverable-evidence-ledger.md) | 可恢复的证据保真运行账本 | Accepted |
| [0066](0066-declarative-atomic-control-plugins.md) | 声明式原子控制插件—认知闭集内的可组合治理 | Proposed |
| [0067](0067-spacetime-runtime-and-governed-creation.md) | 时空运行时与受治理的动态创造 | Proposed |
| [0068](0068-compiled-plugin-kernel-and-unified-run-plan.md) | 编译式插件内核与唯一运行计划 | Proposed |
| [0069](0069-agent-primitive-system-and-declarative-grammar.md) | Agent 原语体系与声明组合语法 | Proposed |
| [0070](0070-reducer-as-plugin.md) | Reducer-as-Plugin | Accepted |
| [0071](0071-composer-per-cluster.md) | Composer-per-Cluster | Proposed |
| [0072](0072-null-default-discipline.md) | Null-Default Discipline | Accepted |
| [0073](0073-runsession-sole-session-path.md) | Session Path Convergence | Proposed |
| [0074](0074-plugin-everything-trimmed-implementation.md) | Plugin-Everything 裁剪版 | Proposed |
| [0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md) | 阶段图与可信内核 | Proposed |
| [0076](0076-six-plane-capability-layout-and-substitution-test.md) | 六平面能力布局与替换测试 | Accepted |
| [0077](0077-terminal-outcome-protocol.md) | TerminalOutcome 协议 | Proposed |
| [0078](0078-hil-approval-state-machine.md) | HIL 状态机 | Proposed |
| [0079](0079-ci-four-layer-test-discipline.md) | CI 四层测试 | Proposed |
| [0081](0081-audit-implementation.md) | ADR-0075 实施审计 | Audit |
| [0082](0082-architecture-review-2026-08-24.md) | 分层认知 Agent 架构评估 | Review |
| [0083](0083-deepseek-harness-plugin-implementation-plan.md) | DeepSeek Harness 插件布局实施计划 | Superseded |
| [0084](0084-plugin-architecture-audit.md) | 插件架构审计 | Audit |
| [0085](0085-plugin-everything-explained.md) | 插件一切架构说明 | Explained |
| [0086](0086-retire-unconsumed-loop-topology.md) | 退役未消费的 LoopTopology 生产闭包 | Accepted |
| [0087](0087-runtime-boundary-cohesion.md) | 运行时边界内聚与遗留 Run 注册表拆分 | Accepted |
| [0088](0088-profile-selected-runtime-factory.md) | Profile 选择完整 Agent Loop Runtime | Accepted |
| [0089](0089-composable-phase-observation.md) | 可组合的声明式阶段观察 | Accepted |
| [0090](0090-session-turn-task-controller.md) | 会话级 Turn 任务控制器 | Accepted |
| [0091](0091-profile-selected-followup-dispatch.md) | Profile 选择的会话 Follow-up 调度与可靠队列 | Accepted |
| [0092](0092-durable-session-command-ledger.md) | 持久化 Session 命令账本 | Accepted |
| [0093](0093-continuous-control-plane.md) | 持续执行控制面 | Proposed |
| [0094](0094-stop-policy-locality.md) | StopPolicy 的 State 群局部性 | Accepted |
| [0095](0095-loop-guard-locality.md) | LoopGuard 的解释器局部性 | Accepted |
| [0096](0096-journal-protocol-layer-everything-pluggable.md) | Journal Protocol Layer 一切插件化 — 协议 SSOT 双向落地 + 链路日志清晰 | Proposed |
| [0097](0097-event-identity-derivation.md) | Event Identity 派生策略 —— ULID（与 ADR-0065 注释一致） | Superseded |
| [0098](0098-session-spine-deltas.md) | SessionEvent 因果流扩段 + Projection 当前态双通道 —— SSE 三 event: 名称空间 | Superseded |
| [0099](0099-runs-live-openai-stream.md) | `/runs/{id}/live` 收敛到 OpenAI ChatCompletion streaming | Superseded |
| [0100](0100-chat-command-is-agent-run.md) | 聊天命令面是一次 Agent Run，不是一次模型补全 | Accepted |
| [0101](0101-tool-facts-and-evidence-only.md) | Tool 事件回归事实 —— arguments/output 经 Evidence 平面，journal 不再携带渲染字段 | Proposed |

| [0104](0104-semantic-layer-rename.md) | 语义层重命名 | Proposed |
| [0101](0101-followup-tool-call-streaming-partial-preview.md) | 工具调用流式部分预览 follow-up | Proposed |
| [0110](0110-followup-plugin-setup-generic.md) | Plugin Setup 通用化 follow-up | Proposed |
| [0119](0119-followup-gateway-name-map.md) | Gateway 名字映射 follow-up | Proposed |
| [0119](0119-followup-gateway-name-removal.md) | Gateway 名字移除 follow-up | Proposed |
| [0105](0105-package-organization-discipline.md) | Python 包目录规模与命名规范（8/10/15 规则） | Proposed |
| [0106](0106-naming-constitution.md) | 命名宪法（v3 九群归属 + 四维分解 + 角色后缀） | Proposed |
| [0107](0107-unimplemented-scenario-modules.md) | scenario plugin modules never implemented (tracked gap) | Proposed |
| [0108](0108-phase-de-and-e.md) | Phase D (CI gates) + Phase E (README + cleanup) closeout | Accepted |
| [0109](0109-plugin-metadata-mandate-and-budgetaware-removal.md) | Plugin 4-Element 声明为强契约 + BudgetAware 废弃 + BudgetPolicy 数据签名 | Accepted |
| [0110](0110-plugin-contract-unification-and-naming-convergence.md) | 插件合约统一化与命名收敛 —— 折叠 LogicAddress，让 PluginContract 真正成为插件侧唯一合约 | Proposed |
| [0111](0111-startup-compilation-as-subpackage.md) | 启动编译化为 `lca-kernel/` 顶层包（被 ADR-0115 修订） | Accepted |
| [0112](0112-gateway-routes-as-plugins.md) | Gateway 路由 Plugin 化（被 ADR-0115 修订） | Accepted |
| [0113](0113-boot-trace-first-class-citizen.md) | 启动 Trace 第一公民 + Sink Seam（被 ADR-0116 合并） | Superseded |
| [0114](0114-boot-event-catalog-increment.md) | 启动事件词表增量 5 个 boot 事件（被 ADR-0116 收敛） | Superseded |
| [0115](0115-kernel-transport-boundary.md) | Kernel / Transport 边界 + lint-imports 门禁 + 8 大职责 | Accepted |
| [0116](0116-boot-event-observability-convergence.md) | 启动事件词表与可观测性收敛（合并原 0113 + 0114） | Accepted |
| [0117](0117-process-lifecycle-env-whitelist.md) | Process 生命周期 + Fail-loud + Env 白名单（K6 + K7） | Accepted |
| [0118](0118-kernel-hmr-patch-watcher.md) | Kernel HMR —— cordis.patch.yml watcher + ReloadError + run_kernel 集成（K8） | Accepted |
| [0119](0119-webserver-as-plugin.md) | Webserver 完全 Plugin 化（对齐 deepseek-harness 范式，删除 `gateway/` 目录） | Proposed |
| [0102](0102-tool-render-contract.md) | Tool 渲染契约 — 集中 TS 生成（lcaToolRender） + 21 工具 registry | Accepted |
| [0103](0103-locked-surface-and-port-policy.md) | back-ui-821-other-keep 锁定表面 + 移植策略（hard/soft-lock + lane A/B/C） | Accepted |
| [0120](0120-retire-dsh-driver.md) | 退役 DSH (DeepSeek Harness) driver 集成路径 — `'dsh'` 执行目标闭集收敛 | Accepted |
| [0121](0121-attachment-fileref-and-plane-provider.md) | Attachment FileRef 与平面 Provider | Accepted |
| [0122](0122-plugin-native-debug-observability.md) | Plugin-native debug 与观测体系 | Accepted |
| [0156](0156-eliminate-projection-and-progress-leakage.md) | 消除投影与进度泄漏 | Accepted |
| [0157](0157-progress-stream-and-retire-toolcallstreaming.md) | Progress 流与退役 ToolCallStreaming | Accepted |
| [0158](0158-projection-isolation-and-finalizer-cleanup.md) | 投影隔离与 finalizer 清理 | Accepted |
| [0159](0159-phase-factsensor-and-tool-lifecycle-events.md) | Phase FactSensor 与工具生命周期事件 | Accepted |
| [0160](0160-llm-call-stream-finalize-on-exit.md) | LLM 调用流式 finalize-on-exit | Accepted |
| [0161](0161-step-advance-on-phase-retry.md) | Phase retry 时 step 推进 | Accepted |
| [0162](0162-fact-vs-progress-judgment-criterion.md) | 事实 vs 进度判别准则 | Accepted |
| [0163](0163-readiness-at-boot-not-on-request.md) | 就绪在 boot 而非请求时 | Accepted |
| [0164](0164-journal-step-tree.md) | Journal step-tree 取代 stream-envelope | Accepted |
| [0165](0165-event-spine-unified-log.md) | Event Spine 统一执行日志（stub；扩展见 0165-execution-point-enforcement） | Accepted |
| [0166](0166-step-segment-phase-and-spine-hardening.md) | Step / Segment / Phase 三层计数与 Spine 硬化 | Accepted |
| [0167](0167-spine-ssot-and-step-materialization.md) | Spine 唯一耐久真值、Step 物化视图与 Model-Visible 轨迹组织 | Accepted |
| [0168](0168-loop-step-control-and-model-visible.md) | Loop Step Control 与 Model-Visible 真实化（被 0168-final 收敛;保留问题陈述） | Superseded |
| [0168.1](0168.1-loop-cursor-state-machine.md) | LoopCursor — 单一 Loop 状态机收敛 step / segment / phase / iteration（被 0168-final 收敛;supersedes 0168 决策段） | Superseded |
| [0168-final](0168-loop-cursor-final.md) | LoopCursor — 单状态机收敛 Spine / Step / Segment / Phase / Iteration / Journal / Projection（supersedes 0168 + 0168.1 决策段） | Proposed |
| [0169](0169-loop-cursor-control.md) | LoopCursor 控制面收敛 — 五缝架构 + 与观测装配分离（gate-as-phase 由 0194 修订；supersedes 0168-final 全文） | Proposed |
| [0170](0170-projection-host.md) | ProjectionHost — Loop 维度可插拔投影宿主（ADR-0169 §D8 投影缝） | Proposed |
| [0171](0171-fork-shared-host.md) | fork 共享 Host 协议 — child cursor 不持独立 Host | Proposed |
| [0172](0172-observability-exporters.md) | Observability Exporters 实现层（metrics / OTel / Langfuse） | Proposed |
| [0173](0173-halt-resume-protocol.md) | halt-resume 协议 — LoopCursor 对外 rescue 路径 | Proposed |
| [0174](0174-profile-cursor-bundles.md) | Profile 分批装配 — `loop_cursor.spine_*` bundle 落地 | Proposed |
| [0175](0175-prompt-trace-into-model-visible.md) | Prompt trace 落 model_visible / spine EP payload 扩字段 | Accepted |
| [0176](0176-step-tree-deriver-closure-and-model-visible-dedup.md) | StepTreeAccumulator 闭环 + Model-Visible 去重重构 + Prompt Section 真值化 | Accepted |
| [0177](0177-envelope-emitter-binding.md) | EnvelopeEmitter binding — 收束 runtime/agent 对 spine reflector 的反向 import | Proposed |
| [0178](0178-observation-control-state-convergence.md) | 观测面 / 控制面 / 状态机三方收口 — 四级收敛与单 SSOT 体系 | Proposed |
| [0180](0180-event-mechanism-as-kernel-plugin.md) | 事件机制 — kernel 元层插件 + 鉴权矩阵 SSOT | Accepted |
| [0181](0181-spine-as-events-publishers-subscribers.md) | spine 降级为 publishers / sinks / subscribers（被 0183 吸收） | Superseded |
| [0182](0182-event-consumer-record-and-whitelist-convergence.md) | 消费入口收口 + 框架契约补齐（被 0183 吸收） | Superseded |
| [0183](0183-event-bus-framework-ssot.md) | 事件总线框架 — 可组合 / 可配置 / 可插拔 + 单 SSOT 落盘链 | Accepted |
| [0184](0184-event-lifecycle-managed-delivery.md) | 事件生命周期受管理投递 — 统一入口、阶段可查、丢失可定位 | Proposed |
| [0185](0185-model-visible-event-bus-alignment.md) | Model-Visible 走 ADR-0183 统一 event bus — plugin 化 producer + fold 重建 | Accepted |
| [0186](0186-session-as-event-ssot.md) | Session 为事件 SSOT — append + observer + fold（延伸 0183/0184；互补 0185） | Implemented |
| [0187](0187-assistant-agent.md) | AssistantAgent — 可配置、可隔离、可进化的个人助理产品面（Home SSOT + 同一 Resolve/Compile + 0093 jobs + G11 进化闸） | Accepted |
| [0188](0188-session-title-event.md) | Session 标题事件 — `session.title.v1` 入词表（log-only 审计档，标题模块唯一事实载体） | Proposed |
| [0189](0189-session-obs-dsh-parity-events.md) | Session 观察面 DSH 对齐 — 信封扩展与 fork/derive/feedback 词表 | Proposed |
| [0190](0190-extreme-plugin-organization.md) | LCA 极端插件化组织规范（文件名已正名为 `0190-`；文档自标 0189，见下方注） | Keep |
| [0191](0191-runtime-loop-dsh-convergence-and-control-plane.md) | Runtime Loop DSH 收敛与 LCA 控制面保留 — 事实/模型/控制/Ephemeral 四态分离 + Reducer 演进 | Implemented |
| [0192](0192-fact-plane-convergence.md) | Fact Plane 收敛 — FactCommitter + PhaseFactEmitter；Journal 平面从 cognition 退役 | Implemented（via 0186/0194/0195） |
| [0193](0193-session-projection-fabric-model-visible.md) | Session Projection Fabric — ModelVisibleUnit 增量投影；统一 model-visible 读面 | Implemented (D1–D7) |
| [0194](0194-cognitive-loop-architecture-convergence.md) | 认知 Loop 架构收敛 — 图内核 / FactGateway 单轨 / 六 phase 正名 / 极端插件化目录 | Implemented (P0–P5 core) |
| [0195](0195-platform-architecture-convergence.md) | 全栈平台架构收敛 — Kernel · Transport · Observability 四段链 · 插件 seam 树 · SSOT 矩阵 | Implemented (P0–P5 core) |
| [0196](0196-convergence-control-plane-and-prompt-surface.md) | Convergence 控制面与 PromptSurface — 交付谓词、调试事件、工具/Prompt SSOT | Implemented (P1–P3) |
| [0201](0201-tool-result-prompt-closure.md) | Model-Visible Tool Result 写面闭环 — 补全 ADR-0193 surface append + FC message 投影 | Implemented |
| [0197](0197-guard-stack-hermes-dsh-convergence.md) | Guard Stack — Hermes 分层收敛 + DSH guard 插件化融合 | Implemented (P1–P2) |
| [0198](0198-observability-compile-graph.md) | Observability Compile Graph — yaml SSOT、ObservabilityCompiler、fold merge | Accepted (P0) |
| [0199](0199-hermes-inspired-cognitive-plugin-convergence.md) | Hermes 启发的认知插件架构收敛 — RuntimeFacade、Plugin Doctor、分域 Registry、privilege 分离 | Proposed (P0 done; P1 approved) |
| [0200](0200-hermes-product-capabilities-absorption.md) | Hermes 产品能力吸收 — review-fork、Curator、ContextEngine、MemoryProvider、no_agent Routine | Proposed |
| [0200](0200-p1-agent-gateway-bridge.md) | P1 Agent Gateway Bridge — WebSocket + Redis Stream 收敛(native LobeHub AgentGateway 协议) | Accepted (PR-1) |
| [0202](0202-transport-ui-env-ssot.md) | Transport/UI env 配置 SSOT — Profile `{from_env: ...}` seam 收口, 退役 os.environ 直读 | Proposed |
| [0203](0203-end-to-end-field-contract.md) | 端到端字段契约: effect_kind 枚举 + canonical_digest 单一助手 | Proposed |
| [0204](0204-surface-render-slot-plan-strategy.md) | SurfaceRender — 模型可见消息的 typed Contract 收口 (2026-09-08 重写; ADR-0195 §1.4 C13 信息血统 + §1.5 V2/V4/V5 应用域; OpenAI*Message Pydantic frozen + ModelVisibleUnit.view() 闭合校验 + Manifest `capability.contract.provides` 沿用 ADR-0110; 同 PR 零中间态删 if/elif/平铺字段) | Accepted — Rewritten |
| [0205](0205-wire-contract-as-plugin-seam.md) | WireContract 元机制 — **2026-09-08 撤回**; 已并入 [ADR-0195 §1.4 / §1.5](0195-platform-architecture-convergence.md) + [ADR-0204](0204-surface-render-slot-plan-strategy.md) 重写版; 历史文件保留追溯 | Deprecated — Superseded |
| [0206](0206-information-graph-kernel.md) | 可编译信息图认知内核 — 单一可执行图种 InfoEdgeSpec + 嵌套子图驱动六个阶段 / 模型可见 / 效应 / 溯源；C1–C14 不变式（含 C11 单图种 / C12 子图端口 / C13 嵌套点火 / C14 阶段退化为 region）；§5.7 八项生效证明 E1–E8 + §8.1 不可替代边界 + §9.1 MVP 金丝雀验收；§10 P7 阶段闭集迁移承担 0075/0194 部分吸收（吸收 0207） | Proposed |
| [0207](0207-graph-orchestrated-cognitive-agent-kernel.md) | 图编排式认知 Agent 内核 — 多图协作与编译期信息契约（已并入 0206） | Superseded |
| [0209](0209-agent-lab-cordis-unification.md) | agent_lab 全量收编进 LCA plugin 体系 — 唯一插件入口 `@plugin` + 单 `lca.plugins.lab.internal.loader` 闭包 + Body/ToolRegistry/Transport/Session 四个 provider 拆分 + Session 单轨 + `agent_lab/adapters/` 与 `tools/registry.{py,yaml}` 删除；PR-A.3 → PR-D final 1/2 已合并（46 tests passed, 5 skipped）；PR-D final 2/2 节点真实 @plugin carrier 重写依赖 cordis LCA runtime（当前测试环境不可达）；与 Note `2026-09-08-agent-lab-absorb-end-state` §delete-when + Note `2026-09-09-lab-cordis-unification-landing.md` delete-when 共同锁定。**暂时停止** — PR-D final 2/2 暂停，等待 cordis LCA runtime 可用后继续 | Proposed — PR-D final 1/2 done; 2/2 paused |
| [0210](0210-stage-closure-migration-p7.md) | 阶段闭集迁移（P7 实施切片）— 0075 `CognitivePhaseGraphPlan` 阶段 SSOT + 0194 Loop 闭集强制部分降级为 `region = phase:<name>` 标签机制（0075/0194 标 Superseded by 0210 partial）；region 不绑定 capability 闭集（违反 ADR-0209 §1.5 / AGENTS.md C5）；profile 可声明扩展 region（如 `phase:plan` / `phase:replan`）；PR-D final 2/2 generator 已生成 89 个 carrier 全部带 `region` 字段；0206 升 Accepted 条件 = 0210 升 Accepted | Proposed |
| [0211](0211-worker-contract-tightening.md) | Worker Contract 收紧 — execute 签名契约（keyword-only / typed 入出 / 无框架容器）+ Config 收紧（不放端口名 / 不放框架句柄 / 只放静态值 + on_error 框架字段）+ 错误三态（Success / Skip / Raise,框架按 Config.on_error 处理）+ 退役契约（`register_worker` / `Seams` / `body_provider.get_body` 三件同 PR 删）+ framework 投影层 `cordis_bridge`（按 Worker.execute 签名自动从 ctx 取 typed values,fail-loud）+ lint-imports `lab-worker-purity` 规则；Refines ADR-0209 §1.2 / §1.3 / §1.6；0209 升 Accepted 条件 = 0211 §9 delete-when 全 6 条满足 | Proposed |
| [0212](0212-step-tree-deriver-ssot-cleanup.md) | step_tree 派生面 SSOT 单写收口 — 删 `StepTreeAccumulatorDeriver` 整文件 + ADR-0195 O7 re-export shim + 删 stale test；`StepTreeFoldDeriver.derive()` 写盘失败从 `log.warning + swallow` 升级为 typed exception `JournalWriteError`（fail-loud）；回归 run_f78f66322f1d 的 doctor H3 重复 step_id；C9 幂等 + C11 事实可追溯 失败端收口 | Proposed |
| [0213](0213-kernel-serve-spawn-result-and-health-readiness.md) | KernelServe spawn 结果结构化 + /health plugin readiness 字段 — `KernelServeSpawner` 5 原子 step（preflight/start/port_bound/http_ready/plugin_ready）+ stderr 每 spawn 独立落盘 + timeout 永不为 True + `kernel-restart` 子命令拆出 `stack.heal` + `/health` body 新增 `plugin` 字段；配套 Note [`2026-09-09-kernel-serve-spawn-state-machine`](../../notes/implemented/seam/2026-09-09-kernel-serve-spawn-state-machine.md)；落地分 PR-1/2/3 | Implemented (PR-1/2/3) |
| [0221](0221-concept-decision-classify-parse-merge.md) | concept.decision.classify — parse 节点合并,消解 fan-out 隐式假设；3 节点图(`parse.tool_calls` / `parse.intent` / `compose.action`)→ 2 节点图(`parse.response` / `compose.action`)；同 LLMResponse 同步输出 `tool_calls` / `delegations` / `intent` 三端口；Refines ADR-0220 §3.3 / §11 P6；0220 升 Accepted 时由 meta-ADR 同步 amend | Proposed |

> 同名 `0165` 系列有两份(stub + 执行点强制):[0165-event-spine-unified-log.md](0165-event-spine-unified-log.md) 与 [0165-execution-point-enforcement.md](0165-execution-point-enforcement.md)(原 0165.1)。SSOT / 轨迹文件组织以 [0167](0167-spine-ssot-and-step-materialization.md) 为准。

> 点号后缀 ADR([0167.1](0167.1-step-tree-deriver-wiring-and-run-layout-cleanup.md)、[0168.1](0168.1-loop-cursor-state-machine.md))是父 ADR 的收尾件,索引按主编号 `0167` / `0168` 归属,不单独占号。
>
> [0190-extreme-plugin-organization.md](0190-extreme-plugin-organization.md) 文件名已正名为 `0190-` 前缀(原 `adr-0190-` 不符合编号规范);文档内自标 ADR-0189(写作时 0187=AssistantAgent 已占号),而 0189 另有 [0189-session-obs-dsh-parity-events.md](0189-session-obs-dsh-parity-events.md)。ADR-0200 引用时用 "0189" 标签;差异记录见 [0200-phase0-cross-reference-verification.md](../specs/0200-phase0-cross-reference-verification.md) §3.2。

## 维护规则
- 不改旧文件；新决策用 `Supersedes: ADR-XXXX` 标记
- CI `tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 守护本表与 `docs/adr/*.md` 编号一致
