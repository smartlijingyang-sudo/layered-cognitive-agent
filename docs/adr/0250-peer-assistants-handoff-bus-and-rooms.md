# ADR-0250 — 持久队友、Handoff 委派总线与群聊房间（Peer Assistants, Handoff Bus & Multi-Agent Rooms）

## 状态

**Implemented (M1 垂直切片) / Planned (M2 生产化) — 2026-09-22**

Refines:
- [ADR-0042](0042-role-library-and-auto-casting.md)（角色库与声明式自动组队）；
- [ADR-0228](0228-plan-intervene-delegate-subgraphs.md)（委派子图与类型化端口）；
- [ADR-0232](0232-concurrent-fan-out-and-aggregation.md)（并发扇出与收集）；
- [ADR-0242](0242-assistant-home-runtime.md)（AssistantHome 真实持久化与隔离命名空间）。

Related seams（挂缝，不另起平行 Runtime）：
- `lca/contracts/models/collaboration/`：领域不可变契约（`PeerProfile`, `HandoffEnvelope`, `RoomSpec`, `PeerFoldedResult`）；
- `roles/architecture/`：标准专家角色卡（观澜、衡岳、镜川）；
- `lca/application/collaboration/`：协调者分流路由（`CoordinatorTriageRouter`）与 Fold 聚合（`DelegationFoldAggregator`）；
- `lca/infrastructure/collaboration/`：房间仓储（`JsonRoomRepository`）与路由策略；
- `deploy/lobehub/patches/ui/`：协同成员条与折叠面板观察面投影；
- `Session.append`：唯一事件真值轨（ADR-0186）。

---

## 0. 决策摘要

传统“所有 Agent 共处同一聊天上下文相互交谈”的群聊模式，必然导致严重的上下文膨胀、工具日志刷屏、死锁竞争以及无法权威收敛的缺陷。

LCA 确立**“持久队友人格（Peer Assistants）+ 协调者单入口收敛（Coordinator Triage）+ 类型化 Handoff 总线（Handoff Bus）+ 终态强制 Fold 汇总（Mandatory Fold）+ 群聊房间 UX（Rooms）”**的现代多 Agent 协同架构：

1. **持久人格队友（Peer Assistants）**：每个专家不是临时 Prompt 堆叠，而是由独立 `AssistantHome` 固化的持久 Agent（首期“架构三角”：观澜、衡岳、镜川），具备独立的 SOUL、私有记忆命名空间与物理隔离工作区；
2. **协调者单入口收敛（Coordinator Triage）**：日常与单步意图默认由协调者自身闭环（SOLO），杜绝无节制打扰专家；复合任务由 Caster 算法触发组队分流；
3. **类型化 Handoff 委派总线（Handoff Bus）**：委派行为遵循严格不可变的 `HandoffEnvelope` 契约，以任务切片（Context Slice）传输，杜绝原始长文本直接倾倒；
4. **Hermes 防上下文污染隔离（Anti-Context Pollution）**：专家执行子任务时的中间 Shell/文件/调试工具原始日志严格截留在专家本地执行沙箱内，回传主通道的仅为结构化分析摘要；
5. **CrewAI 终态强制 Fold 决策汇总（Mandatory Fold）**：多专家产出必须经由聚合器清洗提炼为 `PeerFoldedResult`，由协调者以第一人称输出权威汇报，禁止打字机抢占；
6. **群聊房间规范（RoomSpec）**：提供房间规范与路由策略（`coordinator_first` 与 `mention_only`），支持多 Agent 协同 UX 容器持久化。

---

## 1. 第一性原理与问题边界

### 1.1 协同的三大不可违背边界

| 边界 | 要回答的问题 | LCA 权威位置 |
|---|---|---|
| **人格与自治边界** | 专家的专业领域、工具权限与记忆归谁所有？ | 独立 `AssistantHome` 与 `RoleCard` 契约（ADR-0242） |
| **信道与防污染边界** | 中间繁琐的工具调用日志是否回流主会话？ | 严禁回流；Hermes 强隔离沙箱，仅传摘要切片 |
| **权威收敛边界** | 最终决策谁拥有？由谁向用户负责？ | 协调者经 Fold 聚合后的权威终审，单写 Reducer（C4） |

### 1.2 本 ADR 负责与不负责

* **本 ADR 负责**：
  - 定义持久专家（PeerProfile）、委派信封（HandoffEnvelope）、群聊房间（RoomSpec）及聚合结果（PeerFoldedResult）的领域模型；
  - 确立协调者分流判定、架构三角标准角色卡及防污染聚合标准；
  - 规范多 Agent 协同在 LobeHub 前端 Run 界面与房间视图中的投影规范。
