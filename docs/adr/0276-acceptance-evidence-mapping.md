# ADR-0276：0255 §6 验收映射与证据诚实契约

## 状态

**Proposed — 2026-10-03**

> **一句话**：0255 §6 的 T1–T12 是"对齐 Muse"的判分表——本 ADR 把每条 T 的 owner ADR、测试锚点、证据等级写成 SSOT 映射；**缺席的 T 不许静默**，低等级证据不许冒充高等级。

## 0. 接任务前 7 问（精简自检）

1. 谁受益？夜战验收："架构优雅以真正测试通过为准"需要一把公开的尺子，T1–T12 就是。
2. 真实问题？符合性套件 `tests/runtime/test_adr0255_muse_runtime_conformance.py:1` docstring 宣称 `(T1–T12)`，实际只覆盖 10 条——**T7（工具路由）、T11（审批边界）全仓零用例**；且 T5/T6/T9/T10 是 section 渲染字串断言（L2 下限），与 0255 §6"可直接抄的测试用例"的行为语义有级差，但级差无人标注。
3. 删掉会坏什么？不坏——新契约；但"对齐"声称继续停留在"提示词里有这句话"的层面，且缺席项继续隐身。
4. 更简单方案？直接让 tests 轮补 T7/T11。否决：补之前先把"缺什么、什么等级"写下来，否则补完还是没人知道覆盖率。
5. 契约先行？是。
6. 与现有 ADR 冲突？无。0258/0260/0261/0257 各自的验收不变；本 ADR 是验收之上的**元验收**。
7. 状态诚实？Proposed。映射表是 2026-10-03 HEAD 快照，不是活文档——C4 定了维护纪律。

## 1. 实证

### 1.1 Muse 侧（对齐来源）

- **0255 §6**：12 条 T1–T12，"自研运行时声称'对齐 Muse'，必须通过以下 12 条"——这是对齐声称的**判分表**，不是建议清单。

### 1.2 LCA 侧（缺口实锤）

- **名实不符**：`tests/runtime/test_adr0255_muse_runtime_conformance.py`（307 行，`e060b5d89` 落盘，`c9bf6899a` 修订）模块 docstring 写"符合性验证套件 (T1–T12)"；实际用例覆盖 T1/T2/T3/T4/T5/T6/T8/T9/T10/T12 + 1 个 runtime_row/timestamp 用例。`grep -rn "test_t7\|test_t11" tests/` 零命中（2026-10-03 实证）——**T7、T11 缺席且无人标注**。
- **级差未标注**（本轮逐用例读断言）：
  - T5/T6/T9/T10：断言 `MemoryRetrievalSection.render` 输出含特定字串 / `_PERSONA_INJECTION_WARNING` 含特定字串——section 级装配断言（L2 下限），未到 0255 §6 行为语义（"首轮回答前必须发生检索调用"）。
  - T8：断言 `packaged_layout()` 9 文件 + `assemble_standing` snapshot 含注入标记（L2）；**未区分 0257 §7 的同机全量 vs peer 脱敏**——0255 §6 T8 的"与父相同的身份与记忆注入"在 peer 侧应为 `standing_redacted`，测试无此区分。
  - 加分现状：T2（upsert→跨 run reopen→query 带 source/timestamp，L2）、T3（`guard_reply` 真实拦截门，L2）、T4（`supersede` 替换链 `revision_of`，L2）、T12（standing 豁免，L2）。
- **0255 §6 T5 与 0260 的级差已在排队**：backlog 0260 T2 落地提案（prompt 装配级断言）正是 T5 从 L2（section 字串）升到 L2+（模板级）的路径——本 ADR 不重复立案，只引用。

## 2. 契约

### C1 — 映射表 SSOT（快照见附录，维护纪律见 C4）

每条 T 一行四列：owner ADR、测试锚点、证据等级（C2 定义）、状态（通过 / 契约钉住 / 缺席）。**缺席是合法状态，静默不是**——缺席行必须存在并写明"缺席"。

### C2 — 证据分级

- **L1 提示存在**：断言提示块/字串存在（如"提示词包含决策树"）。
- **L2 装配/单元行为**：断言装配产物或单元级真实行为（guard 拦截、回执门、替换链、snapshot 装配）。
- **L3 真实 run 轨迹**：carrier 真实链路 + 真实模型调用的轨迹证据（fake-model  stub 空转不算）。
- 声称"XX 对齐通过"必须注明等级；**L1 不许冒充 L3**。升级路径按 T 价值区别对待（待拍板 2）。

### C3 — 套件名实相符

测试套件的 docstring/文件名声称的覆盖范围必须与实际用例一一对应；缺席的 T 必须在模块 docstring 或映射表中显式标注"缺席：T7/T11（待补）"。**本轮不动 `tests/**`**——tests lane 补用例或改 docstring 时执行，arch 只提案。

### C4 — 维护纪律

arch 轮每轮抽查映射表（与 todo-28 的 C3 loop README 抽查同轮执行）；tests lane 落地新 T/升级等级时同步更新状态行。映射表活体落点待拍板 3。

## 3. 验收用例（本 ADR 自身的）

- **A1**：附录映射表 12 行齐全，每行 owner/锚点/等级/状态四列非空。
- **A2**：T7/T11 在映射表标注"缺席"（A2 不强求本轮改 `tests/**` 文件——那是 tests lane 的；本 ADR 的标注即满足"不静默"）。
- **A3**：T8 行注明"未覆盖同机/peer 区分（0257 §7）"。
- **A4**：证据等级 L1/L2/L3 在本 ADR §2（C2）有文字定义。

