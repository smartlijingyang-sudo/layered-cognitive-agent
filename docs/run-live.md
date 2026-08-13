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
runLcaJournal
  parseSseBlock / readSse     订流、Last-Event-ID、id: 与多行 data
  projectJournalFrame         Journal → 投影值（纯函数）
  openTurn / applyProjected   气泡 + StreamingHandler
  *Finished 不是 EOF；tail close 才 finishTurn
```

两条 HTTP 面不相交：

| 面 | 路径 | 谁用 |
|---|---|---|
| Run | `POST /runs` + `GET /runs/{id}/live` | Agent 干活 |
| Shim | `/v1/chat/completions` `/v1/embeddings` `/v1/responses` | 标题、系统小助手 |

## HTTP

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/runs` | 开工。body `{ messages, model }`。202 `{ run_id, trace_id, live_url }` |
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

入口：`executeClientAgent` 对 `solo` / `team` / `auto` 短路进 `runLcaJournal`。一次 POST，订一本 `/live`，按 `LlmCallStarted` 开气泡。未知 `event` 忽略。

| SSE `event` | 行为 |
|---|---|
| `LlmCallStarted` | 当前气泡已有内容或工具卡 → `openTurn()`；否则确保有一条 assistant |
| `ReasoningDelta` | `{ type: 'reasoning', text }` |
| `ReasoningCompleted` | 忽略（下一条 text/tool 会收起 Thinking） |
| `StepTextDelta` 且 `channel=answer` | `{ type: 'text', text }`。`decision` 丢弃 |
| `ToolStarted` | `{ type: 'tool_calls' }`。`function.name` = `identifier____apiName`；arguments 从 `plugin_state` 抽 |
| `SandboxOutputDelta` | 补当前卡 `result.state.stdout/stderr` |
| `ToolInvoked` | `plugin_state` 进 `result.state`；停该卡动画 |
| `ToolDenied` | 写 `result.error`；不进答案正文 |
| `AgentRunFinished` / `TeamRunFinished` | 写 error（若有）。**不关流**；`handleFinish` 发生在 tail close |
| `LiveGap` | `console.warn`；不中断 |
| 其它 | 忽略（Casting / Delegation / RunInsight 属于 jsonl / Langfuse） |

工具坐标 SSOT：`gateway/runs/wire.py` 的 `WIRE`。补丁生成进 Driver；`tests/test_run_wire.py` 锁两边相等。`import_skill` 的 `plugin_state.identifier` 有值时 apiName 改为 `importFromMarket`。

`plugin_state` 在 `SafeExecutor` 出厂（`tool_ui_state`）。Gateway 不改写。

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
