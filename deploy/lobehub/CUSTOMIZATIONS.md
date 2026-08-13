# LCA ↔ LobeHub 定制清单

> **用途**：记录 LCA 对 LobeHub 前端/后端的所有定制改动。每次新增定制必须更新本文档。
>
> **基准版本**：LobeHub v2.2.13（`.lobehub-upstream/` 为 pristine 源码，`lobehub-ui/` 为定制后的工作副本）
>
> **应用方式**：`patch_lobehub.py` 统一补丁引擎（12 个幂等 patch，支持 `apply` / `verify` / `list`）

---

## 架构总览

```
LobeHub 前端 (React)
  │  fetchSSE → /webapi/chat/{provider}
  │  lca_tool_event → StreamingHandler → 工具卡片 UI
  ▼
LobeHub 后端 (Next.js)
  │  model-runtime → transformQwenStream / transformOpenAIStream
  │  提取 chunk.lca.events → lca_tool_event 协议块
  │  OpenAI SDK → POST gateway/v1/chat/completions
  ▼
LCA Gateway (:8765)
  │  openai_compat_api.py → 创建 LCA run
  │  journal_openai_projector.py → 标准 OpenAI chunk + lca 扩展
  ▼
LCA Agent/Team Runtime → 上游 LLM
```

**核心约定**：Gateway 输出**标准 OpenAI SSE**（`data: {chat.completion.chunk}`），工具生命周期通过 chunk 内的 `lca: {v: 1, events: [...]}` 扩展字段传递。LobeHub 后端的 stream transformer 提取 `lca.events` 并 emit `lca_tool_event` 协议块，前端渲染工具卡片。

---

## 一、流式协议层

> 让 LCA 的 `lca.events` 扩展在 LobeHub 流式管道中正确传递。

### 1.1 `packages/model-runtime/src/core/streams/openai/openai.ts`

**Patch 名称**：`openai_stream`

在 `transformOpenAIStream` 的 chunk 处理最前面插入 LCA 扩展提取：

```typescript
/* LCA: emit lca.events before OpenAI delta handling */
const lcaExt = (chunk as { lca?: { events?: unknown[] } }).lca;
if (lcaExt?.events?.length) {
  const events = lcaExt.events as Record<string, unknown>[];
  return events.map(
    (event): StreamProtocolChunk => ({
      data: event,
      id: chunk.id,
      type: 'lca_tool_event',
    }),
  );
}
```

**锚点**：`  try {\n    // maybe need another structure to add support for multiple choices`

### 1.2 `packages/model-runtime/src/core/streams/qwen.ts`

**Patch 名称**：`qwen_stream`

与 1.1 相同的 patch，但插入位置在 `transformQwenStream` 的 usage 检查之后、`chunk.choices[0]` 之前：

```typescript
/* LCA: emit lca.events before OpenAI delta handling */
const lcaExt = (chunk as { lca?: { events?: unknown[] } }).lca;
if (lcaExt?.events?.length) {
  const events = lcaExt.events as Record<string, unknown>[];
  return events.map(
    (event): StreamProtocolChunk => ({
      data: event,
      id: chunk.id,
      type: 'lca_tool_event',
    }),
  );
}
```

**为什么两个文件都要改**：OpenAI provider 和 Qwen provider 各自有独立的 stream transformer。当 `QWEN_PROXY_URL` 指向 LCA gateway 时，qwen transformer 也需要提取 `lca.events`。

### 1.3 `packages/model-runtime/src/core/streams/protocol.ts`

**Patch 名称**：`protocol`

两处改动：

1. `StreamProtocolChunk.type` 联合类型加 `| 'lca_tool_event'`
2. switch case 加：
```typescript
case 'lca_tool_event': {
  await callbacks.onLcaToolEvent?.(data);
  break;
}
```

**锚点**：`    | 'tool_calls'\n` 和 `          case 'tool_calls': {`

### 1.4 `packages/model-runtime/src/types/chat.ts`

**Patch 名称**：`chat_callbacks`

在 `ChatStreamCallbacks` 接口中加：

```typescript
/** LCA gateway ``lca.events`` (tool_started / tool_result / tool_state / run_error). */
onLcaToolEvent?: (event: Record<string, unknown>) => Promise<void> | void;
```

