# ADR-0029: 封闭对象图 + SupervisorMode 闭集 + 组合权在 L4

## 状态
Accepted

## 背景
SUPERVISOR 路径依赖「先 `assemble_agent` 半成品，再 `SupervisorBinder.bind` 回写 channel/gate/reasoner」的两阶段生命周期，并产生 `install_*` / `bind_*` / 组装用 `Has*` Protocol 等偶然复杂度。用户面 `decision_gate × supervisor_plane` 自由积含非法组合。

## 决定
1. **封闭对象图**：`run()` 前 Brain/Body/Memory/Transport 拓扑不可变；废除公共 `bind_channel` / `bind_shared_memory` / `install_decision_gate` / 运行期替换 reasoner。
2. **SupervisorMode 闭集**：`ROUTING` | `CONSULTATION` | `BOARD`；gate 仅作 registry 键由 Mode 展开。
3. **Recipe**（L-User）：`pipeline` / `fanout` / `manager` / `consult` / `board` / … 展开为 process + mode。
4. **组合只在 L4**：`Assembly.recompose_as_supervisor` / `recompose_member` **新建**实例；`TeamOrchestrator` 纯句柄。
5. **`RunContext` / `AgentState` 单槽 `session`**：`ConsultationState | RoutingState`；禁止双字段平铺。
6. **ActionScope**：SOLO/MEMBER 无 DELEGATE；SUPERVISOR 含 DELEGATE/HANDOFF。
7. **删除** `SupervisorBinder` 与组装 mutation Protocol。

## 后果
- 正面：生命周期一致、非法配置不可表达、扩展面无 mutation 插槽。
- 负面：breaking change；team 内 supervisor 与原料 Agent 为不同实例。

## 相关
- 废止 ADR-0026 中 Binder patch 字面做法；保留 ConsultationState / SupervisorReasoner 精神。
- 修正 ADR-0027 用户旋钮叙事为 Mode/Recipe。
