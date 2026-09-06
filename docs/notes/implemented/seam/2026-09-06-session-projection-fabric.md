# Agent Note: Session Projection Fabric — Model-Visible 读面收敛

Status: implemented

## Problem

`derive_messages` 名字出现在 Protocol、Session 方法、纯函数、assembler、token meter 等多处，运行时每次全 log 扫描，文档承诺增量缓存未实现。与 ADR-0191 四态分离不一致：Model-visible 应是 Registered Projection，不是 Session 内嵌 fold。

## Decision

新增 `ModelVisibleUnit`（`session.projection.model_visible`），经已有 `ProjectionRegistry` observer 增量维护 surface nodes + messages。`projection_reader.model_visible_messages` 为统一读入口；有 registry 读投影，无 registry 回退 `derive_messages(events)` 纯函数（detached Session / offline）。

`Session._projections` 由 registry `register_to` 接线；`ModelContextAssembler` 经 `model_visible_messages` 读。删除 `build_tool_history` 与 `derive_event_message` 的 `.v1` compat fallback。

## Alternatives considered

- **Session 内嵌增量 surface 缓存**：否决；与 DSH sessionProjections 不对齐，无法 checkpoint/restore。
- **仅改文档不实现缓存**：否决；doc/impl 漂移持续制造「职责不清」。

## Verification

- `tests/plugins/session/test_model_visible_projection.py` — I-MV-PROJ-1 parity
- `tests/architecture/test_projection_fabric_invariants.py` — I-MV-PROJ-2..4
- `tests/cognition/test_model_context_parity.py` — assembler ≡ derive

## Consequences

- `bundles/session-runtime.yaml` 注册 `session_model_visible`（在 stats 之前）
- 测试侧 `build_tool_history` 迁至 `tests/support/tool_history_fixtures.py`
