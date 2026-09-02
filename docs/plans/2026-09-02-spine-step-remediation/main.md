# Spine / Step / Writable Matrix 全栈整改计划

> Status: **Plan — 待评审**
> 起草: 2026-09-02
> 关联 ADR: ADR-0063 / 0164 / 0165(.1) / 0166 / 0167 / 0167.1 / 本计划将产出 ADR-0168

---

## 0. 摘要(Synthesized From First Principles)

LCA 当前 Spine / Step / Writable Matrix 子系统的**架构骨架**(SSOT、五面矩阵、Per-run deriver、Plugin 化 spine、closed-set EP、J1-J4)已在 ADR-0163~0167.1 落地。**但在两个关键执行边界存在半残问题**:

1. **step 边从未被业务路径 emit**:`ADR-0166 D3 / ADR-0167 D11` 承诺的 "loop / phase driver 单点 open/close step" 实际**没有实现**。`lca/runtime/loop_step_control.py` 不存在;业务层 cognition/body 走 `coord.emit(phase.*.fold.start/end)`,`writable.step.*` EP 在最新 run 中出现 **0 次**。
2. **JournalDoc 与 facade.step API 失去回路**:`JournalStep.steps=[]` 的根本原因是(1),次要原因是 `NarrativeDeriver` / `GraphDeriver` 已 plugin 化但 `RunSessionBuilder.build` 只 subscribe `StepTreeAccumulatorDeriver`,**narrative.md / phase_graph.dot 路径断裂**。

更深的"双轨/重复职责"问题集中在四处,每个都需要 AD-级决策才能动:

| # | 位置 | 现状 | 第一性原理判断 |
|---|---|---|---|
| P1 | 业务层切步 | cognition/body 写 `phase.*.fold.*` EP;loop 不写 `writable.step.*` EP | ADR-0166 D3 目标态未达成 |
| P2 | `journal.py` vs `journal_step.py` | 49 事件流 + Step 树并存,StampedEvent / JournalRecord 双 envelope | 同一事实两个 SSOT 容易漂移 |
| P3 | `event_emission.py` hook 链 | hook 调 `facade.record(JournalEvent)` 同时 `_derive_step_completed` 调 `coord.emit_phase` | 双轨残留(ADR-0167 PR-3 目标态未达成) |
| P4 | `model_visible/step_N/` 5 件套 | 由 `_write_model_visible` 写但 `messages.json` 是占位骨架 | ADR-0167 I-MV1 未达成 |

---

## 1. 现状盘点(模块 → 契约 → 互动 → 问题)

### 1.1 模块脑图

```text
contracts/observability/                      ── 14 个 Protocol
contracts/models/observability/               ── 49 事件 frozen dataclass + 8 step 原语 + JournalDoc 3.1 + Totals
   │
   ▼ (单向依赖,禁止反向)
infrastructure/observability/
  facade/        ─ BoundObservability + step_open/close/step_record_* (转 coordinator)
  writable_matrix/  coordinator / registry / defaults (5 面)
  spine/            event_record / event_spine / manifest / context / registry / orphan / transport_emit
                    sinks/{file,routing_file}
                    derivers/{base,narrative,step_tree_accumulator,graph,live_tail,otel_trace,waterfall}
  journal/          RunStore append-only ledger + Projectors
  stream/           TraceInspector
  replay/cursor.py  StandardCursor (零 token 回放)
  evidence/         FilesystemEvidenceStore
  cost/             CostProjector
  events/           EventDescriptor registry
  genai/            semantic mapper
  diagnostics/      pattern library
  adapters/         TelemetryLLMAdapter / AttributePolicy
  backends/         FilesystemJournalStore / FilesystemRunLocator / OtelTracer / MemoryJournal
  narrative/        human narrative helper
   │
   ▼ (plugin 化入口)
plugins/observability/
  spine/       core / emit_pipeline / spantree / runtime_hooks
               reflectors/{signature,source,context,runtime,transport}
               classifiers/{exception_builtin,exception_unclass}
               derivers/{anomaly,narrative,graph,live_tail}
               sinks/{file,console}
               wraps/{ctx_effect,ctx_intercept,assembler}
  writable_matrix/
               assembly (L2 seam) / emitter/otel / serializer/label / storage/multi
   │
   ▼ (transport / business)
plugins/transport/webserver/handlers/runs/
    session/builder.py        ─ RunSessionBuilder.build (★ StepCoordinator 装配 + StepTreeAccumulatorDeriver subscribe)
    execute/execution_environment.py ─ bind_current_coordinator
    terminal/materialization.py      ─ run 终态落盘

lca_kernel/
    boot.py (K3)              ─ spawn_fiber + install_observability
    observability.py (K5)     ─ assemble_observability
    plan.py (K2)              ─ compile_run_plan
```

