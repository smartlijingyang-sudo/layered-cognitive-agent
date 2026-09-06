# ADR-0192 — Fact Plane 收敛：单一事实生产面

## 状态

Implemented（2026-09-06）。延伸 ADR-0186（Session SSOT）、0183（event bus + spine.jsonl）、0191（runtime DSH 收敛）、0065（RunLedger 三平面）、0075（declarative phase graph）。

**实施路径**：本 ADR 描述的终态通过 ADR-0186（Session SSOT）、ADR-0194（FactGateway 单轨 + FactCommitter）、ADR-0195（全栈平台收敛）分步落地，未按本文 E0–E4 分波独立执行。截至 Proposed 日期，所有目标已闭环：

- E0 `FactCommitter` + `SessionFactCommitter` → `lca/contracts/protocols/observability/fact_committer.py` + `lca/infrastructure/session/commit/fact_committer.py`
- E1 `PhaseFactEmitter` + Transaction 接线 → `lca/loop/emit/spine/phase_fact.py` 被 `lca/loop/transaction.py` 调用
- E2 `RuntimeJournalCommitter` → `SessionFactCommitter` → `lca/runtime/loop/runtime_journal.py`
- E3 cognition 侧 Journal 双写清除 → `rg "facade.record|bound.journal|journal.write" lca/cognition/ lca/runtime/ lca/agent/` = 0
- E4 残留删除 → `_merge_events` / `JournalSink` in cognition / `context_manifest_dual_write` 全部 = 0

**配套 Note**：[`docs/notes/implemented/seam/2026-09-06-fact-plane-convergence.md`](../notes/implemented/seam/2026-09-06-fact-plane-convergence.md)。

> **EventBus 与事实平面的关系**：EventBus（`EnvelopeBus`）是实时事件分发机制（publish → hook → sink dispatch），不是事实平面。事实平面的 SSOT 是 `Session.append`（`lca/session/`）。EventBus 在 publish 路径中将事件路由到 Session observer，但事实的唯一生产入口是 Session，不是 EventBus。

## 0. 决策摘要

LCA 观测面已按 ADR-0186 将 **Session.append** 定为 durable 链 SSOT。本 ADR 记录 **Fact Plane** 终态的收敛目标：**认知层只产出候选事实；Harness 阶段事务边界统一提交；Session 是唯一公开生产入口**。该终态已通过上述 ADR 实现。

```text
PhaseExecutor → PhaseResult { payload, deltas, facts }
       │
       ▼
PhaseExecutionTransaction (唯一 commit 边界)
       │
       ├─ PhaseFactEmitter → catalog 生命周期 / manifest / step 边界
       ├─ FactCommitter.commit_* → Session.append / spine EP
       └─ LoopCursor.advance → phase.*.fold (WritePort → Session hook)
       │
       ▼
Session.append (in-process SSOT)
       │
       ├─ PersistenceObserver → <run_id>.spine.jsonl
       └─ fold / projection observers (只读派生)
```

| 角色 | 拥有 | 不做 |
|---|---|---|
| `PhaseExecutor` | 业务计算、`PhaseResult` | 不 `record()` / 不 `journal.write` / 不 `Session.append` |
| `PhaseExecutionTransaction` | 事务边界、fact commit 编排 | 不含业务策略 |
| `FactCommitter` | `Session.append` + spine EP 路由 | 不知 fold / JSONL 格式 |
| `PhaseFactEmitter` | 按 `SemanticPhase` 发射 catalog 事实 | 不读 executor 内部 |
| `Session` | in-process log SSOT | 不知 cognition 细节 |
| fold / projection | 从 `snapshot_events()` 重建 | 零 I/O、不反向写事实 |

**不做什么**：不删除 RunLedger 类型系统（诊断/工具 journal 只读回放仍可用）；不改 Reducer fold 语义。

## 1. 第一性原理

运行时只做三件事：**生产事实 → 持久化 → 派生**。任何机制不能同时承担事实源与投影职责（AGENTS.md §2.2）。

Journal 平面（`RunStore.append` + `ProjectionRegistry.on_event`）在 ADR-0186 之前是合法 SSOT；Session 平面落地后，Journal **不得再作为 cognition 可达的生产入口**。`on_event` 扇出仅允许作为 Session observer 的内部实现，或测试/CLI retained 路径。

