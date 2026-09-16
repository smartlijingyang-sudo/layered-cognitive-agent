# ADR-0233 — C11 escape-hatch policy: spine.* raise-loud, non-spine carve-out with delete-when

**Status:** Accepted — 2026-09-16. 同 PR 落地(spec §12 G-15 决策;实现中判定无需 kernel 变更)。

> **一句话**：`execution_point="unknown"` fallback 在 `lca_kernel/events/persistence/persistence.py:_map_session_event` 中仅在 **非 spine 事件**(Session/Catalog 事件)使用,不违反 C11 事件闭集;`spine.*` 前缀已 fail-loud。保留 carve-out,`delete-when` = ADR-0192 Catalog→Spine 迁移完成。

**Refines / Fixes:**
- Spec §15 G-15 原定"注册 `AgentRunFinished` → `spine.lifecycle.run_finished` 并移除 fallback" — 本 ADR 判定该方向**错误**,改为文档化 carve-out。
- G-9 / G-8(Task 1.6+1.7 已落地)已使 `terminal_event_seq_from_file` 降级为 stub 返回 0,manifest 完整性源改用 `health_hash`,故"注册 AgentRunFinished 让 terminal_event_seq 非 0"的动机不复存在。

## Problem

Spec §15 G-15 假设 `AgentRunFinished` 必须注册成 spine EP,否则 C11 事件闭集被 `execution_point="unknown"` fallback 破坏。调查发现该前提混淆了两个事件系统:

1. `AgentRunFinished` 是 **Session/Catalog** 事件(`lca/infrastructure/observability/events/event/`),不是 spine 事件。
2. `execution_point="unknown"` fallback **只作用于非 spine 事件**;以 `spine.` 前缀的 category 早已 fail-loud(`persistence.py:113-119` raise `ValueError`)。
3. `terminal_event_seq_from_file` 已在 Task 1.6+1.7 降为 deprecated stub(恒返 0),新完整性源是 `health_hash`。所以"让 terminal_event_seq 非 0"不再是目标。

### 现状(实测)

| 事件类型 | `event.type` 前缀 | `category_to_spine_ep` | 当前行为 |
|---|---|---|---|
| spine 事件 | `spine.*` | 有映射 | 映射成功 |
| spine 事件 | `spine.*` | **无映射** | **raise ValueError**(fail-loud)✅ |
| Catalog 事件 | 非 `spine.*`(如 `agent.run_finished`) | None | `execution_point="unknown"` |

## Decision

1. **不注册** `AgentRunFinished` → `spine.lifecycle.run_finished`。Catalog 与 Spine 是两套事件系统(ADR-0192 FactPlane 收敛边界);把 Catalog 事件注册到 `SPINE_EXECUTION_POINTS` 白名单会混淆两套闭集,违反 ADR-0192 收敛方向。
2. **保留** `execution_point="unknown"` fallback 作为非 spine 事件的文档化 carve-out。它不违反 C11,因为 C11 事件闭集(`SPINE_EXECUTION_POINTS`)只约束 spine 事件;非 spine Catalog 事件本不该进入该白名单。
3. **删除动机已消失**:`terminal_event_seq_from_file` 已 stub 化(G-9),`health_hash` 是完整性源(G-8)。原 G-15 中"让 manifest.terminal_event_seq 非 0"的目标不再存在。

## Consequences

- **不新增 spine EP** — `SPINE_EXECUTION_POINTS` 不变。
- **不新增 kernel 代码** — `persistence.py` / `spine.py` 零改动。
- **Delete-when:** `ADR-0192 Catalog→Spine 迁移完成` 时,非 spine Catalog 事件会获得自己的固化和血统,`"unknown"` fallback 到时可删(或改为 raise,取决于迁移后的 shape)。
- **验收测试:** `test_no_regression_unknown_fallback_is_documented` — 断言代码中有 delete-when 注释;`test_spine_prefix_raises_loud` — 断言 `spine.` 无映射仍 raise。

## Test evidence

```
python -c "from lca_kernel.events.persistence.persistence import _map_session_event"
# spine.* 无映射 → ValueError(fail-loud)
# 非 spine → execution_point='unknown' + module docstring 已标注 delete-when
```