### 1.2 关键契约(对照 ADR 与实现)

| 契约 | 来源 | 实现 | 偏差 |
|---|---|---|---|
| `events.jsonl` = SSOT | ADR-0063 I1 | `RoutingFileStorage.write()` | ✅ 已对齐 |
| `journal.json` = 物化视图 | ADR-0167 D1 | `StepTreeAccumulatorDeriver.flush()` | ✅ 装配到位,但**输入为空** |
| `StepCoordinator` = 唯一写入口 | ADR-0167 D2 | `journal_setup.py::build_step_coordinator` | ⚠️ 存在但**调用方只有 facade.step_open** |
| `model_visible/step_N/` 5 件套 | ADR-0167 D3 / I-MV1 | `_write_model_visible()` | ❌ `messages.json` 是骨架 |
| 五面矩阵独立可替换 | ADR-0167 D11 | `WritableFaceRegistry` 7 面 | ⚠️ 后两面在 coordinator 未被 `require` |
| `Coalescer.flush()` / `EventStorage.close()` | contracts/observability/writable_matrix.py | `_write()` 不调 | ❌ 合约方法 > 调用面 |
| 业务代码只能调 `coord.emit_*` | ADR-0167 D11 / I-PLUG1 | cognition/body 已用 | ⚠️ 只到 phase 粒度 |
| loop 单点 open/close step | ADR-0166 D3 / 0167 D2 | `lca/runtime/loop_step_control.py` **不存在** | ❌ **完全未实现** |
| boot 不订阅 per-run deriver | ADR-0167.1 D1 | `spine.core` boot 不 subscribe | ✅ 已对齐 |
| per-run deriver 在 builder 装配 | ADR-0167.1 D2 | builder subscribe step_tree | ⚠️ **未 subscribe narrative / graph** |
| spine reflector.source 强制 | ADR-0165.1 I17 | spine-default 装载 | ✅ |

### 1.3 谁互动谁(关键调用链)

```text
HTTP /runs
  → RunSessionBuilder.build               ── 构造 StepCoordinator + StepTreeAccumulatorDeriver
  → RunExecutionEnvironment.prepare       ── bind_current_coordinator (ContextVar)
  → CognitiveRunDriver.execute            ── 主循环
      ├─ brain.think                      ── coord.emit_phase(phase='think')
      ├─ body.execute_tool                ── coord.emit(phase.tool.call.*)
      ├─ reflect                          ── coord.emit_phase(phase='reflect')
      └─ perceive                         ── coord.emit_phase(phase='perceive')
      │
      ├─ (期望但未发生) coord.begin_step   ❌
      └─ (期望但未发生) coord.end_step    ❌

terminal.materialize:
      ├─ step_tree_deriver.flush() → journal.json (但 steps=[])
      ├─ (未订阅) NarrativeDeriver → narrative.md ❌
      └─ (未订阅) GraphDeriver → phase_graph.dot ❌

facade.step_open() → coord.begin_step()  ← 无业务调用方 (0)
facade.step_record_thinking() → coord.record_thinking()  ← 无业务调用方 (0)
```

### 1.4 问题清单

