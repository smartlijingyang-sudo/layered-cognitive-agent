# LCA 助理头像生成系统（Assistant Avatar Generation System）规格

**创建日期**：2026-10-02
**状态**：Approved (设计已确认，待实现)

本文定义 LCA 助理头像生成子系统的契约：数据模型、生成管线、激活状态机、定时换装调度器、REST 契约、WS 推送通道、前端补丁、安全红线与验证矩阵。实现对照本文档与 ADR-0269。

---

## 1. 背景与目标

LCA 现有头像机制是 `profile.json` 的 `emoji` 字段（经 `bridge.py` 映射到 LobeHub avatar）+ 顶栏 SVG 萌宠（`AssistantTopMascot`）+ 聊天流候选卡片（`AssistantAvatarWidget`，写入 `IDENTITY.md` frontmatter）。该机制没有图像生成、没有候选池、没有定时换装。

本系统对标 Meta Muse 的 Avatar 设计，在 LCA 落地以下能力：

- **身份感知生图**：生图 prompt = 用户原话 + 身份特征（identity traits），两者缺一不可。
- **候选池机制**：create/edit 只生成候选，set 才激活。生成与激活解耦，用户永远有选择权。
- **变体包**：多尺寸静态变体 + 异步视频变体。
- **定时换装**：cron 到点自动 edit 并直接生效，发轻量通知。
- **一键恢复默认头像**。

## 2. 系统边界

### 2.1 Owns

- 新插件 `lca/plugins/avatar/`：provider HTTP 客户端、文件存储、领域服务、轻量调度器、agent 工具、REST 路由、WS 推送。
- 新契约包 `lca/contracts/models/avatar/`。
- 新 agent 工具命名空间 `avatar`（ADR-0256 规范内新增域）。
- 新 WS 端点 `/v1/assistants/{id}/events`（Redis pub/sub 通道）。
- 前端补丁 `deploy/lobehub/patches/`（头像渲染、WS 客户端、候选卡片升级）。

### 2.2 Does NOT own

- 不修改 `lobehub-ui/` 源码（必须走 `deploy/lobehub/patches/`）。
- 不绕过 `AssistantCatalog` 写配置面文件。
- 不修改 `lca/domain/cron` 的既有契约（只新增消费方）。
- 不实现 ADR-0268 的正式 cron worker（定时换装用自建轻量调度器，未来可被正式 worker 取代）。
- 不提交宿主机资产或 grok2api 代理的凭证到本仓库。

## 3. 架构总览

```
LobeHub 前端
  ├─ AssistantAvatarImage（头像渲染，读 GET /v1/assistants/{id}/avatar）
  ├─ assistantEventClient（WS 订阅 /v1/assistants/{id}/events）
  └─ AssistantAvatarWidget（候选卡片 → POST .../set 激活）
        │
        ▼
LCA webserver (routes_1/routes_avatar.py)
  ├─ AvatarService（状态机 + 候选池 TTL）
  ├─ AvatarImageProvider（grok2api HTTP 客户端）
  ├─ AvatarStore（avatar/state.json + 图片文件）
  └─ AvatarEventPublisher（Redis pub/sub → assistant_events:<id>）
        │
        ▼
grok2api 代理 (http://127.0.0.1:8000/v1)
  ├─ POST /v1/images/generations  （文生图）
  ├─ POST /v1/images/edits        （图生图/编辑）
  └─ POST /v1/videos + GET /v1/videos/{id}（异步视频）
```

## 4. 数据模型

契约包 `lca/contracts/models/avatar/`：

| 模型 | 字段 | 说明 |
|---|---|---|
| `AvatarVariant` | `size`(original/small/medium/large), `file_path`, `url`, `width`, `height` | 单个尺寸图片 |
| `AvatarCandidate` | `candidate_id`, `assistant_id`, `kind`(create/edit), `prompt`, `variants`, `video_status`(none/pending/ready/failed), `created_at`, `expires_at` | 候选（expires_at = created_at + 24h） |
| `AvatarActiveBundle` | `candidate_id`, `variants`, `video_status`, `activated_at` | 已激活头像 |
| `AvatarState` | `assistant_id`, `active: AvatarActiveBundle \| null`, `candidates: list[AvatarCandidate]`, `updated_at` | 状态 SSOT 投影 |
| `AvatarUpdatedEvent` | `type`("avatar_updated" \| "avatar_video_ready"), `assistant_id`, `payload` | WS 事件载荷 |

环境变量（单独配置进 `.env`）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AVATAR_IMAGE_BASE_URL` | `http://127.0.0.1:8000/v1` | grok2api 代理 base URL |
| `AVATAR_IMAGE_API_KEY` | 无 | grok2api 访问密钥（`~/.config/grok2api-clients.env` 的 `GROK2API_API_KEY`） |
| `AVATAR_IMAGE_MODEL` | `grok-imagine-image-lite` | 文生图模型 |
| `AVATAR_IMAGE_EDIT_MODEL` | `grok-imagine-image-lite` | 图生图/编辑模型（若代理账号池提供 `grok-imagine-image-edit` 等 super 级模型，可改该变量） |
| `AVATAR_VIDEO_MODEL` | `grok-imagine-video` | 视频生成模型 |

