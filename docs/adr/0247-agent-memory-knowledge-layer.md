# ADR-0247 — Agent 记忆知识层：从原文存档到结构化知识

## 状态

**Accepted — 2026-09-20**

> **一句话**：把 LCA 的 agent 记忆从"关键词触发的原文存档"升级为结构化知识层——LLM 蒸馏提取、typed `MemoryRecord`、受治理记忆工具、用户画像回填、预算内相关性检索、supersede/遗忘生命周期；同时清理 `workspace_instructions` 污染与硬编码关键词机制，修通 `assistant.bootstrap` 正确通道。

**Extends & Refines**：
- [ADR-0244](0244-cognitive-memory-closed-loop-and-sandbox-convergence.md)（认知记忆闭环）
- [ADR-0242](0242-assistant-creation-home-runtime.md)（Assistant Home 运行时）
- [ADR-0187](0187-assistant-agent.md)（Assistant 域与 bootstrap 投影）
- [ADR-0195](0195-platform-architecture-convergence.md)（SSOT 矩阵）

**Supersedes（部分实现路径）**：ADR-0244 落地时在 `lca/nodes/reflect/score/score.py` 引入的 `_SEMANTIC_DIRECTIVE_MARKERS` 关键词提取，违反 ADR-0244 自身 P4"严禁在图节点硬编码意图正则"。

---

## 0. 接任务前 7 问

1. **问题是什么？** 新创建的产品经理 agent 在连续对话中记不住用户身份："我是架构师"说了三次、跨 3 个 run 约 74 秒后才被写入；记忆文件存的是用户抱怨原文；用户画像模板 `USER.md` 从未被回填；模型没有受治理的记忆工具，只能手动 writeFile 写错文件名。
2. **受影响的事实或契约？** `MemoryRecord` schema、`ContextItem` kind、`remember`/`perceive` 子图节点、assistant 自管理工具族、prompt section 注册、`bundles/web-app.yaml` 装配。
3. **唯一真值在哪里？** 助理长期记忆 SSOT 是 `{home}/memory/` 与 `{home}/USER.md`（ADR-0242）；单次 run 事实流真值是 `Session.append` / `<run_id>.spine.jsonl`；`UserProfile` 由系统从事实流回填，不是模型手动写。
4. **改变哪个边界？** 认知图（reflect/remember 子图）、assistant 域（profile 写入与记忆工具）、prompt 呈现面（新增 `USER_PROFILE` section）、bundle 装配（web-app 移除全局 workspace sensor）。
5. **现有 Protocol / ADR 能否表达？** 能。扩展 ADR-0244 的记忆闭环与 ADR-0242 的 Home 运行时，不开平行机制。
6. **失败、重试、恢复和幂等语义？** 记忆写入走 `CommandEnvelope` + `EffectGateway`（C10 窄门），幂等键绑定 `dedupe_key`；提取 LLM 调用失败时快速路径返回空、不阻塞主流程；检索失败返回空 items；暂停 run 恢复时补跑记忆捕获。
7. **如何验证？** 单元测试（schema/提取/检索/工具契约）+ 集成测试（跨 run 记忆注入）+ 端到端 4 轮连续对话回归。

---

## 1. 问题与现象

### 1.1 run 证据（2026-09-20，`asst_382526fbf2bb`）

| run | 用户说 | 结果 |
|---|---|---|
| `run_68ea0e5c76d4` | 你服务与我 我是架构师 你是产品 我不喜欢啰嗦 | askUserQuestion 暂停，reflect/remember 未执行，身份未持久化 |
| `run_a988646b19ad` | 我的意思 你要记住我啊 | agent 回复"目前我们刚开始对话"；自动记忆只存了原文 |
| `run_3a4dc075f0e4` | 我是架构师啊 之前不是说过吗 你不记住我 也不写入user.md吗 | agent 手动写小写 `user.md`（不在 `CONFIG_FACE_FILES`，永不加载） |

### 1.2 本质

LCA 的记忆链路（捕获 → 提炼 → 存储 → 检索 → 呈现 → 更新遗忘）只有"关键词捕获 + 原文存储"两环。`reflect.score` 的 `_SEMANTIC_DIRECTIVE_MARKERS` 硬编码关键词表命中后把用户原文整句存进 `semantic.json`；检索按 recency 全量返回，无预算、无相关性；`USER.md` 是空模板且因 SOUL 超长被 3000 字符截断而永不进入 prompt；模型没有记忆工具，只能用 writeFile 补救。同时 `assistant.bootstrap`（per-agent 正确投影通道）无运行时代码消费，`WorkspaceInstructionsSensor`（读项目根 AGENTS.md）反而独占 `workspace_instructions` kind。

