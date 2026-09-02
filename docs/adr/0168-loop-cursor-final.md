# ADR-0168: LoopCursor — 单状态机收敛 Spine / Step / Segment / Phase / Iteration / Journal / Projection

## 状态

**Proposed — 2026-09-02**

> **Supersedes**: ADR-0168 决策段、ADR-0168.1 决策段。
> **保留**: ADR-0168 作"问题陈述与现状盘点";ADR-0168.1 §转移图 / §Payload / §不变量 L1-L8 全部继承并升级。
> **引用 (cross-ref, 不 supersede)**: ADR-0063 / 0093 / 0094 / 0095 / 0162 / 0164 / 0165(.1) / 0166 / 0167(.1)。
> 实施计划: `docs/plans/2026-09-02-loop-cursor-final/main.md` (由 writing-plans 输出)。

## 一句话

把 LCA spine / step / segment / phase / iteration / journal / projection 七条并行路径收敛为**一个状态机 `LoopCursor`**。业务路径只允许两个动作:`advance(phase)` 与 `record_*(...)`;**所有其他写入、装配、订阅、刷新、关闭、投影、持久化都由 cursor 派生**。修补序列 ADR-0156~0168.1 在结构上不再可能。

## 背景

ADR-0168 §背景 与 ADR-0168.1 §背景 已记录 7 次连续修补(ADR-0156~0162)的同源失败模式:**业务路径加 / 改 → 漏了 emit / emit 多 / emit 错时序**。inventory 进一步暴露 11 类双轨 / 死代码,核心 3 类(详见 ADR-0168 §1.4 + plan 2026-09-02-spine-step-remediation §0):

1. **step 边从未被业务路径 emit**:`lca/runtime/loop_step_control.py` 不存在;`writable.step.*` EP 在最新 run 出现 0 次;`journal.steps=[]`。
2. **同一事件被 spine sink + writable.matrix.storage 双写到 `events.jsonl`**:`bundles/spine-default.yaml:138-148` 同时挂 `spine.sink.file` 与 `writable.matrix.default`,默认文件名都是 `events.jsonl`。
3. **业务层 9 处绕开 StepCoordinator step API**:`cognition/body` 用 `coord.emit_phase` (4 处) / `coord.emit` (5 处) 直接构造 EP 字符串;`cognition` 还有 4 处仍走旧 `record_runtime`(旧 journal `RuntimeObserved` 流)。

加上 inventory §11 的剩余 8 类(LLM 双轨、`facade.step_*` 死代码、`live_tail.py` EP 名丢失、`JournalEvent` 三轨并存、`ProjectionRegistry` ↔ spine subscribers 双分发等),**修补序列的根因不是 hook 层 bug,是 spine / projection / persistence 三套独立订阅 + 独立装配 + 独立 flush 的架构错位**。ADR-0168.1 把控制面收敛到状态机,但投影面与持久化面**未被状态机接管**,因此 §"不在本 ADR 范围"列出 7 项 follow-up(deriver.metrics / OTel 投影路径 / 6 profile 装配 / fork / halt-resume)。

本 ADR 把 ADR-0168.1 §"不在本 ADR 范围" 7 项**全部纳入**;新增 12 项把 projection / persistence / LLM hook / facade / profile 装配 / kernel(K5) / cordis 双词表 / incarnation 身份 / journal envelope 方向感知 / control slot / step-tree 物化 / 验证矩阵一并解决。**不留 Open Questions;不留 Follow-up ADR**。

## 第一性原理与设计原则

### P1 · 真值只能有一个 owner

数据所有权(v3 §6.3 八列矩阵)立了 `AgentState` 唯一 owner = G1 Reducer、`JournalRecord` 唯一 owner = G8 RunLedger。但当前实现里事实投影散落在 6 处:events.jsonl(spine) + journal.json(step-tree deriver) + narrative.md(narrative deriver) + phase_graph.dot(graph deriver) + model_visible/step_N/(step-tree deriver + adapter) + cost.json(cost projector) — 6 处都要自己保证不漏 emit。

**决策**:LoopCursor 是这 6 处的唯一协调者;每个投影 / 持久化都是 cursor 的派生。

### P2 · 状态机和投影不是同一件事,但必须同一时间被派生

dsh `ProjectionDefinition<K,S>` 不漏,是因为它订阅事件源 — 事件来了,apply 自然跑。当前 LCA:loop 产生事件,projection / persistence 各自分别订阅、分别在 builder / boot / adapter 装配 — 没人保证"只有这里可以订",于是 LiveTail 同时是 ring buffer + pub/sub + JournalProjector + replay source(注释 `live_tail.py:7-10` 自承"双轨残留")。

**决策**:`StdLoopCursor.__init__` 是 deriver / persistence / LLM hook 的**唯一装配入口**。RunSessionBuilder 不再订 deriver、不再装配 LLM hook、不再绑 coord — 它只构造 cursor。

### P3 · 好维护 = 每个文件只有一个修改理由

AGENTS.md §5:同一段代码同时做"记录 + 计算 + 副作用"就该拆。当前 `EventSpine` 接收 + routing + dispatch 三职;`WritableMatrix` 注册 + 装配 + 编排三职;`RunSessionBuilder` 建 session + 订 deriver + 装配 LLM hook 三职 — 都违反单一职责。

**决策**:cursor 只管状态机。projection 只读 `snapshot`。persistence 只物化 `snapshot` + 事件流。三个职责,三个 seam,无重叠。

### P4 · 好扩展 = 接口稳定 + 实现可替换

ADR-0061 plugin manifest、ADR-0068 compiled plugin kernel。当前 `coord.emit_phase` / `coord.record_*` / `coord.begin_step` 是 facade 不是 Protocol — 违反 I-PLUG1,扩方法就破坏调用方。

**决策**:`LoopCursor` 是 Protocol;`StdLoopCursor` 是默认实现;profile 可替换 cursor 实现 — 与 ADR-0088 Profile-selected Runtime Factory 一致。

### P5 · 控制/观察分离是结构属性,不是约定

v3 §4.4 + v4 P8 "观察零控制"是硬门禁。当前 `_derive_step_completed` 双轨(facade.record + coord.emit_phase,`event_emission.py:72-77`)是控制混入观察的实证。

**决策**:`Snapshot` 是 `frozen=True` 的只读视图;reducer 与 projection 只读不改(C4 自然满足)。observer 永远不可能"为了写日志而改 state"。

### P6 · 修补序列终止符 = 业务路径不接触 emit / subscribe / flush / close

ADR-0168.1 L19 自承"hook 是范畴错误"。本 ADR 把这条原则扩到所有 7 条并行路径:业务路径只看到 2 个动词 + 1 个 read;emit / subscribe / flush / close 全部由 cursor 派生。

## 决策

### D1 · LoopCursor Protocol(`lca/contracts/observability/loop_cursor.py` · 新建)

