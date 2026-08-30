# ADR-0098: SessionEvent 因果流扩段 + Projection 当前态双通道

> **Superseded by ADR-0099 / 2026-08-29**

**Status**: Accepted — 2026-08-29（与 [ADR-0096 P2 §13](../../adr/0096-journal-protocol-layer-everything-pluggable.md) Deferred 路径对齐）

> **Decision**：把 LLM 流式 deltas（reasoning/text/tool）从 journal Envelope v2 升格为 **SessionEvent**，使 SessionEvent 同时承载 **因果时间序** 与 **当前态** 两类语义。SSE wire 同时输出三类 `event:` 名称空间 —— `deltas` / `projection.{conversation,activity,task}` / `terminal`，各分轴编号，可独立断点续传。

## 1. 背景

ADR-0096 P2 把 server 改成"持久 projection owner"：每次 SessionEvent 都重算投影，client 通过 `/runs/{id}/live` 订阅 projection 变化视图。该模式落地后**五类前端缺陷同时出现**：

| 缺陷 | 现象 |
|---|---|
| F1 SSE 非实时 | projection 只在 checkpoint 时更新,LLM token-by-token 完全无信号 |
| F2 深度思考不可视 | reasoning 在 Envelope v2 `ReasoningDelta`,projection 视图不带 reasoning 字段 |
| F3 工具调用不可视 | `tool.called.v1` 是 SessionEvent 但无 Projection 承载;`value.messages` 数组被 driver 丢弃 |
| F4 Network Error | maxRetry + backoff 自循环 30s 后抛 `TypeError: Failed to fetch`,UI 显示 network error |
| F5 持久化丢失 | persistRow 仅在 terminal 触发,刷新页面消息丢失(截图证据 `lca-persistence-regression/post-reload-state.png`)|

**根因**：把"因果时间序"(events)与"当前态"(projections)强制共用**单一 whole-value projection 通道**,违反了 C7(控制/观察分离)和 C1(闭集词汇表达力)。

## 2. 决策

### D1. SessionEvent 词汇扩段(C1 闭集变更)

新增 5 条 SessionEvent 类型,定义于 `lca/contracts/harness/events.py`:

| type | data schema | 触发位置 |
|---|---|---|
| `text.delta.v1` | `{turn, step, content_ref}` | LLMStreamTap on `OUTPUT_TEXT_DELTA` |
| `reasoning.delta.v1` | `{turn, step, content_ref}` | LLMStreamTap on `REASONING_TEXT_DELTA` |
| `reasoning.completed.v1` | `{turn, step, duration_ms}` | LLMStreamTap on `COMPLETED` 之后 reasoning 段结束 |
| `tool.denied.v1` | `{call_id, reason}` | SafeExecutor 拒绝工具调用 |
| `session.checkpoint.v1` | (existing,extended)`{status: "completed"\|"failed"\|"canceled"\|"waiting_input", terminal_seq?, answer?, error?}` | 已存在,扩字段 |

其他 SessionEvent(type `tool.called.v1` / `tool.completed.v1` / `assistant.responded.v1` / `turn.*.v1`)已存在,继续使用。

**唯一允许升格入口**:新增 `lca/harness/session/llm_stream_tap.py::LLMStreamTap`,不允许其它地方直接 `session_store.append(...)` 这些新事件类型。

### D2. Wire 协议三类 `event:` 名称空间

`GET /lca-api/runs/{run_id}/live` 同时输出:

```
event: deltas          ← SessionEvent 时间序,id = event.seq,Last-Event-ID 续传
event: projection.{k}  ← Projection 当前态,id = projection_seq,独立编号空间
event: terminal        ← 一次性终结信号,server 在此之后主动 close
```

每类有独立 `id:` 计数,客户端按 `event:` 分轴订阅,**不共用** Last-Event-ID。

### D3. Server 在 terminal 后主动 close

`gateway/runs/session_adapter.py::stream_live` 重写后,terminal 事件是**最后一个**,紧随其后的 server 端 close 流。**取消** maxRetry reconnect 循环(consumer 必须能从 from scratch 重连到 `Last-Event-ID` 处,但不在同一次 fetch 内自循环)。

