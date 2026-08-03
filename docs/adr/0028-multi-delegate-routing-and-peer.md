# ADR-0028: Multi-delegate、Routing plane、Peer/Swarm

## 状态
Accepted

## 背景

ADR-0027 预留了业界插槽。本 ADR 填入三块能力：

1. **Multi-delegate**：SUPERVISOR 一步并行委派多个角色  
2. **Routing plane**：自由 PM，无全员结算不变量  
3. **Peer/Swarm**：PEER 族从 choreography 宿主迁出，并提升 `swarm` process  

## 决定

### Multi-delegate

- `Decision.delegate_targets: list[DelegationSpec]`；`iter_delegation_specs()` 归一化  
- `DelegateOperation`：`len==1` 原路径；`>1` 先全部 `send_task` 再 `gather` wait  
- 每目标独立 `update_member_status_for_spec`  
- `MustConsultAllMembers`：多 waiting 时 shortcut/enforce 可 fan-out 全部等待角色  
- Parser 识别 `delegate_targets` / `delegates` JSON  

### Routing plane

- 新类型 `RoutingState`（白名单：teammates / assigned_roles / notes）  
- `RunContext.routing` / `AgentState.routing`  
- `HierarchicalStrategy` 按 `TeamConfig.supervisor_plane` 注入 consultation 或 routing  
- ROUTING **禁止** settlement gate（`must_consult_all` 等）  
- `SupervisorReasoner` 双模板：`hierarchical_prompt` | `routing_prompt`  
- 委派成功后 `record_routing_assignment` 软记录已问角色  

### Peer family

- 新 `PeerStrategy(mode=handoff|swarm)`  
- `TeamProcess.HANDOFF` / `SWARM` 注册到 PeerStrategy  
- `ChoreographyStrategy` 仅 sequential / parallel / debate  
- Swarm：round-robin + 上下文累积，首个 COMPLETED 且有 output 即返回  

## 后果

- 默认 hierarchical 仍是 consultation + gate none（自由）  
- 合规咨询：plane=consultation + must_consult_all（现可一轮并行问完）  
- 动态 PM：plane=routing  
- 对等：process=handoff | swarm  

## 关系

- 落实 ADR-0027 插槽  
- 不削弱 ADR-0026 Consultation 白名单  
