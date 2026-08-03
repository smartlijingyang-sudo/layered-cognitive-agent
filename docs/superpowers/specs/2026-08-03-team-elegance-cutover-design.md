# Design: Team Elegance Cutover — 一次性彻头彻尾重构

**状态**: **FINAL — 全部决策已锁定，正在实现**  
**日期**: 2026-08-03  
**兼容策略**: **可破兼容**（无 shim、无 deprecated 双轨）  
**范围**: 团队编排与组装链路（L4 组合根、L3 团队/策略、L1 Brain/Body/Memory 组装 API、控制面契约）；**不**重写 MAP 循环算法、LLM 适配、传输协议语义  

### 锁定决策（不再开放选项）

| # | 决策 |
|---|------|
| D1 | team 内 supervisor = **Factory 新建实例**；原料 Agent 可继续 solo，互不 patch |
| D2 | L4 `Agent` 持有 **`AgentBuildSpec`**，重建只读 spec，禁止 runtime 考古 |
| D3 | PEER/GRAPH 运行态 **strategy-local**，不进 `RunContext.session` |
| D4 | 公共 API = **`TeamBlueprint` + Recipe 类方法**；无 gate/plane 并排参数 |
| D5 | **ActionScope** 一并落地：SOLO/MEMBER 无 DELEGATE；SUPERVISOR 有 |
| D6 | 废除全部 public bind/install；组装 mutation Protocol 删除 |
| D7 | `SupervisorMode` 三值闭集；`DecisionGateName` 仅 registry 键 |
| D8 | 单 PR 语义切面；测试全量迁移；无双轨 |

---

## 0. 为什么不是「再包一层」

上一轮「Elegance Pass C」混合了治标与治本：Recipe 藏旋钮、`SupervisorKernel` 收散落代码有价值，但 **`install_supervisor` / Capability Pack** 会把「先半成品、再组装期回写」固化成公共面——那是隐患，不是优雅。

本设计唯一标准：

> **一次构造，图即封闭；公开概念闭集且名实相符；组合只在 L4；L3 只调度；L1 无 mutation 组装 API。**

不达标的「看起来干净」一律不做。

---

## 1. 铁律（写入 ADR-0029，CI 可守卫）

### R1. 封闭对象图（Closed Object Graph）

在任意 `run()` / `team.run()` 之前：

- `Brain` / `Body` / `Memory` / `Runtime` / `CognitiveAgent` 的**协作拓扑不可变**
- **禁止**公共 API：`bind_*`、`install_*`、运行期 `brain.reasoner = ...`
- 唯一可变状态：`AgentState` 与 `ControlSession` 内的**运行时数据**（board 进度、delegate 计数、history…）

### R2. 合法组合闭集（Closed Configuration）

Supervisor 用户语义是 **一个** `SupervisorMode`（或 Recipe 展开结果），不是 `plane × gate` 自由积。

| SupervisorMode | 内部展开 | 会话类型 |
|----------------|----------|----------|
| `ROUTING` | 自由 PM | `RoutingState` |
| `CONSULTATION` | 有 board、无强制结算 | `ConsultationState` + gate=none |
| `BOARD` | 全员咨询结算 | `ConsultationState` + `MustConsultAllMembers` |

非法组合（如 ROUTING + must_consult）**类型上不可表达**。

### R3. 组合权唯一在 L4

- **只有** `TeamComposer` / `AgentComposer` / `SupervisorFactory` 创建对象图
- `TeamOrchestrator`、`*Strategy`、`SupervisorBinder`（删除）**不得** patch 已有 agent
- L3 **不得** `isinstance(HasChannel)` 后调用 mutation

### R4. 名实一致

- 公共 API / `glossary` L-User / 导出符号 **只含已实现之物**
- 禁止公共导出「未来槽位」「预留 process」
- ADR 可描述未来；**代码与 L-User 文档不可**

### R5. 单端口成员调用

- 策略级与 DELEGATE 级成员调用 **只**经 `send_and_wait(transport, …)`
- 禁止 strategy 直调 `member.run`（除 transport handler 内部）

### R6. 一次性切面

- **不**保留旧 `MultiAgentTeam(decision_gate=, supervisor_plane=)` 并行 API
- **不**保留 `RunContext.consultation` / `.routing` 双槽 shim
- 测试与 scenario **同 PR 全量迁移**；仓库内零调用旧表面

---

## 2. 目标架构