```python
from typing import Literal, Protocol
from dataclasses import dataclass
from lca.contracts.observability.writable_matrix import EventRecord

PhaseName = Literal[
    "perceive", "think", "gate", "act", "reflect", "remember", "stop"
]
CloseReason = Literal[
    "completed", "user_stop", "budget_exhausted",
    "approval_pending", "approval_rejected", "error", "loop_guard",
    "kernel_shutdown"
]
IterationReason = Literal[
    "tool_retry", "gate_retry", "checkpoint_resume",
    "subagent_resume", "user_replay"
]

@dataclass(frozen=True)
class CursorSnapshot:
    """只读视图;reducer / projection / persistence / observer 消费。"""
    run_id:        str
    trace_id:      str
    incarnation:   int          # D12 显式身份
    step_id:       str | None
    step_index:    int          # 自增,从 1 起;iteration 内重新计数
    iteration:     int          # 外层重试轮次 (⊃ ADR-0095)
    attempt_in_step: int        # step 内重试
    phase:         PhaseName | None   # None = OUTSIDE_LOOP
    iteration_reason: IterationReason | None
    stop_signal:   CloseReason | None
    seq:           int          # 当前事件 seq (RunLedger L3 一致性)


class CursorError(Exception):
    """非法转移 / 关闭后调用 / 跨窗口 record → raise,不静默 fallback。"""


class LoopCursor(Protocol):
    """Loop 单一状态机 (本 ADR)。

    业务路径唯一允许做的:
        - advance(phase)        : 转移 phase 窗口
        - halt(reason)          : 终止当前 iteration
        - close(reason)         : 关闭 cursor (五步顺序,见 D5)
        - record_thinking(...)  : 落 step.thinking.record EP
        - record_tool_call(...) : 落 step.tool_call.record EP
        - record_tool_result(...): 落 step.tool_result.record EP
        - record_request_header(...): 落 llm.request.header EP + 5 件套
        - fork(reason) -> "LoopCursor"  : subagent / delegation

    不暴露:
        begin_step / end_step / open_segment / close_segment
        emit_phase / emit / subscribe / flush / close_storage
        close_deriver / release_hook

    公共面 9 + 1 (snapshot)。
    """

    @property
    def snapshot(self) -> CursorSnapshot: ...

    # 转移 (3)
    def advance(self, phase: PhaseName) -> CursorSnapshot: ...
    def halt(self, reason: CloseReason) -> None: ...
    def close(self, reason: CloseReason) -> None: ...

    # 事实记录 (4)
    def record_thinking(self, payload: "ThinkingRecord") -> None: ...
    def record_tool_call(self, payload: "ToolCallRecord") -> None: ...
    def record_tool_result(self, payload: "ToolResultRecord") -> None: ...

    # 横切 (2)
    def record_request_header(self, header: "RequestHeader") -> None: ...
    def fork(self, reason: Literal["child_agent", "delegation"]) -> "LoopCursor": ...
```

**为什么是 9 + 1,不是 6 也不是 12** (继承自 ADR-0168.1 §D1):逐一对照现行控制点,逐个决定保留 / 删除:

| 现行控制点 | 文件:行 | 在本 ADR 下 |
|---|---|---|
| `coord.begin_step / end_step` | `coordinator.py:138-173` | 删 — 由 `advance(phase)` 派生 |
| `coord.begin_segment / end_segment` | `coordinator.py:175-203` | 删 — 由 phase (think/act) 派生 |
| `coord.emit_phase` (4 调用方) | `safe_executor.py:388,403` 等 | 删 — `advance(phase)` 即发 `phase.<name>.fold` EP |
| `coord.record_thinking` 等 5 个 | `coordinator.py:277-324` | 收 — `cursor.record_thinking` 唯一入口 |
| `facade.step_open / step_close / step_record_*` 7 个 | `facade.py:516-575` | 删 — **无调用方**(inventory §9.1) |
| `event_emission._derive_step_completed` | `event_emission.py:66-87` | 删 — 整段移除(含 facade.record 双轨) |
| `event_emission._derive_action_degraded` | `event_emission.py:50-63` | 保留 — 转 `cursor.record_*` 适配器,emit `runtime.action.degraded` EP |
| `event_emission.make_journal_emitting_hook` | `event_emission.py:97-134` | 删 — hook 范畴错误(ADR-0168.1 L19) |
| `coord.emit` (5 调用方) | `tool_journal_emit.py:141,179,275` 等 | 收 — `cursor.record_tool_call / record_tool_result` 唯一入口 |
| `facade.record_runtime` (4 调用方) | `perceive_hub.py:116,133` 等 | 删 — 改 `cursor.record_thinking / record_tool_call / record_request_header` |
| `RunSessionBuilder.subscribe step_tree` | `session/builder.py:118` | 删 — `cursor.__init__` 唯一装配入口 |
| `RunSessionBuilder.bind_current_coordinator` | `execute/execution_environment.py:128-130` | 收 — `cursor.attach()` 注入 ContextVar |

### D2 · 状态转移图(继承并升级 ADR-0168.1 §D2)

```text
                  ┌────────────────────────────────────────┐
                  │            OUTSIDE_LOOP                │  (cursor.close() 之后)
                  └────────────────────────────────────────┘
                                  │ cursor.advance('perceive')
                                  ▼
                  ┌────────────────────────────────────────┐
                  │  PERCEIVE  (phase window open)         │
                  └────────────────────────────────────────┘
                                  │ advance('think')
                                  ▼
                  ┌────────────────────────────────────────┐
                  │  THINK  (segment.think 隐式)           │◀──┐
                  └────────────────────────────────────────┘   │ retry in step
                                  │ record_thinking            │   (attempt_in_step++)
                                  │ advance('gate')            │
                                  ▼                              │
                  ┌────────────────────────────────────────┐   │
                  │  GATE                                       │
                  └────────────────────────────────────────┘   │
                                  │ (gate 通过 / reject / pause)│
                                  ▼                              │
                  ┌────────────────────────────────────────┐   │
                  │  ACT  (segment.act 隐式)                 │   │
                  └────────────────────────────────────────┘   │
                                  │ record_tool_call              │
                                  │ record_tool_result            │
                                  │ advance('reflect')            │
                                  ▼                              │
                  ┌────────────────────────────────────────┐   │
                  │  REFLECT                                  │
                  └────────────────────────────────────────┘   │
                                  │ (maybe remember)             │
                                  │ advance('stop') ─────────────┘
                                  ▼
                  ┌────────────────────────────────────────┐
                  │  STOP  (close_iteration 候选)         │
                  └────────────────────────────────────────┘
                                  │ (iteration 还有 budget)
                                  │ cursor.advance('perceive') → 下一轮 iteration (iteration++)
                                  ▼
                  ┌────────────────────────────────────────┐
                  │  OUTSIDE_LOOP ← cursor.close(reason)   │
                  └────────────────────────────────────────┘
```

- **step** 边界由 `record_request_header` 派生:每次 LLM 调用前 `cursor.record_request_header(...)` = 一次 `step.thinking.record` 或 `step.tool_result.record` 起点。
- **segment** 边界由 phase 派生:phase = think → `writable.segment.start/end` (kind="think");phase = act → `writable.segment.start/end` (kind="act")。业务路径**不显式开段**。
- **phase** 是真窗口,由 `advance()` 控制。同 phase 重复调用 idempotent(返回同一 `CursorSnapshot`)。
- **iteration** 是外层重试(⊃ ADR-0095 iteration);`attempt_in_step` 是 step 内重试,二者独立计数。
- **fork()** 派生新 `LoopCursor`:新 cursor 继承 parent snapshot 的 `run_id / trace_id / incarnation`,`step_index` 与 `iteration` 各自重新计数;`incarnation` 由 D12 派生。

### D3 · 不变量(继承 ADR-0168.1 §D3,新增 L9-L15)

