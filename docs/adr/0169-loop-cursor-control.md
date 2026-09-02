# ADR-0169: LoopCursor 控制面收敛 — 与观测装配分离

## 状态

**Accepted — 2026-09-02**

> **实施状态(2026-09-02)**: 五缝文件全部落地(`StdLoopCursor` /
> `StdProjectionHost` / `PersistenceCoordinator` / `ModelVisibleCapture` /
> `StdCloseBarrier`);``LoopCursorFactory.from_profile`` 公开;webserver
> :class:`RunSessionBuilder` 已切到 :class:`ObservabilityRuntime.from_profile`
> + :meth:`make_cursor`(回归锁:``tests/observability/loop_cursor/test_builder_runtime_wiring.py``)。
> step_tree_deriver 仍走 ``event_spine.subscribe``(0167 既有契约;0170 deriver
> migration 不在本 PR 范围)。
> **Supersedes**: ADR-0168 决策段、ADR-0168.1 决策段、ADR-0168-loop-cursor-final 全文。
> **保留**: ADR-0168 §背景段(问题陈述与现状盘点);ADR-0168.1 §转移图 / §Payload / §不变量 L1-L8 全部继承并按本 ADR 重新挂点。
> **评审回应**: 评审 `docs/reviews/2026-09-02-adr-0168-final-review.md` 山姆「Conditional Go」三条总判全部纳入；剩余 17 项潜在问题 / 10 条 ADR 评审检查单详见 §10「评审点逐条消化」附录。

## 一句话

把 LCA loop 控制面进一步收敛为 **`LoopCursor` Protocol**,业务路径只允许两件事 —— `advance(phase)` 与 `record_*(...)`。**与 ADR-0168-final 的关键差异**:不再把"投影 / 持久化 / LLM hook / model_visible 装配"塞进 `StdLoopCursor`,而是拆成五缝:**LoopCursor(控制)·ProjectionHost(投影)·PersistenceCoordinator(持久化)·ModelVisibleCapture(边界)·CloseBarrier(关闭屏障)**。修补序列 ADR-0156~0168-final 的"漏 emit / emit 多 / emit 错时序"在结构上不再可能;评审指出的"God Cursor / C7 自打脸 / Mega-ADR 美德化"被拆文与显式 follow-up 编号化解。

## 背景

ADR-0168-final 在 §2.4 自承"C7 控制/观察分离:强化 — cursor 是 control face;event/trace/metrics/projection 不混进 cursor",同时 §D6 `StdLoopCursor` 字段表却持有 `Spine 写路径 + ProjectionRegistry + PersistenceCoordinator + LLMCallHook + ModelVisibleRecorder`。评审判定这是**结构性回退**:把 RunSessionBuilder 的"上帝职责"原样搬进 `StdLoopCursor`,换皮不换病。

正确分解(评审 §2.2 + 行业对照 dsh / OTP / Kafka / Clean Architecture / OTel)——

| 关注点 | owner | 论证依据 |
|---|---|---|
| 真值流 | `EventSpine.append` | ADR-0063 SSOT、L10 单写 |
| 控制语义 | `LoopCursor` | phase / step / segment / iteration 状态机 |
| 投影 | `ProjectionHost.register(def) -> Token` | dsh `ProjectionDefinition`;第三方 deriver 零改 cursor |
| 持久化 | `PersistenceCoordinator.flush/close` | Kafka consumer group 解耦 |
| 模型可见 | `ModelVisibleCapture`(LLM 边界) | ADR-0167 I-MV1,真实捕获 |
| 关闭协同 | `CloseBarrier`(cursor 发 closing 信号) | OTP gen_statem ≠ subscriber |
| 装配 | `ObservabilityRuntime.from_profile` | ADR-0088 profile-selected factory |

**「派生」= 因果派生**(advance → 自动 emit phase EP),**不是所有权吞并**(cursor 持有并 flush 一切)。这条原则被原 ADR 的字面 C7 与字面 D6 同时违反 —— 本 ADR 拆分后两边各得其所。

## 第一性原理与设计原则

### P1 · 真值流 = spine,owner 是它不是 cursor
ADR-0063 已经定 SSOT 在 `EventSpine.append`;cursor 只调用,不持有真值。

### P2 · 状态机和投影必须同时间派生,但不是同一对象持有
派生通过"同一事件流触发订阅者"实现(dsh 同构);不让同一字段表同时持 spine / registry / hook / recorder。

### P3 · 一文件一修改理由
扩展 cursor 等于扩展控制语义 → 白名单冻结;扩展投影走 ProjectionHost → 开集;两者边界硬分。

### P4 · 接口稳定,实现可替换
`LoopCursor` 是 Protocol;`StdLoopCursor` 是默认实现,profile 可替换 cursor 实现(对齐 ADR-0088)。

### P5 · 控制/观察分离是结构,不是约定
Snapshot `frozen=True`;observer 永远不可能"为了写日志而改 state";**结构性保证**,不靠 reviewer 自觉。

### P6 · 业务不碰 emit / subscribe / flush / close
业务路径只看到 `advance / record_* / halt / close / fork / snapshot`;emit / subscribe / flush / close 由 cursor 发信号、由 host/barrier 接管。

## 决策

### D1 · LoopCursor Protocol(冻结公共面 = 9 动词 + 1 snapshot)