### 2.1 分层职责（清洗后）

```text
L4  Application / Composition Root
    AgentComposer, TeamComposer, SupervisorFactory
    TeamBlueprint / Recipe 展开
    唯一允许 new 出完整可运行图的地方

L3  Agent / Team runtime handles
    CognitiveAgent, TeamOrchestrator, TeamProcessStrategy
    MemberOrchestration（统一 invoke 形态）
    只持有已封闭的图并 run；零组装 mutation

L2  CognitiveRuntime
    perceive → think → act → reflect → stop
    不感知 team 组装；只读 AgentState.session

L1  Brain / Body / Memory
    构造期注入全部依赖（transport、gate、reasoner、shared store）
    无 public bind/install

L0  Transport / LLM / Store / Tools
    实现端口；不参与 team 语义

contracts
    数据 + 行为 Protocol（Brain/Body/Reasoner/…）
    无「组装用 mutation Protocol」
```

### 2.2 对象图（目标态）

```text
TeamBlueprint / Recipe
        │
        ▼
  TeamComposer
        ├─ ChannelComposer → InternalTransport（role → handler）
        ├─ AgentComposer × N members
        │     Body(transport_registry 仅默认协议，无 team channel)
        │     Memory(shared_store=…?) 构造注入
        ├─ SupervisorFactory（仅 SUPERVISOR recipe）
        │     Body(transport=team_transport) 构造注入
        │     Brain(reasoner=SupervisorReasoner, decision_gate=?) 构造注入
        │     budget policy 在 factory 内应用
        ├─ StrategyResolver → TeamProcessStrategy
        └─ TeamOrchestrator(TeamContext)  # 纯句柄

team.run(objective)
        → strategy.run(context, objective)
        → （SUPERVISOR）SessionFactory.make(context) + supervisor.run(RunContext(session=…))
        → RuntimeLoop → DELEGATE → send_and_wait → member handler → member.run
        → Result
```

### 2.3 与 CHOREOGRAPHY 均质

| Family | 组装 | 运行 |
|--------|------|------|
| SUPERVISOR | SupervisorFactory 一次建成 | Strategy 建 session + supervisor.run |
| CHOREOGRAPHY | 仅 members + transport | MemberOrchestration 拓扑 |
| PEER | 同 CHOREOGRAPHY | first_completed / swarm 累积（strategy-local） |
| GRAPH | graph + members | GraphStrategy + cursor（strategy-local 或 session） |

**策略层厚度同级**；SUPERVISOR 的本质复杂度关在 Factory + Session 类型里，不在 Orchestrator 补丁链。

---

## 3. 概念模型（公开闭集）

### 3.1 三层词汇

**L-User（默认文档与 API）**

| 词 | 含义 |
|----|------|
| `Agent` | 单体门面 |
| `MultiAgentTeam` | 团队门面 |
| `Recipe` | 团队配方（闭集） |
| `TeamBlueprint` | 显式团队说明（进阶仍清晰） |
| `Result` / `run` | 结果与生命周期动词 |

**L-Team（扩展 process / 读策略）**

| 词 | 含义 |
|----|------|
| `TeamProcess` | 族内拓扑枚举（registry 键） |
| `TeamProcessStrategy` | 策略实现 |
| `TeamContext` / `TeamOrchestrator` | 运行上下文与句柄 |
| `ControlSession` | `RunContext.session` 的联合类型 |
| `send_and_wait` | 成员调用端口 |
| `MemberOrchestration` | 顺序/并行/首成 |

**L-Advanced（框架作者）**

| 词 | 含义 |
|----|------|
| `SupervisorMode` | ROUTING / CONSULTATION / BOARD |
| `ConsultationState` / `RoutingState` | 控制面实现类型 |
| `DecisionGate` | 结算策略 Protocol（构造注入 Brain） |
| `OrchestrationFamily` | process→family 映射（CI / 文档对照） |
| `SupervisorFactory` / `TeamComposer` | 组合实现 |

### 3.2 Recipe 闭集（用户默认入口）

| Recipe | TeamProcess | SupervisorMode | 说明 |
|--------|-------------|----------------|------|
| `PIPELINE` | sequential | — | A→B→C 链式 |
| `FANOUT` | parallel | — | 并行 + synthesizer |
| `MANAGER` | hierarchical | ROUTING | 自由 PM |
| `CONSULT` | hierarchical | CONSULTATION | 有 board、自由收尾 |
| `BOARD` | hierarchical | BOARD | 全员必询 |
| `RELAY` | handoff | — | PEER 首成 |
| `SWARM` | swarm | — | PEER 轮询累积 |
| `GRAPH` | graph | — | 需 execution_graph |
| `DEBATE` | debate | — | 辩论策略 |