**锚点**：`  onToolsCalling?: (data: {`

### 1.5 `packages/fetch-sse/src/fetchSSE.ts`

**Patch 名称**：`fetch_sse`

两处改动：

1. `onMessageHandle` 参数类型联合加 `| { event: Record<string, unknown>; type: 'lca_tool_event' }`
2. switch case 加：
```typescript
case 'lca_tool_event': {
  options.onMessageHandle?.({ event: data, type: 'lca_tool_event' });
  break;
}
```

**锚点**：`      | MessageStopChunk,\n  ) => void;` 和 `        case 'tool_calls': {`

---

## 二、前端 Agent 运行时

> 工具卡片渲染 + closed-loop 跳过客户端 tool loop。

### 2.1 `src/store/chat/agents/types/streaming.ts`

**Patch 名称**：`streaming_types`

四处改动：

1. 新增 `LcaStreamToolEvent` 类型定义（tool_started / tool_result / tool_state / run_error 四种变体）
2. `StreamingCallbacks` 加 `onLcaToolEvent?: (event: LcaStreamToolEvent) => void`
3. `StreamingResult` 加 `lcaClosedLoop?: boolean` 和 `lcaRunError?: string`
4. Stream chunk 类型联合加 `| { event: LcaStreamToolEvent; type: 'lca_tool_event' }`

### 2.2 `src/store/chat/agents/StreamingHandler.ts`

**Patch 名称**：`streaming_handler`

改动：

1. import `LcaStreamToolEvent`
2. 新增私有字段 `lcaClosedLoop`, `lcaRunError`, `lcaToolsById`
3. switch 加 `case 'lca_tool_event'` → `handleLcaToolEvent(chunk.event)`
4. 新增 `handleLcaToolEvent()` 方法 — 将 LCA 工具事件转为 `ChatToolPayload`，驱动工具卡片 UI
5. `StreamingResult` 传递 `lcaClosedLoop` 和 `lcaRunError`

**核心逻辑**：
- `tool_started` → 创建 tool call 卡片，调用 `transformToolCalls` 转换
- `tool_result` / `tool_state` → 更新已有卡片的内容/状态
- `run_error` → 记录错误信息
- `closed_loop` 标记 → 阻止客户端发起 tool loop

### 2.3 `src/store/chat/agents/transports/ClientLLMTransport.ts`

**Patch 名称**：`client_transport`

三处改动：

1. 接入 `onLcaToolEvent` 回调：
```typescript
onLcaToolEvent: (event) => handler.handleChunk({ event, type: 'lca_tool_event' }),
```
2. `lcaRunError` 上浮为 transport 层错误
3. `StreamingResult` 传递 `lcaClosedLoop`

### 2.4 `packages/agent-runtime/src/transport/llm.ts`

**Patch 名称**：`llm_transport_type`

`StreamingResult` 类型加 `lcaClosedLoop?: boolean`

### 2.5 `packages/agent-runtime/src/executors/callLlmFinalizer.ts`

**Patch 名称**：`call_llm_finalizer`

```typescript
// 改前：
hasToolsCalling: output.toolsCalling.length > 0,
// 改后：
hasToolsCalling: !output.lcaClosedLoop && output.toolsCalling.length > 0,
```

**作用**：LCA closed-loop 模式下，工具在 server-side 执行完毕，前端不再发起 client-side tool call。

---

## 三、Provider 路由

### 3.1 `packages/business/const/src/llm.ts`

**Patch 名称**：`default_model`

默认模型和 provider 改为 `solo` / `openai`（正则替换 `DEFAULT_MODEL`、`DEFAULT_PROVIDER`、`DEFAULT_MINI_MODEL`、`DEFAULT_MINI_PROVIDER`）。

### 3.2 `packages/model-runtime/src/providers/openai/index.ts`

**Patch 名称**：`openai_guard`

LCA 虚拟模型（`solo`/`team`/`auto`）强制走 `chat/completions`，绕过 OpenAI 的 `responses` API：

```typescript
const isLcaGatewayModel = ['solo', 'team', 'auto'].includes(model);
/* LCA: solo/team always chat/completions */
if (!isLcaGatewayModel && (isResponsesAPIModel(model) || enabledSearch)) {
  // responses API path
}
```

---