```python
# contracts/observability/loop_cursor.py
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
    run_id:           str
    trace_id:         str
    incarnation:      int           # D6 显式身份
    step_id:          str | None
    step_index:       int           # 自增,从 1 起;iteration 内重新计数
    iteration:        int           # 外层重试(⊃ ADR-0095)
    attempt_in_step:  int           # step 内重试
    phase:            PhaseName | None   # None = OUTSIDE_LOOP
    iteration_reason: IterationReason | None
    stop_signal:      CloseReason | None
    seq:              int           # 当前事件 seq(ADR-0065 L3 一致性)


class CursorError(Exception):
    """非法转移 / 关闭后调用 / 跨窗口 record → raise,不静默 fallback。"""


class LoopCursor(Protocol):
    """Loop 控制面状态机(本 ADR)。
    业务路径唯一允许做的:
        - advance(phase)        : 转移 phase 窗口
        - halt(reason)          : 终止当前 iteration
        - close(reason)         : 关闭 cursor(发 closing 信号给 CloseBarrier)
        - record_thinking(...)  : 落 step.thinking.record EP
        - record_tool_call(...) : 落 step.tool_call.record EP
        - record_tool_result(...): 落 step.tool_result.record EP
        - record_request_header(...): 落 llm.request.header EP + 5 件套
        - fork(reason) -> LoopCursor  : subagent / delegation

    不暴露:
        begin_step / end_step / open_segment / close_segment
        emit_phase / emit / subscribe / flush / close_storage
        register_projection / subscribe_projection / drive_projection
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

**为什么是 9+1,不是 6 也不是 12**:继承自 ADR-0168.1 §D1 对照分析,逐条按"现行控制点 → 本 ADR 处理"对照表判定保留 / 收 / 删(见 §11 控制点迁移矩阵)。

**白名单纪律(评审 §7.5)**:控制动词闭集。任何新 "record_X" 默认问题:**能否变成 spine EP + Projection?** 能则**禁止**扩 Protocol。

### D2 · 状态转移图(继承 ADR-0168.1 §D2)

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
                                  │ record_request_header      │
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

**step 语义钉死(评审 §7.6 选项 A,推荐)**:**step = 一次模型请求**;`record_request_header` 调用一次 = 一次 step 起点。无 LLM 的纯 perceive / tool-only / replay 路径,可能没有 step(只发 phase EP)。**用例表见 §9。**

**L10 修订(评审潜在 #17)**:L5 「record_request_header 任意 phase」**改为**「record_request_header 必在 THINK 窗口开时」——与 L8 不变量字面一致。`record_thinking` 仍在 think;`record_tool_call/result` 仍在 act;`record_request_header` 必触发 think 开窗。

### D3 · 不变量 —— 挂到正确 owner

| 编号 | 内容 | owner | 验证 |
|---|---|---|---|
| L1 | 任何 `writable.step.*` EP 必有 begin/end 配对 | LoopCursor (LLM hook + close) | grep events.jsonl 配对数 == begin 数 |
| L2 | `writable.segment.*` 同上 | LoopCursor (phase 转移派生) | grep segments 配对 |
| L3 | `phase.*` EP 严格按 D2 转移图顺序 | LoopCursor (非法 phase = CursorError) | 转移图单测 |
| L4 | 业务代码不 import EventSpine / Serializer / Storage | importlinter `business-event-isolation` | `uv run lint-imports` |
| L5 | `record_*` 必在某个 phase 窗口开时调用(THINK/ACT) | LoopCursor (不在窗口 = CursorError) | cursor 单测 |
| L6 | 任何 LLM 调用必在 step 内且必产生一次 `llm.request.header` EP | LoopCursor + ModelVisibleCapture | run 实测 + verify-model-visible |
| L7 | terminal close 顺序:`cursor 停 → flush persistence → flush projections → 发 close EP → release` | CloseBarrier | unit test `terminalize_cursor_close_order` |
| L8 | iteration ⊃ ADR-0095 iteration;`attempt_in_step` 与 `iteration` 独立计数 | LoopCursor 状态 | 单测覆盖二阶重试 |
| **L9** | **ProjectionHost.register(def) 是投影唯一注册入口** | **ProjectionHost** | static scan `lca/infrastructure/observability/`:无 `StdLoopCursor.host = ...` 或 `cursor.register_projection` |
| **L10** | **`events.jsonl` 由 `EventSpine.append` 唯一写入**;`writable.matrix.default.storage` 默认文件名改为 `<run_id>.spine.jsonl` | **Spine sink 配置 + CI** | integration test:events.jsonl 行数 = spine.append 次数 (1:1) |
| **L11** | **LLM 边界只 emit spine EP;`ModelVisibleCapture` 唯一接管 model_visible 5 件套** | **Capture 插件 + adapter** | `grep LlmCallCompleted` 在 cognition/body/runtime = 0 |
| **L12** | **cordis event name 必须由 `EventDescriptor` 派生**;业务不 emit `ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')` | **EventDescriptor + importlinter** | runtime scan `ctx.emit('agent'` / `ctx.emit('phase'` = 0 |
| **L13** | **CursorError 不允许静默 fallback**;`NullLoopCursor` 不存在(测试用 `InMemoryLoopCursor` 替代) | `lca/runtime/loop_cursor/` 不导出 NullLoopCursor | `grep NullLoopCursor` = 0 in `lca/` |
| **L14** | **`incarnation` 显式身份 = (run_id, plan_ref, incarnation_seq)**;journal envelope 必携带 | **LoopCursor + envelope** | journal envelope 100% 携带 incarnation 字段 |
| **L15** | **journal format refusal 方向感知**:`< SCHEMA_VERSION` ⇒ `VersionTooOld`;`> SCHEMA_VERSION` ⇒ `VersionTooNew`;未知 event_type 且 ignorable != true ⇒ `UnknownEventType` | **Journal 读写边界** | unit test 覆盖 3 子类型 |
| **L16** | **`writable.iteration.close` 只被 Persistence 消费**;ProjectionHost 不订阅(避免"最后一笔写完投影已关"竞态) | **CloseBarrier + ProjectionHost** | unit test:`subscribe('writable.iteration.close')` in ProjectionHost = 0 |

**结构变化**:**L9 / L10 / L11 / L12 / L14 / L16 不挂在 cursor**,而是挂在**真正负责的 owner**上;cursor 失重的"装配上帝"叙事从硬门禁里退掉。

### D4 · Payload(frozen dataclass,继承 ADR-0168.1 §D4)

```python
# contracts/observability/loop_cursor_payloads.py
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

**关键**:`step_id` 与 `incarnation` 不让业务路径填,cursor 注入;`system_*` / `tools_*` / `messages_*` 由 `ModelVisibleCapture`(ADR-0170) 写,`RequestHeader` 只持有 digest + relpath。

### D5 · L7 close 五步顺序(改动:执行者改为 CloseBarrier)

```text
cursor.close(reason) 走以下步骤,顺序由 CloseBarrier 协调:

  1. 关状态机
       ├─ advance('stop') 完成;当前 step/segment/phase 窗口 emit window_end
       └─ 后续 record_* / advance 抛 CursorError

  2. cursor:发 writable.iteration.closing 信号(EP)
       ├─ PersistenceCoordinator 接收 → 决定 flush 顺序
       └─ ProjectionHost 接收(注意:L16 不订阅 close EP,只订阅 closing EP)

  3. CloseBarrier 协调 flush:
       a. PersistenceCoordinator.flush()           # coalescer + sink
       b. ProjectionHost.flush_all()              # journal / narrative / graph / cost / otel
       c. (L16) writable.iteration.close EP 落在 3a 之后、3b 之前
            ← 钉死:close EP 被 persistence 写入 events.jsonl;
                     ProjectionHost 不订阅(防"投影已关"竞态)

  4. release
       ├─ cursor 端:unhook LLMCallHook + clear ContextVar + snapshot freeze
       └─ host 端:dispose 显式 Token(if any)
