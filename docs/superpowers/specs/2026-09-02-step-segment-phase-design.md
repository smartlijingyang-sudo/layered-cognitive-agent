# Design: Step / Segment / Phase、Spine SSOT 与 Model-Visible 轨迹

- 日期: 2026-09-02
- 状态: Accepted
- 规范真源:
  - 词汇与硬化: [ADR-0166](../../adr/0166-step-segment-phase-and-spine-hardening.md)
  - **SSOT / 写路径 / 轨迹文件组织: [ADR-0167](../../adr/0167-spine-ssot-and-step-materialization.md)**

## 摘要

纠正 ADR-0164 实现把「每相位」当成 step 的漂移。对齐 DeepSeek Harness：

- **step** = 一次模型请求 + 其工具（样本 3）
- **segment** = `think` \| `act`（样本 5）
- **phase** = 闭集相位显式数组，含 perceive（样本 8）

**废除 `step_emitter` bridge。** `StepCoordinator` 唯一写入：spine `events.jsonl`（耐久 SSOT）+ 内存累加器物化 `journal.json`；**live ≡ replay**。

轨迹清晰额外要求（评审合入 ADR-0167）：

- 每步 `model_visible/step_NN/` 保存 system prompt、tool schemas、context-manifest（含 skills）、实际 `messages.json`
- journal / narrative 只持短标题 + digest + 链接，禁止截断 prompt 塞进 `objective`、禁止默认展开 token delta
- 不变量：**Model-visible ≡ logged**（对齐 DSH `request/header` + `deriveMessages`）

## 非目标

见 ADR-0166 §D7、ADR-0167 §D8（不含完整 trajectory-debug UI）。

## 验收

见 ADR-0166 §验收 + ADR-0167 §验收。实施按 ADR-0167 PR-0…PR-6。
