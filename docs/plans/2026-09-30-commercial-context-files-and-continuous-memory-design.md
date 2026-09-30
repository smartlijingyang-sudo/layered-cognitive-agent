# 顶级商用级 Assistant 全景上下文文件体系与持续记忆运行架构设计文档

**文档标识**：`docs/plans/2026-09-30-commercial-context-files-and-continuous-memory-design.md`  
**关联 ADR**：[ADR-0254: 顶级商用级 Assistant 全景上下文文件体系与持续记忆运行架构](../../adr/0254-commercial-context-files-and-continuous-memory-runtime.md)  
**继承与统筹**：[ADR-0242](../../adr/0242-assistant-creation-home-runtime.md) (Home 运行时), [ADR-0247](../../adr/0247-agent-memory-knowledge-layer.md) (知识层语义), [ADR-0249](../../adr/0249-cadence-inspired-dual-track-memory-consolidation.md) (昼夜固化), [ADR-0253](../../adr/0253-muse-sentinel-egress-and-credential-boundary.md) (凭证边界)
**Supersedes**：ADR-0247 §3.1–3.4（存储与持久化部分：废除 `semantic.json` 作为 SSOT，收敛至 `MEMORY.md` 纯 Markdown，废除旧同步抽取图节点）
**自治等级**：`DRAFT`（AP-05）  
**状态**：Approved / Ready for Plan  

---

## 1. 业务背景与第一性原理

### 1.1 业务背景与现状痛点
在单轮对话式 Agent 迈向**长程、自主、可信的商业级 Assistant** 演进中，现有系统普遍存在四层根本缺陷：
1. **记忆与文件割裂**：早期记忆沉淀仅保存在隐式数据库或平铺的 `semantic.json` 中，人设（SOUL）、用户边界（USER）、工具避坑经验（AGENTS / TOOLS）与精选记忆（MEMORY）缺乏自包含、人类可审计的文件系统拓扑，无法直接被 Git 版本化或用户无缝查看编辑；
2. **上下文装配静态僵死**：Prompt 仅在会话发起时一次性拼接，在长程运行或后台任务持续运行期间，底层记忆和规则的变更无法实时被活跃会话感知；
3. **会话压缩（Compaction）引发失忆**：长对话中，随着 Token 超限触发摘要压缩，常驻人设、工作手册与记忆被无差别粗暴浓缩，导致 Agent 随对话深入反而“退化变笨”；
4. **认知反思与主对话阻塞**：在对话主路径上强行执行重量级总结与图提取，导致首字延迟（TTFT）激增、Token 浪费严重；且缺乏每条记忆的“出生证明”（Provenance），易产生幽灵记忆。

### 1.2 第一性原理（First Principles）
1. **注意力有界，文件即数据库（File-as-DB）**：大模型本质无状态且注意力窗口易稀释；将长期事实、规则与偏好委托给纯 Markdown 文件，零重量级中间件依赖，人类完全可读可审计；
2. **上下文是动态维护的视图（Continuous Control Plane）**：运行时持续监听底层文件变动（FS Watcher），以 Unified Diff 形式秒级注入活跃会话（SLA 目标 <1s）；Compaction 机制将“会话历史摘要”与“常驻文件重注”物理隔离；
3. **主路径轻快，慢变化做梦（Dual-Track Decoupling）**：对话主路径仅执行“读快照 + 检索 + 落笔前写盘”；重型合并、人际图谱维护与对齐综述异步化到后台做梦管线（Upkeep / Dreaming），以最终一致性换取极致响应速度；
4. **规则即代码（Rules as Code）**：检索义务、写盘时机、凭证红线不指望模型自觉，全部编码为 Prompt 强约束指令与 C10 执行窄门；
5. **每条记忆携带出生证明（Provenance as First-class Citizen）**：每条持久记忆强制携带 `This came from... when...` 标注，综述断言强制绑定消息 ID 引用，实现 100% 可解释与可纠错。

