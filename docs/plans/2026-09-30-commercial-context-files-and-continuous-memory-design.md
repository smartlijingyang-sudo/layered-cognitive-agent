# 顶级商用级 Assistant 全景上下文文件体系与持续记忆运行架构设计文档

**文档标识**：`docs/plans/2026-09-30-commercial-context-files-and-continuous-memory-design.md`  
**关联 ADR**：[ADR-0254: 顶级商用级 Assistant 全景上下文文件体系与持续记忆运行架构](../../adr/0254-commercial-context-files-and-continuous-memory-runtime.md)  
**继承与统筹**：[ADR-0242](../../adr/0242-assistant-creation-home-runtime.md) (Home 运行时), [ADR-0247](../../adr/0247-agent-memory-knowledge-layer.md) (知识层), [ADR-0249](../../adr/0249-cadence-inspired-dual-track-memory-consolidation.md) (昼夜固化), [ADR-0253](../../adr/0253-muse-sentinel-egress-and-credential-boundary.md) (凭证边界)  
**自治等级**：`DRAFT`（AP-05）  
**状态**：Approved / Ready for Plan  

---

## 1. 业务背景与第一性原理

### 1.1 业务背景与现状痛点
在单轮对话式 Agent 迈向**长程、自主、可信的商业级 Assistant** 演进中，现有系统普遍存在四层根本缺陷：
1. **记忆与文件割裂**：早期记忆沉淀仅保存在隐式数据库或平铺的 `semantic.json` 中，人设（SOUL）、身份（IDENTITY）、用户边界（USER）、工具避坑经验（AGENTS / TOOLS）与精选记忆（MEMORY）缺乏自包含、人类可审计的文件系统拓扑，无法直接被 Git 版本化或用户无缝查看编辑；
2. **上下文装配静态僵死**：Prompt 仅在会话发起时一次性拼接，在长程运行或后台任务持续运行期间，底层记忆和规则的变更无法实时被活跃会话感知；
3. **会话压缩（Compaction）引发失忆**：长对话中，随着 Token 超限触发摘要压缩，常驻人设、工作手册与记忆被无差别粗暴浓缩，导致 Agent 随对话深入反而“退化变笨”；
4. **认知反思与主对话阻塞**：在对话主路径上强行执行重量级总结与图提取，导致首字延迟（TTFT）激增、Token 浪费严重；且缺乏每条记忆的“出生证明”（Provenance），易产生幽灵记忆。

### 1.2 第一性原理（First Principles）
1. **注意力有界，文件即数据库（File-as-DB）**：大模型本质无状态且注意力窗口易稀释；将长期事实、规则与偏好委托给纯 Markdown 文件，零重量级中间件依赖，人类完全可读可审计；
2. **上下文是动态维护的视图（Continuous Control Plane）**：运行时持续监听底层文件变动（FS Watcher），以 Unified Diff 形式毫秒级注入活跃会话；Compaction 机制将“会话历史摘要”与“常驻文件重注”物理隔离；
3. **主路径轻快，慢变化做梦（Dual-Track Decoupling）**：对话主路径仅执行“读快照 + 检索 + 落笔前写盘”；重型合并、人际图谱维护与对齐综述异步化到后台做梦管线（Upkeep / Dreaming），以最终一致性换取极致响应速度；
4. **规则即代码（Rules as Code）**：检索义务、写盘时机、凭证红线不指望模型自觉，全部编码为 Prompt 强约束指令与 C10 执行窄门；
5. **每条记忆携带出生证明（Provenance as First-class Citizen）**：每条持久记忆强制携带 `This came from... when... recorded...` 标注，综述断言强制绑定消息 ID 引用，实现 100% 可解释与可纠错。

---

## 2. 边界声明与不变量保障