* **本 ADR 不负责**：
  - 严禁篡改 L0~L3 核心调度循环：认知六相（Perceive/Think/Act/Reflect/Remember/Stop）闭集不变（C1）；
  - 不开放 Agent 间无边界网状乱序自由呼叫（杜绝 Delegation Ping-Pong 死锁）；
  - 不开辟第二套事件流，所有状态变更必须由既有 `Session.append` 单轨保证（C4/C11）。

---

## 2. 业界 6 大主流范式与吸收落点

| 业界产品 | 核心模式 | 核心机制 | LCA 吸收落点 |
|---|---|---|---|
| **Grok Bot** | 协同操作系统 | 持久队友 + 房间容器 + 异步 Mailbox；协调者压缩汇报 | 吸收三层隔离架构，协调者作为单入口默认收敛 |
| **Hermes Agent** | 子代理沙箱委派 | `delegate_task` 工具；上下文与终端强隔离；异步非阻塞 | 吸收**防上下文污染**铁律：中间工具日志不回传主会话，只传摘要 |
| **OpenAI Swarm** | 轻量 Routine 接力 | 转交即工具（Handoff as a Tool）；上下文继承；Triage 分流 | 吸收类型化 Handoff 契约定义与高可观测性 |
| **AutoGen 0.4** | Actor 事件总线 | SelectorGroupChat 动态仲裁；Swarm 模式；防连续发言死锁 | 吸收发言白名单约束与动态选角策略 |
| **CrewAI** | 组织层级与汇总 | Manager Agent 统一调度；角色卡数据化三要素；禁止乱委派；强制 Fold | 吸收等级制分工与**终态强制 Fold** 机制 |
| **LobeHub 原生** | 状态机与群路由 | Supervisor 封闭词表（speak / broadcast / delegate）；`agentGroup` 状态树 | 吸收前端 Patch 对齐机制，将后端 TeamSpec 投影到前端 UI |

---

## 3. 核心领域契约（Contracts）

数据模型落盘于 `lca/contracts/models/collaboration/peer.py`，必须配置 `ConfigDict(frozen=True, extra="forbid")`：

1. **`PeerProfile`**：描述持久人格队友属性（映射独立 `AssistantHome` 路径与能力白名单）；
2. **`HandoffEnvelope`**：承载异步转交信封（含 correlation_id、sender_id、receiver_id、intent、objective、context_slice 与超时设置）；
3. **`RoomSpec`**：群聊房间 UX 容器（含 room_id、display_name、coordinator_agent_id、member_peer_ids、shared_topic_id 与 routing_policy）；
4. **`PeerFoldedResult`**（兼容别名 `FoldedDelegationResult`）：聚合各专家经清洗后的 member_findings 与 synthesized_verdict，显式标记 consensus_status（`unanimous` / `concerns_noted` / `split`）。

---

## 4. 架构三角角色卡标准（Roles Triad）

架构三角作为 LCA 核心持久队友示范，严格遵循 ADR-0042 分布于 `roles/architecture/`：

1. **观澜（`guanlan.md` · 架构契约与边界总监）**：第一性原理重述、领域契约划定、Does NOT own 负向清单守卫；
2. **衡岳（`hengyue.md` · 状态机与不变量总监）**：事实/状态/决策/许可/回执/投影六大分类判定、Reducer 单写校验、C1~C14 架构不变量捍卫；
3. **镜川（`jingchuan.md` · 对抗审查与反模式审计师）**：AP-01~AP-06 反模式深度审计、并发死锁推演、代码工程卫生复核。

---

## 5. 容错、降级与幂等策略

1. **单点超时容忍**：专家响应超 60s 触发截断，回传带 `[TIMEOUT]` 标记，Fold 聚合器自动将共识降级为 `concerns_noted`，并在终审汇报中明示；
2. **执行异常隔离**：单专家报错带 `[ERROR]` 标记，不中断其他专家分析，Fold 聚合器如实呈现；
3. **路由幂等性**：`correlation_id` 确保多次重复委派命中同一批次，不产生游离任务。

---

## 6. 验证矩阵与守护不变量

| 验证维度 | 对应测试 | 守护不变量 |
|---|---|---|
| 模型不可变与字段禁止 | `tests/contracts/test_peer_collaboration_contracts.py` | C13 typed Contract, extra="forbid" |
| 角色卡与部门映射 | `tests/roles/test_architecture_triad_roles.py` | ADR-0042 规范 |
| 协调者分流与 SOLO 收敛 | `tests/collaboration/test_coordinator_triage.py` | 单入口收敛原则 |
| Hermes 防上下文污染 | `tests/collaboration/test_anti_context_pollution.py` | 防上下文膨胀 |
| 强制 Fold 与共识判定 | `tests/collaboration/test_delegation_fold.py` | CrewAI 强制收敛 |
| 房间仓储与路由策略 | `tests/collaboration/test_room_repository_and_routing.py` | 确定性路由 C8 |
| 全链路回归与负边界 | `tests/collaboration/test_group_chat_e2e.py` | AP-01 Does NOT own 守卫 |
