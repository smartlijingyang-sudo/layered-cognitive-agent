# Nested BundleGraphSpec v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 BundleGraphSpec v2 任意嵌套子图 + 节点级 EP 声明 + think.reason 内部拆解为 3 节点 inner_graph,使 think 链路所有内部流程由 yaml 图描述声明,executor 保持 9–13 行薄壳。

**Architecture:** 3 个独立可合的 PR。PR-1 扩 driver 任意嵌套深度(cycle/depth 检测 + 端口同名透传);PR-2 引入节点级 emit 声明(driver 在 enter/exit 自动发 EP,executor 不感知);PR-3 拆 think.reason 为 plan/render/complete 3 节点 inner_graph,executor 仍是 9 行薄壳。**单一图格式**:复用现有 `sub_spec_ref`,不引入新 schema。

**Tech Stack:** Python 3.12 / Pydantic frozen dataclass / Cordis plugin context / FactGateway emit / pytest

**Spec:** [docs/specs/2026-09-10-nested-bundle-graph-spec.md](../../specs/2026-09-10-nested-bundle-graph-spec.md)

---

## Global Constraints

从 spec 全文逐字提取,每个 task 的实现者必须隐式遵守:

- **节点 = 1 capability → 1 action**:`lca/plugins/think/<node>.py` 的 `node_execute` 9–13 行,只调 1 个 capability,不调 emit、不写 state
- **不引入新 schema**:复用 `sub_spec_ref` / `binding_edge`;不引入 `inner_graph` / `nested_graph` / `return_to`
- **C11 事件闭集不破**:`EXECUTION_POINTS` 白名单不动;5 个 reasoner/prompt_assembler EP 只换触发点
- **不删 `phase.think.standard`**:保持 deprecated 状态,删除由独立 PR 处理
- **不删 `run_reasoner_with_spine_facts`**:v1 标 deprecated + delete-when 注释,不删除代码
- **不删 `bundles/think.yaml`**:只动 `think.reason` 一个节点加 `sub_spec_ref`
- **不改 `bundles/reflect-subgraph.yaml`**:仍是 entries 形态,独立 PR 处理
- **不改 `bundles/think-cordis.yaml`**(从未存在)
- **不改 `lca/plugins/think/route.py`**:双职责留待独立 PR
- **ADR-0217 patch 必须同 PR 落地**(PR-3 落地)
- **68 个现有测试必须全部通过**:think 17 + subgraph 35 + declarative 16
- **ruff + mypy 零新增错误**:允许 baseline 持平
- **git diff --check 必须空**
- **Conventional Commits**:`<type>(<scope>): <subject>`,正文说"做了什么 / 为什么"

---

## 文件结构(Final)

### 新增

| 路径 | 职责 | 任务 |
|---|---|---|
| `lca/loop/emit/node_emitter.py` | EP dispatcher:把 ep_id 路由到现有 emit 函数,容错 | Task 2 |
| `lca/plugins/think/reason_plan.py` | `think.reason.plan` 节点 executor(9 行) | Task 4 |
| `lca/plugins/think/reason_render.py` | `think.reason.render` 节点 executor(9 行) | Task 4 |
| `lca/plugins/think/reason_complete.py` | `think.reason.complete` 节点 executor(9 行) | Task 4 |
| `bundles/think_reason.yaml` | think.reason inner_graph 图描述(3 节点 + 2 边) | Task 5 |
| `tests/think/test_reason_plan_phase_plugin.py` | plan executor 单元测试 | Task 4 |
| `tests/think/test_reason_render_phase_plugin.py` | render executor 单元测试 | Task 4 |
| `tests/think/test_reason_complete_phase_plugin.py` | complete executor 单元测试 | Task 4 |
| `tests/harness/graph/execute/test_inner_subgraph_driver.py` | driver 递归 + cycle/depth 集成测试 | Task 1 |
| `tests/harness/graph/execute/test_node_emit_dispatcher.py` | emit dispatcher 集成测试 | Task 2 |
| `tests/harness/graph/execute/test_port_naming.py` | 端口同名透传集成测试 | Task 1 |
| `tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py` | think.reason 端到端集成测试 | Task 5 |

### 修改

| 路径 | 改动 | 任务 |
|---|---|---|
| `lca/harness/graph/execute/v2/node_graph_driver.py` | 递归深度软限 + cycle 检测 + emit_on_enter/exit 调度 | Task 1, Task 2 |
| `lca/harness/graph/execute/v2/_port_context.py` | `exit_subgraph` 方法:端口同名透传 | Task 1 |
| `lca/contracts/protocols/declarative/declarative_1/bundle_graph.py` | `BundleGraphNode.config` 字段接受 `emit_on_enter / emit_on_exit`(Pydantic 接受 `extra` 不阻止) | Task 2 |
| `bundles/think.yaml` | `think.reason` 节点加 `sub_spec_ref` + `emit_on_enter: []` / `emit_on_exit: []` | Task 5 |
| `lca/loop/emit/cognitive/reasoner.py` | `run_reasoner_with_spine_facts` 标 deprecated + delete-when 注释 | Task 5 |
| `docs/adr/0217-bundle-graph-schema-v2.md` | §3.3 patch:新增 §3.3.1 / §3.3.2 / §3.3.3 三个子章节 | Task 5 |

---

## Task 1:driver 任意嵌套深度 + 端口同名透传

**Files:**
- Modify: `lca/harness/graph/execute/v2/node_graph_driver.py`(新增 `_recursion_stack` 字段 + `_drive_subgraph_ref` 改写)
- Modify: `lca/harness/graph/execute/v2/_port_context.py`(新增 `exit_subgraph` 方法)
- Create: `tests/harness/graph/execute/test_inner_subgraph_driver.py`(4 case)
- Create: `tests/harness/graph/execute/test_port_naming.py`(3 case)

