# Mangli 网关前端对接接口说明

面向前端联调的 HTTP / WebSocket 契约。事实源是实现，不是本文：字段冲突时以 `lca/plugins/transport/webserver` 下的路由与 `lca/contracts/transport/agent_stream_event.py` 为准。

## 1. 登录态与鉴权

Base URL 由部署方给出（示例 `http://<host>:<port>`）。前端**不需要实现任何鉴权逻辑**，也拿不到、用不着应用侧的身份标识。

- 登录态由公司门户下发（cookie 与门户要求的 header），浏览器随请求自动携带；
- 公司网关校验登录态、换算出用户身份，再把请求转发到应用；
- 应用收到的是网关认定的身份。前端自己塞身份头不会被采信，网关注入的才有效。

唯一前提：**请求要带上登录态**。同源 `fetch` 默认带 cookie；前后端不同域时需 `credentials: 'include'`，并在网关放行对应 Origin。WS 升级同样要过网关，跨域的 `wss://` 若因此丢 cookie，网关会在升级阶段就拒绝，表现为握手直接失败而不是 `auth_failed` —— 这类问题先查域名与网关配置，不是 token 的锅。

### 1.1 前端唯一要自己处理的凭据：WS 握手的 ws_token

HTTP 请求带上门户登录态就够了，事件流还多一步：WS 升级由网关照常校验登录态，但连接建立后的帧协议由客户端库固定（`AgentStreamClient` 的 `auth` 帧），浏览器也无法给 `new WebSocket(url)` 加自定义请求头。因此应用侧另发一个 token，专门用于 run 级授权。

token 两个来源：

| 来源 | 用途 |
|---|---|
| `POST /runs` 响应中的 `ws_token` | 创建任务后立刻收流，最常用 |
| `POST /v1/runs/{run_id}/ws-token` | 重连时单独换一个（原 token 过期或已丢） |

两者是同一个签发函数产生的同一种 token，默认 300 秒有效，每次 `jti` / `iat` / `exp` 不同。**未过期可复用；换 run 或超过 5 分钟必须重签。**

完整流程：

```text
① POST /runs ────────────────► 应用用私钥签发 JWT
   ◄── 202 {run_id, ws_token}      sub=当前用户、operation_id=run_id、exp=+300s
② WS 升级 ── gateway ───────► 网关校验登录态，转发升级请求
③ 客户端发 {type:'auth', token} ► 应用验签 → 校验 operation_id == run_id → 校验 sub == run 创建者
   ◄── {type:'auth_success'}      任一步失败 → {type:'auth_failed', reason} 后断开
④ 之后正常收发事件               过期只在握手时检查一次，连接已建立后不会因 300s 到期被踢
⑤ 重连：POST /v1/runs/{id}/ws-token ► 重新签发；run 的事件流已回收则 404
```

注意 `exp` 只在握手时校验：一条已经建立的连接可以长时间保持，不需要中途换 token；只有**新建连接**才需要有效 token。而 `ws-token` 接口要求该 run 的事件流还在 Redis 里（保留 2 小时），所以重连窗口就是这 2 小时。

服务端握手校验三件事，任一不符回 `auth_failed` 并断开：

1. 签名有效且未过期（`reason: "token expired"`）；
2. token 绑定的 `operation_id` 等于 URL 里的 `run_id`，即**一个 token 只对一个 run 有效**（`reason: "operation_id mismatch"`）；
3. token 里的 `sub` 等于该 run 的创建者（`reason: "user_id mismatch for run"`）。

### 1.2 401 / 403 怎么处理

| 状态 | 含义 | 前端处理 |
|---|---|---|
| 401 | 登录态缺失或已失效（网关或应用侧均可能返回） | 引导重新登录，不要重试 |
| 403 | 该 run 属于其他用户（同一浏览器切过账号时常见） | 不重试，提示无权限 |
| 502 / 503 | 服务端依赖不可用 | 提示稍后重试，必要时报障 |

`/health` 免鉴权可探活。`/playground*` 免鉴权，但那是**服务端自测页**，不是接口、不构成契约，前端不要调用也不要依赖，建议网关侧直接屏蔽。

## 2. 主流程

```text
① POST /files            上传附件（可选）→ 拿到 files[].url
② POST /runs             提交问题 → 202 {run_id, ws_token}
③ WS /v1/runs/{run_id}/ws
     → {type:'auth', token}
     → {type:'resume', lastEventId:'0', wantStatus:true}
     → 持续收 {type:'agent_event', id, event:{...}}
④ 若出现 step_start.phase == "human_approval"：
     POST /runs/{run_id}/answer  → 重连 WS（token 未过期直接复用，否则先换）
   若要中途终止：
     POST /runs/{run_id}/cancel
⑤ 收到 agent_runtime_end 后服务端发 {type:'session_complete'} 并关闭 socket
```

