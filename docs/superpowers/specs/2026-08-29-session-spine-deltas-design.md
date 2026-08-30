# 2026-08-29 — Session Spine 因果 deltas + Projection 当前态 双通道设计

> **Status**: Draft, pending user review
> **Parent ADR**: [ADR-0096 §13 P2 Deferred](../../adr/0096-journal-protocol-layer-everything-pluggable.md)
> **Sub ADR planned**: [ADR-0098 — SessionEvent 因果流扩段（C1 闭集变更）](../../adr/0098-session-spine-deltas.md)
> **Date**: 2026-08-29
> **Scope**: gateway `/runs/{id}/live` SSE 协议、server 端 SessionEvent + Projection 双通道产出、client 端 LcaRunDriver 重构

---

## 0. 背景

会话脊柱（Session Spine, ADR-0096 §13 P2）目前以 *whole-value projection* 模式工作：server 只投影当前态，前端据此反推增量。该模式落地后产生**五类不可接受的缺陷**：

1. **SSE 实时性缺失**：projection 更新只在 `session.checkpoint.v1` 时发生，期间 token-by-token 流完全无信号。
2. **深度思考不可视**：reasoning 内容在 journal `ReasoningDelta`（Envelope v2）中，但 conversation projection 不携带 reasoning 字段。
3. **工具调用不可视**：`tool.called.v1` / `tool.completed.v1` 是 SessionEvent 类型，但**没有 Projection 承载它们**，前端 driver 完全丢弃 `value.messages`。
4. **Network Error 反复出现**：driver 内部用 `backoff + maxRetry=10 + snap.fetch` 形成自循环，每次 server 关闭 SSE 或返回非终态都会触发 30 秒退避重连，最终抛 `TypeError: Failed to fetch` 显示为 `network error`。
5. **持久化丢失**：persistRow 仅在 terminal/paused 状态触发，普通 conversation snapshot 不写盘；reload 后内容丢失（截图证据：`lca-persistence-regression/post-reload-state.png`）。

把这五个症状的根因汇总成一句：**server 把"因果时间序"和"当前态"两类对象强行挤进单一 whole-value projection 通道**，违反了 C7 控制/观察分离 + C1 闭集词汇表达力。

---

## 1. 设计决策

**D1.** SessionEvent 通道与 Projection 通道在 wire 层彻底分离，前端用三条独立 `event:` 名称空间消费。

**D2.** 引入 `LLMStreamTap` 作为 SessionEvent 的**唯一允许新增入口**，把 LLM Stream 升格为 SessionEvent。这是 C1 闭集变更，必须先写 ADR-0098。

**D3.** Projection 维持 whole-value 语义不变（不破坏现有 web projection UI），仅 `ActivityProjection.view` 增加 `terminal=True` 标记，用于 server 端一次推送 `event: terminal` 的判定，不进客户端协议层。

**D4.** 客户端不再需要 maxRetry reconnect-loop。server 在 terminal 后主动 close SSE；客户端依赖 `Last-Event-ID` 自然续传。

**D5.** 客户端 `projectJournalFrame` + `StreamingHandler` 全套**复用不动**，只新增 `SessionFrameTranslator` 将 SessionEvent 上游翻译成 JournalFrame 形态。

---

## 2. 不变量（Invariants）

**I1.** 心智流 = LLM Stream deltas 序列，最终升格为 SessionEvent（因果事实）。

**I2.** SessionEvent 有序、不可重排，由 SessionStore JSONL 持久；Projection 是可丢弃可重建的索引视图。

**I3.** server → client SSE 流同时携带 SessionEvent（deltas 通道，因果）与 Projection（projection 通道，当前态），各 `event:` 名称空间分轴 `id:` 编号。

**I4.** network error 后 client 只在 deltas 通道续传（`Last-Event-ID` 同步 seq），projection 通道可整代重算。

**I5.** Reasoning 与 ToolCall 在 Session 层面是 first-class SessionEvent，不再寄生于 journal Envelope v2。

**I6.** Session JSONL = 唯一可信事实；Projection 是 index 视图；LLM Stream deltas 是观察不持久 — token 字面经 `evidence/{digest}` 持久化，SessionEvent 只引 ref。

---

## 3. 架构与数据链路