`MultiAgentTeam.board(...)` 等类方法 = Recipe 糖。  
`TeamBlueprint(recipe=…)` 或 `TeamBlueprint(process=…, supervisor_mode=…)` 为显式形；**无** `decision_gate`+`supervisor_plane` 并排字段。

### 3.3 删除或降级的概念

| 概念 | 处置 |
|------|------|
| 用户面 `decision_gate` + `supervisor_plane` | **删除**；由 `SupervisorMode` / Recipe 取代 |
| `SupervisorBinder` | **删除** |
| `install_decision_gate` | **删除**；`ModularBrain(__init__, decision_gate=)` |
| `bind_channel` | **删除**；`SimpleBody(..., transport=)` 构造时注册 |
| `bind_shared_memory` | **删除**；`SimpleMemorySystem(..., shared_store=)` |
| `HasChannel` / `HasReplaceableReasoner` / `SupportsDecisionGate` / `HasSharedMemory`（组装探测） | **删除公共组装用途**；`HasBrainBodyMemory`/`HasHooks` 若仅服务于 bind 则删或收窄 |
| `SupervisorInstallTarget` / 任何 `install_supervisor` | **永不引入** |
| `RunContext.consultation` / `.routing` | **删除**；统一 `session` |
| `AgentState` 上同名双槽 | **统一 `session`** |
| 公共 `RESERVED_PROCESS_SLOTS` | **移出公共导出**（可留 ADR appendix） |
| 「未来 PeerSession」公共叙事 | **删除**；PEER 明确 strategy-local，无 RunContext.session |
| `TeamOrchestrator` 内 resolve gate / create board / bind | **删除**；上移 Factory/Composer |

### 3.4 保留且锁死的概念

| 概念 | 原因 |
|------|------|
| `ConsultationState` 字段白名单 + CI | 防控制面垃圾袋 |
| `RoutingState` 字段白名单 + CI | 同上 |
| `send_and_wait` 单端口 | 路径收敛 |
| `Decision.delegations` 唯一委派规格 | 已治本 |
| `Registries` 值对象、非进程全局 | ADR-0024 |
| 五层 import-linter | ADR-0001 |
| MAP RuntimeLoop | 单/多 agent 同循环 |

---

## 4. 契约层变更

### 4.1 `RunContext`

```python
@dataclass
class RunContext:
    trace_id: str | None = None
    from_role: str = ""
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    session: ControlSession | None = None  # 唯一控制面槽
    # 无 consultation / routing / 禁止用 extra 存团队状态
```

`ControlSession` = `ConsultationState | RoutingState`（Typed Union / 窄化 helper）。  
GRAPH cursor / PEER 链若未来需要跨 agent 会话，**新类型 + 新 ADR**，不得塞进 Consultation。

### 4.2 `AgentState`

与 RunContext 对齐：`session: ControlSession | None`。  
所有 `state.consultation` / `state.routing` 读点改为 `as_consultation(state.session)` / `as_routing(...)`（contracts 提供窄化函数，失败显式错误）。

### 4.3 `TeamConfig`（内部规范配置）

展开结果，非用户双源：

```python
@dataclass
class TeamConfig:
    process: TeamProcess
    shared_memory_layers: list[MemoryLayer] = ...
    max_rounds: int | None = None
    supervisor_mode: SupervisorMode | None = None  # 仅 hierarchical 非 None
    delegate_max_attempts: int = 3
    # 删除 decision_gate / supervisor_plane 字段
```

`SupervisorMode` → gate 实例 / session 类型 的映射表在 **一处**（`supervisor_mode.py` 或 taxonomy），供 Factory 使用。

### 4.4 `TeamBlueprint`（L4 输入）

