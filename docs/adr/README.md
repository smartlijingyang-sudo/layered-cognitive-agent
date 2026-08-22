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
| [0070](0070-reducer-as-plugin.md) | CognitiveRuntime Reducer-as-Plugin — `_loop` 只调 Protocol，middleware 与 `_emit` 收口 | Accepted |
| [0071](0071-composer-per-cluster.md) | Composer-per-Cluster — 4 个 sub-composer plugin 接管 spawn 的装配策略 | Proposed |
| [0072](0072-null-default-discipline.md) | Null-Default Discipline — Think 群与 Memory retrieval 真 Null 默认 | Accepted |
| [0073](0073-runsession-sole-session-path.md) | Session Path Convergence — `SessionService` Protocol 统一两条路径的契约 | Proposed |
| [0074](0074-plugin-everything-trimmed-implementation.md) | Plugin-Everything 裁剪版 — 接受 0066/0068/0069、裁剪 0067 的 14 PR 实施计划 | Proposed |
| [0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md) | 阶段图与可信内核 | Proposed |

## 维护规则
- 不改旧文件；新决策用 `Supersedes: ADR-XXXX` 标记
- CI `tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 守护本表与 `docs/adr/*.md` 编号一致
