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
| [0094](0094-stop-policy-locality.md) | StopPolicy 的 State 群局部性 | Superseded |
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
| [0208](0208-model-visible-spine-ep-whitelist.md) | Model-Visible Spine EP 白名单收口 — 四 SSOT 一致 + 字节布局 fail-loud | Implemented |
| [0210](0210-stage-closure-migration-p7.md) | 阶段闭集迁移（P7 实施切片）— 0075 `CognitivePhaseGraphPlan` 阶段 SSOT + 0194 Loop 闭集强制部分降级为 `region = phase:<name>` 标签机制（0075/0194 标 Superseded by 0210 partial）；region 不绑定 capability 闭集（违反 AGENTS.md C5）；profile 可声明扩展 region（如 `phase:plan` / `phase:replan`）；0206 升 Accepted 条件 = 0210 升 Accepted | Accepted (PR-7 closed: dual lineage bundles retired) |
| [0212](0212-step-tree-deriver-ssot-cleanup.md) | step_tree 派生面 SSOT 单写收口 — 删 `StepTreeAccumulatorDeriver` 整文件 + ADR-0195 O7 re-export shim + 删 stale test；`StepTreeFoldDeriver.derive()` 写盘失败从 `log.warning + swallow` 升级为 typed exception `JournalWriteError`（fail-loud）；回归 run_f78f66322f1d 的 doctor H3 重复 step_id；C9 幂等 + C11 事实可追溯 失败端收口 | Proposed |
| [0213](0213-kernel-serve-spawn-result-and-health-readiness.md) | KernelServe spawn 结果结构化 + /health plugin readiness 字段 — `KernelServeSpawner` 5 原子 step（preflight/start/port_bound/http_ready/plugin_ready）+ stderr 每 spawn 独立落盘 + timeout 永不为 True + `kernel-restart` 子命令拆出 `stack.heal` + `/health` body 新增 `plugin` 字段；配套 Note [`2026-09-09-kernel-serve-spawn-state-machine`](../../notes/implemented/seam/2026-09-09-kernel-serve-spawn-state-machine.md)；落地分 PR-1/2/3 | Implemented (PR-1/2/3) |
| [0214](0214-task-progress-and-active-convergence.md) | TaskProgress Projection + Multi-Tool Loop Breaker + PG-007 三件套 | Proposed |
| [0217](0217-bundle-graph-schema-v2.md) | Bundle Graph Schema v2 — 纯图描述 + factory→plugin 解析 | Accepted |
| [0218](0218-bundle-graph-v2-subgraph-driver.md) | Bundle Graph v2 subgraph driver — interpreter v2 友好分支 | Accepted |
| [0219](0219-phase-graph-unification.md) | phase-graph 一体化收敛 — interpreter × subgraph driver × phase context × port registry 单一职责回归 | Proposed |
| [0220](0220-three-tier-graph-and-boundary-typing.md) | 三层图概念群与 boundary typed DTO — `PromptReasoner` 减肥，`AgentState` 不持 ref，图与图用 boundary 互通 | Proposed |
| [0222](0222-retire-v1-reasoner-sandbox.md) | Retire graph v1 leftovers；PromptReasoner SRP；sandbox fork fail-loud | Accepted |
| [0225](0225-drop-max-visits-graph-invariant.md) | Drop `max_visits` graph-topology invariant | Implemented |
| [0226](0226-session-write-path-collapse.md) | Session write-path collapse + persist-before-execute | Implemented |
| [0221](0221-concept-decision-classify-parse-merge.md) | concept.decision.classify — parse 节点合并,消解 fan-out 隐式假设；3 节点图(`parse.tool_calls` / `parse.intent` / `compose.action`)→ 2 节点图(`parse.response` / `compose.action`)；同 LLMResponse 同步输出 `tool_calls` / `delegations` / `intent` 三端口；Refines ADR-0220 §3.3 / §11 P6；0220 升 Accepted 时由 meta-ADR 同步 amend | Proposed |
| [0227](0227-graph-node-dsl.md) | `@graph_node` DSL — typed-boundary decorator for phase helpers；将 `NodeExecutor` dataclass + `@plugin(...)` setup pair 折成单一 `@graph_node(...)` 装饰器调用；落地后由 ADR-0228 退役（decorator 产出 cordis carrier 的 `setup.setup` 嵌套结构不被 bundle resolver 识别，runtime 永远看不到 `@graph_node` 节点，3 个 PR3 think 节点已回退为手写 `@plugin(...)` 模式） | Superseded by 0228 |
| [0228](0228-plan-intervene-delegate-subgraphs.md) | plan / intervene / delegate 子图 + `@graph_node` 退役 — 三个新 region 子图(`plan.compose`/`plan.revise`、`intervene.interrupt`/`intervene.resume`、`delegate.compose`/`delegate.await`/`delegate.fold`)落地 typed-port 契约；`@graph_node` 装饰器删除；手写 `@plugin(...)` carrier 模式确立为唯一正典形态；6 phase 闭集保持不变；落地分 PR-3.7.a/b/c | Accepted (PR-3.7.a landed: decorator + tests deleted, docstrings rewritten) |
| [0230](0230-stop-decision-retirement.md) | Stop-Decision Retirement — 删 `StopPolicy` Protocol + `DefaultStopPolicy` + 8 stop 插件 + 3 stop bundle；`StopDecision` 去 `should_stop`；`StopPayload` 去 `should_stop` + `focus_converged`；外层 plan 用 `terminal.commit` 取代 `stop.main`（绑定 `BindingKind.TERMINATE`）；loop 终止由模型 `decision.action_type == "respond"` 与 Body `EffectReceipt.failure_kind == "execution"` 共同驱动；新增 `spine.terminal.commit` (OBSERVABILITY) + `spine.body.deterministic_fail` (STRUCTURAL) EP；Supersedes ADR-0094 的 StopPolicy 局部性结论 | Implemented |
| [0231](0231-region-prefix-ssot-and-node-directory-canonicalization.md) | Region prefix SSOT = `lca/nodes/<region>/` 目录名（无冒号） | Accepted |
| [0232](0232-act-fanout-n-to-n-and-parallel-tool-batch.md) | `act.fanout` N:N + `ToolBatchExecutionMode.PARALLEL` Default for Read-Only Tools | Accepted |
| [0233](0233-c11-escape-hatch-policy.md) | C11 escape-hatch policy：spine.* raise-loud，non-spine carve-out with delete-when | Accepted |
| [0234](0234-effect-pre-dispatch-envelope-check.md) | Effect Pre-Dispatch Envelope Check — PipelineSafeExecutor 5 闸外提到 typed-port graph 节点 `effect.pre_dispatch.envelope_check`;SE 退化为薄壳;删除 5 个本地 `executor.*` verdict_refs(G-7);同 PR 落地(PR-2 of act-subgraph-tightening plan) | Accepted |
| [0235](0235-act-envelope-typed-port-hygiene.md) | act.envelope C13 卫生 — `state` / `decision` 反抽到 typed port(`act.envelope` inputs 增加 `state`;`effect.execute` inputs 扩展到 `[envelope, decision, state]`;`EffectDispatcher.execute` Protocol 签名增加 `*, state=None, decision=None` typed keyword-only);metadata 仅保留 op-relative 字段(C2 双平面);`_existing_effect_receipt` / `_validated_effect_class` metadata 偷读删除;`PipelineSafeExecutor` plan_ref / scope_ref 收口为构造时注入 typed provider;`act.observe.commit_fact` 改 typed kernel capability 注入(R-3 follow-through);`Decision.needs_approval` typed 字段 + `act.approve.gate` 删 `_resolve_port` 偷图(L-2 / G-9 follow-through);同 PR 落地(PR-5 of act-subgraph-tightening plan) | Accepted |
| [0236](0236-dual-lineage-retirement.md) | Dual Lineage Retirement（删 `agent.run.phase` + `declarative-phase-graph` + `declarative-recovery`） | Accepted |
| [0237](0237-subgraph-output-bubble-outer-edge-exclusivity.md) | act 子图输出冒泡 + outer 边互斥（`gate.routing` 单消费者） | Accepted |
| [0240](0240-node-emit-dispatch-whitelist-additions.md) | Node-level emit dispatch whitelist additions — BundleGraphSpec v2 `emit_on_enter` / `emit_on_exit` 接通 driver:10 个 EP 名(`terminal.commit` / `phase.*.fold` / `think.gate.end` / `phase_graph.subgraph.{enter,exit}`) 落入 `_EP_DISPATCH` 表 + `emit_*_for_state` helpers;validator 路径偏移 bug 修复;`NodeEventEmissionCheck` 重启;C11 closed-set 落地(`SPINE_EXECUTION_POINTS` + `_SPINE_EP_TO_CATEGORY` + `spine.yaml` 均已预注册);同 PR 配套 Note [`2026-09-15-node-emit-dispatcher-wiring`](../../notes/implemented/seam/2026-09-15-node-emit-dispatcher-wiring.md) | Implemented |
| [0241](0241-tool-fork-typed-port-projection.md) | `tool.fork.dispatch` typed-port 投影 — plan-side 闭集闭合与 framework 投影语义统一（`translate_inputs` 按名字投影 + ToolsService/BindingsView 作 outer-plan typed port） | Accepted |
| [0242](0242-assistant-creation-home-runtime.md) | Assistant 创建向导、Home 驱动运行与自我管理 — 对话内向导（大类→小类→SOUL 对齐→取名）、run 期人设/工具/技能从 Home 装配、助理级记忆与工作区持久化、per-agent 图/流程/prompt 覆盖与实验隔离、自我管理工具族 | Proposed |
| [0243](0243-assistant-skill-tool-isolation-config.md) | 助理技能/工具隔离与可配置化 — 技能硬链接 + 写时复制物化到 Home、`{home}/tools/` 自定义工具目录、运行时只从 Home 加载、自我管理工具族扩展（edit skill / create|update|delete tool） | Proposed |
| [0244](0244-cognitive-memory-closed-loop-and-sandbox-convergence.md) | 认知记忆闭环、上下文会话流与执行沙箱根治 — Token 预算感知会话切片 + Session 单轨注入、主外层图打通 reflect/remember 及零成本准入门禁、通用技能自描述与程序性记忆自适应沉淀、沙箱系统级 CJK 字体基线与工作空间分层、JournalStep 复数化与精准集合对账 | Accepted |
| [0245](0245-hermes-self-evolution-and-skill-auto-generation.md) | Hermes 自我进化机制与 Skill 自动生成调研 — `memory` + `skill_manage` 工具协议、self_evolution 实验模块、基因匹配进化引擎，为程序性记忆沉淀提供参考实现蓝图 | Research |
| [0246](0246-user-machine-side-effect-plane.md) | 用户机器副作用平面 — 业界范式多方案（Companion/浏览器受限/隧道/托管执行机/MDM）+ LCA Computer/HIL/Gateway 挂缝；不定死网页弹 PowerShell | Implemented |
| [0247](0247-agent-memory-knowledge-layer.md) | Agent 记忆知识层 — 从关键词原文存档升级为结构化知识：LLM 蒸馏提取、typed MemoryRecord、受治理记忆工具、用户画像回填、预算内相关性检索、supersede/遗忘生命周期，修通 assistant.bootstrap 死代码并清理 workspace_instructions 污染与硬编码关键词机制 | Accepted |
| [0248](0248-grok-bot-coordinator-runtime-evidence.md) | 协调型桌面 Agent 运行时 — 证据级解剖（可模范实现） | Implemented |
| [0249](0249-cadence-inspired-dual-track-memory-consolidation.md) | 基于 Cadence 生物范式的昼夜双轨记忆固化架构 — 毫秒级残差门控快记（Fast Path）+ 离线做梦固化慢变（Night Consolidation）+ 有界切片（Patch）+ DDD 聚合根与受治理 C10 窄门回填 | Accepted |
| [0250](0250-peer-assistants-handoff-bus-and-rooms.md) | Peer Assistants Handoff Bus and Rooms | Implemented |
| [0251](0251-openmuse-runtime-sandbox-durable-task-evidence.md) | OpenMuse 架构解剖与借鉴 — 长程租约任务、防漂移双门禁与可接管沙箱证据 | Proposed |
| [0252](0252-multi-user-onboarding-and-identity.md) | 多用户登录与 Onboarding 隔离 — LCA 自有数据库 + LobeHub 原生前端（归属关系 LCA 全权控制，身份 SSOT = Better Auth users） | Implemented |
| [0253](0253-muse-sentinel-egress-and-credential-boundary.md) | Meta Muse 出站控制面、凭证边界与污点审批 — 沙箱无默认路由、独立进程按 request_digest 兑付密钥、私有数据取消自动放行、审批事件与对话正文隔离 | Proposed |
| [0254](0254-commercial-context-files-and-continuous-memory-runtime.md) | 上下文文件与持续记忆。2026-10-02 v2 修订：记忆 SSOT 二选一选 A（Markdown 为准；0247 的 MemoryRecord 领域语义继续继承，bank/index 降为可重建派生索引）。已落地：MEMORY.md 投影、常驻文件按磁盘重读、写盘回执先于「已记下」、人物/群体页、TOOLS.md、实时监听与 WATCHER_FAULT、Side Chat 隔离与私人内容过滤、FTS 检索、做梦慢路径（显式偏好固化、亲近度、偏好综述） | Accepted |
| [0256](0256-tool-namespace-taxonomy.md) | 工具命名空间划分规范：8 域划分、namespace 声明式元数据下沉 factory、defer 加载/审批/wire gate 三者同粒度，附 6 处代码改动与 8 条验收标准；ADR-0255 L1 defer 的划分规范。2026-10-02 修订：fail-fast→fail-soft（硬 fail-fast 收敛到 wiring time，见 §11）；2026-10-02 状态升级 Accepted | Accepted |
| [0257](0257-delegation-context-inheritance-and-verification.md) | 委派上下文继承与复核协议：委派信封（standing 全量+父 turn 摘要+记忆投影）、回灌只收 evidence 指针、不可逆失败先验效果；ADR-0255 §4.6 的 LCA 落地提案 | Proposed |
| [0258](0258-compaction-exemption-and-reinjection.md) | 压缩豁免与重注契约：standing 永不进压缩流、摘要带  血统、刷新读失败保留旧块 fail-closed；ADR-0255 §4.5 的 LCA 落地提案 | Proposed |
| [0259](0259-timestamp-trust-and-date-derivation.md) | 时间戳信任与日期推导契约：now 唯一来源升不变量、日期推导必须经可信工具验证、事件/记录/检索三时间分离；ADR-0255 §4.7 的 LCA 落地提案 | Proposed |
| [0260](0260-forced-retrieval-and-write-before-claim.md) | 强制检索与写盘铁律契约：写盘确认门（acknowledgement.py）升不变量、检索义务决策树升契约+补 home-bound 渲染盲区、当场写/先读后写/冲突原地修正/凭证红线四纪律；ADR-0255 §4.2/§4.3 的 LCA 落地提案 | Proposed |
| [0261](0261-self-introspection-projection.md) | 自省投影契约：自省答案只许来自本 turn 注入块（禁用工作区文件搜寻）、点名配置文件必须真实注入（BackstorySection 守卫升不变量并推广）、新增只读自省工具与写工具配对；ADR-0255 §4.8 的 LCA 落地提案 | Proposed |
| [0262](0262-skill-discovery-and-acquisition.md) | Skill 发现与沉淀契约：先查后动手（提示级义务）、先查后断言（检索失败≠检索无结果）、沉淀晋升三段门（candidate→批准→安装）、补 BM25/regex 双模式；ADR-0255 §4.9 的 LCA 落地提案 | Proposed |
| [0263](0263-routine-scheduling-mutual-exclusion-and-self-healing.md) | 例程调度互斥与自愈契约：单实例互斥锁（owner+心跳）、锁超时自愈收割、busy→显式 SKIP 可观测、触发记录持久化、失败隔离；生产 Muse 调度模式的 LCA 落地提案 | Accepted |
| [0264](0264-proactive-messaging-pipeline.md) | 主动消息三层管道契约：触发/裁决/投递三层分离、裁决纯函数四态（REJECTED/DELIVER_CHAT/DELIVER_QUIET/SILENT）、fail-closed 只用在精确可判定处、投递复用 surface 事件+turn=-1 哨兵+幂等键、落点默认回发起上下文；生产 Muse 主动行为机制的 LCA 落地提案 | Proposed |
| [0265](0265-system-prompt-assembly-order.md) | 系统提示装配顺序契约：stable→volatile 带序约束（宪法层→时间锚点→用户 live 配置→能力面→运行上下文→行为规则）、profile 扩展只许带内增删、义务段不得可选；ADR-0255 §1.1 的 LCA 落地提案 | Proposed |
| [0266](0266-standing-write-matrix-and-update-mechanics.md) | Standing 文件写权限矩阵与更新机制契约：谁可以改 standing 文件、在线写 read-before-write、离线写冲突消解（字段级合并/真冲突 fail-closed）、读取新鲜度语义（三层）；ADR-0255 §2.11/§2.12 的 LCA 落地提案 | Proposed |
| [0267](0267-agent-behavior-three-mechanisms.md) | Agent 行为三机制补齐：工具失败降为数据不杀死 run、记忆按用户画像加权呈现、推理不复述规则条文 | Proposed |
| [0268](0268-context-bus-async-executors-and-cron-projection.md) | 上下文总线、四类异步执行体与 cron 即将到来投影：lca.nothing_to_do 与 cron 域分离、含一次性的 CronJob、服务端 next_run（列表只给时间字符串）、间隔从创建时间起相位、handoff 后由父决定说不说、重叠时只留最新排队项、run 回执必写 | Proposed |
| [0269](0269-assistant-avatar-system.md) | 助理头像生成系统：独立 avatar 插件、身份感知生图（用户原话+identity traits）、create/edit/set 三态候选池（生成与激活解耦、24h TTL）、多尺寸+异步视频变体、cron 定时换装（SpaceActionExecution artifact_id=avatar + 轻量调度器）、Redis pub/sub WS 推送通道 | Proposed |
| [0270](0270-task-intake-gate.md) | 任务受理门契约：首 turn 必答 7 问（run 时精简版）、触及改契约/闭集/SSOT 时 fail-closed 停出方案、受理答案落 journal evidence；ADR-0255 §0 的 LCA 落地提案 | Proposed |
| [0271](0271-avatar-system-alignment-and-supplement.md) | Avatar 头像系统对齐与补遗：与 ADR-0269 的重叠清单、三处实质冲突（IDENTITY.md 写入路径/avatar 第九域/视频异步类型归属）、新增并发守卫/候选上限/隐私补强/第一人称话术 | Proposed |
| [0272](0272-realtime-info-routing-iron-rule.md) | 实时信息路由铁律契约：查询 vs 核验路由二分、search 结果证据纪律（肯定弱化/否定纪律）、真机任务书三要素、账号内数据走 skill 优先；ADR-0255 §3.3 的 LCA 落地提案 | Proposed |
| [0273](0273-streaming-interleave-think-act.md) | 流式交错契约：think 流式产出期间 act 侧做无副作用预准备（参数校验/审批预判/连接预热），交错点在 emit seam、不改六 phase 拓扑；hint 不是承诺、正式 dispatch 仍完整 fail-closed | Proposed |
| [0274](0274-phase-wire-budget.md) | Phase Wire 预算契约：phase 级 token 预算配置层声明、装配后 wire 投射前强制执行；超预算时 perceive 按传感器优先级裁剪、think 触发工具域 defer；ADR-0256 预算思想的 phase 级推广 | Proposed |
| [0275](0275-window-pressure-phase-degradation.md) | 窗口压力 phase 降级契约：WindowPressure 信号 SSOT（phase 只读不写）、降级策略声明式进配置、落点为 control 贡献契约新 slot；reflect 高压力降级快速路径、remember 批量异步；与 0258 记忆层压缩正交 | Proposed |
| [0276](0276-acceptance-evidence-mapping.md) | 0255 §6 验收映射与证据诚实契约：T1–T12 的 owner/锚点/证据等级（L1/L2/L3）映射表 SSOT、缺席不许静默（实锤 T7/T11 缺席）、套件名实相符；ADR-0255 §6 的 LCA 落地提案 | Proposed |
| [0277](0277-cognitive-memory-reconstruction.md) | 记忆机制的认知重构：typed 记忆对象（EpisodicTrace/SemanticClaim/ProceduralRule）+ perceive 传感器注册表 + remember 四决策 consolidation（encode/link/decay/schema）；吸取 Letta（sleep-time）、Zep（双时间线）、Mem0（reconcile）、ACT-R（激活度评分）、Soar（四记忆独立学习）；对齐人类记忆模型（Tulving/遗忘曲线/编码深度/系统巩固） | Proposed |
| [0278](0278-scheduler-mutual-exclusion-convergence.md) | 双调度器互斥与自愈契约收敛：routine scheduler（0263）与 cron daemon（0268 深化）独立实现同一文件锁互斥语义（owner=hostname:pid、stale=2×interval/上限90min）；missed-run 补偿 vs 重试+死信的失败语义分岔待裁决 | Proposed |
| [0279](0279-intent-tool-reconciliation-and-jit-hydration.md) | 意图-工具结构对账与 JIT 动态装配契约：结构差集检测思考链意图工具引用与当轮 tool_calls 鸿沟、动态展开 deferred schema 并回环重调；告别动词表启发式与假声称 | Proposed |
| [0280](0280-zero-model-exposure-for-capable-urls.md) | 携带能力特权 URL 的零大模型暴露与带外意图兑换：工具层特权 URL 进 Vault、仅向大模型暴露 intent_id、卡片挂载跟随 tool result 经 tool surface registry（v2）、前端带外异步兑换与居中弹窗 | Implemented（v2 修正案 Accepted 待实施） |
| [0281](0281-run-artifact-filesystem-permissions.md) | Run 产物文件系统权限契约：traces/runs/<run_id>/ 目录 0700 / 产出文件 0600 owner-only 持有、ensure_run_dir 收紧语义、新增 writer 三件套纪律 | Proposed |
| [0282](0282-blocked-tool-call-journal.md) | 被拒 tool call 入 journal 契约：UseToolOperation 派发前三闸门拒绝必须先留 step.tool_call.record(status=wire_blocked)+step.tool_result.record(ok=False) 事实，deriver 由判 ok 转判 degraded | Proposed |
| [0283](0283-compaction-completion.md) | compaction 机制补齐：sediment-before-compact（压缩前事实先沉淀，sediment 失败 fail-closed 降级 truncate，绝不带病摘要）+ 结构化摘要 CompactSummary（decisions/commitments/entity_states/open_questions/dropped，关键事实 100% 保留验收）+ 语义回溯 recall_compacted（后续）+ Phase 降级 PressurePolicy（后续） | Proposed |
| [0284](0284-three-tier-standing-budget-injection.md) | Standing 三层预算注入契约：Tier-1 platform 整段注入、预算外、零截断（~/.lca 解析，缺失静默跳过）；Tier-2 protected 整节装包自有预算（丢节告警、LCA_STRICT_STANDING=1 抛错）；Tier-3 projection 剩余预算整节装包；字符级截断禁令；home override 走 sanitize 不拒绝 | Accepted/Implemented |
| [0285](0285-tool-bracket-event-outcome.md) | 工具调用结局单一所有权与括号事件收口：第一原理「每次尝试的结局必须可判定且记录不得与权威结局矛盾」推导出结局真值唯一在 step.tool_result.record；节点级括号事件不得携带结局字段（D 先行），冗余括号事件从 act yaml 移除（E 收口），footer 计数改读 step.tool_call.record，wrapper="decision" 钉为区分键 | Accepted/Implemented |
| [0286](0286-n9-node-id-family-namespace-adjudication.md) | N9 节点命名闭集的家族命名空间裁决（todo-44）：primitive.* 接受为 ADR-0220 自有层家族命名空间合法例外（concept 零节点 id 使用，不加）；history.derive 是 wiring 级命名债，维持红钉不洗绿，改名归 quality lane/李超；不改 0220 正文 | Accepted |
| [0287](0287-semantic-memory-single-online-writer.md) | 语义记忆在线单写者与离线对账归位（李超 note 转 ADR 提案）：F1 认领权跨轮泄漏=0260 C1 fail-open 缺口、F2 对账三套实现在线跑临时版、F4 TrailWriter 零生产写入方；D1 在线单写者（工具路径）、D2 认领权改 run_id 派生读（0260 裁决硬前置）、D3 对账收敛四操作闸（0277 ⑥/⑦ 裁决硬前置）、D5 四阶段交付门禁、D6 落盘时延待产品接受 | Proposed |
| [0288](0288-nextrun-cross-slot-due-amendment.md) | ADR-0268 修正案：next_run 跨越式 due 语义（微秒相等判据→越过即 due、档归属防重、只补最近一档；tests lane 已钉住 5 个 xfail 契约测试，待 quality 语义修） | Proposed |
| [0289](0289-bundle-wiring-region-qualified-executor-identity.md) | Bundle 接线执行体身份：region-qualified 复合键+歧义裸名 fail-loud（D4 batch-2 think/primitive 同名双 executor 误接线事故复盘；与 0256 接线时 fail-fast 同哲学） | Implemented |
| [0290](0290-naming-violations-arbitration.md) | 三违规类名仲裁：DesktopLockManager→DesktopLockCoordinator、ReclaimInfo→ReclaimTrace 改名（quality lane）；SpineHandler 豁免（宪法 §4.1 Handler 合法后缀，豁免归档在本 ADR，tests lane 登记 _NAME_EXEMPT） | Accepted |
| [0291](0291-code-conventions-fitness-reactivation.md) | 代码规范健身函数空心化修复与激活策略（todo-56）：_PROJECT_ROOT 指针漂移致四测试恒绿/恒 skip；Phase A–D 分阶段还债+逐个点亮；C1–C4 非空心元规则（基数门/指针自检/豁免铁律/glossary SSOT）；Phase C 三选一待拍板 | Proposed |
| [0255](0255-muse-production-runtime-full-reference.md) | Muse 生产运行时全量参考：每 turn 上下文装配顺序、9 个 standing 文件全文与权限矩阵、36 工具命名空间函数清单与关键参数、9 大机制（记忆三层/强制检索/落笔写盘/provenance/压缩豁免/子 agent 继承/自省投影）与 12 条验收用例；ADR-0254 的实证 companion | Proposed |

