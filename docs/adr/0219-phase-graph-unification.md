# ADR-0219: phase-graph 一体化收敛 — interpreter × subgraph driver × phase context × port registry 单一职责回归

> **状态:** **Proposed — 2026-09-10**
>
> **一句话**: 把当前分散在四个 seam 的 phase-graph 职责一次性收口:`GenericPlanInterpreter` 只跑图不再携带业务 phase 名;`NodeGraphDriver` 只走 subgraph 调度不再代理 outer fold 语义;`RestrictedPhaseContext` 不再用字符串 key 共享跨节点产物,改成 typed `Mapping[SemanticPhase, PhaseResult]`;`PortContext` 不再用裸 `dict[str, Any]`,改成 typed `PortRegistry`(端口由 contracts 定义,key 编译期校验)。同时修掉 `think.gate` 把 `decision` 写到 `enforced_decision` 而不写回 `decision` 的数据流断裂。
>
> **触发 run:** `run_6b991f55c9e3`(`objective=ping`,H6 broken_hop),`session_status=failed`,`session_error=RuntimeError('action type is not authorized')`。同一根因引发的事实链:
>
> 1. `think.classify` 产出 `port_values={"decision": decision}`
> 2. `think.gate` **消费** `decision`,**写出** `{"enforced_decision": ..., "think_signal": ...}`,未写回 `decision` 槽
> 3. `NodeGraphDriver` 终止时 `project_port_values_to_phase_output(port_context._ports)` → `output.decision = port_values.get("decision") = classify 的值`(**未被 gate enforce**)
> 4. 外层 interpreter `_drive` 收到 `output.decision`,经 `record_result` 写入 `cursor.artifacts["think"] = pre-gate decision`(数据流断裂,但表面看不出)
> 5. `act.main` 进入 `_contribution_context`,从 `context.artifacts.get("think")` 拿到一个**不是 None 但语义错误**的决策;按当前 `control.act.authorize` 的实现(`decision is None or not _is_known_action(decision)`),当分类器返回的不是合法 `ActionType` 时落到 deny
>
> 但根因不止数据流。**真正的根因是:interpreter 知道"think"业务名词、phase_governance 用字符串 key 跨节点共享、PortContext 是无类型 dict**——这三个异味叠加,使得 H6 一次只修一处永远修不对,下次换 phase 顺序或加新 phase 还会再爆。
>
> **Agent Note(实施时):** [`docs/notes/implemented/seam/2026-09-10-phase-graph-unification.md`](../notes/implemented/seam/2026-09-10-phase-graph-unification.md)(P1—P5 同步收口)
>
> **Review:** 待评审
>
> **Accepted 闸门:**
>
> 1. §3 `interpreter` 不再 import `SemanticPhase` 的字面值,不出现 `result_kind="think_stage"` / `record_result(semantic_phase=SemanticPhase.THINK, ...)` 的字面 THINK
> 2. §4 `RestrictedPhaseContext` 删除 `artifacts: Mapping[str, object]` 字段,所有读取改成 `context.results_by_phase: Mapping[SemanticPhase, PhaseResult]`
> 3. §5 `lca/plugins/loop/phase/{act,stop,reflect,remember}/standard/plugin.py` 全部从 `cast("Decision | None", context.artifacts.get("think"))` 改为 `context.results_by_phase.get(SemanticPhase.THINK)` 单一入口
> 4. §6 `PortContext` 改成 typed `PortRegistry`,port 名由 `contracts/protocols/declarative/declarative_1/ports.py` 的 `Literal` 闭集定义,未知 port 名编译期拒绝
> 5. §7 `think.gate` 写回 `port_values["decision"] = enforced_decision`(并删除 `enforced_decision` / `think_signal` 这两个**没有 D4 消费者**的字段)
> 6. §8 端到端:`./scripts/lca-ops runs create --user-text "ping" --wait --json` 跑通六语义 `perceive → think → act → reflect → remember → stop`,`act.main` 不再因 `decision` 问题 deny;`broken_hop=None`
> 7. §9 既有 5 个 phase(`perceive` / `act` / `reflect` / `remember` / `stop`)+ think subgraph(5 节点)测试全过;新增 typed port + typed phase result 两组契约测试
> 8. §10 零 `grep -rn 'artifacts\["think"\]\|artifacts\.get("think")' lca/ plugins/`;零 `grep -rn 'SemanticPhase\.THINK' lca/framework/declarative/plugins/interpreter.py`;零 `grep -rn 'think_stage' lca/`

---

## 0. 第一性原理: 问题本质

### 0.1 业务语言 vs 框架语言

phase-graph 的设计目标是 **"用一张图描述六阶段 + 嵌套子图"**。它有两层语言:

| 层 | 语言 | 关注什么 |
|---|---|---|
| 业务层(yaml / profile) | "think 子图 5 步,act 单步" | 阶段拓扑、节点语义 |
| 框架层(interpreter / driver) | "沿着图选 next node,跑 executor,fold 结果" | 调度循环、数据通路 |

按 AGENTS.md §1.5 §3 "**模块化:一个模块一个概念、暴露小而稳定的 surface**"和 §1.5 §2 "**直击本质**",interpreter 应该只用框架语言——它不应该知道"think"是哪个 phase、不应该知道 gate enforce 之后叫什么字段、不应该知道 act 关心哪些 key。

### 0.2 当前 4 个 seam 的异味溯源

