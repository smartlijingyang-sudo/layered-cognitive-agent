# 主动消息机制 · 前端对接契约

> 后端：layered-cognitive-agent（本仓库）｜前端：LobeHub fork（独立仓库）
> 本文档是前后端契约，前端按此实现渲染与刷新。

## 1. 两种投递形态

| 形态 | 触发场景 | 前端拿消息的方式 |
|---|---|---|
| RESPONSE_CARRIED | onboarding 起名完成（`POST /v1/onboarding/naming/settle`） | **响应 JSON** 里直接取，无需额外请求 |
| SESSION_APPEND | 定时任务 / hook 事件（调度器 tick 触发） | 从 session 消息列表读取（见 §3） |

设计原则：**不新开消息协议**。两种形态都复用已有的 surface 事件
taxonomy（`surface/assistant_message`）与已有 HTTP 响应，前端只需
支持"**无前置用户消息的 assistant 气泡**"的渲染。

## 2. RESPONSE_CARRIED：settle 响应字段

`POST /v1/onboarding/naming/settle` 响应新增字段：

```jsonc
{
  "ok": true,
  "assistant_id": "asst_demo",
  "name": "星澜",
  "vibe": "敏锐专注",
  "reaction": "🎉",
  "welcome_message": "你好，朋友！我是你的专属助理。你可以直接叫我 星澜，…"
}
```

- `welcome_message: string | null` —— 欢迎气泡正文；为 `null` 时不渲染
  （后端管线异常 fail-soft，主流程不受影响）。
- 前端行为：settle 成功后，若 `welcome_message` 非空，**直接渲染为一条
  assistant 气泡**，不要再调一次 `/v1/onboarding/welcome`。
- 这就是之前 bug 的根因：旧响应没有该字段，前端无从得知有欢迎消息。

## 3. SESSION_APPEND：session 消息事件格式

调度器产生的消息 append 进目标 session，事件：

```jsonc
{
  "type": "surface/assistant_message",
  "data": {
    "turn": -1,              // 哨兵：非 run 上下文的主动消息（正常 run 的 turn >= 0）
    "step": 0,
    "role": "assistant",
    "content": "该喝水了",
    "tool_calls": null,
    "usage": null,
    "proactive": true,       // 前端可用此区分主动消息（如不同气泡样式）
    "proactive_id": "job1-1727846400000",  // 幂等键，去重用
    "proactive_source": "routine_cron"     // onboarding_completed | routine_cron | hook_event | manual
  }
}
```

前端行为：

1. **渲染**：消息列表遇到 `data.proactive == true` 的 assistant 消息，
   按普通 assistant 气泡渲染（允许前面没有 user 消息）。
2. **去重**：用 `proactive_id` 去重（重试/重放可能导致重复投递）。
3. **刷新**：后端暂无服务端推送通道，前端需**主动拉取** session 消息列表
   （轮询或在已有 SSE/websocket 通道上订阅 session 事件）。
   建议轮询间隔 ≥ 30s，`proactive` 消息低频，不值得长连接。
4. **未经检索标注**：若 `content` 末尾带 `（本次内容未经持久记忆检索，仅供参考）`，
   原样展示（这是后端在无记忆源时的诚实标注，不要 strip）。

## 4. 消息读取 API（已有，无需新增）

- OpenAI 兼容：`POST /v1/chat/completions`（`lca/plugins/transport/webserver/handlers/openai/endpoints.py`）
- session 历史：`RunSessionWriter.derive_messages()` 投影（后端内部，前端经由上述 API 消费）

## 5. 不做的事（有意为之）

- 不新增 websocket/SSE 推送端点（YAGNI：当前 proactive 消息低频，轮询足够；
  高频推送是另一个议题）。
- 不在前端为"主动"单独开一套消息协议（复用 session 消息列表即可）。
