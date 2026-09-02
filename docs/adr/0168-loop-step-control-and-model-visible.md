# ADR-0168: Loop Step Control 与 Model-Visible 真实化

## 状态

**Proposed — 2026-09-02;执行计划:`docs/plans/2026-09-02-spine-step-remediation/main.md`。**

## 一句话

新增 `LoopStepControl` Protocol 与 `StdLoopStepControl` 集中切步;业务路径必经 `StepCoordinator`;`Model-Visible` 5 件套真实落盘;`Narrative` / `Graph` deriver per-run subscribe;`event_emission` hook 半残收口。

## 背景

ADR-0166 / 0167 / 0167.1 把切步责任交给 loop,并要求 `lca/runtime/loop_step_control.py` 集中持有 `begin_step` / `end_step` 决策。但该模块在仓库中**未实现**,业务路径 cognition/body/perceive 仅写 `phase.*.fold.start/end` EP,从未写 `writable.step.*` EP。`run_2ef78e887692` 实测:`writable.step.start` 出现 0 次;`journal.json.steps=[]`;`total_steps=0`。

| 现象 | 根因 | 影响 |
|---|---|---|
| `journal.steps` 始终为空 | 业务路径不调 `coord.begin_step` | DSH step 模型不可观测 |
| `narrative.md` 不含 step 详述 | `NarrativeDeriver` 未在 builder subscribe | trajectory 不可读 |
| `phase_graph.dot` 不存在 | `GraphDeriver` 未在 builder subscribe | 协作关系图丢失 |
| `model_visible/step_N/messages.json` 是骨架 | 无 `RequestHeaderRecord` + 无 `request_header.record` EP | I-MV1 未达成 |
| `facade.step_open` / `step_record_*` 死代码 | 转 self-loop,无业务调用方 | 接口/实现间隙 |
| `event_emission._derive_step_completed` 双轨 | 调 facade.record + coord.emit_phase | 重复事实 |

### ADR-0166 / 0167 已经在规范侧铺好

| 已有 | 文档 | 实装? |
|---|---|---|
| `StepCoordinator.begin_step / end_step / begin_segment / end_segment` | ADR-0167 D2 | ✅ 类存在;❌ 无业务调用方 |
| 5 个 record_* API | ADR-0167 D2 | ✅;❌ 无业务调用方 |
| `StepTreeAccumulatorDeriver` | ADR-0167 D11 | ✅;✅ builder subscribe;⚠️ 输入空 |
| `NarrativeDeriver` / `GraphDeriver` plugin | ADR-0167 D9 / 0167.1 PR-2 | ✅ plugin 化;❌ builder 未 subscribe |
| EXECUTION_POINTS 白名单含 `step.thinking.record` 等 5 项 | ADR-0165.1 D1 | ✅;❌ 无业务 emit |

## 决策

### D1. 新增 contracts/observability/loop_step_control.py

```python
from typing import Protocol

class LoopStepControl(Protocol):
    """loop 单点切步决策(ADR-0166 D3 / 0167 D2 / 0168)"""

    def open_step(self, *, phase: str, **ctx) -> str: ...
    def close_step(self, *, outcome: str = "success", error: str | None = None) -> None: ...
    def open_segment(self, kind: str) -> str: ...
    def close_segment(self, *, outcome: str = "success") -> None: ...

    @property
    def current_step_id(self) -> str | None: ...
```

### D2. 新增 runtime/loop_step_control.py

```python
@dataclass(frozen=True)
class NullLoopStepControl:
    """fallback 全 no-op + 1 次 warning log(不静默失败)"""

    def open_step(self, *, phase: str, **ctx) -> str: ...  # return "<unbound-step>"
    # close / open_segment / close_segment 同理 no-op


@dataclass
class StdLoopStepControl:
    """默认实现:持有 StepCoordinator,集中切步决策。"""

    _coord: StepCoordinator
    _step_open: bool = False
    _seg_open: str | None = None
    _current_step_id: str | None = None

    def open_step(self, *, phase: str, **ctx) -> str:
        if self._step_open:
            raise RuntimeError("open_step while step already open")
        self._step_open = True
        self._current_step_id = self._coord.begin_step(phase, **ctx)
        return self._current_step_id

    def close_step(self, *, outcome: str = "success", error: str | None = None) -> None:
        if not self._step_open:
            return  # 双保险,允许重复 close
        self._coord.end_step(outcome=outcome, error=error)
        self._step_open = False
        self._current_step_id = None

    def open_segment(self, kind: str) -> str: ...
    def close_segment(self, *, outcome: str = "success") -> None: ...

    @property
    def current_step_id(self) -> str | None:
        return self._current_step_id
```

### D3. RunExecutionEnvironment.prepare 装配

