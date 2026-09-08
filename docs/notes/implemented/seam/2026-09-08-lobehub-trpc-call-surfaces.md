# LobeHub 上游:前端 → 后端 tRPC 调用面全图

> Implemented seam note — 基于 `.lobehub-upstream/` 的代码现场,标记**实际触达**的 contract 表面。
> 服务端源码口径:`apps/server/src/routers/` + `packages/database/src/{models,repositories,schemas}`。
> 前端口径:`packages/trpc/src/client/` + `src/services/` + `src/store/` + `src/routes/` + `src/features/`。

## 1. 三 surface + 一别名

| Surface | HTTP 端点 | 客户端构造 | 用途 | 装配位置 |
|---|---|---|---|---|
| `lambdaRouter` | `POST /trpc/lambda` | `lambdaClient`(`createTRPCClient`, vanilla)+ `lambdaQuery`(`createTRPCReact` + `splitLink` + `httpBatchLink` / `httpLink`) | 主业务 API | `packages/trpc/src/client/lambda.ts` |
| `toolsRouter` | `POST /trpc/tools` | `toolsClient`(vanilla) | 沙箱 / MCP / Market / Composio | `packages/trpc/src/client/tools.ts` |
| `asyncRouter` | `POST /trpc/async` | `asyncClient`(vanilla) | 服务器内部 worker 入口,前端**不消费** | `packages/trpc/src/client/async.ts` |
| `mobileRouter` | `POST /trpc/mobile` | iOS/Android 子集,直接走 fetch | mobile 客户端 | `src/app/(backend)/trpc/mobile/[trpc]/route.ts` |

Next.js fetch handler 与 `onError={createTRPCErrorLogger(name)}` 在 `src/app/(backend)/trpc/{lambda,tools,async,mobile}/[trpc]/route.ts`。

`lambdaQuery.Provider` 在 `src/layout/GlobalProvider/Query.tsx`(app 根)。

**没有 WebSocket tRPC 订阅**;Agent 流式走独立 Gateway WebSocket(`src/store/chat/slices/agentRun/actions/transports/gateway/`)。

## 3. 五种调用形式

| 形式 | 文件数 | 用途 |
|---|---|---|
| `lambdaClient.<router>.<proc>.query(...)` / `.mutate(...)` | ~150 | 服务层 + store 内部 action 主流 |
| `lambdaQuery.<router>.<proc>.useQuery(...)` | 8 | settings/provider OAuth device-flow、settings/credential creds 列表 |
| `lambdaQuery.<router>.<proc>.useMutation(...)` | ~12 | OAuth app、PDF 导出、Device CRUD |
| `lambdaQuery.<router>.<proc>.useInfiniteQuery(...)` + `fetchNextPage` | 2 | `chunk.getChunksByFileId` — PDF 分页与 Chunk 抽屉 |
| 自定义 `useClientDataSWR` 包装 service fetcher | 30+ | `useFetchSessions` / `useFetchAgentList` / `useFetchTopics` / `useFetchThreads` 等 |

`useUtils()` 仅一处:`src/routes/(main)/settings/provider/features/ProviderConfig/OAuthDeviceFlowAuth/index.tsx`(revokeAuth 后 invalidate `oauthDeviceFlow.getAuthStatus`)。

`createWorkspaceLambdaClient(workspaceId)` 用于 workspace 设备编辑,`src/features/DeviceManager/DeviceDetailPanel.tsx` 单点。

## 4. 按业务域清单(实际触达的 procedure 数)

