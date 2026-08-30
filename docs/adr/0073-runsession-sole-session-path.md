# ADR-0073: Session Path Convergence

## 状态

Proposed — 2026-08-21

Keeps: [ADR-0004](0004-protocol-first-pluggability.md)、[ADR-0061](0061-plugin-manifest-resolve-boot.md)、[ADR-0063](0063-run-trace-ssot.md)

> **核心决策：承认两条 session 路径并存（`/runs/*` 走 `RunRegistry`，`/v1/sessions/*` 走 `AgentRegistry` + `Inbox` + `SessionStore` + `JsonlSessionPersistence`）；本 ADR 不在本期收敛路径，仅约束两条路径都遵守 `SessionService` Protocol；收敛推迟到 `/v1/sessions/*` 接入 `RunRegistry` 的后续 ADR。**

## 背景

2026-08-21 复核发现：`lca/harness/session/{inbox, store, persistence}.py` 三件具体类**不是死代码**——它们是 `lca/harness/agent/registry.py::AgentRegistry` 的实现细节，`AgentRegistry` 由 `gateway/spine.py::bind_session_spine` 在 `gateway/app.py::create_app` 构造；`gateway/session_routes.py` 的 `/v1/sessions/{create,send_message,snapshot,events,answer,cancel,steer,inject}` 9 个端点都消费 `CommandGateway` → `AgentRegistry`，是生产路由。

`gateway/runs/{execute,session}.py` 的 `RunRegistry` + `RunSession` 是另一条生产路径，对应 `/runs/*` 端点（`create_run` / `get_run` / `cancel_run` / `answer_run` / `stream_run_live`）。

两条路径并存事实：

| 路由面 | session 后端 | Journal 词表 | 投影 |
|---|---|---|---|
| `/runs/*` | `RunRegistry` + `RunSession` + `LiveTail` + `ProcessJournal` | `AgentRunStarted/Finished`、`TeamRunStarted/Finished` | `JournalProjector` 列表 |
| `/v1/sessions/*` | `AgentRegistry` + `Inbox` + `SessionStore` + `JsonlSessionPersistence` | `SessionEvent`（v2 envelope）+ `MessageAccepted/TurnStarted/TurnEnded/SessionCheckpoint/ToolApprovalResolved/InboxSpliced/SessionCreated` | `InMemoryProjectionRegistry` + `ConversationProjection` + `ActivityProjection` + `SkillsProjection` |

宪法 §0.4 line 222 自承「Inbox 在 harness，未被 `_loop` claim」——指的是 `_loop` 不读 Inbox；但 `AgentRegistry` 在 `_loop` 之外（LiveAgent 适配器层）使用 Inbox。`/v1/sessions/*` 是 Spine Spec §2.2.7 Command SPI 的兑现路径，不是 dead code。

具体摩擦：

- `lca/harness/session/` 三件具体类约 220 行；契约 `lca/contracts/harness/session.py` 仅含 dataclass（`SessionHeader` / `EventScope` / `SessionEvent` / `session_event` decorator），无 `SessionService` Protocol。
- 两条路径在 ADR-0065 §三的 v2 envelope 上有部分重叠（`SessionEvent` 字段映射到 `StampedEvent`），但尚未统一。
- `AgentRegistryFacade` Protocol 在 `lca/contracts/harness/command.py:61` 已声明，但 `lca/harness/agent/registry.py::AgentRegistry` 是具体类，未声明 Protocol 继承——契约与实现脱节。

## 决策

**本 ADR 仅做契约收敛，不删除任一路径。**

**`SessionService` Protocol。** 在 `lca/contracts/harness/session.py` 新增：

```python
class SessionService(Protocol):
    def append(self, event: SessionEvent) -> SessionEvent: ...
    def read_from(self, seq: int) -> Sequence[SessionEvent]: ...
    def events(self) -> tuple[SessionEvent, ...]: ...
    def subscribe(self, listener: Callable[[SessionEvent], None]) -> None: ...
    @property
    def current_seq(self) -> int: ...
```

**两条路径都实现该 Protocol。** `AgentRegistry` 持有 `SessionStore`，`SessionStore.append` 签名调整为满足 Protocol。`RunSession` 当前不实现该 Protocol（它的 `runnable` 是 Live Agent 引用，不是 session 后端），保持现状——`RunSession` 是 Run 聚合数据类，不是 session 后端。

**`AgentRegistry` 声明 Protocol 继承。** `class AgentRegistry(AgentRegistryFacade, SessionService): ...`——避免契约脱节。

**不删除。** `lca/harness/session/{inbox, store, persistence}.py` 保留；`lca/harness/agent/registry.py` 保留；`gateway/spine.py` 保留；`gateway/session_routes.py` 保留；`tests/harness/{test_phase_b_spine,test_skill_provider,test_harness_spine_e2e}.py` 保留。**本期零代码删除**。

**后续 ADR（不在本 ADR 范围）。** `/v1/sessions/*` 端点逐步接入 `RunRegistry` 单一路径：每个 `/v1/sessions/*` 端点的 handler 改为调 `RunRegistry.create_run` / `send_message` / `cancel_run`，由 `RunRegistry` 内部持有 `AgentRegistry` 的事实收敛。一旦所有端点接入，`AgentRegistry` + `Inbox` + `SessionStore` + `JsonlSessionPersistence` 即成为内部细节，可作为 ADR 候选删除项。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| 零风险 | 本期不动代码，零 break | 仅增 Protocol 定义 + AgentRegistry 继承声明 |
| 契约清晰 | `SessionService` Protocol 让两条路径在 dataclass 字段外有可测试契约 | Protocol 与 `AgentRegistry` 已有方法的签名需对齐（可能需要小幅 adapter） |
| 收敛留口 | 明确「`/v1/sessions/*` 接入 `RunRegistry`」作为后续 ADR | 该后续 ADR 需要重新评估 trade-offs，本 ADR 不替它决定 |

**验证约束：**

- `tests/test_layer_boundary.py` 断言两条路径都 import 同一 `lca/contracts/harness/session.py::SessionService` Protocol
- `tests/test_session_service_contract.py`（新增）：`AgentRegistry` 实例通过 `isinstance(reg, SessionService)` 为真；调用 5 个 Protocol 方法不抛 `AttributeError`
- `tests/harness/` 全部测试仍通过（不动既有路径）
- vulture `--min-confidence 80` 兜底，确认未引入新死代码

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 立即删除 `lca/harness/session/` 三件具体类与 `AgentRegistry` | `/v1/sessions/*` 9 个端点 production 路径，未接入 `RunRegistry` 前删除会断路由 |
| 把 `/v1/sessions/*` 直接迁到 `/runs/*` | 需要新 ADR 评估命令命名、idempotency key、projection snapshot 语义；范围远超本 ADR |
| 引入抽象 `SessionBackend` 让两条路径共享同一类 | 与本 ADR 的 `SessionService` Protocol 等价，但类形式过早约束；Protocol 形式允许两条路径各自优化 |
| 维持现状不写 ADR | 不约束契约一致性；后续接入时已存字段漂移风险 |