| 编号 | 内容 | 谁保证 | 验证 |
|---|---|---|---|
| L1 | 任何 `writable.step.*` EP 必有 begin/end 配对 | cursor (LLM hook + close) | grep events.jsonl 配对数 == begin 数 |
| L2 | `writable.segment.*` 同上 | cursor (phase 转移派生) | grep segments 配对 |
| L3 | `phase.*` EP 严格按 D2 转移图顺序 | cursor (非法 phase = CursorError) | 转移图单测 |
| L4 | 业务代码不 import EventSpine / Serializer / Storage / cursor.* (除 advance/record_*) | importlinter `business-event-isolation` + cursor surface | `uv run lint-imports` + cursor.isinstance 静态检查 |
| L5 | `record_*` 必在某个 phase 窗口开时调用 | cursor (不在窗口 = CursorError) | cursor 单测 |
| L6 | 任何 LLM 调用必在 step 内且必产生一次 `llm.request.header` EP | cursor (在 step 外调 raise;hook LLM adapter) | run 实测 + verify-model-visible |
| L7 | terminal flush 顺序:`关状态机 → flush coalescer → close storage → flush derivers → emit close EP → release` | `cursor.close()` 内部步骤编号 | unit test `terminalize_cursor_close_order` |
| L8 | iteration ⊃ ADR-0095 iteration;`attempt_in_step` 与 `iteration` 独立计数 | cursor 状态 | 单测覆盖二阶重试 |
| **L9** | `ProjectionDefinition` 是 projection 注册唯一入口;LiveTail 等任何"同时是 N 身份"的复合对象不允许 | cursor (`__init__` 唯一装配点)+ importlinter `projection-registration-single-entry` | static scan `lca/infrastructure/observability/spine/derivers/`:无 `spine.subscribe` 调用 (除 `__init__`) |
| **L10** | `events.jsonl` 写入路径唯一:`spine.sink.file` 单写;`writable.matrix.default.storage` 默认文件名改为 `<run_id>.spine.jsonl` (与 events.jsonl 物理分离) | `bundles/spine-default.yaml` 修订 + integration test | `grep` events.jsonl 行数 = spine.append 次数 (1:1) |
| **L11** | LLM 边界只 emit spine EP,不再写旧 journal `LlmCallStarted/Completed`;`TelemetryLLMAdapter._record` 改为 `cursor.record_request_header` | adapter 重写 + cost projector 走 spine event | `grep LlmCallCompleted` 在 cognition/body/runtime = 0 |
| **L12** | `cordis` event name 完全由 `EventDescriptor` 派生;业务 / plugin 代码不直接 emit `ctx.emit('agent.*' / 'phase.*' / 'tool.*')` | importlinter `cordis-event-derivation` + reflector.source 强制 | runtime scan `ctx.emit('agent'` / `ctx.emit('phase'` = 0 |
| **L13** | `CursorError` 不允许静默 fallback;`NullLoopCursor` 不存在 (测试用 `InMemoryLoopCursor` 替代) | `lca/runtime/loop_cursor/__init__.py` 不导出 NullLoopCursor | `grep NullLoopCursor` = 0 in lca/ |
| **L14** | `incarnation` 显式身份 = `(run_id, plan_ref, incarnation_seq)`;`plan_ref` 变更自动 bump `incarnation_seq` | cursor.snapshot.incarnation 派生 + ADR-0092 ledger 兼容 | journal envelope 100% 携带 incarnation 字段 |
| **L15** | `journal format refusal` 方向感知:`> SCHEMA_VERSION` ⇒ "新 harness,upgrade";`< SCHEMA_VERSION` ⇒ "no upgrade path" | `JournalFormatError` 子类化 (`VersionTooOld` / `VersionTooNew` / `UnknownEventType`);`read_journal` / `RunManifest.__post_init__` 分别 raise | unit test 覆盖 3 子类型 |

### D4 · Payload(frozen dataclass,继承 ADR-0168.1 §D4)

```python
# lca/contracts/observability/loop_cursor_payloads.py (新建)

@dataclass(frozen=True)
class ThinkingRecord:
    content_digest: str
    content_path:   str | None
    token_count:    int | None
    thinking_kind:  Literal["reasoning", "final_response", "compaction"]

@dataclass(frozen=True)
class ToolCallRecord:
    tool_name:        str
    args_digest:      str
    args_payload_path: str | None
    call_seq:         int            # cursor 内自增

@dataclass(frozen=True)
class ToolResultRecord:
    tool_name:     str
    result_digest: str
    result_path:   str | None
    outcome:       Literal["ok", "failure", "timeout", "denied"]

@dataclass(frozen=True)
class RequestHeader:
    """cursor 注入 step_id / incarnation;业务路径不能填。"""
    step_id:             str
    incarnation:         int
    reason:              Literal["initial", "next_step", "series", "change", "inherited"]
    model:               str
    system_digest:       str
    system_path:         str
    tools_digest:        str
    tools_path:          str
    messages_digest:     str
    messages_path:       str
    manifest_digest:     str
    manifest_path:       str
    inherited_from_step: str | None = None
```

**关键**:所有 `*_path` 字段是 `EvidenceRef` 的内容寻址位置(D14 / ADR-0065 L5);`step_id` 与 `incarnation` 不让业务路径填,cursor 注入。这条结构性禁掉"在错的 step / 错的 incarnation 里吐 fake 记录"。

### D5 · L7 close 顺序(继承 ADR-0168.1 §D5 + D18 集成)

```text
cursor.close(reason) 走五步,顺序不可颠倒:

  1. 关状态机 (L7-1)
       ├─ advance('stop') 完成;当前 step/segment/phase 窗口 emit window_end
       └─ 后续 record_* / advance 抛 CursorError

  2. flush writable faces (L7-2 / L7-3)
       ├─ coalescer.flush()           # D11 一致性:所有 step.thinking.record 入盘
       └─ storage.close()             # spine.sink.file 同步刷盘

  3. flush projections (D7 唯一装配)
       ├─ step_tree_deriver.flush()        → journal.json
       ├─ narrative_writer.write(document) → journal.narrative.md
       ├─ graph_deriver.flush()            → phase_graph.dot
       ├─ otel_deriver.dump()              → otel_export.jsonl  (可选,profile 选)
       └─ cost_projector.write()           → cost.json  (D11 一致性)

  4. emit 'writable.iteration.close' EP (L7-5,带 reason)
       └─ 这是最后一次写入 events.jsonl

  5. release
       ├─ unhook LLMCallHook
       ├─ clear ContextVar (loop_cursor)
       └─ snapshot freeze ("closed")
```

异常路径(`error` / `halt → close` / 重复 `close`)见实施计划 §3.2。**close 顺序硬编码在 `StdLoopCursor.close()`,`terminal.materialize` 退化为调用 `cursor.close()`**(继承 ADR-0168.1 §迁移 PR-7)。

### D6 · 装配入口单一 — StdLoopCursor.__init__ 是 spine / projection / persistence / LLM hook 的唯一装配点

```python
# lca/runtime/loop_cursor.py (新建,替代 ADR-0168 计划的 lca/runtime/loop_step_control.py)

@dataclass
class StdLoopCursor:
    """默认实现。持有 Spine 写路径 + ProjectionRegistry + PersistenceCoordinator + LLMCallHook。"""

    _run_id:       str
    _trace_id:     str
    _incarnation:  int                       # D12
    _spine:        EventSpine                # 唯一 SSOT 写入点
    _projections:  LoopProjectionRegistry    # D7 唯一注册入口
    _persistence:  PersistenceCoordinator    # D9 唯一物化入口
    _llm_hook:     LLMCallHook               # D11 一致性强制
    _model_visible: ModelVisibleRecorder     # 5 件套 (model_visible/step_NN/)
    _state:        _CursorState              # 转移图状态

    # 实现 D1 Protocol + D5 L7 顺序

    # D7 唯一装配入口
    @classmethod
    def from_run_session(
        cls,
        *,
        run_id: str,
        trace_id: str,
        spine: EventSpine,
        registry: LoopProjectionRegistry,
        persistence: PersistenceCoordinator,
        llm_hook: LLMCallHook,
        model_visible: ModelVisibleRecorder,
        incarnation: int = 1,
    ) -> "StdLoopCursor": ...

    def attach(self) -> Token: ...           # 注入 ContextVar (取代 bind_current_coordinator)
    def detach(self, token: Token) -> None: ...
```