---

## 2. 业界范式

| 系统 | 关键机制 |
|---|---|
| Hermes Agent | 模型用 `memory` 工具写条目化 MEMORY.md/USER.md（字符上限、重复拒绝、write_approval）；`session_search` 全文检索历史；压缩前 flush 记忆；stable/context/volatile 三层 prompt 装配 |
| Claude Code | CLAUDE.md（用户写）+ Auto Memory（MEMORY.md 索引 + topic 文件、200 行预算、四种记忆类型、Auto Dream 后台合并、freshness 警告） |
| ChatGPT | Saved Memories（结构化事实，用户可见可编辑）+ Reference Chat History（隐式学习） |
| LobeHub 原生 | 后端 LLM 抽取管道：Gatekeeper 判断 + 分层 extractor（identity/preference/context/experience/activity），Postgres + pgvector + BM25，模型用 `lobe-user-memory` 工具检索/写入 |
| OpenClaw | 文件分层记忆（USER.md 指令式 + 原地 supersede、MEMORY.md、日常笔记），hybrid search（向量×关键词×recency 衰减×importance），compaction 前 memory flush，dreaming 后台蒸馏，provenance 闭集防污染 |

业界共识：记忆是**结构化事实**，不是原文日志；写入需要受治理工具与用户可审阅；需要容量/新鲜度/合并/遗忘机制；检索是预算内相关性排序。

---

## 3. 设计

### 3.1 领域模型（DDD）

- **`MemoryRecord`**（实体）：在现有 `layer`（working/semantic/episodic/procedural）之上增加 `category`（identity/preference/fact/episodic/procedural），并携带 `confidence`、`source`（user/tool/model）、`source_trace_id`、`created_at`、`expires_at`、`supersedes`、`status`（active/superseded）、`dedupe_key`。`content` 是提炼后的结构化事实，不是原文。
- **`UserProfile`**（聚合根）：用户身份/偏好/上下文的当前态，SSOT 是 `{home}/USER.md`，由系统从 identity/preference 事实回填，保留 revision 快照（复用 `revisions/`）。
- **`MemoryStore`**（仓储）：`{home}/memory/` 的 typed 读写，支持 `upsert`（按 `dedupe_key`）、`supersede`、`query`。
- **`MemoryRetrievalPolicy`**（领域服务）：`relevance × recency × importance` 排序，受 `token_budget` 约束，排除 superseded/过期记录。
- **`MemoryTool`**（应用服务）：模型可调用的受治理工具（`memory_search` / `memory_add` / `memory_update` / `memory_remove`），走 C10 窄门。

### 3.2 记忆生命周期

```text
capture（用户陈述/工具观察）
  → extract（LLM 蒸馏为结构化 MemoryCandidate，替代关键词表）
  → admit（去重、权威度排序、防污染）
  → write（C10 窄门落盘 memory/）
  → retrieve（perceive 阶段预算内相关性检索）
  → present（USER_PROFILE + CONTEXT 结构化呈现）
  → update/forget（supersede / expires_at / 用户可审阅）
```

### 3.3 图节点改造

1. **`phase.reflect.memory.extract`**（新节点）：输入当前 turn 的 user 消息与 observation，输出结构化 `MemoryCandidate` 列表。用 schema 约束的 LLM 小调用；普通回复零成本快速路径不调 LLM。删除 `score.py` 中 `_SEMANTIC_DIRECTIVE_MARKERS` 与 `_extract_semantic_candidate`。
2. **`phase.remember.admit`**：按 `dedupe_key` 去重，权威度 `user_confirmed > tool_observation > model_inference`，过滤低置信度与原文噪音。
3. **`phase.remember.write`**：落盘 typed `MemoryRecord`，同 `dedupe_key` 新事实把旧记录 `supersede`。
4. **`phase.perceive.memory_retrieve`**：接入 `MemoryRetrievalPolicy`，受 `token_budget` 约束，返回排序后的相关记录，不再全量。

### 3.4 插件化接线

1. 把 `assistant.bootstrap` 投影服务接入 perceive 路径（作为 per-assistant sensor 由 `phase.perceive.observe` 合并），修复死代码通道，让 `workspace_instructions` / `workspace_artifacts` 只来自助理 Home。
2. 从 `bundles/web-app.yaml` 移除 `sensor.workspace-instructions`，保留 sensor 本体给需要读工作目录 AGENTS.md 的 profile。
3. 新增 memory 工具族插件，与现有 `self_manage_tools` 平级，经 `effect_gateway` 执行。