```

**关键改动 vs ADR-0168-final**:cursor.close **不再直接持有** PersistenceCoordinator / ProjectionHost 实例 —— 它只发 closing 信号,由 `CloseBarrier`(独立组件)协调 flush 顺序。Loose coupling,hot-swap friendly。

`terminal.materialize` 退化为 `cursor.close()` 的薄壳 —— 之前那段 `_flush_step_tree / bundle.flush / narrative_writer.write` 三段胶水全删(继承 ADR-0168-final §D18)。

### D6 · incarnation 显式身份

```python
# contracts/observability/incarnation.py
@dataclass(frozen=True)
class Incarnation:
    """Session 显式身份。plan_ref 变更或 explicit fork() → incarnation_seq++。
    与 ADR-0095 iteration 正交:incarnation 是「计划维度」身份;
                                  iteration 是「尝试维度」计数。"""
    run_id:          str
    plan_ref:        str
    incarnation_seq: int   # 单调递增,从 1 起

# cursor 派生:
@property
def snapshot(self) -> CursorSnapshot:
    return CursorSnapshot(
        ..., incarnation=self._incarnation.incarnation_seq, ...
    )

# 写事件时自动携带:
def record_thinking(self, payload: ThinkingRecord) -> None:
    payload_with_inc = replace(payload, incarnation=self._incarnation.incarnation_seq)
    self._spine.append(execution_point="step.thinking.record", payload=asdict(payload_with_inc), ...)
```

**fork 共享 Host** 协议见 ADR-0171(独立文)。

### D7 · ModelVisibleCapture —— LLM 边界真实捕获,**不在 cursor**

继承 ADR-0167 I-MV1(Model-visible ≡ logged):
> 每一次真实 LLM 请求,必须存在可解析的 `RequestHeader` 记录(spine EP + model_visible 文件),使得离线可重建「当时发给模型的 system / tools / messages」。

**职责落在 LLM Adapter 边界**:`TelemetryLLMAdapter._capture_request(model, system, tools, messages, manifest)` 一次性写 5 件套到 `model_visible/step_<NN>/{system,tools,messages,manifest,inherited}.json`,再调 `cursor.record_request_header(...)` 落 spine EP + digest。

**与 cursor 的耦合**:`Capture` 读取 `cursor.snapshot.step_id / incarnation`,但不写 cursor 内部状态。结构上 cursor 不知道 Capture 存在。

详细 ADR-0170 §"ModelVisible 5 件套契约"。

### D8 · 五缝架构图(取代 ADR-0168-final §D6 字段表)

```text
业务 (cognition / body / runtime / agent)
  │ 调: cursor.advance · record_* · halt · close · fork · snapshot
  │
  ▼
┌────────────────────────────────────────────────────────────────┐
│ LoopCursor (控制面 · 状态机) — contracts/observability/loop_cursor │
│   持: spine handle(WritePort 协议位) + _state                     │
│   不持: deriver 列表 / projection registry / persistence 实现       │
│          / llm hook 实例 / model_visible recorder 实例           │
└──────┬─────────────────────────────────────────────────────────┘
       │ 只 append 语义事件到 spine
       ▼
┌────────────────────────────────────────────────────────────────┐
│ EventSpine  SSOT (lca/infrastructure/observability/spine/)       │
│   唯一允许 subscribers;subscribers 持有各自生命周期               │
│   L10 单写:`events.jsonl`                                       │
└──┬──────────────────────────────┬─────────────────────────────┘
   │                              │
   ▼                              ▼
┌──────────────────────────┐  ┌────────────────────────────────┐
│ ProjectionHost            │  │ PersistenceCoordinator           │
│  register(def) -> Token   │  │  flush() / close()               │
│  drive(snapshot, record)  │  │  restore(from_seq) -> Iterator  │
│  flush_all()              │  │  stats (PersistenceStats)       │
│  默认注册清单:             │  └────────────────────────────────┘
│   StepTreeAccumulator     │                ▲
│   NarrativeDeriver        │                │
│   GraphDeriver            │                │
│   CostProjector           │                │
│   ModelVisible 5 件套     │                │
│  LiveTail(纯 ring buffer, │                │
│   pub/sub 走 subscribe_)  │                │
└──────────────────────────┘                 │
          ▲                                  │
          │                                  │
┌─────────┴───────────────┐                  │
│ ModelVisibleCapture      │                  │
│  在 LLM adapter 边界     │                  │
│  写 model_visible/step_N │                  │
│  并调 cursor.record_*    │                  │
└──────────────────────────┘                  │
                                             │
           ┌─────────────────────────────────┘
           │
┌──────────┴─────────────────────────────────────────────────────┐
│ CloseBarrier(独立组件;由 ObservabilityRuntime 持有)              │
│   1. cursor.close signal → 关闭状态机                           │
│   2. emit closing EP                                           │
│   3. await Persistence.flush → ProjectionHost.flush_all         │
│      顺序由 Barrier 协调                                        │
│   4. emit close EP(L16:ProjectionHost 不订阅)                   │
│   5. release                                                   │
└────────────────────────────────────────────────────────────────┘
```

**装配**: `ObservabilityRuntime.from_profile(profile_yaml)` 装配
- `LoopCursorFactory → StdLoopCursor`
- `ProjectionHost(initial_definitions=[...])`
- `PersistenceCoordinator(coalescer, sink)`
- `ModelVisibleCapture`
- `CloseBarrier(cursor, persistence, host)`

`RunSessionBuilder.build` 解析上述五件并 attach,**不再**"new StdLoopCursor 包办一切"。

### D9 · 删除清单(评审 §S9 分阶段绑定)

评审 §S9 论证"D15 一次性硬删与 13 PR 叙事冲突"——本 ADR 绑定删除条件到 PR 阶段,**不绑** 投影重写同 PR。

| 待删 | 删除条件(可 grep 门禁) | 阶段 |
|---|---|---|
| `facade.step_open / step_close / step_record_*` 7 个 | grep `facade.step_open` in `lca/cognition` + `lca/body` = 0 | **PR-1(S1 web-standard 业务迁移)** 后立即 |
| `coord.begin_step / end_step / begin_segment / end_segment` | grep `coord.begin_step` = 0 in `lca/` | **S1** 后立即 |
| `coord.record_thinking / record_tool_call / record_tool_result` | grep = 0 | **S1** 后立即 |
| `coord.emit_phase / coord.emit` | grep = 0 in `lca/cognition` + `lca/body` + `lca/runtime` + `lca/agent` | **S1** 后立即 |
| `event_emission.py` 整模块 | 文件不存在 | **S1** 后立即 |
| `event_emission._derive_step_completed` 整段 | grep = 0 | 同上 |
| `make_journal_emitting_hook` | grep = 0 | 同上 |
| `NullLoopCursor` | grep = 0 | 持续状态 |
| `writable.matrix.default.storage` 默认文件名 `events.jsonl` | integration test 验证(L10) | **PR-2(S2 写路径纯度)** 后 |
| `bundles/spine-default.yaml` bundle 引用 | grep `spine-default` = 0 in `lca/plugins/transport/` profile refs | **PR-7.4(S7.4 最后一批)** 后 |
| `ProjectionRegistry.publish` | grep = 0 | **PR-3(S3 ProjectionHost 落)** 后 |
| `StdLoopCursor._derivers / _projections / _persistence / _llm_hook / _model_visible_recorder` 字段 | AST scan | **S3** 后 |
| `event_bus.py` 整模块 | 文件不存在 | **PR-6(S6) 之后;若 cordis 收口提前可在 S3 后** |
| `run_narrative.py` | 文件不存在 | 同上 |

### D10 · 验证矩阵 + 机器可执行门禁

继承 ADR-0168-final §D19 并固化 4 条门禁脚本:

```bash
# 1. 状态机单元 (D1 + D2)
uv run pytest tests/observability/test_loop_cursor.py -v
uv run pytest tests/observability/test_loop_cursor_transitions.py -v