**装配边界**:
- `RunSessionBuilder.build` (transport `session/builder.py`) **不再** 构造 `StepCoordinator`、**不再** subscribe deriver、**不再** bind LLM hook。改为:解析 cursor → 调 `StdLoopCursor.from_run_session(...)`。
- `RunExecutionEnvironment.prepare` (transport `execute/execution_environment.py`) **不再** 调 `bind_current_coordinator`、**不再** 嵌套 12 个 `bind_*`。改为:解析 cursor → 调 `cursor.attach()` → yield prepared run。
- `lca_kernel/observability.py` K5 装配阶段:除 baseline `install_observability` 外,**新增** `_install_loop_cursor_factory(ctx)` 暴露 `loop_cursor_factory` capability。
- `lca_kernel/boot.py` K3 fiber 启动阶段:不构造 cursor(fiber 启动先于 run);cursor 在 `RunSessionBuilder.build` 时构造。

### D7 · LoopProjectionRegistry 是 projection 唯一注册入口(D1 落地)

```python
# lca/contracts/observability/loop_projection.py (新建)

class LoopProjectionDefinition(Protocol):
    """Cursor 维度的纯 reducer (继承自 contracts/harness/state/projection.py ProjectionDefinition)。
    与 dsh `ProjectionDefinition<K,S>` 对齐;cursor 是事件源,projection 是订阅者。"""
    key:     str
    version: int
    def init(self) -> Any: ...
    def apply(self, state: Any, snapshot: CursorSnapshot, record: EventRecord) -> Any: ...
    def view(self, state: Any) -> Any: ...

class LoopProjectionRegistry(Protocol):
    def register(self, definition: LoopProjectionDefinition) -> Token: ...   # Token = disposer

    def drive(self, snapshot: CursorSnapshot, record: EventRecord) -> None: ...

    def snapshot(self) -> dict[str, Any]: ...

    def subscribe_changes(self, listener: Callable[[dict[str, Any]], None]) -> Token: ...

    def restore(self, *, base_seq: int, header: "SessionHeader", cut: int) -> None: ...
```

**关键**:
- `register()` 返回 `Token` (disposer) — 这是 `ctx.effect()` 模式。卸载 plugin 自动从 snapshot 中消失。
- `drive(snapshot, record)` 由 `StdLoopCursor._drive_projections` 内部调用 — 业务路径不接触。
- `restore(base_seq, header, cut)` 是冷读核心:checkpoint + suffix tail replay → 一致 snapshot(继承 ADR-0063 §D11)。

**与现有 ProjectionRegistry 的关系**:
- `lca/contracts/harness/state/projection.py::ProjectionDefinition` 保留(它是 session 维度的 projection),**不删**。
- 新增 `LoopProjectionDefinition` (loop 维度),两者并存。LiveTail 等"四身份"复合对象通过 `LoopProjectionDefinition` 重写,`on_event` 直接接收 `EventRecord`,不再转 `StampedEvent`(修 inventory §11-7 EP 名丢失 bug)。

**默认注册清单**(由 `StdLoopCursor.__init__` 一次性订阅,业务路径不可见):
- `StepTreeAccumulatorDeriver` → journal.json
- `NarrativeDeriver` → journal.narrative.md
- `GraphDeriver` → phase_graph.dot
- `OtelTraceDeriver` → otel_export.jsonl (profile 选)
- `LiveTailDeriver`(重写,接 `EventRecord`)→ SSE
- `CostProjector` → cost.json
- `AnomalyDetector` → diagnostic

**删除 LiveTail 四身份**:新 `LiveTailDeriver` 只接 `EventRecord`,只做 ring buffer;pub/sub 与 SSE 走 `subscribe_changes` 派生。**注释 `live_tail.py:7-10` 自承的"双轨残留"删除**。

### D8 · PersistenceCoordinator 是持久化唯一入口(D9 落地)

```python
# lca/runtime/persistence_coordinator.py (新建)

class PersistenceCoordinator(Protocol):
    """Loop 维度的持久化协调者。Cursor.close() 内部唯一调用入口。"""
    def flush(self) -> None: ...             # coalescer.flush() + storage.flush()
    def close(self) -> None: ...             # 物理 close
    def restore(self, *, run_id: str, from_seq: int) -> Iterator[EventRecord]: ...   # 流式

    @property
    def stats(self) -> PersistenceStats: ...
```

**职责单一**:
- `coalescer` / `storage` (来自 writable matrix 五面 D11) 由 coordinator 持有,不暴露给业务。
- deriver / projector 写 `journal.json` / `narrative.md` / `phase_graph.dot` 不在 coordinator 内 — 它们是 D7 的 projection,**不** 是 persistence。persistence 只管 `events.jsonl` 的事件流。
- `restore(from_seq)` 是 `read_journal` 的流式版(inventory §11-9 全量加载问题的解)。

**当前 `journal/engine/engine.py::RunStore` (即 RunLedger)**:
- 保留作为 ledger 实现(L1/L2/L3/L7 不变 — ADR-0065)。
- **删除** 旧 49 类 `JournalEvent` 走 RunStore 的入口 — 改为 EventSpine append 派生 RunLedger.append (L1 一致性保证)。
- 旧 `events.jsonl` 物理文件保留 schema=`lca.journal/2` envelope (D15 方向感知)。

### D9 · deriver 装配点合并进 cursor(D7 + D8 集成)

| 现行装配点 | 文件:行 | 在本 ADR 下 |
|---|---|---|
| `RunSessionBuilder.subscribe step_tree` | `session/builder.py:118` | 删 — `StdLoopCursor.__init__` 统一装配 |
| `RunSessionBuilder.bundle.field-replace deriver` | `session/builder.py:129-141` | 删 — cursor 持有 deriver 引用 |
| `bundles/spine-default.yaml` 19 plugin | `bundles/spine-default.yaml:28-51` | 缩 — `loop_cursor.spine_default` 一个 bundle 含 cursor factory + 默认 deriver 注册 |
| `bundles/spine-benchmark-minimal.yaml` | — | 缩 — `loop_cursor.spine_minimal` |
| `bundles/spine-oii-debug.yaml` | — | 缩 — `loop_cursor.spine_debug` |
| `EventSpine.__init__(subscribers=)` | `event_spine.py:43-48` | 删 — deriver 走 `LoopProjectionRegistry`,spine 不再持 subscribers |

**`spine-default.yaml` 重写**(实施计划 §4.1):
- 1 个 `loop_cursor.spine_default` bundle:含 `loop_cursor_factory` capability + 默认 deriver 6 个 + 默认 LLM hook + 默认 persistence 配置。
- spine core / reflectors / classifiers / sinks 改为 cursor factory 内部子组件(不再作为 plugin)。

### D10 · `record_*` 必在 phase 窗口开时才能调(L5 强制)

继承 ADR-0168.1 §L5,扩 payload 类型:

| `record_*` | 合法 phase 窗口 | 非法时行为 |
|---|---|---|
| `record_thinking` | think | `CursorError` |
| `record_tool_call` | act | `CursorError` |
| `record_tool_result` | act | `CursorError` |
| `record_request_header` | 任意 | `CursorError` if cursor.closed |

**继承自 ADR-0168.1 §L5 的新增**(本 ADR 强化):同一 phase 内可多次 `record_*` (与现行 StepCoordinator 行为一致);`record_tool_call` 后 `record_tool_result` 是默认 pairing,不强制 1:1(允许多 call → 1 result via `ToolCallRecord.call_seq`)。

### D11 · durability 分档的 write-behind + act 前强制 flush