```
LLM stream tokens
   │
   ▼ LLM StreamTap.on_stream_event  ←── 唯一允许升格 SessionEvent 的入口
SessionEvent { reasoning.delta.v1, text.delta.v1, tool.called.v1, ... }
   │
   ▼ (existing) SessionStore.append → JSONL persist + fan-out listeners
   │
   ├──► (existing) InMemoryProjectionRegistry.on_event
   │        └──► 投影重算 + projection.* view 通知
   │
   └──► (new) SessionLiveBus.tail(session_id, after_seq)
            └──► SSE "event: deltas", seq = SessionEvent.seq

gateway/runs/session_adapter.py::stream_live
   │
   ├─► yield "event: deltas" id={event.seq}
   ├─► yield "event: projection.{key}" id={projection_seq}
   └─► yield "event: terminal" id={terminal_seq}  ← status ∈ {completed,failed,canceled,waiting_input}
                                                                       │
                                                                       ▼
                                          gateway 在 terminal 事件后主动 close 流
                                          client 线性读流直到 EOF
```

---

## 4. Wire Protocol

### 4.1 `/lca-api/runs/{run_id}/live` 三通道

```
GET /lca-api/runs/{run_id}/live
Last-Event-ID: {最后处理的 seq}

# 通道 1: deltas — 因果时间序，可断点续传
event: deltas
id: {event.seq}
data: {"session_id":"...", "event":{...SessionEvent JSON...}}

# 通道 2: projection — 当前态，三种 key 分别独立编号
event: projection.conversation
id: {projection_seq}
data: {"session_id":"...", "key":"conversation", "version":1, "seq":..., "value":{...full view...}}

event: projection.activity
id: ...
data: {"session_id":"...", "key":"activity", "version":1, "seq":..., "value":{status, turn, error, terminal}}

event: projection.task
id: ...
data: ...

# 通道 3: terminal — 一次性终结信号
event: terminal
id: {terminal_seq}
data: {"session_id":"...", "status":"completed", "terminal_seq":N, "summary":{...}}
```

### 4.2 序号语义

| 通道 | `id` 编号 | 重传语义 |
|---|---|---|
| `event: deltas` | `SessionEvent.seq`（单调递增，可能缺） | `Last-Event-ID` = deltas 最后一个 seq,server 从该 seq 续推 |
| `event: projection.conversation` | ConversationProjection 最后 applied 的 event.seq | client 单独记录，独立续传 |
| `event: projection.activity` | 同上,ActivityProjection 维度 | 同上 |
| `event: projection.task` | 同上,TaskProjection 维度 | 同上 |
| `event: terminal` | terminal event 自身 seq（一次性） | client 已无需重传 |

### 4.3 错误收口（HTTP 状态码）

| HTTP | 含义 | client 处理 |
|---|---|---|
| 200 + terminal event | 流正常 | break |
| 200 + stream close before terminal | server 进程崩溃重启 | client 走 `Last-Event-ID` 重连 |
| 404 | run not found | `noteRowError(new Error("run not found"))` → UI 提示"该对话不存在" |
| 503 + `code=legacy_process_journal_unavailable` | 不应出现（保留兼容） | `noteRowError` |
| 网络断开（`TypeError: Failed to fetch`） | NAT / proxy / DNS | `lcaError.ts` 翻 `CHAT_NETWORK_ERROR` → UI 提示"网络连接中断,请检查网络后刷新" |

---

## 5. Server 侧组件

### 5.1 `lca/harness/session/llm_stream_tap.py`（新）

**单一职责**：把 LLMStreamEvent 升格为 SessionEvent，写 SessionStore。

```python
class LLMStreamTap:
    def __init__(self, session_store: SessionStore, evidence: EvidenceWriter) -> None: ...
    async def on_stream_event(self, *, turn: int, step: int, ev: LLMStreamEvent) -> None:
        # OUTPUT_TEXT_DELTA        → evidence.write + text.delta.v1{turn, step, content_ref}
        # REASONING_TEXT_DELTA     → evidence.write + reasoning.delta.v1{turn, step, content_ref}
        # FUNCTION_CALL_ARGUMENTS_DELTA → tool.called.v1{turn, step, call_id, tool_name, arguments_ref}
        # COMPLETED                → reasoning.completed.v1 / assistant.responded.v1
```

落地点：`lca/cognition/brain/llm_turn/executor.py` 在既有 `LLMStreamEventType` 分支里插入 `await tap.on_stream_event(...)`（不替换既有 yield，新增写入）。