## 3. 上传附件 `POST /files`

`Content-Type: multipart/form-data`，字段名固定为 `files`，可重复以承载多文件。

| 限制 | 值 |
|---|---|
| 单文件 | 100 MB |
| 单请求文件数 | 50 |

成功 `200`：

```json
{
  "files": [
    {
      "attachment_id": "file_9f2c1a4b7d33",
      "url": "/files/file_9f2c1a4b7d33",
      "name": "月报模板.xlsx",
      "size_bytes": 182734,
      "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "source": "https://<fileservice>/..."
    }
  ]
}
```

`source` 是公司文件服务返回的原始地址（仅供排查，不要展示给用户）。后续把 `url` 放进 `messages[].files[]` 提交。

错误体是 OpenAI 风格，字段名是 `message`（与 §1.3 鉴权错误的 `detail` 不同）：

```json
{ "error": { "message": "monthly.xlsx exceeds 104857600 bytes", "type": "invalid_request_error", "code": "file_too_large" } }
```

| HTTP | code | 含义 |
|---|---|---|
| 400 | `missing_files` | 没有 `files` 字段或不是文件 |
| 400 | `too_many_files` | 超过 50 个 |
| 400 | `file_too_large` | 单文件超过 100 MB |
| 400 | `invalid_file` | 声明 MIME 与文件头不符（防伪装） |
| 502 | `fileservice_unavailable` / `fileservice_contract_violation` / `fileservice_error` | 公司文件服务故障 |
| 503 | `fileservice_unconfigured` | 服务端未配置文件服务凭据 |
| 503 | `file_store_unavailable` | 本地 FileStore 未挂载 |

上传是"全部成功或全部失败"：任一文件失败，本次请求不在服务端留下任何文件。

## 4. 创建任务 `POST /runs`

请求体（JSON）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `messages` | 是 | OpenAI 风格消息数组，见下 |
| `mode` | 否 | 运行模式，默认 `solo`；可选值由部署 profile 的模式目录决定 |
| `options` | 否 | 透传给 run 的扩展参数（如 `{"project_id": "..."}`），由 profile/插件消费 |
| `topic_id` | 否 | 会话主题 id；同一 topic 的连续问答会据此补齐上下文 |
| `assistant_id` | 否 | 绑定助理（字符集 `[A-Za-z0-9][A-Za-z0-9_-]*`） |
| `run_id` | 否 | 客户端指定 run id（恢复/幂等场景用） |
| `resume_approval` | 否 | 审批恢复，见 §6 的替代路径 |

`messages[]` 元素：

```json
{
  "role": "user",
  "content": "帮我核对工号并生成本月报告",
  "files": [
    { "url": "/files/file_9f2c1a4b7d33", "name": "月报模板.xlsx", "mime_type": "application/vnd...", "size": 182734 }
  ]
}
```

- `role` 取 `user` / `assistant`；服务端取**最后一条 user 消息**作为本轮任务，之前的消息作为上下文。
- 上下文上限：最多 12 条消息、6000 字符，超出部分丢弃，不会报错。
- `files` 只对最后一条 user 消息生效，`url` 用 §3 返回的相对路径即可（服务端走本地分支，不会回源）。
- 只有附件没有文字时，服务端使用默认任务文案"请查看用户上传的附件"。

成功 `202`：

```json
{
  "run_id": "run_1a2b3c4d",
  "trace_id": "run_1a2b3c4d",
  "agent": { "id": "lca-local", "name": "LCA" },
  "live_url": "/runs/run_1a2b3c4d/live",
  "ws_token": "<JWT，5 分钟有效>"
}
```

错误：`400`（messages 非数组 / 缺 user 消息 / `assistant_id` 非法 / `resume_approval` 缺 `approvalId`）、`401`/`403`（鉴权与归属）、`404`（`assistant_not_found`）、`503`（`jwt_secret_unconfigured`，服务端未配 JWT 私钥）。

## 5. 事件流 `WS /v1/runs/{run_id}/ws`

### 5.1 握手顺序

1. 建立连接后**第一帧必须**是 `{"type":"auth","token":"<ws_token>"}`；否则服务端回 `auth_failed` 并断开。
2. 收到 `{"type":"auth_success"}` 后**紧接着**发 `{"type":"resume","lastEventId":"0","wantStatus":true}`；不发这一帧服务端会一直等到 30s 心跳才回放历史。
3. 之后由服务端推送事件；客户端每 30s 发一次 `{"type":"heartbeat"}`，服务端回 `{"type":"heartbeat_ack"}`。

