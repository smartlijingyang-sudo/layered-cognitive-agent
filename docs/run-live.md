# Run Live

一次用户消息 = 一次 Run。一次 Run 有一本 Journal。Journal 有两个读者：jsonl、LiveTail。

浏览器订同一本 `/live`。SSE `event:` = Python 类名 = jsonl `event_type`。前端 `runLcaJournal` 把 Journal 译成 LobeHub 原生 Thinking 和工具卡。**LCA 拥有 agent loop**；浏览器不跑 `GeneralChatAgent`，也不 invoke 工具。

这是聊天投影的现行说明。原则来自 ADR-0037 Journal-as-Truth。集成与启动见 [lobehub-integration.md](lobehub-integration.md)；补丁清单见 [CUSTOMIZATIONS.md](../deploy/lobehub/CUSTOMIZATIONS.md)。

## 链路

```
用户回车
  └─ executeClientAgent(solo | team | auto)
       └─ runLcaJournal                         deploy/lobehub/patches/runtime/lca_run_driver.py
            │  POST /lca-api/runs               Next rewrite → POST /runs
            │  GET  /lca-api/runs/{id}/live     Last-Event-ID
            ▼
Starlette :8765                                 gateway/app.py 只注册路由
  POST /runs     ingress → RunSession → schedule_run
  GET  /live     LiveTail → stamped_to_sse_frame
            │
            ▼
ObservabilityHub                                只经 create_observability() 装配
  JsonlJournalProjector   traces/runs/{id}.jsonl
  LiveTail                环形缓冲 + 套接字
  OtelProjector           有 Langfuse 凭据才挂
            │
            ▼
Agent / Team
  TelemetryLLMAdapter.stream
    record(LlmCallStarted | ReasoningDelta | StepTextDelta)
  SafeExecutor
    record(ToolStarted{plugin_state} | SandboxOutputDelta | ToolInvoked | ToolDenied)
  收尾
    record(AgentRunFinished | TeamRunFinished)
            │
            ▼
runLcaJournal                          deploy/lobehub/patches/runtime/LcaRunDriver.ts
  parseSseBlock / readSse     订流
  projectJournalFrame         Journal → 投影值
  openTurn / tool 子消息      同一说话人一条 assistant；原生 conversation-flow 收组
finishLcaChat                          patches/runtime/lcaFinishChat.ts
  停转圈 / 队列 / 话题状态 / 通知
  *Finished 不是 EOF；tail close 才 sealRow
```

两条 HTTP 面不相交。意图定面，不是模型名定面。

| 面 | 路径 | 谁用 |
|---|---|---|
| Run | `POST /runs` + `GET /runs/{id}/live` | 某个 **AgentRef** 干活。附件是 `messages[].files` |
| Shim | `/v1/chat/completions` `/v1/embeddings` `/v1/responses` | 标题、话题、embeddings。直连上游补全，**不是 agent**，无记忆 |

`POST /runs` 必带 `agent: { id, name }`。`id` 是隔离键（journal / sandbox / inflight / Langfuse session）；两个 LobeHub `agentId` 说同一句话也是两本 Run。缺省 `{ id: "solo", name: "助手" }`。

`/v1` 通的是管家函数，不要在 shim 里再包一层假 agent。LobeHub 里真正的对话体（含小助手）走 `executeClientAgent`，带上自己的 `agentId`。

Hub 收尾分两拍：`release()` 先关 LiveTail / jsonl（SSE 结束）；`dispose()` 在线程里关 Langfuse，超时放弃。聊天面不等导出器。

## HTTP

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/runs` | 开工。body `{ messages, model, agent }`。202 `{ run_id, trace_id, agent, live_url }` |
| `GET` | `/runs/{id}/live` | Journal SSE。认 `Last-Event-ID` |
| `GET` | `/runs/{id}` | 快照：status / error / mode |
| `GET` | `/runs/{id}/doctor` | `doctor.v1`：H1 开工、H2 记账、H3 转播。H4/H5 在浏览器 |
| `POST` | `/runs/{id}/cancel` | 取消。abort fetch 时必须打 |
| `POST` | `/runs/{id}/answer` | HIL 续跑。LiveTail 在 `waiting_input` 时不关 |
| `GET` | `/files/{id}` | 产物 |

Next rewrite：`/lca-api/runs`、`/lca-api/runs/:path*`、`/runs/:path*`、`/files/:path*` → gateway。

## SSE

```
id: {seq}
event: {Journal 类名}
data: { stamped_to_record(stamped) + domain }

