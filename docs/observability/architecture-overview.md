# Architecture Overview — ADR-0065 三平面

## 全景图

```
┌─────────────────────────────────────────────────────────────┐
│ Tier-4 组合根 (lca/application/, gateway/)                   │
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

## Model-Visible 走 ADR-0183 统一 event bus(ADR-0185)

**状态**:Proposed(待审)。见 [docs/adr/0185-model-visible-event-bus-alignment.md](../adr/0185-model-visible-event-bus-alignment.md) 与配套 Note [docs/notes/proposed/seam/2026-09-04-model-visible-bus-alignment.md](../notes/proposed/seam/2026-09-04-model-visible-bus-alignment.md)。

**要点**:

- model-visible 不再走旁路文件 `<run_dir>/model_visible/`,改走 ADR-0183 统一 event bus,payload **带 system/tools 原文**(对齐 deepseek-harness `request/header` 语义)
- 新增独立 `@plugin` `lca.plugins.events.publishers.model_visible` 作为 `spine.llm.request.header` + `spine.llm.request.header.assistant` 唯一授权 producer,严格满足 ADR-0183 I-FW-BUS-1
- `ModelVisibleHook` 在 LLM adapter 边界 pre/post 拦截,内部用 `headerEquals` + `canonicalHeader` + `foldRequestHeader` fold 优化 journal 体积
- 5 PR 切分(独立可 revert):PR-0 fold spike → PR-1 类型化 → PR-2 publisher 双轨 → PR-3 替换 + viewer 迁移 → PR-4 删旁路文件 + 废 ADR-0169 D7 I-MV1 / ADR-0175 D3 / ADR-0176 D4
- 顺手修复 Note `2026-09-03-model-visible-incomplete-projection.md` 的 3 个 BUG:assistant 没投影、tools.json 空 `{}`、system 错塞 user

**当前实现到目标实现的迁移路径**:

```
旧(待废):                                               新(目标):

Brain._render_prompt                                    Brain._render_prompt
  └─ PromptAssembler → PromptTrace                        └─ PromptAssembler → PromptTrace
  └─ bind_current_reasoner_prompt (ContextVar)             └─ bind_current_reasoner_prompt (ContextVar,仍保留)

LLM adapter.complete(...)                                LLM adapter.complete(...)
  └─ ModelVisibleLLMAdapter._run_capture                   └─ ModelVisibleHook.before_publish
       ├─ StdReasonerPromptCapture                            ├─ 拿 system/tools/messages/manifest
       │    → system_prompt.json / system_prompt_sections.json│
       │                                                       ├─ headerEquals 判等 fold
       ├─ StdModelVisibleCapture                               └─ bus.publish(SpineLlmRequestHeaderPayload)
       │    → tools.json / messages.json / manifest.json        │
       │      / inherited.json (旁路文件)                       await self._inner.complete(...)
       │                                                         └─ ModelVisibleHook.after_dispatch
       └─ cursor.record_request_header(artifact)                     └─ bus.publish(SpineLlmRequestHeaderAssistantPayload)
            → spine EP: llm.request.header (digest + relpath)
                                                               ↓
<run_dir>/model_visible/step_<NN>/*.json  (旁路,即将删除)   <run_id>.spine.jsonl  (ADR-0183 I-FW-SSOT-1 唯一 SSOT)
```

**viewer 改造清单**(PR-3):

- `lca-ops explain <run_id>`:反查 `model_visible/` → 读 spine.jsonl 过滤 model-visible 事件 + `foldRequestHeader(events, step_id=...)`
- webserver trajectory viewer:同上
- `journal replay --diff-only`:走 fold 后比对
- integration tests fixture:期望从 `model_visible/step-001/*.json` 改为 spine.jsonl 含 2 类 model-visible 事件 + fold 可重建

**不破坏的 ADR-0183 不变量**:

- I-FW-BUS-1(producer 唯一入口 `EventBus.publish`)
- I-FW-SSOT-1(`<run_id>.spine.jsonl` 唯一 SSOT)— **本 ADR 强化**:删旁路文件
- I-FW-BUS-2(consumer 唯一入口 `EventBus.subscribe`)
- I-FW-BUS-3(plugin 不可改 EventBus 内部 / SpineSink 字节布局)
- I-FW-BUS-4(业务不订阅 `event.bus.dispatch.*`)

**新增 5 条 I-MV 不变量**(PR-4 由架构测试守护):

- I-MV-1:`ModelVisiblePublisher` 是 `spine.llm.request.header.{,assistant}` 唯一授权 producer
- I-MV-2:`foldRequestHeader(<run_id>.spine.jsonl, step_id)` 可重建 effective header;缺失则 fail-fast
- I-MV-3:禁止读 `<run_dir>/model_visible/` / 写 `loop_cursor/model_visible_*.py`
- I-MV-4:禁 Brain / Reasoner / Body / Agent publish model-visible EP
- I-MV-5:fold 用 `headerEquals` 字节级判等 + `canonicalHeader` 归一化