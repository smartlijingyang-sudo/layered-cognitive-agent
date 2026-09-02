# ADR-0165: Event Spine 统一执行日志（历史入口）

- 状态: Accepted（historical stub）
- 日期: 2026-09-01
- 作者: coding-agent
- 扩展: [ADR-0165-execution-point-enforcement](0165-execution-point-enforcement.md)
- **SSOT / 物化 / Model-visible 以 [ADR-0167](0167-spine-ssot-and-step-materialization.md) 为准**

## 一句话

将框架执行观测从业务方零散埋点收束为 **EventSpine**：白名单 execution points、append-only `events.jsonl`、deriver 只投影。

## 说明

本文件曾在引用链中存在、正文一度缺失。为修复断链而恢复为 **短 stub**。完整执行点强制、自动字段、source-level trace 与 18-plugin 装配见 **ADR-0165-execution-point-enforcement**；耐久真值与 journal 物化、轨迹文件组织见 **ADR-0167**。

## 核心意图（保留）

1. 执行可见 ⟺ 入 spine。
2. Deriver / OTel / console 不得成为第二真值流。
3. start → progress → end 链与 outcome 枚举由后续 ADR 强化。

## 参考

- Spec: `docs/superpowers/specs/2026-09-01-spine-execution-points-design.md`
- [ADR-0165-execution-point-enforcement](0165-execution-point-enforcement.md)
- [ADR-0167](0167-spine-ssot-and-step-materialization.md)
