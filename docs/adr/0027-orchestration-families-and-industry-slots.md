# ADR-0027: 编排族（Orchestration Family）与业界模式插槽

## 状态
Accepted

## 背景

LCA 已有六种 `TeamProcess`，且 ADR-0026 把 hierarchical 的控制面收敛为
`ConsultationState`。但对外叙事仍容易把 **全员咨询结算** 误读成业界通用的
**动态 Supervisor / Swarm / Pipeline**。

业界（CrewAI / LangGraph / AutoGen / Swarm 系）在概念上普遍分族，而不是
一个大 process 字符串：

| 族 | 控制权 | 代表 |
|---|---|---|
| Supervisor / Orchestrator–Worker | 中心 agent 推理调度 | Crew hierarchical、LangGraph supervisor、subagents-as-tools |
| Choreography / Pipeline | 代码拓扑推进 | sequential、parallel fan-out |
| Peer / Swarm | 对等 handoff | OpenAI Swarm、peer transfer |
| Graph | 显式状态机 / DAG | LangGraph 任意图 |

若不在 **语义 / 架构 / 框架** 三层显式预留插槽，后续补“动态 PM、并行
fan-out、纯 swarm”时会再次污染 `ConsultationState` 或 `SimpleReasoner`。

## 决定

### 1. 语义层：四族 + process 是族内具体拓扑

引入 `OrchestrationFamily`（contracts）：

| Family | 含义 | 当前 TeamProcess |
|---|---|---|
| `SUPERVISOR` | 中心 agent 拥有调度裁量 | `hierarchical` |
| `CHOREOGRAPHY` | 策略代码驱动成员调用 | `sequential` / `parallel` / `debate` |
| `PEER` | 控制权在成员间转移 | `handoff`（实现上暂挂 choreography 策略，语义归 PEER） |
| `GRAPH` | 显式图执行 | `graph` |

规则：

- **新 process 必须声明所属 Family**（`PROCESS_FAMILY` 映射 + CI 可测）。
- **Family 决定控制面放哪**；process 只决定族内拓扑细节。
- 业界对照表维护在 `lca/contracts/orchestration_taxonomy.py` 与本 ADR，
  不散落在实现注释里。

### 2. 架构层：控制面类型按 Family 隔离（延续 ADR-0026）

| Family | 控制面 / Session | 禁止 |
|---|---|---|
| SUPERVISOR · consultation | `ConsultationState`（白名单锁定） | 塞 debate/graph/swarm 字段 |
| SUPERVISOR · routing | `RoutingState`（独立类型，已实现） | 扩 `ConsultationState` 白名单冒充 |
| CHOREOGRAPHY | strategy-local / 无 agent session | 往 `AgentState.consultation` 写 |
| PEER | 未来 `PeerSession` 或 handoff 链状态 | 与 consultation 混用 |
| GRAPH | graph cursor / `ExecutionGraph` 运行态 | 塞进 Consultation |

`RunContext` 只承载 **调用元数据** + **当前已实现的可选 session 字段**
（今日仅 `consultation`）。新 session = 新可选字段或新 typed 容器，
**禁止** `extra` 垃圾袋。

### 3. 框架层：三维旋钮，而不是把语义塞进 process 名

团队行为由正交维度组合（已有 + 预留）：

| 维度 | 配置点 | 业界对应 |
|---|---|---|
| **Process / Family** | `TeamConfig.process` → Strategy 注册表 | Crew Process / LangGraph 模板 |
| **Settlement / Gate** | `TeamConfig.decision_gate` | 强不变量 vs 自由路由 |
| **Transport** | `DelegationProtocol` + TransportRegistry | internal / A2A / MCP |
| **Supervisor plane** | `SupervisorPlane` | consultation vs free routing |
| **Invoke shape** | `Decision.delegations`（0/1/N）+ `send_and_wait` | 并行 subagents |

默认对齐业界自由 supervisor：

- `decision_gate` 默认 **`none`**（LLM 裁量；结算机显式打开）
- 需要“全员必询”时显式 `must_consult_all`（consultation 产品形态）

扩展纪律（硬）：

1. **新 TeamProcess** → 新 `TeamProcessStrategy` 类 + registry 注册 + 更新
   `PROCESS_FAMILY`；禁止在已有 strategy 里堆 if/elif 拓扑。
