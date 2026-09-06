# Agent Note: Fact Plane 收敛 — 单一事实生产 seam

Status: implemented

## Problem

Session SSOT（ADR-0186）已 bind 生产 run，但 cognition 仍可通过 `bound.journal` → `RunStore.append` 写入平行账本；phase executor 又在事务外散落调用 lifecycle / meta emit。同一 perceive 步骤可能产生 `ContextManifested`（Journal）、`context.manifested.v1`（Session）、`context.injected.v1`（phase graph 补丁）三条表示。职责边界模糊，fold 与诊断需维护双源逻辑。

## Proposal

引入 **FactCommitter** 作为 harness 层唯一 commit seam，**PhaseFactEmitter** 在 `PhaseExecutionTransaction` 出口按 `SemanticPhase` 发射 catalog 事实；**PerceiveHub** 退化为纯 manifest 计算。Journal 平面从 cognition 可达路径退役，保留只读诊断。分 E0–E4 五波落地，每波可 revert。

## Alternatives considered

### Why not keep Journal as a second SSOT?

RunLedger 三平面（ADR-0065）在 Session 迁移前合理。双 SSOT 导致 durable 链、fold 输入、诊断三处不一致；维护成本随每个新事件类型线性增长。Session + spine.jsonl 已覆盖 durable 需求。

### Why not only fix perceive?

Perceive 是症状。`RuntimeJournalCommitter`、`record_runtime`  scattered emit、executor 内 lifecycle 调用是同一类架构债；单点修补会留下平行入口，下一 phase 复现。

### Why not delete RunStore entirely?

工具生命周期、历史 replay、Coding Agent 只读诊断仍消费 Journal 类型。目标是 **禁止 cognition 生产写入**，不是删除 RunLedger 模块。

### Why not move reducer markers in Wave E2?

`runtime.reducer.apply` 被 turn_control projection 消费；迁到 `ReducerObserver` 需单独 ADR 缝。Wave E2 不触碰 Reducer 仪器。

## Acceptance criteria

- `tests/architecture/test_fact_plane_invariants.py` I-FACT-1..5 无条件 pass
- Perceive 单步仅产生 `context.manifested.v1` + `step.started.v1`（Session），无 `ContextManifested` Journal 写入
- `PhaseExecutionTransaction` 为 declarative fact commit 唯一边界（architecture test）
- `rg '_merge_events' lca/` 为零（E4）

## Risks

- 部分 e2e 测试仍 inject `JournalSink.for_store` — 保留测试适配器至 E4 delete-when
- 离线无 Session 绑定时 catalog emit no-op — 与现有 lifecycle_emit 语义一致