**P1. 业务路径不切步(最严重)** — `writable.step.*` EP 在最新 run 出现 0 次;`journal.steps=[]`;`total_steps=0`。根因: `lca/runtime/loop_step_control.py` 不存在。后果: ADR-0167 D11.4 承诺的"step 是事实闭环"无法验证。

**P2. Narrative / Graph / LiveTail deriver 在 builder 未 subscribe** — `narrative.md` 内容空;`phase_graph.dot` 不存在。根因: ADR-0167.1 PR-2 标记"下次清理"未做。

**P3. event_emission.py 半残** — `_derive_step_completed` 双轨:facade.record + coord.emit_phase。

**P4. model_visible 5 件套是骨架** — `messages.json` 是 placeholder,非真实 LLM 请求原文。I-MV1 未达成。

**P5. facade.step API 死代码** — `step_open` / `step_close` / `step_record_*` 6 个函数 grep 全 lca/ 业务调用方为 0;facade 转 self-loop。

**P6. journal.py 与 journal_step.py 双顶层真相** — 49 事件流 + Step 树并存,StampedEvent / JournalRecord 双 envelope。迁移未完成。

**P7. 6/9 profile 缺 EventSpine 装配** — `web-standard-continuous` / `web-standard-recovery` / `cordis-creator` / `genai-traced` / `coding-agent` / `self-improving-minimal` / `test-minimal` 没有 spine-default bundle。

**P8. Coalescer.flush() / EventStorage.close() 永不调用** — `_write()` 只调 feed/write/serialize;架构边界腐化。

**P9. spine_oii_debug 重复加载 spine.reflector.source** — DAG 解析未去重。

**P10. request_header / RequestHeaderRecord 缺定义** — contract 用 dict 而非 frozen dataclass;无 EP。

---

## 2. 整改方案(从第一性原理)

### 2.1 设计原则(贯穿全部 PR)

| 原则 | 落地 |
|---|---|
| **SSOT 单一** | 业务事实仅 spine(不再 facade.record 直接写 49 事件流) |
| **I-PLUG1 严守** | cognition / body / runtime / agent 不 import EventSpine/Serializer/Storage,只走 coord |
| **loop 单点切步** | `loop_step_control.py` 集中持有 begin_step/end_step 决策;Brain/Body 只 `record_*` |
| **plugin 化一切** | deriver / writer / recorder 都是 plugin;profile 选择装配 |
| **不静默失败** | 缺 capability → fail-fast + log;不静默 no-op |
| **I-MV1 真实化** | 每次 LLM 实际请求必经 RequestHeader → spine EP + model_visible 5 件套 |
| **J1-J4 闭环** | journal.json / narrative.md / phase_graph.dot 三件套都从 spine events 派生 |

### 2.2 PR 分解(10 个 PR)

