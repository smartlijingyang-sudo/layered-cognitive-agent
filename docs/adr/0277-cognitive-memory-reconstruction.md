# ADR-0277：记忆机制的认知重构——typed 记忆对象 + perceive 传感器注册表 + remember 显式 consolidation

## 状态

**Proposed — 2026-10-03**

> **一句话**：LCA 的记忆从"文件堆 + 裸文本注入"升级为"typed 认知对象"——perceive 阶段拿到的是带置信度/来源/双时间线的记忆感知，remember 阶段做的是显式的 consolidation 四决策（encode/link/decay/schema）；设计吸取 Letta（agent 自管记忆 + sleep-time compute）、Zep/Graphiti（双时间线 + 失效不删除）、Mem0（extract→reconcile 四操作）、ACT-R（激活度检索评分）、Soar（四记忆各自独立学习机制）。

## 0. 接任务前 7 问（精简自检）

1. 谁受益？LCA 的 loop：perceive 拿到的记忆从"不可解释的文本块"变成"可评分、可追溯的感知"；remember 从"写文件"变成"可审计的决策"。
2. 真实问题？三处实锤缺口（见 §1.3）：① perceive 注入的是裸文本，无类型、无置信度、无来源——think 无法判断该信多少；② 记忆只增不减，无衰减机制，旧垃圾永久堆积；③ 提取只有语义相似度，无 recency×salience×confidence 评分，模型只能"硬信"检索结果。
3. 删掉会坏什么？不坏——新设计；但记忆质量继续靠"多写点文本"碰运气，且与人类记忆科学的距离保持为零。
4. 更简单方案？只加置信度字段。否决：单字段补丁修不了"无类型→无决策→无审计"的链条问题；且业界已证明（Mem0 的 ADD/UPDATE/DELETE/NOOP、Zep 的双时间线）记忆需要的是**机制**不是字段。
5. 契约先行？是。C1–C6 先定义类型与决策，落地后补。
6. 与现有 ADR 冲突？无。0260（检索义务）、0261（standing 注入）是"记忆进 prompt 的义务层"，本 ADR 是"记忆对象本身的类型层"——正交。loop 的 remember phase 已存在，本 ADR 给它语义。
7. 状态诚实？Proposed。类型定义、评分公式、传感器注册表均为设计，未落地一行代码。

## 1. 实证

### 1.1 人类记忆模型（认知科学侧）

- **Atkinson-Shiffrin（1968）**：感觉记忆 → 短时记忆 → 长时记忆，三级存储，容量/时长逐级变化。对应：tool 结果（感觉）→ 对话上下文（短时）→ 持久化存储（长时）。LCA 目前三级都有，但**级间转换无显式规则**（什么值得从短时进长时？靠人工）。
- **Baddeley 工作记忆（1974/2000）**：中央执行器 + 语音环 + 视空间画板 + 情景缓冲器。关键洞察：工作记忆不是"一块内存"，是**被中央执行器调度的多通道系统**。对应缺口：LCA 的 perceive 把记忆文本直接铺进上下文，无调度、无通道区分。
- **Tulving（1972/1983）**：情景记忆（何时何地何事）vs 语义记忆（提炼的事实）vs 程序性记忆（怎么做）。对应：LCA 的 L1 日志 ≈ 情景，L2 MEMORY.md ≈ 语义，skills/ ≈ 程序性——**分层碰巧对上了，但不是按模型设计的**，所以缺了模型自带的附属机制（见下）。
- **Ebbinghaus 遗忘曲线 + Jost 第二定律**：记忆强度随时间衰减，旧记忆比新记忆衰减慢。对应缺口：**LCA 的记忆无衰减函数**，2026-09 的过期事实与今天的事实权重相同。
- **Craik & Lockhart 编码深度（1972）**：加工越深记得越牢。对应缺口：**LCA 无编码门控**——remember 阶段"学到就写"，没有 salience 评估。
- **系统巩固（McClelland & McNaughton）**：睡眠时海马向皮层转移，提取的是**图式（schema）**而非原始事件。对应缺口：LCA 的夜间 job 只是"整理文字"，没有"从 episodic 提取 semantic"的显式步骤。

