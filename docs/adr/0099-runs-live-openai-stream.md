# ADR-0099: `/runs/{id}/live` 收敛到 OpenAI ChatCompletion streaming

> **Superseded by [ADR-0100](0100-chat-command-is-agent-run.md) / 2026-08-29**
>
> 聊天 wire（把 Agent Run 伪装成 `POST /v1/chat/completions`）退役。`GET /runs/{id}/live` 由 0100 收回，载荷改为四个 UI 事件，不是三通道。对 ADR-0098 三通道 SSE、LiveBus、LLMStreamTap 的否决仍然有效；Journal-as-Truth 不变。

**Status**: Superseded — 2026-08-29

> **Decision**：删除 ADR-0096 MVA、ADR-0097、ADR-0098 引入的自创 3-通道 SSE wire（`event: deltas` / `event: projection.*` / `event: terminal`）与 LiveBus + LLMStreamTap 恢复路径。LobeHub UI ↔ LCA Gateway 的流式契约收敛到标准 `POST /v1/chat/completions` OpenAI ChatCompletion streaming。后端适配前端，不再为恢复语义发明平行 wire。

## 1. 背景

ADR-0096 P2 把 server 改成持久 projection owner：每次 SessionEvent 重算投影，client 通过 `GET /runs/{id}/live` 订阅当前态。落地后五类前端缺陷同时出现——SSE 非实时、reasoning 不可视、工具卡不可视、reconnect 抛 Network Error、刷新丢失消息。根因被诊断为：把「因果时间序」与「当前态」强制塞进同一条 whole-value projection 通道，违反 C7。

ADR-0098 因此把 LLM 流式 deltas 升格为 SessionEvent，并由 `LLMStreamTap` 作为唯一升格入口；`LiveBus` 用 ring + tail 提供 `Last-Event-ID` 续传；SSE 拆成三类 `event:` 名称空间（`deltas` / `projection.*` / `terminal`），各分轴编号。token 字面走 `content_ref → /evidence/{digest}`，SessionEvent 只引 digest。这条路径在纸面上同时满足「可重放因果流」和「可订阅投影通道」，看起来是对 ADR-0096 缺陷的一次到位修复。

实际链路却是：`LLMStreamTap → LiveBus(ring+tail) → SessionEvent 五类词汇 → 3 通道 SSE fan-in → EvidenceRunner → TS SDK 生成器 → LcaRunDriver（~900 LOC）→ lcaJournal（~480 LOC）翻译表`。状态机同时维护双源泵、队列、以及 projection-via-activity 的 terminal 检测；任一拍慢就会悬挂。token 级流被 evidence 间接化后，LLM 实时性反而更差（ADR-0098 自己标出的 F1）。前端为三类 `event:` 写翻译层，任何 wire 微调都要两边补丁对敲。SDK 生成器又让 Python schema 成为第二份事实，SPEC 不再是 SSOT。

最近连续提交都打在 wire 与 LobeHub 补丁上，用户侧症状不变：事件到不了稳定渲染，大半时间不发即停，或需多次刷新。这是架构级问题，不是漏掉的一帧映射。继续在 3 通道 SSE 上堆韧性（EventSource maxRetry、projection 续传、evidence 后备、双轴 seq）只会把补丁加厚。

正确的恢复方向是承认「单一可重放流」和「可订阅投影」是两个产物，不要共用一条 SSE 链。浏览器侧 LobeHub 已经原生消费 OpenAI ChatCompletion streaming（含 `reasoning_content`）；聊天投影应走这条标准面。Journal jsonl、OTel、doctor 继续作为持久化与诊断平面，不再反向驱动 UI wire。

## 2. 决策

### D1. Wire 收敛到 OpenAI ChatCompletion streaming

```
POST /v1/chat/completions
Authorization: Bearer <agent-token>
Content-Type: application/json
Accept: text/event-stream

→ 200 OK
Content-Type: text/event-stream

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"solo",
       "choices":[{"index":0,"delta":{"role":"assistant","content":"...","reasoning_content":"..."},
                   "finish_reason":null}]}\n\n
data: {"id":"chatcmpl-...","object":"chat.completion.chunk",
       "choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_...","function":{"name":"...","arguments":"..."}}]},
                   "finish_reason":null}]}\n\n
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{},"finish_reason":"stop"}]}\n\n
data: [DONE]\n\n

: keepalive   (15s 空闲时的注释帧,无 event/data)
```

