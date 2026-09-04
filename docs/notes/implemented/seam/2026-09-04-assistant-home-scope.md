# Agent Note: AssistantHome — 助理域 seam 边界、配置/记忆/工作区三类真值分层与 ScopePlan 隔离载体

Status: implemented

> 配套 ADR：[ADR-0187](../../../adr/0187-assistant-agent.md)（Accepted — 2026-09-04）。
> 本 Note 记录 ADR-0187 §3 D2/D3/D5/D7 钉下的 seam 边界与不变量的落地口径；
> PR-2…PR-5 已合入（contracts / catalog 插件 / bootstrap+workspace+web-assistant
> profile / gateway 解析），故升 `implemented/`。

## Problem

LCA 现有 Agent 域没有「助理长期面」的概念：AgentSpec（ADR-0033）是声明式输入，RunWorkspace（ADR-0051）是单次 run 的产物账本，Operational Skill（ADR-0048）是全局 store，`~/.lca/agents/` 没有 per-agent 私有 home 目录。要承载「个人助理」产品面（OpenClaw SOUL/IDENTITY/USER/AGENTS/MEMORY/BOOTSTRAP + Hermes skill 自进化 + Grok Bot 多助理路由），存在三个缺口：

1. **真值分层未明**：助理存在三类真值——配置（人设/目标/skill 索引/grant，digest SSOT）、记忆（MEMORY/memory/，追加面）、运行事实（Spine/Journal，0167）。三类变更机制不同：配置低频修订走 `revise`+digest，记忆高频追加走 memory seam，运行事实只写 Spine。混用将导致 digest 抖动或记忆丢失。
2. **隔离载体未定**：`ScopePlan`（`lca/contracts/atoms/scope.py`）已实现 `lifecycle` 8 级 scope + `visibility` scope 集合 + `acl_grants` 衰减 + `budget_ceiling`，但 SpacetimeContext 的 IdentitySpace / VisibilitySpace 子空间是 tracker §三裁剪推迟项。助理身份的「跨助理不可读 memory」语义必须落在已实现最小版上，不依赖未落地的子空间（推迟项应附迁移条款）。
3. **session/run 绑定语义缺位**：现有 `routes_runs_sessions` 不解析 `assistant_id`；`session.persistence_jsonl` 不持久化助理绑定。前端 session/run 无法带助理标识进入 resolve 管线。

## Wire contract

### 三类真值分层（ADR-0187 §3 D2）

| 面 | 内容 | 变更机制 | 进 manifest digest？ | 触发 `revision_seq++`？ |
|---|---|---|---|---|
| 配置（digest SSOT） | profile.json / SOUL / IDENTITY / USER / AGENTS / goals / grants / tools / skills 索引 / routines | `revise`（patch）/ `revise_reimport`（裸改恢复） ⇒ digest 重算 + revisions/ 快照 + EP | 是 |
| 记忆（追加面） | MEMORY.md / memory/ | memory seam（`memory.write_policy` / `memory.retrieval_policy`，`lca/contracts/capabilities.py`） | 否（I-A13） | 否（I-A13） |
| 工作区（执行面） | workspace/ | Body / CommandEnvelope（G7）经 ExecutionSpace effect | 否 | 否 |
| 运行事实 | — | 只写 Spine / Journal（ADR-0167） | — | — |

### `revise` 双模式（ADR-0187 §3 D2）

| 模式 | 语义 | 唯一恢复路径 |
|---|---|---|
| `revise`（patch） | 应用 patch ⇒ digest 重算 ⇒ `revision_seq++` ⇒ `revisions/` 快照 ⇒ EP | — |
| `revise_reimport` | 以磁盘当前文件为输入重算全部配置面 digest ⇒ `revision_seq++` ⇒ 快照 ⇒ EP（`actor="reimport"`） | I-A3 拒收后的恢复 |

裸改本身不是错误：让下次 resolve 拒收生效，直到 `revise_reimport` 重新钉住 digest，把磁盘内容收编为新的受管真值。**不存在第三条写路径**。

### AssistantSpec 形状（ADR-0187 §3 D3）

冻结 dataclass 归 `lca/contracts/models/assistant/spec.py`：