### 1.2 业界顶级机制（2026-10 核验）

- **Letta / MemGPT（arXiv:2310.08560，2025 年演进 sleep-time compute）**：OS 式三级记忆（core 常驻上下文 / recall 对话历史 / archival 外部存储），**agent 自己管理记忆**（core_memory_replace/append）。2025 年关键演进：主 agent 不再自己改记忆，**独立的 sleep-time agent 在空闲时重写记忆块**（raw context → learned context，去重、整理）。可抄：① 记忆管理是 agent 的**一等职责**，不是外部管道；② consolidation 与在线交互**分离**（在线快、离线深）。
- **Zep / Graphiti（Rasmussen et al., arXiv:2501.13956）**：双时间线知识图谱——每条边带 4 个时间戳（`t_created`/`t_expired` 系统时间：何时学到/何时退役；`t_valid`/`t_invalid` 世界时间：何时为真/何时不再为真）。**被取代的事实标记失效而非删除**，可回答"上周二我们相信什么"。DMR 94.8%（vs MemGPT 93.4%），LongMemEval +18.5%。可抄：① 双时间线；② 失效不删除（non-lossy contradiction handling）。
- **Mem0（arXiv:2504.19413）**：两阶段管道——**Extraction**（LLM 从对话提候选事实）→ **Update**（对每条候选检索 top-k 相似记忆，LLM 裁决 ADD / UPDATE / DELETE / NOOP）。60k+ stars，LOCOMO 上 +26%。可抄：① 写路径必须有 **reconcile 步骤**（新记忆先跟旧记忆对账，不许直接堆）；② 四操作是完备的（增/改/删/不管）。
- **ACT-R（Anderson）**：激活度检索——`activation = base-level（新近性+频率的幂律衰减） + spreading（线索关联扩散） + noise`。这是遗忘曲线 + 提取评分的**数学形式**，不是比喻。可抄：检索打分公式，不止语义相似度。
- **Soar（Laird）**：四记忆（working/semantic/episodic/procedural）+ **每种记忆有独立的学习机制**（chunking 学程序、episodic learning 记事件、semantic learning 提炼、强化学习调权重）。可抄：不同类型记忆用不同 consolidation 策略，不要一刀切。

### 1.3 LCA 侧缺口实锤

- **无类型**：`memory_search` 返回文本块直接注入 prompt（0260 只规定了"必须检索"的义务，未规定返回物的类型）。think 收到一段文本，不知道它是"上周的用户原话"还是"三个月前的推断"，置信度无从谈起。
- **无衰减**：`supersede` 有替换链（0260 T4），但那是显式覆盖；**自然衰减不存在**——长期未命中的低价值记忆永久占用检索候选池。
- **无评分**：检索 = 语义相似度 top-k。ACT-R 告诉我们这丢了 recency、frequency、salience 三个维度。
- **无 reconcile**：remember 阶段写文件前，不与现有记忆做 ADD/UPDATE/DELETE/NOOP 裁决（Mem0 的核心步骤缺失）。

## 2. 设计

### 2.1 Typed 记忆对象（三类，对应 Tulving + Soar）

```python
@dataclass
class EpisodicTrace:
    id: str
    when: datetime          # 世界时间（Zep 的 t_valid）
    ingested_at: datetime   # 系统时间（Zep 的 t_created）
    who: list[str]          # 相关人物（接 people/ 图谱）
    what: str               # 事件原文（non-lossy，Mem0 批评过"丢原文"）
    salience: float         # 显著性 0..1（编码门控用）

@dataclass
class SemanticClaim:
    id: str
    claim: str
    confidence: float       # 0..1
    sources: list[str]      # provenance：trace id / 文档 / 对话轮次
    valid_from: datetime | None   # Zep 双时间线
    valid_to: datetime | None     # None = 当前有效；被取代时填值，不删除
    supersedes: str | None  # 指向被取代的 claim id（0260 T4 的 revision_of 链）

@dataclass
class ProceduralRule:
    id: str
    trigger: str            # 何时适用（自然语言 + 可选的结构化条件）
    action: str             # 做什么
    scope: str              # 适用范围（lane / 全局 / 某项目）
```