| 域 | 触达数 | 主要 procedure / 关键调用点 |
|---|---|---|
| 会话 / 消息 / Topic | ~70 | `session.*` (10/11)、`message.*` (27/27,含 `batchMutate` 批量调用,走 `abortableRequest` 取消)、`topic.*` (27/31)、`thread.*` (5/7) |
| Agent / AgentGroup CRUD | ~45 | `agent.*` (26/29,含 `acquireAgentLock` 编辑锁)、`agentGroup` 别名 `group.*` (15/21)、`market.agent.*` / `market.agentGroup.*` |
| AI Provider / Model / API Key | ~22 | `aiProvider.*` (10/10)、`aiModel.*` (11/11)、`apiKey.*` (4/8)、`oauthDeviceFlow.*` (4/4) |
| 工具与插件 | ~45 | `plugin.*` (5/5)、`connector.*` (22/23)、`composio.*` (6/6)、`tools.market.*` / `tools.composio.*` / `tools.search.*` / `tools.mcp.*` |
| RAG / 文件 / 文档 | ~50 | `file.*` (18/19)、`document.*` (17/21)、`knowledgeBase.*` (11/12)、`chunk.*` (7/7,含 `useInfiniteQuery` 2 处)、`notebook.*` (5/5) |
| 任务 / 验证 / Accept | ~70 | `task.*` (~30/46)、`verify.*` + `acceptance.*` (~28+16,共享 `src/services/verify.ts`)、`agentSignal.*` (3/4)、`agentNotify.notify.mutate` |
| 用户 / 设置 / Onboarding | ~75 | `user.*` (23/32)、`userMemories.*` (18/20)、`userMemory.*` (17/22)、`notification.*` (6/6)、`workspaceUserSettings.*` (2/2) |
| 上传 / 导入 / 导出 / 分享 | ~10 | `upload.createS3PreSignedUrl` / `importer.*` (3) / `exporter.*` (2,含 react-query `useMutation`) / `share.getSharedTopic` |
| 市场 / 发现 / 社交 | ~80 | `market.*` 顶层 (25/36) + 9 子路由(`agent` 8/13、`agentGroup` 5/10、`creds` 17/17、`oidc` 3/4、`skill` 5/5、`social` 19/19、`socialProfile` 3/3、`user` 2/2)+ `workspace.ensureMarketOrganization` (4 处) |
| 首页 / 侧栏 / 搜索 | ~12 | `home.*` (4/4)、`recent.getAll`、`search.query`(走 SWR)、`usage.*` (3/4)、`brief.*` |
| 设备 / Git / 项目 / 异构代理 | ~45 | `device.*`(~42 触达 ~25,5 个 react-query `useMutation`)、git 全 surface、`projectSkill` / `projectFile` / `heterogeneousAgent` / `heteroAgentQuota` |
| Bot / IM / AI 聊天 | ~30 | `agentBotProvider.*` (14/14)、`botMessage.*` (18/18,主要在 `trpcAdapters`)、`messenger.*` (15/15)、`aiChat.*` (3/3)、`aiAgent.*` (9/19)、`llmGenerationTracing.recordFeedback` |
| Image / Video / Web / Generation | ~10 | `image.createImage` / `video.createVideo` / `webBrowsing.upsertCrawledDocument` / `followUpAction.extract` / `generation*` / `generationBatch.*` / `generationTopic.*` |
| 凭据 / OAuth App | ~14 | `oauthApp.*` (6/6,3 处 react-query)、`resourcePermission.*` (2/2)、`creds.share/unshare`、`creds.createKV` |
| Changelog / 配额 | ~12 | `changelog.*` (2/2)、`agentQuota.*` (10/13) |

## 5. 错误处理三层

| 层 | 位置 | 处理 |
|---|---|---|
| Link 层(全局) | `packages/trpc/src/client/lambda.ts`、`packages/trpc/src/client/tools.ts` 的 `errorHandlingLink` | 401 防抖 → `market-unauthorized` 事件;session 过期派发登出;abort-error 抑制;desktop `X-Proxy-Error` → `remoteServerErrorToast` |
| 类型守卫 | `src/utils/trpcError.ts` | `isTrpcErrorCode(error, code)` 结构化比对,跨序列化边界安全 |
| 组件层 | 7 个文件 | `instanceof TRPCClientError` + `error.data.code` / `error.data.errorData` |

## 6. 服务端类型回流(~30 处 type-only import)

主要复用:`RecentItem` (Home / Recents)、`UpdateTopicValue` (image / video store)、`CreateImageServicePayload` / `CreateVideoServicePayload`、`GetGenerationStatusResult`、`documentHistory.*` 8 个 type (PageEditor/History + agent menu)、`tools/market` 的 `CallToolResult` / `ExecInSandboxInput` / `ExportAndUploadFileInput` / `ExportAndUploadFileResult`。

**全部 `import type`**,server-only 类型不进 SPA bundle。

## 7. 与非 tRPC 入口的边界

