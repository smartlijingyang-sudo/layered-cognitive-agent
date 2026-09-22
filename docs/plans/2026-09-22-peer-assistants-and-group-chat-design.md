# 架构设计文档：持久队友、Handoff 委派总线与群聊房间（Peer Assistants & Rooms）

**文档标识**：`docs/plans/2026-09-22-peer-assistants-and-group-chat-design.md`
**对齐契约**：[`ADR-0250`](../adr/0250-peer-assistants-handoff-bus-and-rooms.md)（已落地）
**关联 ADR**：ADR-0042（角色库与自动组队）、ADR-0228（委派子图与类型化端口）、ADR-0232（并发扇出）、ADR-0242（AssistantHome 运行时）
**状态**：Approved by User  
**日期**：2026-09-22  

---

## 1. 摘要与设计动机

在现代多 Agent 交互中，传统“所有人共处同一个 LLM 上下文聊天”的模式存在严重的上下文膨胀、工具日志刷屏、模型幻觉以及无法收敛的缺陷。

本设计吸纳 **Grok Bot**（持久队友 + 异步总线 + 房间）、**Hermes Agent**（子代理强隔离 + 异步非阻塞 + 防上下文污染）、**OpenAI Swarm**（类型化 Handoff 契约）、**Microsoft AutoGen 0.4**（团队模式分流）、**CrewAI**（等级制分工与强制 Fold 汇总）以及 **LobeHub 原生**（Supervisor 动作状态机与 `/group` 路由）6 大主流业界范式，为 LCA 补齐“产品协同壳”：

1. **持久人格队友（Peer Agents）**：通过独立 `AssistantHome` 固化角色人格（首期为“架构三角”：观澜、衡岳、镜川），具备独立的 SOUL、私有记忆命名空间与隔离工作区。
2. **协调者单入口收敛（Coordinator Triage）**：用户默认与协调者交互；协调者负责任务分流，能自行快结的不组队；复合架构任务由 ADR-0042 `TeamCaster` 触发选角。
3. **类型化 Handoff 总线与子任务隔离（Handoff Bus & Anti-Context Pollution）**：任务委派通过严格的不可变信封（`HandoffEnvelope`）异步派发，专家的中间工具长日志停留在沙箱内，回传仅含结构化摘要。
4. **强制 Fold 决策汇总（Fold & Synthesis）**：专家产出必须经由 `delegate.fold` 统一聚合，由协调者做第一人称权威汇报，杜绝打字机抢占。
5. **LobeHub 前端协同体验（M1 垂直切片）**：通过声明式 Patch 在 Run 消息流中挂载“协同成员条（MemberChipsBar）”与“专家折叠产出（FoldedSection）”。

---

## 2. 业界 6 大主流范式调研与吸收矩阵

| 业界产品 | 核心模式 | 核心机制 | LCA 吸收落点 |
|---|---|---|---|
| **Grok Bot** | 协同操作系统 | 持久队友(A) + 房间(B) + 临时工人(C)；异步 Mailbox；协调者压缩汇报 | 吸收三层隔离架构，协调者作为单入口默认收敛 |
| **Hermes Agent** | 子代理沙箱委派 | `delegate_task` 工具；上下文与终端强隔离；异步非阻塞；看板编排 | 吸收**防上下文污染**铁律：中间工具日志不回传主会话，只传摘要 |
| **OpenAI Swarm** | 轻量 Routine 接力 | 转交即工具（Handoff as a Tool）；上下文继承；Triage 分流 | 吸收类型化 Handoff 契约定义与高可观测性 |
| **AutoGen 0.4** | Actor 事件总线 | SelectorGroupChat 动态仲裁；Swarm 模式；防连续发言死锁 | 吸收发言白名单约束与动态选角策略 |
| **CrewAI** | 组织层级与汇总 | Manager Agent 统一调度；角色卡数据化三要素；禁止工人乱委派；强制 Fold | 吸收等级制分工与**终态强制 Fold** 机制 |
| **LobeHub 原生** | 状态机与群路由 | Supervisor 封闭词表（speak / broadcast / delegate）；`agentGroup` 状态树 | 吸收前端 Patch 对齐机制，将后端 TeamSpec 投影到前端 UI |