### 2.2 perceive：记忆传感器注册表

记忆不再以裸文本进上下文，而是注册为 perceive 阶段的传感器（对齐 loop 的"传感器注册表"思想，ADR-0254）：

- `EpisodicSensor`：按时间/人物/事件线索召回 → `EpisodicPercept{trace, recency_score}`
- `SemanticSensor`：按主题查 claims（只返回 `valid_to IS NULL` 的当前有效集，历史查询走显式 `as_of` 参数）→ `SemanticPercept{claim, confidence, sources}`
- `RelationSensor`：人物/群组上下文 → `RelationPercept{...}`（接现有 people/groups）
- **门控铁律**：每个 percept 自带 `provenance + confidence`；综合评分低于阈值的不上报——诚实的"我不记得"，而不是把低质文本铺进上下文让 think 硬信。

检索评分（ACT-R 式，SSOT 见 C3）：
`score = w1·semantic_sim + w2·recency_decay(t) + w3·salience + w4·cue_match`，其中 `recency_decay` 用幂律（Ebbinghaus），权重 w1–w4 可配置、默认等权，调参需有 LongMemEval 式评测背书。

### 2.3 remember：consolidation 四决策（显式、可审计）

remember phase 不再是"写文件"，而是对每个候选记忆做一次**显式决策**（Mem0 的 ADD/UPDATE/DELETE/NOOP 升级为认知语义版）：

1. **encode**：salience 打分（新颖性 × 复用价值 × 用户确认度），低于阈值 → 丢弃（不编码）。这就是 Craik & Lockhart 的编码门控。
2. **link**：与现有记忆对账——新 claim 与旧 claim 冲突 → 旧 claim 填 `valid_to`（Zep 式失效不删除）+ `supersedes` 链；重复 → merge；无关 → ADD。
3. **decay**：定期 job 对低 salience + 长期未命中的 trace 做降级（episodic → 摘要 → 归档），不是删除，是**降权**（Jost 第二定律：旧记忆衰减慢，一次降一级）。
4. **schema**：sleep-time pass（Letta 式，独立离线 agent/任务）从 episodic 提取 semantic——"用户连续三周每周三问部署" → `SemanticClaim{用户每周三关注部署}`。这才是系统巩固的含义。

每次决策写一条 `ConsolidationRecord{decision, target_id, rationale}` 进审计日志——remember 的产出可审计，这是与"写文件"的本质区别。

### 2.4 与现有架构的对接

- **loop**：perceive 阶段新增 `MemorySensorRegistry`（传感器的一种）；remember phase 的语义升级为 §2.3，拓扑不变（C3 纪律：改拓扑才动 README）。
- **ADR-0260**：检索义务层不变；本 ADR 规定"检索回来的是什么"（typed percept），0260 规定"必须检索"——正交。
- **ADR-0261**：standing 文件是 SemanticClaim 的一种特化（confidence=1.0, sources=["standing"]），可复用类型。
- **todo-29**：A2（wire 预算）约束 sensor 上报的 token 量；A3（compaction）与 decay 互补（compaction 管上下文窗口，decay 管长期记忆）。

## 3. 契约

- **C1 — 类型铁律**：任何记忆进入 perceive 必须包装为 §2.1 三类之一，禁止裸文本注入。违规 = fail-closed（不上报，而不是降级为文本）。
- **C2 — 来源诚实**：每个 percept 必带 `provenance + confidence`；confidence < 0.3 的不上报，由 sensor 显式返回 `NoRecall`。
- **C3 — 评分 SSOT**：`score = w1·semantic_sim + w2·recency_decay + w3·salience + w4·cue_match`，`recency_decay(t) = t^(-d)`（d 默认 0.5，ACT-R base-level），权重配置化。
- **C4 — 双时间线**：SemanticClaim 必带 `valid_from/valid_to`；被取代填 `valid_to`，**不删除**（Zep）；历史查询用显式 `as_of` 参数。
- **C5 — 决策审计**：每次 remember 产出 `ConsolidationRecord`，四决策之一必须显式标记，rationale 非空。
- **C6 — 状态诚实**：本 ADR 为 Proposed；任一 C 落地前不得声称"LCA 记忆已对齐人类记忆模型"。