### 3.5 Prompt 呈现

- 新增 `USER_PROFILE` section：渲染 `UserProfile` 结构化画像（称呼/身份/偏好/上下文），独立于原文记忆。
- `CONTEXT` 段记忆行从 `- [semantic] 原文` 改为结构化事实行：`- [identity] 用户：架构师`。

### 3.6 暂停 run 补记

run 在 `askUserQuestion` 等交互点暂停时，恢复路径补跑 reflect/remember，捕获该轮用户已陈述的身份/偏好，避免"说了但没记"。

---

## 4. 落地阶段与 PR

| 阶段 | PR | 内容 | 验证 |
|---|---|---|---|
| 基础 | PR-1 | 契约升级：`MemoryRecord`/`MemoryCategory`/`UserProfile` DTO、`MemoryStore`/`MemoryRetrievalPolicy`/`MemoryTool` Protocol | 单元测试 |
| 基础 | PR-2 | 测试基建：memory 测试 harness、fake store、连续对话回归夹具 | 夹具可用 |
| 接入 | PR-3 | `reflect.memory.extract` LLM 蒸馏 + remember 子图改造 | 单元 + 集成测试 |
| 接入 | PR-4 | `memory_retrieve` 接入检索策略（预算/相关性） | 单元 + 集成测试 |
| 接入 | PR-5 | `USER_PROFILE` section + CONTEXT 结构化行 | 单元 + 集成测试 |
| 接入 | PR-6 | memory 工具族（search/add/update/remove） | 单元 + 集成测试 |
| 接入 | PR-7 | `assistant.bootstrap` 接线 + 移除 workspace sensor | 单元 + 集成测试 |
| 接入 | PR-8 | 暂停 run 恢复补记记忆 | 集成测试 |
| 清理 | PR-9 | 删除关键词表、迁移 `semantic.json`、清理小写 `user.md` | 回归测试 |
| 端到端 | PR-10 | 4 轮连续对话跨 run 记忆回归 | e2e 测试 |

顺序原则：先契约与测试基建，再图节点接入，最后清理垃圾逻辑（`principle-sequence-verifiable-units`）。

---

## 5. 验证矩阵

| 变更类型 | 最低验证 | 必须追加 |
|---|---|---|
| contracts/枚举/事件 | `ruff check` + `ruff format` + 相关 pytest | catalog/whitelist + 序列化兼容 + 重放测试 |
| 图节点（新增 EP） | 上述 | `EXECUTION_POINTS` 白名单 + SpineHandler + 测试 |
| Protocol/公共签名 | 上述 | 全部实现 + 消费者 + mypy + 契约测试 |
| Profile/Bundle | plugin shape + resolve 测试 | DAG + 能力归属 + effects 审计 |
| 记忆写入 | 单元 + 集成 | SSOT + 幂等 + supersede 语义 |
| 端到端 | e2e 连续对话 | 跨 run 记忆注入断言 |

---

## 6. 备选方案

- **保持原文存档（do nothing）**：被否。原文是噪音，长期累积导致检索退化与上下文膨胀，且用户身份无法被模型正确引用。
- **纯向量库记忆**：被否。先落地确定性的结构化知识层（schema + 蒸馏 + supersede），向量检索作为后续可插拔插件，避免一步引入外部依赖。
- **纯 LLM 自主记忆（无图节点）**：被否。模型直接写文件不可审计、不可幂等，违反 C10 窄门与 Reducer 单写纪律。
- **新开 `memory.retrieved` ItemKind**：被否。`kind="memory"` 已是闭集且渲染器已消费，新 kind 波及所有消费者（ADR-0244 已拒）。

---

## 7. 风险与迁移

- 旧 `semantic.json` 原文记录迁移为 typed 格式：PR-9 提供一次性迁移脚本，旧记录标记 `superseded` 而非删除。
- LLM 蒸馏增加成本：仅在用户陈述自我/偏好或显式请求记忆时触发，普通回复走快速路径。
- 删除关键词表的行为变化：由 PR-3 的 LLM 蒸馏替代，集成测试覆盖原关键词表能命中的中文表达（"记住我""叫我老板"）。
- `USER.md` 回填是系统行为，模型不再直接写该文件；`HomeSection` 的"勿用沙箱命令访问"提示保持。