# ADR-0254 — 顶级商用级 Assistant 全景上下文文件体系与持续记忆运行架构

## 状态

**Proposed — 2026-09-30**

> **一句话**：借鉴生产环境实测的 Context Muse 体系与业界顶尖商用范式，将 LCA Assistant 的上下文与记忆体系统一收敛为“纯 Markdown-as-DB 三层分级底座（5 大核心 Standing 文件）”、“运行时连续控制面（FS Watcher 实时 Diff 注入 + 物理隔离 Compaction 防失忆）”与“昼夜双轨闭环（在线强制检索写盘 + 离线做梦对齐综述）”，彻底打破长程对话性能衰减、失忆与认知阻塞，实现工业级高可信自演化。

**Extends & Unifies**：
- [ADR-0242](0242-assistant-creation-home-runtime.md)（Assistant Home 运行时与自我管理）：对齐 Assistant Home 规范，收敛核心 Standing Markdown 体系；
- [ADR-0247](0247-agent-memory-knowledge-layer.md)（Agent 记忆知识层）：继承 typed `MemoryRecord` 概念并升级为三层存储（Curated / Trail / Index）与全景 Provenance；
- [ADR-0249](0249-cadence-inspired-dual-track-memory-consolidation.md)（基于 Cadence 生物范式的昼夜双轨记忆固化架构）：统筹底层做梦管线，落地工业级 Upkeep、Relationships 与 Nightly `ALIGNMENT_SYNTHESIS.md` 生成；
- [ADR-0253](0253-muse-sentinel-egress-and-credential-boundary.md)（出站控制面与凭证边界）：继承敏感凭证绝不入记忆的 C5/C10 红线治理；
- [ADR-0195](0195-platform-architecture-convergence.md)（平台架构收敛与信息血统闭合）。

**Supersedes**：
- [ADR-0247](0247-agent-memory-knowledge-layer.md) §3.1–3.4（存储与持久化部分）：废除将 `memory/semantic.json` 作为长期记忆唯一真值 SSOT 的设定，长期记忆 SSOT 全面收敛为 `{home}/MEMORY.md` 纯 Markdown；`semantic.json` 与 SQLite FTS5 并列降级为 Runtime 拥有的只读派生索引与检索缓存。

---

## 0. 接任务前 7 问

1. **问题是什么？**
   传统 Agent 在长程对话中面临四大工业级痛点：① 记忆分散在黑盒数据库或散落 JSON，人类无法直观审计或 Git 版本化；② 上下文装配静态僵死，底层规则变更无法实时被运行中会话感知；③ 会话超限触发 Compaction 时常驻人设与工作手册被无差别压缩导致“严重失忆”；④ 主路径同步抽取分析导致单轮高延迟与幽灵记忆，缺乏证据溯源。
2. **受影响的事实或契约是什么？**
   `AssistantHome` 目录规范、`ContextAssembly` 运行时协议、`FileSystemWatcher` 差异事件、`CompactionStrategy` 隔离协议、`MemoryRecord` 出生证明格式、`AlignmentSynthesis` 领域聚合根与 `CommandEnvelope` 记忆写入窄门。
3. **唯一真值在哪里？**
   - Assistant 长期规则与事实 SSOT：`{home}/AGENTS.md`、`{home}/SOUL.md`、`{home}/USER.md`、`{home}/MEMORY.md`、`{home}/TOOLS.md` 与 `{home}/dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md`；
   - 交互流水因果流 SSOT：`Session.append` 与 `{home}/memory/YYYY-MM-DD.md`；
   - 检索引擎与缓存 SSOT：`{home}/memory/bank/` 与 `{home}/memory/index/`（含降级的 `semantic.json`，Runtime 私有维护，Agent 只读）。