### D4. `ActivityProjection.view` 增加 `terminal` 标记

```python
class ActivityProjection:
    def apply(self, state, event):
        ...
        if state["status"] in TERMINAL_STATUSES:
            state["terminal"] = True   # 仅字典视图多一字段;UI 仍按 status 字段判断
        return state
```

`ConversationProjection` / `TaskProjection` 语义不动。

### D5. 不动现有 wire 层兼容点

- `GET /api/device/devices`、`POST /runs`、`GET /runs/{id}`、`GET /runs/{id}/doctor` 全部不变。
- `/journal/live` 已 503 + `legacy_process_journal_unavailable`,本次不重启该路径。
- `OpenAI /v1/chat/completions` 不动。
- 前端删除 `PROJECTION_EVENT_NAMES` / `projectProjectionFrame` / `isProjectionEventName` 等 derived kind —— **不在本 ADR 范围内**(由前端 M4 commit 提交)。

## 3. 替代方案(被否)

| 方案 | 否决原因 |
|---|---|
| A 回滚 SessionRunAdapter 到 legacy Journal SSE | 违反 ADR-0096 P2 立项动机,丧失可恢复投影 owner |
| C 让 ConversationProjection 内嵌 fetch evidence | projection 背因果负担,违反 C1/C7;实时性仍依赖 projection |
| B' 只在 SessionEvent 加 reasoning/tool 但 wire 仍单通道 | 仍依赖 projection 消费,端到端延迟不解决,F1 不改善 |

## 4. 后果

### 正面

- 五类缺陷全部一次性消失,不再需要 client 端 reconnect-loop。
- SessionEvent = 因果真相,JSONL 可完整重放,deterministic;Projection 是 index,无独立可信状态。
- C7 控制/观察分离在 Session 内第一次实现;client 永远不读 projection 当因果。
- Reasoning/Tool 调用在 wire 上 first-class,前端可直接订阅 `event: deltas` 转 `StreamingHandler`。
- 新增 token 字面必经 `evidence/{digest}` 持久化,SessionEvent 只引 `content_ref`,符合已有 `MessageAccepted` 设计。

### 风险

- C1 闭集扩段:任何想新增 `xxx.delta.v1` 的需求必须走 ADR,不能直接 append。
- `event: deltas` 数量可能很高(token 级);client 必须按 seq 续传而不是按事件内容去重。
- `evidence/{digest}` 协议复用现有 `ContentRef`,若 ref 命名空间后续需要细分需新增 ADR。

### 否决影响

- ADR-0038(LLMStreamEventContract)不变。
- ADR-0065 / ADR-0074 / ADR-0075 不变。
- ADR-0096 P2 不变,本 ADR 是 P2 路径上一段,不是替代。

## 5. 实施路径(commit 序列)

| commit | 内容 | 是否可独立回滚 |
|---|---|---|
| M0 | ADR-0098 (本文) 仅 docs | 是 |
| M1 | `lca/harness/session/llm_stream_tap.py`(新)+ `brain/llm_turn/executor.py` 插 await + 测试 | 是 |
| M2 | `lca/harness/session/live_bus.py`(新)+ 测试 | 是 |
| M3 | `gateway/runs/session_adapter.py::stream_live` 三通道 + `ActivityProjection.terminal` + 测试 | 是 |
| M4 | 前端 `lcaJournal.ts` / `LcaRunDriver.ts` 等(不在本 ADR commit 范围) | — |

## 6. 验收

- `tests/harness/test_llm_stream_tap.py` 红→绿
- `tests/harness/test_session_live_bus.py` 红→绿
- `tests/gateway/test_session_run_adapter_stream_live.py` 红→绿
- `./scripts/lca-ops dev` + `curl -N` 抓到 `event: deltas` / `event: projection.conversation` / `event: terminal`
- `tests/scenario_standard.py` 含 tool 调用,server log 含 `tool.called.v1` / `tool.completed.v1`,无 `Failed to fetch`
- 完整 `tests/` 回归(`-m 'not real_llm'`),不破坏 F4/F5 既有契约测试