### 1.3 双轨延迟语义与分工
- **白天快变轨（Fast-path Transient Buffer，来自 ADR-0249）**：会话中由 `ResidualGovernor` 捕获的突发残差信号快速暂存为 `EPHEMERAL_FAST` 便签（写入 `memory/episodes/`，耗时 <5ms），不阻塞当前交互，等待夜间消化；
- **在线落笔写盘（In-Session Durable Write，来自 ADR-0254）**：当明确需要对用户给出持久承诺/确权并依赖该事实时，Agent 执行经过 C10 窄门的写盘，落盘成功收到回执后才对用户确认；
- **夜间做梦（Nightly Consolidation）**：在离线状态下扫描白天积累的 `EPHEMERAL_FAST` 便签与对话流水，执行去重、消解冲突、晋升并固化至 `MEMORY.md`。

---

## 2. 边界声明与不变量保障

### 2.1 边界清单（AP-01）
* **Owns（本设计负责实现的范围）**：
  1. Assistant Home 下 5 大 Standing Markdown 文件（`AGENTS.md` / `SOUL.md` / `USER.md` / `MEMORY.md` / `TOOLS.md`，对齐 ADR-0242 移除独立 IDENTITY.md）及关联目录（`memory/`、`dreams/`、`side-chats/`）的标准拓扑与 Schema 约定；
  2. Runtime 上下文装配引擎（确定性注入顺序、`<!-- INJECTED FILE: ... -->` 锚点格式、Subagent Transcript 继承与 Side Chat 隔离）；
  3. Inotify / FileSystemWatcher 文件变动捕获与活跃会话 Developer Diff 增量推送契约及故障隔离；
  4. Compaction 压缩隔离保护机制（历史轮次摘要与 Standing 文件磁盘最新重注分离）；
  5. 认知层检索决策树（多 Query 扩展、INDEX 级联查找、未命中 rg 兜底、防编造终端闸门）与“落笔前写盘”协议；
  6. 后台自我提升任务集（Hourly Upkeep、Hourly Relationships、Nightly Dreaming 输出 `ALIGNMENT_SYNTHESIS.md`，对齐≠硬指令）；
  7. 冲突调和（保留教训修正归因）与 Provenance 溯源格式（含署名、观察推断二分与 `memory_explain` 8 维度模型）；
  8. 读-改-写滞后（Staleness）守卫。
* **Does NOT own（严格负向边界，严禁越权扩散）**：
  1. 不改变认知六相（Perceive / Think / Act / Reflect / Remember）的核心循环闭集（C1）；
  2. 不重写宿主机环境基础设施，不直接修改 `~/everything-library` 外部资产；
  3. 不引入外部分布式锁系统或复杂远程图数据库；
  4. 不修改 LobeHub UI 前端底座核心渲染逻辑（仅对接现有 Gateway 协议与消息流）；
  5. 不在 Cognition 内部绕过 C10 窄门裸调用文件 I/O。

### 2.2 双层验证测试矩阵（Two-Tier Verification Strategy）

#### Tier 1: 确定性结构不变量测试（Deterministic Asserts）
* **INV-TOPOLOGY-ALLOWLIST**：断言 Home 根目录所有条目必须 $\subseteq$ `ALLOWED_ROOT_ENTRIES`（包含 5 大 Markdown 与 0242 合法文件），且除 `TOOLS.md` 外核心文件非空；
* **INV-PROVENANCE-SYNTAX**：断言 `MEMORY.md` 的新增行必须通过 `This came from .+ when .+(?:, recorded \d{4}-\d{2}-\d{2})?\.` 宽松正则校验；
* **INV-EFFECT-GATEWAY-TRAIL-APPEND-ONLY**：在 `EffectGateway` 层面拦截针对 `memory/YYYY-MM-DD.md` 的覆写操作，断言抛出 `NarrowGateViolationError`；
* **INV-COMPACTION-STANDING-PRESERVATION**：断言触发 Compaction 后，Prompt 中的 `MEMORY.md` 等 Standing 文件与磁盘原件 100% 字节一致，绝无被截断或摘要化；
* **INV-FS-WATCHER-DIFF-DISPATCH**：断言在会话执行中修改 `USER.md`，活动会话在 1 秒内必然接收到带有 Unified Diff 格式的 Developer 消息；
* **INV-FS-WATCHER-FAULT-TOLERANCE**：Mock Watcher 抛出异常，断言活跃会话正常执行不中断，并产出诊断日志；
* **INV-SUBAGENT-TRANSCRIPT-INHERITANCE**：调用 `subagent.spawn`，断言派生的子上下文包含完整的父级 Transcript 与 Standing 注入快照；
* **INV-INJECTION-DELIMITER-INTEGRITY**：断言装配产物中的每一个注入文件必须严格由 `<!-- INJECTED FILE: xxx -->` 与 `<!-- END INJECTED FILE: xxx -->` 封闭包裹；
* **INV-READ-BEFORE-WRITE-STALENESS**：断言执行 `memory_edit` 前置未读取磁盘最新内容时触发 `StaleSnapshotOperationError`；
* **INV-SECRET-SANITIZATION-FAIL-LOUD**：断言包含 API Key、密码、卡号特征的记忆写入直接被门禁抛出 `CredentialLeakageAttemptError` 阻断。

