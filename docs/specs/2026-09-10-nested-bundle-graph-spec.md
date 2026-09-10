# Nested BundleGraphSpec v2 — 任意嵌套子图与节点级 EP 声明

**版本:v1.0-draft**
**基于:main @ `8e552cc` 实际代码 + ADR-0217 Accepted**
**关联 ADR:** [ADR-0217](../adr/0217-bundle-graph-schema-v2.md) · [ADR-0218](../adr/0218-bundle-graph-v2-subgraph-driver.md)
**关联 Note:** [2026-09-09-phase-node-sub-spec-ref.md](../notes/implemented/contract/2026-09-09-phase-node-sub-spec-ref.md) · [2026-09-10-bundle-graph-schema-v2.md](../notes/implemented/contract/2026-09-10-bundle-graph-schema-v2.md) · [2026-09-11-v2-subgraph-driver.md](../notes/implemented/contract/2026-09-11-v2-subgraph-driver.md)

---

## 0. 第一原理:v1 要解决的真正问题

### 0.1 已知能力(v0,depth=1)

ADR-0217 + Note `2026-09-09`/`2026-09-10`/`2026-09-11` 已经把 think 子图落地为 BundleGraphSpec v2:

- 5 节点 + 5 边的纯图描述在 `bundles/think.yaml`
- 节点级 `sub_spec_ref`(interpreter 进入节点时下沉到子图)
- `binding_edge`(必须 == 节点 id,走完子图后返回该节点)
- `MAX_SUBGRAPH_DEPTH=4` 硬限(节点级 + 边级共享)
- `bundles/reflect-subgraph.yaml` 仍是 entries 形态(legacy fixture)
- `phase.think.standard` 已 deprecated,下个 PR 删除

### 0.2 v1 要解决的三个缺口

| 缺口 | 现状 | v1 之后 |
|---|---|---|
| **嵌套深度硬限** | `MAX_SUBGRAPH_DEPTH=4`,depth>1 未验证 | 任意深度 N(软限,默认 8),PG-007-depth + PG-007-cycle 检测 |
| **节点内流程被 Python 顺序代码遮蔽** | `run_reasoner_with_spine_facts` 在 1 个 seam 函数里硬编码 3 步 + 4 个 EP | `think.reason` 内部拆为 3 节点 inner_graph,执行顺序由 `bundles/think_reason.yaml` 声明 |
| **EP 投递与节点动作耦合** | 5 个 emit 在 seam 函数里 try/except + contextlib.suppress,executor 不参与但也无法独立观测 | 节点 `config.emit_on_enter / emit_on_exit` 声明 EP,driver 在节点 enter/exit 自动发;executor 不感知 EP |

### 0.3 目标不变量

v1 完成后,以下不变量必须成立:

1. **I1 — 节点即图描述符**:任何节点都可以通过 `sub_spec_ref` 携带 inner_graph,inner_graph 与外层图使用**完全相同的 BundleGraphSpec v2 schema**,无新格式。
2. **I2 — 节点 = 1 capability → 1 action**:executor 始终是 9–13 行薄壳,只调 1 个 capability,不调 EP、不写 state、不感知 outer graph。
3. **I3 — EP 是图描述的一部分**:EP 由 `node.config.emit_on_enter / emit_on_exit` 声明,driver 调度,executor 不参与。
4. **I4 — 单一图格式**:不引入 `inner_graph` / `nested_graph` / 第三种 schema;复用 `sub_spec_ref`。
5. **I5 — C11 事件闭集不破**:5 个 reasoner/prompt_assembler EP 全部沿用现有白名单,只换触发点;`EXECUTION_POINTS` 不增不减。
6. **I6 — 现有 68 个测试不退化**:think 17 + subgraph 35 + declarative 16 = 68 个测试必须全部通过。

### 0.4 不做(显式边界)