: keepalive          ← 空闲 15s，注释帧，无 id
```

`data` 与 jsonl 同行：`schema` / `seq` / `ts` / `scope` / `event_type` / `event`。前端从 `event` 取字段。

`LiveGap` 是 LiveTail 唯一允许发明的名字：环形缓冲淘汰了订阅者要的 seq。不是 Journal 事件，不进 jsonl。前端打日志，不中断。

## 前端映射

入口：`executeClientAgent` 对 `solo` / `team` / `auto` 进 `runLcaJournal`，收尾走 `finishLcaChat`（LobeHub 壳，不是 AgentRuntime）。一次 POST，订一本 `/live`。投影成 **原生消息图**：同一说话人一条 `assistant`，每个工具一条 `role=tool` 子消息（`result_msg_id` + `toolCalling` operation）。用户文件卡只保留同名产物的最后一版。`conversation-flow` 自己收成 `assistantGroup`。换说话人时新开一条链（parent = 用户消息）。`StreamingHandler` 只管当前块的活流；`optimisticUpdateMessageContent` 落库；`sealRow` 发现库里仍是 `...` 就再写一次。未知 `event` 忽略。

| SSE `event` | 行为 |
|---|---|
| `LlmCallStarted` | 封上一块，新开一条 assistant。同说话人 parent = 上一条 tool；换说话人 parent = 用户消息。第一条可复用占位行 |
| `ReasoningDelta` | `{ type: 'reasoning', text }` |
| `ReasoningCompleted` | 收起 Thinking；`duration_ms` 写入该块 `reasoning.duration` |
| `StepTextDelta` 且 `channel=answer` | `{ type: 'text', text }`。相对路径图按 ledger/收获文件改写成 `/files/...`。`decision` 丢弃 |
| `ToolCallStreaming` | 与 `ToolStarted` 同一张卡（`tool_call_id` = 后续 `invocation_id`）。无卡则建；有卡则更新 `arguments` / `plugin_state`（代码边生成边出现） |
| `ToolStarted` | 同上 id：补全 `plugin_state`（完整 code/command）。新建 `role=tool` 子消息（若还没有） |
| `SandboxOutputDelta` | 补 tool 行 `pluginState.output/stderr` 与当前卡 `result.state`；有输出后切到 Render，stdout 增量可见 |
| `ToolInvoked` | `plugin_state` + `files` 为卡片 SSOT。Live SSE **抹掉** `result_preview` / `arguments_preview`（只留 jsonl/OTel） |
| `ToolDenied` | 写 `result.error`；`failOperation`；不进答案正文 |
| `AgentRunFinished` / `TeamRunFinished` | 写 error（若有）。**不关流**；`handleFinish` 发生在 tail close |
| `LiveGap` | `console.warn`；不中断 |
| 其它 | 忽略（Casting / Delegation / RunInsight 属于 jsonl / Langfuse） |

工具坐标 SSOT：`gateway/runs/wire.py` 的 `WIRE`。补丁生成进 Driver；`tests/test_run_wire.py` 锁两边相等。`import_skill` 的 `plugin_state.identifier` 有值时 apiName 改为 `importFromMarket`。

`plugin_state` 在 `SafeExecutor` 出厂（`tool_ui_state`）。Gateway 不改写。
`result_preview` / `arguments_preview` 只进 jsonl 与 OTel；`stamped_to_sse_frame` 抹掉后再上 Live。浏览器和 prompt 读不到。

## 后端文件

```
gateway/
  app.py                   组合根：路由 + 注入
  cors.py                  CORS
  modes.py                 solo / team / auto
  assemble.py              build_solo_agent / build_runnable_team
  openai_shim.py           标题 / embeddings / responses
  files.py                 GET /files/{id}
  runs/
    api.py                 create / live / get / cancel / answer / doctor HTTP
    session.py             RunSession + RunRegistry
    execute.py             装配、跑、唯一 finalize
    ingress.py             messages[] → RunInput
    ingest.py              附件
    live.py                LiveTail(JournalProjector)
    doctor.py              diagnose()
    wire.py                工具名 → (identifier, apiName)

deploy/lobehub/patches/runtime/
  LcaRunDriver.ts          投影：SSE → 原生 assistant/tool 图
  lcaJournal.ts            解析 SSE / Journal → 投影值
  lcaArtifacts.ts          文件规范化 + markdown href 改写
  lcaFinishChat.ts         LobeHub 壳：转圈 / 队列 / 通知
  lcaChatRow.ts            占位符对账
  lca_run_driver.py        拷贝 TS、生成 lcaWire.ts、挂钩
```

`layer0` 的 `stamped_to_sse_frame` 是线上编码。Gateway 的读者是 LiveTail，不另挂 `SSEJournalProjector`。

## 状态

| 场景 | 行为 |
|---|---|
| 用户停止 | abort fetch **并且** `POST /runs/{id}/cancel` |
| 断线 | 用最后一帧 `id` 重开 `/live` |
| `waiting_input` | LiveTail 不关；Driver 在当前消息 metadata 标 `waiting_input`；`POST /runs/{id}/answer` 后续跑。Driver 不代填答案 |
| 产物闭包 | `finalize` 可在 `*Finished` **之后**再记一帧 `StepTextDelta(channel=answer)`。前端读到 tail close，不把 Finished 当套接字结束 |
| 终态会话 | Registry 按 TTL（1h）和上限（128）淘汰内存里的终态 Run；jsonl 仍在，doctor 可读 |

## 排障

```
curl -s localhost:8765/runs/$ID/doctor | jq '{broken_hop,summary,factory}'
jq -c '{seq,event_type}' traces/runs/$ID.jsonl
curl -N -H "Last-Event-ID: 0" localhost:8765/runs/$ID/live | head
```

| 现象 | 先查 |
|---|---|
| jsonl 没有事件 | SafeExecutor / LLM adapter 的 `record()` |
| jsonl 有、/live 没有 | LiveTail、`Last-Event-ID`、doctor H3 |
| live 有、卡片没有 | Driver 映射表 / `WIRE` / `transformToolCalls` |
| 卡片字段不对 | `plugin_state` 出厂（layer1 `tool_ui_state`），不是 gateway |