## 4. 验收标准

- A1：perceive 收到 `SemanticPercept` 时，能说出其 confidence 与 sources（测试断言字段存在且非空）。
- A2：构造冲突（用户改地址），旧 claim 的 `valid_to` 被填、新 claim 生效，旧 claim 可通过 `as_of` 查回（Zep 式 point-in-time）。
- A3：低 salience 候选在 encode 阶段被丢弃（测试：阈值以下无写入）。
- A4：检索评分测试——相同语义相似度下，更近/更高 salience 的排前面（ACT-R 式）。
- A5：`ConsolidationRecord` 审计日志非空且 decision 字段四选一。

## 5. 待拍板

1. 三类是否够用？要不要加 `PreferenceClaim`（用户偏好是 SemanticClaim 的特化还是独立类型）？
2. 评分权重 w1–w4 默认值与调参评测集（自建 LongMemEval 式？还是先等权跑起来）？
3. sleep-time consolidation 用独立 cron（如现有三路迭代）还是 remember phase 内联？
4. 与 0260 T4 的 `revision_of` 链合并还是并存（`supersedes` vs `revision_of` 二选一）？
5. 落地顺序：先 C1+C2（类型+来源，纯结构），再 C3（评分），最后 C4（双时间线）？还是一次到位？

## 6. Implementation Notes（2026-10-03 落地）

> 落地分支 `mem/adr-0277`（worktree 隔离开发），6 个 phase commits 已合入 main。测试 118 passed / 2 skipped（skip 的是真模型集成测试，门控 `LAYA_REAL_TEST=1`）。

### 落地 commits

- `81d511346` feat(memory): typed memory objects（P1）
- `4ed71892d` feat(memory): perceive sensor registry（P2）
- `900275427` feat(memory): retrieval scoring SSOT（P3）
- `a5d8a6be2` feat(memory): remember consolidation（P5）
- `2e9edb7bd` test(memory): bi-temporal acceptance A2（P6）
- `cfe6d1473` feat(memory): Laya System-1 backend（P4）

### 模块映射

| ADR 设计 | 落地位置 |
|---|---|
| §2.1 Typed 对象 | `lca/cognition/memory/types.py`：EpisodicTrace / SemanticClaim / ProceduralRule / ConsolidationRecord / ScoredCandidate（frozen dataclass，`__post_init__` 校验 0..1/非空；`SemanticClaim.is_valid_at(ts)`；权重常量 W_SEMANTIC=0.4 / W_SALIENCE=0.25 / W_RECENCY=0.2 / W_CUE=0.15） |
| §2.2 感知器注册表 | `lca/cognition/memory/sensors.py`：EpisodicSensor / SemanticSensor（含显式 `as_of` point-in-time）/ RelationSensor / MemorySensorRegistry（MIN_CONFIDENCE=0.3 门控 + max_percepts token 预算）/ NoRecall（fail-closed sentinel） |
| §2.2 检索评分 | `lca/cognition/memory/scoring.py`：MemoryScorer Protocol / WeightedScorer（ACT-R 确定性公式，默认主路径）/ LayaScorer / HybridScorer（确定性打底 + Laya 重排 top-k，低 confidence 回退）/ ShadowComparator（默认开，写 JSONL 对比日志） |
| §2.3 四决策 | `lca/cognition/memory/consolidation.py`：EncodeGate（salience<0.3 丢弃）/ LinkDecider（reconcile：冲突→旧 claim 填 valid_to + supersedes 链；重复→merge；无关→ADD）/ DecayPolicy（Ebbinghaus 降权，Jost：只降权不删除）/ RuleDecider / RuleSchemaExtractor（规则版占位）/ LayaDecider（noul/choice，低 confidence 回退规则版） |
| Laya 可插拔后端 | `lca/cognition/memory/laya_backend.py`：LayaScoreEngine（延迟导入、温度校准默认 1.5、中文走 multilingual Router；不可用时 fail-closed） |

