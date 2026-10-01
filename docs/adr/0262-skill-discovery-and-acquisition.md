# ADR-0262 — Skill 发现与沉淀契约：先查后动手，先查后断言，晋升三段门

## 状态

**Proposed — 2026-10-02**

> **一句话**：ADR-0255 §4.9（技能发现机制）的 LCA 落地提案。LCA 已有 search/import/activate/read 工具链、skill 目录 sensor、candidate-only 自学习插件，但缺三条契约：① 提示级的"先查后动手"铁律（`skills.py` 只有 activated_skills 展示块）；② 否定断言的证据纪律（"做不到/没接通"必须先有检索记录，检索失败 ≠ 检索无结果）；③ 沉淀晋升路径设计（auto_acquire 留白的 candidate → 批准 → 安装三段门）。检索语义只有关键词，无 BM25/regex 双模式。

**Extends**：
- [ADR-0255](0255-muse-production-runtime-full-reference.md)（Muse 生产运行时全量参考）：本 ADR 是 0255 §4.9（技能发现机制）的 LCA 落地提案——0255 的四条（动手前 `muse.skill_search` 先查；命中读 SKILL.md 照做；无命中自建；可复用流程用 skill-creator 沉淀；先查后断言）定义了目标；本 ADR 负责"升契约 + 补缺口"；
- [ADR-0256](0256-tool-namespace-taxonomy.md)（工具 namespace 分类）：skill 域工具已 namespace 化（`SkillSearchTool.namespace="skill"`），C1 的"先查"义务落在 `skill` 域可见性之内——defer 目录也应向模型展示检索入口；
- [ADR-0260](0260-forced-retrieval-and-write-before-claim.md)（强制检索与写盘铁律）：skill 能力声明是**易变事实**（市场上下架、本地安装状态随时间变）→ T6 复验精神适用；C2 否定证据纪律与"防幻觉终端闸门"同源。

**实证来源**：2026-10-02 iter-arch 轮对当前实现的实证审计——
- 已落地一（工具链齐备）：`lca/infrastructure/tools/skills/` 下有 search / import / activate / read / manifest 子包；`SkillSearchTool`（search/tool.py）`namespace="skill"`、`is_idempotent`，描述写"优先查 LobeHub Market（需鉴权），否则搜本机已安装；找到后用 import_skill 安装，再 activate_skill 加载指南"；
- 已落地二（降级搜索）：`_search_with_degradation` + `_DEGRADED_PREFIX="（已放宽搜索条件）"`，关键词无命中自动放宽条件——但检索语义**只有关键词**，全仓无 BM25/regex；
- 已落地三（目录投影）：`SkillCatalogSensor`（lca/cognition/sensors/skill_catalog.py）把已安装 skill 列表投进 manifest，索引变化时发 `skill.catalog.published.v1` 元事件；
- 已落地四（自学习封口）：`lca/plugins/skill/auto_acquire.py`——candidate-only，注释明写 *"deliberately does not write to the installed skill store"*，*"a separately evaluated and approved promotion path must materialize any candidate"*——晋升路径明确留白；
- 缺口一（**提示级铁律缺席**）：`lca/plugins/prompts/sections/skills.py` 只有 `ActivatedSkillsSection`（渲染已激活 skill），**零**"动手前先查 skill / 先查后断言"义务块——对比 ADR-0260 的 `_RETRIEVAL_DUTY` 模式，skill 域无对应物；
- 缺口二（**无命中只有"自己编"**）：无命中 fallback 文案 `_SANDBOX_FALLBACK="无匹配 skill。建议用 execute_code 直接编码实现，或尝试更简短的关键词重新搜索。"`——只有自建出口，**没有**"沉淀为可复用 skill"的引导；
- 缺口三（**否定纪律缺席**）：全仓无"断言做不到前先检索"的约束；"检索失败"（工具错 / 市场鉴权失败 / 网络不可用）与"检索无结果"在证据上不区分——fail-open 风险：一次市场鉴权失败可能被说成"没有这个 skill"。

---

## 0. 接任务前 7 问

1. **问题是什么？** ① 先查后动手只有工具、没有义务；② 否定断言（"做不到/没接通/没有这个 skill"）无证据纪律；③ 沉淀晋升路径未设计（auto_acquire 留白）；④ 检索语义单一（仅关键词，无 BM25/regex）。
2. **受影响的事实或契约是什么？** skill 域的工具使用纪律、否定回答的证据链、operational skill store 的写入权限、检索语义。
3. **唯一真值在哪里？** skill 是否存在 = `search_skill` 检索结果 + 本地 store 状态，不是模型的"记得/觉得"。能力声明是易变事实，行动前复验。
4. **改变哪个边界？** 把"查 skill"从"自觉"变成 run 级义务；把 skill store 的写入权从"插件可为"变成"批准才可为"；把检索失败与检索无结果从"一种说法"变成"两种证据"。
5. **现有 Protocol / ADR 能否表达？** 不能。0260 管**记忆**检索，不管 skill 检索；0256 管 namespace 可见性（能力层），不管使用义务（义务层）；auto_acquire 的封口是实现级自觉，未升契约。
6. **失败、重试、恢复和幂等语义是什么？** 检索失败 → 降级（放宽条件 → 本地 store）→ 仍失败 → 如实说"检索不可用，无法确认"，**不许**断言"无 skill"；candidate 产出 → 只读草稿，不自动晋升；批准前安装/激活 candidate = 破契约。
7. **如何验证？** §2 验收用例 T1–T4。