## 四、本地开发认证

> 去掉 Better Auth 登录，使用静态 dev user。

### 4.1 `src/layout/AuthProvider/localDevNoAuth.ts`

**Patch 名称**：`dev_auth_files`（新增 3 个文件）

```typescript
export const isLocalDevNoAuth = (): boolean => {
  const flag = process.env.NEXT_PUBLIC_ENABLE_MOCK_DEV_USER;
  return flag === '1' || flag === 'true';
};

export const getLocalDevUserId = (): string =>
  process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID || 'local-dev-user';
```

### 4.2 `src/layout/AuthProvider/LocalDevAuth/index.tsx`

**Patch 名称**：`dev_auth_files`（同上）

无登录 UI wrapper，children + `LocalDevUserUpdater`。

### 4.3 `src/layout/AuthProvider/LocalDevUserUpdater.tsx`

**Patch 名称**：`dev_auth_files`（同上）

`useLayoutEffect` 注入静态 dev user 到 `useUserStore`。

### 4.4 `src/layout/AuthProvider/index.vite.tsx`

**Patch 名称**：`dev_auth_vite`

`ENABLE_MOCK_DEV_USER` 时用 `LocalDevAuth` 替代 `BetterAuth`。

### 4.5 `src/libs/next/proxy/define-config.ts`

**Patch 名称**：`middleware_mock_user`

middleware 跳过 Better Auth session gate：

```typescript
const mockDevFlag = process.env.ENABLE_MOCK_DEV_USER;
if (mockDevFlag === '1' || mockDevFlag === 'true') {
  logBetterAuth('ENABLE_MOCK_DEV_USER: skipping session gate');
  return response;
}
```

---

## 五、路由 / Market 适配

### 5.1 `src/features/AgentSidebar/utils/agentPathname.ts`

**Patch 名称**：`topic_route`

新增 `AGENT_CHAT_SUB_ROUTES` 集合 + `resolveAgentChatRouteTopicId()` 函数。

### 5.2 `src/routes/(main)/agent/features/Conversation/ChatHydration/useChatRouteSync.ts`

**Patch 名称**：`topic_route`

用 `resolveAgentChatRouteTopicId` 替代直接读 `params.topicId`。

### 5.3 `src/routes/(main)/agent/_layout/AgentIdSync.tsx`

**Patch 名称**：`topic_route`

同上。

---

## 六、Dev UX

### 6.1 `src/libs/spaHtml/index.ts`

**Patch 名称**：`lan_dev`

Vite dev 资源 URL 使用 `VITE_DEV_HOST` 环境变量（而非硬编码 `localhost`），支持局域网访问：

```typescript
export const resolveCiteDevOrigin = () => {
  const host = process.env.VITE_DEV_HOST || 'localhost';
  const port = Number(process.env.VITE_DEV_PORT) || 9876;
  return `http://${host}:${port}`;
};
```

---

## 七、Gateway 端（LCA 侧）

> 不是 LobeHub 代码，但是 LobeHub 集成的关键组成部分。

| 文件 | 职责 |
|------|------|
| `gateway/openai_compat_api.py` | `/v1/chat/completions` 端点 — LCA run 包装为 OpenAI 兼容响应 |
| `gateway/journal_openai_projector.py` | Journal → OpenAI chunk 投影器，`_emit_lca_events()` 嵌入 `lca` 扩展 |
| `gateway/lobehub_bridge/lca_sse_extension.py` | `merge_lca_extension()` — 工具事件嵌入 OpenAI chunk |
| `gateway/lobehub_bridge/tool_wire.py` | 工具 wire 协议 — LCA 内部名 ↔ LobeHub 显示名转换 |
| `gateway/named_sse.py` | Named SSE event 格式化（当前未使用，保留供未来 fetchSSE 直连方案） |

---

## 八、环境配置

`.env.lca` → 复制到 `lobehub-ui/.env`：

```bash
# 所有 provider 走 LCA gateway
OPENAI_API_KEY=lca-local
OPENAI_PROXY_URL=http://127.0.0.1:8765/v1
ENABLED_OPENAI=1

QWEN_API_KEY=lca-local
QWEN_PROXY_URL=http://127.0.0.1:8765/v1
ENABLED_QWEN=1
DEFAULT_AGENT_CONFIG=model=qwen3.7-plus;provider=qwen;chatConfig.searchMode=off

