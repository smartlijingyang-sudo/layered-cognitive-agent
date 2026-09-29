# 主动持久化 Agent：真实参考案例与业界范式对照

**日期：** 2026-09-29

**范围：** 以 2026-09-29 真实发生的一次"主动建议"全链路（数据库实测证据）为参考案例，对照 2024–2026 年主动式 Agent 的业界范式，推导 LCA 落地"主动持久化"能力的架构映射与最小可行方案。本记录归档本次调研，不替代当前 ADR 或协议；任何落地方案需走 ADR/Note 流程。

## 结论摘要

一次完整的主动建议链路可拆成两条流水线：**建议生成**（后台定时：目标 + 记忆 + 外部信号 → 打分 → 带 rationale 落库）与**主动触达**（被动展示 → 升级为打断 → 用户接受 → 执行）。参考案例证明了三个工程上最关键的细节：

1. **rationale 在生成时即持久化**（触发信号 + 依据的记忆/目标 + 时效性判断），事后可原样调取——这是"可解释的主动建议"的落点，也是业界"glass box / citations are currency of trust"共识的工程形态。
2. **展示 ≠ 被看到**：案例中 idea 被 surfaced 40 次、实际 impression 35 次，静默两天后才由 notifier 升级为聊天打断。打断决策服从 `intervene ⇔ E[benefit] − E[cost] > θ`（Horvitz 1999 的期望效用公式在 LLM 时代的重建）。
3. **过期时间与事件绑定**：idea 的 `expires_at` 卡在行程开始后自动过期，避免了"过期建议"的经典坑。

LCA 映射上：信号摄取归 infrastructure，生成与打分归 cognition（think 内策略，不新增认知阶段），打断升级归 runtime（Continuous Control Plane + durable WorkQueue，不在认知阶段里跑 cron/daemon），rationale 归 Session/Journal（事实，唯一生产入口 `Session.append`），反馈调 θ 归 remember/reflect（只生成候选，不直接发布）。用户接受才执行，对应既有的 Approval / Verdict 许可控制面。

## 文件索引

- [proactive-persistence-reference-case.md](proactive-persistence-reference-case.md) — 正文：参考案例证据链、机制拆解、业界范式对照、LCA 映射、最小可行架构与评估短板。