# 2. close 顺序 (D5)
uv run pytest tests/observability/test_cursor_close_order.py -v

# 3. 不变量断言 (D3 L1-L16)
uv run pytest tests/observability/test_cursor_invariants.py -v
# L1-L16 每条 1+ test method

# 4. 装配边界(评审 §"机器可执行门禁") —— 新增/强化 4 条脚本
uv run lint-imports                                                  # business-event-isolation (L4)
uv run python scripts/check_cursor_assembly.py                       # L13 + L4
uv run python scripts/check_writable_matrix_boundaries.py            # L10
uv run python scripts/check_cordis_event_derivation.py               # L12
uv run python scripts/check_loop_cursor_no_deriver_hold.py           # 评审 S1 处方

# 5. Schema 演进 (D-评审 L15)
uv run pytest tests/observability/test_journal_format_errors.py -v

# 6. incarnation (D6 + ADR-0171)
uv run pytest tests/observability/test_incarnation_identity.py -v

# 7. CloseBarrier(评审 §7.2 处方)
uv run pytest tests/observability/test_close_barrier.py -v
# 顺序断言 + L16 投影不订阅 close EP

# 8. Snapshot replay CI 不依赖 API key (D19)
uv run pytest tests/replay/test_snapshot_replay_no_api_key.py -v

# 9. Profile 装配(评审 §D16 分批)
uv run pytest tests/profiles/test_all_profiles_have_cursor.py -v
# 仅校验 web-standard 其余 8 profile = issue 跟踪
```

**集成 run 黄金断言(web-standard)**:

```bash
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)