- ❌ 不新增 `inner_graph` 字段(用现有 `sub_spec_ref`)
- ❌ 不引入 `return_to` 字段(沿用 `binding_edge = node.id`,driver 走完 inner_graph 自动返回)
- ❌ 不动 `bundles/think-cordis.yaml`(从未存在,plugin 注册走 5 个 `@plugin(...)` 装饰器)
- ❌ 不删 `phase.think.standard` 退役路径(独立 PR)
- ❌ 不改 `bundles/reflect-subgraph.yaml`(仍是 entries 形态,独立 PR)
- ❌ 不改 `bundles/think.yaml` 中 5 节点以外的节点(只动 `think.reason` 一个节点)
- ❌ 不改 `lca/plugins/think/route.py` 的双职责(上一轮已经识别但不在 v1 范围)

---

## 1. 现状代码基线(精确定位)

### 1.1 现有 `think.reason` 节点(9 行薄壳)

```python
# lca/plugins/think/reason.py
async def node_execute(self, context, input):
    reasoner = context.runtime.reasoner
    state = context.runtime.state
    if reasoner is None or state is None:
        return NodeOutput(port_values={})
    response = await run_reasoner_with_spine_facts(reasoner, state)
    return NodeOutput(port_values={"response": response})
```

### 1.2 委托的 seam 函数(全部内部逻辑)

```python
# lca/infrastructure/session/emit/cognitive_emit.py:383-432
async def run_reasoner_generate_thoughts_with_spine_facts(reasoner, state):
    # Step 1: build_turn_plan(state)           — 纯计算
    # Step 2: emit prompt_assembler_start       — EP
    # Step 3: render_turn(state, plan)          — 纯计算
    # Step 4: emit prompt_assembler_end         — EP (success/failure)
    # Step 5: emit reasoner_meta                — EP
    # Step 6: emit reasoner_reason_start        — EP
    # Step 7: complete_turn(state, render)      — ★ 唯一调 LLM
    # Step 8: emit reasoner_reason_end          — EP (success/failure)
```

### 1.3 现有 5 个 EP 函数(全部不动)

| EP 函数 | 位置 | v1 触发点变化 |
|---|---|---|
| `emit_prompt_assembler_start_for_state` | cognitive_emit.py | v1 不触发(plan emit_on_exit=[]) |
| `emit_prompt_assembler_end_for_state` | cognitive_emit.py | 移到 `think.reason.render` exit |
| `_emit_reasoner_meta_from_render` | cognitive_emit.py(私有) | 移到 `think.reason.render` exit |
| `emit_reasoner_reason_start_for_state` | cognitive_emit.py | 移到 `think.reason.complete` enter |
| `emit_reasoner_reason_end_for_state` | cognitive_emit.py | 移到 `think.reason.complete` exit |

### 1.4 现有 68 个测试基线

按 `2026-09-11-v2-subgraph-driver.md` §Testing:`tests/think/` 17 + `tests/contracts/test_subgraph_reference_contract.py` + `tests/harness/graph/execute/test_interpreter_subgraph.py` + `tests/declarative/test_phase_graph.py` = 35;`tests/contracts/test_phase_node_pr_c.py` 22 = **总计 68 passed,1 baseline failed**(`test_bundle_subgraph_resolver.py` 引用已删除 bundle,与本 PR 无关)。

---

## 2. v1 详细设计

### 2.1 schema 扩展(同 PR 闭环)

ADR-0217 §3.3 patch,新增三个子章节。**全部为可选字段,默认值与 v0 一致**。

#### 2.1.1 节点 `config.emit_on_enter / emit_on_exit` 字段

```python
# lca/contracts/protocols/declarative/declarative_1/bundle_graph.py
@dataclass(frozen=True, slots=True)
class BundleGraphNode:
    id: str
    region: str
    factory: str
    purpose: str | None = None
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    config: Mapping[str, object] = field(default_factory=dict)
    # v1 新增(可选):
    #   config["emit_on_enter"]: list[str]   ← 节点 enter 时 driver 自动发的 EP 列表
    #   config["emit_on_exit"]:  list[str]   ← 节点 exit 时 driver 自动发的 EP 列表
    # 默认空列表,行为等价 v0。
```