继承 dsh `checkpoint-policy` 思路,在 cursor 实现:

```python
# lca/contracts/observability/loop_cursor_durability.py (新建)

Durability = Literal["required", "best_effort"]

@dataclass(frozen=True)
class FlushPolicy:
    durability: Durability
    flush_before: tuple[Literal["llm_request", "tool_execute", "phase_advance", "iteration_close"], ...]

# StdLoopCursor 内部:
def _maybe_flush_before(self, hook: Literal["llm_request", "tool_execute", ...]) -> None:
    if "llm_request" in self._flush_policy.flush_before:
        self._persistence.flush()
    # record_request_header 内部: 先 _maybe_flush_before("llm_request") 再落 EP

def record_request_header(self, header: RequestHeader) -> None:
    self._maybe_flush_before("llm_request")  # ← 关键
    self._state.inject_step_id(header.step_id, self.snapshot.incarnation)
    self._spine.append(execution_point="llm.request.header", payload=asdict(header), ...)
    self._model_visible.record_header(header.step_id, header)
    # ...

def record_tool_call(self, payload: ToolCallRecord) -> None:
    self._maybe_flush_before("tool_execute")  # ← 关键
    ...
```

**ControlSlot 新增**(v4 §5.1 白名单扩 2 项):

| slot | 挂载点 | 行为 |
|---|---|---|
| `act.constrain.flushed-journal-before-tool` | `tool.execute` waterfall 前 | 校验 `cursor.persistence.flush()` 已同步 |
| `act.constrain.flushed-journal-before-llm` | `llm.request` waterfall 前 | 同上 |

`StdLoopCursor.from_run_session` 默认装配这两 slot(profile 可关);违反时 `CursorError`。

**`required` vs `best_effort` 分档**:
- `required` 事件(`llm.request.header`、`writable.iteration.close`、`step.*.record`、`phase.*.fold`)→ 强制 flush before next phase
- `best_effort` 事件(`llm.stream.token`、`exception.caught` 等高频)→ 批写窗口(默认 50ms,profile 可调)

### D12 · incarnation 显式身份

继承 ADR-0065 L3 + ADR-0092 的"replay decisions require the original receipt sequence",升格为显式身份:

```python
# lca/contracts/observability/incarnation.py (新建)

@dataclass(frozen=True)
class Incarnation:
    """Session 显式身份。plan_ref 变更或 explicit fork() → incarnation_seq++。"""
    run_id: str
    plan_ref: str          # 当前 plan 引用
    incarnation_seq: int   # 单调递增,1 起

# cursor 派生:
@property
def snapshot(self) -> CursorSnapshot:
    return CursorSnapshot(
        ...,
        incarnation=self._incarnation.incarnation_seq,
        ...
    )

# 写事件时自动携带:
def record_thinking(self, payload: ThinkingRecord) -> None:
    payload_with_inc = replace(payload, incarnation=self._incarnation.incarnation_seq)
    self._spine.append(execution_point="step.thinking.record", payload=asdict(payload_with_inc), ...)
```

**与 ADR-0168.1 §"不在本 ADR 范围 - fork() 实装"的整合**:`fork()` 现实现,完整继承 parent `Incarnation.run_id + plan_ref`,新 `Incarnation.incarnation_seq = parent + 1`。**填了 ADR-0168.1 §"不在本 ADR 范围" 清单第 6 项**。

**与 ADR-0095 iteration 的关系**:`incarnation` 是"计划维度"身份(plan_ref 变了);`iteration` 是"尝试维度"计数(同 plan 重试)。`CursorSnapshot.iteration` 与 `CursorSnapshot.incarnation` 正交。

### D13 · journal envelope 方向感知格式拒绝(D15 收紧)

继承 `lca/contracts/harness/tasks/session.py:11` 的 `SESSION_FORMAT_VERSION = 1` 精确等于,扩方向感知:

```python
# lca/contracts/observability/journal_format_errors.py (新建)

class JournalFormatError(ValueError):
    """journal envelope 格式错误的根。"""

class VersionTooOld(JournalFormatError):
    """读到的 envelope.schema < 当前 SESSION_FORMAT_VERSION → 不接受升级路径。"""

class VersionTooNew(JournalFormatError):
    """读到的 envelope.schema > 当前 SESSION_FORMAT_VERSION → 需要升级 harness。"""

class UnknownEventType(JournalFormatError):
    """envelope 携带未知 event_type 且 ignorable != true → 拒读(不静默)。"""

# SessionHeader.__post_init__ 改:
def __post_init__(self) -> None:
    if self.version > SESSION_FORMAT_VERSION:
        raise VersionTooNew(...)
    if self.version < SESSION_FORMAT_VERSION:
        raise VersionTooOld(...)
    # 精确等于 = 通过

# JournalRecord.deserialize 改:
def deserialize(raw: dict) -> "JournalRecord":
    if raw["schema"] > SCHEMA_VERSION:
        raise VersionTooNew(...)
    if raw["schema"] < SCHEMA_VERSION:
        raise VersionTooOld(...)
    event_type = raw["event_type"]
    if event_type not in KNOWN_SESSION_EVENT_TYPES:
        if not raw.get("ignorable"):
            raise UnknownEventType(...)
    ...
```

**配套**:`KNOWN_SESSION_EVENT_TYPES`(`scripts/gen-persistence-catalog.ts` 生成的 close-set)与 `EXECUTION_POINTS` close-set 在 build 时 lockstep 校验 — 不可漂移。

### D14 · cordis 双词表收口(取代 AGENTS.md §3 的 "events ≠ cordis events" 注释)

**当前状态**(AGENTS.md §3):
> 使用现有 `cordis.Context` 的服务、事件、scope 和 dispose,不创建模块级单例或迁移期平行 schema。

这条注释留下真实债 — inventory §11 + 日志评估 §一-59/§一-83/§一-32 暴露:`event_bus.py` 整模块还活着 / `run_narrative.py` 自我陈述"journal 已替代" / `make_journal_emitting_hook` 的 waterfall 与 EventBus 同义。

**决策**:cordis 不再是平行词表。`ctx.emit(event_name)` 的 `event_name` 必须由 `EventDescriptor` 派生;业务 / plugin 代码不直接 emit `ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')`。

**实现**:
```python
# lca/contracts/observability/event_descriptor.py (扩)
@dataclass(frozen=True)
class EventDescriptor:
    name: str                                  # canonical name, e.g. "writable.step.start"
    cordis_name: str | None                    # None = 不暴露给 cordis (走 spine only)
    ...

# spine-default.yaml:cordis_translation:
#   writable.step.start: None      # 不走 cordis
#   llm.request.header: "llm.request.header"  # 走 cordis (供 hook 订阅)
#   phase.act.fold.start: "phase.act.fold"    # 走 cordis (供 live_tail)

# lca/infrastructure/observability/spine/event_spine.py::append 改:
def append(self, *, execution_point, ...):
    descriptor = self._registry.require(execution_point)
    ...
    # emit 到 cordis 仅当 descriptor.cordis_name is not None
    if descriptor.cordis_name and self._ctx:
        self._ctx.emit(descriptor.cordis_name, snapshot=..., record=...)
```

**删除**:
- `lca/infrastructure/observability/events/event_bus.py` 整模块
- `lca/infrastructure/observability/narrative/run_narrative.py`(已在日志评估 2026-09-02 修正标"待删",本 ADR 落地)
- `lca/runtime/event_emission.py::make_journal_emitting_hook` (D1 已列)
- `lca/plugins/observability/spine/wraps/ctx_emit.py`(若存在)

**保留**:`cordis` 作为 transport(boot / fiber / service registry),不再作为事件词表。`ctx.effect()` / `ctx.inject()` / `ctx.dispose` 不变。