---

## 1. 契约

### C1 — 先查后动手（新，提示级可落地）

- 进入需要某产品/服务能力的具体任务前，**必须**先调 `search_skill`；检索到 → 读 SKILL.md/激活指南照做（import → activate），不许绕开 skill 自造轮子；
- 无命中 → 按 0255 §4.9 走自建（execute_code / 浏览器 / 其它工具），且**可复用的流程应产出 skill candidate**（见 C3）——自建不是终点，沉淀才是；
- skill 域工具已按 0256 namespace 化，"先查"义务落在 `skill` 域可见性之内——defer 目录首 turn 也应向模型展示检索入口（与 0256 的 DeferPolicy 8 域闭环一致）。

### C2 — 先查后断言（新，否定证据纪律）

- 回复"做不到 / 没接通 / 没有这个 skill"前，**必须**有 `search_skill` 检索记录——无检索记录的否定 = 幻觉（类比 0260 T5"蒙对不算"的反面："蒙错"更不算）；
- **检索失败 ≠ 检索无结果**：工具错误 / 市场鉴权失败 / 网络不可用时，只许说"检索不可用，无法确认"，不许说"没有这个 skill"；
- skill 能力声明是易变事实（市场上下架、本地安装状态变）：行动前复验，适用 0260 T6 精神；本地 store 状态以 `SkillCatalogSensor` 的 manifest 投影为准，不以模型记忆为准。

### C3 — 沉淀晋升三段门（新，设计提案）

- **candidate**（auto_acquire 产出）：不可变草稿，带 task_ref / procedure / evidence_refs / confidence，只读，**不进 store**；
- **promotion**（批准）：批准主体默认**用户本人**（或用户明确授权的评估策略）；批准前 candidate 不得被安装 / 激活 / 检索到；
- **install**（安装）：批准后进 `SkillPackageStore`，走现有 import / activate 路径；
- auto_acquire 的"candidate-only 不写 store"是 **fail-closed 语义，升为不变量**：任何插件 / 模型行为不得静默学 skill 进 store；删封口 = 破契约。

### C4 — 检索语义补齐（提案级）

- 补 **BM25 / regex 双模式**（对齐 Muse 的 `muse.skill_search`）：精确名用 regex，模糊意图用 BM25/关键词；
- 降级链显式化：精确 → 放宽（现有 `_search_with_degradation` 升契约）→ 本地 store → 如实声明检索边界；每一步的证据等级不同，回答时必须区分。

### C5 — 与现有机制的关系（不冲突声明）

- 与 0260：记忆检索管"过去的事实"，skill 检索管"现在的能力"——是 run 级义务的两个实例，不重复；
- 与 0256：C1 的"先查"是**义务层**，0256 的 namespace 可见性是**能力层**——义务要求查，能力决定查不查得到；
- 与 0253：市场鉴权凭证走现有凭证红线，不进 skill 内容、不进 candidate 草稿。

---

## 2. 验收用例

- **T1 先查**：给"查某商品现在有没有货"类领域任务 → 首 turn 工具调用序列含 `search_skill`，且发生在领域动作之前；无检索记录直接动手 = 不合格；
- **T2 否定纪律**：市场鉴权失败时问"有没有 X skill"→ 回答是"检索不可用，无法确认"而非"没有这个 skill"；要求回答附检索证据（query / 结果数 / 失败原因）；
- **T3 封口**：auto_acquire 产出 candidate 后，store 内容哈希不变、无新安装记录、无 manifest 变更事件；
- **T4 晋升**：批准后 candidate 可 install 并被 `search_skill` 检索到；未批准的 candidate 不可被检索/安装/激活。

---

## 3. 待拍板

① C1 落点：独立 skill 义务提示块（对标 0260 的 `_RETRIEVAL_DUTY`）vs 并入 tools 段；
② 检索语义：BM25/regex 的优先级与实现位置（tool 内 vs 独立 search 服务）；
③ promotion 批准主体：用户本人（默认 fail-closed）vs 可配置评估策略；
④ 无命中自建边界：execute_code 自建 vs 走浏览器/外部获取后沉淀——沉淀的证据门槛（对标 auto_acquire 的 min_confidence/min_evidence）。

---

## 4. 决策记录（2026-10-02，李超授权 Athena 按 muse 思想裁决）

1. **C1 落点：独立 skill 义务提示块**（对标 0260 `_RETRIEVAL_DUTY`，不并入 tools 段）。理由：skill 检索是 run 级义务（C5 已定性为与记忆检索并列的义务实例），义务块显式化是生产 Muse 的实证模式；并入 tools 段会被能力描述稀释。
2. **检索语义：tool 内渐进增强（关键词 → BM25 → regex 降级链），不建独立 search 服务**。理由：现有 `_search_with_degradation` 已是降级链雏形，就地增强改动最小；独立服务是 YAGNI——今天连 BM25 都没有。
3. **promotion 批准主体：默认用户本人；评估策略接口预留但不实现**。理由：安装 skill 改变 agent 能力 ≈ 不可逆操作 → fail-closed 默认用户批；可配置策略是未来的扩展点，不是今天的决策。
4. **无命中自建边界：先自建解决当下任务（C1），可复用流程产出 candidate 走 C3 三段门；证据门槛复用 auto_acquire 的 min_confidence/min_evidence**。理由：不发明第二套门槛（DRY）；自建是手段、沉淀是目的（C1 已定）。