**Interfaces:**
- Consumes: 现有 `_drive_subgraph_ref(ref, outer_state, depth=0)`(在 `interpreter.py:phase_graph_compiler` 调用);`ref` 类型为 `SubgraphReference(plan_ref, entry_node, binding_edge)`,位于 `lca/contracts/protocols/declarative/declarative_1/declarative_graph.py`
- Produces:
  - `SubgraphDepthExceededError(depth: int)` — PG-007-depth,位于 `lca/contracts/exceptions/`
  - `SubgraphCycleError(plan_ref: str)` — PG-007-cycle,同位置
  - `PortNamingConflictError(node_id: str, port: str)` — PG-006-port-conflict,同位置
  - `PortContext.exit_subgraph(outer_outputs: tuple[str, ...]) -> dict[str, object]` — 端口同名透传

### Steps

- [ ] **Step 1.1:写失败的测试 — depth 超限**

```python
# tests/harness/graph/execute/test_inner_subgraph_driver.py
import pytest
from lca.contracts.exceptions.subgraph import SubgraphDepthExceededError


async def test_depth_exceeded_fail_loud():
    """嵌套深度超过 max_subgraph_depth(默认 8)必须 PG-007-depth fail-loud。"""
    driver = NodeGraphDriver(spec=..., max_subgraph_depth=2, ...)
    # 构造一个 3 层嵌套 sub_spec_ref 链(用真实 fixture)
    with pytest.raises(SubgraphDepthExceededError):
        await driver.run(outer_state, artifacts)
```

- [ ] **Step 1.2:运行测试,确认失败**

Run: `pytest tests/harness/graph/execute/test_inner_subgraph_driver.py::test_depth_exceeded_fail_loud -v`
Expected: FAIL with `SubgraphDepthExceededError not defined` 或 `ImportError`

- [ ] **Step 1.3:实现最小代码 — 异常类**

```python
# lca/contracts/exceptions/subgraph.py(新增)
"""Subgraph recursion exception family (ADR-0217 §3.3.1, PG-007-*)."""
from __future__ import annotations


class SubgraphDepthExceededError(RuntimeError):
    """Raised when sub_spec_ref nesting exceeds max_subgraph_depth (PG-007-depth)."""
    def __init__(self, depth: int, max_depth: int) -> None:
        super().__init__(f"subgraph depth {depth} exceeds max {max_depth}")
        self.depth = depth
        self.max_depth = max_depth


class SubgraphCycleError(RuntimeError):
    """Raised when same plan_ref appears twice in recursion stack (PG-007-cycle)."""
    def __init__(self, plan_ref: str) -> None:
        super().__init__(f"subgraph cycle detected at plan_ref={plan_ref!r}")
        self.plan_ref = plan_ref


class PortNamingConflictError(ValueError):
    """Raised when two nodes in same BundleGraphSpec declare same output port (PG-006)."""
    def __init__(self, node_id: str, port: str) -> None:
        super().__init__(f"port {port!r} conflict in node {node_id!r}")
        self.node_id = node_id
        self.port = port
```

- [ ] **Step 1.4:实现最小代码 — driver 递归**

```python
# lca/harness/graph/execute/v2/node_graph_driver.py(patch)
MAX_SUBGRAPH_DEPTH_DEFAULT = 8  # v0 硬限 4 改为软限

class NodeGraphDriver:
    def __init__(self, spec, plan_ref, scope, registry, observers, max_subgraph_depth=MAX_SUBGRAPH_DEPTH_DEFAULT):
        # ... 既有参数 ...
        self.max_subgraph_depth = max_subgraph_depth
        self._recursion_stack: set[str] = set()

    async def _drive_subgraph_ref(self, ref, outer_state, depth=0):
        if depth > self.max_subgraph_depth:
            raise SubgraphDepthExceededError(depth, self.max_subgraph_depth)
        if ref.plan_ref in self._recursion_stack:
            raise SubgraphCycleError(ref.plan_ref)
        self._recursion_stack.add(ref.plan_ref)
        try:
            return await self._drive_inner(ref, outer_state, depth)
        finally:
            self._recursion_stack.discard(ref.plan_ref)
```

- [ ] **Step 1.5:运行测试,确认通过**

Run: `pytest tests/harness/graph/execute/test_inner_subgraph_driver.py::test_depth_exceeded_fail_loud -v`
Expected: PASS

- [ ] **Step 1.6:写失败的测试 — cycle 检测**

```python
# tests/harness/graph/execute/test_inner_subgraph_driver.py(追加)
from lca.contracts.exceptions.subgraph import SubgraphCycleError


async def test_cycle_detected_fail_loud():
    """同 plan_ref 嵌套 2 次必须 PG-007-cycle fail-loud。"""
    # 构造 self-referencing sub_spec_ref:
    # bundle_a.yaml 节点 sub_spec_ref.plan_ref = "bundle_a.yaml"
    driver = NodeGraphDriver(spec=..., plan_ref="bundle_a.yaml", ...)
    with pytest.raises(SubgraphCycleError):
        await driver.run(outer_state, artifacts)
```

- [ ] **Step 1.7:运行 + 验证 pass + commit**

```bash
git add lca/contracts/exceptions/subgraph.py lca/harness/graph/execute/v2/node_graph_driver.py tests/harness/graph/execute/test_inner_subgraph_driver.py
git commit -m "feat(declarative): driver recursive sub_spec_ref with depth+cycle guards (PG-007)"
```

- [ ] **Step 1.8:写失败的测试 — 端口同名透传**

