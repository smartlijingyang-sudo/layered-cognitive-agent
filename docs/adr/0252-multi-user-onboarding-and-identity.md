# ADR-0252: 多用户登录与 Onboarding 隔离 — LCA 自有数据库 + LobeHub 原生前端

- Status: Implemented — 2026-09-25（PR-1..PR-4 已落地）
- Date: 2026-09-25
- Deciders: 李超 / 山姆汇总
- Relates:
  - ADR-0187: AssistantAgent — 可配置、可隔离、可进化的个人助理产品面
  - ADR-0242: Assistant 创建向导、Home 驱动运行与自我管理
  - ADR-0243: 助理技能/工具隔离与可配置化
  - ADR-0200: Agent Gateway Bridge（WebSocket + Redis Stream）
  - ADR-0202: Transport/UI env 配置 SSOT
- Refines: ADR-0187 §D2 / D4 / D6 / D7 / D12
- Non-goals:
  - 不新建独立 Agent loop，不新增平行 ADR/Note/Protocol 机制
  - 不做 per-user 物理目录隔离（`~/.lca/users/<uid>/assistants/` 形态被否决）
  - 不引入 LCA 自建登录 UI（登录面保持 LobeHub 原生 Better Auth）
  - 不做密码找回 / 邮箱验证 / 社交登录绑定流程（依赖 Better Auth 既有能力）

---

> **一句话**：在 ADR-0187 助理域之上，为 LCA web 面补齐真实登录、按用户隔离的 Onboarding 与数据库支撑的用户↔助理归属关系。身份 SSOT 是 LobeHub Better Auth 的 `users` 表；归属关系由 **LCA 自有数据库**（开发默认 SQLite `~/.lca/lca.sqlite3`，生产可选独立 Postgres 库）全权控制，LobeHub 后端不读不写。助理 Home 保持平铺 `~/.lca/assistants/<id>`，`manifest.json` 记录 `user_id`。Onboarding 复用 LobeHub 原生组件，数据源换成 LCA 角色预设 + 全局技能勾选（默认全选）。

---

## 1. 背景

### 1.1 现状

1. **无登录**。`deploy/lobehub/.env.lca` 设 `ENABLE_MOCK_DEV_USER=1` + `MOCK_DEV_USER_ID=local-dev-user`，前端 `LocalDevAuth` 注入静态用户，Next.js 中间件被补丁跳过会话检查（`deploy/lobehub/patches/auth/middleware_mock_user.py`）。
2. **LCA REST 无鉴权**。`/v1/assistants`、`/runs`、`/v1/sessions` 全部裸奔，`GET /v1/assistants` 返回主机上全部助理（`lca/plugins/transport/webserver/routes_1/routes_assistants.py`）。
3. **无用户概念**。`~/.lca` 只有 `assistants/`、`skills/`、`rooms/` 等，没有 `users/`，助理 Home 与用户无关联。
4. **无数据库支撑**。LCA 侧唯一迁移 `lca/migrations/2026_09_07_lca_running_operations.sql` 未应用；`RunningOperationStore` 已有 SQLite（dev）+ Postgres（生产）双后端先例（`lca/infrastructure/observability/running_operation_store.py`）。
5. **契约已预留**。`CreateAssistantRequest` 已含 `initial_skills` 字段（空值 = 物化全部全局技能），但 `POST /v1/assistants` 路由未解析该字段。
6. **前端集成已打通**。聊天时 `executeGatewayRun.ts` 从 agent 行 `agencyConfig.lcaAssistantId` 读出 `assistant_id` 转发进 `POST /runs`；`AssistantFrontendBridge` 已能把 LCA 助理投影成 LobeHub `agents` 行。

### 1.2 需求

用户进入默认需要登录，账号不一定是邮箱。Onboarding 引导用户创建自己的 agent：创建生成新的 agent 目录并绑定用户 id；`~/.lca` 下 assistant 等配置有管理关联关系；每个用户 onboarding 得到隔离的全新 agent；结合预设让用户知道 agent 的 skill 能力，可勾选，默认全选；其他尽量保持 LobeHub 原生一致，组件 UI 复用。

---

## 2. 决策

### D1 · 身份 SSOT = LobeHub Better Auth `users` 表

登录走 LobeHub 原生 Better Auth（用户名或邮箱均可），`userId` = LobeHub `users.id`，是唯一身份真值。LCA 不自建用户注册表、不维护第二套密码哈希。

理由：保持原生一致，避免重复实现认证，`agents/sessions/messages` 等前端数据继续按同一 `userId` 隔离。LCA 侧 `lca_users` 只是缓存与 onboarding 状态的投影，不是身份事实源。