4. **改变哪个边界？**
   - 契约层：标准化 5 大 Standing Markdown 规范与 Provenance 标注格式；
   - 运行时层：增强连续控制面，引入 FS Watcher Diff 注入与 Compaction 隔离装配器；
   - 基础设施层：实现三层存储拓扑、Inotify 监听器与本地 FTS5 / Bank 索引；
   - 认知层：注入强制检索决策树与“落笔前写盘”铁律，对接离线做梦管线。
5. **现有 Protocol / ADR 能否表达？**
   不能完全表达。ADR-0242 仅规范静态 Home 骨架且废除 IDENTITY.md，ADR-0247 将 JSON 作为 SSOT 导致血统割裂，ADR-0249 聚焦生物做梦底层。必须由本 ADR 统筹收敛为顶层集大成者（Capstone Architecture）。
6. **失败、重试、恢复和幂等语义是什么？**
   - FS Watcher 注入失败不阻断正常会话；
   - Compaction 历史摘要失败自动告警并优雅降级为有界滑窗，Standing 文件重注具备绝对确定性与幂等性；
   - 记忆写盘严格走特化 `CommandEnvelope(capability="assistant.memory.write", scope="{home}")`（继承 ADR-0249 §3.1 执行窄门与 ADR-0253 §3.2 凭证审计），写盘成功收到 Effect Receipt 才向用户确认，失败原子回滚并如实汇报。
7. **如何验证？**
   - 拓扑纯洁性单测（`INV-TOPOLOGY-PURITY`）；
   - 出生证明正则校验（`INV-PROVENANCE-SYNTAX`）；
   - 历史压缩隔离测试（`INV-COMPACTION-STANDING-PRESERVATION`）；
   - Watcher Diff 实时注入测试（`INV-FS-WATCHER-DIFF-DISPATCH`）；
   - 凭证防泄漏红线拦截测试（`INV-SECRET-SANITIZATION-FAIL-LOUD`）；
   - Side Chat 隔离守卫测试（`INV-SIDE-CHAT-PRIVACY-ISOLATION`）；
   - 读-改-写滞后守卫测试（`INV-READ-BEFORE-WRITE-STALENESS`）。

---

## 1. 业界对标与生产实测背景

### 1.1 业界代表性系统对照

| 维度 | 传统 RAG / 向量外挂 | Claude Code / Auto Memory | OpenClaw / Hermes | Context Muse（实测 Athena） | LCA ADR-0254 目标 |
|---|---|---|---|---|---|
| **存储底座** | 远程向量库 / JSON | CLAUDE.md + 200行 MEMORY.md | USER.md + MEMORY.md + 技能库 | **纯 Markdown-as-DB 三层拓扑**（Curated / Trail / Index） | **统一 5 大 Markdown 拓扑 + Trail + Index + Bank** |
| **运行时动态感知** | 无，每次请求冷拉取 | 静态装配，单次刷新 | 会话启动时静态注入 | **Inotify Watcher 秒级 Diff 实时注入** | **FS Watcher Unified Diff 开发者消息注入（SLA <1s）** |
| **长会话压缩** | 粗暴截断 / 全量摘要 | 摘要压缩，记忆常驻 | Compaction 前 flush | **会话历史压缩，Standing 文件磁盘重注** | **物理隔离双轨 Compaction 协议** |
| **检索行为** | 模型自决，易漏检 | 静态索引感知 | 工具检索 + 关键词 | **Prompt 硬性检索决策树（多 Query + 降级）** | **强制检索义务 + 多角度 Query + rg 兜底** |
| **记忆更新** | 轮次同步提取，阻塞 | 后台 Auto Dream | memory 工具 + 审批 | **落笔前写盘 + 冲突原地修正 + 凭证红线** | **落笔前写盘 + 修正归因保留教训 + C10 窄门** |
| **对齐与演化** | 无 | 新鲜度警告 | 基因匹配自演化 | **Nightly Dreaming 输出带引用的对齐综述** | **做梦管线输出 ALIGNMENT_SYNTHESIS.md** |