### D15 · facade.* 与 coord.* 一次性删除(无 deprecation 兼容)

**理由**:用户指示"任何未决都不留"+"不可能,必须都解"。`facade.step_open / step_close / step_record_*` 7 个方法(inventory §3.1)**无业务调用方**;`coord.begin_step / end_step / begin_segment / end_segment / record_thinking / record_tool_call / record_tool_result / record_reflect / record_span` 9 个方法**仅有 facade 自调用**。一次性删除比 deprecation 1 个版本更干净。

**删除清单**:
- `lca/infrastructure/observability/facade/facade.py:516-575` 全部 step API(7 个方法)
- `lca/infrastructure/observability/writable_matrix/coordinator.py:138-324` 的 `begin_step / end_step / begin_segment / end_segment / record_* / emit_phase / emit`(9 个方法 + `_mint_record` 内部函数改为 `_spine.append` 包装)
- `lca/runtime/event_emission.py` 整模块
- `lca/infrastructure/observability/adapters/adapters.py:99, 423-450` 的 `_open_think_step / _close_think_step / _record`(2 个方法),adapter 改为 `cursor.record_request_header`
- `lca/cognition/body/safe_executor.py:388-403` 的 `coord.emit` → `cursor.record_tool_call / record_tool_result`
- `lca/cognition/body/tool_journal_emit.py:141, 179, 275` 的 `coord.emit` → `cursor.record_tool_call / record_tool_result`
- `lca/cognition/perceive_hub.py:93, 116, 133` 的 `coord.emit_phase / record_runtime` → `cursor.advance('perceive')` + `cursor.record_thinking` (派生自 cognition body 的 perceiving 结果)
- `lca/infrastructure/observability/facade/projection_registry.py::publish`(若存在)→ `LoopProjectionRegistry.drive`
- `lca/plugins/transport/webserver/handlers/runs/session/builder.py:118-141` 的 step_tree subscribe + bundle.field-replace
- `lca/plugins/transport/webserver/handlers/runs/execute/execution_environment.py:128-141` 的 bind_current_coordinator + bind_backends + bind_descriptors(capability 注入合并进 cursor.attach())

**保留**:`facade.record / facade.score / facade.annotate / facade.span / facade.detached_span / facade.traced / facade.record_runtime / facade.record_operation` 等通用 facade(非 step 范畴),不删。

### D16 · profile 装配全集(7 profile 全部覆盖)

继承 plan §P7(6 个 profile 缺 EventSpine 装配),扩为全部 9 profile:

| profile | 当前 | 本 ADR 下 |
|---|---|---|
| `web-standard.yaml` | spine-default ✅ | `loop_cursor.spine_default` |
| `oii-debug.yaml` | spine-default ✅ | `loop_cursor.spine_debug` |
| `benchmark.yaml` | spine-benchmark-minimal ✅ | `loop_cursor.spine_minimal` |
| `web-standard-recovery.yaml` | declarative-recovery(无 spine) | `loop_cursor.spine_recovery` (新 bundle, recovery-aware cursor) |
| `web-standard-continuous.yaml` | continuous-control-plane(无 spine) | `loop_cursor.spine_continuous` (新 bundle, 持续控制平面 cursor) |
| `cordis-creator.yaml` | scenario-cordis-creator(无 spine) | `loop_cursor.spine_cordis` (新 bundle, 与 cordis 双词表收口配套) |
| `self-improving-minimal.yaml` | 无 spine | `loop_cursor.spine_minimal` |
| `genai-traced.yaml` | observability-default + genai-telemetry | `loop_cursor.spine_genai` (新 bundle, GenAI 语义) |
| `coding-agent.yaml` | observability-default + coding-agent-tools | `loop_cursor.spine_coding` (新 bundle, coding 适配) |
| `test-minimal.yaml` | base + web-app(无 spine) | `loop_cursor.spine_minimal` |

**新增 6 个 bundle**:每个 profile 一个 cursor 配置 bundle。**填了 ADR-0168.1 §"不在本 ADR 范围" 清单第 5 项**。

### D17 · kernel(K5) 装配收敛

继承 `lca_kernel/observability.py` K5 现有装配,新增 cursor factory:

```python
# lca_kernel/observability.py:50-80 扩
def install_observability(ctx) -> BoundObservability:
    bound = assemble_observability(ctx, ObservabilitySettings())
    ctx.provide("observability", bound)
    # NEW: cursor factory (D6)
    ctx.provide("loop_cursor_factory", _build_cursor_factory(ctx, bound))
    return bound

# lca_kernel/boot.py:207-298 不动(cursor 在 transport 构造,不进 boot)
```

**CursorFactory 行为**:
```python
class LoopCursorFactory(Protocol):
    def from_run_session(self, *, run_id: str, trace_id: str, plan_ref: str,
                         run_dir: Path, metadata: dict) -> LoopCursor: ...
```

`from_run_session` 内部:`Incarnation(run_id, plan_ref, 1)` + 解析 `LoopProjectionRegistry` + `PersistenceCoordinator` + `LLMCallHook` + `ModelVisibleRecorder`,**一次性装配 cursor**。

### D18 · terminal.materialize 退化为 cursor.close()

继承 ADR-0168.1 §迁移 PR-7 + D5 close 五步:

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/materialization.py (重写)

def record_terminal_materialization(session) -> MaterializationReport:
    cursor = require_capability(ctx, "loop_cursor")  # 由 builder 注入
    cursor.close(reason=_journal_outcome_from_session(session))  # ← 唯一入口

    # manifest / latest pointer 等元数据落盘(非 loop 事实)
    locator = FilesystemRunLocator(...)
    manifest = RunManifest.from_session(session)
    manifest_path.write_text(manifest.to_json())
    locator.update_latest_pointer(session.run_id)

    return MaterializationReport(manifest=manifest, flush_errors=[])
```

**删除**:`materialization.py:32-94` 的 `_flush_step_tree` / `bundle.flush` / `narrative_writer.write` 三段 — cursor.close() 内部已完成。

### D19 · 验证矩阵

继承 ADR-0168 §验证 + 扩展:

```bash
# 1. 状态机单元 (D1 + D2)
uv run pytest tests/observability/test_loop_cursor.py -v
uv run pytest tests/observability/test_loop_cursor_transitions.py -v
# 转移图 12 边 100% 覆盖 + payload 7 dataclass 100%

# 2. close 顺序 (D5)
uv run pytest tests/observability/test_cursor_close_order.py -v
# L7-1 ~ L7-5 顺序断言

# 3. 不变量断言 (D3 L1-L15)
uv run pytest tests/observability/test_cursor_invariants.py -v
# L1-L15 每条 1+ test method

# 4. 装配边界 (D4 / D6 / D9)
uv run lint-imports                                    # business-event-isolation (L4)
uv run python scripts/check_cursor_assembly.py        # L9 projection 唯一入口
uv run python scripts/check_writable_matrix_boundaries.py  # L10 events.jsonl 单写
uv run python scripts/check_cordis_event_derivation.py     # L12 cordis 双词表收口

# 5. Schema 演进 (D13)
uv run pytest tests/observability/test_journal_format_errors.py -v
# VersionTooOld / VersionTooNew / UnknownEventType 三子类型

# 6. Incarnation (D12)
uv run pytest tests/observability/test_incarnation_identity.py -v
# plan_ref 变更 → incarnation_seq++ + envelope 携带

# 7. ControlSlot (D11)
uv run pytest tests/observability/test_flushed_journal_slots.py -v
# 违 slot = CursorError