# 本地开发无登录
ENABLE_MOCK_DEV_USER=1
NEXT_PUBLIC_ENABLE_MOCK_DEV_USER=1
MOCK_DEV_USER_ID=local-dev-user
NEXT_PUBLIC_MOCK_DEV_USER_ID=local-dev-user
```

---

## 如何新增定制

1. **确定改动层次**：流式协议 / Agent 运行时 / Provider 路由 / 认证 / 路由适配 / Dev UX
2. **在 `patch_lobehub.py` 中新增 patch 函数**：遵循 `p_xxx()` 命名，返回 `bool`（True=applied, False=skipped）
3. **注册到 `PATCHES` 清单**：填写 name / description / files / risk / category
4. **添加 verify marker**：在 `_VERIFY_MARKERS` 中注册 (file, marker_string)
5. **更新本文档**：记录文件路径、改动内容、锚点、原因
6. **验证**：`python3 deploy/lobehub/patch_lobehub.py verify` 确认所有 patch 状态

---

## 文件索引

| # | 文件（相对 lobehub-ui/） | 层次 | Patch 名称 |
|---|--------------------------|------|------------|
| 1 | `packages/model-runtime/src/core/streams/openai/openai.ts` | 流式协议 | `openai_stream` |
| 2 | `packages/model-runtime/src/core/streams/qwen.ts` | 流式协议 | `qwen_stream` |
| 3 | `packages/model-runtime/src/core/streams/protocol.ts` | 流式协议 | `protocol` |
| 4 | `packages/model-runtime/src/types/chat.ts` | 流式协议 | `chat_callbacks` |
| 5 | `packages/fetch-sse/src/fetchSSE.ts` | 流式协议 | `fetch_sse` |
| 6 | `src/store/chat/agents/types/streaming.ts` | Agent 运行时 | `streaming_types` |
| 7 | `src/store/chat/agents/StreamingHandler.ts` | Agent 运行时 | `streaming_handler` |
| 8 | `src/store/chat/agents/transports/ClientLLMTransport.ts` | Agent 运行时 | `client_transport` |
| 9 | `packages/agent-runtime/src/transport/llm.ts` | Agent 运行时 | `llm_transport_type` |
| 10 | `packages/agent-runtime/src/executors/callLlmFinalizer.ts` | Agent 运行时 | `call_llm_finalizer` |
| 11 | `src/store/chat/agents/transports/AgentTimelineTransport.ts` | Agent 运行时 | `agent_timeline_transport` |
| 12 | `src/store/chat/agents/transports/buildClientRuntimeHost.ts` | Agent 运行时 | `agent_timeline_transport` |
| 13 | `packages/business/const/src/llm.ts` | Provider 路由 | `default_model` |
| 12 | `packages/model-runtime/src/providers/openai/index.ts` | Provider 路由 | `openai_guard` |
| 13 | `src/layout/AuthProvider/localDevNoAuth.ts` | 认证 | `dev_auth_files` |
| 14 | `src/layout/AuthProvider/LocalDevAuth/index.tsx` | 认证 | `dev_auth_files` |
| 15 | `src/layout/AuthProvider/LocalDevUserUpdater.tsx` | 认证 | `dev_auth_files` |
| 16 | `src/layout/AuthProvider/index.vite.tsx` | 认证 | `dev_auth_vite` |
| 17 | `src/libs/next/proxy/define-config.ts` | 认证 | `middleware_mock_user` |
| 18 | `src/features/AgentSidebar/utils/agentPathname.ts` | 路由适配 | `topic_route` |
| 19 | `src/routes/(main)/agent/features/Conversation/ChatHydration/useChatRouteSync.ts` | 路由适配 | `topic_route` |
| 20 | `src/routes/(main)/agent/_layout/AgentIdSync.tsx` | 路由适配 | `topic_route` |
| 21 | `next.config.ts` | 代理 | `file_proxy_rewrite` |
| 22 | `src/libs/spaHtml/index.ts` | Dev UX | `lan_dev` |
| 23 | `packages/builtin-tool-cloud-sandbox/src/client/Render/ExecuteCode/index.tsx` | UI | `sandbox_generated_files` |