**EP 列表元素必须是 `EXECUTION_POINTS` 白名单中的字符串**(由 `emit_for_node` dispatcher 路由)。**C11 事件闭集不破**:`EXECUTION_POINTS` 白名单不动,5 个 EP 全部已有。

#### 2.1.2 driver 任意嵌套深度

```python
# lca/harness/graph/execute/v2/node_graph_driver.py
MAX_SUBGRAPH_DEPTH_DEFAULT = 8   # v1 默认;v0 硬限 4 改为软限

async def _drive_subgraph_ref(self, ref, outer_state, depth=0):
    if depth > self.max_subgraph_depth:           # 默认 8,可由 profile config 覆盖
        raise SubgraphDepthExceededError(depth)   # PG-007-depth
    # cycle detection: 同 plan_ref 在递归栈出现第二次 → PG-007-cycle
    if ref.plan_ref in self._recursion_stack:
        raise SubgraphCycleError(ref.plan_ref)    # PG-007-cycle
    self._recursion_stack.add(ref.plan_ref)
    try:
        return await self._drive_inner(ref, outer_state, depth)
    finally:
        self._recursion_stack.discard(ref.plan_ref)
```

#### 2.1.3 端口同名透传

```python
# lca/harness/graph/execute/v2/_port_context.py
def exit_subgraph(self, outer_outputs: tuple[str, ...]) -> dict[str, object]:
    """inner_graph 终止时,把同名端口值透传到 outer PortContext。"""
    outer_input = {}
    for port in outer_outputs:
        if port in self.inner_port_values:
            outer_input[port] = self.inner_port_values[port]
    return outer_input
```

**铁律**:

- 端口同名透传(铁律 1):inner_graph 终止端口名 ∈ outer 节点 `outputs` → 透传
- 缺失输入 = 空 NodeOutput(铁律 2):driver 不报错
- 同图同名端口冲突 = PG-006-port-conflict(铁律 3):编译期 fail-loud
- 跨子图端口不互通(铁律 4):inner_graph 局部 PortContext,终止时销毁

### 2.2 三个新 executor

#### 2.2.1 `lca/plugins/think/reason_plan.py`

```python
@dataclass(frozen=True, slots=True)
class ThinkReasonPlanExecutor:
    semantic_name: str = "think.reason.plan"
    region: str = "phase:think"

    async def node_execute(self, context, input):
        reasoner = context.runtime.reasoner
        state = context.runtime.state
        if reasoner is None or state is None:
            return NodeOutput(port_values={})
        plan = reasoner.build_turn_plan(state)
        return NodeOutput(port_values={"turn_plan": plan})
```

#### 2.2.2 `lca/plugins/think/reason_render.py`

```python
@dataclass(frozen=True, slots=True)
class ThinkReasonRenderExecutor:
    semantic_name: str = "think.reason.render"
    region: str = "phase:think"

    async def node_execute(self, context, input):
        reasoner = context.runtime.reasoner
        state = context.runtime.state
        plan = input.port_values.get("turn_plan")
        if reasoner is None or state is None or plan is None:
            return NodeOutput(port_values={})
        render = reasoner.render_turn(state, plan)
        return NodeOutput(port_values={"turn_render": render})
```

#### 2.2.3 `lca/plugins/think/reason_complete.py`

```python
@dataclass(frozen=True, slots=True)
class ThinkReasonCompleteExecutor:
    semantic_name: str = "think.reason.complete"
    region: str = "phase:think"

    async def node_execute(self, context, input):
        reasoner = context.runtime.reasoner
        state = context.runtime.state
        render = input.port_values.get("turn_render")
        if reasoner is None or state is None or render is None:
            return NodeOutput(port_values={})
        response = await reasoner.complete_turn(state, render)
        return NodeOutput(port_values={"response": response})
```