```python
# lca/plugins/transport/webserver/handlers/runs/execute/execution_environment.py
from lca.runtime.loop_step_control import StdLoopStepControl

def prepare(self, session: RunSession) -> None:
    self._bind_token = bind_current_coordinator(session.coordinator)
    if session.coordinator is not None:
        session.loop_control = StdLoopStepControl(session.coordinator)
    else:
        session.loop_control = NullLoopStepControl()
        log.warning("loop_control using NullLoopStepControl; step_open will be no-op")
```

### D4. CognitiveRunDriver 主循环切步

`lca/plugins/transport/webserver/handlers/runs/execute/loop_drivers.py::CognitiveRunDriver.execute` 在每次 iteration 开始调 `loop_control.open_step(phase='llm-act')`;iteration 收尾调 `loop_control.close_step(outcome=...)`。

### D5. safe_executor / tool_journal_emit 改用 loop_control + coord.record_*

| 旧调用 | 新调用 |
|---|---|
| `safe_executor._open_act_step` 写 `phase.act.fold.start` | `loop_control.open_segment('act')` + `coord.record_tool_call(...)` + `coord.emit_phase('act', ...)` |
| `safe_executor._close_act_step` 写 `phase.act.fold.end` | `loop_control.close_segment('ok'\|'failure')` + `coord.record_tool_result(...)` |
| `TelemetryLLMAdapter._record` 调 `_open_think_step` / `_close_think_step` | `loop_control.open_segment('think')` + `coord.record_thinking(...)` + `loop_control.close_segment` |

### D6. RunSessionBuilder.build subscribe Narrative + Graph

```python
# lca/plugins/transport/webserver/handlers/runs/session/builder.py:107-130 扩展
step_tree_deriver = StepTreeAccumulatorDeriver(...)
narrative_deriver = NarrativeDeriver(StepNarrativeWriter(run_dir, run_id))
graph_deriver = GraphDeriver(output_path=run_dir / "phase_graph.dot")

event_spine.subscribe(step_tree_deriver.on_event)
event_spine.subscribe(narrative_deriver.on_event)
event_spine.subscribe(graph_deriver.on_event)

# terminal.materialize 末尾联动
narrative_deriver.write_document(step_tree_deriver.document)
```

### D7. 新增 RequestHeader dataclass + llm.request.header EP

```python
# lca/contracts/observability/request_header.py (新)
@dataclass(frozen=True)
class RequestHeader:
    step_id: str
    reason: Literal["initial", "next_step", "series", "change", "inherited"]
    model: str
    system_digest: str; system_path: str
    tools_digest: str; tools_path: str
    messages_digest: str; messages_path: str
    manifest_digest: str; manifest_path: str
    token_estimate: int | None = None
    inherited_from_step: str | None = None
```

`EXECUTION_POINTS` 加 `llm.request.header`。

### D8. StepCoordinator.record_request_header 落 spine EP + model_visible

```python
def record_request_header(self, header: RequestHeader) -> None:
    self._write(self._mint_record(
        execution_point="llm.request.header",
        payload=asdict(header),
    ))
    path = self._run_dir / "model_visible" / f"step_{self._current_step}" / "request-header.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(header), indent=2))
```

### D9. TelemetryLLMAdapter._record 真实落 5 件套

在组装完 messages/tools/manifest 后、调 LLM 前,落 5 件套到 `model_visible/step_NN/`:

```python
def _record(self, *, step_id, messages, tools, manifest, model, system_prompt):
    if not step_id:
        return
    request_header = RequestHeader(
        step_id=step_id, reason="initial", model=model,
        system_digest=sha256(system_prompt.encode()).hexdigest(),
        system_path=f"model_visible/step_{step_id}/system-prompt.md",
        messages_digest=sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
        messages_path=f"model_visible/step_{step_id}/messages.json",
        tools_digest=sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest(),
        tools_path=f"model_visible/step_{step_id}/tool-schemas.json",
        manifest_digest=sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
        manifest_path=f"model_visible/step_{step_id}/context-manifest.json",
    )
    self._coord.record_request_header(request_header)
    # 同步落 5 件套(实际 messages/tools/manifest)
    self._model_visible_writer.write(request_header, messages, tools, manifest, system_prompt)
```

### D10. terminal.materialize 调 Coalescer.flush() + EventStorage.close()

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/materialization.py
def materialize(run_id, ...):
    registry = require_capability(ctx, "writable_face_registry")
    coalescer = registry.require("coalescer"); coalescer.flush()
    storage = registry.require("storage"); storage.close()
    # ... 后续 step_tree / narrative / graph deriver flush
