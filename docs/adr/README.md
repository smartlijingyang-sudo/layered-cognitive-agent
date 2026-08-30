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
| [0083](0083-deepseek-harness-plugin-implementation-plan.md) | DeepSeek Harness 插件布局实施计划 | Plan |
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

| [0104](0104-runtime-package-organization-discipline.md) | 包组织纪律：8/10/15 规则 + 命名空间映射 | Proposed |
| [0105](0105-package-organization-discipline.md) | Python 包目录规模与命名规范（8/10/15 规则） | Proposed |
| [0106](0106-naming-constitution.md) | 命名宪法（v3 九群归属 + 四维分解 + 角色后缀） | Proposed |
| [0107](0107-unimplemented-scenario-modules.md) | scenario plugin modules never implemented (tracked gap) | Proposed |
| [0108](0108-phase-de-and-e.md) | Phase D (CI gates) + Phase E (README + cleanup) closeout | Accepted |

## 维护规则
- 不改旧文件；新决策用 `Supersedes: ADR-XXXX` 标记
- CI `tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 守护本表与 `docs/adr/*.md` 编号一致
| [0102](0102-tool-render-contract.md) | Tool 渲染契约 — 集中 TS 生成（lcaToolRender） + 21 工具 registry | Accepted |
| [0103](0103-locked-surface-and-port-policy.md) | back-ui-821-other-keep 锁定表面 + 移植策略（hard/soft-lock + lane A/B/C） | Accepted |