**每个 executor 9–11 行薄壳**,**不 import emit,不感知 EP**,**不写 state**(沿用 `state_mutation: "forbidden"` `@plugin(...)` 装饰器声明)。

### 2.3 EP dispatcher(`lca/loop/emit/node_emitter.py`,新文件)

```python
"""Node-level EP dispatcher for BundleGraphSpec v2 (ADR-0217 §3.3.2).

Maps emit_on_enter / emit_on_exit config keys to existing FactGateway
emit functions. Executor plugins MUST NOT import this module.
"""
from __future__ import annotations
import contextlib
from typing import Any

from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.emit.cognitive_emit import (
    emit_prompt_assembler_end_for_state,
    emit_prompt_assembler_start_for_state,
    emit_reasoner_reason_end_for_state,
    emit_reasoner_reason_start_for_state,
)

_EP_DISPATCH: dict[str, Any] = {
    "prompt_assembler_start": emit_prompt_assembler_start_for_state,
    "prompt_assembler_end":   emit_prompt_assembler_end_for_state,
    "reasoner_meta":          None,  # 私有 helper,见 emit_reasoner_meta_for_node
    "reasoner_reason_start":  emit_reasoner_reason_start_for_state,
    "reasoner_reason_end":    emit_reasoner_reason_end_for_state,
}


def emit_for_node(ep_id: str, state: AgentState, **kwargs) -> None:
    """Dispatch one EP by id with contextlib.suppress(Exception)."""
    fn = _EP_DISPATCH.get(ep_id)
    if fn is None:
        return  # 未知 EP 静默忽略(driver 不参与 EP 词表维护)
    with contextlib.suppress(Exception):
        fn(state, **kwargs)
```

**`reasoner_meta` 走专门 helper**(因为 `_emit_reasoner_meta_from_render` 当前是私有函数,接受 `plan` + `render` 两个参数):

```python
# lca/loop/emit/node_emitter.py
def emit_reasoner_meta_for_node(state, plan, render) -> None:
    with contextlib.suppress(Exception):
        _emit_reasoner_meta_from_render(plan, render)
```

### 2.4 driver 改动(伪代码,标定 patch 位置)

```python
# lca/harness/graph/execute/v2/node_graph_driver.py — _drive_node 内
async def _execute_with_emits(self, node, node_input):
    # 进入:发 emit_on_enter
    for ep_id in node.config.get("emit_on_enter", []):
        emit_for_node(ep_id, state)

    try:
        output = await node.executor.node_execute(self.context, node_input)
    except BaseException:
        # 失败:reasoner_reason_end 必须发 outcome=failure
        for ep_id in node.config.get("emit_on_exit", []):
            if ep_id == "reasoner_reason_end":
                emit_for_node(ep_id, state, outcome="failure")
            # 其他 end EP 由具体节点 executor 失败语义决定,本版不强制
        raise

    # 成功:发 emit_on_exit
    for ep_id in node.config.get("emit_on_exit", []):
        emit_for_node(ep_id, state)
    return output
```

### 2.5 `bundles/think_reason.yaml`(新文件,完整形态)

```yaml
id: think.reason.subgraph
region: phase:think
purpose: think.reason 内部 3 步执行 — plan → render → complete

nodes:
  - id: think.reason.plan
    factory: think.reason.plan
    inputs: []
    outputs: [turn_plan]
    config:
      max_visits: 1
      emit_on_enter: []
      emit_on_exit:  []

  - id: think.reason.render
    factory: think.reason.render
    inputs: [turn_plan]
    outputs: [turn_render]
    config:
      max_visits: 1
      emit_on_enter: []
      emit_on_exit:  [prompt_assembler_end, reasoner_meta]

  - id: think.reason.complete
    factory: think.reason.complete
    inputs: [turn_render]
    outputs: [response]
    config:
      max_visits: 3   # ★ 唯一允许 max_visits > 1,LLM 重试在 inner_graph 内消化
      emit_on_enter: [reasoner_reason_start]
      emit_on_exit:  [reasoner_reason_end]

edges:
  - from: think.reason.plan
    to: think.reason.render
    when: true
  - from: think.reason.render
    to: think.reason.complete
    when: true
  # 终止:think.reason.complete 走完,driver 沿 binding_edge=think.reason 返回外层
```