### D2 · LCA 自有数据库（LCA 全权控制）

归属关系与 onboarding 状态存在 **LCA 自有数据库**，LobeHub 后端不读不写：

| 环境 | 存储 | 路径/连接 |
|---|---|---|
| 开发/默认 | SQLite（WAL） | `~/.lca/lca.sqlite3` |
| 生产 | 独立 Postgres 库 `lca`（非 `lobechat`） | `{from_env: LCA_DATABASE_URL}` 注入 |

沿用 `RunningOperationStore` 双后端模式：SQLite 实现 + Postgres 实现共享同一 DDL 语义。`LCA_DATABASE_URL` 经 Profile `{from_env: ...}` 注入，required:false，插件代码禁止直读 `os.environ`（ADR-0202 纪律）。LCA 自己跑迁移（`lca/migrations/`），LobeHub 的 drizzle 迁移与重置脚本不涉及该库。

### D3 · 数据模型

```sql
-- lca/migrations/2026_09_25_lca_identity.sql（Postgres 版；SQLite 版用 TEXT/JSON 等价 DDL）
CREATE TABLE IF NOT EXISTS lca_users (
  user_id          text PRIMARY KEY,             -- LobeHub users.id，来自可信头
  username         text,
  email            text,
  onboarding_state text NOT NULL DEFAULT 'pending', -- pending|agent_created|completed
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lca_user_assistants (
  user_id        text NOT NULL REFERENCES lca_users(user_id) ON DELETE CASCADE,
  assistant_id   text PRIMARY KEY,               -- asst_*，LCA 磁盘 Home id
  client_id      text NOT NULL,                  -- 前端幂等键
  role_id        text,                           -- 角色卡 id（from_role）
  initial_skills jsonb NOT NULL DEFAULT '[]'::jsonb,
  agent_id       text,                           -- LobeHub agents.id（agt_*），bridge 注册后回填
  status         text NOT NULL DEFAULT 'pending',    -- pending|active|failed
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, client_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS lca_user_assistants_agent_idx
  ON lca_user_assistants (agent_id) WHERE agent_id IS NOT NULL;
```

新文件：

- `lca/contracts/protocols/assistant/ownership.py` — `AssistantOwnership` Protocol + `UserAssistantBinding` frozen dataclass
- `lca/infrastructure/persistence/user_store.py` — SQLite + Postgres 双实现（仿 `RunningOperationStore`）
- `lca/plugins/assistant/ownership/plugin.py` — provide `assistant.ownership`，配置 `{database_url: {from_env: LCA_DATABASE_URL}, dev_mode: bool}`

### D4 · 认证边界：可信头 + 共享 token，可选会话校验

1. 登录后 Next.js 中间件在 `/lca-api/*` 重写请求上注入 `x-lca-user-id: session.user.id`（mock 分支注入 `local-dev-user`）。补丁落在 `deploy/lobehub/patches/auth/lca_user_header.py`，改 `src/libs/next/proxy/define-config.ts`。
2. LCA 侧 auth 依赖校验共享 token（沿用 `X-LCA-Token: lca-local`）并读取 `X-LCA-User-Id` 写入 `request.state.lca_user_id`。缺失头除 `/health`、`OPTIONS` 外返回 401。
3. 可选加固 `LCA_VERIFY_SESSION=1`（默认关）：LCA 用转发 Cookie 调 LobeHub `GET /api/auth/get-session`，校验返回 `user.id` 与头一致，防头伪造。
4. 后续硬化路径 `LCA_AUTH_MODE=jwt`：用短时 LCA JWT（`purpose="lca-rest"`，复用 `mint_user_jwt` / `verify_user_jwt`）替代可信头。第一版预留开关，不实现。

### D5 · 助理 Home 归属

保持平铺 `~/.lca/assistants/<id>`。`manifest.json` 增加顶层 `user_id` 字段，由 `catalog.create` 写入。该字段是归属元数据，**不进配置面 digest**、不触发 `revision_seq`、`revise_profile` 不可改（与 `created_at` 同级）。查询用 DB 表，manifest 字段做离线审计。

`CreateAssistantRequest` 增加 `owner_user_id: str | None = None`；`catalog.list()` 增加 `user_id` 过滤（DB 不可用时回退 manifest 扫描，兼容存量 Home）。

### D6 · REST/run 归属隔离（fail-closed）

