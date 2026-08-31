# 13 群 ↔ 8/9 群映射权威表（ADR-0110 D7）

## 用途

v3 宪法 8/9 群（State / Perceive / Think / Gate / Act / Memory / Collaboration / Journal / Composition）
与 ADR-0069 工程外化 13 群的映射表。**这是仓库内对两套分类学并存的最权威单一来源**，
所有 `FunctionalGroup.V3_TO_0069_MAPPING` 字典读取者应在此表校对。

## 映射规则

| v3 群 | 等价 ADR-0069 群 | 备注 |
|---|---|---|
| State | G3_FACTS | 单一 |
| Perceive | G2_SPACETIME + G4_PERCEPTION | **唯一被一拆为二的群** |
| Think | G5_COGNITION | 单一 |
| Gate | G6_DECISION | 单一 |
| Act | G7_EXECUTION | 单一 |
| Memory | G3_FACTS | 单一 |
| Collaboration | G8_COLLAB | 单一 |
| Journal | G3_FACTS + G12_EVIDENCE | 一拆为二（事实流 + 评测） |
| Composition | G10_COMPOSITION | 单一 |

## 第一性原则

- **v3 9 群仍是宪法原语**：plugin 群检查（lca plugin check）不会强制填 0069 群
- **0069 13 群是工程外化分类学**：用于跨系统推理、PlanTemplate 命名、ADR 与文档
- **不是替代关系**：13 群是 v3 9 群的细颗粒工程投影；两个群不能并存时再新增第 14 群（必须经 ADR 批准）

## 新增第 14 群的护栏

任何新群必须：

1. 先证伪现有 13 群均不能表达该主问题
2. 写 ADR 提案（relates-to: ADR-0069 + 本文件）
3. 在 PR 落地之前只能塞进 `PluginContract.contribution` 段作为可选静态补充

## 实现

- `lca/contracts/atoms/functional_group/functional_group.py` 中 `V3_TO_0069_MAPPING` 字典
- `scripts/check_plugin_metadata.py` 输出 end-of-run 提示「13 群 ↔ 8/9 群映射见 docs/architecture/functional-group-mapping.md」
- 不变 enum / 不变 schema

## 历史与权威

- ADR-0069 §一 13 群分类学（源）
- ADR-0069 §六 PluginContract 9 段（与本表正交）
- v3 宪法 `docs/design/2026-08-19-cognitive-primitive-constitution-v3.md` §3.2（源）
- v3.1 宪法补丁 `docs/design/2026-08-21-cognitive-primitive-constitution-v3-1.md` §1.1（双源并入接受）
- ADR-0110 D7 收口（文档指针）