### 2.6 `bundles/think.yaml` 改动(只动 think.reason 一个节点)

```yaml
nodes:
  # ... 4 个原节点不变 ...

  # ★ v1 改动:think.reason 加 sub_spec_ref
  - id: think.reason
    factory: think.reason
    inputs: [in_assembled_manifest]
    outputs: [response]                      # 与 inner_graph 终止端口同名 → 透传
    config:
      max_visits: 8                          # outer 级别,控制 inner_graph 进入次数
      sub_spec_ref:                          # ★ v1 新增
        plan_ref: bundles/think_reason.yaml
        entry_node: think.reason.plan
        binding_edge: think.reason           # 必须 == node.id,沿用 v0
      emit_on_enter: []
      emit_on_exit:  []

# edges 完全不变(driver 自动处理 sub_spec_ref)
```

### 2.7 数据流(从 LLM 调用角度看)

```text
1. outer driver 进入 think.reason 节点
2. driver 看到 sub_spec_ref → 进入 inner_graph(think_reason.yaml)
3. driver 进入 think.reason.plan
   - executor: reasoner.build_turn_plan(state) → ReasonerTurnPlan
   - emit_on_enter=[] / emit_on_exit=[] → 不发 EP
4. driver 沿 plan→render 边过渡,when=true 直接走
5. driver 进入 think.reason.render
   - executor: reasoner.render_turn(state, plan) → ReasonerTurnRender
   - emit_on_enter=[] → 不发 EP
   - emit_on_exit=[prompt_assembler_end, reasoner_meta] → driver 自动发 2 个 EP
6. driver 沿 render→complete 边过渡,when=true 直接走
7. driver 进入 think.reason.complete
   - emit_on_enter=[reasoner_reason_start] → driver 自动发 start EP
   - executor: await reasoner.complete_turn(state, render) → LLMResponse
   - emit_on_exit=[reasoner_reason_end] → driver 自动发 end EP(success/failure)
8. inner_graph 终止 → driver 沿 binding_edge=think.reason 返回外层
9. 端口 `response` 透传到 outer PortContext
10. outer driver 沿 think.reason→think.classify 边过渡,when=true 直接走
11. think.classify 读 response 端口(已透传)→ 输出 decision
```

### 2.8 错误处理矩阵

| 失败位置 | 错误类型 | driver 行为 | EP 行为 |
|---|---|---|---|
| plan 失败 | 确定性 | 不重试,抛异常 | 不发 EP |
| plan 失败 | 瞬时 | 按 phase execution policy 重试 | 不发 EP |
| render 失败 | 确定性 | 不重试,抛异常 | driver 失败路径**不强制发 prompt_assembler_end(failure)**,由原 executor 失败语义决定;v1 不强化 |
| render 失败 | 瞬时 | 重试 | 同上 |
| complete 失败 | LLM 错误(瞬时) | **节点内重试 max_visits=3** | 每次失败:start/failure EP 配对 |
| complete 失败 | LLM 错误(确定性) | 不重试,抛异常 | start/failure EP 配对 |
| inner_graph 超过 max_subgraph_depth | N/A | PG-007-depth fail-loud | N/A |
| inner_graph 同 plan_ref 在递归栈出现第二次 | N/A | PG-007-cycle fail-loud | N/A |

### 2.9 状态传递