| 非 tRPC 入口 | 路径 |
|---|---|
| Next.js App Router `/api/*` catch-all | `src/app/(backend)/api/[[...path]]/route.ts` → `apps/server/src/hono/index.ts` |
| Agent Gateway WebSocket(流式) | `src/store/chat/slices/agentRun/actions/transports/gateway/` |
| Market 鉴权 | `/auth/market/...` 与 OAuth device flow |

## 8. 与 LCA 集成视角

- LCA fork (`lobehub-ui/`) 复用同一份 `lambdaClient` / `lambdaQuery`,通过 `@/libs/trpc/*` alias;改 tRPC 路径对 LCA 行为影响**主要**通过以下三个面:
  1. `src/services/*` 的 vanilla `lambdaClient.<router>.<proc>` 调用(SWR fetcher + 业务 action)
  2. `src/store/*` 内部 `lambdaClient` 与外部 react-query `lambdaQuery` 之间的切换
  3. `src/features/*` 与 `src/routes/(main)/settings/...` 中的直接 react-query hook
- 变更 `lambdaRouter` 任一 procedure **必须闭环**:
  - `apps/server/src/routers/lambda/<router>.ts` 的 procedure body + Zod schema
  - `packages/database/src/models/<model>.ts` 与对应 repository 的 query/mutation
  - `src/services/<domain>/index.ts` 服务层 + `src/store/<slice>/action.ts` store
  - `src/routes/*` 与 `src/features/*` 触发该 procedure 的 UI
  - 测试:`packages/database/src/models/__tests__/...` + service 层单测 + e2e
- 错误处理链路(`errorHandlingLink` → 401 → market-unauthorized → 登出通知)若改动,需检查 `src/business/client/handleLobeHubModelDeprecatedError.ts` 与 7 处 `TRPCClientError` 引用是否仍正确解码。

## 9. 反模式(已发现)

- 同一份 procedure 在 `services/` 与 `routes/` 中**两处**直接调用(`apiKey`、`oauthApp`、`oauthDeviceFlow`、`market.creds`),且两处使用不同的 hook 范式(vanilla + react-query)—— 后续迁移到统一 `useQuery` 时需两处同步改。
- `asr.transcribe`、`klavis.getKlavisPlugins`、`pushToken.{register,unregister}`、`agentEvalExternal.*`、所有 `async.*`、所有 `business-server` 空 stub — 前端**完全不消费**,server 端定义仍存在但属于 cloud-only 或未启用入口。
- `lambdaClient` 与 `lambdaQuery` 同时暴露给应用,store 内部偏向 vanilla(`lambdaClient`),UI 偏向 react-query(`lambdaQuery`),需要**统一的失效与乐观更新策略**(目前散落在 `src/store/chat/slices/agentRun/actions/`、`src/store/tool/slices/composioStore/action.ts`、`src/store/tool/slices/lobehubSkillStore/action.ts`)。

## 10. 验证命令

```bash
# 客户端装配
ls -la .lobehub-upstream/packages/trpc/src/client/

# 顶层 router 文件
ls .lobehub-upstream/apps/server/src/routers/lambda/ | wc -l   # 88

# 前端 vanilla 调用
rg "lambdaClient\.[a-zA-Z]+\." .lobehub-upstream/src/ -l | wc -l

# 前端 react-query 调用
rg "lambdaQuery\.[a-zA-Z]+\." .lobehub-upstream/src/ -l | wc -l

# TRPCClientError 引用
rg "TRPCClientError" .lobehub-upstream/src/ -l | wc -l
```

## Alternatives considered

- **A. 只写主 router 调用清单(不写 vanilla vs react-query 对比)**:省字数,但漏掉失效策略、optimistic、infinite 三个 runtime 语义关键区分。
- **B. 直接给原报告(子 agent 全文)** ~600 行:不压缩,LCA 后续 commit 审查困难。
- **C. 选 C:压缩为契约 surface + 调用形式 + 业务域清单 + 三层错误 + 反模式**。

## 状态

Implemented — 本笔记为对 `.lobehub-upstream/` vendored copy 的代码现场快照,**非新增 ADR**,不引入新机制。后续若 `.lobehub-upstream/` bump(可见 `.lobehub-upstream/.git`)需要重跑同口径的子 agent 验证。