```python
@dataclass(frozen=True)
class TeamBlueprint:
    members: tuple[CognitiveAgent, ...]  # 或 L4 Agent，Composer 内剥壳
    recipe: Recipe | None = None
    process: TeamProcess | None = None  # 与 recipe 二选一
    supervisor: CognitiveAgent | None = None  # 原料 agent；Factory 重建 supervisor 图
    supervisor_mode: SupervisorMode | None = None  # hierarchical 且无 recipe 时必填
    shared_memory_layers: tuple[MemoryLayer, ...] = ()
    max_rounds: int | None = None
    execution_graph: ExecutionGraph | None = None
    delegate_max_attempts: int = 3
    strategy: TeamProcessStrategy | None = None  # 测试注入
```

`expand(blueprint) -> TeamConfig` 纯函数；非法组合 `ValueError`。

### 4.5 Protocol 清洗

**保留（行为）：** `Brain`, `Body`, `MemorySystem`, `Reasoner`, `Runtime`, `TeamProcessStrategy`, `AgentTransport`, `DecisionGate`（`enforce` + 可选 shortcut 仍可用独立 `SupportsShortcut` **仅 Brain 内部** isinstance）, `LLMAdapter`, `Tool`, …

**删除（组装 mutation）：**

- `SupportsDecisionGate.install_decision_gate`
- `HasChannel.bind_channel`
- `HasSharedMemory.bind_shared_memory`
- `HasReplaceableReasoner`（若仅服务于 reasoner 替换）
- 组装路径上对 `HasBrainBodyMemory` 的 bind 探测（Factory 直接依赖具体装配函数）

**DecisionGate 与 Brain：**

```python
class ModularBrain:
    def __init__(self, reasoner, decision_parser, critic, ..., decision_gate: DecisionGate | None = None):
        self._decision_gate = decision_gate  # 只读依赖，无 install 方法
```

---

## 5. L1 构造期依赖（废除 mutation）

### 5.1 `SimpleBody`

- `__init__(..., transport: AgentTransport | None = None, transport_registry=...)` **已有 transport 参数** — 保留并作为 **唯一** 注入 team channel 方式
- **删除** `bind_channel`
- FallbackDecoratedBody：删除对 bind 的转发；装饰器构造时包装已注入 channel 的 inner

### 5.2 `ModularBrain`

- `__init__(..., decision_gate: DecisionGate | None = None)`
- **删除** `install_decision_gate`
- reasoner **仅构造注入**；无公开可写 `reasoner` 属性用于组装（若测试需替换，用新 Brain 实例，不 patch）

### 5.3 `SimpleReasoner` / `SupervisorReasoner`

- 保持职责分离（ADR-0026 精神）
- `SupervisorReasoner.from_simple` **只在 SupervisorFactory 内**调用，产出 **新** Reasoner 实例交给 **新** ModularBrain
- 禁止对已存在 Brain 替换 reasoner

### 5.4 `SimpleMemorySystem`

- `__init__(..., shared_store: SharedMemoryStore | None = None)`
- **删除** `bind_shared_memory`
- TeamComposer 创建 member 时传入 shared store（若 blueprint 要求共享层）

### 5.5 Action 范围（可选但建议本切一并做干净）

- `build_action_registry(scope: ActionScope)`  
  - `SOLO` / `MEMBER`：respond + tools（+ 按需）  
  - `SUPERVISOR`：respond + tools + delegate（+ handoff 若需要）  
- 避免 member 注册无意义的 DELEGATE 处理器（减少隐患与提示噪音）

---

## 6. L3 / L4 模块职责

### 6.1 删除

| 模块/符号 | 原因 |
|-----------|------|
| `supervisor_bind.py` / `SupervisorBinder` | 补丁器生命周期错误 |
| `TeamOrchestrator` 内 `_bind` / `_create_member_status` / `_resolve_decision_gate` 组装逻辑 | 越权组合 |

### 6.2 新增（深模块，接口小）

| 模块 | 接口 | 实现 |
|------|------|------|
| `layer4_app/compose/team_blueprint.py` | `expand`, Recipe 表 | 纯函数 |
| `layer4_app/compose/channel_composer.py` | `build_team_transport` | 现 team_wiring |
| `layer4_app/compose/supervisor_factory.py` | `compose(raw_supervisor, transport, mode, registries, teammates_meta) -> CognitiveAgent` | 重建 brain/body/runtime，封闭图 |
| `layer4_app/compose/team_composer.py` | `compose(blueprint) -> TeamOrchestrator` | 编排上述 |
| `layer4_app/compose/agent_composer.py` | 现 `assemble_agent` 体 | 从 assembly 抽出 |
| `layer3_agent/member_orchestration.py` | sequential / parallel / first_completed | 加深现 member_invoke |
| `contracts/supervisor_mode.py` | enum + expand_to_session_kind / gate_name | 单点映射 |
| `contracts/session.py` | `ControlSession` 别名 + `as_consultation` / `as_routing` | 窄化 |