| 状态 | 传递方式 | 谁负责 |
|---|---|---|
| `AgentState` | driver 通过 `runtime.state` 透传,所有节点共享同一引用 | 不变 |
| `port_values` | driver 在 inner_graph 入口建立局部 PortContext,出口销毁(同名端口透传) | 新约定 |
| `ReasonerTurnPlan` / `ReasonerTurnRender` | 走 inner_graph 内部 port_values | 新约定 |
| `LLMResponse` | inner_graph 端口 `response` → outer 端口 `response` 同名透传 | 铁律 1 |
| Budget | outer budget - 1 传给 inner,inner 用尽即停 | 不变 |
| State mutation | 所有 3 个新 plugin 装饰器声明 `state_mutation: "forbidden"` | ADR-0218 §3.3 |

### 2.10 ADR-0217 升级 patch(必须同 PR)

```text
ADR-0217 §3.3 patch:
  - 新增子章节 "3.3.1 Nested sub_spec_ref 任意深度"
    - max_depth 从硬限 4 改为软限(可配置,默认 8)
    - cycle 检测:同 plan_ref 嵌套超过 max_depth 时 PG-007-cycle
    - budget 递减:outer budget - 1 传给 inner,inner 用尽即停
  - 新增子章节 "3.3.2 节点 emit 声明"
    - node.config 新增字段 emit_on_enter / emit_on_exit (list[str])
    - driver 在节点 enter/exit 时按列表发 EP
    - executor 不知道 EP 存在
  - 新增子章节 "3.3.3 端口同名透传"
    - inner_graph 终止端口名 ∈ outer 节点 outputs 字段 → 透传
    - 同名冲突 → PG-006-port-conflict
    - inner_graph 局部 PortContext 终止时销毁
```

### 2.11 `run_reasoner_with_spine_facts` seam 退役路径

**v1 不删**,标 `.. deprecated::` + 在 `lca/loop/emit/cognitive/reasoner.py` 顶部 docstring 加:

```text
delete-when:
  1. 所有 phase graph driver 都走 v2(NOT v0 GraphAssembler fallback)
  2. 节点级 sub_spec_ref 在 prod profile 落地(think-subgraph-dev 已用)
  3. think.reason inner_graph 拆解已落地(本 PR)
  4. 至少 1 个 prod profile 跑通 3 个月,期间无 seam fallback 触发
  owner: lca/loop/emit/cognitive/reasoner.py 维护者
  validation: 条件 1-3 已满足;条件 4 由 owner 评估
```

---

## 3. 测试矩阵

### 3.1 单元测试(per executor,共 3 文件 12–15 个 case)

| 测试文件 | 测试点 |
|---|---|
| `tests/think/test_reason_plan_phase_plugin.py` | 1. executor 调 `reasoner.build_turn_plan` 1 次;2. 返回 NodeOutput 含 `turn_plan`;3. 注入 None reasoner 返回空;4. 注入 None state 返回空;5. **不调任何 emit 函数** |
| `tests/think/test_reason_render_phase_plugin.py` | 1. executor 调 `reasoner.render_turn` 1 次;2. 上游 port 缺 `turn_plan` 返回空;3. 注入 None reasoner 返回空;4. **不调任何 emit 函数** |
| `tests/think/test_reason_complete_phase_plugin.py` | 1. executor `await reasoner.complete_turn` 1 次;2. 上游 port 缺 `turn_render` 返回空;3. 注入 None reasoner 返回空;4. **不调任何 emit 函数** |

### 3.2 集成测试(driver + emit dispatcher + 内层子图,共 12 个 case)

| 测试文件 | 测试点 |
|---|---|
| `tests/harness/graph/execute/test_inner_subgraph_driver.py` | 1. driver 进入 think.reason → 自动进入 inner_graph;2. driver 走完 inner_graph → 自动返回外层;3. inner_graph 失败 → outer result_kind=phase_error;4. **PG-007-cycle:同 plan_ref 嵌套 9 层 fail-loud** |
| `tests/harness/graph/execute/test_node_emit_dispatcher.py` | 1. emit_on_exit=[X,Y] → driver 走完后调 X,Y 各 1 次;2. 节点失败 → end EP 用 outcome=failure;3. emit_for_node(未知 ep_id) → 静默忽略;4. **executor 不接收 emit 相关参数** |
| `tests/harness/graph/execute/test_port_naming.py` | 1. inner_graph 终止端口 == outer outputs → 透传成功;2. 同 BundleGraphSpec 内同名 outputs → PG-006 fail-loud;3. inner_graph 内部端口不污染 outer |
| `tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py` | 1. 加载 `bundles/think_reason.yaml` 真实文件;2. driver 跑完 plan→render→complete 全流程;3. **4 个** EP 按节点 emit 配置发出(顺序匹配 §2.7;`prompt_assembler_start` 按 §0.4 边界不触发);4. 端口 `response` 透传到 outer |