字段全部为标准 OpenAI 扩展：`delta.content` 为助手文本增量；`delta.reasoning_content` 为思考（LobeHub `openai.ts` 原生识别）；`delta.tool_calls` 为展示态函数调用（后端已执行完 tool，只 emit `id` / `name` / `arguments`，LobeHub 渲染工具卡但不再 rerun）；`finish_reason` 为 `stop` 终态；`usage` 为终态 token 计数。

不包含任何自定义 `event:` 名称空间、`content_ref → /evidence/{digest}`，以及 `event_seq` / `projection_seq` 分轴 `id`。所有事件共享一条 SSE 链上的 `id:` 即可。

### D2. LobeHub 侧只保留最小 provider 注册

在 `model-runtime/openaiCompatibleFactory.createOpenAICompatibleRuntime()` 注册一个 LCA provider，`baseURL` 指向 `${LCA_HOST}/v1`，`apiKey` 用 `NEXT_PUBLIC_LCA_TOKEN`。`lca_model_catalog` 把 `solo` / `team` / `auto` 标到该 provider。聊天不再走 `executeClientAgent → runLcaJournal → finishLcaChat` 的 agent 协议分支，改为 model-runtime。

删除全部 `lca_*.ts`（Journal / Artifacts / ChatRow / Persist / Error / Consumer_resilience / RunDriver）。`lca_run_driver` 缩减为模型目录注册 + 调流入口替换（~30 LOC）。

### D3. 后端：一个 plugin + 已有 route

新增 `lca/plugins/providers/openai_stream_encoder/`，把 Agent 内部 `record()` 事件单向映射为 OpenAI chunk，无 fan-in：

| 内部事件 | OpenAI chunk |
|---|---|
| `ReasoningDelta` | `delta.reasoning_content` |
| `ReasoningCompleted` | 不发 chunk（handler 自行标记 thinking duration） |
| `StepTextDelta` | `delta.content` |
| `ToolStarted` | `delta.tool_calls[i].{id, name, args}` |
| `ToolInvoked` | 完整 `tool_calls` 段 + 后续 markdown 化产物的 `delta.content` |
| `ToolDenied` | `delta.content` 写一行 `tool denied: ...` |
| `AgentRunFinished` | `finish_reason = "stop"` + `data: [DONE]` |

接入 `gateway/openai_shim.py` 已有 `/v1/chat/completions` 的 stream 分支：`model ∈ {solo, team, auto}` 且 `stream=true` 时走 Agent Loop + encoder；其它 model 仍走非 agent 的 OpenAI 直转。

### D4. `/runs` 路由语义清理

保留 `/runs`、`/runs/{id}`、`/runs/{id}/cancel`、`/runs/{id}/answer`、`/runs/{id}/profile`（对话状态）、`/runs/{id}/doctor`、`/runs/{id}/evidence/{ref}`（诊断 / 产物）。**删除** `/runs/{id}/live`；原三通道 SSE 由 `/v1/chat/completions` 取代。`/journal/live` 继续 503。前端不再 `fetch('/runs/${runId}/live')`。

### D5. 持久化与回放保留

内部 `record()` 仍写 jsonl（`JsonlJournalProjector`）。OTel（有 Langfuse 凭据时）仍投射。`/runs/{id}/doctor` 继续读 Session Spine projection + jsonl seq。CLI 与测试直接消费 jsonl path，不新增 wire 消费者；`journal_consumer` / TS SDK 生成器退出 Provider 注册。

### D6. 插件化保留

`Brain`、`Reasoner`、`Critic`、`SafeExecutor`、`Tool`、`Sandbox`、`Memory`、`Plugin Manifest`、`Sensor` / `Reducer` / Journal 词表均不动。`ChatCompletionStreamEncoder` 是 wire 适配层 plugin，作用域限于 Gateway 流式编码。Profile YAML 不变；`model: solo` 即让 `/v1/chat/completions` 进入 Agent 路径。

### D7. 不增加的事

- 不增加 EventSource maxRetry / backoff；浏览器原生 fetch + abort 足够。
- 不增加 projection channel 续传；结束时一次性 snapshot 给 UI。
- 不增加 evidence store 后备；文本直接 inline。
- 不增加 SDK 自动生成；[设计 spec](../specs/2026-08-29-runs-live-openai-stream-design.md) 是双方 SSOT。
- 不增加 `projection_seq` 与 `event_seq` 双轴。

