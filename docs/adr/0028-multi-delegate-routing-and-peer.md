# ADR-0028: Multi-delegate、Routing plane、Peer/Swarm

## 状态
Accepted（2026 cleanup: single `delegations` field + typed peer strategies）

## 背景

ADR-0027 预留了业界插槽。本 ADR 填入三块能力：

1. **Multi-delegate**：SUPERVISOR 一步并行委派多个角色  
2. **Routing plane**：自由 PM，无全员结算不变量  
3. **Peer/Swarm**：PEER 族独立 strategy 类型  

## 决定

### Multi-delegate

- `Decision.delegations: list[DelegationSpec]` 是唯一委派表示（0 / 1 / N）
- `DelegateOperation`：`len==1` 单目标；`>1` fan-out gather；均经 `send_and_wait`
- 每目标独立 `update_member_status_for_spec`
- `MustConsultAllMembers`：多 waiting 时 shortcut/enforce 可 fan-out 全部等待角色
- Parser 识别 JSON `delegations` 列表，或 flat `target_role` + `subtask`

### Routing plane

- 类型 `RoutingState`（白名单：teammates / assigned_roles / notes）
- `RunContext.routing` / `AgentState.routing`
- `HierarchicalStrategy` 按 `TeamConfig.supervisor_plane` 注入 consultation 或 routing
- ROUTING **禁止** settlement gate（`must_consult_all` 等）
- `SupervisorReasoner` 双模板：`hierarchical_prompt` | `routing_prompt`
- 委派成功后 `record_routing_assignment` 软记录已问角色

### Peer family

- `HandoffStrategy` / `SwarmStrategy` 各自独立类（无字符串 mode 表）
- `TeamProcess.HANDOFF` / `SWARM` 分别注册
- 与 `ActionType.HANDOFF`（非阻塞 body 动作）语义分离
- Swarm：round-robin + 上下文累积，首个 COMPLETED 且有 output 即返回

### 成员调用单端口

- `lca.layer0_infra.transport.invocation.send_and_wait` 为 Observation 级统一入口
- `member_invoke.invoke_member` 与 body DELEGATE 均经 transport，无本地 bypass

## 后果

- 删除 `delegate_to` / `delegate_targets` 双写与 `iter_delegation_specs`
- GRAPH 通过 `execution_graph=` 接入公共 API；无死 `graph_definition_ref`