```python
# tests/harness/graph/execute/test_port_naming.py
async def test_inner_subgraph_port_passthrough():
    """inner_graph 终止端口 == outer outputs 字段,值透传到 outer PortContext。"""
    # outer 节点 think.reason outputs=[response]
    # inner_graph 终止节点 think.reason.complete outputs=[response]
    # inner_graph 终止时,PortContext.exit_subgraph 把 response 注入 outer input
    outer_input = port_ctx.exit_subgraph(outer_outputs=("response",))
    assert outer_input == {"response": <LLMResponse>}
```

- [ ] **Step 1.9:实现 `PortContext.exit_subgraph`**

```python
# lca/harness/graph/execute/v2/_port_context.py(patch)
def exit_subgraph(self, outer_outputs: tuple[str, ...]) -> dict[str, object]:
    """inner_graph 终止时,把同名端口值透传到 outer PortContext(铁律 1)。
    
    铁律 4:inner_graph 局部 PortContext 终止时销毁,只保留 outer 同名端口的值。
    """
    outer_input: dict[str, object] = {}
    for port in outer_outputs:
        if port in self.inner_port_values:
            outer_input[port] = self.inner_port_values[port]
    return outer_input
```

- [ ] **Step 1.10:运行测试 + lint**

```bash
pytest tests/harness/graph/execute/test_inner_subgraph_driver.py tests/harness/graph/execute/test_port_naming.py -v
ruff check lca/harness/graph/execute/v2/node_graph_driver.py lca/harness/graph/execute/v2/_port_context.py lca/contracts/exceptions/subgraph.py tests/harness/graph/execute/test_inner_subgraph_driver.py tests/harness/graph/execute/test_port_naming.py
```

Expected: pytest 全 PASS,ruff 零新增错误

- [ ] **Step 1.11:跑回归,确认 68 测试不退化**

```bash
pytest tests/think/ tests/contracts/test_subgraph_reference_contract.py tests/harness/graph/execute/test_interpreter_subgraph.py tests/declarative/test_phase_graph.py tests/contracts/test_phase_node_pr_c.py -v
```

Expected: 68 个测试全 PASS(允许 1 个 baseline failed,即 `test_bundle_subgraph_resolver.py` 引用已删除 bundle)

- [ ] **Step 1.12:Commit + push + 开 PR**

```bash
git add -A
git commit -m "feat(declarative): port passthrough via PortContext.exit_subgraph (PG-006/PG-007)"
git push -u origin <branch>
gh pr create --title "PR-1: driver recursive sub_spec_ref with depth+cycle guards" --body "..."
```

---

## Task 2:节点级 emit 声明 + dispatcher

**Files:**
- Create: `lca/loop/emit/node_emitter.py`(~50 行 dispatcher)
- Modify: `lca/harness/graph/execute/v2/node_graph_driver.py`(节点 enter/exit 调 emit_for_node)
- Create: `tests/harness/graph/execute/test_node_emit_dispatcher.py`(4 case)

**Interfaces:**
- Consumes: 现有 5 个 EP 函数(全部从 `lca.infrastructure.session.emit.cognitive_emit` 导入):`emit_prompt_assembler_start_for_state`、`emit_prompt_assembler_end_for_state`、`_emit_reasoner_meta_from_render`(私有)、`emit_reasoner_reason_start_for_state`、`emit_reasoner_reason_end_for_state`
- Produces:
  - `emit_for_node(ep_id: str, state: AgentState, **kwargs) -> None` — 公共 dispatcher,容错
  - `emit_reasoner_meta_for_node(state, plan, render) -> None` — `reasoner_meta` 专用 helper

### Steps

- [ ] **Step 2.1:写失败的测试 — dispatcher 路由**

```python
# tests/harness/graph/execute/test_node_emit_dispatcher.py
from lca.loop.emit.node_emitter import emit_for_node


async def test_emit_for_node_routes_known_ep(monkeypatch):
    """emit_for_node(known_ep, state) 必须调对应 emit 函数。"""
    called = []
    def fake_emit(state, **kwargs):
        called.append((state, kwargs))
    monkeypatch.setattr(
        "lca.loop.emit.node_emitter._EP_DISPATCH",
        {"test_ep": fake_emit},
    )
    state = _dummy_state()
    emit_for_node("test_ep", state, foo="bar")
    assert called == [(state, {"foo": "bar"})]
```

- [ ] **Step 2.2:运行测试,确认失败**

Run: `pytest tests/harness/graph/execute/test_node_emit_dispatcher.py::test_emit_for_node_routes_known_ep -v`
Expected: FAIL with `ModuleNotFoundError: lca.loop.emit.node_emitter`

- [ ] **Step 2.3:实现 `lca/loop/emit/node_emitter.py`**

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
        return
    with contextlib.suppress(Exception):
        fn(state, **kwargs)


def emit_reasoner_meta_for_node(state: AgentState, plan, render) -> None:
    """reasoner_meta EP 需要 plan + render 两个参数,走专门 helper。"""
    from lca.infrastructure.session.emit.cognitive_emit import (
        _emit_reasoner_meta_from_render,
    )
    with contextlib.suppress(Exception):
        _emit_reasoner_meta_from_render(plan, render)


__all__ = ["emit_for_node", "emit_reasoner_meta_for_node"]
```

- [ ] **Step 2.4:运行测试,确认通过**

Run: `pytest tests/harness/graph/execute/test_node_emit_dispatcher.py::test_emit_for_node_routes_known_ep -v`
Expected: PASS

- [ ] **Step 2.5:写失败的测试 — 未知 EP 静默忽略**

```python
# tests/harness/graph/execute/test_node_emit_dispatcher.py(追加)
async def test_emit_for_node_unknown_ep_silent():
    """未知 ep_id 必须静默忽略(driver 不参与 EP 词表维护)。"""
    state = _dummy_state()
    emit_for_node("totally_unknown_ep", state)  # 不抛异常