---

## 3. 架构边界与自治等级（AP-01 & AP-05）

### 3.1 负向清单声明（Does NOT own，AP-01）
* **Owns（本次范围）**：
  1. 领域契约定义：`lca/contracts/models/collaboration/peer.py`；
  2. 架构三角角色卡标准库：`roles/architecture/`（`guanlan.md`、`hengyue.md`、`jingchuan.md`）；
  3. 协调者路由与组队协议：结合 ADR-0042 Auto-casting 与委派信封构造；
  4. LobeHub 前端 Patch：注入协同成员条（MemberChipsBar）与专家折叠面板（FoldedSection）；
  5. 自动化测试套件与不变量断言（8 项断言）。
* **Does NOT own（严格禁止越界）**：
  1. 严禁篡改 L0~L3 核心运行循环：认知六相（Perceive/Think/Act/Reflect/Remember/Stop）闭集不变（C1）；
  2. 严禁直接编辑 `lobehub-ui/` 或 `vendor/` 源码（必须使用 `deploy/lobehub/patches`）；
  3. 严禁开辟第二套事件流，所有状态变更由既有 Reducer 与 `Session.append` 单轨保证（C4/C11）；
  4. 不开放 Agent 间无边界相互自由呼叫（杜绝 Delegation Ping-Pong 死锁）。

### 3.2 自治等级（Autopilot Ladder，AP-05）
* **定级**：**`DRAFT`（契约与草案驱动）**
  - **判定依据**：新增非侵入式的领域契约与角色卡，配合声明式前端补丁，现有单 Agent 会话及所有历史测试 100% 保持原有行为。
  - **门禁要求**：所有新增数据模型必须配置 `extra="forbid"`，补丁必须通过 `patch_lobehub.py verify` 与 `check_patch_integrity.py` 严格校验。

---

## 4. 核心领域契约（Contracts & Models）

契约文件落盘于：`lca/contracts/models/collaboration/peer.py`

```python
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class PeerProfile(BaseModel):
    """持久专家队友规格（映射独立 AssistantHome）"""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    peer_id: str                      # 唯一角色标识，如 "arch_guanlan"
    name: str                         # 角色名称，如 "观澜"
    role: str                         # 职责定位，如 "架构契约与边界总监"
    description: str                  # 职责简述，用于 Caster 语义匹配
    home_namespace: str               # 对应持久化 Home 路径 (~/.lca/assistants/...)
    capabilities: tuple[str, ...]     # 挂载的能力白名单

class HandoffEnvelope(BaseModel):
    """异步委派信封（对齐 ADR-0228 DelegationRequest/Receipt）"""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    correlation_id: str               # 协作批次与关联 Run ID
    sender_id: str                    # 发送方（协调者 ID）
    receiver_id: str                  # 接收方（专家 Peer ID）
    intent: Literal["consult", "delegate", "review", "fold"]
    objective: str                    # 具体子任务目标
    context_slice: dict[str, Any]     # 显式传递的轻量上下文切片（严禁传未压缩历史）
    priority: bool = False            # 是否高优先级唤醒
    timeout_ms: int = 60000           # 超时阈值

class RoomSpec(BaseModel):
    """群聊房间规范（协作 UX 容器）"""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    room_id: str                      # 房间 ID，如 "room_arch_studio"
    display_name: str                 # 房间名称，如 "李超架构室"
    coordinator_agent_id: str         # 协调者 ID
    member_peer_ids: tuple[str, ...]  # 成员专家列表
    shared_topic_id: str              # 共享 Topic
    routing_policy: Literal["coordinator_first", "mention_only"] = "coordinator_first"

class PeerFoldedResult(BaseModel):
    """结构化委派汇总结果（由 delegate.fold 节点生成，ADR-0250）"""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    task_id: str
    member_findings: dict[str, str]   # 各专家回传的精简结论
    synthesized_verdict: str          # 协调者提炼的终审权威结论
    consensus_status: Literal["unanimous", "concerns_noted", "split"]

# 兼容别名（避免与 ADR-0228 既有 FoldedDelegationResult 平行冲突）
FoldedDelegationResult = PeerFoldedResult
```

