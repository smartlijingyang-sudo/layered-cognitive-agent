# ADR-0269 — 助理头像生成系统

## 状态

**Proposed — 2026-10-02**

> **一句话**：LCA 用独立 `avatar` 插件落地 Muse 式头像系统 —— 身份感知 prompt 生图、create/edit/set 三态候选池（生成与激活解耦）、多尺寸+异步视频变体、cron 定时换装、轻量 WS 推送通道。

**Extends**：

- [ADR-0255](0255-muse-production-runtime-full-reference.md) 是 Muse 工具与机制的参考清单。本 ADR 把其中 Avatar 一段以 LCA 名字落地为生产契约。
- [ADR-0256](0256-tool-namespace-taxonomy.md) 的 8 域继续有效。本 ADR 增加 `avatar` 工具域，不改其它域。
- [ADR-0264](0264-proactive-messaging-pipeline.md) 的裁决函数继续管定时换装后的轻量通知（DELIVER_CHAT / DELIVER_QUIET / SILENT）。
- [ADR-0268](0268-context-bus-async-executors-and-cron-projection.md) 的 `CronJob` 存储与 `next_run` 被本 ADR 复用为定时换装的载体：`execution=SpaceActionExecution(artifact_id="avatar")`、`body` 存换装请求原文。本 ADR 不修改 cron 契约，也不实现正式 cron worker。

**不 supersede**：`profile.json` 的 `emoji` 字段继续作为默认头像（active 为空时回退）。`IDENTITY.md` 的 `avatar:` frontmatter 历史写法退役，不再新增写入。

---

## 0. 接任务前 7 问

1. **问题是什么？** 用户要能给助理换生成式头像：先看几个候选，选中才生效；助理能定时换装并轻量通知；换装后所有界面立即同步；默认头像一键恢复。
2. **受影响的事实或契约是什么？** 头像候选与激活状态、身份特征来源、生图/视频 provider 契约、REST/WS 事件载荷、cron 换装任务的载体。
3. **唯一真值在哪里？** 头像状态唯一真值在 assistant home 的 `avatar/state.json`。候选池是带 TTL 的中间态。生图结果在写入 `avatar/` 文件后成为事实。WS 事件是投影通知，不承载状态。
4. **改变哪个边界？** 新增 `avatar` 工具命名空间；新增 `/v1/assistants/{id}/avatar/*` REST 路由；新增 `/v1/assistants/{id}/events` WS 通道；新增外部 provider（grok2api 代理）集成。
5. **现有 Protocol / ADR 能否表达？** 不能。0255 是参考清单不是 LCA 契约；现有 `emoji` 头像机制没有候选池、图像生成或定时换装。需要新契约包 `lca/contracts/models/avatar/`。
6. **失败、重试、恢复和幂等语义是什么？** 生成失败：瞬时错误退避重试 2 次，失败不落池。set 幂等：重复 set 同一候选返回同一 active。候选过期：set 返回 409。视频失败：`video_status=failed`，头像可用，可重触发。调度器崩溃：CronJob 文件持久，重启按 `next_run` 重扫。
7. **如何验证？** §14（契约/状态机/调度器/REST/WS 单测 + 前端补丁完整性 + 浏览器 E2E）。

---

## 1. 独立插件边界

新插件 `lca/plugins/avatar/` 拥有：provider HTTP 客户端、文件存储、领域服务、轻量调度器、五个 agent 工具、REST 路由、WS 推送。不扩展现有 `assistant` 插件，不复用 `AssistantAvatarWidget` 的 IDENTITY.md 写入路径。

替代方案：

- **扩展 assistant 插件**：复用现有 widget 但耦合助理生命周期，旧写入路径与 `profile.json` SSOT 冲突，无法独立测试。拒绝。
- **REST-only（无 agent 工具）**：LLM 无法自主换装，定时换装无法由调度器执行，违背 Muse 的「助理能换装」语义。拒绝。

## 2. 数据模型与存储

契约包 `lca/contracts/models/avatar/`：`AvatarVariant`（四尺寸）、`AvatarCandidate`（TTL=created_at+24h）、`AvatarActiveBundle`、`AvatarState`（active 可空 + 候选列表）、`AvatarUpdatedEvent`。

存储布局 `~/.lca/assistants/<id>/avatar/`：`state.json` 为状态 SSOT（原子写 + revision）；`candidates/<candidate_id>/` 与 `active/<candidate_id>/` 各存四尺寸 PNG；`video/<candidate_id>.mp4` 为视频变体。图片经 `GET /v1/assistants/{id}/avatar/files/{path}` 服务（白名单路径防穿越）。