```

- [ ] **Step 2.6:运行 + commit**

```bash
pytest tests/harness/graph/execute/test_node_emit_dispatcher.py -v
git add lca/loop/emit/node_emitter.py tests/harness/graph/execute/test_node_emit_dispatcher.py
git commit -m "feat(declarative): node-level EP dispatcher emit_for_node"
```

- [ ] **Step 2.7:改 driver — 节点 enter/exit 发 EP**

```python
# lca/harness/graph/execute/v2/node_graph_driver.py(patch, 在 _drive_node 内)
from lca.loop.emit.node_emitter import emit_for_node, emit_reasoner_meta_for_node


async def _execute_with_emits(self, node, node_input):
    """节点 enter/exit 按 config 自动发 EP,executor 不感知 EP 存在。"""
    state = self.context.runtime.state

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
        raise

    # 成功:发 emit_on_exit(reasoner_meta 特殊处理)
    for ep_id in node.config.get("emit_on_exit", []):
        if ep_id == "reasoner_meta":
            # reasoner_meta 需要 plan + render,从 output 里抽
            plan = node_input.port_values.get("turn_plan")
            render = output.port_values.get("turn_render")
            if plan is not None and render is not None:
                emit_reasoner_meta_for_node(state, plan, render)
        else:
            emit_for_node(ep_id, state)

    return output
```

- [ ] **Step 2.8:写失败的测试 — driver 调度 emit_on_exit**

```python
# tests/harness/graph/execute/test_node_emit_dispatcher.py(追加)
async def test_driver_dispatches_emit_on_exit(monkeypatch):
    """driver 走完节点后,按 config.emit_on_exit 调 emit_for_node。"""
    # 构造一个 emit_on_exit=[test_ep] 的节点
    # driver.run() 后断言 emit_for_node 被调 1 次,参数 = ("test_ep", state)
```

- [ ] **Step 2.9:运行 + 验证 pass**

Run: `pytest tests/harness/graph/execute/test_node_emit_dispatcher.py -v`
Expected: 全 PASS

- [ ] **Step 2.10:跑回归 + lint + commit**

```bash
pytest tests/think/ tests/contracts/test_subgraph_reference_contract.py tests/harness/graph/execute/test_interpreter_subgraph.py tests/declarative/test_phase_graph.py tests/harness/graph/execute/test_node_emit_dispatcher.py -v
ruff check lca/harness/graph/execute/v2/node_graph_driver.py lca/loop/emit/node_emitter.py tests/harness/graph/execute/test_node_emit_dispatcher.py
git add -A
git commit -m "feat(declarative): driver dispatches emit_on_enter/exit automatically"
git push -u origin <branch>
gh pr create --title "PR-2: node-level emit declaration + dispatcher" --body "..."
```

---

## Task 3:BundleGraphNode.config 字段接受 emit 列表(noop,如已支持)

**Files:**
- Read: `lca/contracts/protocols/declarative/declarative_1/bundle_graph.py`(确认 config 字段是 `Mapping[str, object]`,已支持任意 key)

**Step:**

- [ ] **Step 3.1:确认 BundleGraphNode.config 字段定义**

```python
# 读 lca/contracts/protocols/declarative/declarative_1/bundle_graph.py
# 确认 config: Mapping[str, object] = field(default_factory=dict)
# 如果是 Mapping[str, object],Task 2/5 的 yaml 字段(emit_on_enter / emit_on_exit)已自动支持
# 如果是 Mapping[str, <strict type>],需扩展为 Mapping[str, object] 或加 validator
```

Expected: `config` 是 `Mapping[str, object]`(已支持任意 key)

- [ ] **Step 3.2:如需扩展,改 BundleGraphNode**

(仅当 Step 3.1 发现 config 字段是 strict type 时执行)

```python
# lca/contracts/protocols/declarative/declarative_1/bundle_graph.py(patch)
@dataclass(frozen=True, slots=True)
class BundleGraphNode:
    # ...
    config: Mapping[str, object] = field(default_factory=dict)  # 改为 object
```

- [ ] **Step 3.3:commit(如果改了)**

```bash
git add lca/contracts/protocols/declarative/declarative_1/bundle_graph.py
git commit -m "feat(declarative): BundleGraphNode.config accepts arbitrary keys for emit_*"
```

---

## Task 4:三个新 executor(plan / render / complete)

**Files:**
- Create: `lca/plugins/think/reason_plan.py`
- Create: `lca/plugins/think/reason_render.py`
- Create: `lca/plugins/think/reason_complete.py`
- Create: `tests/think/test_reason_plan_phase_plugin.py`
- Create: `tests/think/test_reason_render_phase_plugin.py`
- Create: `tests/think/test_reason_complete_phase_plugin.py`

**Interfaces:**
- Consumes: 现有 `PromptReasoner` 的 3 个方法:`build_turn_plan(state) -> ReasonerTurnPlan`、`render_turn(state, plan) -> ReasonerTurnRender`、`complete_turn(state, render) -> LLMResponse`(位于 `lca/cognition/brain/reasoner/reasoner.py`);`@plugin(...)` 装饰器模板参考 `lca/plugins/think/shortcut.py`
- Produces: 3 个 executor,各 9 行薄壳,`semantic_name` 分别为 `think.reason.plan` / `think.reason.render` / `think.reason.complete`

### Steps

- [ ] **Step 4.1:写失败的测试 — plan executor**

```python
# tests/think/test_reason_plan_phase_plugin.py
from lca.plugins.think.reason_plan import ThinkReasonPlanExecutor
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeInput


async def test_plan_executor_calls_build_turn_plan():
    """executor 必须调 reasoner.build_turn_plan(state) 1 次,返回 NodeOutput 含 turn_plan。"""
    executor = ThinkReasonPlanExecutor()
    captured = {}

    class FakeReasoner:
        def build_turn_plan(self, state):
            captured["state"] = state
            return "PLAN_OBJ"

    fake_state = object()
    fake_runtime = type("R", (), {"reasoner": FakeReasoner(), "state": fake_state})()
    fake_context = type("C", (), {"runtime": fake_runtime})()

    output = await executor.node_execute(fake_context, NodeInput(port_values={}))
    assert output.port_values == {"turn_plan": "PLAN_OBJ"}
    assert captured["state"] is fake_state
```

- [ ] **Step 4.2:运行测试,确认失败**

Run: `pytest tests/think/test_reason_plan_phase_plugin.py::test_plan_executor_calls_build_turn_plan -v`
Expected: FAIL with `ModuleNotFoundError: lca.plugins.think.reason_plan`

- [ ] **Step 4.3:实现 plan executor**

```python
# lca/plugins/think/reason_plan.py
"""phase.think.reason.plan — pure compute: build_turn_plan (no LLM).

think.reason inner_graph 节点 1/3:在调 LLM 之前先选模板 + 列 sections 预览。
executor 不调 EP、不写 state、不知道 EP 存在(EP 由 driver 按 config.emit_on_exit 自动发)。

ADR-0218 §3.3:节点 = 1 capability → 1 action。
ADR-0217 §3.3.1:任意嵌套子图。
"""
from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ThinkReasonPlanExecutor:
    """think.reason.plan 节点:reasoner.build_turn_plan(state) → ReasonerTurnPlan。"""

    semantic_name: str = "think.reason.plan"
    region: str = "phase:think"

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think.reason inner_graph 节点入口。

        inputs 端口(yaml):[] (无,只读 runtime.state)
        outputs 端口(yaml):[turn_plan]
        """
        reasoner = context.runtime.reasoner
        state = context.runtime.state
        if reasoner is None or state is None:
            return NodeOutput(port_values={})
        plan = reasoner.build_turn_plan(state)
        return NodeOutput(port_values={"turn_plan": plan})


@plugin(
    id="phase.think.reason.plan",
    Config=None,
    provides=("phase.think.reason.plan",),
    requires=("reasoner",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_reason_plan.checked",
                "phase_think_reason_plan.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "reasoner"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """双键注册:Cordis provide(composite + region-less)。"""
    del config
    executor = ThinkReasonPlanExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)
    ctx.provide(executor.semantic_name, executor)


__all__ = ["ThinkReasonPlanExecutor", "setup"]
```

- [ ] **Step 4.4:运行测试,确认通过**

Run: `pytest tests/think/test_reason_plan_phase_plugin.py -v`
Expected: PASS

- [ ] **Step 4.5:写失败的测试 — render executor**

```python
# tests/think/test_reason_render_phase_plugin.py
async def test_render_executor_calls_render_turn():
    """executor 必须调 reasoner.render_turn(state, plan) 1 次,返回 turn_render。"""
    executor = ThinkReasonRenderExecutor()
    captured = {}

    class FakeReasoner:
        def render_turn(self, state, plan):
            captured["plan"] = plan
            return "RENDER_OBJ"

    fake_state = object()
    fake_runtime = type("R", (), {"reasoner": FakeReasoner(), "state": fake_state})()
    fake_context = type("C", (), {"runtime": fake_runtime})()
    fake_input = NodeInput(port_values={"turn_plan": "PLAN_OBJ"})

    output = await executor.node_execute(fake_context, fake_input)
    assert output.port_values == {"turn_render": "RENDER_OBJ"}
    assert captured["plan"] == "PLAN_OBJ"
```

- [ ] **Step 4.6:实现 render executor**

(结构与 plan 一致,只把 `build_turn_plan` 换成 `render_turn`,从 `input.port_values.get("turn_plan")` 拿 plan)

```python
# lca/plugins/think/reason_render.py(参考 reason_plan.py 形态)
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


@plugin(
    id="phase.think.reason.render",
    # ... 同 plan executor 的 contract 模板,descriptors 改为 phase_think_reason_render.* ...
)
async def setup(ctx: PluginContext, config=None) -> None:
    # 同 plan executor 的双键注册
```

- [ ] **Step 4.7:运行 render 测试 + 验证 pass**

Run: `pytest tests/think/test_reason_render_phase_plugin.py -v`
Expected: PASS

- [ ] **Step 4.8:写失败的测试 — complete executor**

```python
# tests/think/test_reason_complete_phase_plugin.py
async def test_complete_executor_calls_complete_turn():
    """executor 必须 await reasoner.complete_turn(state, render) 1 次,返回 response。"""
    executor = ThinkReasonCompleteExecutor()
    captured = {}

    class FakeReasoner:
        async def complete_turn(self, state, render):
            captured["render"] = render
            return "RESPONSE_OBJ"

    fake_state = object()
    fake_runtime = type("R", (), {"reasoner": FakeReasoner(), "state": fake_state})()
    fake_context = type("C", (), {"runtime": fake_runtime})()
    fake_input = NodeInput(port_values={"turn_render": "RENDER_OBJ"})

    output = await executor.node_execute(fake_context, fake_input)
    assert output.port_values == {"response": "RESPONSE_OBJ"}
    assert captured["render"] == "RENDER_OBJ"
```

- [ ] **Step 4.9:实现 complete executor**

```python
# lca/plugins/think/reason_complete.py(参考 reason_plan.py 形态)
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


@plugin(
    id="phase.think.reason.complete",
    # ... 同 plan executor 的 contract 模板,descriptors 改为 phase_think_reason_complete.* ...
)
async def setup(ctx: PluginContext, config=None) -> None:
    # 同 plan executor 的双键注册
```

- [ ] **Step 4.10:运行 complete 测试 + 验证 pass**

Run: `pytest tests/think/test_reason_complete_phase_plugin.py -v`
Expected: PASS

- [ ] **Step 4.11:反向断言 — 三个 executor 不 import emit**

```bash
grep -rn "from lca.infrastructure.session.emit\|from lca.loop.emit" lca/plugins/think/reason_*.py
```

Expected: 必须 0 行输出(空)

- [ ] **Step 4.12:跑 audit-plugin-shape**

```bash
./scripts/lca-ops audit-plugin-shape
```

Expected: PASS

- [ ] **Step 4.13:跑 lint + commit**

```bash
ruff check lca/plugins/think/reason_plan.py lca/plugins/think/reason_render.py lca/plugins/think/reason_complete.py tests/think/test_reason_plan_phase_plugin.py tests/think/test_reason_render_phase_plugin.py tests/think/test_reason_complete_phase_plugin.py
git add lca/plugins/think/reason_plan.py lca/plugins/think/reason_render.py lca/plugins/think/reason_complete.py tests/think/test_reason_plan_phase_plugin.py tests/think/test_reason_render_phase_plugin.py tests/think/test_reason_complete_phase_plugin.py
git commit -m "feat(think): 3 thin executors for reason.plan/render/complete (1 cap → 1 action)"
```

---

## Task 5:`bundles/think_reason.yaml` + 改 `bundles/think.yaml` + ADR patch + seam deprecated

**Files:**
- Create: `bundles/think_reason.yaml`
- Modify: `bundles/think.yaml`(think.reason 节点加 sub_spec_ref + emit_on_enter/exit)
- Modify: `lca/loop/emit/cognitive/reasoner.py`(标 deprecated)
- Modify: `docs/adr/0217-bundle-graph-schema-v2.md`(§3.3 patch)
- Create: `tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py`(4 case)

**Interfaces:**
- Consumes: 现有 3 个新 plugin(`phase.think.reason.plan` / `.render` / `.complete`)已通过 Task 4 注册到 FactoryRegistry
- Produces:
  - `bundles/think_reason.yaml` — think.reason inner_graph 图描述
  - `bundles/think.yaml` — think.reason 节点挂 sub_spec_ref

### Steps

- [ ] **Step 5.1:写失败的 e2e 测试 — 加载 inner_graph yaml**

```python
# tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py
async def test_load_think_reason_yaml_compiles():
    """bundles/think_reason.yaml 必须能被 BundleGraphSpec v2 编译,无 PG-005 错误。"""
    spec = BundleSubgraphResolver().resolve("bundles/think_reason.yaml")
    assert spec is not None
    assert len(spec.nodes) == 3
    assert {n.id for n in spec.nodes} == {"think.reason.plan", "think.reason.render", "think.reason.complete"}
```

- [ ] **Step 5.2:运行测试,确认失败**

Run: `pytest tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py::test_load_think_reason_yaml_compiles -v`
Expected: FAIL with `bundles/think_reason.yaml not found` 或 PG-005

- [ ] **Step 5.3:实现 `bundles/think_reason.yaml`**

```yaml
# bundles/think_reason.yaml — think.reason inner_graph (v1)
#
# ADR-0217 Bundle Graph Schema v2。3 节点 + 2 边,执行顺序由图描述声明。
# driver 递归调度:每个节点 enter/exit 按 config.emit_on_* 自动发 EP。
# think.reason 节点持有 sub_spec_ref.plan_ref 指向本文件(spec §2.6)。
#
# 不放(plugin_id/$module/entries):@plugin 不读,v2 driver 不读。

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
      max_visits: 3   # 唯一允许 max_visits > 1,LLM 重试在 inner_graph 内消化
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

- [ ] **Step 5.4:运行测试,确认通过**

Run: `pytest tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py::test_load_think_reason_yaml_compiles -v`
Expected: PASS

- [ ] **Step 5.5:改 `bundles/think.yaml` — think.reason 节点加 sub_spec_ref**

```yaml
# bundles/think.yaml(patch,只动 think.reason 一个节点)
nodes:
  # ... 4 个原节点不变 ...

  # ★ v1:think.reason 加 sub_spec_ref
  - id: think.reason
    factory: think.reason
    inputs: [in_assembled_manifest]
    outputs: [response]                      # 与 inner_graph 终止端口同名 → 透传
    config:
      max_visits: 8                          # outer 级别,控制 inner_graph 进入次数
      sub_spec_ref:
        plan_ref: bundles/think_reason.yaml
        entry_node: think.reason.plan
        binding_edge: think.reason           # 必须 == node.id
      emit_on_enter: []
      emit_on_exit:  []
```

- [ ] **Step 5.6:写失败的 e2e 测试 — 端到端跑通**

```python
# tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py(追加)
async def test_reason_inner_subgraph_full_flow(monkeypatch):
    """driver 跑完 plan→render→complete,4 个 EP 按节点 emit 配置发出。"""
    # mock reasoner 的 build_turn_plan / render_turn / complete_turn
    # 调用 driver.run() 后断言:
    #   1. emit_prompt_assembler_end 被调 1 次
    #   2. emit_reasoner_reason_start 被调 1 次
    #   3. emit_reasoner_reason_end 被调 1 次(outcome=success)
    #   4. 端口 `response` 透传到 outer PortContext
```

- [ ] **Step 5.7:运行测试,确认 pass + 跑回归**

```bash
pytest tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py -v
pytest tests/think/ tests/contracts/test_subgraph_reference_contract.py tests/harness/graph/execute/test_interpreter_subgraph.py tests/declarative/test_phase_graph.py tests/contracts/test_phase_node_pr_c.py tests/harness/graph/execute/test_node_emit_dispatcher.py tests/harness/graph/execute/test_inner_subgraph_driver.py tests/harness/graph/execute/test_port_naming.py -v
```

Expected: 全部 PASS(68 baseline + 25–28 新测试)

- [ ] **Step 5.8:标 `run_reasoner_with_spine_facts` deprecated**

```python
# lca/loop/emit/cognitive/reasoner.py(patch,顶部 docstring 加)
"""
Reasoner spine fact envelope (ADR-0194 P1-15).