- `assistant_id: str` / `home_path: str` / `revision_seq: int` / `template_id: str` / `profile_name: str` / `profile_description: str`
- `agent_spec: AgentSpec`（ADR-0033 核心，**复用不平行**）
- `bootstrap: AssistantBootstrapRefs`（soul/identity/user/agents digest；MEMORY 不在列）
- `skill_ids: tuple[str, ...]` / `job_ids: tuple[str, ...]` / `grant_digest: str` / `tools_policy_digest: str`

**命名隔离**：`revision_seq` 是助理**配置修订**计数，与 ADR-0169 / 0171 的 `incarnation_seq`（计划维度运行身份）**正交**，不复用同一词。

### 解析时序（ADR-0187 §3 D3, boot vs run）

- **boot 期**：assistant.* 插件按 profile 装配——就绪的是编译与物化能力，不是具体助理实例
- **run 期**：session/run 带 `assistant_id` ⇒ Catalog 读 Home，校验 manifest 配置面 digest（失败 = fail-closed 4xx）⇒ 产出 AgentSpec 形状输入 ⇒ **同一条** Resolve → Compile ⇒ CompiledRunPlan 按 `(assistant_id, manifest_digest)` 缓存
- `revise` ⇒ manifest digest 变化 ⇒ 缓存失效，下一 run 重新 resolve

Home 解析是**数据投影**，不是运行期重装配插件图；boot 期能力就绪 + run 期按 digest 取缓存编译产物 = 「同一条编译器」的全部含义。

### ScopePlan 隔离载体（ADR-0187 §3 D5）

| 边界 | 规则 | ScopePlan 字段 |
|---|---|---|
| Scope | 每次对话/run = 打开 assistant/run scope（父 = profile/agent）；lease 到期 disposer 回收 | `lifecycle` 8 级 scope，`agent` 级值 = `assistant_id` |
| 文件系统 | 工具默认 `workspace_only=true`；根 = Home `workspace/`（ExecutionSpace 事实，非全局单例） | ExecutionSpace（已实现） |
| 身份 | `ScopePlan.lifecycle` 的 `agent` 级 = `assistant_id`；Journal / Spine 以此为载体 | `lifecycle.agent_scope` |
| 能力 | 子 assistant / job / skill 的 capability ⊆ 父 grant；`grants.yaml` 再收窄；扩大只经 G11 promote | `acl_grants` 衰减 |
| 记忆 | 默认不可读其他 `assistant_id` 的 MEMORY/memory/ | `visibility` scope 集合 |
| 技能 | 助理 `skills/` overlay；bundled 只读；进化只写本 Home | — |

**推迟项迁移条款**：IdentitySpace / VisibilitySpace 子空间落地后，助理身份与记忆可见性迁入子空间，I-A2 / I-A6 的验证对象随之切换；本 Note 不以子空间为前置。

### session/run 绑定语义（ADR-0187 §3 D7）

| 入口 | 语义 | 落点 |
|---|---|---|
| `POST /v1/sessions` | 可选 `assistant_id`，建立会话级绑定；缺省 = 遗留默认 agent | `routes_runs_sessions` |
| `POST /v1/sessions/{id}/messages` | 继承会话绑定；body 再传 `assistant_id` 且与绑定不一致 → **409** | `routes_runs_sessions` |
| `POST /runs` | 可选 `assistant_id`（一次性 run，不建立会话绑定） | `routes_runs_sessions` |
| `POST /v1/assistants` / `GET /v1/assistants/{id}` / `PATCH .../profile` / `POST .../skills:install` | 助理管理面 | `routes_assistants`（新插件） |

会话级绑定经 `SessionPersistence` 缝（`lca/contracts/protocols/session/session_persistence.py`）持久化；gateway 只解析与校验，**不持有绑定状态**。

解析失败（未知 id / digest 不匹配）→ **fail-closed** 4xx，不静默回落默认助理（除非显式 `fallback=default`）。

## Decision

ADR-0187 §7 PR-2…PR-5 的 seam 边界已落地；下表是各 seam 的现况落点：