`wantStatus: true` 时服务端在回放结束后补一帧 `{"type":"resume_complete","status":"..."}`；status 已是终态（`completed` / `error` / `interrupted`）时会紧接 `session_complete` 并关闭连接；`waiting_input` 不算终态，连接保持。

### 5.2 服务端帧

| `type` | 说明 |
|---|---|
| `auth_success` / `auth_failed {reason}` | 握手结果 |
| `resume_complete {status}` | 历史回放结束 |
| `agent_event {id, event}` | 业务事件，`id` 是 Redis 流 id，用于断线续传 |
| `heartbeat_ack` | 心跳应答 |
| `session_complete` | 本段事件流结束（服务端随后关闭连接） |

### 5.3 业务事件

`agent_event.event` 形如 `{type, data, operationId, stepIndex, timestamp}`。前端需要处理的分支：

| `event.type` | 关键字段 | 用途 |
|---|---|---|
| `stream_start` | `data.assistantMessage` | 新建助手消息气泡 |
| `stream_chunk` | `data.chunkType` + `data.content` / `data.reasoning` / `data.toolsCalling` | 增量渲染：`text` 正文、`reasoning` 思考、`tools_calling` 工具准备 |
| `tool_start` | `data.toolCalling.{identifier, apiName, arguments, id}` | 展示工具调用卡片 |
| `tool_end` | `data.isSuccess`, `data.result` | 工具结果 |
| `step_start` | `data.phase`, `data.requiresApproval`, `data.pendingToolsCalling` | 阶段切换；**暂停信号见 §6** |
| `agent_runtime_end` | `data.finalState`, `data.reason`, `data.artifactClosure` | 本轮结束；`artifactClosure` 是产物清单 |
| `error` | `data.message` | 运行时错误 |

`agent_runtime_end.data.reason` 的取值包括 `completed` / `error` / `interrupted` / `timeout`，以及**暂停**用的 `waiting_for_human`（部分路径为 `waiting_input`）。

## 6. 人工审批（HITL）

暂停时服务端依次发：

```text
step_start   { data: { phase: "human_approval", requiresApproval: true, pendingToolsCalling: [...] } }
agent_runtime_end { data: { reason: "waiting_for_human" } }
session_complete   → 服务端关闭 WS 连接
```

`pendingToolsCalling[]` 每项含 `tool_name`、`call_id`、`arguments`。审批 id 的取法：

- 有具体工具 → 用该工具名（`tool_name`）；
- 纯 widget 审批（无工具）→ 用字面量 `"widget"`。

提交审批 `POST /runs/{run_id}/answer`：

```json
{
  "approval_id": "askUserQuestion",
  "payload": "选择 B 方案",
  "idempotency_key": "<run_id>:<approval_id>:<随机或时间戳>",
  "rejection_reason": "（仅拒绝时携带，此时 payload 作为拒绝理由文本）"
}
```

- 三个字段 `approval_id` / `payload` / `idempotency_key` 均必填且非空，否则 `400`。
- 带 `rejection_reason` 表示拒绝，不带表示批准；`payload` 在批准时作为人工回答内容。
- 成功 `200`：`{"run_id": "...", "status": "resumed"}`；`payload` 重复提交时依赖 `idempotency_key` 去重，请保证同一意图使用同一 key 重试。

审批后**必须重连**才能继续看输出（暂停已关闭上一段连接）：

1. 拿 token：原 token 没过 5 分钟就直接复用；已过期或不确定就 `POST /v1/runs/{run_id}/ws-token` 重新签发（见 §1.1，token 与 run 绑定，run_id 不变即可复用/重签）；
2. 用 token 重连 WS，`resume.lastEventId` 传上一次收到事件信封里的 `id`，即可从断点续传而不是整段重放。

`POST /runs` 也接受 `resume_approval` 字段完成同样的恢复（camelCase：`approvalId` / `toolCallId` / `parentMessageId` / `rejectionReason`），但它返回的是新的 run 回执且不带 `ws_token`，前端常规场景用 `/answer` 更简单。

## 7. 停止任务 `POST /runs/{run_id}/cancel`

无请求体。成功 `200`：`{"status": "canceled"}`（已结束的 run 返回其终态，如 `completed`，同样 `200`）。

WS 里也有 `{"type":"interrupt"}` 帧，但只在连接活着（运行中）时有用；进入 HITL 暂停后服务端已经关掉连接，控制帧发不出去。为了只有一条取消路径，统一用这个 HTTP 接口。取消成功后服务端会补发 `agent_runtime_end`（`reason=interrupted`）和 `session_complete`。