- `GET /v1/assistants` 只返回调用者绑定的助理。
- `GET/PATCH /v1/assistants/{id}`、`POST .../skills:install`、`.../retire`、jobs：非 owner 一律 404，不泄露存在性；写操作 403。
- `POST /runs`：`decode_create_run` 对带 `assistant_id` 的请求做归属检查，非 owner 返回 403，不静默回落默认助理。
- `dev_mode=true` 时上述检查全部放行并映射到 `local-dev-user`；`dev_mode=false` 时缺 token 返回 401，fail-closed 无静默兜底。

### D7 · Onboarding 流程（原生组件 + LCA 数据源 + 技能勾选）

1. 原生 onboarding 前缀照旧（Telemetry → ResponseLanguage → FullName → Interests → ProSettings）。
2. `AgentPickerStep` 组件复用，数据源换成 LCA 角色预设。补丁 `deploy/lobehub/patches/onboarding/lca_presets.py` 改 `src/services/agentMarketplace.ts`，把 `lambdaClient.market.agent.getOnboardingFull` 换成 `GET /lca-api/v1/onboarding/presets`。`roles/` 角色卡按 department 映射到原生 `MarketplaceCategory`（未知部门落默认桶），`AgentCard` / `CategoryFilter` 原样渲染。
3. 新增 `SkillCapabilityStep`（插入 Classic 流，`deploy/lobehub/patches/onboarding/skill_picker.py`），从同一 presets 端点的 `skills` 段列出全局技能（`~/.lca/skills` 中含 `SKILL.md` + `manifest.json` 的包），`@lobehub/ui` `Checkbox` 渲染，**默认全选**。
4. Continue 调 `POST /lca-api/v1/assistants`，body 带 `{client_id, name, from_role, initial_skills: [...selected]}`。
5. LCA 后端 `catalog.create` 物化新 Home，只硬链接勾选技能到 `{home}/skills/`；写 `manifest.user_id`；插入 `lca_user_assistants`（status=pending）；bridge 注册 LobeHub agent 行；最后 `status=active`。
6. 前端刷新 agent 列表，调原生 `finishOnboarding()`，跳转 `/chat/<agt_id>`。

新增端点：

- `GET /v1/onboarding/presets` — 角色预设 + 技能目录（经 `role_card_resolver` + 全局技能库）
- `POST /v1/assistants` 扩展 body：`client_id`、`from_role`、`initial_skills`
- `POST /v1/assistants/{id}/register-lobehub` — bridge 注册失败后的重试端点

### D8 · Bridge 投影与幂等

浏览器路径由前端调原生 `agent.createAgent`（agent 行归属真实 `userId`），LCA 侧 `AssistantFrontendBridge` 保留给 dev / CLI / skill 创建路径。bridge 转发 `Cookie` / `Authorization`，并传 `clientId="lca-<assistant_id>"` 做幂等。注意 `CreateAgentSchema` 当前不含 `clientId`，需要一个小补丁 `deploy/lobehub/patches/runtime/lca_bridge_client_id.py` 给 `apps/server/src/routers/lambda/agent.ts` 的 `createAgent` 加 `clientId` 透传，配合 `agents` 表 `client_id_user_id_unique` 唯一索引，重复注册映射为成功。

失败语义：`catalog.create`（磁盘）→ `ownership.bind(pending)` → bridge 注册 → `set_agent_id` + `active`。bridge 失败返回 `agent_id: null` + `status=pending`，UI 提示稍后同步，`register-lobehub` 可重试。列表只展示 `active` 绑定的助理。

### D9 · dev_mode 保持现有 mock 流

`ENABLE_MOCK_DEV_USER=1` 时行为与今天完全一致：中间件注入 `local-dev-user`，LCA `dev_mode=true` 放行，不要求 token。`dev_mode=false` 时 mock 流不可用，强制登录。

---

## 3. 不变量

| ID | 内容 | 验证 |
|---|---|---|
| I-1 | 每个 web 创建的 Home 有且仅有一条 `lca_user_assistants` 记录，且 `manifest.user_id == 请求身份` | 集成测试 |
| I-2 | `GET /v1/assistants` 只返回调用者的助理 | API 测试 |
| I-3 | 非 owner 读 404、写 403，不泄露存在性 | API 测试 |
| I-4 | `POST /runs` 带他人 `assistant_id` 返回 403 | run 测试 |
| I-5 | `user_id` 永远来自可信头/token，不来自 body | 单测 |
| I-6 | `initial_skills` ⊆ 全局技能目录，未知 id 422 | 单测 |
| I-7 | `assistant.created` / `assistant.bootstrap.completed` EP 仅在 Home 创建后发；绑定插入先于 bridge 注册 | EP 闭集测试 |
| I-8 | `dev_mode=true` 与今日行为一致；`dev_mode=false` 缺 token 401，无静默回落 | 回归测试 |

---

## 4. 后果