### 契约覆盖（诚实）

- C1 类型铁律 ✅：percept 必为三类之一；registry 不上报裸文本。
- C2 来源诚实 ✅：confidence<0.3 的 sensor 显式返回 NoRecall，不降级为文本。
- C3 评分 SSOT ✅：`score = 0.4·semantic_sim + 0.25·salience + 0.2·recency_decay + 0.15·cue_match`，`recency_decay = (1+age_hours)^(-0.5)`。权重为初值，调参需评测背书。
- C4 双时间线 ✅：valid_from/valid_to + supersedes；as_of point-in-time 查询；失效不删除。
- C5 决策审计 ✅：ConsolidationRecord{decision, target_id, rationale}，decision 四选一、rationale 非空。
- C6 状态诚实：仍有效——未做 LongMemEval 式评测前，不声称"LCA 记忆已对齐人类记忆模型"。

### 验收 A1–A5

- A1 ✅ test_0277_sensors.py：SemanticPercept 断言 confidence/sources 存在且非空。
- A2 ✅ test_0277_bitemporal.py：改地址冲突 → 旧 claim valid_to 被填、新 claim 生效且 supersedes 指向上游、as_of 查回历史。
- A3 ✅ test_0277_consolidation.py：salience<0.3 在 encode 阶段被丢弃。
- A4 ✅ test_0277_scoring.py：相同 semantic_sim 下更新/更高 salience 的排前面。
- A5 ✅ test_0277_consolidation.py：每次决策 ConsolidationRecord 非空、decision 四选一。

### 待拍板 5 项裁决（2026-10-03，已定，执行完毕）

1. PreferenceClaim 不独立，仍 3 类型（以后可插）。
2. 权重初值 semantic 0.4 / salience 0.25 / recency 0.2 / cue_match 0.15。
3. sleep-time 落在现有 cron/hook 的 remember 离线任务（RuleSchemaExtractor 为规则版占位）。
4. 失效关系用 supersedes（Zep 非丢失式）。
5. 落地顺序 P1→P6（本节即执行记录）。

### Laya 集成状态

- checkpoint：`convaiinnovations/laya-typed-decisions`，已下载至 `/home/lichao/.cache/laya/checkpoints/`（repo 外持久目录；snapshot `1a793eb5`）。
- 真模型验证：2026-10-03 在 252（L20）实测通过——engine 可用（load_error=None）；中文 query「用户住在哪里？」3 候选打分 label=2/1/2（校准后 confidence 0.24–0.33，保守）；noul decide 返回 decision='no'（confidence 0.50）。System-1 速度符合预期。
- 约束遵守：打分必须用 typed-decisions checkpoint（base 在 typed-decisions 上低于多数类基线 0.36 vs 0.46）；confidence 温度校准（默认 temperature=1.5，应对出厂 over-confident）。
- shadow 模式：**默认开**。ShadowComparator 同时跑 WeightedScorer + LayaScorer，写 `./shadow_scores.jsonl`；shadow 数据证明 Laya 更优之前，Laya 永不做主 scorer。
- 隔离纪律：Laya 绝不碰 typed 对象定义、传感器注册表结构、双时间线 schema、reconcile 记账逻辑——确定性骨架零模型方差。

### 已知偏差 / 后续（backlog）

- cue 匹配是双向子串启发式 v1："地址"这类主题词命中不了"住在……"文本（P6 测试用 `cues=["地址","住在"]` 绕过，docstring 已注明）。sensor 侧以后要升级主题词匹配。
- LinkDecider 冲突检测是"主题词重叠 + 文本不同"启发式 v1，docstring 已诚实标注。
- RuleSchemaExtractor 是规则版占位（7 天窗口 ≥3 次相似 what → 提炼 claim，confidence=0.6），LLM 版以后插。
- 权重调参需自建 LongMemEval 式评测集（C6 约束）；shadow 日志攒够数据后才能裁决 Laya 是否转正。
