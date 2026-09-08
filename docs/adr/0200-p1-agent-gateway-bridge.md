# ADR-0200 — P1 Agent Gateway Bridge（WebSocket + Redis Stream 收敛）

## 状态

Accepted（2026-09-07）。Phase 1（PR-1：contract + StreamEventManager）已完成；PR-2（coordinator + gateway + facade switch）落地后即标记 `implemented`。

**Companion**: [ADR-0200 hermes 吸收](0200-hermes-product-capabilities-absorption.md) (产品能力吸收).

**延伸并统摄**：[ADR-0186](0186-session-as-event-ssot.md)（事实平面）、[ADR-0194](0194-cognitive-loop-architecture-convergence.md)（Loop 收敛）、[ADR-0195](0195-platform-architecture-convergence.md)（平台三时态）、[ADR-0198](0198-observability-compile-graph.md)（观测 compile graph）、[ADR-0199](0199-hermes-inspired-cognitive-plugin-convergence.md)（Hermes 启发收敛）。

**本文档角色**：在 ADR-0195 平台壳 + ADR-0199 入口统一之上，回答 **「如何以 native LobeHub AgentGateway 协议为 wire surface、把 LCA 的 LiveRunProjection fold 暴露给前端，同时不破坏 Session 事实单轨与 capability monotonic」**。

---

## 0. 决策摘要

LCA **不重写** Session / LiveRunProjection。LCA **新增** 一条 Redis Stream 通道 + Starlette `WebSocketRoute`，把 `LiveRunProjection.tail` 的 fold 结果以 native `AgentStreamEvent` 形态发布：

```text
SpineEvent ──→ Session.append ──→ LiveRunProjection.tail
                                          │
                                          ▼
              LcaAgentRuntimeCoordinator
                  ├── EventTranslator   (pure fold, no I/O)
                  ├── metadata_writer   → lca_running_operations (DB row)
                  ├── tool_state_writer → messages[].pluginState (DB col)
                  └── LcaStreamEventManager.publish
                                            │
                                            ▼
                            agent_runtime_stream:<run_id>  (Redis)
                                            │
                                            ▼
                    LcaAgentGateway (Starlette WebSocketRoute, RS256 JWT)
                                            │
                                            ▼
                  @lobechat/agent-gateway-client  (native, 零改动)
```

**LCA 保留并强化**：
- `Session.append` 事实单轨（ADR-0186/0194）—— Coordinator 是 fold 消费者，**不是** producer。
- `LiveRunProjection` 纯函数性（ADR-0198 I-OCG-6）—— side effect 全部下移到 Coordinator + writers。
- Capability monotonic（C5）—— `CommandEnvelope` 仍是副作用唯一出口；JWT mint/verify 是 read-side，不破坏写能力。
- Tool error 二分类（C10）—— `LlmError` / `LlmRetry` / `ToolDenied` 折叠时只映射到 `error` / `stream_retry` / `tool_end(isSuccess=False)` 三种 AgentStreamEvent。

**LCA 吸收 native 协议**：
- 18 `AgentStreamEvent` + 5 `ClientMessage` + 7 `ServerMessage` 字节级镜像。
- Redis Stream layout：`agent_runtime_stream:<run_id>`、TTL 2 h、MAXLEN `~1000`。
- JWT：RS256、5 min、`purpose: "cli-sandbox"`、`sub: <user_id>`。
- WS heartbeat：30 s / 3 次 missed / 1→30 s 指数退避。

**LCA 拒绝**：
- 在 `lca_running_operations` 加 `status` 列（spec §3.2 硬约束）。
- `tool_end` WS 事件携带 `projected_state`（spec §5.3.1 硬约束）；由 Coordinator 先写 `messages[].pluginState`，前端 `gatewayEventHandler.tool_end` 再 `fetchAndReplaceMessages`。
- 把 `LegacyRunDispatcher` / `LCA_RUNTIME_FACADE` / `RunUiEncoder` 留作 fallback（PR-4 一次性删干净）。

---

## 1. 新增模块与归属