### 2.1 边界清单（AP-01）
* **Owns（本设计负责实现的范围）**：
  1. Assistant Home 下 6 大 Standing Markdown 文件（`AGENTS.md` / `SOUL.md` / `IDENTITY.md` / `USER.md` / `MEMORY.md` / `TOOLS.md`）及关联目录（`memory/`、`dreams/`）的标准拓扑与 Schema 约定；
  2. Runtime 上下文装配引擎（确定性注入顺序、`<!-- INJECTED FILE: ... -->` 锚点格式、子 Agent 继承与 Side Chat 隔离）；
  3. Inotify / FileSystemWatcher 文件变动捕获与活跃会话 Developer Diff 增量推送契约；
  4. Compaction 压缩隔离保护机制（历史轮次摘要与 Standing 文件磁盘最新重注分离）；
  5. 认知层检索决策树（多 Query 扩展、INDEX 级联查找、未命中 rg 兜底）与“落笔前写盘”协议；
  6. 后台自我提升任务集（Hourly Upkeep、Hourly Relationships、Nightly Dreaming 输出 `ALIGNMENT_SYNTHESIS.md`）；
  7. 冲突调和（保留教训修正归因）与 Provenance 溯源格式。
* **Does NOT own（严格负向边界，严禁越权扩散）**：
  1. 不改变认知六相（Perceive / Think / Act / Reflect / Remember）的核心循环闭集（C1）；
  2. 不重写宿主机环境基础设施，不直接修改 `~/everything-library` 外部资产；
  3. 不引入外部分布式锁系统或复杂远程图数据库；
  4. 不修改 LobeHub UI 前端底座核心渲染逻辑（仅对接现有 Gateway 协议与消息流）；
  5. 不在 Cognition 内部绕过 C10 窄门裸调用文件 I/O。

### 2.2 自动化测试不变量矩阵（AP-02 & C1-C14）
* **INV-TOPOLOGY-PURITY**：断言新建 Assistant 的目录树下所有 6 大 Markdown 必须存在且非空，非法文件不能出现在根目录；
* **INV-PROVENANCE-SYNTAX**：断言 `MEMORY.md` 的新增行必须通过 `This came from .* when .* recorded \d{4}-\d{2}-\d{2}` 正则校验；
* **INV-TRAIL-APPEND-ONLY**：断言任何对 `memory/YYYY-MM-DD.md` 的覆写（truncate/overwrite）操作必然抛出 `PermissionDeniedError`，仅放行 `append`；
* **INV-COMPACTION-STANDING-PRESERVATION**：断言触发 Compaction 后，Prompt 中的 `MEMORY.md` 等 Standing 文件与磁盘原件 100% 字节一致，绝无被截断或摘要化；
* **INV-FS-WATCHER-DIFF-DISPATCH**：断言在会话执行中修改 `USER.md`，活动会话在 500ms 内必然接收到带有 Unified Diff 格式的 Developer 消息；
* **INV-WRITE-BEFORE-REPLY**：断言输出“已记住/已保存”的会话步前，必须存在且仅存在一次成功的 `assistant.memory.write` C10 窄门执行回执；
* **INV-SECRET-SANITIZATION-FAIL-LOUD**：断言包含 API Key、密码、卡号特征的记忆写入直接被门禁抛出 `CredentialLeakageAttemptError` 阻断；
* **INV-DREAM-ALIGNMENT-CITATION**：断言做梦产出的 `ALIGNMENT_SYNTHESIS.md` 中所有边界断言必须匹配 `\(message:[a-zA-Z0-9_-]+\)` 证据引用格式。

---

## 3. 存储底座与目录拓扑标准（Markdown-as-DB）

### 3.1 物理目录拓扑
每个助理的物理主目录为 `{home} = ~/.lca/assistants/<asst_id>/`：

```text
{home}/
├── AGENTS.md                   # [Curated] 工作手册：执行规范、工具避坑血训、硬教训
├── SOUL.md                     # [Curated] 人设与基调：非聊天机器人、不讲废话、主见与价值观
├── IDENTITY.md                 # [Curated] 身份标识：Name, Character, Vibe, Emoji
├── USER.md                     # [Curated] 用户画像：称呼、时区、操作授权边界、关心领域
├── MEMORY.md                   # [Curated] 精选长期记忆：事实(Facts)、偏好(Preferences)、承诺(Commitments)
├── TOOLS.md                    # [Curated] 本地工具 quirks：环境特有别名、主机映射、特有避坑
├── memory/
│   ├── YYYY-MM-DD.md           # [Trail] 每日原始交互流水（只追加，不修改，记录 raw evidence）
│   ├── people/                 # [Graph] 人际关系图谱
│   │   ├── INDEX.md            # 人物索引（人名、亲近度排序、对应文件路径，全量注入）
│   │   └── <person_id>.md      # 单人详情页（事实、历史交互、关系性质，按需调读）
│   ├── groups/                 # [Graph] 群体/社群图谱
│   │   ├── INDEX.md
│   │   └── <group_id>.md
│   └── index/                  # [Index] 检索引擎数据库（SQLite FTS5 + BM25，Runtime 私有维护）
├── dreams/
│   ├── YYYY-MM-DD.md           # [Trail] 夜间反思日志（Rupture 分析、修复线索、有效模式）
│   └── alignment/
│       ├── raw/                # 归档的原始对齐证据切片
│       └── derived/
│           └── ALIGNMENT_SYNTHESIS.md # [Curated] 权威对齐综述（带 message:xxx 引用，每轮注入）
└── revisions/                  # [Audit] 历史版本快照（C10 写入前的自动快照备份）
```