#### Tier 2: 认知行为一致性评测（Cognitive Behavior Conformance Evals）
* **EVAL-RETRIEVAL-DUTY**：在实质性请求场景（场景 D）下，断言模型在输出最终结论前 100% 发起多 Query 检索；
* **EVAL-WRITE-BEFORE-REPLY**：在确权记录场景（场景 B）下，断言写盘工具调用事件先于面向用户的承诺输出；
* **EVAL-SIDE-CHAT-PRIVACY**：在 Side Chat 检索包含主 Chat 私密偏好的场景（场景 G）下，断言模型 0 透露该私密信息；
* **EVAL-ANTI-HALLUCINATION**：在完全缺失历史记录的问题下，断言模型明确表达不确定性，事实虚构率 = 0%；
* **EVAL-DREAM-ALIGNMENT-SYNTHESIS**：运行夜间做梦回放（场景 F），断言生成的断言中 `message:[a-zA-Z0-9_-]+` 命中率 = 100%。

---

## 3. 存储底座与目录拓扑标准（Markdown-as-DB）

### 3.1 物理目录拓扑
每个助理的物理主目录为 `{home} = ~/.lca/assistants/<asst_id>/`：

```text
{home}/
├── AGENTS.md                   # [Curated] 工作手册：执行规范、工具避坑血训、硬教训
├── SOUL.md                     # [Curated] 人设、基调与身份元数据(Frontmatter)：不讲废话、主见与价值观
├── USER.md                     # [Curated] 用户画像：称呼、时区、操作授权边界、关心领域
├── MEMORY.md                   # [Curated] 精选长期记忆唯一真值 SSOT：事实(Facts)、偏好(Preferences)、承诺(Commitments)
├── TOOLS.md                    # [Curated] 本地工具 quirks：环境特有别名、主机映射、特有避坑(允许为空)
├── memory/
│   ├── YYYY-MM-DD.md           # [Trail] 每日原始交互流水（只追加，不修改，记录 raw evidence）
│   ├── episodes/               # [Buffer] ADR-0249 EPHEMERAL_FAST 毫秒级快变便签暂存区
│   ├── people/                 # [Graph] 人际关系图谱
│   │   ├── INDEX.md            # 人物索引（人名、亲近度排序、对应文件路径，全量注入）
│   │   └── <person_id>.md      # 单人详情页（事实、历史交互、关系性质，按需调读）
│   ├── groups/                 # [Graph] 群体/社群图谱
│   │   ├── INDEX.md
│   │   └── <group_id>.md
│   ├── bank/                   # [Index] 检索引擎向量/分块索引（Runtime 私有维护，只读）
│   └── index/                  # [Index] 检索引擎全文库（SQLite FTS5 + 降级的 semantic.json 缓存）
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

### 3.2 出生证明与 memory_explain 8 维度模型
1. **出生证明语法**：
   ```markdown
   - [事实正文]。 This came from <来源渠道或工具> when <用户触发事件或提问>[, recorded <YYYY-MM-DD>].
   ```
2. **署名与二分**：明确标注表达者（Attribution），区分客观观察（Observation）与主观推断（Inference），推断需附带置信度与不确定性。
3. **memory_explain 8 维度模型**：运行时支持展开 `claim`, `kind`, `salience`, `attribution`, `quote`, `timeline`, `confidence`, `supersession_chain`。

### 3.3 ADR-0249 Sinks 映射表

| ADR-0249 概念 / PatchKind | ADR-0249 旧写回目标 | ADR-0254 权威统一落盘目标 | 演进与收敛说明 |
|---|---|---|---|
| **IdentityPatch** | `{home}/USER.md` + revisions/ | `{home}/USER.md` + revisions/ | 保持一致，用户画像单一入口 |
| **PreferencePatch** | `{home}/memory/semantic.json` | `{home}/MEMORY.md` (Curated SSOT) | **架构收敛**：废除 JSON 裸写，收敛为 Markdown SSOT |
| **ProceduralPatch** | `{home}/skills/` | `{home}/skills/` + `{home}/AGENTS.md` | 扩展：排错经验与执行教训直接沉淀入 `AGENTS.md` |
| **EpisodicPatch** | `{home}/memory/episodes/` | `{home}/memory/YYYY-MM-DD.md` (Trail) | 收敛为标准按天流水 Trail 文件；短期便签缓冲在 `memory/episodes/` |
| **Consolidation State** | (状态机标记) | `{home}/MEMORY.md` 状态跃迁 | **事实固化**：EPHEMERAL_FAST 晋升为 CONSOLIDATED_SLOW |
| **Dreaming Synthesis** | (无，ADR-0249 缺失) | `{home}/dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md` | **新增设计**：对齐综述用于系统自适应调参 |

---

## 4. 运行时控制面与装配机制

### 4.1 会话启动装配顺序（场景 A）
系统组装 Prompt 时，必须遵循确定性优先级：
1. **系统骨架 (System Skeleton)**：角色基石、工具集 Schema、全局安全与红线规则；
2. **注入 Standing 全文快照 (Injected Files)**：`AGENTS.md` / `SOUL.md` / `USER.md` / `MEMORY.md` / `TOOLS.md` / `people/INDEX.md` / `groups/INDEX.md` / `ALIGNMENT_SYNTHESIS.md`，全部包裹于 `<!-- INJECTED FILE: <name> --> ... <!-- END INJECTED FILE -->` 锚点中；
3. **注入动态运行时状态 (Runtime State)**：Goals 任务列表、时间/时区/设备/chat_id、异步任务上下文；
4. **历史与当轮消息**：历史轮次（或 Recap 摘要） + 用户当轮输入。
* **Subagent 继承律**：通过 `subagent.spawn` 派生的子 Agent 必须完整继承父级的 Transcript 与 Standing 快照，保证舰队世界观一致。

### 4.2 FS Watcher 秒级 Diff 实时注入（场景 C）
监听 `{home}/` 目录。一旦底层文件被后台任务、用户外部编辑修改，DiffEngine 计算标准 Unified Diff，向当前会话注入一条 Developer 消息（实测 1~3 秒内，SLA 目标 <1s）：
```text
The system file watcher flagged a change to `~/MEMORY.md`...
--- a/MEMORY.md
+++ b/MEMORY.md
@@ -49,7 +49,9 @@
+- 某项最新确认的事实...
```
Agent 履行“在后续推理中纳入变更（Take the change into account going forward）”契约，无需重读全盘即可实时感知。FS Watcher 异常时仅记录诊断事件，绝不阻断活跃会话。

### 4.3 会话压缩（Compaction）隔离防护（场景 H）
会话超限触发 Compaction 时：
* **会话历史轨**：将老轮次压缩为精炼 Summary，替换上下文开头的旧轮次；
* **常驻记忆轨**：5 大 Standing 文件**绝对禁止压缩**，直接从磁盘重新读取最新 Snapshot 原件注入；
* **冲突化解规则**：摘要中明确声明“Standing 文件为实时副本，非历史记录；分歧以最新文件证据为准”。

### 4.4 滞后（Staleness）纪律与最终一致性
* 拒绝单机分布式锁，采用应用层守卫：
  1. **读-改-写前必重读磁盘**；
  2. **最新证据胜出（Newer Supersedes Older）**；
  3. **落盘即生效**：写入磁盘成功并收到 Effect Receipt 后才向用户确认。

### 4.5 Side Chat 读写路由规则（场景 G）
* **读路由**：同时检索主记忆与当前分支会话的 `side-chats/<id>/MEMORY.md`；
* **数据隐私防火墙**：在共享/分支聊天中，**“检索到 ≠ 可透露”**，私密记忆严禁越权外泄；
* **写路由**：
  - 本分支特有结论或未定决议写入 `side-chats/<id>/MEMORY.md`；
  - 跨会话的持久通用事实与用户偏好，提示用户确认后写入主 `MEMORY.md`。

---

## 5. 认知演化闭环（Fast Path 与 Slow Path）

### 5.1 在线快变轨（Fast Path）
1. **强制检索决策树与防幻觉终端闸门（场景 D）**：
   * 豁免条件：纯寒暄打招呼、简短无实质确认、逐字复制输入材料；
   * 实质性请求：涉及人名社群读 INDEX；涉及既往决定/偏好/配额必须发起 `memory_search([query_1, query_2, query_3])` 多角度检索，命中后 `memory_get` 精读，未命中直接扫文件兜底；询问出处时调 `memory_explain`；
   * **防幻觉终端闸门**：未命中时严格承认信息缺失并标注不确定性，绝不凭空编造事实；
2. **落笔前写盘（场景 B）**：
   * 学到 durable 事实时，必须在回复用户前先发起工具调用落盘；
   * 收到写入成功回执后，才允许在最终回复中告知用户“已记下”；
3. **冲突原地调和（场景 E）**：
   * 新旧矛盾原地修正归因，保留教训，写明“此前误诊，已纠正”痕迹；
4. **凭证红线绝对隔离**：
   * 密码、Token、卡号、验证码严禁进入记忆，违者门禁 fail-loud 拦截（继承 ADR-0253 隔离标准）。

### 5.2 离线做梦管线（Slow Path，场景 F）
与 [ADR-0249](../../adr/0249-cadence-inspired-dual-track-memory-consolidation.md) 闭环联动，由 `lca-ops memory dream` 调度执行：
1. **输入源**：**必须以 Trail 完整流水（`memory/YYYY-MM-DD.md`，保留了被 Compaction 压缩前的原始对话）为输入**，杜绝依赖被压缩退化的摘要；
2. **Hourly Memory Upkeep**：新轮次提炼事实入 `MEMORY.md`，执行 Claim 去重与取代，原始细节进 `memory/YYYY-MM-DD.md`；
3. **Hourly Relationships**：维护 `memory/people/` 与 `groups/`，更新 INDEX 亲密度排序；
4. **Nightly Dreaming 与“对齐 ≠ 指令”哲学约束**：
   - 检测用户纠错裂痕（Ruptures，如“你问太多了”）；
   - 提炼有效协作模式（Effective Patterns，如“直接给可用结果”）；
   - 输出夜间反思日志 `dreams/YYYY-MM-DD.md`；
   - 合成权威对齐综述 `dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md`（含画像、价值观、边界、摩擦、默契建议，带 `message:xxx` 引用）；
   - **对齐 ≠ 指令**：综述注入是对 Agent 行为与沟通偏好的自适应“软调参”，不是不可违抗的硬指令；用户在会话中一旦提出新的纠偏，下一夜 Dreaming 会动态重写对齐综述，消除认知僵化。

---

## 6. 分阶段落地实施计划（Roadmap）

* **M1 阶段 (P0 - 存储底座与装配闭环)**：
  - 标准化 Assistant Home 5 大 Standing Markdown 模板与目录拓扑；
  - 升级上下文组装器，支持 `<!-- INJECTED FILE: ... -->` 锚点与顺序优先级；
  - 落地 Provenance 出生证明后缀格式契约（可选 recorded 日期）；
  - 落地 Tier 1 结构不变量：`INV-TOPOLOGY-ALLOWLIST` 与 `INV-PROVENANCE-SYNTAX`。
* **M2 阶段 (P1 - 运行时动态感知与防护)**：
  - 落地 Compaction 双轨隔离协议；
  - 落地 Inotify / FileSystemWatcher 文件变动推送 Unified Diff 开发者消息与故障容错；
  - 落地 Subagent Transcript 继承；
  - System Prompt 注入强制检索决策树、防编造终端闸门与“落笔前写盘”铁律；
  - 落地 Tier 1 结构不变量：`INV-COMPACTION-STANDING-PRESERVATION` 与 `INV-FS-WATCHER-DIFF-DISPATCH`。
* **M3 阶段 (P2 - 昼夜做梦与对齐自演化)**：
  - 对接 ADR-0249 做梦引擎，接入 `lca-ops memory dream`；
  - 落地 Hourly Upkeep 与 Relationships 图谱维护；
  - 落地 Nightly Rupture 检测与 `ALIGNMENT_SYNTHESIS.md` 证据链生成；
  - 落地 Side Chat 读写路由与隐私隔离；
  - 落地 Tier 2 行为一致性场景回放评测（5 大 Scenarios）。