### 3.3 回归测试(68 个测试必须全部通过)

| 测试组 | 命令 | 预期 |
|---|---|---|
| think 5 步老测试 | `pytest tests/think/ -v` | 17 passed |
| subgraph 契约 | `pytest tests/contracts/test_subgraph_reference_contract.py tests/harness/graph/execute/test_interpreter_subgraph.py tests/declarative/test_phase_graph.py -v` | 全部 passed |
| declarative 全套 | `pytest tests/contracts/ tests/declarative/ -v` | 全部 passed |
| 端到端 | `pytest tests/e2e/test_declarative_long_horizon_recovery.py -v` | passed |

### 3.4 E2E(必跑)

| 项 | 命令 | 预期 |
|---|---|---|
| 端到端 think 子图 | `./scripts/lca-ops runs create --user-text "hello" --profile profiles/think-subgraph-dev.yaml` | run_id 创建成功,spine trace 含 think.reason.plan/render/complete 三个 inner 节点 trace |
| 5 个 EP 投递顺序 | `jq '.events[] \| select(.event_type \| startswith("reasoner") or startswith("prompt_assembler"))' traces/runs/<run_id>.spine.jsonl` | 顺序匹配 §2.7 |
| max_visits 限制 | 注入 fake failing reasoner,complete 失败 3 次 | driver 第 4 次进入 fail-loud |
| cycle 检测 | 构造 self-referencing sub_spec_ref | PG-007-cycle fail-loud |

### 3.5 反向断言(必须主动验证失败场景)

| 反向断言 | 命令 | 预期(必须 fail) |
|---|---|---|
| 三个 executor 不能 import emit | `grep -r "from lca.infrastructure.session.emit" lca/plugins/think/reason_*.py` | 必须 0 行 |
| `think_reason.yaml` 不能写 plugin_id | `grep -E "\\\$module\|plugin_id\|entries:" bundles/think_reason.yaml` | 必须 0 行 |
| `emit_on_exit` 不能用未知 EP | 构造 `emit_on_exit: [unknown_ep]` 跑测试 | fail-loud |

### 3.6 lint/format/mypy 基线

| 命令 | 必须结果 |
|---|---|
| `ruff check lca/plugins/think/reason_*.py lca/loop/emit/node_emitter.py tests/think/test_reason_*.py tests/harness/graph/execute/test_node_emit_dispatcher.py` | **零新增错误**(允许 baseline 持平) |
| `mypy lca/plugins/think/reason_*.py lca/loop/emit/node_emitter.py` | **零新增错误**(允许 baseline 持平) |
| `git diff --check` | 必须空 |
| `./scripts/lca-ops audit-plugin-shape` | 必须通过 |

---

## 4. 实施 PR 计划(预估 3 PR,顺序依赖)

### PR-1:driver 任意嵌套深度(独立于 think.reason)

- `lca/harness/graph/execute/v2/node_graph_driver.py`:递归深度软限,cycle 检测
- `lca/harness/graph/execute/v2/_port_context.py`:端口同名透传
- 新增错误码:
  - `PG-007-depth`(`SubgraphDepthExceededError`,§2.1.2)
  - `PG-007-cycle`(`SubgraphCycleError`,§2.1.2)
  - `PG-006-port-conflict`(端口同名冲突,§2.1.3 铁律 3)