### 正面

- 真实登录门 + 每用户隔离的助理，产品面完整。
- 归属关系由 LCA 自有数据库控制，不依赖 LobeHub 数据域，迁移/重置互不干扰。
- 复用 LobeHub 原生登录 UI、onboarding 组件与 agent/session 数据域，改动面集中在补丁与少量 LCA 端点。
- 技能勾选直接映射既有 `initial_skills` 契约，默认全选 = 既有"空列表物化全部全局技能"语义。

### 负面 / 代价

- LCA 首次引入自有数据库迁移与读写路径，需要维护 SQLite/Postgres 双后端。
- 可信头依赖 Next.js 中间件为信任边界，公网多租户场景需要升级到 `LCA_AUTH_MODE=jwt`。
- `manifest.user_id` 不进 digest，磁盘文件可被篡改；运行期以 DB 为准。

### 删除条件

| 条件 | 验证 |
|---|---|
| `LCA_AUTH_MODE=jwt` 落地后，可信头路径可删 | `rg "x-lca-user-id" deploy/ lca/` → 0 |
| 归属关系迁入 LobeHub `agents` 行作为 SSOT 后，`lca_user_assistants` 可删 | ADR 更新 + `rg "lca_user_assistants"` → 0 |
| `assistant.ownership` 无部署使用 | profile 无引用 + 数据已迁移 |

---

## 5. 实施 PR 序列

| PR | 内容 | 验收 |
|---|---|---|
| PR-1 | 本 ADR 合入 + 索引更新 | 评审通过 |
| PR-2 | 迁移 + `ownership` 契约/存储/插件（SQLite + Postgres）+ 单测 | `bind/list/owner_of/set_agent_id` 测试绿 |
| PR-3 | `CreateAssistantRequest.owner_user_id` + catalog create/list 归属 + REST 归属 + `initial_skills`/`client_id` 解析 + presets 端点 + `/runs` 归属检查 + `dev_mode` | API 测试 + 存量回归绿 |
| PR-4 | LobeHub 补丁：`lca_user_header`、`lca_presets`、`skill_picker`、`lca_bridge_client_id` + `.env.lca` 切换 | 登录 → onboarding → 聊天 E2E（`agent-testing`）+ mock 回归 |

前置：AGENTS.md §1 gate 3 要求，本 ADR 是能力模型/SSOT 变更的强制门禁；PR-2 起可并行开发 PR-4 的补丁调研，但合入顺序保持 PR-2 → PR-3 → PR-4。

---

## 6. 否决的替代方案

| 方案 | 结论 | 原因 |
|---|---|---|
| `~/.lca/users/<uid>/assistants/` 物理隔离 | 否 | 改动 `assistants_root` 语义，需迁移全部存量 Home，波及 catalog/runs/bridge 每个路径；高爆炸半径，收益有限 |
| LCA 自建身份库 + 自建登录 UI | 否 | 重复 Better Auth，违背"保持原生一致"，身份 SSOT 分裂 |
| LCA-issued JWT 作为第一版认证 | 否 | 增加 exchange 端点、会话校验、密钥管理等移动部件；作为 `LCA_AUTH_MODE=jwt` 硬化路径保留 |
| 两张表放 `lobechat` 库（共库） | 否 | LobeHub 迁移/重置可能波及 LCA 数据；用户明确要求 LCA 自己控制数据库 |
| Onboarding 先走 LobeHub `agent.createAgent` 再建 LCA Home | 否 | 反转 bridge 方向，留下 agent 行指向不存在 Home 的窗口期 |

---

## 7. 开放问题

1. **存量助理归属**：现有 `~/.lca/assistants/*` 无 owner。迁移策略：dev 环境归 `local-dev-user`，或提供"认领"步骤。
2. **`LCA_VERIFY_SESSION` 默认关闭的信任假设**：单机本地部署可接受；公网部署前是否默认开启？
3. **全局技能跨用户共享**：技能目录来自 `~/.lca/skills`，所有用户一致；per-user 技能策展是否后续做？
4. **`roles/` department → `MarketplaceCategory` 映射**：枚举不匹配时落默认桶，是否需要前端展示兜底分类？
5. **多进程 SQLite 并发**：LCA webserver 单进程可接受 WAL；未来多 worker 是否强制 Postgres？

---

## 修订记录

| 日期 | 变更 |
|---|---|
| 2026-09-25 | 初稿；基于三路并行设计探索（LCA 自建身份 / LobeHub 原生 + JWT / 最小混合），采用最小混合为基底，归属数据落 LCA 自有数据库；吸收 JWT 硬化路径与 dev_mode fail-closed 语义 |