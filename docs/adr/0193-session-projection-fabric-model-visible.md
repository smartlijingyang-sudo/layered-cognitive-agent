# ADR-0193 — Session Projection Fabric：Model-Visible 收敛

## 状态

Implemented（2026-09-07）。D1–D7 全部落地：`ModelVisibleUnit` + bundle 注册、projection_reader、Session._projections 接线、Session.derive_messages / assembler、HeuristicTokenMeter 切换、`build_tool_history` / `.v1` fallback 退役、`I-MV-PROJ-*` 架构守卫。延伸 ADR-0191（四态分离）、0189（derive/fork）、0186（Session SSOT）、0185（model-visible fold）。

**配套 Note**：[`docs/notes/implemented/seam/2026-09-06-session-projection-fabric.md`](../notes/implemented/seam/2026-09-06-session-projection-fabric.md)。

## 0. 决策摘要

`derive_messages` 的**算法 SSOT** 仍是 `lca_kernel/events/fold.py` + `messages.derive_messages` 纯函数；**运行时读 SSOT** 改为 `ModelVisibleUnit` 投影（`session.projections` 注册表增量 fold）。`Session.derive_messages()` 与 `ModelContextAssembler` 读投影；离线 / fork / 无 registry 时回退纯函数。

```text
Session.append (Facts)
        │
        ▼
ProjectionRegistry (observer 驱动)
        │
        ├─ model_visible  → ModelVisibleUnit (增量 surface + messages)
        ├─ turn_control   → TurnControlUnit
        ├─ token_usage    → TokenUsageUnit
        └─ session_stats  → SessionStatsUnit
        │
        ▼
ModelContextAssembler.assemble()  ← 运行时 LLM wire 唯一入口
```

**不做什么**：不改 fold 数学；不删 `derive_messages(events)` 纯函数（offline parity）；不合并 `fold_model_visible`（per-step 视图，互补）。

## 1. 依赖执行清单（必须按序）

| 序 | 依赖 | 交付 | 验证 |
|---|---|---|---|
| D0 | — | ADR-0193 + Note | 文档链接 |
| D1 | D0 | `ModelVisibleUnit` + bundle 注册 | `test_model_visible_projection.py` |
| D2 | D1 | `projection_reader.model_visible_messages` | parity ≡ `derive_messages` |
| D3 | D2 | `Session._projections` + registry `register_to` 接线 | registry 集成测试 |
| D4 | D3 | `Session.derive_messages` / assembler / `assemble_model_history` | `test_model_context_parity.py` |
| D5 | D4 | `HeuristicTokenMeter` 读投影 | token meter 测试 |
| D6 | D5 | 删 `.v1` fallback、`build_tool_history` 生产符号 | architecture tests |
| D7 | D6 | `I-MV-PROJ-*` 架构守卫 | `test_projection_fabric_invariants.py` |

## 2. 不变量

| ID | 内容 |
|---|---|
| **I-MV-PROJ-1** | 有 registry 时 `model_visible_messages(session)` ≡ `derive_messages(snapshot)` |
| **I-MV-PROJ-2** | cognition 生产路径禁止 `build_tool_history` / 直接 `derive_messages` import |
| **I-MV-PROJ-3** | projection 单元禁止 `Session.append` |
| **I-MV-PROJ-4** | 新 surface 生产路径只写 surface 事件，不依赖 `.v1` fallback |

## 3. delete-when

```text
build_tool_history:
  delete_when: rg 'build_tool_history' lca/cognition/ lca/infrastructure/ lca/runtime/ = 0

derive_messages .v1 fallback:
  delete_when: derive_messages 测试不依赖 message.accepted.v1 / assistant.responded.v1

Session.derive_messages 纯函数回退:
  delete_when: 全部测试 Session 均挂 projection registry（可选 Wave F）
```

## 4. 与 ADR-0192 关系

**正交**：0192 清 Fact 生产面（Journal → Session.append）；0193 清 Model-visible 读面（多入口 → Projection Fabric）。可并行落地，0193 不依赖 0192 E 波。