---

## 5. 架构三角角色卡标准（`roles/architecture/`）

三张标准角色卡采用 Markdown + YAML Frontmatter 格式，严格符合 ADR-0042：

1. **`guanlan.md`（观澜 · 边界与契约总监）**：
   - 核心使命：第一性原理重述、领域模型边界划定、Protocol/Seam 接口严密性、Does NOT own 负向清单守卫。
   - 风格：严谨、直击本质、零废话。
2. **`hengyue.md`（衡岳 · 状态机与不变量总监）**：
   - 核心使命：系统六大分类（事实/状态/决策/许可/回执/投影）判定、Reducer 单写校验、C1~C14 架构不变量捍卫、确定性测试断言规划。
   - 风格：沉稳、滴水不漏、极度重视可追溯性。
3. **`jingchuan.md`（镜川 · 对抗审查与演化审计师）**：
   - 核心使命：反模式库（AP-01~AP-06）逐项核验、死锁/竞态推演、供应链与依赖污染审查、代码工程卫生复核。
   - 风格：敏锐、批判性视角、专注边界破绽与极端情况。

---

## 6. 协调者状态机与运行时拓扑

### 6.1 协调者四向路由判定
1. **日常/单步意图** ➔ 协调者自身直接闭环（Solo）；
2. **单一耗时工具调用** ➔ 调度临时 Subagent（C 层工人），跑完即回收；
3. **单一领域专家提问** ➔ 单点 Handoff 至指定专家；
4. **复合系统架构任务** ➔ 激活 `TeamCaster`，选定架构三角并发委派。

### 6.2 运行时拓扑数据流
```text
[用户输入: 一句话复合架构任务]
   │
   ▼
[协调者 Think] ─── (识别为复合架构任务) ───► [TeamCaster.cast]
   │                                              │
   ▼                                              ▼
[ADR-0228: delegate.compose] ◄──────────── [CastingPlan]
   │
   ├─► HandoffEnvelope #1 ──► [观澜 (Guanlan)]: 专注契约、Seam 与负向边界
   ├─► HandoffEnvelope #2 ──► [衡岳 (Hengyue)]: 专注状态机、不变量与 Reducer 单写
   └─► HandoffEnvelope #3 ──► [镜川 (Jingchuan)]: 专注反模式审查与对抗审计
   │
   ▼
[ADR-0228: delegate.await] (并发收集各专家的 DelegationReceipt)
   │
   ▼
[ADR-0228: delegate.fold] ──► [协调者第一人称提炼] ──► [输出给用户]
```

### 6.3 上下文防污染（Hermes 隔离原则）
- **输入截断**：仅注入任务切片 `context_slice`，不传全量聊天历史；
- **沙箱隔离**：各专家的中间检索与思考日志留存私有日志，不污染主通道；
- **收口输出**：专家回传精炼后的结论 Markdown，由 Fold 聚合为统一结构。

### 6.4 协调者工具面（Coordinator Tool Interface）
- **架构组队工具（`cast_architecture_team`）**：`TeamCastTool` 允许协调者在 Think 阶段以结构化参数发起架构三角并发协同，产出 Folded 聚合结果；
- **单点转交工具（`handoff_to_peer`）**：`HandoffToPeerTool` 允许协调者向指定专家（如 `arch_guanlan`）定向投递 `HandoffEnvelope` 任务信封；
- 模块落盘于 `lca/infrastructure/tools/collaboration/`。

### 6.5 持久化队友工作区物化（Peer Assistant Materializer）
- **模型解析与物化**：`PeerProfileResolver` 从 `roles/architecture/` 解析强类型 `PeerProfile`；
- **真实工作区固化**：`materialize_peer_assistant` 将观澜、衡岳、镜川物化至 `~/.lca/assistants/arch_*`，生成 `SOUL.md`、`USER.md`、`AGENTS.md` 及 `meta.json`；
- 模块落盘于 `lca/application/collaboration/peer_provider.py`。