| PR | seam 边界落点 | 状态 |
|---|---|---|
| PR-2 | `contracts/models/assistant/spec.py` AssistantSpec；`contracts/protocols/assistant/catalog.py` Catalog Protocol；capability 键（`assistant.catalog` / `assistant.skill_overlay` / `assistant.evolve` / `assistant.jobs` / `assistant.frontend_bridge`）；EP 描述符（`assistant.created` / `bootstrap.completed` / `profile.revised` / `paused` / `resumed` / `skill.installed` / `skill.activated` / `skill.evolved.proposed` / `skill.evolved.promoted` / `job.registered` / `job.fired` / `retired`） | 已合入 |
| PR-3 | `assistant.catalog` 插件 + AssistantHome 目录布局 + create/get/list | 已合入 |
| PR-4 | bootstrap 注入 ContextManifest + workspace 绑定 ExecutionSpace + `web-assistant` profile；验收含跨助理 memory 隔离测试（I-A6）+ memory seam 按 agent scope 作用域验证 | 已合入 |
| PR-5 | gateway `/assistants` + session/run `assistant_id` 解析 + persistence_jsonl 持久化；web-standard 回归绿 | 已合入 |
| PR-7 | 对话创建流（角色模板 + `create_assistant` 工具 + 前端投影 + run 绑定 + 人设注入）；边界见 [assistant-create-flow](./2026-09-04-assistant-create-flow.md) | 已合入 |

**禁止动作**（来自 ADR-0187 §6 删除条件）：

- 新增 `AssistantRuntime` / `AssistantLoop` / `AssistantCognitiveLoop`
- 平行 `compile_assistant_plan()` 绕开既有 CompiledRunPlan
- 单一服务类同时：写配置 SSOT + 执行世界 effect + 发布新能力
- `install_skill` 实现为「下载后 exec/import 进 live Context」
- Assistant 插件直读 `os.environ` 定 workspace
- 兼容 shim 无 delete-day
- jobs 绕过 ADR-0093 自建调度线程或队列表

## Alternatives considered

### Why not 记忆面也进 manifest digest？

配置低频修订、记忆高频追加，共用一套 digest 变更机制会让每次记忆写入都触发
`revision_seq++` 与快照抖动。分开后记忆走 memory seam 追加、配置走
`revise`+digest（I-A13）。代价是两套变更机制要分别守护——由 I-A13 双向单测承担。

### Why not 用 SpacetimeContext 的 IdentitySpace / VisibilitySpace 子空间做隔离？

这两个子空间是 tracker §三裁剪的推迟项，尚未实现。隔离落在已实现的
`ScopePlan` 最小版（lifecycle 8 级 scope + visibility + acl_grants + budget）
上，子空间落地后按 D5 迁移条款切换。代价是迁移时要换验证对象——已在
Acceptance/Verification 注明。

### Why not 平行编译一条 `compile_assistant_plan()`？

会绕开既有 Resolve→Compile 管线、形成第二套 AgentSpec 编译器，违反
「同一条编译器」原则（ADR-0187 §6 删除条件）。Home 解析是数据投影：
产出 AgentSpec 形状输入喂同一条管线。代价是 resolve 期必须做 digest 校验
（I-A3 fail-closed），换来源真值可信。

## Verification

- 架构测试（`tests/architecture/test_assistant_*.py`）守护 I-A1…I-A13：
  - I-A1：无 `assistant_id` 的 run 行为 = 启用前基线（web-standard 回归绿）
  - I-A2：任意 run 带 `assistant_id` ⇒ `ScopePlan.lifecycle` 的 `agent` 级值 = 该 id（fixture / journal 重建）
  - I-A3：resolve 时配置面 digest 与文件不一致 ⇒ resolve 失败；`revise_reimport` 后通过且 `revision_seq++`（篡改配置 md 不经 revise ⇒ fail-closed）
  - I-A4：`grants.yaml` ⊆ profile grant（property test）
  - I-A5：工具 cwd ⊆ home/workspace（除非显式更高 grant；sandbox test）
  - I-A6：禁止跨助理读 memory（isolation test，memory seam 按 agent scope 作用域验证）
  - I-A7：配置变更 ⇒ `revision_seq++` 且 `revisions/` 有快照
  - I-A8：evolve 提案默认 experiment，非 ACTIVE（gate test）
  - I-A9：不新增顶层 loop 类（importlinter / arch test）
  - I-A10：assistant-runtime 未进 web-standard（profile resolve 快照）
  - I-A11：create/revise/install/pause/resume/retired/evolve/job.registered/job.fired 必发对应 EP（EP 闭集测试）
  - I-A12：jobs 必经 ADR-0093 WorkQueue；assistant.jobs 无常驻线程/定时器
  - I-A13：记忆面写入不经 manifest digest、不触发 `revision_seq`；配置写入必经 revise（unit 双向）