# 8. Snapshot replay CI 不依赖 API key (D19)
uv run pytest tests/replay/test_snapshot_replay_no_api_key.py -v
# 输入 captured events.jsonl + plan_ref, 输出 TraceInspector.report
# golden fixture diff (不调 LLM)

# 9. Profile 装配 (D16)
uv run pytest tests/profiles/test_all_profiles_have_cursor.py -v
# 9 profile 全部含 loop_cursor bundle

# 10. 集成 run (D1-D18 全链路)
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)

# 验证点必须全部满足:
grep -c "writable.step.start"     traces/runs/$LATEST/events.jsonl   # ≥ 1
grep -c "writable.step.end"       traces/runs/$LATEST/events.jsonl   # = begin 数
grep -c "writable.iteration.close" traces/runs/$LATEST/events.jsonl  # = 1
grep -c "LlmCallCompleted"        traces/runs/$LATEST/journal.json   # = 0 (D11-1 落地)
wc -l                            traces/runs/$LATEST/events.jsonl   # = spine.append 次数 (L10)
jq ".steps | length"              traces/runs/$LATEST/journal.json   # ≥ 1
jq ".steps[].incarnation"         traces/runs/$LATEST/journal.json   # 全部携带 (D12)
ls traces/runs/$LATEST/phase_graph.dot                          # 存在
ls traces/runs/$LATEST/model_visible/step_*/request-header.json # ≥ 1
ls traces/runs/$LATEST/cost.json                                # 存在 (D11)
jq ".events[].schema"             traces/runs/$LATEST/events.jsonl # 全部 = "lca.journal/2" (D13)

# 11. 死代码清理 (D14 + D15)
uv run vulture lca --min-confidence 80      # event_bus / run_narrative / facade.step_* / coord.begin_step 全为 0
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports

# 12. Real-LLM 集成(可选)
DEEPSEEK_API_KEY=... uv run pytest -m real_llm -v --run-id-prefix cursor-final