### 1.2 生产环境 8 大场景实录（来自 2026-09-30 活体验证）
1. **场景 A（启动装配）**：顺序即优先级（骨架 → Standing 快照 → 运行时状态 → 用户消息），子 Agent 完整继承父级 Transcript 与 Standing 快照；
2. **场景 B（记忆生命周期）**：T0 提问检索 → T1 实查官方状态 → T2 落笔前写盘并带 Provenance → T3 当晚 Upkeep 去重入 Trail → T4 次日召回；
3. **场景 C（文件变更 Diff 实时注入）**：后台改动 `MEMORY.md`，数秒内（实测 1~3s）Watcher 向活跃会话推送 Unified Diff，Agent 无感同步最新知识；
4. **场景 D（检索决策树）**：豁免纯寒暄与确认，其余实质请求必须多 Query 检索，未命中直接扫文件兜底；
5. **场景 E（冲突调和）**：修正归因不删教训（如将 worker 越权更正为主 agent 越权，保留“此前误诊”痕迹）；
6. **场景 F（Dreaming 一夜流程）**：扫描 Ruptures 与有效模式，写 dated 反思，合成带 `message:xxx` 引用的 `ALIGNMENT_SYNTHESIS.md` 次日注入“调参”；
7. **场景 G（Side Chat 隔离）**：独立分支对话隔离记忆（`side-chats/<id>/MEMORY.md`），双向检索但严格坚守“检索到 ≠ 可透露”；
8. **场景 H（Compaction 机制）**：压缩轮次历史，不压缩记忆，Standing 文件按磁盘最新 Snapshot 重新注入。

---

## 2. 第一性原理与架构模型

