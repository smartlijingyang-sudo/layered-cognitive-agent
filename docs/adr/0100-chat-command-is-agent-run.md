# ADR-0100: 聊天命令面是一次 Agent Run，不是一次模型补全

**Status**: Accepted — 2026-08-29

**Supersedes**: [ADR-0099](0099-runs-live-openai-stream.md) 的聊天 wire（把 Agent Run 伪装成 `POST /v1/chat/completions`）。**不退役** 0099 对 ADR-0098 **三通道载荷** 的否决，也不改 Journal-as-Truth。路径名 `GET /runs/{id}/live` 收回，换成四事件画布。

> **Decision**：用户回车向 Gateway 发一条 Agent **命令**（`POST /runs`）。Gateway 在服务端跑认知 loop。浏览器再 **观察** 这场 Run（`GET /runs/{id}/live`），只收四个 UI 事件。命令与观察分开。LobeHub 是画布。LCA 不是 OpenAI 模型。

## 1. 第一性原理

四句话：

1. **一次用户回合 = 一次 Agent Run。** Loop 在 Gateway 里。对外看不见「调了几次模型」。
2. **浏览器不拥有 loop。** 它不跑工具、不重试空补全、不把 `cordis-creator` 当模型名送给 Responses API。
3. **改系统的请求和看进度的请求不是同一条。** 开工 / 取消 / HIL 是命令；SSE 是观察（C7）。
4. **Journal 是事实，SSE 是画布。** 浏览器不订 Journal，也不订「当前投影快照」。它只收已经能画的增量。

历史上聊天就是 `POST /runs` 开工，再订 live。后来两条弯路：

| 弯路 | 做了什么 | 为什么错 |
|---|---|---|
| ADR-0096 / 0098 | `/live` 三通道（deltas / projection.* / terminal）+ ~900 行 Driver | 坏在**载荷**：因果流和当前态塞进同一条 SSE。路径本身是观察面 |
| ADR-0099 | 删掉 `/live`，聊天改挂 `POST /v1/chat/completions` | 坏在**语义**：一次请求变成「请补全一次」。LobeHub 按模型规则判空、重试、本地 `call_tool`。`ModelEmptyError` 是症状 |

钉回去的是第 1 条和第 3 条。**不是** 0098 的三通道，也不是那个 Driver。

## 2. 决策

### D1. 命令：`POST /runs` → 202

不增加 `/v1/agent/chat`。不把聊天主路径切到 `/v1/sessions`。不把 SSE 焊在 POST 上。

```
POST /runs
{ messages, mode, agent, ... }

→ 202
{ run_id, trace_id, agent, live_url }
```

`live_url` 为 `/runs/{run_id}/live`。Body 沿用现有字段。入口 id 叫 **mode**（`solo` / `team` / `auto` / `cordis-creator`）。选择器仍可能发 `model`，Gateway 当 mode 别名。这些 id **不是** 上游 LLM 名。

取消、HIL 仍是命令：`POST /runs/{id}/cancel`、`POST /runs/{id}/answer`。

### D2. 观察：`GET /runs/{id}/live` → 四个 UI 事件

收回这条路径。载荷不是 Journal，不是投影，不是 OpenAI chunk。

```
GET /runs/{run_id}/live?after=0

→ 200 text/event-stream

event: reasoning
data: {"text":"..."}

event: text
data: {"text":"..."}

event: tool
data: {"name":"bash","phase":"started","detail":"ls -l"}

event: done
data: {"status":"completed"}

: keepalive
```

| event | data | UI |
|---|---|---|
| `reasoning` | `{text}` | 思考块追加 |
| `text` | `{text}` | 助手正文。只含用户可见文字 |
| `tool` | `{name, phase, detail}` | `phase` ∈ `started` / `done` / `denied`。工具已在 Body 执行完 |
| `done` | `{status, error?}` | `status` ∈ `completed` / `failed` / `canceled` / `awaiting_human`。之后关流 |

`after` 是本流已画到的序号，默认 `0`（从头订这场 Run）。HIL 后续再 GET 一次时带上，避免把已画内容重放进气泡。**不是** 0098 的双轴 `event_seq` / `projection_seq`，也不是断线自动续传状态机。刷新中断就中断。

空闲 15s 发 `: keepalive`。

禁止：`chat.completion.chunk`、`data: [DONE]`、`delta.tool_calls`、Journal 类型名、`projection.*`、`content_ref`、决策 JSON。

Journal → 四事件是 Gateway 里一个单向函数。现有 `OpenAIStreamEncoder` 不再是聊天 wire。不要两套映射。