> 同名 `0165` 系列有两份(stub + 执行点强制):[0165-event-spine-unified-log.md](0165-event-spine-unified-log.md) 与 [0165-execution-point-enforcement.md](0165-execution-point-enforcement.md)(原 0165.1)。SSOT / 轨迹文件组织以 [0167](0167-spine-ssot-and-step-materialization.md) 为准。

> 点号后缀 ADR([0167.1](0167.1-step-tree-deriver-wiring-and-run-layout-cleanup.md)、[0168.1](0168.1-loop-cursor-state-machine.md))是父 ADR 的收尾件,索引按主编号 `0167` / `0168` 归属,不单独占号。
>
> [0190-extreme-plugin-organization.md](0190-extreme-plugin-organization.md) 文件名已正名为 `0190-` 前缀(原 `adr-0190-` 不符合编号规范);文档内自标 ADR-0189(写作时 0187=AssistantAgent 已占号),而 0189 另有 [0189-session-obs-dsh-parity-events.md](0189-session-obs-dsh-parity-events.md)。ADR-0200 引用时用 "0189" 标签;差异记录见 [0200-phase0-cross-reference-verification.md](../specs/0200-phase0-cross-reference-verification.md) §3.2。

## 维护规则
- 不改旧文件；新决策用 `Supersedes: ADR-XXXX` 标记
- CI `tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 守护本表与 `docs/adr/*.md` 编号一致

- [ADR-0248 Grok Bot coordinator runtime (evidence)](./0248-grok-bot-coordinator-runtime-evidence.md) — 证据级五对象/投递契约/唤醒/人闸/连续性与主动；对照 learn-grok-bot + 重建树 + LocalExec