| seam | 异味 | 根因 |
|---|---|---|
| `interpreter._drive` sub_spec_ref 分支(`interpreter.py:395-480`) | `result_kind="think_stage"` 字面字符串(L424)、`SemanticPhase.THINK` 字面(L471)、`traversal.artifacts["think"]` 字符串 key 注释(L462-465) | interpreter 把 think 当特例写进主循环,而 think 实际是"任意有 sub_spec_ref 的 phase"的通用情形 |
| `node_graph_driver.py` `_drive_subgraph_inner`(L361-378 文档,L820-907 实现) | v1 PR-3 留空 stub、driver 既跑内部节点又负责 outer fold、channel.absorb 又被外层 interpreter 再 absorb 一次 | 把"outer 投影"和"inner 调度"塞进同一个对象 |
| `phase_governance.py:131-170` `_contribution_context` | `context.artifacts.get("think")` / `"act"` / `"reflect"` 字符串 key 跨节点共享 | 用 dict 模拟"运行时栈",没有 typed 约束;4 个下游 plugin 都用 `cast("Decision \| None", context.artifacts.get("think"))` 重复 |
| `think/gate.py` | 写 `enforced_decision` 不写回 `decision`,数据流断裂 | port_values 是字典,作者把"新概念"当"新字段"用,忘了契约是"决策经 gate enforce 之后仍是决策",不是"变成另一个东西" |
| `_port_context.py` `PortContext._ports: dict[str, Any]` | 端口名无类型约束,运行时才发现 typo | 端口是契约的一部分,不该用裸 dict 表示 |

### 0.3 为什么"只修 H6 不行"

按 AGENTS.md §1.5 §2 "**同一根因第二次出现 = 上次没修对**":

- `interpreter.py:462-465` 的注释直接写「之前只走 advance 但 advance 不写 artifacts,导致 act 段 decision=None 而触发 'action type is not authorized'」——这是上次 patch
- 这次 run 还是同一个错误信息(`action type is not authorized`)——**只动了 surface**,没动根因
- 不修 interpreter 业务知识:下次 think 改成 6 步、act 拆成 2 步,interpreter 又要硬编码新名字
- 不修 typed phase result:加任何新 phase 都要往 `_contribution_context` 里手写字符串 key
- 不修 typed port registry:加任何新 port 都要全 dict 改一遍,typo 不知道
- 不修 gate 数据流:任何下游只要写"新概念"就丢失原契约

### 0.4 不变量(本 ADR 之后)

| ID | 不变量 | 验证手段 |
|---|---|---|
| **N1** | `interpreter` 不持有任何 `SemanticPhase` 字面 | `grep -n 'SemanticPhase\.' lca/framework/declarative/plugins/interpreter.py` = 0 |
| **N2** | `interpreter` 不持有任何 phase 私有 `result_kind` 字面 | `grep -n 'think_stage\|perceive_stage\|act_stage\|reflect_stage\|remember_stage\|stop_stage' lca/framework/declarative/plugins/interpreter.py` = 0 |
| **N3** | `RestrictedPhaseContext` 跨节点产物走 `results_by_phase: Mapping[SemanticPhase, PhaseResult]` | 字段定义在 contracts;4 个下游 plugin 一处入口 |
| **N4** | 端口名是 `contracts/.../ports.py` 的闭集 `Literal` | `PortRegistry` 用 `TypedDict` 或 `Pydantic` 接 Literal |
| **N5** | `node_graph_driver.py` 不调 outer interpreter API(不调 `_contribution_context` / `record_result`) | driver 只输出 `InterpretationResult.output: PhaseOutput`,outer 自己 fold |
| **N6** | `think.gate` 写回 `decision` 槽,不发明新字段 | port contract 文档 + 测试断言 |

---

## 1. 设计原则

| 原则 | 本 ADR 怎么落 |
|---|---|
| 职责单一 | interpreter 只跑 outer graph;driver 只跑 subgraph;phase_governance 只装填 typed 依赖;PortRegistry 只管 port typed set |
| 模块化 | interpreter 不 import subgraph driver 内部;driver 不 import interpreter 业务 phase 名 |
| 边界清晰 | interpreter / driver / phase_governance / PortRegistry 四者两两之间只走 typed Contract |
| 优雅 | typed 闭集替字符串字面;每个字段都有 D5 消费者 |
| 第一性原理 | "interpreter 不该知道 think" 和 "decision 经 gate enforce 仍是 decision" 是同一类问题的两个表现——抽象层级错位 |
| 不留临时代码 | 不引入 compat shim;同 PR 删除 `artifacts: Mapping[str, object]`、`enforced_decision`、`think_signal`、`result_kind="think_stage"`、`interpreter._drive_subgraph_inner` v1 stub |
| 测试是设计的一部分 | typed port + typed phase result 两组契约测试必过 |

---

## 2. 现状(必读的 4 个 seam)

### 2.1 `interpreter.py` 的 sub_spec_ref 分支(异味点 1)

```python
# lca/framework/declarative/plugins/interpreter.py:402-480
if node.sub_spec_ref is not None:
    if self._subgraph_runner is None or self._channel_factory is None:
        raise DeclarativeValidationError("PG-005", ...)
    sub_runner = self._subgraph_runner
    channel = self._channel_factory()
    sub_state, output = await sub_runner.run(
        ref=node.sub_spec_ref,
        outer_state=current_state,
        channel=channel,
    )
    channel.absorb(output)
    current_state = sub_state
    virtual_result = PhaseResult(
        result_kind="think_stage",   # ← 字面字符串
        payload=output.decision,
    )
    edge = self._select_edge(
        graph.edges, node.id, virtual_result, traversal.artifacts, current_state,
    )
    visits.append(
        PhaseVisit(node.id, node.semantic_phase, "think_stage", edge.target),  # ← 字面字符串
    )
    payload = (
        getattr(output, "decision", None)
        if "output" in locals()
        else getattr(current_state, "decision", None)
    )
    phase_result = PhaseResult(
        result_kind="think_stage",   # ← 字面字符串
        payload=payload,
    )
    traversal.record_result(
        semantic_phase=SemanticPhase.THINK,  # ← 字面 THINK
        result=phase_result,
        effect_output=payload,
    )
    traversal.advance(edge=edge, payload=payload, causation_refs=())
    continue
```

### 2.2 `node_graph_driver.py` 的双重职责(异味点 2)

driver 既跑 inner 节点循环,又在 `_drive_subgraph_inner`(interpreter.py L820-907)留 v1 stub 让 outer 进来读 `_failed_result` / 调 `_drive`。同时 `_drive_subgraph_inner` 还在兜底"legacy GraphAssembler + inner drive"路径,与 v2 marker 路径并存。