| PR | 标题 | 依赖 | 改动规模 | 验证 |
|---|---|---|---|---|
| **PR-1** | 引入 `LoopStepControl` 与 ADR-0168 | — | 1 ADR + 1 新模块 + 5 调用点 | `tests/observability/test_loop_step_control.py` |
| **PR-2** | 业务路径切步:safe_executor / perceive_hub / TelemetryLLMAdapter 调 begin_step/end_step + record_* | PR-1 | 5-8 文件 | run 实测 + journal.steps ≥ 1 |
| **PR-3** | Narrative / Graph deriver per-run subscribe | — | 1 文件(扩 builder.py:107-130) | `lca-ops journal narrative <run>` 非空;phase_graph.dot 存在 |
| **PR-4** | `event_emission.py` 收敛:hook 只走 spine;_derive_* 迁到 LoopStepControl | PR-1, PR-2 | 1-2 文件 | `facade.record` 在 cognition 路径为 0 |
| **PR-5** | model_visible 真实化:RequestHeader dataclass + llm.request.header EP + record_request_header | — | 1 contract + 1 EP + 1 deriver | `lca-ops journal verify-model-visible <run>` 通过 |
| **PR-6** | 删 facade.step_* 死代码;JournalEmitFn 收口 | PR-1, PR-4 | 2-3 文件 | check_writable_matrix_boundaries 通过 |
| **PR-7** | Coalescer.flush() / EventStorage.close() 真正收尾 | — | 2 文件 | terminalize 第一行调一次 |
| **PR-8** | request_header.record + Profile 默认开启;spine.deriver.otel_trace/waterfall plugin wrapper | — | 2-3 plugin + profile patch | oii-debug waterfall HTML 可用 |
| **PR-9** | 双 SSOT 收口:journal.py 49 事件保留 readonly dataclass(仅反序列化);StampedEvent/JournalRecord → v2.1 + source inversion | — | 1 ADR append + 0 代码删除 | `tests/test_journal_v21_legacy_compat.py` |
| **PR-10** | 9 profile 装配 audit + fix + check_profile_observability_coverage.py | — | profiles/*.yaml + 1 脚本 | 检查脚本通过 |

### 2.3 PR-1 详细设计

**目标**:实现 `lca/runtime/loop_step_control.py`,集中切步决策

**接口**(contracts):

```python
# lca/contracts/observability/loop_step_control.py (新)
class LoopStepControl(Protocol):
    """loop 单点切步决策(ADR-0166 D3 / 0167 D2 / 0168)"""
    def open_step(self, *, phase: str, **ctx) -> str: ...
    def close_step(self, *, outcome: str, error: str | None = None) -> None: ...
    def open_segment(self, kind: str) -> str: ...
    def close_segment(self, *, outcome: str) -> None: ...
```

**实现**(`lca/runtime/loop_step_control.py` 新):

```python
@dataclass
class StdLoopStepControl:
    _coord: StepCoordinator
    _step_open: bool = False
    _seg_open: str | None = None

    def open_step(self, *, phase: str, **ctx) -> str:
        if self._step_open:
            raise RuntimeError("open_step while step already open")
        self._step_open = True
        return self._coord.begin_step(phase, **ctx)

    def close_step(self, *, outcome: str = "success", error: str | None = None) -> None:
        if not self._step_open:
            return
        self._coord.end_step(outcome=outcome, error=error)
        self._step_open = False
    # open_segment / close_segment 同理
```

**绑定**: `RunExecutionEnvironment.prepare` 增一行,构造 `StdLoopStepControl(coord)` 存 `session.loop_control`。

**调用**: `CognitiveRunDriver.execute` 主循环调 `loop_control.open_step(phase='llm-act')` 在 iteration 开始;`close_step` 在收尾。

**fallback**: `build_step_coordinator` 若未注入 loop_control,工厂返回 NullLoopStepControl(全 no-op + log warning)。

### 2.4 PR-2 详细设计

| 业务路径 | 现状 | 目标 |
|---|---|---|
| `runtime/event_emission.py::_derive_step_completed` | 调 `coord.emit_phase('reflect')` | 改为 `loop_control.close_step(outcome='ok'\|'failure')` |
| `cognition/perceive_hub.py:93` `coord.emit_phase('perceive')` | 已正确 | 不动 |
| `cognition/body/safe_executor.py:_open_act_step` | 写 `phase.act.fold.start` | 改 `loop_control.open_segment('act')` + `coord.record_tool_call` + `coord.emit_phase('act')` |
| `cognition/body/safe_executor.py:_close_act_step` | 写 `phase.act.fold.end` | 改 `loop_control.close_segment` + `coord.record_tool_result` |
| `cognition/body/tool_journal_emit.py` 调 `coord.emit('step.tool_call.record')` | 已正确 | 不动 |
| LLM 调用入口 `TelemetryLLMAdapter._record` | 调 `_open_think_step` / `_close_think_step` | 改 `loop_control.open_segment('think')` + `coord.record_thinking` + `loop_control.close_segment` |

### 2.5 PR-3 详细设计

`RunSessionBuilder.build` 当前 subscribe `StepTreeAccumulatorDeriver` (line 107-119),扩展到 4 个。live_tail 已有 process-wide 单例,**不需 per-run subscribe**;仅 subscribe narrative + graph。

修订后 builder.py:107-130:

```python
step_tree_deriver = StepTreeAccumulatorDeriver(...)
narrative_deriver = NarrativeDeriver(StepNarrativeWriter(run_dir, run_id))
graph_deriver = GraphDeriver(output_path=run_dir / "phase_graph.dot")
event_spine.subscribe(step_tree_deriver.on_event)
event_spine.subscribe(narrative_deriver.on_event)
event_spine.subscribe(graph_deriver.on_event)
```

**风险**: `NarrativeDeriver` 当前 `on_event` 只 log,实际写入靠 `write_document(...)` 在 finalize 触发。需在 builder 增加 `narrative_deriver.write_document(document)` 在 terminal 阶段调用 — PR-3 一并实现。

### 2.6 PR-5 详细设计

**目标**:每次实际 LLM 请求,落 `request_header.record` EP + 真实 5 件套。

**contracts**:

```python
# lca/contracts/observability/request_header.py (新)
@dataclass(frozen=True)
class RequestHeader:
    step_id: str
    reason: Literal["initial", "next_step", "series", "change", "inherited"]
    model: str
    system_digest: str
    system_path: str
    tools_digest: str
    tools_path: str
    messages_digest: str
    messages_path: str
    manifest_digest: str
    manifest_path: str
    token_estimate: int | None = None
    inherited_from_step: str | None = None
```

**EP 增列**: `manifest.py` 加 `llm.request.header`(start 侧)。

**实现**: `coordinator.py` 增 `record_request_header(header: RequestHeader)`,写 spine EP + 同步落 `model_visible/<step_id>/request-header.json`。

**调用**: `TelemetryLLMAdapter._record`(组装完 messages/tools/manifest 后,真调 LLM 前):

```python
def _record(self, ...):
    step_id = self._coord.current_step_id
    if not step_id:
        return  # loop 未开 step,降级为 noop
    request_header = RequestHeader(
        step_id=step_id, reason="initial", model=model,
        system_digest=sha256(self._system_prompt.encode()).hexdigest(),
        system_path=f"model_visible/step_{step_id}/system-prompt.md",
        messages_digest=sha256(json.dumps(messages).encode()).hexdigest(),
        messages_path=f"model_visible/step_{step_id}/messages.json",
        tools_digest=sha256(json.dumps(tools).encode()).hexdigest(),
        tools_path=f"model_visible/step_{step_id}/tool-schemas.json",
        manifest_digest=sha256(json.dumps(manifest).encode()).hexdigest(),
        manifest_path=f"model_visible/step_{step_id}/context-manifest.json",
    )
    self._coord.record_request_header(request_header)
```

### 2.7 验证矩阵

| 验证项 | 命令 / 期望 |
|---|---|
| 最新 run `writable.step.start` ≥ 1 | `grep -c writable.step.start traces/runs/$(jq -r .run_id traces/latest.json)/events.jsonl` |
| `journal.json.steps` 非空 | `jq '.steps \| length'` ≥ 1 |
| `totals.steps` ≥ 1 | `jq .totals.steps` |
| `narrative.md` 含 step 表 | head 文件含 `## 🔍 Steps 详述` |
| `phase_graph.dot` 存在 | `ls traces/runs/<run>/phase_graph.dot` |
| `model_visible/step_N/request-header.json` 存在 | `ls traces/runs/<run>/model_visible/step_*/request-header.json` |
| `model_visible/step_N/messages.json` 真实 messages | `jq '.messages \| length'` ≥ 2 |
| importlinter business-event-isolation 通过 | `uv run lint-imports` |
| `scripts/check_writable_matrix_boundaries.py` 通过 | `uv run python scripts/check_writable_matrix_boundaries.py` |
| `tests/test_loop_step_control.py` 通过 | `uv run pytest tests/observability/test_loop_step_control.py` |

---

## 3. ADR-0168 草案

```markdown
# ADR-0168: Loop Step Control 与 Model-Visible 真实化