| 路径 | 层 | 角色 |
|---|---|---|
| `lca/contracts/transport/{__init__,agent_stream_event,gateway_messages,stream_keys}.py` | contracts | wire-protocol 镜像。零 infra / cognition / runtime / agent / application / plugins / harness import（AST-verified）。 |
| `lca/infrastructure/observability/stream/stream_event_manager.py` | infrastructure | `LcaStreamEventManager`：XADD/XREAD/XRANGE/XLEN/EXPIRE wrapper，SSE-frame `AsyncIterator`。 |
| `lca/infrastructure/observability/stream/redis_client.py` | infrastructure | URL-precedence 工厂（`REDIS_URL` > `LCA_REDIS_URL` > `redis://127.0.0.1:6379/0`）。 |
| `lca/application/runtime/coordinator/{event_translator,terminal_hints,runtime_coordinator}.py` | application | StampedEvent → AgentStreamEvent fold；`RunSession.status` → 6-value wire enum；Coordinator start/handle_stamped/terminal/watchdog。 |
| `plugins/transport/webserver/handlers/runs/terminal/streaming/{agent_gateway,auth,resume}.py` | plugins | `LcaAgentGateway` Starlette `WebSocketRoute`；RS256 JWT mint + verify；history replay + `resume_complete`。 |
| `plugins/transport/webserver/handlers/runs/api/{command_endpoints,query_endpoints}.py` (modify) | plugins | `create_run` 增加 `ws_token`；`get_running_operation` 读 `lca_running_operations` jsonb。 |
| `application/runtime/default_facade.py` (modify) | application | `dispatch_run` 从 `LegacyRunDispatcher` 切到 `LcaAgentRuntimeCoordinator`。 |

新增模块一律走 `lca.application` 组合根装配；插件通过 capability key 交互，不直接 import。

---

## 2. 不变量

| ID | 内容 |
|---|---|
| **I-AGB-1** | `lca.contracts.transport` 不得 import `lca.infrastructure / cognition / runtime / agent / application / plugins / harness`。由 `lint-imports` 守护。 |
| **I-AGB-2** | Coordinator 是 `LiveRunProjection.tail` 的 fold 消费者；不得写 Session 事实。违反抛 `CoordinationLayerError`。 |
| **I-AGB-3** | `tool_state_writer(run_id, tool_call_id, projected_state)` 必须在 `LcaStreamEventManager.publish(tool_end)` **之前**完成。`AsyncMock` call-order 测试守护。 |
| **I-AGB-4** | `tool_end.data` **不得** 携带 `projected_state`；前端通过 `messages[].pluginState` 读取。 |
| **I-AGB-5** | `lca_running_operations` 表不得新增 `status` 列；语义由 `messages[].pluginState + accepted_answer_keys jsonb` 承担。 |
| **I-AGB-6** | Redis Stream key 必须是 `agent_runtime_stream:<run_id>`；TTL ∈ [7100, 7200] 秒；MAXLEN 近似 ≤ 1100。 |
| **I-AGB-7** | JWT payload 必须包含 `purpose: "cli-sandbox"`、`sub: <user_id>`；算法 RS256；过期 ≤ 5 分钟。 |
| **I-AGB-8** | WS 心跳：`client_interval = 30 s`、`missed_threshold = 3`、`backoff ∈ [1 s, 30 s] 指数`。 |
| **I-AGB-9** | Coordinator watchdog：当 `RunSession.status ∈ TERMINAL` 但 60 s 内无 `SpineClose` 时，**合成** `agent_runtime_end` 并 cleanup stream。**禁止** 重复 publish（idempotent guard）。 |
| **I-AGB-10** | `LcaAgentRuntimeCoordinator.synthesize_terminal_if_pending` 在 natural terminal 已 publish 时为 no-op。 |

---

## 3. 与现有 ADR 的张力点

### 3.1 vs ADR-0186 / 0194 — Session 事实单轨

Coordinator 是 `LiveRunProjection.tail` 的订阅者（read-only），不写 Session。`agent_runtime_init` / `agent_runtime_end` 等 Redis Stream event 是**传输通道**（2 h TTL），不是事实；二者**生命周期不同**：

| 平面 | 寿命 | 写入者 |
|---|---|---|
| Session journal | durable（持久） | `Session.append`（单一入口） |
| Redis Stream | 2 h（传输） | `LcaStreamEventManager.publish` |

不混用：把 init/end 写 Session 会让事实平面承担传输语义；写 Redis 又破坏 Session 单轨。Coordinator 是**两者之间的桥**。

### 3.2 vs ADR-0198 — Observability Compile Graph

`LiveRunProjection` 仍是纯 fold（I-OCG-6）；Coordinator 把 fold 结果送入 transport channel，是 fold **消费者**，不是 fold 实现本身。`replay_projection(id, events)` 与 live fold 共用同一 Plugin 路径，Coordinator 不复制 fold 逻辑。

### 3.3 vs ADR-0195 — 平台三时态

