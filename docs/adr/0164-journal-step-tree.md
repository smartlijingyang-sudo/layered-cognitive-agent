# ADR-0164: Journal step-tree 取代 stream-envelope

- 状态: Accepted
- 日期: 2026-09-01
- 作者: coding-agent
- 取代: ADR-0037 (record-as-data stream envelope), ADR-0074 PR-6 v2 envelope
- 相关: ADR-0156/0157/0158(投影/进度/finalizer 清理), ADR-0065(run ledger)

## 一句话

journal 主存储从"事件流 + seq 流水"升级到"step 故事 + 因果链"。一个 step = 一个认知闭环(上下文 → 思考 → 工具 → 结果 → 反思)。

## 背景

PR-6 (2026 Q2) 之前, journal 用 v1 envelope 流式追加 (`journal.jsonl`, 4273 条 seq)。PR-6 升级到 v2 envelope (`lca.journal/2`, schema 字段更多, 但仍是流式)。

到了 2026-09, 真实生产数据 (traces/runs/*) 已经 7017 个 run, 全部 .jsonl 格式。运行中发现两个根本问题:

1. **人类认知不对齐**: 一个 9 步认知循环在 jsonl 里展开成 4273 条 seq。读者必须自己 grep `scope.step` 推断"这是同一步"。 失败步在哪一行也找不到。

2. **本质错位**: journal 是事实账本, 人类想要的"事实"是"这个 run 的 6 步故事", 不是"4273 条 envelope 记录"。 流式是存储/投影友好的形态, 但不是叙事友好的形态。

## 决策

**journal 主存储从 v2 stream envelope 升级到 step-tree envelope (`lca.journal/3`)**。 一个 run 是一个 JournalDocument (顶层 envelope) 含 N 个 JournalStep (有序, 每个有 step_id / step_index / phase)。

每个 step 的 5 原语:
- `context_before`: StepContext (objective /  attachments /  prior_summary_chain /  cumulative_files /  extra)
- `thinking`: ThinkingTrace (model /  latency /  reasoning /  decision /  tool_call /  tokens)
- `tool_call`: ToolCallRecord (invocation_id /  name /  arguments /  arguments_summary)
- `tool_result`: ToolResult (ok /  latency /  stdout_head /  stderr /  files_created /  error /  delta_summary)
- `reflect`: ReflectTrace (summary /  verdict /  extra)

每个 step 还有 `spans: tuple[SpanRecord, ...]` 折叠诊断事实 (RuntimeObserved / ToolRetryProgress / ContextCompacted 等)。

### 闭集从 49 → 12

只保留容器 / 协作 / 控制 / 附件 / 插件 / boot 6 类 "事件级别" 事实 (12 种): AgentRunStarted/Finished, DelegationIssued/Completed, TeamRunStarted/Finished, Attachment*, Plugin*, BootProfile*, ApprovalRequested/Resolved。 一切 step 内部细节 (LLM/Tool/Stream) 进入 step-tree。

### 存储形态

`traces/runs/<run_id>/`
- `journal.json`: 主存储 (lca.journal/3, step-tree, pretty-print)
- `journal.raw.jsonl`: 可选保留 (旧 stream, 兜底回放)
- `journal.narrative.md`: StepNarrativeWriter 产出 (人读友好 markdown)
- `manifest.json`: 保持

### boot 装配

`lca.plugins.seams.observability.run_ledger` 在 `create_run_components` 阶段:
1. rename `journal.jsonl` → `journal.raw.jsonl` (旧数据保留)
2. JsonlJournalProjector 仍写到 `journal.raw.jsonl` (回放兜底)
3. **同时**构造 StepGroupedBackend + StepNarrativeWriter (主路径)
4. 挂到 session.step_tree_bundle
5. terminalizer 时 `_flush_step_tree()` 写 journal.json + narrative.md

### runtime emit 路径 (双写过渡期)

Phase 3 改造: `lca/runtime/step_emitter.py` 桥接层, 把现有 emit (TelemetryLLMAdapter / tool_journal_emit / perceive_hub / event_emission) 折叠进 step_lifecycle:
- `bridge_llm_completed` → step.thinking
- `bridge_tool_started` / `bridge_tool_invoked` → step.tool_call / tool_result
- `bridge_perceive_opened/closed` → step phase=perceive
- `bridge_step_completed_emitted` → close_step

调用方 API 完全不变 (emit_tool_started / record(event) 仍调用), 内部双写。 Phase 7 集中清理时删原 `record(event)` 调用, 只剩 step_lifecycle。

### CLI

`lca.ops journal {logs, steps, narrative, raw, migrate}` 5 个子命令:
- `logs`: 旧 SSE 流 (兼容保留)
- `steps`: step 表 / 单步 / 因果链 / JSON
- `narrative`: markdown narrative
- `raw`: 兜底读 raw.jsonl
- `migrate`: 把 .jsonl 启发式重建为 .json

### 一次性迁移 (Phase 6)

`lca.infrastructure.observability.journal.step.migrate.JournalMigrator`:
- 启发式把 v2 stream envelope 重建为 step-tree
- 标 `metadata.migration_inferred = True`
- 不删除 .jsonl(保留为回放源)
- CLI: `lca-ops journal migrate <run_id> [--all] [--dry-run]`

### doctor v3

`lca.plugins.transport.webserver.handlers.runs.doctor.step_check`:
- 8 hops (H1-H8)
- H4/H5 在 mode=backend 显式 skipped (不再永远 ok=None)
- H8 (新): 步骤因果链完整性 — 每 step 的 prior_summary_chain 末元素 == 上 step 的 reflect.summary

## 不做的事

- **不删** v2 JournalEvent 类 (Phase 7 才删, 涉及 ~49 个 dataclass 清理)
- **不删** JsonlJournalProjector / FactStreamProjector / LiveTail (SSE 还在用, 兜底回放)
- **不删** 旧 `journal.jsonl` 文件 (用户生产数据, 谨慎)
- **不改** StepTextDelta / ReasoningDelta 等流式事件 (SSE live 还需要)
- **不写** 自动 migrate (用户主动跑 `lca-ops journal migrate`)

## 后果

### 正面

- **可读性**: 9 步 run 1 张表看完, 不再 4273 条 seq 翻找
- **因果链显式**: prior_summary_chain 是 step 必备字段, 上一步反思自动串到下一步
- **5 原语对齐**: thinking / tool_call / tool_result / reflect / context_before 都是 step 的结构化字段, 不是散在事件流里
- **失败显眼**: step.outcome=fail + step.error 直接读, 不用 grep StackTrace
- **H8 链路检查**: doctor 自动发现"prior_summary_chain 断裂" 的 step

### 负面 / 风险

- **数据迁移**: 7017 个 run 是 .jsonl, 必须跑 `lca-ops journal migrate --all` 才能用新视图。 不跑的话 `journal steps` 报 "not found"
- **双写期临时复杂度**: Phase 3-5 期间 stream + step-tree 同时写。 Phase 7 集中清理后才彻底
- **失去流式细: step-tree 的 stdout_head 限 500 字符, 全文得 evidence store。 reader 不再能 grep "第 1034 条 seq"
- **依赖 reader (Phase 6)**: 必须用 `lca-ops journal steps / narrative / raw` 看, 不能再 `cat journal.jsonl`

### 兼容性

- **API 兼容**: facade.record(event) / emit_tool_started / 等所有 emit API 仍可用(双写)
- **数据兼容**: 旧 v1/v2 journal.jsonl 仍可读(Phase 6 之后才删)
- **工具兼容**: doctor / CLI / narrative 都接受 mode 区分 + dry-run

## 替代方案考虑

### A. 保留 stream, 升级 projection 视图

**否决**: projection 是视图, 不是真值。 用户最终要改真值才有完整链路。

### B. 把 step-tree 作为新增第三种文件 (journal.tree.json)

**否决**: 多一个文件不解决"哪个是真值"的问题。 stream 真值依然在, step-tree 只是视图, 反而更乱。

### C. 用数据库 (sqlite) 替换 jsonl

**否决**: 引入新依赖 + 数据库迁移 + 查询层。 step-tree 是纯文件, json + 简单 reader, 不需要数据库层。 长期看 step-tree 自然支持 "sqlite 后端" 但不是 Phase 6 的范围。

## 参考

- docs/design/2026-08-19-cognitive-primitive-constitution-v3.md (L2/L3/L4 闭环)
- docs/adr/0037-record-as-data.md (原 stream envelope 设计)
- docs/adr/0074-pr-6-journal-v2.md (v2 envelope, PR-6)
- docs/adr/0156-step-tree-projection.md (前置清理)
- docs/specs/harness-spine-spec.md (后续更新 §Journal Step-Tree Contract)