2. **新 SUPERVISOR 语义**（routing / nested manager）→ 新 Session 类型 +
   可选新 process 或 `SupervisorPlane`；**禁止**改 Consultation 白名单装无关字段。
3. **新 Gate** → `DecisionGateName` + `ComponentKind.DECISION_GATE` 注册；
   不进 Reasoner 分支。
4. **并行 / multi-delegate** → 先扩 `Decision` / `DelegateOperation` 契约，
   再改 strategy；不把 fan-out 逻辑写进 `ModularBrain`。
5. **Solo / member 默认脑** 保持 team-agnostic（ADR-0026）；
   supervisor 认知仅组装期 `SupervisorBinder` 安装。

### 4. 预留插槽（有名无实现，防止占坑乱写）

`RESERVED_PROCESS_SLOTS`（字符串名，未进 `TeamProcess` 枚举直至实现）：

| 预留名 | Family | 意图 | Session |
|---|---|---|---|
| `supervisor_routing` | SUPERVISOR | 动态 PM，可跳过角色、无全员不变量 | `RoutingState`（未实现） |
| `swarm` | PEER | 纯对等 handoff mesh | `PeerSession`（未实现） |
| `consensus` | CHOREOGRAPHY 或 PEER | 合意/投票式收尾 | strategy-local |

`SupervisorPlane` 枚举：

| 值 | 状态 |
|---|---|
| `consultation` | **已实现**（当前 hierarchical 默认 plane） |
| `routing` | **已实现**（`RoutingState` + plane=ROUTING + gate none） |

实现某预留名时：升为 `TeamProcess` 成员、注册 strategy、补映射与测试，
并更新本 ADR 后果表。

### 5. 业界模式 → LCA 插槽映射（查阅表）

| 业界模式 | LCA Family | 推荐配置 | 今日成熟度 |
|---|---|---|---|
| Crew sequential | CHOREOGRAPHY | `process=sequential` | 已实现 |
| Crew hierarchical（自由经理） | SUPERVISOR | `hierarchical` + `decision_gate=none` | 已实现（gate 默认 none） |
| Crew hierarchical（强制全员） | SUPERVISOR | `hierarchical` + `must_consult_all` | 已实现 |
| LangGraph supervisor node | SUPERVISOR | 同上；multi-delegate via `delegations` | 已实现 |
| LangGraph subagents-as-tools | SUPERVISOR | DELEGATE / Transport | 已实现（阻塞） |
| parallel scatter-gather | CHOREOGRAPHY | `process=parallel` | 已实现 |
| Swarm peer handoff | PEER | `process=handoff` / `process=swarm` | 已实现 |
| 任意 DAG | GRAPH | `process=graph` + `execution_graph=` | 已实现 |
| nested supervisors | SUPERVISOR | 未来嵌套 TeamUnit / subgraph | 未实现（插槽：routing + graph） |

## 放弃的方案

- **单一 process 万能字符串 + 大 if**：已在 ADR-0006/0024 否决。
- **ConsultationState 变成通用 TeamSession 垃圾袋**：ADR-0026 否决；本 ADR 重申。
- **为预留名提前注册 NotImplemented strategy**：增加用户踩坑；仅 taxonomy 占名。
- **用 LangGraph 替换全部 process**：GRAPH 是族之一，不吞掉 SUPERVISOR/CHOREOGRAPHY 语义。

## 后果

- **正面**：
  - 语义上能回答“我们支持业界哪种模式、差哪一刀”
  - 架构上控制面按族隔离，扩展有落点
  - 框架上 gate / process / plane / transport 正交，默认贴近自由 supervisor
- **负面 / 迁移**：
  - `decision_gate` 默认从 `must_consult_all` 改为 `none`：依赖隐式全员结算的调用方须显式打开
  - `handoff` / `swarm` 已迁至独立 PEER strategy 类（见 ADR-0028 cleanup）
- **与既有 ADR**：
  - 延续 ADR-0006 的 process 可插拔
  - 强化 ADR-0026 的 session 隔离
  - 不改变 ADR-0002 认知环

## 落地清单（本 ADR 同期）

1. `lca/contracts/orchestration_taxonomy.py`：Family、映射、预留槽、业界对照常量
2. `TeamConfig.decision_gate` 默认 `none`；L4 API 透出 `decision_gate`
3. 场景 YAML 中 consultation 用例显式 `decision_gate: must_consult_all`
4. glossary + 本索引更新
5. 测试：process↔family 全覆盖；预留名不与现网 process 冲突