```

### D11. 删 facade.step_* 死代码;event_emission hook 收敛到 coord

`lca/infrastructure/observability/facade/facade.py` 删除:
- `step_open` / `step_close`
- `step_record_thinking` / `step_record_tool_call` / `step_record_tool_result` / `step_record_reflect` / `step_record_span`

保留 `@deprecated` 包装 1 个版本,docstring 引导到 `StepCoordinator` 直接调用。`event_emission._derive_step_completed` 双轨删除 `facade.record(StepCompleted)` 一路,只走 `loop_control.close_step` + `coord.emit_phase('reflect')`。

## 不变量

| 编号 | 内容 | 验证 |
|---|---|---|
| I-0168-1 | 每次 iteration 必有 `writable.step.start` + `writable.step.end` 一对 EP | grep events.jsonl ≥ 1 |
| I-0168-2 | `journal.json.steps` 非空,`totals.steps ≥ 1` | jq |
| I-0168-3 | `journal.narrative.md` 含 step 表 | head |
| I-0168-4 | `phase_graph.dot` 存在 | ls |
| I-0168-5 | `model_visible/step_N/request-header.json` 含真实 digests | jq + sha256 校验 |
| I-0168-6 | `events.jsonl` + `journal.json` 一致(replay ≡ finalize) | replay test |
| I-0168-7 | 业务代码不 import `EventSpine` / `Serializer` / `Storage`(I-PLUG1) | importlinter `business-event-isolation` |
| I-0168-8 | `Facade.step_*` 删除后无外部调用 | grep `facade.step_open` 为 0 |
| I-0168-9 | `terminal.materialize` 第一行 `coalescer.flush() + storage.close()` | unit test |
| I-0168-10 | `_derive_step_completed` 不再调 `facade.record` | grep |

## 兼容性

- 删除 `facade.step_open` / `step_close` / `step_record_*` 之前保留 1 个版本的 `@deprecated` 包装,docstring 引导到 `StepCoordinator`
- `StampedEvent` / `JournalRecord`(journal.py)保留 readonly dataclass 集合供反序列化(PR-9)
- 删除 `_derive_action_degraded` 中的旧路径,与 `tests/test_simple_body_no_op_removed.py` 对齐

## 后果

### 正面

- `journal.json` 反映真实 step 闭环,doctor H2 不再误报
- `narrative.md` 含 step 表,`phase_graph.dot` 显示协作关系,DSH 风格轨迹可读
- `model_visible/step_N/` 真实 5 件套,replay 可重建,verify-model-visible 可校验
- `facade.step_*` 死代码清理后,facade 公共面窄而稳
- `event_emission` 半残收敛,业务事实仅走 spine
- 业务代码不直接 import EventSpine,架构边界严守

### 负面

- safe_executor / tool_journal_emit 改动面广,影响实际工具调用路径 → 单测 + run 实测
- builder 多 subscribe 2 个 deriver 可能影响延迟 → narrative/graph 都是 no-op except flush
- 删 facade.step_* 短期内可能影响调用方 → @deprecated 1 版本

### 不在本 ADR 范围

- ❌ `spine.deriver.metrics`(Prometheus)— 单独 PR
- ❌ `journal.py` 49 事件类删除(PR-9,readonly dataclass 保留)
- ❌ `spine.deriver.otel_trace` plugin wrapper(类已存在)
- ❌ OTel / Langfuse 投影路径
- ❌ 6 个非 web-standard profile 的 spine 装配(PR-10)

## 验证

```bash
# 单测
uv run pytest tests/observability/test_loop_step_control.py -v
uv run pytest tests/observability/test_writable_matrix_swaps.py -v
uv run pytest tests/test_runtime_journal_binding_integration.py -v

# 集成:重启 kernel 跑一个 run
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)

# 验证点(必须全部满足)
grep -c "writable.step.start" traces/runs/$LATEST/events.jsonl    # ≥ 1
jq ".steps | length" traces/runs/$LATEST/journal.json             # ≥ 1
jq .totals.steps traces/runs/$LATEST/journal.json                 # ≥ 1
ls traces/runs/$LATEST/phase_graph.dot                             # 存在
ls traces/runs/$LATEST/model_visible/step_*/request-header.json    # ≥ 1
jq ".messages | length" traces/runs/$LATEST/model_visible/step_001/messages.json  # ≥ 2

# 架构边界
uv run lint-imports
uv run python scripts/check_writable_matrix_boundaries.py
```

## 引用

- ADR-0063 Run Trace SSOT
- ADR-0164 Journal Step Tree
- ADR-0165(.1) Execution Point Enforcement
- ADR-0166 Step / Segment / Phase 三层计数与 Spine 硬化
- ADR-0167 Spine 唯一耐久真值、Step 物化视图与 Model-Visible 轨迹组织
- ADR-0167.1 Step-Tree Deriver Wiring 与 Run Layout 收尾
- DSH `docs/architecture.zh.md` §轮次流程(step = 一次模型请求 + 工具)
- `lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py`
- `lca/infrastructure/observability/writable_matrix/coordinator.py`
- `lca/plugins/transport/webserver/handlers/runs/session/builder.py`
- `lca/plugins/transport/webserver/handlers/runs/execute/loop_drivers.py`