## 2. 差距（已全部关闭）

| 差距 | 原状 | 处置 |
|---|---|---|
| Perceive 双写 | `JournalSink` + `context.manifested.v1` | ✅ 仅 Session catalog |
| Phase executor 散落 emit | `perceive.py` / `remember.py` 直调 lifecycle | ✅ `PhaseFactEmitter` |
| Declarative journal | `RuntimeJournalCommitter` → `record_runtime` | ✅ `SessionFactCommitter` |
| Hub 职责污染 | emit + cursor + fold | ✅ 纯 manifest 计算 |
| 诊断双源 | `ContextManifested` vs `context.manifested.v1` | ✅ Session fold 优先 |
| 死代码 | `_merge_events` 未调用 | ✅ 已删除 |

## 3. 设计

### 3.1 FactCommitter（契约）

`lca/contracts/protocols/observability/fact_committer.py`：

- `commit_fact(RunFact)` — 按 `kind` 路由 catalog / spine
- `commit_evidence` / `commit_observation` — 声明式事务证据与 effect receipt
- 实现：`SessionFactCommitter`（`lca/infrastructure/session/commit/fact_committer.py`）

`JournalCommitter` 保留为别名；新代码使用 `FactCommitter`。

### 3.2 PhaseFactEmitter

`lca/loop/emit/spine/phase_fact.py` — 在 `PhaseExecutionTransaction` 成功路径末尾调用：

| SemanticPhase | Catalog 事实 | Cursor |
|---|---|---|
| PERCEIVE | `step.started.v1`、`context.manifested.v1` | `advance("perceive")` |
| REMEMBER | `step.ended.v1` | — |
| 其他 | 无默认 catalog（facts 经 committer） | 按 ADR-0169 逐步接线 |

### 3.3 事件映射（Journal → Session）

| Legacy JournalEvent | Session catalog | 处置 |
|---|---|---|
| `ContextManifested` | `context.manifested.v1` | 停止 Journal 生产 |
| `GateDecided` | `gate.decided.v1` | 已有 `cognitive_emit` |
| `RuntimeObserved` (declarative) | spine EP `phase.fact` / `effect.receipt` | 经 FactCommitter |

### 3.4 不变量（I-FACT-1..5）

| ID | 内容 | 测试 |
|---|---|---|
| **I-FACT-1** | `Session.append` 是唯一事实生产公开入口 | `test_i_fact_1_*` |
| **I-FACT-2** | cognition / runtime / agent 禁 `journal.write` / `facade.record` / `bound.journal` | `test_fact_plane_invariants.py` I-FACT-2 |
| **I-FACT-3** | `PhaseExecutionTransaction` 是唯一 declarative commit 边界 | `test_i_fact_3_*` |
| **I-FACT-4** | fold / projection 无写路径 | 延伸 I-SESSION-2 |
| **I-FACT-5** | catalog 事件生产者闭集 + 架构测试 | `test_i_fact_5_*` |

## 4. 实施记录（E0–E4 已全部闭环）

| Wave | 内容 | delete-when | 状态 |
|---|---|---|---|
| E0 | `FactCommitter` 契约 + `SessionFactCommitter` + I-FACT 架构测试 | — | ✅ |
| E1 | `PhaseFactEmitter` + Transaction 接线 | — | ✅ |
| E2 | PerceiveHub 纯化；`RuntimeJournalCommitter` → `SessionFactCommitter` | — | ✅ |
| E3 | diagnostics Session 优先；删除 Journal 双写 | — | ✅ |
| E4 | shim 删除 | `_merge_events` = 0 / `JournalSink` in cognition = 0 / `facade.record` in cognition = 0 | ✅ |

## 5. 与既有 ADR 关系

| ADR | 处置 |
|---|---|
| **0186** | **延伸并收口**：FactCommitter 是 Session.append 的唯一 harness 路由 |
| **0191** | **互补**：Facts 四态分离；Fact Plane 清创 Journal 双写 |
| **0194** | **主要实施载体**：FactGateway 单轨 + cognition emit 收敛 |
| **0195** | **主要实施载体**：全栈平台收敛，Session 目录提升 |
| **0065** | **不冲突**：RunLedger 降级为只读诊断/工具回放；非 cognition 生产面 |
| **0075** | **延伸**：阶段图 + 阶段事务 = 事实编排器 |