### 6.6 群聊房间仓储与路由策略（RoomRepository & Router）
- **文件仓储**：`JsonRoomRepository` 支持将 `RoomSpec` 持久化至 `~/.lca/rooms/*.json`，具备完整的 CRUD 与幂等性；
- **路由策略引擎**：`RoomMessageRouter` 实现确定性路由判定：
  - `coordinator_first`：默认由协调者单入口收敛，仅当出现 `@专家` 时路由至对应专家；
  - `mention_only`：严格按点名白名单转发；
- 模块落盘于 `lca/domain/collaboration/room.py`。

---

## 7. 前端 LobeHub Patch 交互设计

采用声明式补丁挂载于 `deploy/lobehub/patches/ui/`：

1. **协同成员条（`MemberChipsBar`）**：
   - 位于消息气泡顶部，展示当前参与该任务的专家芯片：`[观澜 · 边界与契约] [衡岳 · 状态机与不变量] [镜川 · 对抗审计]`；
   - 具备运行状态标识（`已收敛汇总`）。
2. **专家产出折叠区（`FoldedAgentSection`）**：
   - 紧随成员条下方，采用 Ant Design `<Collapse>` 组件提供观澜、衡岳、镜川各专家的独立分析折叠卡片；
   - 支持用户按需展开查看原始沙箱审计论据，兼顾极简体验与审计追溯；
   - 保持补丁与 LobeHub 上游代码隔离，严禁直接篡改 `lobehub-ui/` 源码（AP-01）。

---

## 8. 容错、降级与幂等策略（AGENTS.md §1 第 6 问）

1. **选角异常降级**：若 `TeamCaster` 选角受阻，重试一次后平滑降级为协调者单人执行，不中断会话；
2. **单专家超时容忍**：专家响应超 60s 截断，Receipt 标为 `timeout`，Fold 节点基于已就绪专家的结论收敛，并在汇报中如实说明；
3. **单点错误隔离**：单专家执行报错被捕获，不导致整批协同任务崩溃；
4. **幂等查重**：`correlation_id` + `idempotency_key` 双重防重，重试请求直接复用已生成的 Receipt。

---

## 9. 自动化测试断言矩阵（AP-02）

所有架构声明必须在单元测试中具备确定性验证：

| 编号 | 测试用例 | 验证要点与不变量断言 |
|---|---|---|
| **T1** | `test_peer_collaboration_contracts.py` | 断言 `PeerProfile`、`HandoffEnvelope`、`RoomSpec` 继承不可变性且严格禁止额外字段（`extra="forbid"`） |
| **T2** | `test_architecture_triad_roles.py` | 静态扫描 `roles/architecture/`，断言观澜、衡岳、镜川的 YAML frontmatter 完整性及能力白名单符合 ADR-0042 |
| **T3** | `test_coordinator_triage.py` | 验证协调者路由状态机：单步任务走 Solo，复合架构任务精准触发架构三角组队 |
| **T4** | `test_anti_context_pollution.py` | 模拟长工具调用，断言协调者与主会话收到的上下文完全无工具日志噪音（Hermes 隔离断言） |
| **T5** | `test_delegation_fold.py` | 模拟 3 专家并发回传，断言 `delegate.fold` 聚合出的 `FoldedDelegationResult` 具备唯一性与共识判定 |
| **T6** | `test_fault_tolerance_timeout.py` | 模拟单专家超时与部分失败，断言系统优雅降级，Fold 节点如实反馈部分可用状态 |
| **T7** | `test_collaboration_ui_patch.py` | 校验 LobeHub 前端补丁：`patch_lobehub.py verify` 退出码为 0，`check_patch_integrity.py` 82/82 保持 byte-identical |
| **T8** | `test_negative_boundaries.py` | 守护 AP-01 负向边界：断言 L0~L3 核心运行循环、6 阶段目录未被意外修改 |