## 一句话
新增 LoopStepControl Protocol 集中切步;业务路径必经 StepCoordinator;
Model-Visible 5 件套真实落盘;Narrative/Graph deriver per-run subscribe;
收尾 event_emission hook 半残。

## 决策
- D1. 新增 contracts/observability/loop_step_control.py (Protocol)
- D2. 新增 runtime/loop_step_control.py (StdLoopStepControl 默认实现)
- D3. RunExecutionEnvironment.prepare 构造 LoopStepControl 并注入 session
- D4. CognitiveRunDriver 主循环 open_step(phase='llm-act') / close_step(outcome)
- D5. safe_executor / tool_journal_emit 改用 loop_control + coord.record_*
- D6. RunSessionBuilder.build subscribe Narrative + Graph deriver
- D7. 新增 RequestHeader dataclass + llm.request.header EP + coord.record_request_header
- D8. TelemetryLLMAdapter._record 真实落 messages/tools/manifest 到 model_visible/step_N/
- D9. terminal.materialize 调 Coalescer.flush() + EventStorage.close()
- D10. 删 facade.step_* 死代码;event_emission hook 收敛到 coord

## 验证
- writable.step.* EP ≥ 1 / run
- journal.steps 非空
- model_visible/step_N/request-header.json 含真实 digests
- importlinter business-event-isolation 通过
```

---

## 4. 不在本计划范围

- ❌ spine.deriver.metrics (Prometheus) — 单独 PR
- ❌ 删 journal.py 49 事件类(保留 readonly dataclass 集合)
- ❌ spine.deriver.otel_trace plugin wrapper(类已存在)
- ❌ lca_kernel/ boot 流程
- ❌ OTel / Langfuse 投影路径

---

## 5. 风险与依赖

| 风险 | 缓解 |
|---|---|
| PR-2 改 safe_executor 影响实际工具调用路径 | 单测 + run 实测 + 灰度 |
| PR-3 builder 多 subscribe 2 deriver 影响延迟 | narrative/graph 都是 no-op except flush |
| PR-5 model_visible 真实化增加 I/O | sha256 in-memory + 文件在 LLM 响应后落盘 |
| PR-6 删 facade.step_* 影响外部 import | 保留 @deprecated wrapper 1 个版本 |
| PR-7 Coalescer.flush() 触发时序 | terminal.materialize 第一行调一次 |

---

## 6. 时间线(估)

- PR-1: 1-2 天 | PR-2: 2-3 天 | PR-3: 1 天 | PR-4: 1 天 | PR-5: 2-3 天
- PR-6: 1 天 | PR-7: 0.5 天 | PR-8: 1 天 | PR-9: 1 天 | PR-10: 1 天
- **总估**: 10-14 天 单线 + 30% soak + 30% review buffer ≈ 18-22 工作日

---

## 7. 落地步骤(用户批准后立刻开始)

1. **PR-1**:创建 `docs/adr/0168-loop-step-control-and-model-visible.md` + `lca/contracts/observability/loop_step_control.py` + `lca/runtime/loop_step_control.py` + `tests/observability/test_loop_step_control.py`。先不接入任何业务路径(本 PR 只建立 seam)。
2. **PR-2**:接入 `safe_executor` / `perceive_hub` / `TelemetryLLMAdapter` / `tool_journal_emit`。每个文件改动前后跑一次 `run_xxx` 实测对比 journal.steps / totals.steps。
3. **PR-3**:builder.py:107-130 扩 subscribe,加 narrative/graph finalize 联动。
4. **持续验证**:`./scripts/lca-ops kernel-restart` + `latest run debug-run` + `journal trace` + `journal steps` + `journal narrative`。

每完成一个 PR 立刻跑上述验证矩阵,出问题立即修复,**不在 PR-N 留 TODO 给 PR-N+1**。