不提供旧 `/runs/{id}/live` 任何事件名兼容窗口。升级指南见 [run-live.md](../specs/run-live.md) 的 SSE 章节。

## 3. 后果

### 正面

- 流式契约回到 LobeHub 已验证的 OpenAI ChatCompletion 面，token / reasoning / tool 卡走原生渲染，不再维护自创 `event:` 翻译表。
- 删除 LiveBus、LLMStreamTap、三通道 fan-in、evidence 间接化，以及约 3000 LOC 的前端 Journal 驱动与 TS SDK 生成器。
- 内部 Journal-as-Truth 不变：jsonl、OTel、doctor、CLI 回放仍以 `record()` 为事实源，与 UI wire 解耦。
- 认知闭集、双平面、插件 Manifest / Profile 装配均不动；encoder 只是 Gateway 适配层。
- 单一 SSE 链、单工映射，状态机不再同时维护双源泵与 terminal 检测。

### 负面

- `/runs/{id}/live` 立即删除，旧 LobeHub patch 与 Last-Event-ID 续传不再可用，必须与前端最小 provider 注册一起切换。
- `delta.tool_calls` 可能触发 LobeHub 工具重放，必须靠请求体 `tools: []` 与后端 `tool_choice: 'none'` 把 tool 卡限制为展示态。
- 断线不续帧：客户端重发整段 `messages[]`；不保留 `Last-Event-ID`。
- 非 agent 的 `/v1` 管家路径（标题 / embeddings / responses）与 agent 流式路径暂时共用同一 route，靠 `model` + `stream` 分流，裁剪 fallback 覆盖范围留到下一阶段。
- ADR-0096 §13 Deferred、ADR-0097、ADR-0098 的实施库存（5 类 SessionEvent 扩段、consumer contract、TS codegen）作废，已落地代码按计划删除，不可在本 wire 上继续演进。

## 4. 退役（Superseded）

本 ADR 退役下列决策，以其作为 UI 流式契约或恢复路径的部分为准：

| 被退役 | 原承诺 | 现状 |
|---|---|---|
| [ADR-0096](0096-journal-protocol-layer-everything-pluggable.md) **§13 Deferred 路径** | Phase 2 按需演进 transport / consumer / TS SDK；MVA live wire 作为投影订阅面 | §13 Deferred 整段（含后续 M1–M5.5 live 演进）ack 为 superseded；Journal 协议层其它 seam 不在本 ADR 重开 |
| [ADR-0097](0097-event-identity-derivation.md) | 为 live / consumer 契约派生稳定 `event_id`（ULID） | 随自创 SSE 消费者退役；jsonl 内部 identity 若仍需要，退回 Store 局部实现，不再作为跨仓 wire 决策 |
| [ADR-0098](0098-session-spine-deltas.md) | SessionEvent 扩段 + 3 通道 SSE（`deltas` / `projection.*` / `terminal`）+ LLMStreamTap / LiveBus | 整份退役。因果流改由 OpenAI chunk 表达；投影不再走同一条 SSE |

ADR-0037（Journal-as-Truth）、ADR-0038（LLMAdapter 流式事件契约）以及认知闭集相关 ADR **不变**。内部 `record()` 事件词表不因本决策扩段或缩段。

## 5. 实施顺序

设计 SSOT：[2026-08-29-runs-live-openai-stream-design.md](../specs/2026-08-29-runs-live-openai-stream-design.md)。

落地计划（rebase-friendly commits）：[2026-08-29-runs-live-openai-stream.md](../superpowers/plans/2026-08-29-runs-live-openai-stream.md)。

1. `feat(openai-stream): ChatCompletionStreamEncoder plugin + 单工 Bridge`
2. `refactor(openai-shim): solo|team|auto model 走 Agent Loop`（新路径与旧路径并存）
3. `test(e2e): 端到端 OpenAI SSE chunk shape`
4. `refactor(lobehub-patches): 删 lca* + 注册 OpenAI provider`
5. `chore(gateway): 删除 /runs/{id}/live 路由`
6. `chore(harness-session): 删除 live_bus / llm_stream_tap / scope_recorder`
7. `chore(contracts): 退 5 类 delta 扩段`
8. `docs(adr-0099): 记录 cleanup rationale，supersede 0098 / 0097 / 0096 §13`
9. `docs(specs): 更新 run-live.md + lobehub-integration.md`

每一步可独立 revert。验收见设计 spec §7（`POST /v1/chat/completions` smoke + 新集成测试 + `pytest -m 'not real_llm'`）。
