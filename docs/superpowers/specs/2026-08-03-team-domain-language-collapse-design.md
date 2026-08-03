# Design: Team 领域语言坍缩（可破兼容）

**状态**: **IMPLEMENTED** — 可破兼容已落地（无 shim）  


**日期**: 2026-08-03  
**兼容策略**: **可破兼容**（无 shim、无 deprecated 双轨）  
**范围**: 团队编排公共词汇、构造 API、配置/YAML、L4 组合根命名、策略注册键；**不**重写认知环、LLM、传输协议语义  

### 锁定决策

| # | 决策 |
|---|------|
| D1 | 兼容策略：可破 · 无 shim · 全量迁移测试/YAML/文档 |
| D2 | 公共词汇走 **领域语言**，禁止 meta 叠词（Recipe/Process/Pattern/Mode/Family/Plane） |
| D3 | 协作方式 **真组合**：`Team` = `members` +（`lead: TeamLead` **异或** `coordination: Coordination`） |
| D4 | 有主导者语义用 **`TeamLead` + `LeadMandate`**，不用 Supervisor*/managed/hierarchical |
| D5 | 无主导者语义用 **`Coordination` 具体类型**（Pipeline / FanOut / …），不用大杂烩枚举 |
| D6 | 封闭对象图与单端口 `send_and_wait`、唯一 `Decision.delegations` **继承并保留** |
| D7 | 组合根实现者名：**AgentComposer / TeamComposer**（取代 Assembly 公共叙事） |
| D8 | 门面类：**Team**（删除 `MultiAgentTeam`，无 alias） |

---

## 0. 为何再动刀

上一轮（elegance cutover / ADR-0029）修了 **封闭对象图** 与 **非法 gate×plane**，但公共面仍是化石叠层：

```
Recipe ≈ Process ≈ Family 切片
SupervisorMode ≈ Plane × Gate 闭集
Assembly 混进「怎么协作」的叙事
```

结果：认知成本高、文档与 API 双入口、名不达意。  
本设计唯一标准：

> **领域里怎么说，API 就怎么写；合法协作可组合且不可非法表达；实现分类学不准泄漏到用户面。**

---

## 1. 通用语言（Ubiquitous Language）

以下词汇是 **唯一** 公共团队语义。每个词必须经得起「它在现实协作里指什么」的追问。

### 1.1 核心名物

| 术语 | 定义 | 边界 |
|------|------|------|
| **Agent** | 具备角色与目标的单体行动者，可独立 `run(task)` | 不含「如何与队友协作」 |
| **Team** | 多个 Agent 为同一 objective 协作的单位，可 `run(objective)` | 恰好绑定一种协作机制 |
| **TeamLead** | Team 内被授予 **派活与收口裁量** 的主导 Agent 及其授权形态 | 不是运维 Supervisor；不是任意 member |
| **LeadMandate** | TeamLead 行使主导权时的 **授权与义务闭集** | 不是「性格/风格」装饰词 |
| **Coordination** | **无 TeamLead** 时，成员任务如何推进的机制 | 与 TeamLead 互斥 |
| **Delegation** | Lead（或未来对等体）向成员交付子任务的行为；数据上仅 `Decision.delegations` | 不是 Team 级构造参数 |

### 1.2 为何不用旧词（推敲记录）

| 旧词 | 弃用理由 |
|------|----------|
| Recipe | 厨子隐喻，非领域；与 Process 同义叠床 |
| Process | 被「业务流程 / OS 进程」污染；且与实现 Strategy 键纠缠 |
| Pattern | 设计模式元语言，用户要的是「怎么协作」不是「哪个 pattern」 |
| Supervisor / SupervisorMode | 与监控 Supervisor 撞车；Mode 暗示随意旋钮 |
| Hierarchical | 描述结构形容词，不是协作机制名 |
| managed | 含糊（谁 managed？） |
| Family / Plane | 扩展作者分类学，不是产品语义 |
| Assembly | 对象图工厂，不是协作概念；不应出现在 team 入门叙事 |
| Handoff（作 Team 模式名） | 与 `ActionType.HANDOFF` 撞车 |

### 1.3 LeadMandate 用词推敲

不用 **Style**（易被读成外观/语气）。用 **Mandate（授权/职权范围）**：

| LeadMandate | 领域含义 | 内部展开（用户不可见） |
|-------------|----------|------------------------|
| **ROUTING** | 主导者可自由分派，**无**「必须问完所有人」的义务 | `RoutingState`；无 settlement gate |
| **CONSULT** | 主导者面对 **固定名单**，可参考状态板，**不**强制全员结算 | `ConsultationState`；gate=none |
| **BOARD** | 主导者面对名单，且 **必须全员咨询结算** 后方可最终收口 | `ConsultationState` + `must_consult_all` |