## 8. 换取 WS 令牌 `POST /v1/runs/{run_id}/ws-token`

成功 `200`：`{"token": "<jwt>", "token_type": "Bearer", "expires_in": 300, "issued_at": 1763557200}`（`issued_at` 是秒级时间戳，可用来判断是否快到 5 分钟）。

| HTTP | 说明 |
|---|---|
| 404 | run 的事件流已不存在（未注册或已销毁），此时改用 `GET /runs/{id}` 读摘要 |
| 401 | 登录态缺失或失效 |
| 403 | run 属于其他用户 |
| 503 | 服务端未配签发密钥 |

## 9. 查询任务 `GET /runs/{run_id}`

用于事件流已过期后读取结果：

```json
{
  "run_id": "run_1a2b3c4d",
  "trace_id": "run_1a2b3c4d",
  "status": "completed",
  "session_status": "completed",
  "question": "帮我核对工号并生成本月报告",
  "output": "……最终答复文本……",
  "started_at": "2026-11-19T09:00:00Z",
  "closed_at": "2026-11-19T09:01:12Z",
  "steps": [ { "step_id": "...", "step_index": 0, "phase": "think", "duration_ms": 812, "thinking": {...}, "tool_call": {...}, "tool_result": {...}, "evidence": [...] } ],
  "doctor_report": null
}
```

`404` 表示没有该 run 记录。

## 10. 下载产物 `GET /files/{attachment_id}`

需要登录态；返回文件流（`Content-Disposition` 指向原始文件名）。`GET /files/{attachment_id}/meta` 返回元数据。

`agent_runtime_end.data.artifactClosure` 与 `addFileAttachment` 类产物项里的 `attachment_id` 拼成 `/files/{id}` 即可下载。**注意**：`<a href>` 触发的是独立导航请求，拿不到页面内存里的凭据，下载会 401；前端请用 `fetch`（带 `credentials: 'include'`）取 `blob` 再触发下载。

## 11. 错误码汇总

| HTTP | 场景 |
|---|---|
| 400 | 请求体结构错误（`messages` 非数组、缺 user 消息、审批字段缺失、`assistant_id` 非法）／上传校验失败（见 §3） |
| 401 | 登录态缺失或失效 |
| 403 | run 不属于当前用户 |
| 404 | run 不存在 / 事件流已失效 / 助理不存在 |
| 502 | 公司文件服务或权限服务不可用 |
| 503 | 服务端配置缺失（文件服务凭据、FileStore、JWT 私钥） |

401 的具体原因写在 `error.detail` 或 `error.code` 里；前端不必按原因分支，一律按「重新登录」处理，把原始响应贴给服务端排查即可。

## 12. 最小可用示例

```js
// 不设任何鉴权头：登录态由浏览器自动带 cookie
const cred = { credentials: 'include' };

// 1) 上传
const form = new FormData();
form.append('files', file);
const uploaded = await (await fetch('/files', { ...cred, method: 'POST', body: form })).json();

// 2) 创建
const created = await (await fetch('/runs', {
  ...cred,
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    messages: [{ role: 'user', content: text, files: uploaded.files }],
    mode: 'solo',
  }),
})).json();

// 3) 收流
const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/v1/runs/${created.run_id}/ws`);
let lastEventId = '0';
ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: created.ws_token }));
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === 'auth_success') ws.send(JSON.stringify({ type: 'resume', lastEventId, wantStatus: true }));
  if (msg.type === 'heartbeat_ack') return;
  if (msg.type === 'agent_event') {
    lastEventId = msg.id || lastEventId;
    handleEvent(msg.event); // 见 §5.3
    if (msg.event.type === 'agent_runtime_end' && msg.event.data.reason?.startsWith('waiting')) showApprovalPanel();
  }
  if (msg.type === 'session_complete') ws.close();
};
```

## 13. 联调提示

- 事件流用 Redis Stream 承载，保留 2 小时；到期后 `ws-token` 返回 404，改用 `GET /runs/{id}`。
- 一个 run 同一时刻只应有一个前端连接；重连请带 `lastEventId`，否则会把整段历史再渲染一次。
- 上传是同步落盘的：`POST /files` 返回时字节已经写入服务端 FileStore，创建 run 时不会再访问外部文件服务。
- 前端不参与身份加密，也无法伪造身份；如果 401 说凭据不对，那是网关与服务端之间的事，找服务端排查。
- 联调时如果 WS 一直 `auth_failed`，先看 `reason`：`token expired` 是 5 分钟过了要重签，`operation_id mismatch` 是拿了别的 run 的 token，`user_id mismatch for run` 是 token 的 `sub` 与该 run 的创建者不一致。
