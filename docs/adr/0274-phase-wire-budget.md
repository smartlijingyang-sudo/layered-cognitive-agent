# ADR-0274：Phase Wire 预算契约（perceive/think 的 token 预算声明与降级）

## 状态

**Proposed — 2026-10-03**

> **一句话**：每个 phase 声明 wire token 预算（**配置层**声明，不进认知原语）；prompt 装配后、wire 投射前由 loop 机制层强制执行；超预算时 perceive 按传感器优先级裁剪、think 触发工具域 defer（ADR-0256 思想）；降级必须留痕。

## 0. 接任务前 7 问（精简自检）

1. 谁受益？长上下文 run：防止"传感器全开 + 历史全量"把 wire 撑爆，延迟与费用双降。
2. 真实问题？用量**事后可知、事前无约束**：`TokenUsage` 每次 LLM 调用后才返回，装配侧没有任何预算声明。
3. 删掉会坏什么？不坏——新机制；但删掉后"超预算"只能事后在账单里发现。
4. 更简单方案？全局硬截断（如超 N token 直接报错）。否决：粗暴截断杀死合法长任务；分 phase 预算+降级更精细。
5. 契约先行？是。
6. 与现有 ADR 冲突？无。0256 的 DeferPolicy 是"工具域延迟加载"，本 ADR 是"预算超限的触发器"，互补。
7. 状态诚实？Proposed；估算器精度是已知弱项（见 C4 与待拍板①）。

## 1. 实证

### 1.1 Muse 侧（对齐来源）

- **ADR-0256 DeferPolicy**：8 域工具延迟加载，本质是"wire 预算思想"——默认不加载、按需加载。0256 解决的是**工具 schema**的预算，本 ADR 把同一思想推广到 **phase 级 prompt 装配**。
- **先例**：`docs/plans/2026-10-02-muse-connector-architecture-design.md` §4.4 `ConnectedServicesSection` 固定 **100-token 预算**上限——段级预算声明在 LCA 生态已有先例。
- **本运行时**：defer 首 turn 只露工具目录（不注入全量 schema），是"预算约束装配"的生产实证。

### 1.2 LCA 侧（缺口实锤）

- `lca/infrastructure/tool_defer/policy.py:41` `DeferPolicy`：8 域声明齐备，但**只有工具域**有预算语义；phase 级 prompt 装配无预算声明。
- `lca/nodes/think/llm/invoke.py:121`：`response.usage or TokenUsage()`——用量是**事后**返回；全仓 grep `tiktoken|estimate_tokens|count_tokens`，`lca/` 内**零**事前估算（仅 `infrastructure/memory/retrieval/scoring.py` 有检索打分用的 token 逻辑，与装配预算无关）。
- 时间预算有先例：`invoke.py:133` `_wall_clock_exhausted`（`state.budget` + `remaining_wall_clock_seconds`）——"预算耗尽→降级"是已有模式，但只覆盖 wall-clock，**不覆盖 wire tokens**。
- perceive 传感器无预算门：ADR-0262 实证 `SkillCatalogSensor` 投 manifest、全量投递，无优先级裁剪契约。

## 2. 契约

### C1 — 预算声明进配置，认知原语不感知预算

`phase_wire_budget: {perceive: <tokens>, think: <tokens>, ...}` 声明在 run profile / bundle 配置（`bundles/` 或等价配置层）。perceive/think/reflect 等认知原语代码**不读**预算——预算是机制层概念，不进认知语义。

### C2 — 强制点：装配后、wire 投射前

在 ADR-0265 的装配链路末端（模板装配完成 → `_history.py` wire 投影之前），由 loop 机制层做预算校验。校验失败不抛错（除非配置显式要求 fail-closed），走 C3 降级。

### C3 — 超预算降级策略（分 phase，可配置）

- **perceive**：按传感器优先级裁剪投递（传感器需声明 `priority`；低优先级先被裁；裁剪清单进 journal）。
- **think**：触发工具域 defer（复用 DeferPolicy：超预算部分工具域/段延迟加载，首 turn 只露目录）。
- **降级留痕**：每次降级发事件 + journal 记录"裁了什么、为什么"，**不得静默**。

### C4 — 估算器只用于预算比较，不用于计费

token 估算用确定性近似（`chars/4` 起步；tiktoken 可用时用精确分词）。估算偏差方向与量级必须在实现文档中声明。**估算值永不用于费用结算**，只做预算比较。

## 3. 验收用例

- **T1（预算生效）**：配置 `perceive` 预算为极小值，跑 sensor 全开的 run，断言低优先级传感器被裁剪且 journal 有裁剪记录。
- **T2（think 降级）**：配置 `think` 预算极小，断言工具域走 defer（首 turn 只露目录），且后续 `tool_search` 可恢复加载。
- **T3（估算器诚实）**：估算器对 100 段样本的估计值与真实分词对比，偏差分布落在文档声明范围内。

## 4. 待拍板

1. 估算器精度要求：`chars/4` 近似是否足够，还是必须 tiktoken 精确分词（依赖体积 vs 精度）。
2. think 超预算时：优先 defer 工具域，还是优先裁剪对话历史（两者都合理，顺序需定）。
3. 预算违反语义：fail-closed 阻断（精确可控）vs fail-open 降级+告警（本 ADR 倾向后者，需拍板）。

## 5. 实证来源

- `lca/infrastructure/tool_defer/policy.py:41`（DeferPolicy）
- `lca/nodes/think/llm/invoke.py:121,133`（事后用量 / wall-clock 预算先例）
- ADR-0256（工具域延迟加载）、ADR-0262（SkillCatalogSensor 实证）、ADR-0265（装配链路）
- `docs/plans/2026-10-02-muse-connector-architecture-design.md` §4.4（100-token 段预算先例）