三种是 **三种授权**，不是「一种 hierarchical 加旋钮」。

### 1.4 Coordination 具体类型（名即拓扑）

| 类型 | 领域含义 | 旧对应 |
|------|----------|--------|
| **Pipeline** | 成员按序接力；前者产出成为后者任务 | sequential / pipeline recipe |
| **FanOut** | 成员并行处理同一 objective；可后置汇总 | parallel / fanout |
| **PeerRelay** | 平级顺序尝试；**先完成者**结果胜出（不链式传产出） | handoff process / relay |
| **PeerSwarm** | 平级轮转改进，直至成功或轮次耗尽 | swarm |
| **Debate** | 成员多轮交锋/修订直至轮次或收敛规则 | debate |
| **Graph** | 按显式 DAG 推进（含条件边/并行边/聚合） | graph + execution_graph |

前缀 **Peer\***：标明控制权在成员间/策略间，**不在** TeamLead。  
**Relay** 避开 Action 级 HANDOFF 歧义。

---

## 2. 组合模型（构造期闭集）

### 2.1 不变量

```text
Team 合法态 =
  members: NonEmpty[Agent]  ∪  恰好其一:
    (1) lead: TeamLead
    (2) coordination: Coordination
```

- `lead` 与 `coordination` **同时出现** → `ValueError`  
- **皆无** → `ValueError`  
- `lead` 存在 ⇒ 成员经 transport 被 lead 的 DELEGATE 调用；策略为 Lead 路径  
- `coordination` 存在 ⇒ 策略代码/图推进；**无** lead session  

### 2.2 公共 API 草图

```python
from lca import Agent, Team, TeamLead, LeadMandate
from lca import Pipeline, FanOut, PeerRelay, PeerSwarm, Debate, Graph

# —— 有主导者 ——
team = Team(
    members=[researcher, writer],
    lead=TeamLead(pm, LeadMandate.BOARD),
)
team = Team(members=[...], lead=TeamLead.board(pm))
team = Team(members=[...], lead=TeamLead.routing(pm))
team = Team(members=[...], lead=TeamLead.consult(pm))

# —— 无主导者 ——
team = Team(members=[a, b, c], coordination=Pipeline())
team = Team(members=[a, b], coordination=FanOut())
team = Team(members=[a, b], coordination=PeerRelay())
team = Team(members=[a, b], coordination=PeerSwarm(max_rounds=5))
team = Team(members=[a, b], coordination=Debate(max_rounds=3))
team = Team(members=[...], coordination=Graph(execution_graph=dag))

# 语法糖（仍落到同一模型，非第二套语义）
Team.pipeline(a, b, c)
Team.fan_out(a, b)
Team.peer_swarm(a, b, max_rounds=5)
Team.graph(members, execution_graph=dag)
Team.with_lead(TeamLead.board(pm), members=[a, b])

result = await team.run("objective")
```

### 2.3 TeamLead

```python
class LeadMandate(str, Enum):
    ROUTING = "routing"
    CONSULT = "consult"
    BOARD = "board"


class TeamLead:
    """Team 的主导者：原料 Agent + 职权 Mandate。"""

    def __init__(self, agent: Agent, mandate: LeadMandate) -> None: ...

    @classmethod
    def routing(cls, agent: Agent) -> TeamLead: ...
    @classmethod
    def consult(cls, agent: Agent) -> TeamLead: ...
    @classmethod
    def board(cls, agent: Agent) -> TeamLead: ...
```

组合期：`TeamComposer` 用 **原料 Agent + Mandate** **新建** lead 运行时实例（封闭图；原料 Agent 仍可 solo，互不 patch）。  
ActionScope：lead 实例为 SUPERVISOR（实现名可保留枚举值 `supervisor` 或改为 `lead`——见 §5）。

### 2.4 Coordination 值对象

```python
@dataclass(frozen=True)
class Pipeline:
    pass


@dataclass(frozen=True)
class FanOut:
    pass  # synthesizer 若需，作为可选字段后置，本设计不强制


@dataclass(frozen=True)
class PeerRelay:
    pass


@dataclass(frozen=True)
class PeerSwarm:
    max_rounds: int = 3


@dataclass(frozen=True)
class Debate:
    max_rounds: int = 3


@dataclass(frozen=True)
class Graph:
    execution_graph: ExecutionGraph
```

`Coordination` = 上述类型的 `Union` 或标记 Protocol（`@runtime_checkable` 可选）。  
**禁止**再引入平行的 `TeamProcess` / `Recipe` 枚举作为公共第二入口。

### 2.5 YAML 场景

```yaml
teams:
  board_review:
    lead:
      agent: pm          # roles 表中的 key
      mandate: board     # routing | consult | board
    members: [legal, finance]

  ingest:
    coordination: pipeline
    members: [extract, transform, load]

  workflow:
    coordination: graph
    execution_graph: ... # 引用或内联，与现有 loader 能力对齐
    members: [n1, n2]
```

