# ADR-0277 四问深审（2026-10-03 09:09 iter-arch 轮）

> 对象：`docs/adr/0277-cognitive-memory-reconstruction.md`（Athena 直办交付，commit `b98bd81a6`，状态 Proposed — 2026-10-03）
> 方法：质量铁律 ADR 四问（contract 可测试？状态诚实？交叉引用有效？"待拍板"是否被 silently 当决策？）
> 实证基线：隔离 worktree @`52738ce78`（main 当时 HEAD）；只读核验，未改 0277 正文。

## Q1：contract 条目可测试吗？✅ 通过

- C1（类型铁律，fail-closed）：可测——断言裸文本注入被拒、percept 必为三类之一。
- C2（来源诚实，confidence < 0.3 → `NoRecall`）：可测——字段在场 + 阈值行为。
- C3（评分 SSOT：`score = w1·semantic_sim + w2·recency_decay + w3·salience + w4·cue_match`，`recency_decay(t) = t^(-d)`，d 默认 0.5）：可测——公式与权重配置化。
- C4（双时间线：`valid_from/valid_to` 必带，被取代填 `valid_to` 不删除，历史查询显式 `as_of`）：可测。
- C5（决策审计：`ConsolidationRecord{decision, target_id, rationale}`，四决策显式标记、rationale 非空）：可测。
- C6（状态诚实 meta 条款）：可测（状态行断言）。
- A1–A5 验收均为行为级，可测。✅

## Q2：状态诚实吗？✅ 通过

- 状态行 `**Proposed — 2026-10-03**`；§0 Q7 明说"未落地一行代码"；C6 禁止提前声称对齐。✅
- §1.3 四处实锤缺口逐项核验（本轮实证）：
  1. **无类型** ✅：`memory_search` 返回 `(doc_id, content, path)` 文本三元组（`lca/infrastructure/memory/contextfiles/domain/search.py:78-90`），think 侧无类型/置信度可用。
  2. **无衰减** ✅：`lca/infrastructure/memory/` 全树零 `decay` 命中。注：`MemoryRecord.valid_until_ms` + `is_expired()` 是**显式过期**（TTL），不是激活度衰减——与本 ADR 的 decay 互补，不重复，文档表述无误。
  3. **无评分** ✅，且文档表述**偏保守**：`relevance()`（`scoring.py:28`）是**词项重叠**（中文字符集/英文词集重叠 + 子串加成），连语义相似度都不是；recency/salience/confidence 三维度确实全无。
  4. **无 reconcile** ✅：remember = `lca/nodes/remember/{admit,write,fold}` 三节点，无 ADD/UPDATE/DELETE/NOOP 裁决步骤。
- "remember phase 已存在" ✅（三节点目录实证）；"0260 是义务层、本 ADR 是类型层，正交" ✅（0260 全文无类型定义）。

## Q3：交叉引用有效吗？⚠️ 2 处实锤错误 + 2 处备注

1. **`revision_of` 引用错误**（§2.1 `supersedes` 字段注释 + §5 待拍板④）：ADR-0260 T4 的实际术语是 **`supersession_chain`**（0260:92："旧条目被原地修正且 `supersession_chain` 含新旧两条"），`revision_of` 在 0260 全文零命中。
   - 拟议修正：两处 `revision_of` → `supersession_chain`；待拍板④改写为："`supersedes`（本 ADR 新字段）与 `supersession_chain`（0260 T4 既有链）合并还是并存？"
2. **传感器注册表归因错误**（§2.2）："对齐 loop 的'传感器注册表'思想，ADR-0254"——ADR-0254《顶级商用级 Assistant 全景上下文文件体系与持续记忆运行架构》全文零 `sensor` 命中。真正的先例是 **ADR-0274**（wire 预算：perceive 传感器优先级裁剪）+ ADR-0262 的 `SkillCatalogSensor`。
   - 拟议修正：归因改为 ADR-0274（+ 0262 SkillCatalogSensor 为实例）。
3. 备注（非错误）：§1.1 "L1 日志 ≈ 情景，L2 MEMORY.md ≈ 语义"——LCA 无 L1/L2 术语（docs 全文无命中）；`≈` 已标明是类比，可接受，建议修订时加注"类比标签，非 LCA 术语"。
4. 备注（未提及但相关）：ADR-0247 的 `MemoryRecord`（`lca/contracts/models/core/conversation/memory.py:28`，dedupe/supersede/provenance/lifecycle 领域语义，按 0254 v2 继续有效）——三类 typed 对象与其是替代/包装/并行？文档未回答（见 Q4 新增待拍板⑦）。

## Q4："待拍板"有没有被 silently 当已决策？✅ 5 项均真实开放；另补 2 项缺口

- ①（PreferenceClaim 是否独立类型）②（w1–w4 权重与评测集）③（sleep-time 载体）④（命名收敛，见 Q3-1 修正）⑤（落地顺序）：均无 silent 决策。✅
- 注：C2 的 `0.3` 阈值无 rationale（为何是 0.3？），建议补一句依据或并入待拍板②一并定。
- **新增待拍板⑥（存储 vs 投影，P1）**：typed 对象是**运行时投影**（与 0254 v2 决策 A 一致：MEMORY.md + daily 为记录真值）还是**新的存储真值**（与 0254 v2 冲突）？文档未声明落点。§0 Q6 "与现有 ADR 冲突？无" 在此点上略显乐观——冲突与否取决于这个未声明的选择。
- **新增待拍板⑦（与 0247 的关系，P1）**：`EpisodicTrace`/`SemanticClaim`/`ProceduralRule` vs 0247 `MemoryRecord`——替代、包装、还是并行？`supersedes` 与 0247 的 supersede 语义是否为同一？
- §2.4 "standing 文件是 `SemanticClaim` 的一种特化（confidence=1.0, sources=['standing']）"是建模断言，未进待拍板——建议并入⑥/⑦一并裁决，或明确标注为建模假设。

## 结论

- 四问结果：Q1 ✅ / Q2 ✅ / Q3 ⚠️（2 处实锤引用错误，附精确到行号的修正提案）/ Q4 ✅（5 项开放真实，另补 2 项 P1 待拍板）。
- 本轮**不动 0277 正文**（Athena 直办交付，修正以本提案形式交作者/李超定夺；arch 轮只提案、不擅自决定架构方向）。
- 不新增 ADR（0255 实质机制章节已全线收官；0277 是新方向，由作者推进）。