- `rg 'AssistantRuntime|AssistantLoop|compile_assistant_plan' lca` = 0
- `rg 'os\.environ' lca/plugins/assistant` = 0（根路径仅来自 Profile 注入）
- `assistant.evolve` 实现 `SkillAcquirer`（`lca/plugins/skill/auto_acquire.py`），不引入平行进化协议
- EP 描述符全部登记进 `lca/contracts/observability/event_descriptor_registry.py`，cordis event 表映射在 `lca/contracts/observability/cordis_event_table.py`，发射方全部在 `lca/plugins/assistant/*`

## Consequences

落地后仍持有的代价与对应守护：

| 代价 | 守护 |
|---|---|
| **digest 纪律对「随手改配置 md」不友好** | 有意为之；用户应走 `revise` API/skill。裸改通过 `revise_reimport` 收编，**禁止告警后放行** |
| **Home（长期面）vs RunWorkspace（run 账本）两层目录语义混淆** | 文档说清（ADR-0187 §6 负面/代价已记录）；产品面介绍阶段补一张拓扑图 |
| **定时投递源延后**（0187.1） | Phase 1 接受手动 fire（`POST .../jobs/{id}:fire`） |
| **IdentitySpace / VisibilitySpace 子空间推迟** | 隔离全落 `ScopePlan` 已实现最小版；子空间落地后按 D5 迁移条款切换 |
| **session 绑定双落点（routes_runs_sessions + persistence_jsonl）漂移** | 集成测试：会话级绑定经持久化跨进程边界可重建；新增 PATCH 走两条路径结果一致 |
| **`assistant.evolve` 写盘风险** | 默认 experiment 草稿，**默认不落盘**到 `skills/`；须 `write_approval`（人或显式自动策略）后才 promote；架构测试断言 |
| **jobs 隐藏在 assistant.jobs 内的线程/定时器** | I-A12 架构测试扫描 import（`threading` / `asyncio.create_task` / `apscheduler` 等）= 0 |
| **`web-assistant` profile 误进 web-standard** | I-A10 profile resolve 快照测试 |

## Migration status

PR-1…PR-5 已合入；PR-7 对话创建流已合入（边界见
[assistant-create-flow](./2026-09-04-assistant-create-flow.md)）。PR-6
（skill_overlay + install URL）与 PR-8（evolve experiment + jobs 注册/手动
fire）由并行工作推进中。本 Note 已由 `proposed/seam/` 迁至
`implemented/seam/`（PR-3/4 落地后的同批迁移）。

## Related

- ADR-0187 — AssistantAgent 产品面设计门禁
- ADR-0033 — 声明式 AgentSpec（复用 `agent_spec` 字段）
- ADR-0048 — Operational Skill 库（`assistant.skill_overlay` 复用）
- ADR-0051 — Run Workspace Plane（AssistantHome / workspace/ 长期面 vs RunWorkspace / run 账本 区分）
- ADR-0067 — 时空运行时与受治理动态创造（evolve 提案走 0067 闸）
- ADR-0069 — Agent 原语体系与声明组合语法（AssistantAgent 群归属 G1 × G10 × G2）
- ADR-0088 — Profile 选择完整 Agent Loop Runtime（run 期走同一条 Compile）
- ADR-0093 — 持续执行控制面（jobs 坐 WorkQueue，不另起调度）
- ADR-0167 — Spine SSOT（assistant.* EP 落同一总线）
- ADR-0169 / 0171 — Incarnation（与 `revision_seq` 正交，不复用同一词）
- `lca/contracts/atoms/scope.py` — `ScopePlan`（隔离载体已实现最小版）
- `lca/contracts/capabilities.py` — capability 键登记
- `lca/contracts/observability/event_descriptor_registry.py` — EP 描述符登记
- `lca/contracts/observability/cordis_event_table.py` — cordis 事件表映射
- `lca/contracts/protocols/session/session_persistence.py` — SessionPersistence 缝
- `lca/plugins/skill/auto_acquire.py` — `SkillAcquirer` 缝（`assistant.evolve` 复用）