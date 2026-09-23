# 架构设计文档：群聊房间运行时（Room Runtime Go-Live）

**文档标识**：`docs/plans/2026-09-23-room-runtime-go-live-design.md`
**对齐契约**：[`ADR-0250`](../adr/0250-peer-assistants-handoff-bus-and-rooms.md)（已落地）、[`ADR-0248`](../adr/0248-grok-bot-coordinator-runtime-evidence.md)（产品解剖）
**关联 ADR**：ADR-0042（角色库与自动组队）、ADR-0228（委派子图与类型化端口）、ADR-0246（用户机副作用平面）
**状态**：Approved by User
**日期**：2026-09-23

## 1. 摘要与设计动机

群聊房间是 Grok Bot「持久队友 + 房间 + 异步 Mailbox」产品形态在 LCA 的落点。现有代码已经具备房间的静态层：`RoomSpec` 契约、`JsonRoomRepository` 仓储、`RoomMessageRouter` 路由。缺口是运行时：用户发消息后没有真正的执行路径，`TeamCastTool` 与 `HandoffToPeerTool` 的专家回执是模拟文本，没有跑真实 agent。

本设计把房间从「契约 + 仓储 + 路由」补齐为「可运行闭环」：用户消息 → 路由 → 真实 run 分发 → 房间转录记录 → 折叠结果回房间。M1 垂直切片只做后端闭环，前端群聊视图留到阶段 3。

## 2. 现状盘点

| 层 | 现状 | 位置 |
|---|---|---|
| 契约 | `RoomSpec`、`PeerProfile`、`HandoffEnvelope`、`PeerFoldedResult` | `lca/contracts/models/collaboration/peer.py` |
| 仓储路由 | `JsonRoomRepository`、`RoomMessageRouter`（coordinator_first / mention_only） | `lca/domain/collaboration/room.py` |
| 组队 | `LLMTeamCaster` → `CastingPlan` → Team 编译 | `lca/application/authoring/casting.py` |
| 折叠 | `DelegationFoldAggregator` 生成【协同汇报】 | `lca/application/collaboration/fold.py` |
| 唤醒 | `WakeSource` 闭集 + `RevivalCoordinator` | `lca/contracts/models/vocal/wake.py`、`lca/application/vocal/revival.py` |
| 前端 | `CollaborationTeamBar` 成员条卡片 | `deploy/lobehub/patches/ui/CollaborationTeamBar.tsx` |
| 运行底座 | `POST /runs`、`RunPort`、gateway WS | `lca/plugins/transport/webserver/handlers/runs/` |

两个核心缺口。

1. 房间消息没有运行时。现在只有路由判定，没有「用户发消息 → 真正跑一个 run → 结果回房间」的调度器。
2. `TeamCastTool` / `HandoffToPeerTool` 是模拟的。`delegate_tool.py` 中的 receipts 是硬编码文本，没有真正执行 agent。

## 3. 目标行为

用户在房间里发一条消息。协调者按 `routing_policy` 分流。coordinator_first 模式走自动组队，mention_only 模式按 @ 白名单转交。run 通过现有 `RunPort` 真实执行。房间转录记录用户消息和 run 启动事实。折叠结果可以回写房间。

## 4. 架构设计

### 4.1 数据模型

新增 `RoomMessageKind` 与 `RoomMessage`，放在 `lca/contracts/models/collaboration/peer.py`。

```python
class RoomMessageKind(StrEnum):
    USER = "user"
    RUN_STARTED = "run_started"
    PEER = "peer"
    FOLDED = "folded"
    APPROVAL = "approval"

class RoomMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str
    room_id: str
    kind: RoomMessageKind
    sender_id: str
    content: str
    correlation_id: str = ""
    run_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int
```

房间消息是不可变追加事实。`correlation_id` 关联一轮协同，`run_id` 关联真实 run。

### 4.2 房间消息存储

`RoomMessageStore` 协议与 `JsonRoomMessageStore` 实现放在 `lca/domain/collaboration/room.py`，与现有 `JsonRoomRepository` 同目录。

- 追加写，按 `message_id` 幂等去重。
- 落盘到 `~/.lca/rooms/<room_id>/messages.jsonl`，追加式。
- `list_messages(room_id)` 按时间序返回全部消息。

### 4.3 房间调度器

`RoomDispatcher` 放在 `lca/application/collaboration/room_dispatch.py`。

依赖注入：

- `room_repository: RoomRepository`
- `message_store: RoomMessageStore`
- `run_starter: RunStarter`（协议：`async (objective, mode, correlation_id) -> RunDispatchResult`）
- `clock`（可选，默认 `time.time`）

`dispatch(room_id, user_text, sender_id="user")` 流程：

1. 从仓储取 `RoomSpec`，不存在抛 `RoomNotFoundError`。
2. 追加 `USER` 消息。
3. 用 `RoomMessageRouter` 路由，得到 `selected_peers`（记录用）。
4. 决定 mode。成员大于 1 时 `team`，否则 `solo`。
5. 调用 `run_starter` 创建真实 run。
6. 追加 `RUN_STARTED` 消息，payload 携带 `run_id`、`trace_id`、`selected_peers`。
7. 返回 `RUN_STARTED` 消息。