### 5.2 `lca/harness/session/live_bus.py`（新）

**单一职责**：每个 SessionStore 绑一个 SessionLiveBus，分发 append 过的 SessionEvent 给所有订阅者，支持断点续传。

```python
class SessionLiveBus:
    def __init__(self) -> None:
        self._ring: dict[str, dict[int, SessionEvent]] = {}  # 限 2048
    def bind(self, session_store: SessionStore) -> None:
        session_store.subscribe(self._fanout)  # 利用 SessionStore.subscribe 既有机制
    async def tail(self, session_id: str, after_seq: int) -> AsyncIterator[SessionEvent]:
        # 先从 ring 输出 [after_seq, max_seq] 范围内的事件
        # 然后切到 fanout 实时队列
```

### 5.3 `SessionRunAdapter.stream_live` 重写

`gateway/runs/session_adapter.py::stream_live` 改为双源合并：

```python
async def stream_live(self, run_id, last_seq=0):
    bus, registry = self._live_bus, self._projection_registry
    queue: asyncio.Queue = asyncio.Queue()
    deltas_done = asyncio.Event()
    projection_done = asyncio.Event()

    async def deltas_loop():
        async for event in bus.tail(run_id, last_seq):
            await queue.put(("deltas", event.seq, event))
            if event.type == "session.checkpoint.v1":
                if event.data.get("status") in TERMINAL_STATUSES:
                    break

    async def projection_loop():
        async for change in registry.subscribe_changes(run_id):
            await queue.put(("projection", change.seq, change))
            activity_view = change.value if change.key == "activity" else None
            if activity_view and activity_view.get("terminal"):
                break

    # 合并 → terminal 事件 → 主动 close
    ...
    yield "event: terminal" ...
```

### 5.4 `ActivityProjection.terminal=True`

`lca/harness/projection/web.py::ActivityProjection.apply` 在 status 命中 `{"completed","failed","canceled","waiting_input"}` 时设置 `state["terminal"] = True`，`view` 透出。语义变化：**view 多一个字段**，旧 client 只读 `status` 字段不受影响。

---

## 6. Client 侧组件

### 6.1 翻译器 `SessionFrameTranslator`

`deploy/lobehub/patches/runtime/lcaJournal.ts` 增加类型与函数：

```ts
export type SessionFrame = {
  type: string;          // SessionEvent.type
  seq: number;
  data: Record<string, unknown>;
  time_ms?: number;
  speaker?: string;      // actor
};

export type Translator = (sess: SessionFrame, runner: EvidenceRunner) => JournalFrame[];

export interface EvidenceRunner {
  fetch(content_ref: string): Promise<string>;
  invalidate(content_ref: string): void;  // 404 时缓存清理
}
```

### 6.2 SessionEvent → JournalFrame 映射表

| SessionEvent.type | → JournalFrame.event | payload |
|---|---|---|
| `text.delta.v1` | `StepTextDelta` | `{text_delta, channel:"answer"}` |
| `reasoning.delta.v1` | `ReasoningDelta` | `{text_delta}` |
| `reasoning.completed.v1` | `ReasoningCompleted` | `{duration_ms}` |
| `turn.started.v1` | `LlmCallStarted` | `{model, plan_ref}` |
| `tool.called.v1` | `ToolStarted` | `{tool_name, invocation_id, state_ref:{arguments_ref}}` |
| `tool.completed.v1` | `ToolInvoked` | `{state_ref:{result_ref}, files}` |
| `tool.denied.v1` | `ToolDenied` | `{reason}` |
| `assistant.responded.v1` | `StepTextDelta`（终态,channel="answer"） | `{text_delta}` |
| `session.checkpoint.v1` | (drop;由 server terminal 事件承担) | — |
| `model.{requested,completed,failed}.v1` | `RuntimeObserved`(已经是 model 类) | `{...}` |

`StreamingHandler` 全套不动。所有原有 `projectJournalFrame` / `projectLobeHubJournalFrame` 路径不变。

### 6.3 `LcaRunDriver.ts` 重构

