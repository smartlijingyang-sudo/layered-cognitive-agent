# Run Live

一次用户消息 = 一次 Run。一次 Run 有一本 Journal。Journal 有两个读者：jsonl 文件、LiveTail。

```
POST /runs            开工
GET  /runs/{id}/live  Journal SSE（event: = Python 类名 = jsonl event_type）
GET  /runs/{id}       快照
GET  /runs/{id}/doctor  broken_hop
POST /runs/{id}/cancel
POST /runs/{id}/answer
```

前端 `JournalTransport` 把帧喂给 LobeHub 原生 `StreamingHandler`。工具卡用 Journal 里已经写好的 `plugin_state`。

HIL：`GET /runs/{id}` 的 `status=waiting_input` 时 LiveTail **不关**。Transport 不把暂停当 error；`POST /runs/{id}/answer` 后用 `Last-Event-ID` 继续订同一本账。断线同样用最后一帧 `id` 重开 `/live`。

`timeline.v1` 已废。不要再找 `thinking.delta`、`lca.events`、`AgentTimelineTransport`。

排障：

```
curl -s localhost:8765/runs/$ID/doctor | jq '{broken_hop,summary,factory}'
jq -c '{seq,event_type}' traces/runs/$ID.jsonl
curl -N -H "Last-Event-ID: 0" localhost:8765/runs/$ID/live | head
```