`active == null` 表示默认头像：前端回退 `profile.json` 的 emoji / SVG 萌宠，因此 `clear()` 一键恢复不依赖额外资产。

## 3. 生成管线与身份特征

provider 用本机 grok2api 代理（`AVATAR_IMAGE_BASE_URL` 默认 `http://127.0.0.1:8000/v1`，访问密钥单独配置 `AVATAR_IMAGE_API_KEY` 进 `.env`，不写入本仓库）：

- 文生图：`POST /v1/images/generations`（`grok-imagine-image-lite`）。
- 图生图：`POST /v1/images/edits`（multipart，`AVATAR_IMAGE_EDIT_MODEL`）。
- 视频：`POST /v1/videos` + 轮询 `GET /v1/videos/{id}`，异步生成，完成后推 `avatar_video_ready`。

身份特征（对齐 Muse 的 IDENTITY 混入）：`_load_identity()` 读 `profile.json` + `IDENTITY.md`（若存在）+ `SOUL.md` 身份/性格/语气章节；`_summarize_traits()` 一次 qwen 调用产出 3–6 个英文风格标签，LLM 不可用时确定性 fallback。LLM 摘要器经插件配置 `summarizer_llm` 注入（默认 `None` = 确定性 fallback，为出厂默认）。prompt = `{user_request_verbatim}` + `Identity traits: {traits}`。用户请求原样传递，工具不改写。

## 4. 三态候选池

`avatar_create` / `avatar_edit` 只生成候选（各 4 个）进池，**不激活**；`avatar_set(candidate_id)` 校验在池且未过期 → 拷为 active → 清空候选池 → 推 `avatar_updated` → 异步起视频。`avatar_get` 返回状态；`avatar_clear` 恢复默认。

铁律：用户「创建请求」不等于「对某个候选的批准」，第一轮绝不自动激活。唯一例外是定时换装走内部 `avatar_edit(auto_activate=True)`。候选 24 小时过期，过期后 `set` 返回 409。

## 5. 定时换装

`AvatarCostumeScheduler`（asyncio 后台循环，60s tick）复用 `lca/domain/cron` 的 `CronStore` + `next_run`，扫描 `execution.kind=="space_action" && execution.artifact_id=="avatar"` 的到期任务；触发时读 `job.body` 调用 `avatar_edit(auto_activate=True)`，写 `CronRun` 回执，经 ADR-0264 裁决发轻量通知。`avatar_schedule` 工具负责创建这类 CronJob。

ADR-0268 的正式 cron worker 实现后，本调度器可退役，由 worker 消费同一批 CronJob（`worker_context.py` 已支持 `SpaceActionExecution`）。

## 6. WS 推送通道

新增 `/v1/assistants/{id}/events` WebSocket（`registry.register_websocket` 挂载），用 `get_agent_runtime_redis_client()` 做 Redis pub/sub，channel `assistant_events:<assistant_id>`。`set`/`clear`/视频完成时发布 `AvatarUpdatedEvent`，前端收到即全量刷新。前端保留同 tab `CustomEvent` 兜底，WS 断线重连后主动拉一次 `GET /v1/assistants/{id}/avatar` 补齐状态。

替代方案：**仅轮询**（跨 tab 30s 轮询 avatar 端点）零新基建但非即时，不符合 Muse「set 成功后立即全端刷新」。**复用 run 级网关 WS** 无法覆盖 run 之外的头像变更。均拒绝。

## 7. 安全红线

- `reference_image` 只允许 ``/files/<attachment_id>`` 用户上传附件引用，或省略（=当前 active 头像）；裸 base64 / data URI 来源不明，一律拒绝（工具返回失败 Observation，REST 返回 400）。工具与 REST 入参校验强制。
- 成人向内容由 provider 自身 policy 判断，工具层不拦截。
- `AVATAR_IMAGE_API_KEY` 只从 `.env` 读取，禁止进日志/回执/prompt/事件。
- 图片静态服务白名单 + 路径规范化；每个助理的 avatar 文件只在其独立 ``avatar/`` 目录内解析，跨助理不可达。

## 8. 验证

契约/状态机/调度器/REST/WS 单测 + 前端补丁完整性（`patch_lobehub.py apply` + `check_patch_integrity.py`）+ 浏览器 :3010 E2E（create 出候选 → set → 全端刷新 → 视频异步就绪）。详细矩阵见 [docs/specs/2026-10-02-assistant-avatar-generation-system.md](../specs/2026-10-02-assistant-avatar-generation-system.md)。