```ts
export async function runLcaJournal(get: () => ChatStore, options: LcaRunOptions): Promise<ProjectedRow> {
  // ... assistantId / ensureTurn / handler 初始化保留 ...

  const translator = makeTranslator(runId);            // new
  const evidence = makeEvidenceRunner(runId);          // new

  try {
    const createRes = await fetch('/lca-api/runs', { ... });        // 已有
    // ... parse created, store runId ...

    const streamRes = await fetch(`/lca-api/runs/${runId}/live`, {
      headers: { ...authHeaders, 'Last-Event-ID': String(afterSeq) },
      signal,
    });
    if (!streamRes.ok) { ... }

    for await (const frame of readSse(streamRes)) {
      switch (frame.event) {
        case 'deltas': {
          // frame.eventPayload = {session_id, event: SessionEvent}
          const sess = frame.eventPayload.event;
          for (const jf of translator.toJournalFrames(sess, evidence)) {
            await applyProjected(projectJournalFrame(jf));
          }
          break;
        }
        case 'projection.conversation':
          // 同步 latestAssistantMessage 到 DB (debounce)
          await syncProjectionToDb(frame.eventPayload.value);
          break;
        case 'projection.activity':
          // 仅触发 persist debounce;不再决定 break
          schedulePersist();
          break;
        case 'terminal': {
          await persistRow();                  // 强制落盘
          publishFinalDeliverables();
          await finishTurn();
          return currentRow();
        }
        default:
          break;
      }
    }
    // 自然 EOF (server 主动 close) → 与 terminal 同等待遇
    await persistRow();
    publishFinalDeliverables();
    await finishTurn();
    return currentRow();
  } catch (error) {
    if (signal.aborted) { ... cancel + return ... }
    noteRowError(toLcaTranslateError(error));           // 走 lcaError.ts 单点
    await ensureTurn();
    await finishTurn();
    publishFinalDeliverables();
    return currentRow();
  }
}
```

**删除清单**（M4 一次性删）：
- `LcaRunDriver.ts`：`lastAssistantMessage`/`projectionContent`/`authoritativeContent`/`lastActivityStatus` 四个 state。
- `LcaRunDriver.ts`：整个 `case 'conversation-snapshot' / 'activity-status' / 'task-status'` 分支。
- `LcaRunDriver.ts`：整个 reconnect/backoff/snap.fetch 循环。
- `lcaJournal.ts`：`PROJECTION_EVENT_NAMES`/`projectProjectionFrame`/`isProjectionEventName`/`conversation-snapshot`/`activity-status`/`task-status` 三个 derived kind。

### 6.4 错误归一 `lcaError.ts`

| 服务端 / 客户端抛 | 翻译后 `ChatMessageError.type` | UI 文案 |
|---|---|---|
| `live HTTP 503 + code=legacy_process_journal_unavailable` | `AgentRuntimeError` | "服务端迁移中,请改用 /runs/{id}/live" |
| `live HTTP 4xx` | `AgentRuntimeError` | "请求被拒:{err.message}" |
| `live HTTP 5xx` | `AgentRuntimeError` | "网关暂时不可用,请刷新或稍后重试" |
| `TypeError: Failed to fetch` / `NetworkError` | `AgentRuntimeError` | "网络连接中断,请检查网络后刷新" |
| `event: terminal` 携带 `error` | `AgentRuntimeError` | "模型/工具错误:{err.message}" |
| `evidence/{ref}` 404 | (drop,静默) | 不暴露 UI |

### 6.5 持久化 debounce

`lcaPersist.ts` 改：
- `onContentUpdate` / `onToolCallsUpdate` 触发 800ms debounce 落盘。
- 任何 inactivity 超过 5s 强制 persist 一次。
- `event: terminal` 立刻 flush（不走 debounce）。

### 6.6 `consumer_resilience.ts` 收缩

`ReconnectController` / `BackoffStrategy` 不再被 LcaRunDriver 内部使用，仅保留 utility（供别处复用），不删除文件。

---

## 7. 验收规约（Definition of Done）