grep -c "writable.step.start"       traces/runs/$LATEST/events.jsonl   # ≥ 1
grep -c "writable.step.end"         traces/runs/$LATEST/events.jsonl   # = begin 数
grep -c "writable.iteration.close"  traces/runs/$LATEST/events.jsonl   # = 1
grep -c "LlmCallCompleted"          traces/runs/$LATEST/journal.json   # = 0 (L11 落地)
wc -l                               traces/runs/$LATEST/events.jsonl   # = spine.append 次数 (L10)
jq ".steps | length"                traces/runs/$LATEST/journal.json   # ≥ 1
jq ".steps[].incarnation"           traces/runs/$LATEST/journal.json   # 全部携带 (D6)
ls traces/runs/$LATEST/phase_graph.dot                              # 存在
ls traces/runs/$LATEST/model_visible/step_*/request-header.json     # ≥ 1
ls traces/runs/$LATEST/cost.json                                    # 存在
jq ".events[].schema"               traces/runs/$LATEST/events.jsonl   # 全部 = "lca.journal/2" (L15)
```

**死代码清理**:
```bash
uv run vulture lca --min-confidence 80
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
```

### D11 · 阶段化实施(评审 §7.3 ADR 拆分;**取代** ADR-0168-final 单篇 mega)

**PR 编号约定**:沿用项目内既有 PR-x 序列(详见 ADR-0066 / 0067 / 0074 / 0117 等 PR-x 表风格)。每个 PR 在本文档内有**两套命名**:
- **`PR-N`**(PR-1 ~ PR-7):项目内通用阶段编号;编码 agent 与评审共识。
- **`D11阶段号`**(S1-S6 + S7.1-S7.4):**DAG 节点**,带前置依赖;可机器解析阶段门禁。

**强制顺序 DAG**:每个后续 PR 的入口条件 = 前一阶段的所有阶段门禁全绿。**禁止跨 PR 合并**(评审潜在 #15 半套合并处方)。**禁止**对 PR 编号「PR-N + PR-M 同 PR」(失败归因难、回退不独立)。

| PR 编号 | D11 阶段 | 主体 ADR | 范围(单 PR 不可叠加跨阶段内容) | 成功度量 | 删除/完成条件 | 前置条件 |
|---|---|---|---|---|---|---|
| **PR-1** | S1 | ADR-0169 | LoopCursor Protocol + CursorSnapshot + Payload + L1-L8 + 业务 2 动词迁 web-standard;**不动** persistence / projection / capture 装配 | 12 转移图边全绿;`cognition/body/runtime/agent` 无 `coord.emit_phase` / `coord.record_*` / `coord.begin_step` | grep 全部 = 0 | 无(ADR-0169 Proposed)|
| **PR-2** | S2 | ADR-0169 + ADR-0170 预备 | L10 双写消灭:`writable.matrix.default.storage` 默认文件名改 `<run_id>.spine.jsonl` + `spine.sink.file` 单写 | `wc -l events.jsonl` == spine.append 次数(1:1);`grep LlmCallCompleted` = 0 | integration test 绿 | PR-1 全绿 |
| **PR-3** | S3 | ADR-0170 | ProjectionHost 协议 + 默认注册清单 + LiveTail 单身份 + CloseBarrier + L9-L10-L16 落位 | `StdLoopCursor` AST 不含 `_projections / _derivers / _persistence / _llm_hook / _model_visible_recorder`;LiveTail 不订阅 `writable.iteration.close` | 架构测试 + AST scan | PR-2 全绿(L10 单写稳定)|
| **PR-4** | S4 | ADR-0169 + ADR-0171 | L14 incarnation 强制 + ModelVisible Capture(D7)真实捕获 5 件套 + fork 共享 Host | envelope 100% 携带 incarnation;child cursor 字段白名单;capture 不污染 cursor | 单元 + 集成测试 | PR-3 全绿(0170 装配稳定)|
| **PR-5** | S5 | ADR-0173 | halt-resume 协议独立 rescue 路径(`resume_cursor(...)`);`web-standard-recovery.yaml` 首次可跑;不复用 cursor.close 异常路径 | I-RESUME-1..6 全绿;`web-standard-recovery.yaml` 一致性 grep 0 | 单元 + recovery profile 跑通 | PR-4 全绿(fork + Capture 稳定)|
| **PR-6** | S6 | ADR-0172 | Observability Exporters 实现层(metrics / OTel / Langfuse 走 `LoopProjectionDefinition` 注册到 host) | `langfuse_eval` profile 默认不挂;cursor 字段不变 | 端到端 exporter 单测 | PR-5 全绿 |
| **PR-7.1** | S7.1 | ADR-0174 | 迁 `oii-debug.yaml` + `benchmark.yaml` | 12 项黄金断言全过 | grep 独立验证 + lint warning | PR-6 全绿 |
| **PR-7.2** | S7.2 | ADR-0174 | 迁 `test-minimal.yaml` + `self-improving-minimal.yaml` | 12 项黄金断言全过 | grep 独立验证 + lint warning | PR-7.1 全绿 |
| **PR-7.3** | S7.3 | ADR-0174 | 迁 `web-standard-recovery.yaml` + `web-standard-continuous.yaml`(**必与 PR-5 / ADR-0173 联跑**)| 12 项黄金断言全过 + halt-resume 不破 | grep 独立验证 + lint warning | PR-5 全绿 + PR-7.2 全绿 |
| **PR-7.4** | S7.4 | ADR-0174 | 迁 `cordis-creator.yaml` + `genai-traced.yaml` + `coding-agent.yaml`(**必与 PR-6 / ADR-0172 联跑**)| 12 项黄金断言全过 + Exporter 不污染 cursor | grep 独立验证 + lint 升 ERROR | PR-6 全绿 + PR-7.3 全绿 |

**总计**:6 ADR 文档 + 7 主 PR(PR-1 ~ PR-7)+ 4 批 profile 子 PR(PR-7.1 ~ PR-7.4)= **约 13 PR,4 个 release cycle**。

**PR 阶段门禁机器可执行定义**(每 PR 独立 CI 校验脚本):
- **PR-1**: `scripts/check_cursor_assembly.py` + `tests/observability/test_loop_cursor_transitions.py::test_12_edges`
- **PR-2**: `tests/integration/test_l10_single_writer.py` + `tests/integration/test_no_dual_sink.py`
- **PR-3**: `scripts/check_loop_cursor_no_deriver_hold.py` + `tests/observability/test_close_barrier.py` + `tests/observability/test_live_tail_unsubscribes_close_ep.py`(L16)
- **PR-4**: `tests/observability/test_incarnation_identity.py` + `tests/observability/test_fork_shared.py` + `tests/observability/test_model_visible_capture.py`
- **PR-5**: `tests/observability/test_halt_resume.py` + `tests/profiles/test_recovery_profile_resume.py`
- **PR-6**: `tests/exporters/test_exporter_no_cursor_pollution.py` + `tests/exporters/test_langfuse_credential_fail.py`
- **PR-7.x**: `scripts/check_loop_cursor_bundle_required.py`(PR-7.1-3 阶段 warning,PR-7.4 升 ERROR)+ 12 项黄金断言 × 该批 profile

**为何不允许合并 PR(评审 §5.4 + 潜在 #15 处方)**:
- PR-1 + PR-3 同 PR 会一次性"切步 + 装 Host",失败归因难、review 视线宽、回退 1 PR 不可独立。
- PR-3 未绿就启 PR-4:LiveTail 双环 + Persist 重复 flush(SSE 重发 + 文件锁竞争)。
- PR-4 未绿就启 PR-5:resume 复用 halted_cursor 实例(I-RESUME-1 违反)。
- PR-5 未绿就启 PR-6 / PR-7:Exporter 在不稳定 host 上跑散,且 cordis 词表未收口,L12 易破。
- PR-7.3 未与 PR-5 联跑:recovery profile 装配崩而 cursor 状态机没问题,归因错。
- PR-7.4 未与 PR-6 联跑:Langfuse profile 跑绿但 Exporter 与 cursor 耦合,断 I-PROJ-5。

**D9 阶段编号回链对齐**:D9 删除清单中的"阶段"字段已与本 PR 编号一一对应(S1-S7.4 见上表);编码 agent 与 reviewer 看到 D9 删除条件时,直接读 D11 表即可定位触发该删除的 PR。

## 不变量承接与新引入

| 既有 | 本 ADR 处理 |
|---|---|
| C1 闭集(认知闭环) | 不变;`PhaseName` 是 `Literal[...]`,编译期禁扩展 |
| C2 双平面 | 不变;cursor 是认知面的状态机,执行面仍只读 snapshot |
| C3 Journal | 不变;cursor 派生 EP,Journal 仍是 SSOT |
| C4 Reducer | 不变;reducer 只读 `snapshot`,不改它 |
| C5 能力衰减 | cursor.fork 内置 grant 校验(ADR-0171 协议位继承) |
| C7 控制/观察分离 | **结构性落地**:cursor 只持 spine handle;ProjectionHost 持有 projections;PersistenceCoordinator 持有 persistence;ModelVisibleCapture 持有捕获;C7 不再字面打脸 D6 |
| I-PLUG1(业务不 import spine) | 强化:cognition/body/runtime/agent 不 import `EventSpine`/`Serializer`/`Storage`/`cursor.*`(除 advance/record_*),只走 cursor Protocol |
| ADR-0063 Run Trace SSOT | 不变;`events.jsonl` 仍 SSOT,L10 强制单写 |
| ADR-0065 Recoverable Evidence Ledger | 不变;L1-L7 契约保持;EvidenceRef 内容寻址沿用 |
| ADR-0093 Continuous Control Plane | 不变;web-standard-continuous profile 沿用 control plane cursor 实现 |
| ADR-0094 StopPolicy 局部性 | 不变;`halt(reason)` 入口保留 |
| ADR-0095 LoopGuard iteration | 不变;`iteration` ⊃ ADR-0095 iteration,L8 锁 |
| ADR-0162 Fact vs Progress 准则 | 不变;cursor.record_* 落事实,CursorSnapshot 派生 progress |
| ADR-0167 Model-Visible ≡ Logged | **强化**:Capture 在 LLM 边界,非 cursor 事后拼 |
| **新引入 I-CURSOR-1** | cursor.advance 是 phase 转移唯一入口;CursorError 不静默 fallback |
| **新引入 I-CURSOR-2** | snapshot 是 frozen + read-only;reducer / projection 不可改 |
| **新引入 I-CURSOR-3** | CloseBarrier 协调 flush 顺序;cursor.close 只发信号 |
| **新引入 I-CURSOR-4** | cordis event name 由 EventDescriptor.cordis_name 派生;`ctx.emit('agent.*'...)` 业务禁止 |
| **新引入 I-CURSOR-5** | incarnation = (run_id, plan_ref, incarnation_seq);envelope 必携带 |
| **新引入 I-CURSOR-6**(合并到 ADR-0171) | child cursor 不持独立 Host 实例;fork 通过共享 Host |

## 兼容性

**无 facade 兼容包装**:评审认可"inventory 证明无业务调用方,deprecation 是负担而非保护"——`facade.step_*` 7 个 + `coord.*` 9 个一次性删,但**删除条件绑到 PR-3 业务迁移 grep 门禁**,不绑投影重写同 PR(评审 §S9)。

**双 envelope 兼容保留**:继承 ADR-0065 + ADR-0067:`StampedEvent` ↔ `JournalRecord` 兼容保留(过渡期);`migrate_v1_to_v2` 保留。

**Schema 版本**:`SCHEMA_VERSION` 在 L15 升级为方向感知,不删除旧版本。

**Profile 兼容**:仅 web-standard 一次迁完(**PR-1 / S1**);其余 8 profile 用 issue 跟踪(ADR-0174),每批 2-3 个,从 S7.1 到 S7.4。

**五缝注册的 cordis / plugin 兼容**:cordis 不再是平行词表(评审 §S4 处方);`ctx.emit(event_name)` 必须由 EventDescriptor 派生。

## 删除条件

| 待删 | 条件 | 验证 |
|---|---|---|
| `facade.step_*` 7 个方法 | 全部删除,无 deprecation | `grep facade.step_open` = 0 in `lca/` |
| `coord.begin_step / end_step / begin_segment / end_segment / emit_phase / emit` | 全部删除 | `grep coord.begin_step` = 0 in `lca/` |
| `coord.record_thinking / record_tool_call / record_tool_result / record_reflect / record_span` | 全部删除 | 同上 |
| `event_emission.py` 整模块 | 全部删除 | 文件不存在 |
| `runtime/loop_step_control.py` | 不创建(被 `runtime/loop_cursor.py` 取代) | `ls lca/runtime/loop_step_control.py` 不存在 |
| `_derive_step_completed` | 删除 | `grep _derive_step_completed` = 0 |
| `_derive_action_degraded` | 转 adapter | 文件存在但仅含 thin wrapper(ADR-0170) |
| `make_journal_emitting_hook` | 删除 | `grep make_journal_emitting_hook` = 0 |
| `NullLoopCursor` | 不创建(L13) | `grep NullLoopCursor` = 0 |
| `bundles/spine-default.yaml` | 重命名 `bundles/loop_cursor.spine_default.yaml` | bundle name 变更 |
| `bundles/spine-benchmark-minimal.yaml` | 重命名 `loop_cursor.spine_minimal.yaml` | 同上 |
| `bundles/spine-oii-debug.yaml` | 重命名 `loop_cursor.spine_debug.yaml` | 同上 |
| `live_tail.py` EP 名丢失(_to_stamped) | 重写为直接接 EventRecord | `grep _to_stamped` = 0 |
| `event_bus.py` | 删除(评审 §S4) | 文件不存在 |
| `run_narrative.py` | 删除(评审 §S4) | 文件不存在 |
| `writable.matrix.default.storage` 默认文件名 `events.jsonl` | 改为 `<run_id>.spine.jsonl` (L10) | integration test 验证 |
| `WritableFace.model_visible_recorder / replay_cursor` | 删除 FACE_NAMES 条目 | `writable_matrix.py:108-114` 删除 |
| `coord.record_runtime` 在 cognition | 删除 | `grep record_runtime` 在 cognition = 0 |
| 旧 journal `LlmCallStarted/Completed` 写路径 | 删除(L11) | `grep LlmCallCompleted` 在 cognition/body/runtime = 0 |
| `ProjectionRegistry.publish` | 删除(合并进 ProjectionHost.drive) | grep = 0 |
| `JournalEvent` 49 类 | 保留 readonly dataclass;不再走 RunStore 写入 | `grep journal.write` = 0 in `cognition/body/runtime/agent` |
| **`StdLoopCursor._projections / _derivers / _persistence / _llm_hook / _model_visible_recorder` 字段** | **结构性删除**(评审 S1 处方) | AST scan `StdLoopCursor` 仅含 `_spine` + `_state` + immutable identifier |

## 后果

### 正面

1. **修补序列终止**:业务路径只看到 `advance(phase)` 与 `record_*(...)`,emit / subscribe / flush / close 信号由 cursor 发、host/barrier 接管,ADR-0156~0168-final 同类问题在结构上不再可能。
2. **五缝职责唯一**:control = cursor;projection = `ProjectionHost`;persistence = `PersistenceCoordinator`;model_visible = `ModelVisibleCapture`;close coordination = `CloseBarrier`。
3. **新增 deriver 零改 cursor**(评审 §5.1):架构测试断言 `loop_cursor.py` 无 deriver 字段。
4. **C7 与 D6 字面一致**(评审 §2.4 处方):cursor 只持 spine handle + state。
5. **spine 仍是总线**(评审 §S4 处方):EventSpine 保留 subscribers;deriver 走 ProjectionHost 注册;spine 仍可被任何第三方订阅。
6. **terminal.materialize 退化为 thin wrapper**(继承 ADR-0168-final §D18):CloseBarrier 协调 flush 顺序。
7. **incarnation 显式身份**(继承 + 收紧到 envelope 必携带):replay 时 iteration 边界可重建。
8. **cordis 双词表收口**(评审 §S4):`event_bus.py` + `run_narrative.py` 删除,业务 / plugin 不直接 emit `ctx.emit('agent.*'...)`。
9. **格式拒绝方向感知**(评审 §3 抖 L15):旧写新读 / 新写旧读分别给明确错误码。
10. **分批 profile**(评审 §5.4 处方):web-standard 先跑绿,其余 8 profile 用 issue 跟踪(ADR-0174)。
11. **Protocol 闭集纪律**(评审 §7.5):控制动词白名单冻结;任何新 record_X 默认问题"能否变 EP + Projection"。
12. **评审 18 项潜在问题 + 10 条 ADR 检查单逐条消化**(§10 附录);不留在"open question"。

### 负面

1. **五缝 + CloseBarrier 引入 4 个新组件**(ProjectionHost / PersistenceCoordinator / ModelVisibleCapture / CloseBarrier)。但:每个边界都是单一职责、可独立替身测。
2. **~13 PR 跨 4 cycle**(评审 §5.4):用户接受"架构优雅 + 实施分阶段"。
3. **删 deprecation wrapper**:业务方若有外部调用(测试夹具 / 第三方插件)需同步迁移;但 inventory 证明无业务调用方,影响有限。
4. **cordis 收口可能破坏既有 plugin**:inventory 证 I-PLUG1 当前无违规,但 D14 要求 EventDescriptor.cordis_name 字段,既有 reflector 需补该字段(ADR-0170 §"vocabulary")。
5. **机器可执行门禁**(评审 §"给编码 agent 的执行纪律")**强制**:禁单 PR 改 multi-profile + 改 multi-thing;每 PR 一条 grep 不变量。这是设计而非坏处。

## 引用

### Supersedes
- ADR-0168 决策段 (`docs/adr/0168-loop-step-control-and-model-visible.md:D1-D11`)
- ADR-0168.1 决策段 (`docs/adr/0168.1-loop-cursor-state-machine.md:D1-D6`)
- ADR-0168-loop-cursor-final 全文 (`docs/adr/0168-loop-cursor-final.md:D1-D20`)

### 关联(新增,本 ADR 同级)
- ADR-0170 ProjectionHost 协议(本 ADR L9 owner + 默认注册清单 + LiveTail 单身份 + Capture 边界)
- ADR-0171 fork 共享 Host 协议(I-CURSOR-6)
- ADR-0172 Observability Exporters 实现层(原 ADR-0168-final §D14 实施层)
- ADR-0173 halt-resume 协议(web-standard-recovery 跑绿)
- ADR-0174 Profile 分批装配(web-standard 后 8 profile)

### Cross-reference(不 supersede,继续有效)
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
- ADR-0095 LoopGuard iteration
- ADR-0156~0167 系列(面 / 共同祖先)
- ADR-0162 Fact vs Progress 准则
- ADR-0164 Journal Step Tree
- ADR-0165(.1) Execution Point Enforcement
- ADR-0167 Model-Visible ≡ Logged(I-MV1)
- ADR-0168 §背景段(问题陈述)
- ADR-0168.1 §背景段 + §转移图 + §Payload(继承)

### 保留
- ADR-0168 §背景段(问题陈述与现状盘点):inbound 双写 / coord.emit_phase / facade.step_* 等 inventory 证据。

### 实施计划
- `docs/plans/2026-09-02-spine-step-remediation/main.md`(继承,本 ADR 不重写)
- 后续由 writing-plans 输 PR-1 (S1) / PR-2 (S2) / PR-3 (S3) / PR-4 (S4) / PR-5 (S5) / PR-6 (S6) / PR-7.1..PR-7.4 (S7.1-S7.4) 子计划

---

## §9 · step 语义用例表(钉死选项 A)

| 场景 | phase 链 | 是否产生 step | record_request_header | 投影 |
|---|---|---|---|---|
| 标准 perceive-think-act | perceive→think→gate→act→reflect→stop | 1 step | yes(在 think 窗口)| 完整 |
| 纯 tool-only 路径 | perceive→think→gate→act→reflect→stop | 1 step | yes(无 model 调用,但 trigger 走基线 step)| 完整 |
| 纯 perceive 无 LLM | perceive→stop | **0 step** | **no** | 仅 phase EP |
| replay 历史 events | OUTSIDE_LOOP→STOP | 0 step | no(EP 来自 events.jsonl,不再 emit)| journal 由 replay 派生 |
| checkpoint resume | iteration++ via `iteration_reason=checkpoint_resume` | 1 step(新)| yes | 完整 + inherited_from_step |

**Step 语义选项 A 钉死**:step 是「一次模型请求」的因果投影;非 LLM 路径不入 step 计数(L8 iteration 与 attempt_in_step 均不计算)。

**用法强制**:`record_request_header` 必在 THINK 窗口开时调用 —— 调一次等价于"开一次新 step"。若 LLM adapter 在 THINK 窗口外被调,CursorError 直抛(违反 L6)。

---

## §10 · 评审点逐条消化(山姆「Conditional Go」ADR 检查单)

10 条检查单 + 18 项潜在问题逐条现状。每条给:**判定**(已消化 / 改写 / 独立 ADR / 不同意)+ **位置**。

### A. 评审附录 C(10 条评审检查单)

| # | 检查项 | 判定 | 位置 |
|---|---|---|---|
| 1 | 收敛的是调用面还是对象所有权?只允许前者 | 调用面 ✓ | D1 / §D8(对象所有权拆五缝)|
| 2 | 观察零控制 / 控制不持有观察实现 | ✓ | D3 C7 改写 + L9-L16 挂 owner |
| 3 | 新增 deriver 是否零改状态机核心 | ✓ | §D8 五缝图 + D11 ADR-0170 成功度量 |
| 4 | 是否保留事件总线的订阅可扩展性 | ✓ | §D8 spine 仍持 subscribers |
| 5 | 范围是否可被两周内一条不变量证明 | ✓ | D10 集成 run 黄金断言 + D11 拆文 |
| 6 | 「不留 follow-up」是否出现?出现则要求拆文 | ✓ | D11 + 4 篇独立 ADR |
| 7 | 硬删是否绑定可 grep 的迁移完成条件 | ✓ | D9 阶段化绑定 + grep 门禁脚本 |
| 8 | Profile 爆炸是否与核心语义解耦 | ✓ | D11 / ADR-0174 issue 跟踪 |
| 9 | 与上一篇 ADR 的 C7/P3 是否字面冲突 | ✓ 修复 | C7 改写 vs D6 字面一致 |
| 10 | Coding agent 是否可能「半套合并」?门禁要机器可执行 | ✓ | D10 四条门禁脚本 + 集成 run 黄金断言 |

### B. 评审附录 A(潜在问题 1-18)

| # | 潜在问题 | 判定 | 落点 |
|---|---|---|---|
| 1 | 改 narrative 要动 loop_cursor.py | ✓ 修复 | D8 五缝;narrative 在 ProjectionHost(ADR-0170)|
| 2 | 「不留 follow-up」导致单 ADR 不可审完 | ✓ 修复 | D11 / 4 篇独立 ADR + 阶段门禁 |
| 3 | spine 无 subscriber / 总线降级 | ✓ 拒绝 | §D8 spine 仍持 subscribers(ADR-0167 SSOT)|
| 4 | C7 与 D6 矛盾 / 文档双写意图 | ✓ 修复 | C7 改写 + D6 重写 |
| 5 | Protocol 持续加 record_* / 开放控制面 | ✓ 闭集 | D1 白名单纪律 |
| 6 | step 绑 LLM header / 语义耦合 | ✓ 钉死选项 A | §9 用例表 |
| 7 | 每 EP 同步 drive 全投影 / 性能未建模 | ⚠️ 跨 ADR | ADR-0170 default 批写窗口 + ADR-0172 Exporter 背压 |
| 8 | child fork 复制 Host / 未设计共享 | ✓ 拆文 | ADR-0171 |
| 9 | 九 profile 同迁 / 范围绑决策 | ✓ 分批 | ADR-0174 issue 跟踪 |
| 10 | 硬删 coord API / 无迁移窗 | ✓ 分阶段 | D9 grep 门禁 + PR-3 后立即删 |
| 11 | ContextVar attach 仍在 / 环境隐式依赖 | ⚠️ 部分 | 本 ADR 留 attach;显式参数化放到 ADR-0171 fork 共享文 |
| 12 | VersionTooOld 无升级路径 | ✓ 拆文 | ADR-0173 兼讨论;运维导出工具放到 operations ADR 候选 |
| 13 | LiveTail 重写 / SSE 回归 | ⚠️ 跨 ADR | ADR-0170 默认注册清单 + 契约测试 |
| 14 | metrics/OTel「也算本 ADR」/ 范围渗透 | ✓ 拆文 | ADR-0172 实现层独立 |
| 15 | Coding agent 半套合并 | ✓ 门禁脚本 | D10 四条 + CI 集成 run 黄金断言 |
| 16 | Persistence vs Projection 边界口头清、close 里又一起 flush | ✓ 修复 | D5 CloseBarrier 协调顺序;L16 钉死 |
| 17 | record_request_header 任意 phase | ✓ 修复 | D2 钉死 THINK 窗口 |
| 18 | 三文件 0168 命名 / 认知税 | ✓ 修复 | 本 ADR 编号 0169 + README 索引更新 |

### C. 评审总判三条对照

1. **保留**:LoopCursor 作为 loop 控制状态机 + 业务 2 动词 + CursorError + L10 单写 + incarnation + cordis 收口 + 删死 facade.step_* ——全部保留,见 D1/D3/D6/D14/D15。
2. **拒绝/拆开**:
   - "StdLoopCursor.__init__ 作为 spine / projection / persistence / LLM hook / model_visible 唯一装配入口"——**拒绝**,改造为五缝 + CloseBarrier(§D8)。
   - "不留 Follow-up ADR 作为成功标准"——**拒绝**(改为"按编号落地 + 阶段门禁")。
   - "D15 无窗口硬删与 D16 九 profile 同决策强绑"——**接受评估**(D9 拆阶段绑 grep;ADR-0174 分批)。
3. **排序**(与评审 §7.3 同向,详见 D11 阶段表):
   - **PR-1 / S1** 控制面(LoopCursor Protocol + 业务 2 动词迁 web-standard)
   - **PR-2 / S2** L10(events.jsonl 单写 + LlmCallCompleted = 0)
   - **PR-3 / S3** ProjectionHost(L9 / L10 / L16 挂到 host,CloseBarrier 协调 flush)
   - **PR-4 / S4** fork 共享 Host(incarnation + ModelVisible Capture + child cursor 共享)
   - **PR-5 / S5** halt-resume 独立 rescue(`resume_cursor(...)`,不复用 cursor.close 异常路径)
   - **PR-6 / S6** Observability Exporters(metrics / OTel / Langfuse 走 LoopProjectionDefinition)
   - **PR-7.1-4 / S7** Profile 分批(每批 ≤ 3 profile,S7.3 联跑 S5,S7.4 联跑 S6)

### D. 评审一句话判决的回应

> ADR-0168 final 找对了病(并行控制与漏 emit),开对了药名(LoopCursor),却开错了剂量(让状态机吞下投影宇宙)。

ADR-0169 接受这个诊断,处方:**薄控制状态机 × 宽事件 SSOT × 可插拔投影宿主** —— 三缝永久分开(实际五缝),用关闭屏障同步,而不是用一个类同步。五缝在 §D8 落图。

---

## §11 · 控制点迁移矩阵(继承 ADR-0168.1 §D1 表格)

| 现行控制点 | 文件:行 | 本 ADR 处理 |
|---|---|---|
| `coord.begin_step / end_step` | `coordinator.py:138-173` | 删 — 由 `advance(phase)` 派生 |
| `coord.begin_segment / end_segment` | `coordinator.py:175-203` | 删 — 由 phase(think/act)派生 |
| `coord.emit_phase`(4 调用方)| `safe_executor.py:388,403` 等 | 删 — `advance(phase)` 即发 `phase.<name>.fold` EP |
| `coord.record_thinking` 等 4 个 | `coordinator.py:277-324` | 收 — `cursor.record_thinking` 唯一入口 |
| `facade.step_open / step_close / step_record_*` 7 个 | `facade.py:516-575` | 删 — 无调用方(inventory §9.1)|
| `event_emission._derive_step_completed` | `event_emission.py:66-87` | 删 — 整段移除(含 facade.record 双轨)|
| `event_emission._derive_action_degraded` | `event_emission.py:50-63` | 保留 — 转 thin adapter(ADR-0170)|
| `event_emission.make_journal_emitting_hook` | `event_emission.py:97-134` | 删 — hook 范畴错误(ADR-0168.1 L19)|
| `coord.emit`(5 调用方)| `tool_journal_emit.py:141,179,275` 等 | 收 — `cursor.record_tool_call / record_tool_result` 唯一入口 |
| `facade.record_runtime`(4 调用方)| `perceive_hub.py:116,133` 等 | 删 — `cursor.record_thinking / record_tool_call / record_request_header` |
| `RunSessionBuilder.subscribe step_tree` | `session/builder.py:118` | 删 — 由 ProjectionHost.register 装配 |
| `RunSessionBuilder.bind_current_coordinator` | `execute/execution_environment.py:128-130` | 收 — `cursor.attach()` 注入 ContextVar |
| `StdLoopCursor._derivers` 字段 | ADR-0168-final §D6 | 删字段 — 转移到 ProjectionHost |
| `StdLoopCursor._projections` 字段 | ADR-0168-final §D6 | 删字段 — ProjectionHost 持有 |
| `StdLoopCursor._persistence` 字段 | ADR-0168-final §D6 | 删字段 — PersistenceCoordinator 持有 |
| `StdLoopCursor._llm_hook` 字段 | ADR-0168-final §D6 | 拆 — ModelVisibleCapture 持有 Capture;LLM adapter 持 hook |
| `StdLoopCursor._model_visible_recorder` 字段 | ADR-0168-final §D6 | 删字段 — ModelVisibleCapture 在 LLM 边界 |