删除：`recipe` / `process` / `supervisor_mode` / `decision_gate` / `supervisor_plane`。

---

## 3. 分层职责与边界

```text
contracts（领域契约）
  LeadMandate, TeamLead 规格数据（或仅 Mandate 枚举 + 组合参数）
  Coordination 值类型（或协议 + 各 dataclass）
  TeamContext, Session, Decision, Result
  禁止导出: Recipe, TeamProcess, SupervisorMode, OrchestrationFamily, SupervisorPlane

L4 api
  Agent, Team, TeamLead, LeadMandate, Pipeline, FanOut, …

L4 composer（原 assembly）
  AgentComposer.compose(...)
  TeamComposer.compose(members, lead|coordination, ...)
  唯一允许 new 出封闭可运行图的地方
  lead 路径: 重建 lead agent、挂 transport、gate、Lead 认知
  coordination 路径: 解析对应 Strategy、焊 transport

L3
  TeamRunner（原 TeamOrchestrator）：持 Context + Strategy，只 run
  *Strategy：PipelineStrategy, FanOutStrategy, LeadStrategy, …
  member_invoke / send_and_wait

L2 CognitiveRuntime
  不感知 Team / LeadMandate；只读 AgentState.session

L1 Brain / Body
  构造期注入 channel / gate / reasoner；无 public bind/install
  DecisionGate 仍为扩展点；仅由 BOARD mandate 展开挂载

L0 Transport / LLM / Store
  端口实现
```

### 3.1 内部展开表（实现唯一真相，不进 AGENTS 正文）

| 用户构造 | Strategy | Session | Gate |
|----------|----------|---------|------|
| `lead` + ROUTING | LeadStrategy | RoutingState | none |
| `lead` + CONSULT | LeadStrategy | ConsultationState | none |
| `lead` + BOARD | LeadStrategy | ConsultationState | must_consult_all |
| Pipeline | PipelineStrategy | — | — |
| FanOut | FanOutStrategy | — | — |
| PeerRelay | PeerRelayStrategy | — | — |
| PeerSwarm | PeerSwarmStrategy | — | — |
| Debate | DebateStrategy | — | — |
| Graph | GraphStrategy | — | — |

LeadStrategy = 今日 HierarchicalStrategy 的领域更名。  
策略注册键：**与用户类型对应的稳定字符串**（如 `pipeline` / `fan_out` / `lead`），**不再**使用 `TeamProcess.HIERARCHICAL`。

### 3.2 保留的铁律（从 0029 继承）

1. **封闭对象图**：`run` 前拓扑不可变  
2. **单端口成员调用**：`send_and_wait`  
3. **委派唯一载体**：`Decision.delegations`  
4. **session 单槽**：`ConsultationState | RoutingState`  
5. **组合权只在 L4 Composer**

---

## 4. 实现者命名（L-Advanced，非入门必读）

| 角色 | 名 | 备注 |
|------|-----|------|
| 单 Agent 对象图工厂 | **AgentComposer** | 原 `Assembly.assemble_agent` |
| Team 对象图工厂 | **TeamComposer** | 原 `Assembly.assemble_team` |
| 默认可插拔注册 | `defaults.register_defaults` | 保持 |
| Team 运行句柄 | **TeamRunner** | 原 TeamOrchestrator；也可暂留 Orchestrator 名，优先语义清晰 |
| Lead 路径策略 | **LeadStrategy** | 原 HierarchicalStrategy |
| 结算门（registry） | `DecisionGateName` | **不**作为 Team 构造参数 |

文件建议：

- `lca/layer4_app/composer.py`（由 assembly.py 迁/改名）  
- `lca/contracts/team_coordination.py`（LeadMandate + Coordination 类型）  
- 删除或掏空公共导出：`supervisor_mode.py` 中 Recipe/Mode；`enums.TeamProcess`；`orchestration_taxonomy` 公共 API  

`ActionScope.SUPERVISOR`：本设计允许 **实现枚举值暂留** `supervisor` 以免无意义的底层 churn，或一并改为 `LEAD`——实现计划中二选一，**默认改为 `LEAD`** 以名实一致（ActionScope 是构造期闭集，改名成本可控）。

---

## 5. 删除清单（仓库内零残留）

| 删除 | 替代 |
|------|------|
| `Recipe` | Coordination 类型 / TeamLead 工厂 |
| `TeamProcess` | 同上 + 策略内部 key |
| `SupervisorMode` | `LeadMandate` |
| `expand_recipe` | `TeamComposer` 内 mandate/coordination 分支 |
| `OrchestrationFamily` / `SupervisorPlane` 代码引用 | 删除；历史见 ADR 附录 |
| `MultiAgentTeam` | `Team` |
| `Assembly` 公共名 | `AgentComposer` / `TeamComposer` |
| `process` / `recipe` / `supervisor_mode` YAML | `lead` / `coordination` |
| AGENTS 中 Family/Recipe/Mode 段 | §7 半页领域语言 |