```text
                                 ┌──────────────────────────────────────────────────────────┐
                                 │                 Continuous Control Plane                 │
                                 │       (FileSystemWatcher / Ingestion / Compaction)       │
                                 └───────────┬──────────────────────┬───────────────────────┘
                                             │                      │
                                   启动装配 / 磁盘重注          变动触发 Unified Diff
                                             │                      │
                                             ▼                      ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   Agent 在线交互平面 (Fast Path)                                    │
│   1. Perceive: 消费注入快照 + 接收实时 Diff 增量                                                   │
│   2. Think: 触发强制检索决策树 (memory_search / get / explain)                                     │
│   3. Act: 执行业务动作；若产生持久事实，遵循【落笔前写盘】经 C10 窄门写入                              │
└────────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                             │ 互补解耦，最终一致
                                             ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   离线做梦演化平面 (Slow Path)                                     │
│   1. Hourly Memory Upkeep: 消费对话流水，事实去重整合至 MEMORY.md，原始细节进 memory/YYYY-MM-DD.md │
│   2. Hourly Relationships: 维护 people/ 与 groups/ 图谱及 INDEX.md 亲密度排序                      │
│   3. Nightly Dreaming: 深度复盘 Ruptures，沉淀 dreams/，合成带证据链引用的 ALIGNMENT_SYNTHESIS.md   │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 领域驱动设计（DDD）与物理拓扑

### 3.1 Assistant Home 文件系统拓扑标准
对齐 ADR-0242 的清理要求，**彻底移除独立的 `IDENTITY.md`**，身份元数据（Name/Character/Vibe/Emoji）以 `meta.json` 为真值并通过 `SOUL.md` 表达。核心 Standing 文件规范收敛为 **5 大文件**：

```text
{home}/
├── AGENTS.md                   # [Curated] 工作手册：执行规范、工具避坑血训、硬教训
├── SOUL.md                     # [Curated] 人设与基调：非聊天机器人、不讲废话、主见与价值观
├── USER.md                     # [Curated] 用户画像：称呼、时区、操作授权边界、关心领域
├── MEMORY.md                   # [Curated] 精选长期记忆唯一真值 SSOT：事实(Facts)、偏好(Preferences)、承诺(Commitments)
├── TOOLS.md                    # [Curated] 本地工具 quirks：环境特有别名、主机映射、特有避坑
├── memory/
│   ├── YYYY-MM-DD.md           # [Trail] 每日原始交互流水（只追加，不修改，记录 raw evidence）
│   ├── people/                 # [Graph] 人际关系图谱
│   │   ├── INDEX.md            # 人物索引（人名、亲近度排序、对应文件路径，全量注入）
│   │   └── <person_id>.md      # 单人详情页（事实、历史交互、关系性质，按需调读）
│   ├── groups/                 # [Graph] 群体/社群图谱
│   │   ├── INDEX.md
│   │   └── <group_id>.md
│   ├── bank/                   # [Index] 检索引擎向量/块索引（Runtime 私有维护，只读）
│   └── index/                  # [Index] 检索引擎全文数据库（SQLite FTS5 + 降级的 semantic.json 缓存）
├── side-chats/                 # [Isolation] 独立分支会话记忆隔离区
│   └── <chat_id>/
│       └── MEMORY.md           # 分支会话专属长期记忆（遵循检索到≠可跨聊透露）
├── dreams/
│   ├── YYYY-MM-DD.md           # [Trail] 夜间反思日志（Rupture 分析、修复线索、有效模式）
│   └── alignment/
│       ├── raw/                # 归档的原始对齐证据切片
│       └── derived/
│           └── ALIGNMENT_SYNTHESIS.md # [Curated] 权威对齐综述（带 message:xxx 引用，每轮注入）
└── revisions/                  # [Audit] 历史版本快照（LCA 架构增强项，继承 ADR-0242/0249 快照机制）
```

### 3.2 出生证明（Provenance Suffix）契约
`MEMORY.md` 中的每一条长期断言，必须携带标准化出生证明，`, recorded <日期>` 设为可选兼容模式：
```markdown
- [事实正文]。 This came from <来源渠道或工具> when <用户触发事件或提问>[, recorded <YYYY-MM-DD>].
```

### 3.3 ADR-0249 Sinks 到 ADR-0254 的映射矩阵
为确保架构无缝收敛，ADR-0249 定义的四大 Patch 与固化产物，在 ADR-0254 中建立确定的落盘目标映射：

| ADR-0249 概念 / PatchKind | ADR-0249 旧写回目标 | ADR-0254 权威统一落盘目标 | 演进与收敛说明 |
|---|---|---|---|
| **IdentityPatch** | `{home}/USER.md` + revisions/ | `{home}/USER.md` + revisions/ | 保持一致，用户画像单一入口 |
| **PreferencePatch** | `{home}/memory/semantic.json` | `{home}/MEMORY.md` (Curated SSOT) | **架构收敛**：废除 JSON 裸写，收敛为 Markdown SSOT |
| **ProceduralPatch** | `{home}/skills/` | `{home}/skills/` + `{home}/AGENTS.md` | 扩展：排错经验与执行教训直接沉淀入 `AGENTS.md` |
| **EpisodicPatch** | `{home}/memory/episodes/` | `{home}/memory/YYYY-MM-DD.md` | 收敛为标准按天流水 Trail 文件 |
| **Consolidation Output** | (仅作为状态机跃迁标记) | `{home}/dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md` | 具象化：产出权威对齐综述用于系统自适应调参 |

---

## 4. 运行时连续控制面（Continuous Runtime Plane）

### 4.1 会话启动装配拓扑
系统组装 Prompt 时，必须遵循确定性优先级：
1. **系统骨架**：角色基石、工具集 Schema（C5 约束）、安全红线；
2. **Standing 文件快照**：5 大文件及对齐综述内容由 `<!-- INJECTED FILE: <name> --> ... <!-- END INJECTED FILE: <name> -->` 封闭包裹；
3. **运行时动态状态**：Goals 任务列表、时间/时区/设备/chat_id；
4. **历史与当轮消息**：历史轮次（或 Recap 摘要） + 用户当轮输入。
* **Subagent 继承律**：通过 `subagent.spawn` 派生的子 Agent，必须完整继承父级的 Transcript 与 Standing 快照，保证舰队世界观一致。

### 4.2 FS Watcher 秒级 Diff 实时注入
Runtime 启动 Inotify 监听器。当任一 Standing 文件在磁盘发生变更（文件 hash 改变）：
- DiffEngine 生成标准 Unified Diff；
- 向当前活跃 Session 队列注入 Developer Diff 消息（实测 1~3 秒内，SLA 目标 <1s）；
- Agent 恪守“在后续推理中纳入该变更”规则，实现上下文的无感自愈与动态感知。

### 4.3 物理隔离 Compaction 协议
当对话超限触发 Compaction 时：
- **历史对话轨**：压缩为摘要替代老轮次；
- **常驻记忆轨**：5 大 Standing 文件绝不参与压缩，重新从磁盘加载最新 Snapshot 注入；
- 摘要中明确注入指示：*“Standing context files are live current copies and are not part of the compacted history. Resolve factual conflicts using the latest applicable evidence.”*

### 4.4 注入快照滞后（Staleness）纪律与最终一致性
- 注入上下文是快照不是实时视图（Snapshot not live view）；
- 拒绝单机分布式锁，采用应用层守卫：
  1. **读-改-写前必重读磁盘**：Agent 执行 `memory_edit` 时必须先读取最新文件行；
  2. **最新证据胜出（Newer Supersedes Older）**；
  3. **落盘即生效**：写入磁盘成功并收到 Effect Receipt 后才向用户确认。

---

## 5. 认知闭环与演化管线（Cognition & Consolidation）

### 5.1 在线快变轨（Fast Path）
1. **强制检索决策树**：
   - 仅纯寒暄、简短无实质确认、逐字复制当轮材料 3 类情况豁免检索；
   - 其余请求必须发起 `memory_search([query_1, query_2, query_3])`，命中后 `memory_get` 精读，未命中扫文件兜底；
2. **落笔前写盘（Write Before Replying）**：
   - Durable 事实必须先发起工具调用并经 C10 窄门写入磁盘，获得成功回执后，才允许向用户回复“已记下”；
3. **冲突调和**：
   - 新旧矛盾原地修正归因，保留教训，写明“此前误诊，已纠正”痕迹；
4. **凭证红线**：
   - 密码、API Key、卡号等机密绝对禁止进记忆，违者门禁抛出 `CredentialLeakageAttemptError`。

### 5.2 离线做梦管线（Slow Path）
与 [ADR-0249](0249-cadence-inspired-dual-track-memory-consolidation.md) 对接，由后台任务调度（`lca-ops memory dream`）：
- **Hourly Upkeep**：对话事实去重整合至 `MEMORY.md`，原始流水写入 `memory/YYYY-MM-DD.md`；
- **Hourly Relationships**：维护 `people/` 与 `groups/` 图谱与亲近度索引；
- **Nightly Dreaming**：检测用户纠错裂痕（Ruptures）与有效交付模式，输出 `dreams/YYYY-MM-DD.md` 并合成带 `message:xxx` 证据引用的 `ALIGNMENT_SYNTHESIS.md`，次日清晨全量注入调参。

---

## 6. LCA 五层映射与架构不变量硬性断言矩阵

### 6.1 LCA 五层映射

| LCA 层 | 本架构职责落位 |
|---|---|
| **contracts** | Markdown 格式规范、HTML 注入注释协议、`INDEX.md` 目录格式、Provenance 后缀正则 |
| **infrastructure** | Assistant Home 文件系统目录树、Inotify FS Watcher 监听器、`memory/index/` 与 `memory/bank/` 检索引擎 |
| **cognition** | `memory_search/get/explain` 检索语义、多 Query 扩展策略、Rupture 裂痕检测、对齐综述提炼 |
| **runtime** | 上下文组装器（顺序优先级）、Compaction 隔离处理器、FS Watcher Diff 消息分发器 |
| **agent** | 强制检索义务、落笔前写盘、读-改-写前读磁盘、凭证红线拦截 |

### 6.2 架构不变量硬性断言矩阵（AP-02 & C1-C14）

| 不变量 ID | 不变量要求 | 自动化测试中的确定性断言（Deterministic Asserts） | 测试用例规划 |
|---|---|---|---|
| **INV-TOPOLOGY-PURITY** | 目录拓扑纯洁性 | `assert_topology_valid(asst_home)`：断言 5 大 Markdown 必须存在且非空，非法文件不能出现在根目录 | `tests/contracts/test_context_files_topology.py` |
| **INV-PROVENANCE-SYNTAX** | 出生证明语法合规 | 正则匹配校验：`re.match(r".*This came from .+ when .+(?:, recorded \d{4}-\d{2}-\d{2})?\.", line)` | `tests/contracts/test_memory_provenance_syntax.py` |
| **INV-TRAIL-APPEND-ONLY** | 流水日志只追加 | 断言任何覆写操作（`mode='w'`）触发 `PermissionDeniedError`，仅放行 `mode='a'` | `tests/infrastructure/memory/test_trail_append_only.py` |
| **INV-COMPACTION-STANDING-PRESERVATION** | 压缩不稀释常驻记忆 | 对话超限执行压缩后，断言 Prompt 中的 `MEMORY.md` 全文与磁盘文件 100% 字节一致 | `tests/runtime/test_compaction_standing_isolation.py` |
| **INV-FS-WATCHER-DIFF-DISPATCH** | 文件变动动态感知 | 修改 `USER.md` 后，断言活跃会话队列在 1 秒内收到带有 `unified diff` 格式的 Developer 消息 | `tests/runtime/test_fs_watcher_diff_dispatch.py` |
| **INV-WRITE-BEFORE-REPLY** | 落笔前写盘铁律 | 断言输出“已保存/记住了”前，Trace 中必然存在合法的 `assistant.memory.write` C10 执行回执 | `tests/cognition/test_write_before_reply_guard.py` |
| **INV-SECRET-SANITIZATION-FAIL-LOUD** | 凭证防泄漏红线 | 写入含 `sk-` / Token / 密码特征内容，断言抛出 `CredentialLeakageAttemptError` 阻断 | `tests/infrastructure/memory/test_secret_leak_block.py` |
| **INV-DREAM-ALIGNMENT-CITATION** | 对齐综述证据链绑定 | 断言 `ALIGNMENT_SYNTHESIS.md` 中所有边界断言必须匹配 `\(message:[a-zA-Z0-9_-]+\)` 引用 | `tests/cognition/test_dream_alignment_citation.py` |
| **INV-SIDE-CHAT-PRIVACY-ISOLATION** | Side Chat 隐私防火墙 | 断言分支 Chat 中检索到的私密上下文条目在跨 Chat 输出时被隐私过滤器阻断 | `tests/runtime/test_side_chat_privacy_isolation.py` |
| **INV-READ-BEFORE-WRITE-STALENESS** | 读-改-写磁盘重读保障 | 断言执行 `memory_edit` 前置未读取磁盘最新内容时触发 `StaleSnapshotOperationError` | `tests/infrastructure/memory/test_read_before_write_staleness.py` |

---

## 7. 落地实施路线图（Roadmap）

- **M1 阶段 (P0 - 存储底座与装配闭环)**：标准化 5 大 Markdown 模板、组装器 `<!-- INJECTED FILE: ... -->` 锚点、放宽的 Provenance 正则校验与拓扑测试；
- **M2 阶段 (P1 - 运行时动态感知与防护)**：Compaction 隔离协议、FS Watcher Diff 推送、System Prompt 检索决策树注入与写盘守卫测试；
- **M3 阶段 (P2 - 昼夜做梦与对齐自演化)**：对接 ADR-0249 做梦引擎、Hourly Upkeep 与 Relationships 图谱、Nightly 对齐综述生成与端到端实机验证。