### 6.3 `TeamOrchestrator`（薄句柄）

```python
class TeamOrchestrator:
    def __init__(self, context: TeamContext, strategy: TeamProcessStrategy): ...
    async def run(self, objective: str) -> Result:
        return await self._strategy.run(self._context, text)
```

不接收「半成品 members + 自己 bind」。  
`TeamContext` 已含：封闭 members、封闭 supervisor（或 None）、transport、config、teammates、**预创建的 session 工厂数据**（如 `member_status` 空 board 模板或 factory）。

**Session 创建时机：**

- **推荐**：每次 `HierarchicalStrategy.run` 开始时 `new ConsultationState/RoutingState`（board 清零），避免跨 `team.run` 污染
- board 实现类由 registries 解析，但 **在 Strategy 或小型 `SessionFactory`（L3 无副作用纯创建）** 完成，不在 Orchestrator.__init__ bind agent

### 6.4 `HierarchicalStrategy`

```python
async def run(self, context, objective):
    assert context.supervisor is not None
    session = make_supervisor_session(context)  # 纯函数
    return await context.supervisor.run(objective, RunContext(session=session))
```

无 plane 分支 bind；mode 已在 factory 时决定 reasoner/gate。

### 6.5 `Assembly`

```python
def assemble_team(self, blueprint: TeamBlueprint) -> TeamUnit:
    return TeamComposer(self._registries).compose(blueprint)

def assemble_agent(self, ...) -> CognitiveAgent:
    return AgentComposer(self._registries).compose(...)
```

`assembly.py` 保持薄门面；默认 registries 注册逻辑仍在 `defaults.py`。

### 6.6 L4 API

```python
class MultiAgentTeam:
    def __init__(self, blueprint: TeamBlueprint, *, assembly: Assembly | None = None): ...

    @classmethod
    def pipeline(cls, members, **kw) -> MultiAgentTeam: ...
    @classmethod
    def fanout(cls, members, **kw) -> MultiAgentTeam: ...
    @classmethod
    def manager(cls, supervisor, members, **kw) -> MultiAgentTeam: ...
    @classmethod
    def consult(cls, supervisor, members, **kw) -> MultiAgentTeam: ...
    @classmethod
    def board(cls, supervisor, members, **kw) -> MultiAgentTeam: ...
    @classmethod
    def relay(cls, members, **kw) -> MultiAgentTeam: ...
    @classmethod
    def swarm(cls, members, **kw) -> MultiAgentTeam: ...
    @classmethod
    def graph(cls, members, execution_graph, **kw) -> MultiAgentTeam: ...
    @classmethod
    def debate(cls, members, **kw) -> MultiAgentTeam: ...

    async def run(self, objective: str) -> Result: ...
```

**删除**旧构造参数：`process`+`decision_gate`+`supervisor_plane` 并排（若保留 `process=` 唯一进阶路径，必须 **搭配** `supervisor_mode=` 闭集，且文档标 L-Advanced；推荐主路径只有 Recipe/类方法）。

**本设计选择（干净）：** 公共构造 **只接受 `TeamBlueprint` 或 Recipe 类方法**；测试可用 `TeamBlueprint(process=..., supervisor_mode=..., strategy=mock)`。

---

## 7. SupervisorFactory 细节（核心治本）

### 7.1 输入

- 用户传入的 supervisor `CognitiveAgent` 视为 **角色与预算原料**（role_profile、max_steps、llm 来源）
- **不**在其上 patch；**拆出**可复用零件或从 role_profile + llm **重建**

### 7.2 推荐重建策略（清晰、无隐患）

为避免「从已封闭 agent 挖 engrailed 依赖」的灰区：

1. L4 `Agent` 在 team 场景可提供 `SupervisorSpec(role, goal, backstory, tools, llm, max_steps, …)`  
2. 或 Factory 要求：`raw.runtime` 暴露只读访问器仅用于 **读取** llm/tools 配置以重建（只读，非 bind）  
3. **默认实现路径：** `MultiAgentTeam` 的 supervisor 参数与 members 一样是 L4 `Agent`；Composer 调用内部 `recompose_as_supervisor(agent, transport, mode)`：  
   - 从原 assembly 路径相同的零件工厂 **新建** Body/Brain/Runtime  
   - Brain 使用 `SupervisorReasoner` + 按 mode 注入 gate  
   - Body 使用 team transport  
   - 丢弃原料 agent 的旧 runtime 引用（team 持有新实例）