---

## 6. 迁移映射

| 旧 | 新 |
|----|-----|
| `MultiAgentTeam.pipeline(...)` | `Team.pipeline(...)` / `coordination=Pipeline()` |
| `MultiAgentTeam.fanout(...)` | `Team.fan_out(...)` / `FanOut()` |
| `MultiAgentTeam.manager(sup, members)` | `Team(..., lead=TeamLead.routing(sup))` |
| `MultiAgentTeam.consult(sup, members)` | `lead=TeamLead.consult(sup)` |
| `MultiAgentTeam.board(sup, members)` | `lead=TeamLead.board(sup)` |
| `MultiAgentTeam.relay(...)` | `coordination=PeerRelay()` |
| `MultiAgentTeam.swarm(...)` | `coordination=PeerSwarm(...)` |
| `MultiAgentTeam.debate(...)` | `coordination=Debate(...)` |
| `MultiAgentTeam.graph(..., execution_graph=)` | `coordination=Graph(execution_graph=)` |
| `process=HIERARCHICAL, mode=ROUTING` | `lead=TeamLead.routing(...)` |
| `process=SEQUENTIAL` | `coordination=Pipeline()` |
| `Assembly().assemble_team` | `TeamComposer().compose` |

---

## 7. 文档（AGENTS 目标形态，≤15 行级）

```markdown
## 团队协作

- Agent：单角色；Team：一队人 + 一种协作机制。
- 有主导者：`Team(members=..., lead=TeamLead.board(pm))`
  - mandate：`routing` 自由派活 | `consult` 有名单不强制 | `board` 必须全员咨询后收口
- 无主导者：`Team(members=..., coordination=Pipeline()|FanOut()|PeerRelay()|PeerSwarm()|Debate()|Graph(...))`
- 场景 YAML 使用 `lead.mandate` 或 `coordination`，二者勿并存。
```

---

## 8. 非目标

- 不重写 perceive→think→act 环  
- 不改 LLM / A2A / MCP 协议语义  
- 不改 `DelegationSpec` 字段集（除非发现与命名强冲突）  
- 不引入第三协作轴（禁止「coordination + lead + 神秘 mode」）  
- 不保留双轨 API「方便过渡」

---

## 9. 验收标准

1. `from lca import Agent, Team, TeamLead, LeadMandate, Pipeline, ...` 可完成全部一等协作  
2. 全仓 grep：无 `TeamProcess` / `Recipe` / `SupervisorMode` / `MultiAgentTeam` / 公共 `Assembly` 编排叙事  
3. 构造 `lead`+`coordination` 同现 → 测试断言失败  
4. `board` 路径行为与今 `BOARD` 一致（全员结算）；`routing` 与今 ROUTING 一致  
5. `uv run ruff/format/lint-imports/mypy/pytest/vulture` 全绿  
6. 新人无需阅读 Family/Plane/Recipe 即可组队  

---

## 10. 实现波次（计划阶段细化）

| Wave | 内容 |
|------|------|
| W1 | contracts：`LeadMandate`、Coordination 类型；删 Process/Recipe/Mode 公共类型 |
| W2 | `AgentComposer`/`TeamComposer`；Team API；Lead 重建路径 |
| W3 | 策略更名与注册键；LeadStrategy 共用三 mandate |
| W4 | scenario_loader、全量测试、e2e、AGENTS |
| W5 | ADR-0030 supersede 0027 用户旋钮与 0029 Recipe/Mode 公共面；死代码与 taxonomy 清理 |

---

## 11. 相关

- Supersedes（用户面叙事）：ADR-0027 三维旋钮、ADR-0029 Recipe/SupervisorMode 公共模型  
- Keeps：ADR-0029 封闭对象图、单 session 槽、L4 组合权、无 bind/install  
- Keeps spirit：ADR-0026 ConsultationState / 结算；ADR-0028 multi-delegate  

---

## 12. 开放点（实现计划前可微调用词，不改模型）

| 点 | 默认 | 备选 |
|----|------|------|
| Fan-out 糖方法 | `Team.fan_out` | `Team.fanout` |
| Graph 类型名 | `Graph` | `WorkGraph` |
| ActionScope 枚举值 | 改为 `LEAD` | 暂留 `SUPERVISOR` |
| Team 运行句柄类名 | `TeamRunner` | 暂留 `TeamOrchestrator` |

**模型不开放**：lead XOR coordination、TeamLead+LeadMandate、Coordination 具体类型、可破无 shim。