## 4. 待拍板

1. T7/T11 补用例的归属与排期：tests lane 下轮认领？T11 的审批语义涉及人机交互，验收形态（契约测试 vs 场景测试）需设计。
2. 证据等级晋级是否强制：L1→L2→L3 设时间表，还是按 T 价值区别对待（如 T5 的模板级 0260 T2 提案已在排队，T9 字串级可能长期够用）。
3. 映射表活体落点：本 ADR 附录快照 + backlog 跟踪，还是 `docs/notes/` 下 dated 审计笔记（如 P2 #7 插件清单先例）。
4. T8 的同机/peer 区分是否值得一个独立验收（0257 §7 决策的测试落点）。

## 5. 实证来源

- ADR-0255 §6（T1–T12 原文）、§7（实施映射）
- `tests/runtime/test_adr0255_muse_runtime_conformance.py`（307 行；`e060b5d89` 落盘；`c9bf6899a` 修订"寒嗄"typo+对齐 0255 措辞）
- ADR-0257 §7（peer 脱敏 `standing_redacted` vs 同机全量——李超 `132f381a8` 裁决）
- ADR-0258（T12 owner）、ADR-0260（T2/T3/T4/T5/T6 owner；T2 提案 backlog）、ADR-0261（T1/T9 owner）、ADR-0253/0266（T9/T10 owner）、ADR-0256（T11 owner 候选：审批面）
- 0255 §6 T7 全仓零用例实证：`grep -rn "test_t7\|test_t11" tests/`（2026-10-03）

## 附录：映射表（2026-10-03 HEAD 快照）

| T | 0255 要求（一句话） | owner ADR | 测试锚点 | 等级 | 状态 |
|---|---|---|---|---|---|
| T1 | 自我认知：答出 soul/identity 真实内容 | 0261 | `test_adr0255_muse_runtime_conformance.py::test_t1_self_cognition_grounded_in_real_physical_files` | L2 | 通过 |
| T2 | 跨 run 记忆：引用 MEMORY.md 原文+出处 | 0258/0260 | `...::test_t2_cross_run_memory_recall_with_provenance`（upsert→reopen→query） | L2 | 通过 |
| T3 | 写盘回执先于"已记下" | 0260 | `...::test_t3_write_receipt_before_acknowledgement`（`guard_reply` 真实拦截） | L2 | 通过 |
| T4 | 冲突原地修正，不双写 | 0260/0247 | `...::test_t4_conflict_in_place_supersede_preserves_provenance`（`revision_of` 链） | L2 | 通过 |
| T5 | 强制检索：首轮回答前必检索 | 0260 | `...::test_t5_mandatory_search_decision_tree_in_prompt`（section 字串断言） | L2（下限） | 通过；升级提案 0260 T2（模板级）排队中 |
| T6 | 易变事实复验 | 0260 | `...::test_t6_volatile_fact_revalidation_constraint`（section 字串断言） | L2（下限） | 通过 |
| T7 | 工具路由：走真机/skill 实查 | 无 | 无（全仓零用例） | — | **缺席** |
| T8 | 子 agent 继承身份与记忆注入 | 0257 | `...::test_t8_subagent_transcript_and_standing_inheritance`（9 文件 snapshot） | L2 | 通过；**未覆盖同机/peer 区分（0257 §7）** |
| T9 | 注入抗性：拒绝写 SOUL | 0253/0261 | `...::test_t9_anti_injection_protects_soul_and_identity`（warning 字串断言） | L1 | 通过 |
| T10 | 凭证红线：不记原文 | 0253/0266 | `...::test_t10_credential_redline_in_memory_rules`（section 字串断言） | L1 | 通过 |
| T11 | 审批边界：等用户决定 | 0256（候选） | 无（全仓零用例） | — | **缺席** |
| T12 | 压缩不失忆 | 0258 | `...::test_t12_compaction_exempts_standing_files_preserves_identity` | L2 | 通过 |

---

## 6. 决策记录（2026-10-05）：T7/T11 补用例归属与排期

**裁决**（李超授权 Athena 按第一性原理拍板；对应 §4 待拍板第 1 项）：

1. **归属**：tests lane 认领。第一性原理：T7/T11 缺席的是用例，不是设计——
   0276 的初衷是消灭“宣称覆盖、实际缺席”，补用例是 tests lane 的本职；
   “只标注缺席不补”等于把债合法化，不取。
2. **T7（工具路由）**：契约测试，走真机/skill 实查（以 0255 §6 的行为语义为准，
   不止于字串断言）。
3. **T11（审批边界）**：先契约测试，后场景测试。第一性原理：审批的本质是
   “等用户决定”的状态机语义（暂停→待审批→决定→恢复/取消），状态流转可契约化，
   无需真人交互即可断言；审批决定本身可模拟注入。场景测试（真人机交互）排期另议。
4. **排期**：tests lane 下轮认领；T11 的验收形态若在落地中发现契约测试表达力不足，
   回到本 ADR 修订 §4，不静默降级。

§4 其余待拍板项（证据等级晋级、映射表活体落点、T8 同机/peer 区分）本次不裁决，
维持 Proposed 跟踪。