| ID | 验收 |
|---|---|
| AC-1 | `curl -N /lca-api/runs/{id}/live` 抓到三类 event（deltas / projection.* / terminal），至少 5 个 deltas 来自真实 LLM |
| AC-2 | 浏览器截图中 reasoning 折叠面板展开显示完整推理内容 |
| AC-3 | 浏览器截图中 tool 调用块显示 `tool_name`、arguments、result |
| AC-4 | 浏览器截图无 "network error" 红色提示 |
| AC-5 | 浏览器截图：页面刷新后助手消息、行内 reasoning、tool 调用块仍存在 |
| AC-6 | `./scripts/lca-ops` minimal run 命令可端到端走通 |
| AC-7 | `tests/test_session_live_bus.py` 红→绿 |
| AC-8 | `tests/test_session_run_adapter.py`（修改后）红→绿 |
| AC-9 | `lcaJournal.test.ts` 增 translation 用例红→绿 |
| AC-10 | `ruff check + lint-imports + mypy lca + pytest` 全部绿 |

---

## 8. 迁移顺序（按 M0-M4 串行，每 commit 跑 ruff+相关测试）

| Milestone | 改动 | 验证 |
|---|---|---|
| **M0** 写 ADR-0098（仅 docs） | `docs/adr/0098-session-spine-deltas.md` | user review + ADR 程序 |
| **M1** `LLMStreamTap` 新增 + executor 接入 | `lca/harness/session/llm_stream_tap.py`(新) + `executor.py` 插一行 await | `tests/test_llm_stream_tap.py` 红→绿 |
| **M2** `SessionLiveBus` 新增 | `lca/harness/session/live_bus.py`(新) | `tests/test_session_live_bus.py` 红→绿 |
| **M3** `stream_live` 双通道 + `ActivityProjection.terminal=True` | `gateway/runs/session_adapter.py` + `projection/web.py` 改动 | `tests/test_session_run_adapter.py` 红→绿,curl -N 三事件 |
| **M4** `LcaRunDriver` 重构 + `lcaError`/`lcaPersist` 配合 | 5 个 lobehub patch 文件 | `lcaJournal.test.ts` + 浏览器截图对照 |

---

## 9. 删除清单（明确减法）

- 不动 `ConversationProjection` 语义
- 不动 `TaskProjection` 语义
- 不动 `InMemoryProjectionRegistry.subscribe_changes`
- 删除 `PROJECTION_EVENT_NAMES`/`projectProjectionFrame`/`isProjectionEventName`
- 删除 `conversation-snapshot` / `activity-status` / `task-status` 三个 derived kind
- 删除 LcaRunDriver 的 4 个 state 与 reconnect/snap-fetch 循环
- 不新增 `JournalPath` / `RunManifest.terminal_event_seq` 等无关字段
- 不修改 LLM Stream Contract（ADR-0038）

---

## 10. 跨项目不变式（再强调一次）

- **C1 闭集变更**只允许通过 ADR-0098 增加 5 条 SessionEvent。
- **C7 控制/观察分离**：deltas 是观察事件；projection 是状态观察；terminal 是终止信号。三者不混名空间。
- **C4 Reducer**：`ActivityProjection.terminal=True` 状态变更仍走 Reducer，不绕开。
- **C2 双平面**：LLMStreamTap 在 cognition-side 触发 SessionEvent 写入；不在 executor 内原地改 AgentState（保留现有 cognitive/brain 习惯）。
- **AGENTS §7 禁止**：不修改 vendor/`lobehub-ui/`生成文件，全部走 `deploy/lobehub/patches/`。

---

## 11. 待办与悬而未决

- ADR-0098 待写（M0 单独 commit）。
- `evidence/{ref}` 协议是否需要在 SessionEvent 内显式携带 ref 名字空间还是统一 `content_ref`，由 M1 实现时敲定（不影响 D1-D5）。
- LLMStreamTap 的 evidence 写入并发模型（M1 阶段决定串行 or batch）。
- Gateway 的 session_id == run_id 双轨映射（M3 时确认无破坏）。

---

## 12. 术语

| 词 | 含义 |
|---|---|
| SessionEvent | Session 事实流事件（C1 受 ADR-0098 约束）|
| deltas 通道 | SSE `event: deltas` 时间序承载 |
| projection 通道 | SSE `event: projection.{key}` 当前态承载 |
| terminal 事件 | SSE `event: terminal` 单次终结信号 |
| evidence/{ref} | LLM token / tool io 字面持久化 |
| LLMStreamTap | LLM Stream → SessionEvent 升格唯一入口 |
| SessionLiveBus | SessionStore.subscribe 包装的分发总线 |
| StreamFrame | 翻译器输入（SessionEvent 形态）|
| JournalFrame | 翻译器输出（lcaJournal 已有的事件形态）|