- 新增 `tests/harness/graph/execute/test_inner_subgraph_driver.py` 4 case
- 风险:中等(driver 状态机改动),验证用现有 think.yaml + reflect-subgraph.yaml 双 fixture

### PR-2:节点级 emit 声明

- `lca/contracts/protocols/declarative/declarative_1/bundle_graph.py`:BundleGraphNode.config 字段接受 emit_on_enter / emit_on_exit
- 新增 `lca/loop/emit/node_emitter.py`(~50 行 dispatcher)
- `lca/harness/graph/execute/v2/node_graph_driver.py`:节点 enter/exit 调 emit_for_node
- 新增 `tests/harness/graph/execute/test_node_emit_dispatcher.py` 4 case
- 风险:低(纯增量字段,默认空列表 → 行为等价 v0)

### PR-3:think.reason 拆解为 inner_graph

- 新增 `lca/plugins/think/reason_plan.py` + `reason_render.py` + `reason_complete.py`
- 新增 `bundles/think_reason.yaml`
- `bundles/think.yaml`:think.reason 节点加 `sub_spec_ref` + `emit_on_exit: []`
- 新增 `tests/think/test_reason_*_phase_plugin.py` 12 case
- 新增 `tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py` 4 case
- `lca/loop/emit/cognitive/reasoner.py`:run_reasoner_with_spine_facts 标 deprecated + delete-when 注释
- 风险:低(driver 已支持,只是 yaml + 3 个新 plugin 增量)

### PR 顺序约束

- PR-1 必须先于 PR-2(emit dispatcher 依赖 cycle/depth 检测就绪)
- PR-2 必须先于 PR-3(think.reason inner_graph 用 emit_on_exit)
- PR-1 / PR-2 可以独立合,PR-3 是端到端验证

---

## 5. 验收标准

v1 完成 = 以下全部为真:

1. ✅ ADR-0217 §3.3 patch 已写入(含 §3.3.1/§3.3.2/§3.3.3 三个子章节)
2. ✅ `bundles/think_reason.yaml` 存在且为 BundleGraphSpec v2 形态
3. ✅ `bundles/think.yaml` think.reason 节点带 sub_spec_ref,emits 配置为 `emit_on_enter: []` / `emit_on_exit: []`
4. ✅ 3 个新 plugin 文件存在,各 9–11 行薄壳,**不 import emit**
5. ✅ `lca/loop/emit/node_emitter.py` 存在并对外暴露 `emit_for_node` + `emit_reasoner_meta_for_node`
6. ✅ 68 个现有测试全部 passed,无新增 baseline failure
7. ✅ 新增 25–28 个测试(3 文件 12–15 单元 case + 4 文件 12 集成 case)全部 passed
8. ✅ `pytest tests/think/ tests/harness/graph/execute/test_*subgraph* tests/harness/graph/execute/test_*emit* tests/harness/graph/execute/test_*port* tests/contracts/test_subgraph_reference_contract.py tests/declarative/test_phase_graph.py -v` 全过
9. ✅ `./scripts/lca-ops audit-plugin-shape` 通过
10. ✅ `ruff check` + `mypy` 零新增错误
11. ✅ `git diff --check` 空
12. ✅ 端到端 run 跑通,spine trace 含 3 个 inner 节点 trace
13. ✅ `run_reasoner_with_spine_facts` 标 deprecated,delete-when 注释完整

---

## 6. 删除条件(delete-when)

本 spec 在以下条件全部满足时归档到 `history/2026-MM/`:

1. v1 已在生产 profile(think-subgraph-dev / web-standard)跑通 ≥ 3 个月
2. PR-1 / PR-2 / PR-3 全部合入 main
3. ADR-0217 §3.3 patch 已生效
4. 至少 1 个生产 run 完成端到端验证
5. `run_reasoner_with_spine_facts` seam 退役路径已删除(由独立 PR 处理)

owner: spec 作者 + lca/loop/emit/cognitive/reasoner.py 维护者
validation: 上述条件全部成立时由 owner 归档