可见文本回退（服务端）：answer 通道为空时用 `DecisionMade.response_text` 或 `AgentRunFinished.output_text` 发一条 `text`。仍为空且失败则只 `done{failed,error}`。客户端读到 `done` 就结束，**不重试**。

HIL：`done.status=awaiting_human` 关流 → 人答 → `POST /runs/{id}/answer` → **再 GET 一次** `/live?after=<已画序号>`。这是第二次订阅，不是把 POST 悬挂到人回来。

### D3. LobeHub：一个协议补丁

补丁 `lca_run_driver`（`deploy/lobehub/patches/runtime/lca_run_driver.py`）做且只做：

1. 对话发送离开 AgentRuntime / `/webapi/chat/openai`。
2. `POST /lca-api/runs` → 拿 `run_id` / `live_url`。
3. `GET` 该 live，把四事件写入当前气泡。不 `call_tool`。
4. `done` 收尾。`failed` 展示 `error`。`awaiting_human` 等用户，answer 后再 GET。abort 时 `POST /runs/{id}/cancel`（此时已有 id）。

注入后，LobeHub 侧暴露两个函数：`runLcaJournal(...)` 投影 Journal → 原生 assistant/tool 消息图；`finishLcaChat(...)` 停转圈/队列/通知。两者由 `streamingExecutor.ts` 串接（见 `lcaJournal.ts` 第 1 步 state_ref-first）。

删除因伪装 OpenAI 才存在的：`drop_lca_chat_hijack`、`openai_guard`。

保留但不是协议：`lca_model_catalog`、`default_model`、`file_proxy_rewrite`（须能转到 `/lca-api/runs` 与 `/lca-api/runs/:id/live`）、以及与 wire 无关的 UI 补丁。

禁止再补丁：`StreamingHandler`、`ClientLLMTransport`、`GeneralChatAgent`、`Reasoning.tsx`。

管家面继续 `/v1/chat/completions`、`/v1/embeddings`、`/v1/responses`，必须是真实上游模型。误带 mode id 时 `resolve_upstream_model` 后直转，**不开** Loop。不再从 `/v1/chat/completions` + `stream=true` 开工。

### D4. 三面（C7）

| 面 | 路径 | 职责 |
|---|---|---|
| 命令 | `POST /runs`、cancel、answer | 改变系统 |
| 观察 | `GET /runs/{id}/live` | 画布，四种事件 |
| 事实 | Journal jsonl、OTel、`GET /runs/{id}/doctor` | 回放与诊断。浏览器不订 |

`/v1/sessions/*` 本 ADR 不动。

## 3. 后果

### 正面

- 回车 = Run，语义与后端一致。
- 命令与观察分开：HIL、取消在 POST 完成时已有 `run_id`。
- LobeHub 不再叠一层 loop；`ModelEmptyError` 离开聊天主路径。
- `/live` 这个名字还在，载荷从「账本+投影」收成「四事件」。

### 代价

- 聊天是两次 HTTP（开工 + 订流）。这是 C7 的正当成本，不是历史包袱。
- 必须有一个 LobeHub 协议补丁。
- 不提供帧级自动重连。
- 工作区里针对 0099 空补全的 encoder 补丁不应合并。

## 4. 退役范围

| 被退役 | 保留 |
|---|---|
| ADR-0099 D1–D3：OpenAI chunk 当聊天 wire；「删除 /live」这条 | ADR-0099 对三通道载荷、LiveBus、LLMStreamTap、evidence 间接化的否决 |
| `/v1/chat/completions` 在 LCA mode + stream 时开工 | 该路由作为管家直转 |
| 「不要劫持 executeClientAgent」 | 劫持极薄，只接 D1+D2 |

ADR-0037、ADR-0038、认知闭集、插件 Manifest **不变**。`record()` 词表不为本 ADR 扩段。

## 5. 实施顺序

协议 SSOT：[run-live.md](../specs/run-live.md)、[lobehub-integration.md](../specs/lobehub-integration.md)、[CUSTOMIZATIONS.md](../../deploy/lobehub/CUSTOMIZATIONS.md)。

1. Gateway：`GET /runs/{id}/live` 输出四事件；`POST /runs` 固定 202 + `live_url`。
2. 从 `/v1/chat/completions` 去掉 Agent 分流。
3. 补丁 `lca_run_driver`；删除 `drop_lca_chat_hijack`、`openai_guard`。
4. 停用聊天路径上的 `OpenAIStreamEncoder`。
5. 浏览器验收：回车 = `POST /runs` + `GET .../live`；无 `/webapi/chat/openai` 当 Agent 流；无 `ModelEmptyCompletion`。

每步可独立 revert。
