# 实现计划：群聊房间运行时（Room Runtime Go-Live）

**文档标识**：`docs/plans/2026-09-23-room-runtime-go-live-plan.md`
**对齐设计**：[`2026-09-23-room-runtime-go-live-design.md`](2026-09-23-room-runtime-go-live-design.md)
**关联 ADR**：ADR-0250、ADR-0248、ADR-0042、ADR-0228
**状态**：Approved by User
**日期**：2026-09-23

## 目标

实现 M1 垂直切片：群聊房间从「契约 + 仓储 + 路由」变为「可运行闭环」。用户在房间里发消息，run 通过既有 `RunPort` 真实执行，房间转录记录用户消息与 run 启动事实，折叠结果可回写房间。

## 任务清单

### Task 1: 契约层

- [ ] 在 `lca/contracts/models/collaboration/peer.py` 增加 `RoomMessageKind` 枚举与 `RoomMessage` 模型。
  - 字段：`message_id`、`room_id`、`kind`、`sender_id`、`content`、`correlation_id`、`run_id`、`payload`、`created_at_ms`。
  - `frozen=True`，`extra="forbid"`。
  - 更新 `__all__`。
- [ ] 测试 `tests/collaboration/test_room_message_contract.py`。

### Task 2: 房间消息存储

- [ ] 在 `lca/domain/collaboration/room.py` 增加 `RoomMessageStore` 协议与 `JsonRoomMessageStore`。
  - `append(message)` 幂等（按 `message_id` 去重）。
  - `list_messages(room_id)` 按时间序返回。
  - 落盘 `~/.lca/rooms/<room_id>/messages.jsonl`。
- [ ] 测试 `tests/collaboration/test_room_message_store.py`。

### Task 3: 房间调度器

- [ ] 新建 `lca/application/collaboration/room_dispatch.py`。
  - `RoomNotFoundError`。
  - `RunDispatchResult` dataclass（`run_id`、`trace_id`、`accepted`、`rejection_reason`）。
  - `RunStarter` 协议：`async __call__(*, objective, mode, correlation_id) -> RunDispatchResult`。
  - `RoomDispatcher`：`dispatch(room_id, user_text, sender_id="user")`、`finalize(room_id, run_id, folded)`。
- [ ] 测试 `tests/collaboration/test_room_dispatcher.py`、`test_room_dispatcher_finalize.py`。

### Task 4: REST 路由

- [ ] 新建 `lca/plugins/transport/webserver/routes_3/routes_rooms.py`。
  - `POST /v1/rooms`、`GET /v1/rooms`、`GET /v1/rooms/{room_id}`。
  - `POST /v1/rooms/{room_id}/messages`、`GET /v1/rooms/{room_id}/messages`。
  - `run_starter` 接线到 `RunPort`：`prepare_run_from_messages`、`parse_agent_ref`、`resolve_profile_mode`、`RunRequest`、`create_and_dispatch`、`register_gateway_run`。
  - 复用 `cors_headers` 与 `RouteSpec` 注册。
- [ ] 路由插件注册（`@plugin`，`requires=("route_registry",)`）。
- [ ] 测试 `tests/collaboration/test_room_routes.py`。

### Task 5: 集成与门禁

- [ ] `tests/collaboration/test_room_api_e2e.py`：用假 `RunPort` 冒烟房间 API 闭环。
- [ ] 运行 `ruff check`、`ruff format`、相关 pytest。
- [ ] 运行 `python scripts/verify_md_links.py`、`python scripts/verify_doc_budgets.py` 验证文档门禁。

## 验证矩阵

| 变更类型 | 验证 |
|---|---|
| 普通实现，单 seam | `ruff check` + `ruff format` + 相关 pytest |
| 契约模型 | 上述 + 契约测试 |
| REST 路由 | 上述 + 路由注册测试 |
| 文档 | `verify_md_links` + `verify_doc_budgets` |

## 提交计划

1. `docs(plans): room runtime go-live design and plan`
2. `feat(collaboration): add RoomMessage contract and RoomMessageStore`
3. `feat(collaboration): add RoomDispatcher with real run dispatch`
4. `feat(webserver): add /v1/rooms REST routes`
5. `test(collaboration): room runtime tests`