### 2.3 `phase_governance.py` 的字符串 key 共享(异味点 3)

```python
# lca/harness/graph/governance/phase_governance.py:131-170
@staticmethod
def _contribution_context(executable_node, context, result):
    decision = context.artifacts.get("think")       # 字符串 key
    observation = context.artifacts.get("act")      # 字符串 key
    reflection = context.artifacts.get("reflect")   # 字符串 key
    return replace(
        context,
        decision=(
            result.payload
            if executable_node.semantic_phase is SemanticPhase.THINK  # 字面比较
            and isinstance(result.payload, Decision)
            else decision
            if isinstance(decision, Decision)
            else None
        ),
        ...
    )
```

下游 4 个 plugin(`act/standard` / `stop/standard` / `remember/standard` / `reflect/standard`)重复同样模式:`cast("Decision \| None", context.artifacts.get("think"))`。

### 2.4 `think/gate.py` 数据流断裂(异味点 4)

```python
# lca/plugins/think/gate.py:50-72
async def node_execute(self, context, input):
    runtime = context.runtime
    state = runtime.state
    gate = runtime.decision_gate
    decision = input.port_values.get("decision")   # 消费
    if decision is None:
        return NodeOutput(port_values={})
    if state is not None and isinstance(gate, DecisionGate):
        decision = await gate.enforce(state, decision)   # enforce 之后
    return NodeOutput(
        port_values={
            "enforced_decision": decision,  # ← 新字段,无 D4 消费者
            "think_signal": "gated",        # ← 摆设字段
        },
    )                                       # ← 没写回 decision
```

`enforced_decision` / `think_signal` 在 `lca/` 下没有任何消费者(`grep -rn "enforced_decision\|think_signal" lca/` 仅 plugin 自己内部出现)。

---

## 3. interpreter 单一职责回归

### 3.1 决定

`interpreter` 的主循环按"outer graph 调度 + fold typed phase result"两个职责重构,不再写任何 phase 业务名:

1. `interpreter.py:402-480` 的 sub_spec_ref 分支:
   - 删除 `result_kind="think_stage"` 字面(三次);改为 `result.result_kind = "decision"`(typed fold 输出,见 #3)
   - 删除 `SemanticPhase.THINK` 字面;改为 `node.semantic_phase`(已经是 typed 字段)
   - 删除 `traversal.artifacts["think"]` 字符串 key 注释;改为 typed fold(见 §4)
2. `interpreter._drive_subgraph_inner`(interpreter.py L820-907):**整段删除**。保留 `_drive_subgraph_ref`(outer 边级 subgraph 调用点),内部统一委派 `subgraph_runner.run()`(v2 driver seam)。v1 legacy `GraphAssembler + inner drive` 路径同 PR 删除(被 ADR-0217 §6 取代,现网 100% v2 plan)
3. 新增 `interpreter._fold_subgraph_output(output: PhaseOutput) -> PhaseResult` typed fold 辅助函数:
   - 输入是 `PhaseOutput`(typed Pydantic,见 §5)
   - 输出是 `PhaseResult`,`payload` 是 `output.decision`(因为 subgraph 唯一对外 contract 是 decision;其他字段 observation/reflection/response 是其它 phase 关心,不在 outer interpreter fold 范围)
   - `result_kind = "decision"`(领域字符串,与 `_contribution_context` 消费路径对齐,见 §3.3)
4. `interpreter` import 删除:
   - `from lca.contracts.protocols.declarative.declarative_1.declarative_common import SemanticPhase`(L34)
   - 任何 `result_kind="<私有字面>"` 引用(如 `"think_stage"`);**保留**领域 `result_kind="decision"` / `"observation"` / `"control"` 等,因为这些由 phase executor / control plugin 写,被 `_contribution_context` 消费(不是 interpreter 自己发明的)

### 3.2 `SemanticPhase` 在 interpreter 的允许出现点

| 位置 | 允许 | 不允许 |
|---|---|---|
| `node.semantic_phase`(typed 字段读取) | ✅ | |
| `executable_node.semantic_phase`(typed 字段读取) | ✅ | |
| 与 `SemanticPhase.<X>` 字面比较 | | ❌ |
| 字面 `SemanticPhase.THINK` 等 | | ❌ |
| `record_result(semantic_phase=SemanticPhase.X, ...)` | | ❌(改成 typed fold) |

### 3.3 Domain result_kind 与 generic kind 的区分

`PhaseResult.result_kind: str` 字段保留 `str` 形式,**不引入新 enum**。原因:现网 `result_kind` 是**领域字符串**(`"decision"` / `"observation"` / `"control"` / `"phase_error"` 等),由 phase executor 写入,被 control plugin 与 `_contribution_context` 消费。新增 `PhaseResultKind` enum 替换 `str` 会迫使全网重写 30+ 调用点,范围远超本 ADR 的根因修复目标,且**不解决 H6**。

H6 的根因是 **interpreter 自己发明了私有字面 `"think_stage"`** ——它不属于任何 enum,也不属于"领域字符串"集合。本 ADR 的 fix 是:

1. 删除 interpreter.py L424 / L455 / L467 的 `result_kind="think_stage"` 三处字面
2. 改为 typed fold:`interpreter._fold_subgraph_output(output: PhaseOutput) -> PhaseResult` 输出 `result_kind = "decision"`(与 think 子图对外 contract `output.decision` 对齐)
3. `output: PhaseOutput` 由 `subgraph_runner.run()` 返回,`PhaseOutput.decision: Decision | None` 是 typed Pydantic 字段(L37 `lca/framework/subgraph/plugins/channel.py`)

### 3.4 delete-when

- `interpreter.py` `grep 'SemanticPhase\.'` 返回 0 行(`node.semantic_phase` / `executable_node.semantic_phase` 字段读取不计)
- `interpreter.py` `grep 'think_stage'` 返回 0 行
- `interpreter._drive_subgraph_inner` 整段删除;`interpreter._drive_subgraph_ref` 委派 `subgraph_runner.run()`(单一 seam)
- 所有测试通过

---

## 4. `RestrictedPhaseContext` typed phase result

### 4.1 决定

删除 `RestrictedPhaseContext.artifacts: Mapping[str, object]` 字段(`lca/harness/declarative/lifecycle/phase_context.py:31`)。同时删除 `decision` / `observation` / `reflection` 单字段(L34-36)。新增 `RestrictedPhaseContext.results_by_phase: Mapping[SemanticPhase, PhaseResult]`,由 phase_governance 装填,interpreter 在调用 phase executor 前一次性 resolve。

```python
# lca/harness/declarative/lifecycle/phase_context.py
@dataclass(slots=True)
class RestrictedPhaseContext(PhaseContext):
    plan_ref: str
    node_ref: str
    state: AgentState
    journal: JournalCommitter
    budget: Budget
    # 删除:
    # artifacts: Mapping[str, object]    # 字符串 key 共享,违反 N3
    # decision: Decision | None
    # observation: Observation | None
    # reflection: Reflection | None
    # 新增 typed 跨节点产物闭集
    results_by_phase: Mapping[SemanticPhase, PhaseResult] = field(default_factory=dict)
    capabilities: PhaseCapabilityReader
    checkpoint_reason: str | None = None
    _proposed_deltas: list[RunDelta] = field(default_factory=list)
```

### 4.2 `phase_governance._contribution_context` 重构

`phase_governance.py:131-170` 的 `_contribution_context` 改为单一 typed fold:

```python
@staticmethod
def _contribution_context(executable_node, context, result):
    new_results = dict(context.results_by_phase)
    new_results[executable_node.semantic_phase] = result  # typed key
    return replace(context, results_by_phase=new_results)
```

不再有 `decision` / `observation` / `reflection` 单字段。所有 phase executor 通过 `context.results_by_phase.get(SemanticPhase.THINK)` 拿上游产物。

### 4.3 下游 4 个 plugin 同步 + 11 个 control / phase plugin 一并 typed entry

按 §4.2 typed fold 后,`RestrictedPhaseContext` 暴露 `payload_of(phase, want)` typed 方法(Protocol 级,**不是**模块级 helper):

```python
class PhaseContext(Protocol):
    def payload_of(self, phase: SemanticPhase, want: type[object]) -> object | None:
        """Return the typed payload from one upstream phase result."""
        ...
```

11 个 phase / control plugin 全部用 `context.payload_of(SemanticPhase.THINK, Decision)` 风格调用:

| 文件 | 调用模式 |
|---|---|
| `lca/plugins/loop/phase/act/standard/plugin.py` | `context.payload_of(SemanticPhase.THINK, Decision)` |
| `lca/plugins/loop/phase/stop/standard/plugin.py` | `context.payload_of(SemanticPhase.X, X)` × 3 |
| `lca/plugins/loop/phase/reflect/standard/plugin.py` | `context.payload_of(SemanticPhase.ACT, Observation)` × 2 |
| `lca/plugins/loop/phase/remember/standard/plugin.py` | 同上 |
| `lca/plugins/loop/control/act_authorize/plugin.py` | `context.payload_of(SemanticPhase.THINK, Decision)` |
| `lca/plugins/loop/control/act_execute/plugin.py` | 同上 |
| `lca/plugins/loop/control/act_safe_boundary/plugin.py` | 同上 |
| `lca/plugins/loop/control/act_constrain/plugin.py` | 同上 |
| `lca/plugins/loop/control/think_guard/plugin.py` | 同上 × 2 |
| `lca/plugins/loop/control/stop_decide/plugin.py` | 同上 |
| `lca/plugins/loop/control/remember_admit/plugin.py` | `payload_of(SemanticPhase.ACT, Observation)` + `payload_of(SemanticPhase.REFLECT, Reflection)` |

**设计选择:** `payload_of` 是 `PhaseContext` Protocol 的方法,而**不是**模块级 helper(`upstream_decision` / `upstream_observation` / `upstream_reflection`)。理由:

- helper 函数让 reader 看不到"来自哪个 phase",调用方要记 `upstream_X` 是 X 类型的 helper,反模式;
- `payload_of(SemanticPhase.X, T)` 把数据流显式留在调用点;
- Protocol 方法与现有 `emit_fact` / `propose_delta` 同级,职责一致;
- 一次 `isinstance` 检查就够了,不需要"为每个类型造一个函数"的命名税。

### 4.4 delete-when

- `RestrictedPhaseContext` 无 `artifacts` 字段,`grep -n 'context\.artifacts\b' lca/` = 0(注释除外)
- `grep -n 'artifacts\["think"\]\|artifacts\.get("think")' lca/ plugins/` = 0
- `grep -n 'artifacts\["act"\]\|artifacts\["reflect"\]\|artifacts\["remember"\]' lca/ plugins/` = 0
- `lca/plugins/loop/phase/_shared/typed_payload.py` **不存在** —— 不引入 helper(改 Protocol 方法)
- 11 个 plugin 全部用 `context.payload_of(SemanticPhase.X, T)` 调用,`grep -n 'upstream_decision\|upstream_observation\|upstream_reflection' lca/` = 0
- `phase_governance._contribution_context` 改为单一 typed fold,无字面 phase 字符串比较

---

## 5. typed `PortRegistry`

### 5.1 决定

`lca/harness/graph/execute/v2/_port_context.py` 的 `PortContext` 改为 typed `PortRegistry`,端口名是 `contracts/protocols/declarative/declarative_1/ports.py` 的闭集 `Literal`:

```python
# lca/contracts/protocols/declarative/declarative_1/ports.py
from typing import Literal

# 端口名闭集:每个端口名都有 D1 定义点 + D4 消费者,无 D5 = 禁止入 schema
PortName = Literal[
    "decision",            # think.classify / gate → outer
    "observation",         # observe nodes → outer
    "reflection",          # reflect nodes → outer
    "response",            # LLM response → think.classify
    "turn_plan",           # think.reason.plan → think.reason.render
    "turn_render",         # think.reason.render → think.reason.complete
    "enforced_decision",   # 退役,见 §7
    "think_signal",        # 退役,见 §7
]
```

### 5.2 `PortRegistry` typed 入口

```python
# lca/harness/graph/execute/v2/port_registry.py
class PortRegistry:
    __slots__ = ("_ports",)
    def __init__(self) -> None:
        self._ports: dict[str, Any] = {}
    def set(self, name: PortName, value: Any) -> None: ...
    def get(self, name: PortName) -> Any: ...
    def merge(self, port_values: Mapping[PortName, Any]) -> None: ...
    def build_input(self, declared_ports: tuple[PortName, ...]) -> NodeInput: ...
```

`set` / `get` / `merge` 接 `PortName` Literal,`mypy --strict` 在编译期拒绝 typo。运行时 `set` 仍然容忍(动态 yaml 字段),但 `pyright` IDE 实时提示。

### 5.3 `NodeOutput` 改 typed

`lca/contracts/protocols/declarative/declarative_1/node_executor.py`:

```python
class NodeOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    port_values: Mapping[PortName, Any]  # ← typed key
```

### 5.4 delete-when

- `grep -rn 'port_values: Mapping\[str, Any\]' lca/contracts/ lca/harness/graph/execute/v2/` = 0(注释除外)
- `grep -rn 'port_values\[.*\]' lca/plugins/think/` 全部通过 typed entry
- `mypy --strict lca/contracts/protocols/declarative/declarative_1/ports.py lca/harness/graph/execute/v2/port_registry.py` 无 error
- PortRegistry 单测覆盖 merge / build_input 边界

### 5.5 图不知道业务,业务不知道图

**原则(第一性原理):图层(`BundleGraphNode` / driver)与业务层(plugin / yaml `inputs/outputs`)互不感知。**

当前异味:

```yaml
# bundles/think_reason.yaml — 图层 yaml 写业务 port 名
nodes:
  - id: think.reason.plan
    outputs: [turn_plan]            # ← 业务字段名污染了图
  - id: think.reason.render
    inputs: [turn_plan]             # ← 业务字段名污染了图
    outputs: [turn_render]
```

```python
# lca/framework/subgraph/plugins/node_graph_driver.py:204
inp = port_context.build_input(node.inputs)  # ← 图层读业务字段名
```

`inputs` / `outputs` 是 **plugin 的 port contract**,不是图的拓扑。图层应该只关心"哪个节点连哪个节点";节点接哪个 port、上游是否给齐,是 plugin 自己的事。

#### 决定

| 改动 | 位置 |
|---|---|
| `BundleGraphNode.inputs` / `BundleGraphNode.outputs` 字段从 contract **删除**(runtime 不再读) | `lca/contracts/protocols/declarative/declarative_1/bundle_graph.py` L52-53 |
| `BundleGraphSpec.__post_init__` 不再要求 inputs/outputs 非空 | 同上 |
| `NodeExecutor` Protocol 新增 typed 属性:`declared_inputs: tuple[PortName, ...]`、`declared_outputs: tuple[PortName, ...]` | `lca/contracts/protocols/declarative/declarative_1/node_executor.py` |
| `node_graph_driver.py:204` 改为 `build_input(executor.declared_inputs)`(从 executor instance 拿,不再读 `node.inputs`) | `lca/framework/subgraph/plugins/node_graph_driver.py` |
| 所有 11 个 think plugin 同步声明 `declared_inputs` / `declared_outputs`(typed `PortName` Literal 闭集) | `lca/plugins/think/**/*.py` |
| `bundles/think.yaml` / `bundles/think_reason.yaml` 删除 `inputs:` / `outputs:` 字段(向后兼容:yaml 仍容忍这两个字段,但 runtime 忽略,作为文档注释保留) | `bundles/think*.yaml` |
| `lca/plugins/think/reason/entry.py`、`lca/plugins/think/local_gate.py` 同 §9.2 整文件退役 |  |

#### 边级 data edge 类型

`BundleGraphEdge.kind: Literal["control", "data"]` 当前已存在但**未被 runtime 消费**(driver 只看 `when`)。保留类型字面但 §5.5 不强制使用——data-edge 是 §5 之后的下一步。

#### delete-when

- `grep -rn 'node\.inputs\|node\.outputs\|n\.inputs\|n\.outputs' lca/harness/graph/execute/v2/ lca/framework/subgraph/plugins/` = 0
- `grep -rn 'declared_inputs\|declared_outputs' lca/plugins/think/` ≥ 11 条(11 个 plugin 各自声明)
- `grep -rn 'inputs:\|outputs:' bundles/think.yaml bundles/think_reason.yaml` = 0(bundle yaml 不再写业务字段)
- `mypy --strict lca/contracts/protocols/declarative/declarative_1/node_executor.py` 验证 `declared_inputs` / `declared_outputs` 是 typed `tuple[PortName, ...]`
- 测试 `tests/contracts/test_node_executor_port_contract.py`:验证所有 think plugin 的 `declared_inputs` ⊆ `PortName` 闭集

---

## 6. `NodeGraphDriver` 单一职责

### 6.1 决定

`node_graph_driver.py` 拆成两个 module:

| 新模块 | 职责 | 行数上限 |
|---|---|---|
| `lca/framework/subgraph/plugins/node_graph_driver.py`(已存在,瘦身) | **inner 调度循环**: 跑 5 节点顺序循环,emit `phase_graph.node.start/end`,调 executor,merge port,选 edge | 250 |
| `lca/framework/subgraph/plugins/subgraph_runner.py`(新增) | **outer 接口**: 接 `ref`,resolve plan,创建 PortRegistry,委派 driver,投影 `port_values → PhaseOutput`,返回 `InterpretationResult` | 100 |

### 6.2 driver 瘦身

删除:
- `_drive_subgraph_ref`(L331-358): 移到 `subgraph_runner.py`
- `_drive_subgraph_inner`(L361-378): 整段删除(v1 stub 同 PR 删)
- `_failed_result`(L396-432): 移到 `subgraph_runner.py`,作为 runner 失败出口

保留:
- `__init__` / `run` / `_execute_with_emits` / `_emit_observers`
- `_recursion_stack` 改为可选参数(`recursion_stack: set[str] | None = None`),driver 不再自己处理递归,递归由 outer runner 调度

### 6.3 runner 新增

```python
# lca/framework/subgraph/plugins/subgraph_runner.py
class SubgraphRunner:
    def __init__(self, *, scope, factory_resolver, channel_factory, observers=()):
        self._scope = scope
        self._factory_resolver = factory_resolver
        self._channel_factory = channel_factory
        self._observers = observers
        self._recursion_stack: set[str] = set()
        self._max_depth = MAX_SUBGRAPH_DEPTH_DEFAULT

    async def run(
        self, *, ref: SubgraphReference, outer_state: AgentState, channel: PhaseOutputChannel,
    ) -> tuple[AgentState, PhaseOutput]:
        """跑 subgraph, 返回 (state, output)。递归由 runner 自己负责。"""
        if ref.plan_ref in self._recursion_stack:
            raise SubgraphCycleError(ref.plan_ref)
        if len(self._recursion_stack) >= self._max_depth:
            raise SubgraphDepthExceededError(len(self._recursion_stack), self._max_depth)
        self._recursion_stack.add(ref.plan_ref)
        try:
            return await self._run_inner(ref, outer_state, channel)
        finally:
            self._recursion_stack.discard(ref.plan_ref)

    async def _run_inner(self, ref, outer_state, channel):
        plan = self._scope.resolve(ref.plan_ref)
        driver = NodeGraphDriver(
            spec=plan, plan_ref=ref.plan_ref, scope=self._scope,
            observers=self._observers,
        )
        result = await driver.run(outer_state=outer_state, channel=channel, ...)
        return result.state, result.output
```

### 6.4 delete-when

- `node_graph_driver.py` ≤ 200 行(`wc -l`)
- `_failed_result` 移至 runner
- `_drive_subgraph_ref` / `_drive_subgraph_inner` 删除
- `interpreter._drive_subgraph_inner`(interpreter.py L820-907)整段删除
- 所有 subgraph 测试通过(单测 + 集成测)

---

## 7. `think.gate` 数据流修复

### 7.1 决定

```python
# lca/plugins/think/gate.py:50-72
async def node_execute(self, context, input):
    runtime = context.runtime
    state = runtime.state
    gate = runtime.decision_gate
    decision = input.port_values.get("decision")
    if decision is None:
        return NodeOutput(port_values={})
    if state is not None and isinstance(gate, DecisionGate):
        decision = await gate.enforce(state, decision)
    # 写回 decision 槽;不再发明新字段
    return NodeOutput(port_values={"decision": decision})
```

### 7.2 port 退役

`enforced_decision` / `think_signal` 两个字段在 §5.1 的 `PortName` Literal 中标记为退役(注释保留历史),但保留为字面值 0 出现:

- `grep -rn 'enforced_decision\|think_signal' lca/plugins/ lca/harness/` = 0
- `bundles/think.yaml` 不再有 `inputs:` / `outputs:` 引用这两个字段

### 7.3 delete-when

- `think/gate.py` 输出 port_values 仅含 `"decision"`(若 decision 非 None)或 `{}`(若 decision None)
- H6 重跑:`./scripts/lca-ops runs create --user-text "ping" --wait --json` 跑通六语义,`act.main` 不再因 decision 缺失 deny
- `tests/think/test_gate.py` 新增 typed port 断言(只写 decision,不写其他字段)

---

## 8. 端到端验证

| # | 项 | 命令 | 通过条件 |
|---|---|---|---|
| 1 | N1 grep | `grep -n 'SemanticPhase\.' lca/framework/declarative/plugins/interpreter.py` | 0 行(字段读取不计) |
| 2 | N2 grep | `grep -rn 'think_stage\|perceive_stage\|act_stage\|reflect_stage\|remember_stage\|stop_stage' lca/framework/declarative/plugins/interpreter.py` | 0 行 |
| 3 | N3 grep | `grep -rn 'artifacts\["think"\]\|artifacts\.get("think")\|artifacts\["act"\]\|artifacts\["reflect"\]\|artifacts\["remember"\]' lca/ plugins/` | 0 行 |
| 4 | N4 mypy | `mypy --strict lca/contracts/protocols/declarative/declarative_1/ports.py lca/harness/graph/execute/v2/port_registry.py lca/framework/subgraph/plugins/subgraph_runner.py` | 0 error |
| 5 | N5 grep | `grep -n '_contribution_context\|record_result\|traversal\.artifacts' lca/framework/subgraph/plugins/node_graph_driver.py` | 0 行 |
| 6 | N6 grep | `grep -rn 'enforced_decision\|think_signal' lca/ lca/plugins/` | 0 行(注释除外) |
| 6b | N6b grep(图层无业务字段) | `grep -rn 'node\.inputs\|node\.outputs\|n\.inputs\|n\.outputs' lca/harness/graph/execute/v2/ lca/framework/subgraph/plugins/` | 0 行 |
| 6c | N6c grep(bundle yaml 无 inputs/outputs) | `grep -E '^\s*(inputs\|outputs):' bundles/think.yaml bundles/think_reason.yaml` | 0 行 |
| 6d | N6d plugin 声明 typed ports | `grep -c 'declared_inputs\|declared_outputs' lca/plugins/think/**/*.py` | ≥ 11 条 |
| 7 | 端到端 run | `./scripts/lca-ops kernel-restart && ./scripts/lca-ops runs create --user-text "ping" --wait --json` | run 状态 `success`,trace_id 有完整六语义事件 |
| 8 | 既有测试 | `pytest tests/think/ tests/harness/graph/execute/ tests/declarative/test_phase_graph.py tests/contracts/test_subgraph_reference_contract.py tests/harness/declarative/ -v` | 全过(允许 baseline fail 隔离) |
| 9 | 新增契约测试 | `pytest tests/contracts/test_port_registry_typing.py tests/contracts/test_results_by_phase.py -v` | 全过 |
| 10 | plugin shape | `./scripts/lca-ops audit-plugin-shape` | 0 新增违例 |
| 11 | import lint | `./scripts/lca-ops lint-imports` | 不引入新违例(baseline 既有违例可标注) |
| 12 | ruff | `ruff check lca/ tests/` | 不引入新违例 |
| 13 | 包契约 | `./scripts/lca-ops check-package-contracts` | 不引入新违例 |

---

## 9. 兼容性

### 9.1 profile YAML

`web-standard.yaml` `think.main` 节点 `sub_spec_ref` 字段不动(已有;§3 验证它已在编译路径正确投影到 `PhaseNode.sub_spec_ref`)。`bundles/think.yaml` 仅 `think.reason` 节点保留 `inputs: [in_assembled_manifest]` / `outputs: [response]`(ADR-0217 §3.3.3 inner_graph port passthrough 用),其余节点无 `inputs:` / `outputs:`。

### 9.2 既有 plugin

| plugin | 改动 |
|---|---|
| `lca/plugins/think/{shortcut,route,reason,classify,gate}/` | 6 个 `node_execute` 内部 port_values 字面 key 与 §5.1 `PortName` Literal 对齐 |
| `lca/plugins/think/local_gate.py` | **整文件退役** — `local_gate` 在生产路径未引用(`grep -rn "local_gate\|think.local_gate" bundles/ profiles/` = 0),仅有 `lca/plugins/think/__init__.py` import。无 D4 消费者,按 §7.2 原则同 PR 删 |
| `lca/plugins/think/reason/entry.py` | **整文件退役** — `reason.entry` 同样仅在 `__init__.py` import,无 bundle / profile 引用。同 PR 删 |
| `lca/plugins/loop/phase/{perceive,act,reflect,remember,stop}/standard/` | 4 个 standard plugin 改 typed entry(§4.3) |
| `lca/plugins/loop/phase/think/standard/` | 整个 plugin 退役(已被 ADR-0217 + node-level sub_spec_ref 取代) |

### 9.3 既有测试

| 测试文件 | 改动 |
|---|---|
| `tests/contracts/test_subgraph_reference_contract.py` | +4 用例覆盖 typed PortName 闭集 |
| `tests/harness/graph/execute/test_interpreter_subgraph.py` | +3 用例覆盖 `_fold_subgraph_output` typed fold |
| `tests/declarative/test_phase_graph.py` | +2 用例覆盖 `results_by_phase` typed fold |
| `tests/think/test_gate.py` | 重写:仅断言 `decision` 写回,不再断言 `enforced_decision` / `think_signal` |
| `tests/declarative/test_phase_governance.py` | 重写:仅断言 typed fold,不再断言字符串 key 共享 |

---

## 10. Alternatives considered

### 10.1 Why not 只修 `think.gate` 数据流(最小改动)?

最小改动 = 只把 `gate.py` 改成写回 `decision` 不发明新字段。H6 重跑会通过,但:

- interpreter 仍知道 `SemanticPhase.THINK` 字面
- phase_governance 仍用字符串 key 跨节点共享
- PortContext 仍是裸 dict

下次 think 改成 6 步、act 拆成 2 步、加任何新 phase,会再次以同样模式爆。**修一处不动架构 = 假装修对了**。

### 10.2 Why not 把 `artifacts` 改成 `dataclass` 而不是 `Mapping[SemanticPhase, PhaseResult]`?

`dataclass` 同样能 typed,但无法处理"phase 数量随配置变化"的情形——`SemanticPhase` 是 6 个 enum,dict 形式才能显式表达"哪些 phase 已有产物"。`Mapping[SemanticPhase, PhaseResult]` 配合 Pydantic `Field(default_factory=dict)` 是当前最简 typed 形式。

### 10.3 Why not 在 `interpreter` 里直接处理 typed fold,不引入 `_fold_subgraph_output` 辅助函数?

辅助函数是单一职责边界——interpreter 主循环只负责"调起来 + 跑 + 选边",fold 是数据投影,放辅助函数更易测、更易复用(将来 act / reflect 可能也需要 fold subgraph output 到自己的 phase result)。

### 10.4 Why not 把 `enforced_decision` / `think_signal` 当作"phase-private 字段"保留?

它们没有 D4 消费者(只有 plugin 自己写,没人读)。按 ADR-0195 §1.4 "无 Contract 跨边界 = fail-loud" + C6 最小化,无消费者字段不保留。同 PR 删。

### 10.5 Why not 删 `interpreter._drive_subgraph_inner` v1 legacy `GraphAssembler + inner drive` 路径?

ADR-0217 §6 + ADR-0218 §4 已经把 v2 plan 路径走通,v1 legacy 是为老 declarative plan 兜底。按 AGENTS.md §4 "**无 delete-when 的兼容分支 = 红灯**",v1 legacy 路径无 owner、无 delete-when、无消费者(生产 100% v2 plan),同 PR 删。如果将来老 declarative plan 需要回来,新增 ADR 走原流程。

### 10.6 Why not 把 `think.gate` 改成"先消费 decision,enforce 后再写回决策 provider port"?

`PortRegistry` typed 闭集只允许 `PortName` Literal 里的字段。"决策 provider port" 不在闭集里——因为它本身就是 `decision`。**正确的语义是:gate 是 decision 的一个 transformer,不是 decision 的另一个人**。这就是数据流断裂的根因,fix 方式是承认"gate 之后仍是 decision"。

### 10.7 Why not 保留 `_drive_subgraph_ref` 在 interpreter,只删除 `_drive_subgraph_inner`?

`_drive_subgraph_ref` 在 interpreter.py L740-820 是 outer 边级 subgraph 调用点,职责是"interpreter 接到边级 subgraph 时调用";与 `_drive_subgraph_inner`(v1 stub)是两个不同 seam。`_drive_subgraph_ref` 保留,内部委派 `subgraph_runner.run()`(§6.3)。

### 10.8 Why not 整套方案分多 ADR?

ADR-0217 / ADR-0218 已经分别引入 BundleGraphSpec v2 + NodeGraphDriver v2,但**留下了 5 个异味点**(interpreter 业务知识 / 字符串 key 共享 / 裸 dict PortContext / gate 数据流 / 双 seam 重复)。分多 ADR = 评审多次 = 评审者无法看到"五件事是一件事"。一份 super-ADR 一次性收口。

### 10.9 Why not 把 `PhaseResult.result_kind` 改成 enum 替换 `str`?

试过(`phase_result_kind.py` 初版),发现会迫使全网重写 30+ 调用点("decision" / "observation" / "control" / "phase_error" 等都是领域字符串)。**范围远超 H6 根因**,且不解决 H6(根因是 interpreter 私有 `"think_stage"` 字面,不是"result_kind 不 typed")。本 ADR §3.3 改为"只删 interpreter 私有字面,保留领域 result_kind 字符串"——最小改动,根因覆盖。

### 10.10 Why not 在 `_shared/typed_payload.py` 放 `upstream_decision` / `upstream_observation` / `upstream_reflection` 三个 helper?

试过(`lca/plugins/loop/phase/_shared/typed_payload.py` 初版,内含三个函数)。用户评审回"**太丑**":三个 helper 名字隐去 phase 来源,reader 调用时不知道数据从哪个 phase 出来;等于把"`artifacts.get('think')` 字符串 key"换了个更长的函数名,**反模式没真去掉**。改成 `PhaseContext` Protocol 的 `payload_of(phase, want)` 方法,数据流显式留在调用点,无 helper 命名税。删除 helper 文件,`grep -n 'upstream_\|typed_payload' lca/` = 0。

---

## 11. delete-when 总览(可观察的状态)

| 条件 | 命令 / 文件 | 通过条件 |
|---|---|---|
| interpreter 0 个 `SemanticPhase` 字面 | `grep -n 'SemanticPhase\.' lca/framework/declarative/plugins/interpreter.py` | 0 |
| interpreter 0 个 `*_stage` 字面 | `grep -rn '_stage' lca/framework/declarative/plugins/interpreter.py` | 0 |
| `RestrictedPhaseContext` 无 `artifacts` 字段 | `grep -n 'artifacts' lca/harness/declarative/lifecycle/phase_context.py` | 0 字段定义;仅历史注释 |
| 下游 0 个 `artifacts.get("think")` | `grep -rn 'artifacts\.get("think")' lca/plugins/` | 0 |
| `PortRegistry` typed 闭集 | `mypy --strict lca/contracts/.../ports.py` | 0 error |
| `node_graph_driver.py` ≤ 250 行 | `wc -l lca/framework/subgraph/plugins/node_graph_driver.py` | ≤ 250 |
| `_drive_subgraph_inner` 删除 | `grep -n '_drive_subgraph_inner' lca/framework/declarative/plugins/interpreter.py lca/framework/subgraph/plugins/node_graph_driver.py` | 0 |
| `enforced_decision` / `think_signal` 0 出现 | `grep -rn 'enforced_decision\|think_signal' lca/ lca/plugins/` | 0 |
| H6 端到端通过 | `./scripts/lca-ops runs create --user-text "ping" --wait --json` | run `success` |
| 5 个 phase + think subgraph 测试全过 | `pytest tests/think/ tests/harness/graph/execute/ tests/declarative/test_phase_graph.py tests/contracts/test_subgraph_reference_contract.py` | 全过 |

当且仅当上述 10 条全过,本 ADR 升级 Accepted。

---

## 12. 关系链

**Builds on:**
- ADR-0075(declarative phase graph SSOT 根)
- ADR-0195 §4(SSOT 矩阵 + C13 信息血统闭合)
- ADR-0217(BundleGraphSpec v2 + FactoryRegistry)
- ADR-0218(v2 NodeGraphDriver + Adapter 模式)
- [notes/implemented/contract/2026-09-09-phase-node-sub-spec-ref.md](../notes/implemented/contract/2026-09-09-phase-node-sub-spec-ref.md)(节点级 sub_spec_ref)
- [notes/implemented/contract/2026-09-10-bundle-graph-schema-v2.md](../notes/implemented/contract/2026-09-10-bundle-graph-schema-v2.md)(BundleGraphSpec + NodeExecutor)

**Refines:**
- `GenericPlanInterpreter._drive` sub_spec_ref 分支(interpreter.py L402-480)
- `GenericPlanInterpreter._drive_subgraph_inner`(interpreter.py L820-907,整段删)
- `NodeGraphDriver._drive_subgraph_ref` + `_drive_subgraph_inner`(node_graph_driver.py L331-378 + L361-378,前者移 runner,后者删)
- `phase_governance._contribution_context`(phase_governance.py L131-170)
- `RestrictedPhaseContext` 字段形状(lca/harness/declarative/lifecycle/phase_context.py)
- `PortContext` → `PortRegistry`(lca/harness/graph/execute/v2/_port_context.py)
- `think.gate` 数据流(lca/plugins/think/gate.py L50-72)

**Supersedes:** 无(本 ADR 是收编,不是替代;0217/0218 保留作为本 ADR 的 build-on)

**Reject:**
- 「只修 `think.gate` 数据流」(§10.1)
- 「`artifacts` 改 `dataclass`」(§10.2)
- 「interpreter 直接 typed fold,不要辅助函数」(§10.3)
- 「保留 `enforced_decision` / `think_signal`」(§10.4)
- 「保留 v1 legacy `GraphAssembler + inner drive`」(§10.5)
- 「把 `_drive_subgraph_ref` 一起删」(§10.7)
- 「整套方案分多 ADR」(§10.8)
- 「`PhaseResult.result_kind` 改 enum 替 `str`」(§10.9)
- 「`_shared/typed_payload.py` 放 `upstream_decision` / `upstream_observation` / `upstream_reflection`」(§10.10)

---

## 13. 编号

**0219**