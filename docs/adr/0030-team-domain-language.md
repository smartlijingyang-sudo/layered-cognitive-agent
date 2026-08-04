# ADR-0030: Team 领域语言（Lead / Coordination）

## 状态
Accepted

## 背景
Recipe / TeamProcess / SupervisorMode / Family / Plane 叠层导致认知与维护成本过高。

## 决定
1. 公共面仅 **Agent / Team / TeamLead / LeadMandate / Coordination 类型**。
2. `Team = members + (lead XOR coordination)`，构造期闭集。
3. `LeadMandate`: routing | consult | board；gate 仅由 mandate 展开。
4. 组合根：`AgentComposer` / `TeamComposer`；删除 `Assembly` / `MultiAgentTeam` / `TeamProcess` / `Recipe` / `SupervisorMode` 公共面。
5. 策略注册键：`pipeline` / `fan_out` / `lead` / `peer_relay` / `peer_swarm` / `debate` / `graph`。

## 后果
- 正面：一元领域语言，非法组合不可表达。
- 负面：breaking change，无 shim。

## 相关
- Supersedes 用户面叙事：此前的三维旋钮（Family / Plane / Mode）与 Recipe/Mode 公共模型。
- Keeps：封闭对象图、send_and_wait、delegations、单 session 槽。