Coordinator 处于 **transport 时态**（observe + emit），不进入 **capability 时态**（副作用执行）或 **fact 时态**（Session 写入）。三者通过 C5 / C7 单向流：`Session` (fact) → `LiveRunProjection` (fold) → `Coordinator` (transport) → `WebSocket` (output)。

### 3.4 vs ADR-0199 — Hermes 启发的入口统一

`create_run` 响应增 `ws_token` 字段（spec §3.1 + §15 Q1）。`ws_token` 是**附属产出**（用于立即握手 WS），不取代 `RunIntent` / `RuntimeFacade.dispatch_run` 的入口语义。`get_running_operation` 是**只读查询**，符合 §2.3「诊断命令默认只读」。

---

## 4. 删除路径（PR-4）

audit 脚本 `scripts/audit_lca_legacy_path.py` 在 CI exit 0 后，下列 pattern 必须**全文检索 0 次**：

| Pattern | 旧角色 | 删除条件 |
|---|---|---|
| `LegacyRunDispatcher` | SSE dispatch 旧入口 | audit script exit 0 |
| `LCA_RUNTIME_FACADE` | env flag 切换 facade | audit script exit 0 |
| `RunUiEncoder` | UI 适配器 | audit script exit 0 |
| `stream_run_live` | SSE 路由 | audit script exit 0 |
| `lcaRunObserve` | front-end SSE 适配 | audit script exit 0 |
| `lcaRunHil` | front-end HIL SSE | audit script exit 0 |
| `lcaJournal` | front-end journal observer | audit script exit 0 |
| `LcaRunDriver` | front-end 模块入口 | audit script exit 0 + `reconcile()` 恢复 4 处 lobehub-ui 源改动并删除 5 个 LCA-only TS 文件 |
| `lcaRunCommand` | front-end command observer | audit script exit 0 |

删除模板（必须填满，无 delete-when = 红灯）：

```text
# COMPAT(owner: ADR-0200, from: <旧入口>, to: <新入口>,
#         delete_when: scripts/audit_lca_legacy_path.py exits 0 in CI,
#         forbidden_new_usage: <禁止新增用法>)
```

---

## 5. 验证矩阵

| 变更 | 最低验证 | 强制追加 |
|---|---|---|
| `lca.contracts.transport` | `ruff check` + 28 tests pass + AST purity check | wire-byte parity tests（camelCase、exclude_none、Literal discriminator） |
| `LcaStreamEventManager` | `ruff check` + 7 L1 tests pass against `127.0.0.1:6379` | TTL ∈ [7100, 7200]、MAXLEN ≤ 1100、xread strict-greater |
| `LcaAgentRuntimeCoordinator` | `ruff check` + L1 tests pass | `tool_state_writer.call_count` before `tool_end` publish、watchdog idempotent guard |
| `LcaAgentGateway` (WebSocketRoute) | starlette `TestClient` 8 L2 tests pass | auth_failed vs auth_expired distinction、heartbeat timing、interrupt path |
| `default_facade.dispatch_run` 切换 | L2 e2e：create_run → ws_token → WS handshake → first event | audit script exit 0 |
| 删除 PR-4 paths | audit script + repo grep | `git grep -nE '(LegacyRunDispatcher\|LCA_RUNTIME_FACADE\|...)' lca/ gateway/ deploy/` returns 0 |

`real_llm` 默认不运行；L4-1（1 h stability smoke）走 nightly。

---

## 6. 风险与拒绝路线

| 风险 | 缓解 |
|---|---|
| `LiveRunProjection.tail` 增加订阅者导致 fold 性能退化 | Coordinator 是 `AsyncIterator` pull 模式，不订阅，只 fold 单条 stamped event；增加成本 O(1) per event。 |
| Redis 单点故障 = WS 不可用 | L3-04 (kernel restart) 测试守护；Coordinator watchdog 仍能在 Redis down 时合成 terminal 事件写 Session（待定，PR-3 验证）。 |
| Front-end TS 镜像改动让 native client 失配 | spec §6.1.2 硬约束：patch 模块只插入 `/* LCA-P1: <purpose> */` marker，不修改 native 导出；`reconcile()` 删除模块即恢复源码。 |
| Pydantic 2.13 discriminated Union 与 `Literal["..."]` 默认值的兼容性 | PR-1 已在 `_WireBase` + 显式 `default = "..."` 中解决；后续任务复用同一 base class。 |
| `LiveRunProjection` 当前 `StampedEvent` schema 与 spec §5.3 fold table 不完全 1:1 | PR-2 Task 4 EventTranslator 显式列出 13 个 handler；新事件需要同时扩 PR-2 handler + closure_catalog（ADR-0198 I-OCG-1）。 |
