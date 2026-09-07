# ADR-0196 — Convergence 控制面与 PromptSurface SSOT

## 状态

**Implemented (P1–P3)**（2026-09-07）。P1：Delivery Gate、PromptSurface、调试事件、Progress/Terminal Gate 语义修正。P2：`ConvergencePolicy` + `ConvergenceRuntime` 默认装配、`sensor.convergence-task` 写 manifest `convergence_task_class` hint、`turn.control.v1` 携带 `files_created` 供 gate fold。P3：Stop grace respond 经 `ConvergenceRuntime.evaluate_budget_and_emit` + `synthesize`。Guard 插件化见 ADR-0197。

## 0. 决策摘要

Agent run 失败常表现为「工具成功但用户无交付」。根因是系统将 **操作成功** 等同于 **进展**，且缺少 **交付谓词**；Prompt 层 `<tools>（无可用工具）</tools>` 与 FC schema / sandbox 说明书三套表征分裂。

本 ADR 引入：

1. **Convergence 控制面**（contracts）— `DeliveryEvidence`、`ConvergenceVerdict`、`TaskClass`
2. **PromptSurface** — tools XML 与 sandbox 块唯一渲染接缝
3. **gate.delivery-satisfied** — 交付已满足时禁止 producer 工具续跑
4. **Session 调试事件** — `convergence.evaluated.v1`、`delivery.evidence.v1`、`prompt.surface.rendered.v1`

Gate 仍 ⊂ Think；不增第七 phase。Stop grace path 留 P3。

## 1. 不变量

| ID | 不变量 |
|---|---|
| CV1 | `DeliveryEvidence` 由 manifest + control turns fold；Gate 只读，不 live workspace |
| CV2 | Prompt `<tools>` XML 与 FC `tools[]` 同源（`PromptSurface.render_tools_xml(tools)`） |
| CV3 | `TaskClass.INFORMATIVE_TEXT` 默认不注入完整 sandbox export bible |
| CV4 | 交付已满足时 producer 工具决策 MUST rewrite 为 RESPOND（`DeliverySatisfiedGate`） |
| CV5 | 收敛评估与 prompt 渲染 MUST 发 session catalog 事件（debug-run 可 grep） |

## 2. 扩展

- Profile 通过 ``convergence.policy.default`` 提供 ``ConvergencePolicy`` + ``ConvergenceRuntime``（P2 已落地）
- Perceive ``sensor.convergence-task`` 写 manifest ``convergence_task_class`` hint（P2 已落地）
- ``turn.control.v1`` 携带 ``files_created`` 供 gate fold（P2 已落地）
- Stop grace respond 经 ``ConvergenceRuntime.evaluate_budget_and_emit`` + ``synthesize``（P3 已落地）
- Profile 可选自定义 ``ConvergencePolicy`` 插件替换 default（注册 ``convergence_policy`` capability）
- Guard Stack 见 [ADR-0197](0197-guard-stack-hermes-dsh-convergence.md)（loop/act guard 插件化）

## 3. 关联

- [0194 认知 Loop 收敛](0194-cognitive-loop-architecture-convergence.md)
- [0051 Run workspace](0051-run-workspace-and-artifact-closure.md)
