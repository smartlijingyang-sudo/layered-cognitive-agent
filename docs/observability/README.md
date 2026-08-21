# Observability —— ADR-0065

LCA 可观测性子系统 ADR-0065 的索引与概念地图。

## 三平面

1. **账本平面** — `JournalRecord` 的不可变序列;唯一事实 owner(L1-L3)
2. **证据平面** — `EvidenceStore` 治理的受控载荷(L5 / L8)
3. **物化视图平面** — 带版本与高水位的只读投影(L6 / §六)

## L1-L9 不变量

| # | 不变量 | 锚点 |
|---|---|---|
| L1 | 一次发生一次提交 | `RunLedger.append()` 单一写入入口 |
| L2 | 提交先于观察 | durable commit 完成才通知投影 |
| L3 | 身份与顺序不可重铸 | `(run_id, run_seq)` 严格连续 |
| L4 | 描述符先于实例 | `EventDescriptor` 注册表 + payload_schema_version |
| L5 | 证据引用可验证 | `EvidenceRef.algorithm+digest+byte_length` 校验 |
| L6 | 视图永不成为事实 | projector / summary / cost 不调 `append()` |
| L7 | 终态封存 | `seal()` 提交 terminal event 后冻结 |
| L8 | 策略先于持久化和外送 | classifier / retention / audience 在写入边界执行 |
| L9 | 组合根唯一 | gateway 路径不直接 `new` Journal/LiveTail |

## 文档

- [architecture-overview.md](./architecture-overview.md) — 三平面 + seam 拓扑
- [journal-v2-schema.md](./journal-v2-schema.md) — `JournalRecord` 字段全解
- [evidence-sidecar-spec.md](./evidence-sidecar-spec.md) — `EvidenceStore` / `EvidenceRef` / `EvidencePolicy`
- [run-layout.md](./run-layout.md) — `traces/runs/<id>/` + `latest.json` 原子语义
- [plugin-interaction-graph.md](./plugin-interaction-graph.md) — Mermaid 渲染规则
- [code-trace.md](./code-trace.md) — `SourceLocation` 受控 instrumentation
- [agent-debug-cookbook.md](./agent-debug-cookbook.md) — 4 阶段诊断流程 + 错误码字典
- [cli-reference.md](./cli-reference.md) — `lca-ops` 子命令参考

## ADR

- [ADR-0065](../adr/0065-recoverable-evidence-ledger.md) — 可恢复的证据保真运行账本
- [ADR-0064 (superseded)](../adr/0064-journal-v2-evidence-sidecar.md) — 旧版 journal v2 + evidence sidecar
- [ADR-0063](../adr/0063-run-trace-ssot.md) — 统一运行事件账本(已落地)
- [ADR-0037](../adr/0037-journal-as-truth.md) — Journal-as-Truth