# ADR-0275：窗口压力下的 Phase 降级契约（compaction 思想进 loop 机制层）

## 状态

**Proposed — 2026-10-03**

> **一句话**：窗口压力（context window 使用率）的探测与 phase 降级决策收敛到 loop control 贡献契约的新 slot；压力大时 reflect 降级为 ADR-0246 快速路径、remember 批量异步；**各 phase 实现不感知压力**，降级由机制层 verdict 驱动。

## 0. 接任务前 7 问（精简自检）

1. 谁受益？长 run 的稳定性：窗口见底时不是硬失败，而是有纪律地降级。
2. 真实问题？压力信号**各 phase 各自为战**：wall-clock 有 `_wall_clock_exhausted`，window 压力无统一信号源、无声明式降级策略。
3. 删掉会坏什么？不坏——新机制；但窗口耗尽时的行为仍是各相机的"自生自灭"。
4. 更简单方案？全局统一截断。否决：同 0274，粗暴截断杀死合法长任务；分级降级保留核心能力。
5. 契约先行？是。
6. 与现有 ADR 冲突？无。ADR-0258（compaction 豁免与重注）是**记忆层**的压缩机制；本 ADR 是**执行层**的压力降级，互补不重叠。
7. 状态诚实？Proposed。**纠正 backlog 旧误记**：`lca/loop/control/` 并非"只有 README 的空目录"——它已有 ADR-0194/0074 的 control contribution 契约；本 ADR 落点是**新增降级 slot**，不是"长出第一个模块"。

## 1. 实证

### 1.1 Muse 侧（对齐来源）

- **0255 §4.5 compaction**（已由 ADR-0258 落地：standing 豁免、摘要带血统、刷新 fail-closed）：Muse 把"窗口压力"当作一等机制处理。本 ADR 把同一思想从**记忆层**延伸到**执行层**——压力大时不是只压缩记忆，而是**降级 phase 行为**。
- **Muse DeferPolicy 思想**（0256）：超限时延迟加载而非硬失败——降级而非阻断，与本 ADR 的分级降级同构。

### 1.2 LCA 侧（缺口实锤）

- **control 契约已存在**（纠正旧误记）：`lca/loop/control/README.md` 定义 declarative control contribution 契约——slots `control.think.guard` / `control.act.chain` / `control.stop.policy`，roles PREPARE / TRANSFORM / GOVERN / OBSERVE / FINALIZE（ADR-0194 §2.1、ADR-0074）。**降级是新 slot，不是新目录**。
- **降级能力已有、策略缺失**：ADR-0246 reflect 快速路径（零 LLM）已实现（todo-28 C1 正在统计其覆盖率）；`lca/nodes/think/llm/invoke.py:133` `_wall_clock_exhausted` 是"预算耗尽→降级"的时间维度先例；但**窗口压力维度**无信号源、无策略声明——各 phase 对窗口见底无统一响应。
- **与 0258 的边界**：0258 管"记忆如何被压缩"（压缩什么、血统、回退链）；本 ADR 管"压力下 phase 如何降级"（reflect 降级、remember 异步化）。两份契约正交。

## 2. 契约

### C1 — 压力信号 SSOT：`WindowPressure`，phase 只读不写

`WindowPressure{window_used_ratio, remaining_budget_tokens, estimated_total}` 由**机制层**在每 phase visit 后更新（输入：`TokenUsage` 累计 + 0274 的估算器）。各 phase 实现**只读**该信号，不得自行计算、不得写入。

### C2 — 降级策略声明式，进配置不进代码

`degradation_policy` 声明在 bundle/profile 配置，形如：
`{reflect: {high: fast_path}, remember: {high: batch_async}, perceive: {critical: minimal_sensors}}`。
阈值等级（`high`/`critical` 的比值）由配置定义，phase 代码无阈值硬编码。

### C3 — 落点：control 贡献契约的新 slot，复用现有机制

新增 slot `control.degrade.policy`（建议 role：TRANSFORM，在 executor 后、govern 前给出降级 verdict；或 GOVERN，终端降级决策——待拍板）。phase 实现**零改动**：降级由 control verdict 驱动 executor 切换（如 reflect 切快速路径），不污染各 phase。

### C4 — 降级可观测，永不静默

每次降级触发必须发事件 + journal 留痕（"压力值 X 触发 reflect→fast_path"）。降级是**可审计**的运行时决策，不是暗门。

## 3. 验收用例

- **T1（信号 SSOT）**：长 run 中每 phase visit 后 `WindowPressure` 单调更新；任一 phase 内 grep 不到自行计算 window 压力的代码路径。
- **T2（降级生效）**：配置 `reflect.high=fast_path`，构造高压力 run，断言 reflect 走了零 LLM 快速路径且 journal 有降级记录。
- **T3（不污染）**：diff 审查——降级逻辑只出现在 control slot 插件与配置，phase 实现文件零改动。

## 4. 待拍板

1. 压力阈值：`high`/`critical` 的 `window_used_ratio` 比值（如 0.7/0.9，需拍板）。
2. `remember` 批量异步的落盘一致性：batch 窗口多大、crash 时丢多少可接受。
3. `WindowPressure` 与 `_wall_clock_exhausted` 的时间预算：合并为统一 `RunBudget` 还是并存（本 ADR 倾向并存：时间与窗口是正交维度，需拍板）。

## 5. 实证来源

- `lca/loop/control/README.md`（control contribution 契约：slots + roles）
- `lca/nodes/think/llm/invoke.py:133`（wall-clock 降级先例）
- ADR-0194 §2.1、ADR-0074（control 契约）、ADR-0246（reflect 快速路径）、ADR-0258（compaction 记忆层机制，与本 ADR 正交）
- ADR-0274（估算器复用）
