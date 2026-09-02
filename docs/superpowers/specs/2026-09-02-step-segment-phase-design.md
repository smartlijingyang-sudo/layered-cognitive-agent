# Design: Step / Segment / Phase 三层计数与 Spine 硬化

- 日期: 2026-09-02
- 状态: Accepted（决策正文见 ADR）
- 规范真源: [ADR-0166](../../adr/0166-step-segment-phase-and-spine-hardening.md)

## 摘要

纠正 ADR-0164 实现把「每相位」当成 step 的漂移。对齐 deepseek-harness：

- **step** = 一次模型请求 + 其工具（样本 3）
- **segment** = `think` \| `act`（样本 5；含思考，不叫 action）
- **phase** = 闭集相位显式数组，含 perceive（样本 8）

流式 reasoning/text delta 运行时 coalesce，落盘合并进 `thinking`（可选 `stream_stats` span）。并硬化 spine：CLI `journal.json` 路径、工具双层事件、phase_graph start、run-local seq、finally 语义、FileSink 路径。

## 非目标

见 ADR-0166 §D7。

## 验收

见 ADR-0166 §验收。实施计划在用户确认本 spec/ADR 后由 writing-plans 产出。
