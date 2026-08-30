# Run Live

一次用户消息 = 一次 Run。一次 Run 有一本 Journal。Journal 的读者是 jsonl（及可选 OTel），**不是**浏览器。

聊天分两面：**命令** `POST /runs` 开工，**观察** `GET /runs/{id}/live` 画四个 UI 事件。**LCA 拥有 agent loop**；LobeHub 只渲染，不 invoke 工具，不把这次请求当成一次模型补全。

协议决策：[ADR-0100](../adr/0100-chat-command-is-agent-run.md)。持久化：[ADR-0037](../adr/0037-journal-as-truth.md)。集成：[lobehub-integration.md](lobehub-integration.md)；补丁：[CUSTOMIZATIONS.md](../../deploy/lobehub/CUSTOMIZATIONS.md)。

不恢复 ADR-0098 三通道载荷。不把 Agent 伪装成 `POST /v1/chat/completions`（ADR-0099 聊天 wire 已退役）。`/live` 这条路径收回，只承载画布事件。

## 链路

```
用户回车
  └─ runLcaJournal + finishLcaChat (注入自 lca_run_driver 补丁)
       ├─ POST /runs                 202 {run_id, live_url}
       └─ GET  /runs/{id}/live       四事件
            ▼
Starlette :8765
  POST /runs                         create_and_dispatch
  GET  /runs/{id}/live               UI 编码器
  POST /runs/{id}/cancel|answer
  GET  /runs/{id} / doctor / profile
  POST /v1/chat/completions          管家直转；不开 Agent
            ▼
Agent / Team
  record(...) → jsonl
  UI 编码器 → reasoning | text | tool | done
```

| 面 | 路径 | 谁用 |
|---|---|---|
| 命令 | `POST /runs` → 202 | 一次回车 = 一次 Run。mode = `solo` / `team` / `auto` / `cordis-creator` |
| 观察 | `GET /runs/{id}/live` | 画布。四种事件 |
| 管家 | `/v1/chat/completions`、`/v1/embeddings`、`/v1/responses` | 标题、embeddings。直连上游，**不开** loop |
| 状态 | `GET /runs/{id}`、cancel / answer / profile / doctor | 生命周期、HIL、诊断 |

`agent: { id, name }` 是隔离键。缺省 `{ id: "solo", name: "助手" }`。

## HTTP

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/runs` | 开工。`202 {run_id,trace_id,agent,live_url}` |
| `GET` | `/runs/{id}/live` | 画布 SSE。`?after=N` 跳过已画序号，默认 0 |
| `GET` | `/runs/{id}` | 快照：status / error / mode |
| `GET` | `/runs/{id}/doctor` | 诊断 |
| `POST` | `/runs/{id}/cancel` | 取消。abort 时必须打 |
| `POST` | `/runs/{id}/answer` | HIL 续跑，然后再次 GET live |
| `GET` | `/runs/{id}/profile` | boot 期 snapshot |
| `GET` | `/files/{id}` | 产物 |
| `POST` | `/v1/chat/completions` | **仅管家**。真实上游模型 |

Next rewrite：`/lca-api/runs`、`/lca-api/runs/:path*`、`/runs/:path*`、`/files/:path*` → gateway。

## SSE

```
GET /runs/{id}/live?after=0
Accept: text/event-stream

→ 200
Content-Type: text/event-stream

event: reasoning
data: {"text":"..."}

event: text
data: {"text":"..."}

event: tool
data: {"name":"bash","phase":"started","detail":"ls"}

event: done
data: {"status":"completed"}

: keepalive
```

`phase` ∈ `started` / `done` / `denied`。`done.status` ∈ `completed` / `failed` / `canceled` / `awaiting_human`。

服务端可见文本回退：answer 通道为空时用 `DecisionMade.response_text` 或 `AgentRunFinished.output_text`。客户端读到 `done` 即结束，不重试。

禁止：OpenAI chunk、`[DONE]`、`delta.tool_calls`、`projection.*`、`content_ref`、决策 JSON、Journal 类型名。

不要帧级 `Last-Event-ID` 自动续传。`after` 只用于「第二次订阅从哪接着画」（HIL）。

## 前端

`runLcaJournal`：`POST /lca-api/runs` → `GET live_url` → 写气泡。不 `call_tool`。`awaiting_human` 后 `POST .../answer`，再 GET `?after=<已画>`。配合 `finishLcaChat` 停转圈。

**体积说明**：协议面（HTTP + 4 个 SSE 事件）保持极小。LobeHub 侧实现面已外溢到 `src/store/chat/agents/transports/` 下的 8 个 TS 文件（`LcaRunDriver.ts` 主文件 + 投影/工件/收尾工具），目前约 1400 LOC。约束的不是绝对行数，而是"协议事件集不增不减 + LobeHub transports 目录之外不出现 LCA 业务代码"。见 ADR-0100 §D3 注。

选择器只暴露 mode：`solo` / `team` / `auto` / `cordis-creator`。

## 持久化

`record()` 写 `traces/runs/{id}.jsonl`，与 SSE 解耦。doctor / CLI 读 jsonl。Casting / Delegation 不上聊天流。

## 状态

| 场景 | 行为 |
|---|---|
| 用户停止 | abort live **并且** `POST /runs/{id}/cancel` |
| 断线 | 不续帧；已写入消息库的内容保留 |
| `awaiting_human` | 关 live；answer 后再 GET 一次 |
| 终态 | Registry TTL 淘汰内存 Run；jsonl 仍在 |

## 排障

```
RUN=$(curl -s -H "Authorization: Bearer lca-local" \
  -H "Content-Type: application/json" \
  -d '{"mode":"solo","messages":[{"role":"user","content":"hello"}]}' \
  localhost:8765/runs | jq -r .run_id)

curl -N -H "Authorization: Bearer lca-local" \
  localhost:8765/runs/$RUN/live
```

| 现象 | 先查 |
|---|---|
| 浏览器打 `/webapi/chat/openai` 当聊天 | `lca_run_driver` 补丁没接上 |
| jsonl 没有事件 | `record()` |
| jsonl 有、live 没有 | UI 编码器；路由是否重新挂上 `/live` |
| `ModelEmptyCompletion` | 仍在走 LobeHub AgentRuntime |
| 工具被前端重跑 | 驱动是否 `call_tool` |

## 关联

- [ADR-0100](../adr/0100-chat-command-is-agent-run.md) — 现行命令 / 观察面
- [ADR-0099](../adr/0099-runs-live-openai-stream.md) — 已退役的 OpenAI 伪装；三通道否决仍有效
- [lobehub-integration.md](lobehub-integration.md)