# 13. Snapshot replay (D19)
uv run pytest tests/replay/ -v
# 不依赖 API key,纯 replay
```

### D20 · 阶段化实施(三阶段)

按"架构优雅 + 实施分阶段"原则(用户指示"都要"):

**Phase 1 · LoopCursor 控制面收敛** (~5 PR)
1. PR-1: 新建 `LoopCursor` Protocol + payload dataclass + 转移图单元测试
2. PR-2: `StdLoopCursor` 默认实现 + 装配入口 + LLM hook 注入
3. PR-3: 业务路径迁移 (safe_executor / tool_journal_emit / perceive_hub / TelemetryLLMAdapter / event_emission)
4. PR-4: 删除 facade.step_* / coord.begin_step / event_emission (D15)
5. PR-5: Profile 装配全集 (D16, web-standard + oii-debug + benchmark)

**Phase 2 · 投影与持久化收敛** (~4 PR)
6. PR-6: `LoopProjectionRegistry` Protocol + 实现 + 默认注册清单 (D7)
7. PR-7: `PersistenceCoordinator` Protocol + 实现 + 流式 restore (D8)
8. PR-8: deriver 装配点合并进 cursor + spine-default.yaml 重写 (D9)
9. PR-9: events.jsonl 单写 + writable.matrix.default.storage 改名 (D10, L10)

**Phase 3 · 周边与硬化** (~4 PR)
10. PR-10: incarnation 显式身份 + journal envelope 携带 (D12)
11. PR-11: journal format refusal 方向感知 (D13)
12. PR-12: cordis 双词表收口 + 删 event_bus / run_narrative (D14)
13. PR-13: snapshot replay CI + 验证矩阵全面跑通 (D19)

**合计 ~13 PR,3 个 release cycle**(每 phase 1 cycle)。

## 不变量承接与新引入

| 既有 | 本 ADR 处理 |
|---|---|
| C1 闭集(认知闭环) | 不变;`PhaseName` 是 `Literal[...]`,编译期禁扩展 |
| C2 双平面 | 不变;cursor 是认知面的状态机,执行面仍只读 snapshot |
| C3 Journal | 不变;cursor 派生 EP,Journal 仍是 SSOT |
| C4 Reducer | 不变;reducer 只读 `snapshot`,不改它 |
| C5 能力衰减 | cursor.fork 内置 grant 校验 |
| C7 控制/观察分离 | **强化**:cursor 是 control face;event/trace/metrics/projection 不混进 cursor |
| I-PLUG1(业务不 import spine) | **强化**:cognition/body/runtime/agent 不 import `EventSpine`/`Serializer`/`Storage`/`cursor.*`(除 advance/record_*),只走 cursor Protocol |
| ADR-0063 Run Trace SSOT | 不变;`events.jsonl` 仍 SSOT,L10 强制单写 |
| ADR-0065 Recoverable Evidence Ledger | 不变;L1-L7 契约保持;`EvidenceRef` 内容寻址沿用 |
| ADR-0066 Step/Segment/Phase 三层计数 | **升级**:cursor 派生 step/segment/phase,业务不接触 |
| ADR-0093 Continuous Control Plane | 不变;`web-standard-continuous` profile 沿用 control plane cursor 实现 |
| ADR-0094 StopPolicy 局部性 | 不变;`halt(reason)` 入口保留 |
| ADR-0095 LoopGuard iteration | 不变;`iteration` ⊃ ADR-0095 iteration,L8 锁 |
| ADR-0164 Journal Step Tree | **升级**:step tree 由 cursor 派生,业务不接触 |
| ADR-0165(.1) Execution Point Enforcement | 不变;`EXECUTION_POINTS` close-set 锁;L15 与 journal format refusal 锁步 |
| ADR-0166 Step/Segment/Phase 三层计数 | **升级**:业务路径不接触 step/segment 边界 |
| ADR-0167 Spine 唯一耐久真值 | 不变;spine SSOT 保持;L10 强化单写 |
| ADR-0167.1 Step-Tree Deriver Wiring | **升级**:deriver 装配点合并进 cursor (D9) |
| ADR-0162 Fact vs Progress 准则 | 不变;cursor.record_* 落事实,CursorSnapshot 派生 progress |
| **新引入 I-CURSOR-1** | cursor.advance 是 phase 转移唯一入口;CursorError 不静默 fallback |
| **新引入 I-CURSOR-2** | snapshot 是 frozen + read-only;reducer / projection 不可改 |
| **新引入 I-CURSOR-3** | cursor.close 五步顺序硬编码;`terminal.materialize` 是 thin wrapper |
| **新引入 I-CURSOR-4** | cordis event name 由 EventDescriptor.cordis_name 派生;`ctx.emit('agent.*'...)` 业务禁止 |
| **新引入 I-CURSOR-5** | incarnation = (run_id, plan_ref, incarnation_seq);envelope 必携带 |

## 兼容性

按用户指示"D15 facade.* 与 coord.* 一次性删除(无 deprecation 兼容)" + "任何未决都不留":

**无 facade 兼容包装**:`facade.step_open` 等 7 个方法一次性删,无 `@deprecated` 包装。**理由**:inventory §3.1 + §9.1 证明这 7 个方法**无业务调用方**,deprecation 是负担而非保护。

**无 coord 兼容包装**:`coord.begin_step` 等 9 个方法一次性删。**理由**:`StepCoordinator` 是 cursor 内部组件,不外暴露;外部只能通过 `LoopCursor` Protocol 访问。

**双 envelope 兼容**:继承现行 ADR-0065 + ADR-0067:`StampedEvent` ↔ `JournalRecord` 兼容保留(过渡期);`migrate_v1_to_v2` 保留。

**schema 版本**:`SCHEMA_VERSION` 在 D13 升级为方向感知,不删除旧版本。

**Profile 兼容**:9 profile 全量迁移到 cursor bundle;profile YAML 不保留旧 spine-default bundle 引用(实施计划 §4.1 改名 `loop_cursor.spine_*`)。

## 删除条件

| 待删 | 条件 | 验证 |
|---|---|---|
| `facade.step_*` 7 个方法 | 全部删除(D15),无 deprecation | `grep facade.step_open` = 0 in `lca/` |
| `coord.begin_step / end_step / begin_segment / end_segment / emit_phase / emit` | 全部删除(D15) | `grep coord.begin_step` = 0 in `lca/` |
| `coord.record_thinking / record_tool_call / record_tool_result / record_reflect / record_span` | 全部删除(D15) | 同上 |
| `event_emission.py` 整模块 | 全部删除(D15) | 文件不存在 |
| `runtime/loop_step_control.py` | 不创建(被 `runtime/loop_cursor.py` 取代) | `ls lca/runtime/loop_step_control.py` 不存在 |
| `_derive_step_completed` | 删除 | `grep _derive_step_completed` = 0 |
| `_derive_action_degraded` | 转 adapter (D1) | 文件存在但仅含 thin wrapper |
| `make_journal_emitting_hook` | 删除 | `grep make_journal_emitting_hook` = 0 |
| `NullLoopCursor` | 不创建(L13) | `grep NullLoopCursor` = 0 |
| `bundles/spine-default.yaml` | 重命名为 `bundles/loop_cursor.spine_default.yaml` | bundle name 变更 |
| `bundles/spine-benchmark-minimal.yaml` | 重命名 `loop_cursor.spine_minimal.yaml` | 同上 |
| `bundles/spine-oii-debug.yaml` | 重命名 `loop_cursor.spine_debug.yaml` | 同上 |
| `live_tail.py` EP 名丢失(_to_stamped) | 重写为直接接 EventRecord (D7) | `grep _to_stamped` = 0 |
| `event_bus.py` | 删除(D14) | 文件不存在 |
| `run_narrative.py` | 删除(D14) | 文件不存在 |
| `writable.matrix.default.storage` 默认文件名 `events.jsonl` | 改为 `<run_id>.spine.jsonl` (L10) | integration test 验证 |
| `WritableFace.model_visible_recorder / replay_cursor` | 删除 FACE_NAMES 条目 (无默认实现) | `writable_matrix.py:108-114` 删除 |
| `coord.record_runtime` 在 cognition | 删除(D15) | `grep record_runtime` 在 cognition = 0 |
| 旧 journal `LlmCallStarted/Completed` 写路径 | 删除(D11-1) | `grep LlmCallCompleted` 在 cognition/body/runtime = 0 |
| `ProjectionRegistry.publish` | 删除(D7,合并进 LoopProjectionRegistry.drive) | grep = 0 |
| `JournalEvent` 49 类 (含 BootProfileResolved 等) | 保留 readonly dataclass(供反序列化);不再走 RunStore 写入 | `grep journal.write` = 0 in `cognition/body/runtime/agent` |

## 后果

### 正面

1. **修补序列终止**:ADR-0156~0168.1 的"漏 emit / emit 多 / emit 错时序"在结构上不可能 — 业务路径只看到 `advance(phase)` 与 `record_*(...)`,emit / subscribe / flush / close 全部由 cursor 派生。
2. **三面职责唯一**:control = cursor;projection = `LoopProjectionRegistry`;persistence = `PersistenceCoordinator`。无重叠,无 LiveTail 四身份。
3. **SPINE 单一写入**:`events.jsonl` 由 `EventSpine.append` 唯一写入(L10 强制单写)。
4. **业务路径不接触 spine / persistence / projection**:L4 + L9 + L10 锁,grep 验证为 0。
5. **terminal.materialize 退化为 thin wrapper**:D18 + D5 close 五步硬编码,胶水层消除。
6. **incarnation 显式身份**:D12 + D14 一致,replay 时 iteration 边界可重建。
7. **cordis 双词表收口**:D14,`event_bus.py` + `run_narrative.py` 删除,业务 / plugin 不直接 emit `ctx.emit('agent.*'...)`。
8. **格式拒绝方向感知**:D13,旧写新读 / 新写旧读分别给明确错误码,build 时锁步。
9. **9 profile 全部覆盖**:D16,新增 6 个 cursor 配置 bundle。
10. **snapshot replay CI 不依赖 API key**:D19-8,`tests/replay/test_snapshot_replay_no_api_key.py` 落地。

### 负面

1. **StdLoopCursor 是新增 SSOT,bug 影响范围大**;但比 hook 散弹好测,转移图 12 边全列出(D2),payload 7 dataclass 全 frozen(D4),close 5 步顺序硬编码(D5)。
2. **13 PR 跨 3 release cycle**:用户接受"架构优雅 + 实施分阶段"。
3. **删除 deprecation wrapper**:业务方若有外部调用(测试夹具、第三方插件)需同步迁移;**但 inventory 证明无业务调用方**,影响有限。
4. **cordis 收口可能破坏既有 plugin**:inventory §9.4 已证明 I-PLUG1 当前无违规,但 D14 要求 `EventDescriptor.cordis_name` 字段,既有 reflector 需补该字段(实施计划 §4.3)。

### 不在本 ADR 范围

**无**(用户指示"任何未决都不留"+"不可能,必须都解"):

- ❌ spine.deriver.metrics (Prometheus) → **本 ADR 范围内**(D7 默认注册清单可包含)
- ❌ 删 `journal.py` 49 事件类 → **本 ADR 范围内**(D15 改 readonly)
- ❌ spine.deriver.otel_trace plugin wrapper → **本 ADR 范围内**(D7 默认注册清单)
- ❌ OTel / Langfuse 投影路径 → **本 ADR 范围内**(D7 + D16 `loop_cursor.spine_genai` bundle)
- ❌ 6 个非 web-standard profile 的 spine 装配 → **本 ADR 范围内**(D16 全 9 profile)
- ❌ fork() 实装 → **本 ADR 范围内**(D1 + D12)
- ❌ halt 的 resume 协议 → **本 ADR 范围内**(D1 `halt(reason)` + D5 close 五步 `error` 路径覆盖)

## 引用

### Supersedes
- ADR-0168 §决策段 (`docs/adr/0168-loop-step-control-and-model-visible.md:D1-D11`)
- ADR-0168.1 §决策段 (`docs/adr/0168.1-loop-cursor-state-machine.md:D1-D6`)
- ADR-0168.1 §迁移表 (PRD → ADR-0168-final)

### Cross-reference (不 supersede,继续有效)
- ADR-0063 Run Trace SSOT
- ADR-0065 Recoverable Evidence Ledger
- ADR-0066 Step / Segment / Phase 三层计数与 Spine 硬化
- ADR-0068 Compiled Plugin Kernel 与 Unified Run Plan
- ADR-0088 Profile-selected Runtime Factory
- ADR-0089 Composable Phase Observation
- ADR-0090 Session Turn Task Controller
- ADR-0091 Profile-selected Followup Dispatch
- ADR-0093 Continuous Control Plane
- ADR-0094 StopPolicy 局部性
- ADR-0095 LoopGuard 局部性
- ADR-0162 Fact vs Progress 准则
- ADR-0164 Journal Step Tree
- ADR-0165(.1) Execution Point Enforcement
- ADR-0167 Spine 唯一耐久真值、Step 物化视图与 Model-Visible 轨迹组织
- ADR-0167.1 Step-Tree Deriver Wiring 与 Run Layout 收尾

### 保留
- ADR-0168 §背景段(问题陈述与现状盘点)

### 实施计划
- `docs/plans/2026-09-02-loop-cursor-final/main.md`(由 writing-plans 输出)
