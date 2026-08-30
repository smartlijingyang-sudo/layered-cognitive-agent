# Architecture Overview — ADR-0065 三平面

## 全景图

```
┌─────────────────────────────────────────────────────────────┐
│ Tier-4 组合根 (lca/layer4_app/, gateway/)                   │
│   - 通过 ctx.require() 拉 capability,不直接 new            │
└──────────────────┬──────────────────────────────────────────┘
                   │ ctx.require("run_ledger_factory")
┌──────────────────▼──────────────────────────────────────────┐
│ RunLedgerHandle (run-scoped, 由 factory 创建)              │
│  ├── RunLedger (账本平面, 单一临界区 + expected-version) │
│  ├── EvidenceResolver (证据平面, 受策略读取)              │
│  ├── ProjectionRegistry (物化视图, commit 后扇出)         │
│  └── MaterializationStore (物化视图落盘, 带 watermark)    │
└──────────────────┬──────────────────────────────────────────┘
                   │ 四个独立 capability
┌──────────────────▼──────────────────────────────────────────┐
│ evidence_store / run_locator / projection_registry /       │
│ materialization_store / run_ledger_factory (each: seam +    │
│ provider + tier-3)                                          │
└─────────────────────────────────────────────────────────────┘
```

## 写入路径(L1-L4)

1. 业务层调 `record(AgentRunStarted(...))` (facade)
2. facade 调 `RunStore.append(event)`
3. RunStore 校验 descriptor(L4)+ expected-version(L3)+ durable commit(L2)
4. terminal event → `seal()`(L7)
5. projection fan-out post-lock(L2 提交先于观察)

## 读取路径(L5 / L6)

1. `TraceInspector(events)` 派生 `inspect_trace / explain_failure`
2. `CostProjector.on_event()` 累加 cost by pricing_ref
3. `MaterializationStore` 写 `materializations/<id>/<v>/` 带 watermark
4. **绝不**反向调 `append()`(L6)

## Gateway 层(L9)

`gateway/runs/_journal_factory.py` 是唯一允许 `new` Journal/LiveTail/ProcessJournal
的位置;`check_gateway_no_direct_journal_new.py` 静态扫描兜底。

## Coding Agent(L6 / §六)

7 个 read-only tool 走 `TraceInspector` + 账本只读;`check_no_journal_write_in_coding_agent.py`
AST 扫描确保无 `record()` / `RunLedger.append()` 旁路。

## 外部入站(§八)

W3C `traceparent` / `tracestate` 走 `DefaultW3CValidator` 不可信校验;通过后
只作为 `causation.links[].external_trace_id`,不覆盖 LCA `trace_id` / `run_id`。