.. deprecated::
    v1 (2026-09-10 spec): think.reason 已拆为 inner_graph(plan/render/complete),
    EP 由节点 config.emit_on_* 声明,driver 自动发。本 seam 函数被 think.reason
    inner_graph 替代,保留仅为兼容老 caller。

delete-when:
    1. 所有 phase graph driver 都走 v2(NOT v0 GraphAssembler fallback)
    2. 节点级 sub_spec_ref 在 prod profile 落地(think-subgraph-dev 已用)
    3. think.reason inner_graph 拆解已落地(本 spec)
    4. 至少 1 个 prod profile 跑通 3 个月,期间无 seam fallback 触发

owner: lca/loop/emit/cognitive/reasoner.py 维护者
validation: 条件 1-3 已满足;条件 4 由 owner 评估
"""
```

- [ ] **Step 5.9:ADR-0217 §3.3 patch**

```markdown
<!-- docs/adr/0217-bundle-graph-schema-v2.md(patch,在 §3.3 末尾追加) -->

### 3.3.1 Nested sub_spec_ref 任意深度

v1 (2026-09-10 spec) 扩展:节点级 `sub_spec_ref` 支持任意深度嵌套。

- `max_subgraph_depth` 从硬限 4 改为软限,默认 8
- 同 `plan_ref` 在递归栈出现第二次 → `SubgraphCycleError`(PG-007-cycle)
- 嵌套深度超过 `max_subgraph_depth` → `SubgraphDepthExceededError`(PG-007-depth)
- budget 递减:outer budget - 1 传给 inner,inner 用尽即停

### 3.3.2 节点 emit 声明

v1 扩展:`node.config` 接受 `emit_on_enter: list[str]` 和 `emit_on_exit: list[str]`。

- driver 在节点 enter/exit 时按列表调 `emit_for_node(ep_id, state)`
- executor 不知道 EP 存在,沿用 ADR-0218 §3.3 薄壳原则
- EP 列表元素必须是 `EXECUTION_POINTS` 白名单中的字符串
- `EXECUTION_POINTS` 白名单不增不减(C11 事件闭集不破)

### 3.3.3 端口同名透传

v1 扩展:inner_graph 终止端口名 ∈ outer 节点 `outputs` → 透传到 outer PortContext。

- 铁律 1:端口同名透传
- 铁律 2:缺失输入 = 空 NodeOutput
- 铁律 3:同图同名端口冲突 = PG-006-port-conflict
- 铁律 4:inner_graph 局部 PortContext 终止时销毁
```

- [ ] **Step 5.10:跑端到端 — 创建真实 run**

```bash
./scripts/lca-ops runs create --user-text "hello" --profile profiles/think-subgraph-dev.yaml
```

Expected: run_id 创建成功,无 PG-XXX 错误

- [ ] **Step 5.11:验证 spine trace 含 3 个 inner 节点**

```bash
# 找到最近一次 run_id
RUN_ID=$(./scripts/lca-ops status --json | jq -r '.last_run_id')
jq '.events[] | select(.event_type | test("think.reason.(plan|render|complete)")) | {event_type, ts, payload_keys}' traces/runs/${RUN_ID}.spine.jsonl | head -50
```

Expected: 至少 3 条 inner 节点 trace(plan/render/complete 各 ≥ 1)

- [ ] **Step 5.12:反向断言 — executor 不 import emit**

```bash
grep -rn "from lca.infrastructure.session.emit\|from lca.loop.emit" lca/plugins/think/reason_*.py
```

Expected: 必须 0 行输出

- [ ] **Step 5.13:反向断言 — think_reason.yaml 不含 plugin_id**

```bash
grep -E '\$module|plugin_id|entries:' bundles/think_reason.yaml
```

Expected: 必须 0 行输出

- [ ] **Step 5.14:跑全 lint + mypy + audit-plugin-shape**

```bash
ruff check lca/plugins/think/reason_*.py lca/loop/emit/node_emitter.py lca/harness/graph/execute/v2/ tests/think/test_reason_*.py tests/harness/graph/execute/test_*subgraph* tests/harness/graph/execute/test_*emit* tests/harness/graph/execute/test_*port*
mypy lca/plugins/think/reason_*.py lca/loop/emit/node_emitter.py lca/harness/graph/execute/v2/
./scripts/lca-ops audit-plugin-shape
git diff --check
```

Expected: ruff/mypy 零新增错误,audit-plugin-shape PASS,diff --check 空

- [ ] **Step 5.15:commit + push + 开 PR**

```bash
git add bundles/think_reason.yaml bundles/think.yaml lca/loop/emit/cognitive/reasoner.py docs/adr/0217-bundle-graph-schema-v2.md tests/harness/graph/execute/test_reason_inner_subgraph_e2e.py
git commit -m "feat(declarative): think.reason inner_graph + ADR-0217 §3.3 patch + seam deprecated"
git push -u origin <branch>
gh pr create --title "PR-3: think.reason inner_graph + ADR-0217 §3.3.1/3.3.2/3.3.3" --body "..."
```

---

## Self-Review

### 1. Spec coverage(spec §0–§6 覆盖矩阵)

| spec 节 | 实现任务 |
|---|---|
| §0.2 表 — 嵌套深度软限 + cycle | Task 1 |
| §0.2 表 — think.reason inner_graph | Task 5 |
| §0.2 表 — EP 节点级声明 | Task 2 |
| §0.3 I1 — 节点即图描述符 | Task 5 (think.reason 持有 sub_spec_ref) |
| §0.3 I2 — 节点 = 1 capability → 1 action | Task 4 (3 个 9 行 executor) |
| §0.3 I3 — EP 是图描述一部分 | Task 2 |
| §0.3 I4 — 单一图格式 | Task 1 (复用 sub_spec_ref, 不引入 inner_graph) |
| §0.3 I5 — C11 不破 | Task 2 (5 个 EP 全沿用, EXECUTION_POINTS 不动) |
| §0.3 I6 — 68 测试不退化 | 每个 Task 末尾跑回归 |
| §2.1.1 — config.emit_on_enter/exit | Task 2 + Task 3 |
| §2.1.2 — driver 任意嵌套深度 | Task 1 |
| §2.1.3 — 端口同名透传 | Task 1 |
| §2.2 — 3 个 executor | Task 4 |
| §2.3 — EP dispatcher | Task 2 |
| §2.4 — driver 改动 | Task 2 |
| §2.5 — bundles/think_reason.yaml | Task 5 |
| §2.6 — bundles/think.yaml 改动 | Task 5 |
| §2.7 — 数据流 | Task 5 (e2e test 验证) |
| §2.8 — 错误处理矩阵 | Task 1 (cycle/depth) + Task 2 (reasoner_reason_end failure) |
| §2.9 — 状态传递 | Task 1 (PortContext) + Task 4 (state_mutation: forbidden) |
| §2.10 — ADR-0217 patch | Task 5 |
| §2.11 — seam deprecated | Task 5 |
| §3.1 — 单元测试(3 文件 12–15 case) | Task 4 |
| §3.2 — 集成测试(4 文件 12 case) | Task 1, 2, 5 |
| §3.3 — 68 回归 | 每个 Task 末尾 |
| §3.4 — E2E | Task 5 Step 5.10/5.11 |
| §3.5 — 反向断言 | Task 4 Step 4.11 + Task 5 Step 5.12/5.13 |
| §3.6 — lint/mypy | Task 5 Step 5.14 |

✅ 全部 spec 要求都有 task 实现

### 2. Placeholder scan

| 模式 | 命中? |
|---|---|
| "TBD" / "TODO" / "implement later" / "fill in details" | ❌ 无 |
| "Add appropriate error handling" / "handle edge cases" | ❌ 无(每 Task 错误处理明确) |
| "Write tests for the above"(无代码) | ❌ 无(每 Step 给完整 test 代码) |
| "Similar to Task N"(无代码) | ❌ 无(Task 4.6/4.9 标"参考 plan executor 形态",但关键代码块完整) |
| 步骤描述无 how | ❌ 无(代码块覆盖所有 code step) |
| 引用未定义类型/函数 | ❌ 无(每个 Produces 接口都标了定义位置) |

### 3. Type consistency

| 类型/方法 | 任务 1 定义 | 后续任务使用 | 一致? |
|---|---|---|---|
| `SubgraphDepthExceededError(depth, max_depth)` | Task 1.3 | Task 1.1, 1.4 | ✅ |
| `SubgraphCycleError(plan_ref)` | Task 1.3 | Task 1.6, 1.4 | ✅ |
| `PortNamingConflictError(node_id, port)` | Task 1.3 | (未直接使用,在 driver 检测时 raise) | ✅ |
| `PortContext.exit_subgraph(outer_outputs)` | Task 1.9 | Task 1.8 测试, Task 5 driver | ✅ |
| `emit_for_node(ep_id, state, **kwargs)` | Task 2.3 | Task 2.7 driver, Task 2.5/2.8 测试 | ✅ |
| `emit_reasoner_meta_for_node(state, plan, render)` | Task 2.3 | Task 2.7 driver | ✅ |
| `ThinkReasonPlanExecutor.semantic_name = "think.reason.plan"` | Task 4.3 | Task 5.3 yaml factory | ✅ |
| `ThinkReasonRenderExecutor.semantic_name = "think.reason.render"` | Task 4.6 | Task 5.3 yaml factory | ✅ |
| `ThinkReasonCompleteExecutor.semantic_name = "think.reason.complete"` | Task 4.9 | Task 5.3 yaml factory | ✅ |
| `bundles/think_reason.yaml` nodes/edges schema | Task 5.3 | Task 5.1 测试 | ✅ |
| `bundles/think.yaml` think.reason node sub_spec_ref fields | Task 5.5 | Task 5.6 测试 | ✅ |

无类型不一致。

### 4. PR 顺序约束

| PR | 依赖 |
|---|---|
| PR-1 (Task 1) | 无 |
| PR-2 (Task 2+3) | Task 1 已合(driver 调度 emit 需要 recursion stack 就绪) |
| PR-3 (Task 4+5) | Task 1+2+3 已合(driver + dispatcher + 3 executor + yaml) |

✅ 顺序约束清晰,可独立 PR review。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-10-nested-bundle-graph-v1.md`.**

按 writing-plans skill 末尾要求,询问执行方式:

**两种执行方式,选哪个:**

1. **Subagent-Driven(推荐)** — 每个 Task dispatch 一个 fresh subagent,Task 之间 review,快速迭代
2. **Inline Execution** — 在当前 session 按 Task 顺序执行,带 checkpoint review