## 5. 文件布局与存储

`~/.lca/assistants/<assistant_id>/avatar/`：

```
state.json
candidates/<candidate_id>/{original,small,medium,large}.png
active/<candidate_id>/{original,small,medium,large}.png
video/<candidate_id>.mp4
```

- `state.json` 是头像状态唯一真值（File-as-SSOT）。写入采用原子写（临时文件 + rename），并追加 revision 到 assistant home 的 `revisions/`。
- 候选池 TTL 24 小时：读取时惰性清理过期候选；调度器每小时做一次全量清理。
- 图片经 `GET /v1/assistants/{id}/avatar/files/{path}` 提供 HTTP 访问，前端 `<img src>` 直连。
- `active == null` 表示使用默认头像（前端回退到 `profile.json` 的 emoji / SVG 萌宠）。

## 6. 生成管线

`AvatarImageProvider`（协议） + `Grok2ApiProvider`（实现）：

- `generate_image(prompt, reference_image_bytes=None) -> bytes`
  - 无参考图：`POST /v1/images/generations`，JSON body `{"model": AVATAR_IMAGE_MODEL, "prompt": ..., "n": 1}`。
  - 有参考图：`POST /v1/images/edits`，multipart（model、image、prompt）。
  - 响应取 `data[0].url`，立即下载字节存入本地。原始图 + Pillow 缩放生成 small/medium/large 三尺寸。
- `create_video(image_bytes) -> task_id`：`POST /v1/videos`。
- `get_video(task_id) -> VideoStatus`：轮询 `GET /v1/videos/{id}`，ready 后下载 `content` 存 `video/<candidate_id>.mp4`。

失败语义：

- 瞬时错误（网络、5xx、429）：指数退避重试最多 2 次。
- 确定性错误（4xx 参数错误）：不重试，返回类型化失败。
- 下载图片/视频失败按瞬时错误处理（URL 有 TTL，立即下载）。

### 6.1 身份特征（identity traits）

`_load_identity(assistant_id)` 读取：

- `profile.json`（name、description、emoji）；
- `IDENTITY.md`（若存在，含历史 `avatar:` frontmatter）；
- `SOUL.md` 的身份/性格/语气章节。

`_summarize_traits(identity) -> str`：一次 qwen LLM 调用，产出 3–6 个英文风格标签（如 "sharp, warm, cyberpunk"）。LLM 经插件配置 `summarizer_llm` 注入（默认 `None` = 确定性 fallback：`name + description + emoji` 拼接，为出厂默认）。

**prompt 模板**：

```
{user_request_verbatim}

Identity traits: {identity_traits}
Style: consistent character, high quality avatar portrait, centered.
```

`user_request` 必须原样传递。工具不改写、不润色、不翻译用户输入。

## 7. 激活流程与状态机

五个 agent 工具（namespace `avatar`）：

| 工具 | 参数 | 行为 |
|---|---|---|
| `avatar_create` | `user_request` | 生成 4 个候选进池，**不激活**。返回候选列表 |
| `avatar_edit` | `user_request`, `reference_image?` | 读当前 active 原图做 img2img，生成 4 个候选，**不激活**。`reference_image` 默认 = 当前头像 |
| `avatar_set` | `candidate_id` | 校验候选在池且未过期 → 拷为 active → 清空候选池 → 推 `avatar_updated` → 异步起视频任务 |
| `avatar_get` | 无 | 返回 active + 候选列表 |
| `avatar_clear` | 无 | 删除 active，恢复默认头像，推 `avatar_updated` |

状态机铁律：

- create/edit 与 set 严格两轮。第一轮绝不自动激活（用户的创建请求 ≠ 对某个候选的批准）。
- 唯一例外：定时换装走内部 `avatar_edit(auto_activate=True)`，直接生效。
- 候选过期后 `set` 返回 `409`（过期错误），需要重新 create。
- 幂等：重复 `set` 同一 `candidate_id` 返回同一 active；`create` 重试生成新候选，旧候选继续有效直到过期。

## 8. 定时换装调度器

`AvatarCostumeScheduler`（asyncio 后台循环，默认 60 秒 tick）：

- 复用 `lca/domain/cron` 的 `CronStore` 与 `next_run`，扫描 `execution.kind == "space_action" && execution.artifact_id == "avatar"` 的到期 CronJob。
- 触发时读 `job.body`（即 user_request 原文），调用内部 `avatar_edit(auto_activate=True)`。
- 写 `CronRun` 回执（outcome、finished_at）。
- 经 ADR-0264 裁决（DELIVER_CHAT / DELIVER_QUIET / SILENT）发轻量通知，如「我换了身衣服：雨天装扮 🎭」。

新增 agent 工具 `avatar_schedule({user_request, schedule, timezone})`：创建上述 CronJob（内部调 `CronService.add`，`execution=SpaceActionExecution(artifact_id="avatar")`）。