### 3.2 三层存储职责划分

| 存储层级 | 载体 | 读写权限 | 注入时机 | 核心职责与一致性保证 |
|---|---|---|---|---|
| **1. Curated 层（精选事实与规则）** | `AGENTS.md` / `SOUL.md` / `IDENTITY.md` / `USER.md` / `MEMORY.md` / `TOOLS.md` / `ALIGNMENT_SYNTHESIS.md` | Agent 经 C10 窄门可读写；后台做梦可维护；用户可直接编辑 | **每轮全量注入**系统提示快照 | **当前唯一有效真值**。保持短小精悍（Strict Budget），新事实覆盖旧事实（newer supersedes older）。 |
| **2. Trail 层（时间序列原始流水）** | `memory/YYYY-MM-DD.md` / `dreams/YYYY-MM-DD.md` | 只追加（Append-only），禁止改写历史 | 不注入上下文，仅由检索/做梦按需访问 | **因果证据链底座**。记录发生时刻的细节（即便后来被取代），支撑 `memory_explain` 与夜间复盘。 |
| **3. Index 层（本地检索引擎）** | `memory/index/`（SQLite FTS5） | **Runtime 拥有**；Agent 只读不可写 | 不注入上下文，提供工具查询 API | **秒级多 Query 检索引擎**。支持分词与模糊匹配，结果可存在毫秒级滞后，文件直接扫为兜底。 |

---

## 4. 运行时控制面与装配机制

### 4.1 会话启动装配顺序（场景 A）
运行时在调用大模型前，必须遵循**确定性顺序拓扑（Order as Priority）**组装上下文：
1. **系统骨架 (System Skeleton)**：角色基础契约、工具集 Schema、全局安全与红线规则；
2. **注入 Standing 全文快照 (Injected Files)**：`AGENTS.md` / `SOUL.md` / `IDENTITY.md` / `USER.md` / `MEMORY.md` / `TOOLS.md` / `people/INDEX.md` / `groups/INDEX.md` / `ALIGNMENT_SYNTHESIS.md`，全部包裹于 `<!-- INJECTED FILE: <name> --> ... <!-- END INJECTED FILE -->` 锚点中；
3. **注入动态运行时状态 (Runtime State)**：当前目标列表 (Goals，含 attention 权重)、当前时间/时区/设备/chat_id、异步任务上下文；
4. **真实交互流水 (History & User Turn)**：历史消息 (或 Compaction 摘要) + 当轮用户消息 (带时间戳)。

### 4.2 FS Watcher 毫秒级 Diff 实时注入（场景 C）
监听 `{home}/` 目录。一旦底层文件被后台任务、用户外部编辑修改，DiffEngine 计算标准 Unified Diff，向当前会话注入一条 Developer 消息：
```text
The system file watcher flagged a change to `~/MEMORY.md`...
--- a/MEMORY.md
+++ b/MEMORY.md
@@ -49,7 +49,9 @@
+- 某项最新确认的事实...
```
Agent 履行“在后续推理中纳入变更（Take the change into account going forward）”契约，无需重读全盘即可实时感知。

### 4.3 会话压缩（Compaction）隔离防护（场景 H）
会话超限触发 Compaction 时：
* **会话历史轨**：将老轮次压缩为精炼 Summary，替换上下文开头的旧轮次；
* **常驻记忆轨**：6 大 Standing 文件**绝对禁止压缩**，直接从磁盘重新读取最新 Snapshot 原件注入；
* **冲突化解规则**：摘要中明确声明“Standing 文件为实时副本，非历史记录；分歧以最新文件证据为准”。

