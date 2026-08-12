# Agent Timeline (timeline.v1)

## 原则

- **Journal** = 全量 SSOT（jsonl / debug）
- **UI wire** = 仅 timeline.v1 封闭事件集
- **无** `chat.completion.chunk` 承载 agent 循环
- **无** `lca.events` 寄生扩展
- **无** 历史兼容 re-export / alias

## 链路

```text
Journal → TimelineProjector（声明式映射表）
       → timeline.v1 SSE
            ├─ POST /v1/chat/completions?stream  (X-LCA-Stream: timeline.v1)
            └─ POST /v1/agent/runs + GET .../timeline
       → AgentTimelineTransport（LobeHub）
       → content / Thinking / tools / files
```

## gateway 模块

| 文件 | 职责 |
|------|------|
| `timeline/protocol.py` | 版本、白名单、SSE 编码 |
| `timeline/projector.py` | journal → timeline |
| `timeline/stream.py` | 异步 SSE 生成 |
| `timeline/routes.py` | agent run HTTP |
| `openai_compat_api.py` | agent 流走 timeline；title 仍 OpenAI 形 |

## 白名单

`run.start` · `thinking.delta` · `thinking.end` · `answer.delta` · `tool.start` · `tool.delta` · `tool.end` · `run.end`

## 前端

- `AgentTimelineTransport` — 解析 timeline SSE，更新消息
- 已移除 lca.events 相关补丁（openai_stream 短路等）
- 环境：`NEXT_PUBLIC_LCA_GATEWAY` 或 `OPENAI_PROXY_URL`（去掉 `/v1`）指向 gateway

## 验证

```bash
uv run pytest tests/test_timeline_projector.py tests/test_lobehub_tool_wire.py -q
# 需 gateway 运行时：
python scripts/e2e_timeline_smoke.py
```