## 9. REST 契约

路由挂载于现有 `routes_1` 体系（`RouteSpec + register_routes`），鉴权复用 assistant 路由的 JWT / `x-lca-token`。

| 端点 | 方法 | 请求 | 响应 |
|---|---|---|---|
| `/v1/assistants/{id}/avatar` | GET | 无 | `AvatarState` |
| `/v1/assistants/{id}/avatar/candidates` | GET | 无 | 候选列表 |
| `/v1/assistants/{id}/avatar/candidates` | POST | `{user_request, reference_image?}` | 候选列表（有 reference_image = edit） |
| `/v1/assistants/{id}/avatar/set` | POST | `{candidate_id}` | `AvatarActiveBundle` |
| `/v1/assistants/{id}/avatar/clear` | POST | 无 | `AvatarState` |
| `/v1/assistants/{id}/avatar/files/{path}` | GET | 无 | 图片字节（`image/png`） |

错误语义：非法参数 `400`；候选不存在或过期 `409`；assistant 不存在 `404`；路径穿越 `400`。

## 10. WS 推送通道

- 新端点 `/v1/assistants/{id}/events`（Starlette `WebSocketRoute`，经 `registry.register_websocket` 挂载）。
- 用 `get_agent_runtime_redis_client()` 做 Redis pub/sub：`set`/`clear`/视频完成时向 channel `assistant_events:<assistant_id>` 发布 `AvatarUpdatedEvent`。
- WS handler 订阅 channel 并转发给前端；鉴权复用网关 WS 的 JWT 校验；断线自动重连由前端负责。
- 事件类型：`avatar_updated`（set/clear 后立即推）、`avatar_video_ready`（视频异步完成后增量推）。

## 11. 前端补丁

全部经 `deploy/lobehub/patches/` 声明式补丁：

1. `AssistantAvatarImage`：读 `GET /v1/assistants/{id}/avatar`，active 存在渲染图片 URL，否则回退 SVG 萌宠。统一用于聊天顶部、Status drawer、消息气泡旁。
2. `assistantEventClient.ts`：连接 `/v1/assistants/{id}/events`，收到 `avatar_updated` / `avatar_video_ready` 立即刷新共享头像状态。
3. `AssistantAvatarWidget` 升级：候选区展示生成的图片候选（来自 REST），确认调 `POST .../set`，替代当前写 `IDENTITY.md` frontmatter 的方式。
4. 共享 hook/store：三处头像渲染读同一份 active_avatar 状态。
5. 话术：`set` 成功后提示「我的头像换好了」，不说「你的头像」。

## 12. 安全红线

- **reference_image 来源约束**：只允许 ``/files/<attachment_id>`` 用户上传附件引用（FileStore），或省略（=当前 active 头像图片）。裸 base64 / data URI 来源不明，工具入参校验直接拒绝（失败 Observation），REST 返回 400。
- **成人向内容**：工具层不拦截，由生图 provider 自身 policy 判断（与 Muse 一致）。
- **密钥**：`AVATAR_IMAGE_API_KEY` 只从 `.env` 读取，禁止写入日志、回执、prompt 或事件。
- **路径安全**：`/avatar/files/{path}` 白名单 + 路径规范化，防目录穿越；文件只在本助理独立 `avatar/` 目录内解析，跨助理不可达。
- **状态文件**：`avatar/state.json` 走 assistant home 原子写 + revision，不绕过 `AssistantCatalog` 配置面保护。

## 13. 失败语义、幂等与恢复

- **生成失败**：瞬时错误重试 2 次后返回失败；候选不落池。
- **set 幂等**：重复 set 同一候选返回同一 active；已激活候选再次 set 返回当前 active。
- **视频任务失败**：`video_status = failed`，头像仍可用；后续可手动重触发。
- **调度器崩溃**：CronJob 存储为文件，重启后按 `next_run` 重新扫描；已完成的 run 记录不重复写。
- **WS 断线**：前端重连后主动拉一次 `GET /v1/assistants/{id}/avatar` 补齐状态。

## 14. 测试与验证

| 层 | 覆盖 |
|---|---|
| 契约 | `AvatarState`/`AvatarCandidate` 序列化、TTL 计算、过期清理 |
| Provider | mock HTTP：文生图/图编辑/视频轮询、失败重试、URL 下载 |
| 服务状态机 | create 不激活、set 激活/幂等、过期拒绝、clear 恢复、auto_activate 例外 |
| 调度器 | 到期 CronJob 触发换装 + 写回执 + 通知 |
| REST | 鉴权、参数校验、路径穿越防护 |
| WS | publish → 订阅者收到 `avatar_updated` |
| 前端 | patch integrity + vitest（头像组件、WS 客户端事件处理） |
| E2E | 浏览器 :3010：create 出候选 → set → 全端头像刷新 → 视频异步就绪 |

验证命令：`ruff check`、`ruff format`、`pytest tests/lca_plugins/...`、`python3 deploy/lobehub/patch_lobehub.py apply` + `python3 deploy/lobehub/check_patch_integrity.py`。