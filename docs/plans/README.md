# docs/plans 索引

设计文档（design）与实施计划（plan）的归档目录。命名惯例：`YYYY-MM-DD-<主题>-design.md` / `-plan.md`。
设计稳定后是否 ADR 化由 iter-arch 轮评估；已 ADR 化 / 已落地的设计在此标注交叉引用。

## 2026-10-01 新增（11 篇，6 个主题）

| 主题 | design | plan | 状态 |
|---|---|---|---|
| ADR-0255 Muse 运行时对齐 | 2026-10-01-adr0255-muse-runtime-alignment-design.md | 2026-10-01-adr0255-muse-runtime-alignment.md | 已落地 → [ADR-0255](../adr/0255-muse-production-runtime-full-reference.md) |
| ADR-0256 工具 namespace 分类 | 2026-10-01-adr-0256-tool-namespace-taxonomy-design.md | 2026-10-01-adr-0256-tool-namespace-taxonomy-plan.md | 已落地 → [ADR-0256](../adr/0256-tool-namespace-taxonomy.md) |
| Assistant avatar drawer + 文件 SSOT 编辑器 | 2026-10-01-assistant-avatar-drawer-and-file-ssot-editor-design.md | 2026-10-01-assistant-avatar-drawer-and-file-ssot-editor-plan.md | 设计已交付，实施状态待确认 |
| Conversational onboarding + assistant 命名 | 2026-10-01-conversational-onboarding-and-assistant-naming-design.md | 2026-10-01-conversational-onboarding-and-assistant-naming-plan.md | 2026-10-01 新增，状态待确认 |
| 硬编码治理 | 2026-10-01-hardcoding-remediation-design.md | 2026-10-01-hardcoding-remediation-plan.md | Approved；iter-arch 评估结论：不整篇 ADR 化（INV 矩阵已承载契约价值，见 iteration-backlog todo-4） |
| LCA runnable capability test suite | 2026-10-01-lca-runnable-capability-test-suite-design.md | —（仅 design） | 2026-10-01 新增，状态待确认 |

## 2026-10-02 新增

| 主题 | 文件 | 状态 |
|---|---|---|
| ADR-0268 cron 地基进度交接 | 2026-10-02-adr-0268-cron-foundation-handoff.md | 已合入 `tmp/adr0268-merged`；后续实现见 [ADR-0268 §14](../adr/0268-context-bus-async-executors-and-cron-projection.md) |

## 历史归档（按月）

- **2026-09-30**：commercial-context-files-and-continuous-memory-design、commercial-dialogue-scenario-eval-design/-plan、mailbox-ledger-dashboard-page-design/-plan
- **2026-09-29**：auth-isolation-and-login-fix-plan
- **2026-09-28**：mailbox-ledger-realtime-cqrs-sync-design/-plan
- **2026-09-27**：muse-personal-mcp-design、muse-personal-mcp
- **2026-09-26**：cadence-memory-consolidation-design
- **2026-09-25**：agent-friendly-dynamic-search-design/-plan
- **2026-09-24**：everything-library-design/-plan、grok-bot-production-alignment-design/-plan
- **2026-09-23**：adr-0248-completion-and-runtime-wiring-design/-plan、room-runtime-go-live-design/-plan
- **2026-09-22**：approval-policy-engine-design/-plan、creator-mode-assistant-home-alignment-design/-plan、dynamic-role-and-team-decoupling-design/-plan、gated-vocal-runtime-and-delivery-contract-design/-plan、local-machine-status-and-auto-install-design/-plan、mcp-integration-refactor-design/-refactor、memory-closed-loop-and-scenario-validation-design/-plan、peer-assistants-and-group-chat-design/-plan、wake-matrix-and-subagent-mute-runtime-plan、wechat-channel-lca-integration-design/-plan
- **2026-09-21**：assistant-creation-and-resume-refactor-design/-refactor、grokbot-field-notes-superpowers-integration-design/-plan、refactor-search-mcp-heuristics-design/-heuristics、typesafe-memory-prefilter-design/-plan
- **2026-09-20**：adr-0246-m1-local-exec-port、adr-0246-m2-m4-e2e-design/-plan、agent-memory-knowledge-layer、assistant-evolution-flow-design/-flow、conversational-local-machine-connection-design/-plan
- **2026-09-19**：adr-0244-implementation-plan、assistant-self-management-closure
- **2026-09-16**：improve-codebase-sweep
- **2026-09-14**：stop-decision-retirement
- **2026-09-02**：spine-step-remediation/（目录）
- **2026-09-01**：run-failure-rca-and-fix-plan
- **2026-08-27**：agent-loop-focus-governance、agent-loop-industry-findings、agent-loop-industry-notes
- **2026-08-19**：cognitive-primitive-v3-implementation、cordis-migration
- **2026-08-16**：harness-spine-completion
- **2026-08-14**：execution-alignment、execution-planes

## 未日期前缀（6 篇）

adr-0074-plugin-everything-tracker.md、adr-0096-implementation-tracker.md、codebase-improve-100-rounds.md、hermes-capability-matrix.md、hermes-progress.md、task.md

## 维护规则

- 新增 design/plan 文档时在此登记一行（2026-10-01 起的新文档进顶部表格，历史文档保持按月归档不动）；
- 设计废弃 / 落地后更新状态列并交叉引用对应 ADR；
- 设计稳定且含契约级决策 → 提案 ADR 化（iter-arch 评估），此处留交叉引用。