原料 agent 若被用户在 team 外继续 `run`，行为仍是 solo——**与 team 内 supervisor 实例分离**（文档写明）。这消除「同一对象双重身份」隐患。

### 7.3 Mode → 零件

```text
ROUTING:
  gate = None
  session_type = RoutingState
  reasoner = SupervisorReasoner (routing prompt 或统一 hierarchical_prompt 分支)

CONSULTATION:
  gate = None
  session_type = ConsultationState
  member_status 每 run 新建

BOARD:
  gate = MustConsultAllMembers()
  session_type = ConsultationState
  member_status 每 run 新建
```

Prompt：保持 `SupervisorReasoner` 固定模板；routing vs consultation 差异由 **session 内容** 驱动（roster 有无 board），不在组装期第二次 install。

---

## 8. MemberOrchestration

```text
invoke(context, member, task) -> Result          # send_and_wait
map_sequential(context, objective, *, chain, stop_first) -> Result
map_parallel(context, objective, synthesizer) -> Result
```

- `SequentialStrategy` / `HandoffStrategy` / `ParallelStrategy` / `SwarmStrategy` 只调上述  
- 删除各 strategy 复制的循环与直调 `member.run`

---

## 9. 文档与 ADR

| 动作 | 内容 |
|------|------|
| **新增 ADR-0029** | Closed Object Graph + SupervisorMode 闭集 + 组合权 L4 + 一次性切面 |
| **Amend ADR-0026** | Binder 删除；构造期 SupervisorReasoner；精神保留 ConsultationState |
| **Amend ADR-0027** | 用户面 Recipe/Mode；plane/gate 不再并排配置；Family 仍为分类学 |
| **Amend ADR-0004** | 组装 mutation Protocol 不是扩展点；行为 Protocol 才是 |
| **重写 glossary** | 三层词汇；删 Binder/install/双旋钮 L-User |
| **AGENTS.md** | 场景 YAML 用 `recipe:` 或 `supervisor_mode:` |
| **删除/归档** 过时 proposal 中与 bind 冲突的「继续 install」建议 | 避免双叙事 |

---

## 10. Scenario / 测试迁移

### 10.1 YAML

```yaml
teams:
  launch:
    recipe: board          # 优先
    supervisor: pm
    members: [a, b, c]
# 或进阶：
#   process: hierarchical
#   supervisor_mode: board
```

删除：`decision_gate` / `supervisor_plane` 字段（全仓库 grep 清零）。

### 10.2 测试

- 全量替换 `TeamConfig(decision_gate=..., supervisor_plane=...)`  
- 删除 `SupervisorBinder` 单测；改为 `SupervisorFactory` 构造封闭断言  
- 新增守卫测试：  
  - `SimpleBody` / `ModularBrain` / `SimpleMemory` **无** `bind_*`/`install_*`  
  - `TeamOrchestrator` 源码禁止 `bind_` / `install_`  
  - `expand` 闭集：仅三 Mode  
  - `RunContext` / `AgentState` 无 `consultation`/`routing` 字段  
  - public exports 无 `RESERVED_PROCESS_SLOTS`  
- 行为回归：现有 e2e / scenario / multi_delegate / handoff / parallel 语义保持

### 10.3 成功判据（合并门禁）

1. `uv run ruff check/format` + `lint-imports` + `mypy lca` + `pytest` + `vulture` 全绿  
2. 仓库 `rg 'install_decision_gate|bind_channel|bind_shared_memory|SupervisorBinder|supervisor_plane|decision_gate='` 在 `lca/` 与 `tests/` **零匹配**（允许 ADR 历史正文）  
3. L-User 示例只需 Recipe 类方法  
4. hierarchical 与 sequential 的 Strategy 文件均无组装逻辑  

---

## 11. 实施切面（概念一次，提交可原子分层）

**发布形态：单一切面分支 / 单次合并语义**（用户可见一次 breaking）。  
内部 commit 可按层拆分便于 review，但 **不中途兼容旧 API**：