`finalize(room_id, run_id, folded: PeerFoldedResult)` 流程：

1. 追加 `FOLDED` 消息，content 为 `synthesized_verdict`，payload 携带 `member_findings`、`consensus_status`、`member_metadata`。

`finalize` 是折叠结果回写房间的入口。M1 提供方法，阶段 2 用 run 完成事件自动调用。

### 4.4 REST 路由

新增 `lca/plugins/transport/webserver/routes_3/routes_rooms.py`，沿用 `RouteSpec` 声明式注册：

- `POST /v1/rooms` 创建房间
- `GET /v1/rooms` 列出房间
- `GET /v1/rooms/{room_id}` 获取房间
- `POST /v1/rooms/{room_id}/messages` 发消息（触发调度）
- `GET /v1/rooms/{room_id}/messages` 列出消息

`run_starter` 在路由层接线到 `RunPort`：用 `prepare_run_from_messages` 解析消息、`parse_agent_ref` 解析身份、`resolve_profile_mode` 解析模式，构造 `RunRequest` 后调用 `create_and_dispatch`，再调 `register_gateway_run` 让 run 进入 gateway 流。

### 4.5 运行时拓扑

```text
[用户 POST /v1/rooms/{room_id}/messages]
   │
   ▼
[RoomDispatcher.dispatch]
   │
   ├─ 追加 USER 消息
   ├─ RoomMessageRouter 路由 → selected_peers
   ├─ run_starter (RunPort.create_and_dispatch)
   ├─ register_gateway_run
   └─ 追加 RUN_STARTED 消息
   │
   ▼
[run 在既有运行底座执行, gateway 事件流入 LobeHub]
   │
   ▼
[阶段 2: run 完成事件 → finalize → 追加 FOLDED 消息]
```

## 5. 分阶段方案

### 阶段 1（M1）：房间消息运行时

- `RoomMessage` 契约
- `RoomMessageStore` + `JsonRoomMessageStore`
- `RoomDispatcher` + `RunStarter` 协议
- `/v1/rooms` REST 路由
- 单元测试与集成测试

### 阶段 2：惰性 Revival（已落地）

- `RoomDispatcher.sync_completed`：读取房间转录时，对已到达终态的 run 自动追加 `FOLDED` 消息。
- 幂等：同一 `correlation_id` 已有 FOLDED 则不重复追加；进行中的 run 跳过。
- 终态来源：`RunPort.summary` 返回的 status（completed / failed / canceled 等）。
- 说明：run 的完整输出文本不持久化在后端可读位置，FOLDED 消息携带终态摘要；完整结论仍在 run 自己的会话里由 gateway 投递。
- `MailboxStore` 与 push 式 `RuntimeLifecycleEvent` 订阅留作后续增强。

### 阶段 3：前端群聊视图

- LobeHub patch：房间侧边栏、群聊会话、@ 提及、成员条、交接可见。
- 复用 `CollaborationTeamBar` 与现有 run 消息流。

### 阶段 4：Routines（可选）

- 房间定时任务与事件触发。本设计不展开。

## 6. 容错与幂等

1. 房间不存在返回 404。
2. 消息追加按 `message_id` 幂等，重复投递不产生重复转录。
3. `run_starter` 失败时 `RUN_STARTED` 不追加，`USER` 消息保留，调用方收到错误。
4. `correlation_id` 每轮生成一次，贯穿路由、run 与折叠。

## 7. 测试矩阵

| 编号 | 测试用例 | 验证要点 |
|---|---|---|
| T1 | `test_room_message_contract.py` | `RoomMessage` 不可变、`extra="forbid"`、类型正确 |
| T2 | `test_room_message_store.py` | 追加、幂等、按时间序列出、持久化 |
| T3 | `test_room_dispatcher.py` | 路由判定、run 启动、消息追加顺序、房间不存在报错 |
| T4 | `test_room_dispatcher_finalize.py` | `finalize` 追加折叠消息、payload 完整 |
| T5 | `test_room_routes.py` | REST 路由注册、创建房间、发消息、列消息 |
| T6 | `test_room_api_e2e.py` | 集成测试：真实 `RunPort` 路径的冒烟 |

## 8. 边界划分（AP-01）

Owns：

1. `lca/contracts/models/collaboration/peer.py` 的 `RoomMessage` 契约。
2. `lca/domain/collaboration/room.py` 的 `RoomMessageStore`。
3. `lca/application/collaboration/room_dispatch.py` 的 `RoomDispatcher`。
4. `lca/plugins/transport/webserver/routes_3/routes_rooms.py` 与路由插件。
5. 对应测试。

Does NOT own：

1. 不改认知六相闭集与既有不变量（C1/C11）。
2. 不直接改 `lobehub-ui/` 或 `vendor/`。
3. 不新开平行事件词表，房间消息不进 `Session.append` 轨道。
4. 不改变 `POST /runs` 的既有行为与响应。

## 9. 非目标

- 本设计不实现异步 Mailbox 与 revival 自动回写（阶段 2）。
- 本设计不实现前端群聊视图（阶段 3）。
- 本设计不引入新的并行事件系统。
- 本设计不迁移 `RoomSpec` 与 `JsonRoomRepository` 的既有实现。