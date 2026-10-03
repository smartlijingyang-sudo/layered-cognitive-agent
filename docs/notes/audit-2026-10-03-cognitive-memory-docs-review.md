# 深审：认知记忆设计规范 + 实施计划 + ADR-0277 落地修订（2026-10-03 10:09 arch 轮）

对象：`docs/plans/2026-10-03-cognitive-memory-architecture-design.md`（9a60c9633+668ffb009）、
`docs/plans/2026-10-03-cognitive-memory-architecture-plan.md`（07f2a1570+668ffb009）、
`docs/adr/0277-cognitive-memory-reconstruction.md` 的 09:16 修订（c0579fe9a，Implementation Notes）。
方法：ADR 四问 + 逐条交叉引用实证（HEAD 7aec9ef8b）。agy 正文不动，只提案。

## Q1 contract 可测试吗 ✅

- 设计 §6 INV-MEM-01~06（轨 A 确定性不变量）全部可测：500 Token 预算、SSOT 单向、模态门控 0 候选、
  高敏感遮蔽 100%、哨兵注入 100%、双时间线取代链。
- 轨 B（LLM 行为评测，Dialogue Replay + LLM Judge，达标率 ≥90%）的评测 harness 尚未存在——
  tests lane 可认领（untracked 的 `docs/specs/cognitive-memory-evals-benchmark.md` 疑为 agy 的评测 WIP，本轮未读）。

## Q2 状态诚实？⚠️ 1 处内部矛盾实锤（0277 正文内）

- 设计文档头标 `Proposed (基于 ADR-0277 增量扩展) — 2026-10-03` ✅ 诚实。
- **实锤**：0277 正文 §0 Q7（:17）仍写"类型定义、评分公式、传感器注册表均为设计，**未落地一行代码**"，
  但同文档 §6 Implementation Notes（:132，c0579fe9a 09:16 加）写"6 个 phase commits 已合入 main，
  测试 118 passed / 2 skipped"——本轮实证 6 commits 全在 main 上（81d511346/4ed71892d/900275427/
  a5d8a6be2/2e9edb7bd/cfe6d1473），`consolidation.py/scoring.py/laya_backend.py` 全存在，
  EncodeGate/LinkDecider/DecayPolicy/`supersedes` 关键符号齐全。**agy 修订时加了落地节但忘了更新 Q7 自检行。**
  提案（P1，docs 侧 1 行修正）：Q7 改为"Proposed（设计）；Implementation Notes 已记录 6 个落地 commits；
  状态升级待李超拍板"。
- **上轮深审结论过期声明**：2026-10-03 09:09 arch 轮对 0277 的四实锤（无类型/无衰减/无评分/无 reconcile，
  "未落地一行代码"）是针对 09:09 时 main 的正确结论；09:16 后 0277 修订 + Task 1-4 落地使其过期。
  后续引用该深审结论时须以本轮为准。

## Q3 交叉引用 ⚠️ 1 处名实不符 + 1 处措辞有水

- ✅ 有效引用：C10 执行窄门（设计 §0.3）→ ADR-0232/0244/0247 均有定义；Laya（设计 §0.1
  "HybridScorer（ACT-R 加权 + Laya 重排）"）→ 0277 §2.3 映射表确有 LayaScorer/LayaDecider；
  `supersedes` 取代链术语 → 与 0277 T4 一致，**未继承 0277 旧版的 `revision_of` 错误**（上轮深审发现未在新 docs 重复）。
- **实锤（P1）**：设计 §5 标题与 Plan Goal 段均写"7 大维度 28 项"，实际内容为 **6 个维度、31 项**
 （一 1-5 / 二 6-11 / 三 12-16 / 四 17-22 / 五 23-28 / 六 29-31）。提案：改为"6 大维度 31 项"
  （或补齐缺失的一维，arch 只提案）。
- 措辞有水（P2）：设计 §0.1 "今日落地 main 的 **ADR-0277**（认知记忆重构基座）"——0277 状态行仍是
  Proposed（:5），"落地"的是 agy 的 6 个实现 commits。建议改为"基于 ADR-0277（Proposed；
  Implementation Notes 已记录 6 个落地 commits）"。

## Q4 待拍板 ⚠️ 2 项新增

- ⑥ 魔法数字缺 rationale（P2）：0.8 归档置信度、0.5 salience 门、500/100 Token 预算、GRAPH Top 15、
  entities 50 触发 GC、3000ms 熔断、max hops 2、0.8 复杂度、规则提取 confidence=0.6——
  全部无依据标注；Task 1-4 已按这些数字落地实现。同类标准见上轮"0277 C2 0.3 阈值"提案。
- ⑦ 0277 Proposed → Accepted/Implemented 状态迁移（P1）：Implementation Notes 的落地声明与
  Proposed 状态并存，按 0256 先例（李超 132f381a8 裁决升级）需李超拍板；arch 只建议不擅自决定。

## 观察（不动手）

- Task 5 进行中：main 工作树 modified（`guards/__init__.py`、`sections/memory.py`）+ untracked
 （`guards/firewall.py`、`tools/shield/`、`test_tact_and_pitfall_shield.py`）对应 Plan Task 5，
  属 agy WIP，零触碰。