| Commit 波次（同一 PR 或 stack，无旧表面残留） | 内容 |
|-----------------------------------------------|------|
| C1 | contracts: SupervisorMode, session 单槽, TeamConfig, 窄化 helper, 删双槽字段 |
| C2 | L1: Brain/Body/Memory 构造注入；删 bind/install 方法与 Protocol |
| C3 | L4 compose: Factory/Composer/Blueprint/Recipe；Assembly 瘦身 |
| C4 | L3: 薄 Orchestrator、薄 Hierarchical、MemberOrchestration；删 supervisor_bind |
| C5 | API + scenario_loader + 全测试迁移 |
| C6 | ADR-0029 + glossary + AGENTS + 守卫测试 + 导出清洗 |

**禁止：** C1 合并后长期保留 `consultation` property shim 给「半迁移测试」。

---

## 12. 风险与显式取舍

| 风险 | 处置 |
|------|------|
| Supervisor 重建丢失用户在 raw agent 上的自定义 brain | 文档：team supervisor 走 Factory 标准图；自定义 supervisor 需 `TeamBlueprint(strategy=…)` 或扩展 SupervisorFactory hook（进阶） |
| 同一 L4 Agent 实例加入 team 后身份分裂 | 文档：team 持有 **新** supervisor 实例；raw 仍可 solo |
| 一次性 PR 巨大 | stack 多 commit；CI 全量；不拆「兼容 release」 |
| ActionScope 裁剪漏 action | 默认 SUPERVISOR 含 delegate；MEMBER 与今 member 行为对齐测试锁死 |
| 与 ADR-0026「组装期 bind」字面冲突 | ADR-0029 明确 **废止 bind，保留「组装期定身份」精神** |

### 明确不做

- 不把一切改为 LangGraph  
- 不合并 Consultation/Routing 为一个 bag  
- 不引入 install 包装  
- 不保留双轨 API  
- 不在本切面重写 OpenAI/MCP 传输实现  

---

## 13. 优雅性终检

| 维度 | 如何满足 |
|------|----------|
| 概念 | 用户 Recipe/Mode 闭集；工程正交不进构造器 |
| 生命周期 | 构造封闭；run 只动 state/session |
| 位置 | 组合 L4；调度 L3；认知 L1/L2 |
| 职责 | Factory 创建；Orchestrator 持有；Strategy 拓扑；Body 执行 |
| 边界 | 无跨层 patch；无悬空未来 API |
| 隐患 | 无半成品 agent、无双槽、无双源配置、无 mutation Protocol |

---

## 14. 批准检查表（用户）

- [ ] 接受 **无 shim 一次性 breaking**  
- [ ] 接受 **废除全部 bind/install 公共面**  
- [ ] 接受 **SupervisorMode/Recipe 取代 gate+plane 用户旋钮**  
- [ ] 接受 **team 内 supervisor 为 Factory 新实例**（与原料 Agent 分离）  
- [ ] 接受 **PEER 无 ControlSession**（strategy-local）  
- [ ] 批准后进入 `writing-plans` 任务级实现计划并开工  

---

## 附录 A — 旧 → 新 速查

| 旧 | 新 |
|----|-----|
| `decision_gate=must_consult_all, plane=consultation` | `recipe=BOARD` / `supervisor_mode=BOARD` |
| `gate=none, plane=routing` | `recipe=MANAGER` / `mode=ROUTING` |
| `gate=none, plane=consultation` | `recipe=CONSULT` / `mode=CONSULTATION` |
| `SupervisorBinder.bind` | `SupervisorFactory.compose`（新建） |
| `RunContext(consultation=…)` | `RunContext(session=…)` |
| `brain.install_decision_gate(g)` | `ModularBrain(..., decision_gate=g)` |
| `body.bind_channel(t)` | `SimpleBody(..., transport=t)` |
| `memory.bind_shared_memory(s)` | `SimpleMemorySystem(..., shared_store=s)` |
| `MultiAgentTeam(..., process, gate, plane)` | `MultiAgentTeam.board(...)` / `TeamBlueprint(...)` |

## 附录 B — 与「包装式 Kernel」的差异

| 包装式 | 本切面 |
|--------|--------|
| Kernel.compose 内 bind 已有 agent | Factory **新建**封闭 agent |
| install_supervisor 一次调用 | **无 install API** |
| 保留 plane+gate 字段 | **Mode 闭集** |
| Orchestrator 仍参与组装 | Orchestrator **纯句柄** |
| 双轨兼容 | **单轨** |