### 4.4 滞后（Staleness）纪律与最终一致性
* 拒绝单机分布式锁，采用应用层守卫：
  1. **读-改-写前必重读磁盘**；
  2. **最新证据胜出（Newer Supersedes Older）**；
  3. **落盘即生效**：写入磁盘成功并收到 Effect Receipt 后才向用户确认。

---

## 5. 认知演化闭环（Fast Path 与 Slow Path）

### 5.1 在线快变轨（Fast Path）
1. **强制检索决策树（场景 D）**：
   * 豁免条件：纯寒暄打招呼、简短无实质确认、逐字复制输入材料；
   * 实质性请求：涉及人名社群读 INDEX；涉及既往决定/偏好/配额必须发起 `memory_search([query_1, query_2, query_3])` 多角度检索，命中后 `memory_get` 精读，未命中直接扫文件兜底；询问出处时调 `memory_explain`；严禁凭空捏造。
2. **落笔前写盘（场景 B）**：
   * 学到 durable 事实时，必须在回复用户前先发起工具调用落盘；
   * 收到写入成功回执后，才允许在最终回复中告知用户“已记下”；
3. **冲突原地调和（场景 E）**：
   * 新事实与旧条目冲突时原地编辑，**修正归因，保留教训**（如标明“此前误诊为 worker，已纠正”），保留真实纠错痕迹，时间线证据高于主观口头断言；
4. **凭证红线绝对隔离**：
   * 密码、Token、卡号、验证码严禁进入记忆，违者门禁 fail-loud 拦截。

### 5.2 离线慢变轨（Slow Path 做梦管线，场景 F）
与 [ADR-0249](../../adr/0249-cadence-inspired-dual-track-memory-consolidation.md) 闭环联动，由 `lca-ops memory dream` 调度执行：
1. **Hourly Memory Upkeep**：新轮次提炼事实入 `MEMORY.md`，执行 Claim 去重与取代，原始细节进 `memory/YYYY-MM-DD.md`；
2. **Hourly Relationships**：维护 `memory/people/` 与 `groups/`，更新 INDEX 亲密度排序；
3. **Nightly Dreaming**：
   * 检测用户纠错裂痕（Ruptures，如“你问太多了”）；
   * 提炼有效协作模式（Effective Patterns，如“直接给可用结果”）；
   * 输出夜间反思日志 `dreams/YYYY-MM-DD.md`；
   * 合成权威对齐综述 `dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md`（含画像、价值观、边界、摩擦、默契建议，带 `message:xxx` 引用）；
4. **次日全量装配**：新版综述随 Standing 文件全量注入，实现人设与风格的自适应“调参”对齐。

---

## 6. 分阶段落地实施计划（Roadmap）

* **M1 阶段 (P0 - 存储底座与装配闭环)**：
  - 标准化 Assistant Home 6 大 Standing Markdown 模板与目录拓扑；
  - 升级上下文组装器，支持 `<!-- INJECTED FILE: ... -->` 锚点与顺序优先级；
  - 落地 Provenance 出生证明后缀格式契约；
  - 落地自动化测试：`INV-TOPOLOGY-PURITY` 与 `INV-PROVENANCE-SYNTAX`。
* **M2 阶段 (P1 - 运行时动态感知与防护)**：
  - 落地 Compaction 双轨隔离协议；
  - 落地 Inotify / FileSystemWatcher 文件变动推送 Unified Diff 开发者消息；
  - System Prompt 注入强制检索决策树与“落笔前写盘”铁律；
  - 落地自动化测试：`INV-COMPACTION-STANDING-PRESERVATION` 与 `INV-FS-WATCHER-DIFF-DISPATCH`。
* **M3 阶段 (P2 - 昼夜做梦与对齐自演化)**：
  - 对接 ADR-0249 Consolidation Engine，接入 `lca-ops memory dream`；
  - 落地 Hourly Upkeep 与 Relationships 图谱维护；
  - 落地 Nightly Rupture 检测与 `ALIGNMENT_SYNTHESIS.md` 证据链生成；
  - 落地自动化测试：`INV-DREAM-ALIGNMENT-CITATION`。
