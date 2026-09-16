# Plan: 卸 composer projection · 让 graph 节点走 typed-port 信息彻底

> Workspace: `/home/lichao/layered-cognitive-agent`
> Branch (target): `eng/slim-composer-and-typed-ports` (3 串行 PR)
> 参考: ADR-0220 §6, ADR-0221 P3, ADR-0222, ADR-0225/0226/0227/0228

---

## 0. 上下文与根因

### 0.1 一句话

`BrainComposer` 在 boot 时把 `Brain` 内部属性(`reasoner`、`skill_router`、`classifier`、`decision_gate`)展开成 `phase_capabilities` 字典,业务图节点靠 `context.runtime.<name>` 偷字段。这种"投影 + 偷字段"的组合,让同一份事实在 graph 上出现 4 次(`brain.reasoner` / `runtime.reasoner` / `phase_capabilities["reasoner"]` / `phase_capabilities["phase.think.reason"]`),违反 ADR-0195 §1.4 C13 信息血统闭合。

### 0.2 证据收据

- `lca/plugins/composer/think/brain_composer.py:60-114` 把 14 件事塞进 `compose_agent` 一个方法
- 39 个 graph 节点中,**12 个**仍用 `_resolve_port(name, context)` 偷 `context.runtime.<field>`(见 grep 结果)
- `phase_capabilities` 投影到 `RuntimePhaseCapabilities`(`runtime/support/runtime_bindings.py:56`),节点通过 `_AdapterScope.__getattr__`(`framework/graph/adapter.py:259`)访问
- `think.context_compact.py`、`think.history.assemble.py` 等大节点把"读 runtime state"和"做计算"两件事混在一起

### 0.3 当前架构的可工作图(现状)

```
BrainComposer.compose_agent() ───┐
  instrument_llm(llm)            │
  resolve_brain(spec, llm)       │
  apply_lead_brain(brain, gate)   │
  require GATES                   ├──► phase_capabilities = {
  for attr in (skill_router,       │       "gates": ...,
    reasoner, classifier):        │       "skill_router": brain.skill_router,
      phase_capabilities[k] = v   │       "reasoner": brain.reasoner,
  alias 投影 (reasoner 等)         │       "phase.think.route": brain.skill_router,
  require REASONER_ROLE_PROFILE   │       "phase.think.reason": brain.reasoner,
  require tools                   │       "phase.think.classify": brain.classifier,
  require/adapter llm             │       "phase.think.decision_gate": ...,
  _resolve_decision_gate 3 路     │       "reasoner.role_profile": profile,
                                   │       "tools": tools,
                                   │       "adapter": llm,
                                   │       "phase.think.decision_gate": ...
                                   │   }
                                   └──► AgentGraphContribution(...)

RuntimePhaseCapabilities.values = MappingProxyType(phase_capabilities)
                            ▲
                            │ _AdapterScope.__getattr__(name) → getattr(base, name)
                            │
context.runtime.<field>   ──┘   (节点偷字段的接入点)
```

### 0.4 目标架构

```
BrainComposer.compose_agent() ───┐
  instrument_llm(spec.llm)       │    ← 仅 3 件事
  resolve_brain(spec, llm, scope)│
  return AgentGraphContribution( │     投影全部交给 GraphInterpreter
    brain=brain, llm=llm,        │     graph 自己通过 typed port 拿下游依赖
    hooks=...,                    │
  )                              │

DeclarativeInterpreter.run(plan):
  for each node:
    input = build_input(node.declared_inputs, registry)   # typed-port input
    output = node_executor.node_execute(NodeContext(
        runtime=RuntimePhaseCapabilities({
            "brain": brain,                               # 单一来源
            "body": body,
            "memory": memory,
            "perceive_hub": perceive_hub,
            "writer": per_turn_writer,                    # only kernel-injected
            "state": agent_state,                         # only kernel-injected
            "effect_gateway": per_turn_dispatcher,        # only kernel-injected
        }),
        node_id=node.id,
        graph=plan,
    ), input)
    registry.merge_output(output.port_values)
```

**关键差异**:
- `brain.reasoner` 不再被拆进 `phase_capabilities` — 节点要么直接收 typed port,要么 `getattr(runtime, "brain").reasoner` 走 brain 本身(只 1 处跳转)
- 节点 `declared_inputs` 覆盖所有计算依赖,只有 `state` / `writer` / `effect_gateway` / `cursor` 是 kernel-injected runtime carrier(不变)
- `BrainComposer` 缩到 ~30 行

---

## 1. 目标分解:3 个串行 PR

| PR | 主题 | 影响文件数 | 复杂度 | 风险 |
|---|---|---|---|---|
| **PR-A** | 节点去 `context.runtime.<field>` 偷字段,改 typed-port 输入 | ~12 个节点 + 1 composer + 多 bundle yaml | 中 | 中 |
| **PR-B** | 拆 `think.llm.dispatch`(调 LLM + 写 journal) 与 `think.context_compact`(闸门 + 策略) | 4 个新节点 + 2 个 bundle yaml 重写 | 中 | 中 |
| **PR-C** | 删 3 个 provider plugin + 卸 `BrainComposer` 投影 | 3 个 plugin 删 + composer 缩到 ~30 行 + tests 重写 | 小 | 小 |

每个 PR 独立可合、可回滚。

---

## 2. PR-A: 节点 typed-port 输入,卸 `phase_capabilities` 投影

### 2.1 目标

让 graph 节点的输入**只走 typed port**(即 `input.port_values[<port_name>]` 或 `declared_inputs` 注册的端口),不再通过 `context.runtime.<field>` 偷字段。**唯一的例外**是 kernel-injected 的 4 个 runtime carrier:`state` / `writer` / `effect_gateway` / `cursor`(这些必须在 runtime scope,不是节点 typed-input)。

### 2.2 节点分类(基于 grep 结果)

| 节点 | 当前偷字段 | 应改 typed-port |
|---|---|---|
| `think/dispatch/llm.py` | `state` (允许) + `writer` (允许) + `model_visible_request` (确认是 typed port) + `adapter` | `adapter` → typed port,声明到 `declared_inputs` |
| `think/history/assemble.py` | `state` (允许) + `writer` (允许) + `forked_tools` (typed port) + `response` (typed port) | 无需改 — 已声明 |
| `think/decision/parse.py` | `state` (允许) + `llm_response` (typed port) | 无需改 |
| `think/context_compact.py` | `writer` (允许) + `state` (允许) | 无需改 |
| `think/reason/render.py` | `state` (允许) + `reasoner` ← **要改** + `role_profile` ← **要删**(能力已废) | 整节点需重写,见 PR-A §2.5 |
| `think/reason/plan.py` | `state` (允许) + `reasoner` ← **要改** | 改为读 `input.port_values["selector"]` 或 `runtime.brain.reasoner.selector` |
| `think/budget_check.py` | `state` (允许) | 无需改 |
| `think/gate.py` | (注释提到) `context.runtime.decision_gate` ← **要改** | 改为 `runtime.brain.decision_gate`(走 brain 本身) |
| `think/route/route.py` | `context.runtime.skill_router` ← **要改** | 同上 |
| `think/route/shortcut.py` | `context.runtime.supports_shortcut` ← **要改** | 同上 |
| `think/decision_repair.py` | `_RUNTIME_TOOLS_KEY` ← **要改** | 改 typed port |
| `concept/tool_fork/dispatch.py` | `context.runtime.tools` ← **要改** | 改 typed port |
| `concept/decision_enforce/chain_run.py` | `decision_gates` / `decision_gate` ← **要改** | 改 typed port |
| `concept/decision_shortcut_try/try_shortcut.py` | `supports_shortcut` ← **要改** | 改 typed port |
| `concept/prompt_render/assemble.py` | `prompt_template_provider` ← **要改** | 改 typed port |
| `concept/prompt_render/fill.py` | `tools_provider` + `prompt_section_registry` ← **要改** | 改 typed port(两字段都 typed port) |
| `concept/memory_write/dispatch.py` | `memory` ← **要改** | 改 typed port |
| `concept/effect/execute.py` | `writer` (允许) + `state` (允许) + `effect_gateway` (允许) | 无需改 — 3 个都是 runtime carrier |
| `concept/context_compose/collect.py` | `state` ← **要改** | 改 typed port |
| `concept/perceive_turn/collect.py` | (grep 未列出,需 verify) | verify |
| `concept/perceive_turn/fold.py` | (grep 未列出,需 verify) | verify |
| `reflect/score/score.py` | `brain` + `cognitive_reflection_pipeline` + `agent_state` | **大改**:全部走 typed port |
| `remember/write/write.py` | `effect_gateway` ← **要改** | 改 typed port |
| `intervene/approve_gate.py` | `decision` / `command` (typed port) | 无需改 — 已声明 |
| `intervene/interrupt.py` | `decision` / `spine_seq` (typed port) | 无需改 — 已声明 |
| `act/envelope/envelope.py` | `state` (允许) | 无需改 |
| `act/observe/observe.py` | `journal` ← **要改** | 改 typed port |
| `perceive/observe/observe.py` | `perceive_hub` + `agent_state` ← **要改** | 改 typed port |
| `delegate/compose.py` | `decision` + `capability_grant` (typed port) | 无需改 |

### 2.3 BrainComposer 改造

```python
# brain_composer.py:60-114 → 缩到 ~30 行
def compose_agent(self, request, scope):
    llm = instrument_llm(request.spec.llm)
    brain = resolve_brain(request.spec, llm, scope=scope)
    if request.decision_gate is not None:
        brain = apply_lead_brain(brain, request.decision_gate)
    return AgentGraphContribution(
        brain=brain,
        body=None, memory=None, state_store=None,
        perceive_hub=None, hooks=None, observability=None,
        llm=llm,
        phase_capabilities={},                # ← 投影全删
        metadata={"composer": self.key},
    )
```

`RuntimePhaseCapabilities` 仍由 `project_runtime_phase_capabilities()`(`runtime/projection/phase_capabilities.py:19`)注入 4 个 canonical 字段(`brain` / `body` / `memory` / `perceive_hub`)。其余节点依赖通过 typed port 解决。

### 2.4 Brain 自身暴露 typed port(关键设计)

`Brain` 协议保留作为 cognitive-plane 入口,内部仍持 `reasoner` / `skill_router` / `classifier` / `decision_gate` 等字段;但**节点要拿这些时**,统一通过 `runtime.brain.<attr>`(brain 是 typed `Brain` 实例,Python 字段访问是 typed 的,不再"偷字段"——这是单步访问,不是 service-locator 反模式)。

两种实现路线,选 **B**(侵入最小、复用现有 GraphInterpreter):

**A. 改 `RuntimePhaseCapabilities`**:把每个 brain 子组件拆成独立 capability 键。**不选** — 破坏 `Brain` 协议的封装,且要求 kernel 知道 brain 的内部结构。

**B. 节点统一从 `context.runtime.brain` 拿 `Brain` 实例,自己访问 brain 上的字段**(本质是 typed 协议字段访问,不是 `runtime.<random_capability_key>` 反模式)。

```python
# 节点典型形态 (PR-A 之后):
@dataclass(frozen=True, slots=True)
class ThinkRouteExecutor:
    declared_inputs: tuple[PortName, ...] = ("state",)  # state = typed AgentState
    declared_outputs: tuple[PortName, ...] = ("routing",)
    async def node_execute(self, context, input):
        state = input.port_values["state"]            # typed port
        brain = context.runtime.brain                  # typed Brain instance
        # ↓ 单步访问 brain 自身字段(typed Protocol)
        decision = brain.skill_router.route(state)
        return NodeOutput(port_values={"routing": decision})
```

**为什么这是 typed 不是反模式**:
- `Brain` 是 `@runtime_checkable Protocol`,`brain.<attr>` 是 typed 字段访问,IDE/mypy 可静态验证
- 不经过 service-locator / key-string lookup,没有 capability 注册表参与
- `RuntimePhaseCapabilities.values["brain"]` 是 kernel/canonical graph fact,**不是 composer 的临时投影**
- 节点读到 `brain.skill_router` 时,brain 自己负责 selector factory 一次性定型(在 `resolve_brain` 里),节点不再需要知道 selector 是哪个 capability

### 2.5 `think/reason/plan.py` 与 `think/reason/render.py` 退役

理由:这两个节点都是 ADR-0222 后的 **adapter**(把老 PromptReasoner 签名转 typed DTO),在 `agent/reasoning_turn.yaml` 业务图被 `reason.prepare.template` / `reason.render.prompt`(`concept/template_select` + `concept/prompt_render`)取代了。

**PR-A 工作**:不删,但把内部 `getattr(runtime, "reasoner")` 改为 `getattr(runtime, "brain").reasoner` — 维持这些 adapter 节点在 inner think subgraph 的兼容作用(若有外部测试还在用),typed-port 化与新图节点对齐。

### 2.6 验证矩阵

| 类型 | 命令 | 通过条件 |
|---|---|---|
| 单元 | `uv run pytest tests/nodes/ tests/concept/ tests/think/ -x` | 全部通过 |
| 集成 | `uv run pytest tests/cognition/ tests/concept/ -x` | 全部通过 |
| Architecture | `uv run pytest tests/architecture/ -x` | 全部通过(包括删 `test_reasoner_role_profile_capability.py` 后新增的 `test_no_phase_capability_projection` 守护测试) |
| 静态 | `uv run ruff check lca/nodes lca/plugins/composer/think/` | 0 errors |
| 静态 | `uv run lint-imports` | 0 errors(只新引入的) |
| 静态 | `uv run python scripts/check_package_contracts.py` | 0 errors |
| E2E | `./scripts/lca-ops e2e timeline` | 0 failures |

新增回归测试:

1. `tests/architecture/test_no_runtime_field_theft.py` — 静态扫描 `lca/nodes/**/*.py`,禁止 `getattr(context.runtime, "<word>")` 与 `context.runtime.get("<word>")` 出现非白名单字段(`state` / `writer` / `effect_gateway` / `cursor` / `brain` / `body` / `memory` / `perceive_hub`)
2. `tests/architecture/test_brain_composer_no_projection.py` — 断言 `BrainComposer.compose_agent()` 返回的 `phase_capabilities` 只含 `{}`(canonical 字段在 `project_runtime_phase_capabilities` 注入,与 composer 解耦)
3. `tests/think/test_reason_render_phase_plugin.py` 和 `tests/think/test_reason_plan_phase_plugin.py` 改 typed input 测试,不再依赖 `runtime.reasoner`

### 2.7 文件清单(PR-A)

| 改动 | 文件 |
|---|---|
| 节点去偷字段 | `lca/nodes/think/reason/{plan,render}.py`、`lca/nodes/think/gate.py`、`lca/nodes/think/route/{route,shortcut}.py`、`lca/nodes/think/decision_repair.py`、`lca/nodes/concept/tool_fork/dispatch.py`、`lca/nodes/concept/decision_enforce/chain_run.py`、`lca/nodes/concept/decision_shortcut_try/try_shortcut.py`、`lca/nodes/concept/prompt_render/{assemble,fill}.py`、`lca/nodes/concept/memory_write/dispatch.py`、`lca/nodes/concept/context_compose/collect.py`、`lca/nodes/remember/write/write.py`、`lca/nodes/reflect/score/score.py`、`lca/nodes/act/observe/observe.py`、`lca/nodes/perceive/observe/observe.py`、`lca/nodes/think/dispatch/llm.py` |
| Composer 缩 | `lca/plugins/composer/think/brain_composer.py` |
| Composer 助手内联 | `lca/plugins/composer/think/brain.py`(拆 `instrument_llm` 到 `application/api/api.py` 装配根 helper;`apply_lead_brain` 移到 `ModularBrain.with_gate()` 方法) |
| 守护测试 | 新增 `tests/architecture/test_no_runtime_field_theft.py`、`tests/architecture/test_brain_composer_no_projection.py` |
| 测试更新 | `tests/concept/`、`tests/think/` 下所有 `runtime.reasoner` / `runtime.decision_gate` 风格的测试 fixture 改 typed input |
| Bundle yaml | 不改(节点输入字段名不变,只是实现改了) |

### 2.8 delete-when

PR-A 合并后:删除 `phase.think.role_profile` plugin、删 `REASONER_ROLE_PROFILE` capability key、删 `tests/architecture/test_reasoner_role_profile_capability.py`(挪进 PR-C)。

---

## 3. PR-B: 拆混合职责的大节点

### 3.1 目标

把同时承担"读 runtime state"和"做计算"两件事的节点拆开,每节点只做 1 件事。

### 3.2 拆分表

| 当前节点 | 行数 | 它做的 2 件事 | 拆成 |
|---|---|---|---|
| `think/llm.dispatch/llm.py` | 230 | (1) `adapter.stream(...)` 调 LLM + (2) `writer.append_assistant_message` + `append_tool_call` 写 journal | `think.llm.invoke` (纯 adapter.stream)+ `think.llm.persist` (纯 writer.append) |
| `think/context_compact.py` | 343 | (1) 闸门(`budget.used/max >= 0.7`)+ (2) 策略(`truncate_oldest`)+ (3) 异常吞没(emit `CompactReceipt.skipped`)+ (4) 路由决策(3 种 `_route_*`) | `think.budget.threshold_gate` (闸门 + RoutingDecision) + `think.context.truncate` (策略 + CompactReceipt) + 异常处理由 Gate 节点统管 |
| `think/history/assemble.py` 第 3 级 fallback `_system_from_role_profile` | (302 行) | 组装 ModelVisibleRequest + 兜底 role_profile 拼字符串 | 删 `_system_from_role_profile`(PR-A 已废 `reasoner.role_profile` capability,这条 fallback 必无入口) |

### 3.3 新增 4 节点

#### `lca/nodes/think/llm/invoke.py`(~80 行)

```python
@dataclass(frozen=True, slots=True)
class LlmInvokeExecutor:
    semantic_name: str = "llm.invoke"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("model_visible_request", "adapter")
    declared_outputs: tuple[PortName, ...] = ("llm_response", "usage")
    async def node_execute(self, context, input):
        request = input.port_values["model_visible_request"]
        adapter = input.port_values["adapter"]
        # 适配 typed DTO → wire kwargs; 不写 journal; 不读 state
        prompt = request.messages[-1]["content"] if request.messages else ""
        history = request.messages[:-1] if len(request.messages) > 1 else []
        response = LLMResponse(text="")
        async for event in adapter.stream(
            prompt, system=request.system, history=history,
            tools=list(request.tools) if request.tools else None,
        ):
            if event.type is LLMStreamEventType.COMPLETED and event.response is not None:
                response = event.response
        return NodeOutput(port_values={"llm_response": response, "usage": response.usage or TokenUsage()})
```

#### `lca/nodes/think/llm/persist.py`(~70 行)

```python
@dataclass(frozen=True, slots=True)
class LlmPersistExecutor:
    semantic_name: str = "llm.persist"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("llm_response", "writer", "step")
    declared_outputs: tuple[PortName, ...] = ("journaled",)
    async def node_execute(self, context, input):
        response = input.port_values["llm_response"]
        writer = input.port_values["writer"]
        step = input.port_values["step"]
        writer.append_assistant_message(
            turn=step, step=step, role="assistant",
            content=response.text,
            tool_calls=[
                {"id": tc.call_id, "name": tc.name, "arguments": tc.arguments}
                for tc in (response.tool_calls or ())
            ] or None,
            usage=response.usage,
        )
        for tc in response.tool_calls or ():
            writer.append_tool_call(turn=step, step=step, call_id=tc.call_id,
                                   name=tc.name, arguments=str(tc.arguments))
        return NodeOutput(port_values={"journaled": True})
```

#### `lca/nodes/think/budget/threshold_gate.py`(~50 行)

```python
@dataclass(frozen=True, slots=True)
class ThinkBudgetThresholdGateExecutor:
    declared_inputs: tuple[PortName, ...] = ("budget",)
    declared_outputs: tuple[PortName, ...] = ("routing",)
    async def node_execute(self, context, input):
        budget = input.port_values["budget"]
        if budget.exceeded(resource=None):
            reason = _pick_exceeded_reason(budget)
            return NodeOutput(port_values={"routing": RoutingDecision(
                action_type=ActionType.STOP, should_terminate=True,
                next_node="terminal.commit", next_hint=reason,
            )})
        return NodeOutput(port_values={"routing": RoutingDecision(
            action_type=ActionType.RESPOND, should_terminate=False,
            next_node="think.context.truncate", next_hint="budget_ok",
        )})
```

#### `lca/nodes/think/context/truncate.py`(~120 行)

只保留 `_payload_byte_size` + `_truncate_oldest_to_byte_budget` + `_should_compact` 的策略实现,**不读 state、不读 writer、不发 routing**。输入 `state.budget` 与 `state.retrieved_context` 改成 typed port 输入。

### 3.4 删 `llm.dispatch` 与 `context_compact` 老节点

- 删 `lca/nodes/think/dispatch/llm.py`(230 行)
- 删 `lca/nodes/think/context_compact.py`(343 行)
- Bundle yaml 中更新 edges:在 `agent/reasoning_turn.yaml` 与 `bundles/think/think_subgraph.yaml`(如有)拆边

### 3.5 Bundle yaml 调整

```yaml
# bundles/think/think_subgraph.yaml (示例,实际需读原文件确认)
nodes:
  - id: think.llm.invoke
    factory: phase.think.llm.invoke
    inputs: [model_visible_request, adapter]
    outputs: [llm_response, usage]
  - id: think.llm.persist
    factory: phase.think.llm.persist
    inputs: [llm_response, writer, step]
    outputs: [journaled]
edges:
  - source: think.llm.invoke
    target: think.llm.persist
  - source: think.llm.persist
    target: think.decision.parse
```

### 3.6 验证矩阵

| 类型 | 命令 | 通过条件 |
|---|---|---|
| 单元 | `uv run pytest tests/think/ tests/cognition/ -x` | 全部通过 |
| 架构 | `uv run pytest tests/architecture/test_node_def_count.py`(新增,断言 think.llm.invoke ≤ 3 methods,think.context.truncate ≤ 4 methods) | 通过 |
| 静态 | `uv run ruff check lca/nodes/think/llm/ lca/nodes/think/budget/ lca/nodes/think/context/` | 0 errors |
| E2E | `./scripts/lca-ops e2e timeline` | 0 failures |
| 手工 | `./scripts/lca-ops timeline <latest_run>` | 能看到 `llm.invoke → llm.persist` 两段独立 spine event |

新增测试:
1. `tests/think/llm/test_invoke.py` — `adapter.stream` mock,断言节点不写 writer
2. `tests/think/llm/test_persist.py` — `writer` mock,断言节点不调 adapter
3. `tests/think/budget/test_threshold_gate.py` — 4 资源各超限/不超限
4. `tests/think/context/test_truncate.py` — 5 个 payload 形态(空 / 小于 target / 大于 target / 多元素混合)

### 3.7 文件清单(PR-B)

| 改动 | 文件 |
|---|---|
| 新增 | `lca/nodes/think/llm/invoke.py`、`lca/nodes/think/llm/persist.py`、`lca/nodes/think/budget/threshold_gate.py`、`lca/nodes/think/context/truncate.py` |
| 删 | `lca/nodes/think/dispatch/llm.py`、`lca/nodes/think/context_compact.py` |
| Bundle yaml | `bundles/think/think_subgraph.yaml`(如有)+ `bundles/primitive/llm_call.yaml` 内含的 dispatch 引用改 invoke/persist |
| 注册 | `bundles/base.yaml` 注册新 4 个 plugin |
| 测试 | 新增 4 个测试文件 + 删 `tests/think/dispatch/` 测试 |

---

## 4. PR-C: 删 3 个 provider plugin,卸余下投影

### 4.1 目标

PR-A + PR-B 已让 graph 完全 typed-port 化;此 PR 删 3 个冗余的 L1/L0 provider plugin,把它们的职责内联到 application 装配根(`lca/application/api/api.py` 的 `spawn_agent` 调用链)。

### 4.2 删 3 个 plugin

| 删 | 当前职责 | 改成 |
|---|---|---|
| `phase.think.role_profile` | `ctx.provide("reasoner.role_profile", RoleProfile)` | `Agent` 构造时把 `RoleProfile` 写进 `AgentSpec.profile`(`api.py:128-134` 已做),runtime 装配时直接 `Agent(role_profile=spec.profile)` |
| `phase.think.reasoner.compose` | 构造 `PromptReasoner(llm, selector, template_provider, section_registry)` 并 provide | `resolve_brain()` 内联构造 `PromptReasoner`,brain 自己持有 |
| `lca-composer-provider` | 注册 `composition.compose_factory` | `application/api/api.py` 装配时直接调用 `CordisComposer(ctx)`,不走 capability 查找 |

### 4.3 卸余下 `phase_capabilities` 投影

`BrainComposer.compose_agent()` 已无投影代码(`PR-A` 末态);`project_runtime_phase_capabilities()` 仅注入 4 个 canonical graph fact(`brain` / `body` / `memory` / `perceive_hub`)。

### 4.4 文件清单(PR-C)

| 改动 | 文件 |
|---|---|
| 删 | `lca/plugins/think/role_profile_provider.py`、`lca/plugins/think/reasoner/compose.py`、`lca/plugins/think/composition/composer_provider.py`、`lca/plugins/think/composition/provider_provider.py` |
| 删 (registry) | `lca/contracts/capabilities.py` 中的 `REASONER_ROLE_PROFILE`、`COMPOSITION_COMPOSE_FACTORY`、`COMPOSITION_INVARIANT_CHECKER` 条目 |
| 改 | `lca/plugins/composer/think/brain.py` 中 `resolve_brain` 直接 `PromptReasoner(...)`(移除 `consume("llm", llm, PromptReasoner)` 间接构造)|
| 改 | `lca/application/api/api.py` 的 `spawn_agent`/`spawn_team` 调用链;直接构造 `CordisComposer` 而非 `ctx.require("composition.compose_factory")` |
| 改 | `bundles/base.yaml` 移除 3 个 plugin 条目 |
| 删 (test) | `tests/architecture/test_reasoner_role_profile_capability.py`(全 4 个测试,断言该 capability 已废)|
| 改 (test) | `tests/architecture/test_composer_factory_capability.py` 改为 `tests/architecture/test_cordis_composer_direct_construction.py`(断言 api 装配根直接构造)|
| 改 (test) | `tests/test_plugin_alignment.py::test_tier1_plugin_shape` 等 plugin shape 测试去掉这 3 个 plugin id |

### 4.5 验证矩阵

| 类型 | 命令 | 通过条件 |
|---|---|---|
| 单元 | `uv run pytest tests/ -x` | 全部通过 |
| 静态 | `uv run ruff check lca/` | 0 errors |
| 静态 | `uv run lint-imports` | 0 errors |
| 静态 | `uv run python scripts/check_package_contracts.py` | 0 errors,**且 plugin 数从 base bundle 减少 3 个** |
| 守护 | `./scripts/lca-ops audit-plugin-shape` | 0 unexpected |
| 守护 | `./scripts/lca-ops why reasoner.role_profile` | "not found"(capability 闭集已不含该 key) |
| E2E | `./scripts/lca-ops e2e timeline` | 0 failures |
| 运行 | `./scripts/lca-ops runs create --user-text "hello"` | 一次完整 run,行为不变 |

### 4.6 兼容性 / delete-when

- `REASONER_ROLE_PROFILE` capability key 删除后,所有 `getattr(runtime, "reasoner.role_profile")` 调用(`lca/nodes/think/reason/render.py:96`、`lca/nodes/think/history/assemble.py:203`)已被 PR-A 改成 `runtime.brain.role_profile` 或删除;此 PR 仅删 capability 注册条目。
- `phase.think.role_profile` plugin 删后,boot profile yaml 不再有该条目;任何测试 fixture 若手工 `ctx.provide("reasoner.role_profile", ...)` 会失败(预期,已无人这么写)。
- `lca-composer-provider` 删后,`application/api/api.py` 装配链直接 `CordisComposer(ctx, invariant_checker=...)`;若其他测试仍通过 `ctx.require("composition.compose_factory")`,改为直接 `CordisComposer(ctx)`。

---

## 5. PR 串行合并顺序

```
PR-A (typed-port 化,卸投影)
   ↓ (graph 节点 100% typed input)
PR-B (拆大节点为单职责节点)
   ↓ (think 节点职责彻底清晰)
PR-C (删 3 个 provider plugin,清 capability 闭集)
   ↓
最终态:
   - BrainComposer 30 行
   - 每个节点 70-150 行,单一职责
   - 0 个节点偷 context.runtime.<field>(白名单 8 个 kernel-injected 字段除外)
   - capability 闭集收紧 ~3 个 key
   - plugin boot-time provide 减少 3 次
```

---

## 6. 风险与回滚

### 6.1 风险点

| 风险 | 应对 |
|---|---|
| 节点 typed-port 化破坏 bundle yaml 中 `inputs:` 字段名假设 | 节点 `declared_inputs` 与 yaml `inputs:` 必须同步改;同一 PR 改两端 + 测试 |
| `brain.<attr>` 访问路径在测试中反射 mock | 测试 fixture 改 `MagicMock(brain=...)` 模式,而非 `MagicMock(reasoner=...)` |
| `think.context_compact` 拆 2 节点后 graph 拓扑变(原来 1 边变 2 边) | E2E 用 `timeline` 验证 spine event 顺序;若顺序敏感,加 typed-port 约束 |
| `PromptReasoner` 构造位置从 plugin 移到 `resolve_brain` 内联 | 测试 `tests/cognition/reasoner/test_prompt_reasoner_fail_matrix.py` 验证构造签名不变 |
| 删 plugin 后 boot profile yaml 不再声明该 plugin | `audit-plugin-shape` 与 `bundle resolve` 兜底;任何漏删的 fixture 立即 fail |

### 6.2 回滚

每个 PR 独立可回滚:
- PR-A 回滚:节点恢复 `getattr(runtime, "<field>")`,`BrainComposer` 恢复投影代码
- PR-B 回滚:恢复 `think.llm.dispatch` 与 `think.context_compact` 单一节点,bundle yaml 边恢复
- PR-C 回滚:恢复 3 个 provider plugin,boot profile 加回 3 行

---

## 7. 验证关卡汇总

| 关卡 | 命令 | 应用 PR |
|---|---|---|
| 类型 | `uv run ruff check lca/` | A/B/C |
| 类型 | `uv run ruff format --check lca/` | A/B/C |
| 导入 | `uv run lint-imports` | A/B/C |
| 契约 | `uv run python scripts/check_package_contracts.py` | A/B/C |
| Plugin shape | `./scripts/lca-ops audit-plugin-shape` | C |
| Notes 体检 | `./scripts/lca-ops notes-check` | A/B/C |
| 单元 | `uv run pytest tests/nodes/ tests/concept/ tests/think/ tests/cognition/ -x` | A/B |
| 集成 | `uv run pytest tests/concept/ tests/integration/ tests/architecture/ -x` | A/C |
| 回归 | `uv run pytest tests/cognition/reasoner/test_prompt_reasoner_fail_matrix.py` | A/C |
| 回归 | `uv run pytest tests/concept/test_prompt_render.py` | A |
| 守护 | `tests/architecture/test_no_runtime_field_theft.py` | A |
| 守护 | `tests/architecture/test_brain_composer_no_projection.py` | A |
| 守护 | `tests/architecture/test_node_def_count.py` | B |
| E2E | `./scripts/lca-ops e2e timeline` | A/B/C |
| 手工 | `./scripts/lca-ops timeline <latest_run>` | B |
| 手工 | `./scripts/lca-ops why reasoner.role_profile` (期望 "not found") | C |

---

## 8. 留作后续(本 plan 不做)

- `PromptReasoner` 的 `build_turn_plan` / `_empty_state_for_selector` 净化(见 §0 上下文第一轮追问) — 与 `concept/template_select` graph 节点重叠;可在 PR-A 后单独 PR 处理
- `history/assemble.py` `_system_from_role_profile` 兜底已在 PR-A 删(`reasoner.role_profile` 去掉后无入口);`_system_from_response` 留着(是 spec §G 真实路径)
- 各 layer 内部的图节点细分(`concept/effect/execute` 拆 dispatcher + surface appender)若发现复用价值再做

---

## 11. Review 发现 — 第二轮:compose / resolver / think 子图整体编排

本节针对 review 问题逐条给出**现状判断 → 第一性原理 → 处理路径**,并将其转成 2 个新 PR(PR-D / PR-E)追加到串行队列。

### 11.1 不合理的 compose / resolver / provider 插件盘点

逐文件过了一遍 `lca/plugins/composer/` 与 `lca/plugins/think/composition/`:

| 插件 / Composer | 行数 | 职责 | 是否合理 | 处理 |
|---|---|---|---|---|
| `BrainComposer` (`composer/think/brain_composer.py`) | 120 | think 集群装配 | **不合理**(14 件事混) | **PR-A** 缩到 ~30 行 |
| `BodyComposer` (`composer/act/body_composer.py`) | 100 | act 集群装配 | **合理**(7 件事都同一职责:act cluster 装配) | **保留** |
| `PerceiveComposer` (`composer/perceive/composer.py`) | 73 | perceive/memory/state 集群装配 | **合理**(5 件事都同一职责:perceive cluster) | **保留** |
| `TeamComposer` (`composer/collaboration/team_composer.py`) | 89 | team 装配 | **合理**(team 是独立 cluster) | **保留** |
| `BrainProvider` (`composer/think/brain_provider.py`) | 64 | 把 `BrainComposer` 包成 plugin | **不合理**(Capability 提供者是 L1 PROVIDER,而 `BrainComposer` 是 application 装配根的 helper,**多此一举** —— 业界没有"为 assembly helper 注册 capability"的范式) | **PR-D §删** |
| `BodyProvider` (`composer/act/body_provider.py`) | 66 | 同上,包 `BodyComposer` | **不合理**(同根因) | **PR-D §删** |
| `PerceiveProvider` (`composer/perceive/provider.py`) | 66 | 同上,包 `PerceiveComposer` | **不合理**(同根因) | **PR-D §删** |
| `TeamProvider` (`composer/collaboration/team_provider.py`) | 67 | 同上,包 `TeamComposer` | **不合理**(同根因) | **PR-D §删** |
| `CordisComposer` (`think/composition/composer_provider.py`) | 284 | mount/unmount dynamic plugin (Creator mode) | **合理**(Creator 是另一个 user-mode) | **保留** |
| `apply_lead_brain` (`composer/think/brain.py`) | (函数) | 给 brain 装上 lead 用的 decision_gate | **不合理**(应该内联到 `ModularBrain.with_gate()`) | **PR-A §改** |
| `instrument_llm` (`composer/think/brain.py`) | (函数) | 装 telemetry + model_visible hook | **合理**(确实是装配根职责) | **PR-A §改名 `application/assemble/llm_instrument.py`** |
| `resolve_brain` (`composer/think/brain.py`) | (函数) | 调 brain factory + 接 prompt catalog | **合理**(装配根职责) | **PR-A §改名 + 放到 application** |
| `LiveActionAuthority` (`composer/act/action_authority.py`) | 55 | 把 `ActionAuthority` policy plan 转成 handler registry | **合理**(action authority 是独立职责) | **保留** |
| `ScopeCapabilityResolver` (`composer/composition/capability_resolution.py`) | 110 | 把 cordis `inject` 适配成 plan binding 用的能力解析 | **不合理**(本质是 `dict` 的 `dict.get`;整个 `CapabilityResolutionError` + `require_exact_bindings` + `require_declared_capabilities` 都是**没有用户的抽象** —— 装配期根本没"missing"或"ambiguous" 这两类失败场景,profile yaml 早 fail-loud 了) | **PR-D §删 + 内联到 `plan_binding.py`** |
| `bind_agent_from_scope` / `bind_plan` / `_composer_candidates` (`composer/composition/plan_binding.py`) | 293 | 编排 5 步 plan → composer → graph | **部分合理**:`bind_plan` / `_composer_candidates` 是真职责;`_validate_capability_bindings` 是**重复扫描** plan(已经 `_composer_candidates` 查过) | **PR-D §精简** |
| `PrompCatalog` provider (`composer/composition/prompt_catalog.py`) | (待查) | 提供 prompt catalog factory | (待确认是否被使用) | **PR-D §verify** |
| `skill_store` provider (`composer/composition/skill_store.py`) | (待查) | 提供 skill store | (待确认) | **PR-D §verify** |
| `RuntimeCapabilityClosure` + 13 个 factory 字段 (`composer/runtime/runtime/capabilities.py`) | 240 | 把 13 个 plan-declared runtime factory 闭合到一个 dataclass | **不合理**(绝大多数字段都是 `factory.create(...)` 调用,**没有任何中间逻辑** —— 这是把 dict 强转 dataclass 增加类型注解,但语义没变化;`bind_runtime_graph` 还要再逐字段 `consume(...)`) | **PR-D §精简:保留 5 个真有 logic 的(Reducer/EffectDispatcherFactory/DeltaReducerFactory/JournalFactory/InterpreterFactory),其余内联为 dict pass-through** |
| `ProductionRuntimeDeps` (`composer/runtime/runtime/deps.py`) | 91 | 把 graph 字段映射到 runtime 字段 | **合理**(数据形状转换) | **保留** |
| `RuntimeCapabilityClosure` 中的 `_RUNTIME_CAPABILITY_KEYS` (16 个) | — | 手动维护的 capability key 白名单 | **不合理**(白名单 16 项中至少有 5 项从来不被节点 typed-port 消费;`runtime.lifecycle_publisher`、`resume_input_adapter` 等是 set-once 闭包字段,**不是节点用**) | **PR-D §收窄到 6 个真被 graph 消费的** |
| `FixtureRuntimeAdapter` (`composer/runtime/fixture/runtime_adapter.py`) | 119 | 测试 fixture → 生产 deps 适配 | **合理**(test seam) | **保留** |
| `NullPerceiveHub` / `FixtureRuntimeAdapter` (`composer/runtime/fixture/runtime_factory.py`) | 31 | 测试默认 perceive hub + fixture 工厂 | **合理**(test seam) | **保留** |
| `bind_runtime_graph` (`composer/runtime/runtime/binding.py`) | 90+ | 把 graph + capabilities 闭合成 `DeclarativeRuntimeBindings` | **合理**(数据形状转换) | **保留** |
| `resolve_node_executor_bindings` (`composer/runtime/runtime/capabilities.py:200-230`) | 30 | 扫 `scope.own_bindings` 拿 NodeExecutor | **不合理**(扫所有 `*::factory` 命名约定的 key —— 这是反射式"service locator",违反 ADR-0195 §1.4 C13;节点应该在 boot 时**显式注册** NodeExecutor 名字到 dict,而不是 kernel 反向扫 string 约定) | **PR-D §改:在 `lca/nodes/` 注册时显式构造 `node_executors: Mapping[str, NodeExecutor]` dict,kernel 直接消费,不再扫** |
| `AgentAssemblyPort` + `PlanBoundAgentAssembler` (`composer/composition/agent_assembly.py`) | 170 | "为 TeamComposer 提供的 narrow recursion seam" | **不合理**(TeamComposer 自己能调 `assemble_agent`,不需要额外 port) | **PR-D §删掉 Port,把 TeamComposer 直接调 `PlanBoundAgentAssembler.assemble_agent`** |
| `promote_lead` (`composer/composition/agent_assembly.py:128-148`) | 20 | lead agent 重写 budget 限制 | **合理**(lead promotion 是独立职责) | **保留** |

### 11.2 think 子图编排 — 现状与业界对照

#### 11.2.1 think subgraph 现状全图

```
┌─────────────────────────────────────────────────────────────────┐
│ think.subgraph                                                  │
│                                                                 │
│  think.shortcut ──→ think.route.decide ──→ think.gate          │
│                              │               (short-circuit path)│
│                              ↓ (miss path)                       │
│                       think.budget.check                        │
│                              │ ok                               │
│                              ↓                                  │
│                       think.context.compact                     │
│                              │ ok                               │
│                              ↓                                  │
│                          think.route ──→ think.reason           │
│                                              │                  │
│                                              ↓                  │
│                          think.history.assemble                 │
│                                              │                  │
│                                              ↓                  │
│                          think.llm.dispatch                     │
│                                              │                  │
│                                              ↓                  │
│                          think.decision.parse                   │
│                                              │                  │
│                                              ↓                  │
│                          think.decision.repair                  │
│                                              │ (ok/repaired)    │
│                                              ↓                  │
│                                            think.gate          │
│                                                                 │
│  (think.budget.check 超限 → terminal.commit)                    │
└─────────────────────────────────────────────────────────────────┘

子图内节点数: 11
单节点平均行数: ~155 (含 think.context_compact 343 + history.assemble 302)
数据事实点:
  - role_profile  -> AgentSpec.profile (构造期,application)
  - brain         -> RuntimePhaseCapabilities["brain"] (composition)
  - brain.reasoner / skill_router / decision_gate / supports_shortcut
                 -> context.runtime.<name> (节点偷字段)
  - state         -> context.runtime.state (kernel)
  - writer        -> context.runtime.writer (kernel)
```

#### 11.2.2 业界 think 节点范式

| 框架 | think 节点数 | 节点职责 | 信息流 |
|---|---|---|---|
| **LangGraph** | 1-3 | `prepare_context` / `llm_call` / `parse_output` | typed state dict,每节点显式 read/write state |
| **CrewAI** | 1 (`Agent.step`) | "执行 task → 输出" | role + tools + goal 构造时定型,无 runtime capability |
| **Anthropic** | 1 (`messages.create`) | "prompt → completion" | 单一 system+user prompt,无 graph |
| **OpenAI Agents SDK** | 2 (`Runner.run` → `agent.execute`) | "prepare input → call LLM" | instructions 构造时定型,无 capability 查找 |
| **LangChain** | 1-2 (`PromptTemplate` + `LLMChain`) | "fill template → call" | runtime 无 capability 概念 |
| **LCA 当前** | **11** | 看上面那张图 | `context.runtime.<field>` 偷字段 |

**业界共识**:think 子图应该是 **3-5 个** 显式节点,每节点 = **1 个"准备-执行-观察"完整动作**,信息流是 **typed state dict**(LangGraph 风格)或 **构造期定型 role**(其他 4 家)。

LCA 11 个节点偏多,**主要冗余**:
1. `think.route.decide` 与 `think.budget.check` 与 `think.context.compact` 三个**纯 gate**(无 LLM、无 IO、只读 state + 发 routing) — 业界 1 个 `decide` 节点足矣
2. `think.history.assemble` 与 `think.llm.dispatch` 拆得过细,且 history.assemble 还在做"3 级 fallback 拼 system prompt"(`_system_from_role_profile`)
3. `think.reason.fork_tools → think.reason.plan → think.reason.render` 三个**纯内部 sub-step**,在 `bundles/think_reason.yaml` 与新 `agent/reasoning_turn.yaml` 间有重复(PR-A 后 fork_tools 已被 `concept.tool_fork` 取代)
4. `think.decision.repair` 是 JSON 修复节点,**业界不该存在于 think 子图**(OpenAI/CrewAI 都直接放弃坏 JSON,langgraph 用 retry policy)— 应改 typed-boundary 自描述

#### 11.2.3 think 子图"应做" — 第一性原理

**认知学**:think 子图的目的是**回答"下一步做什么"**(下一动作 + 所需 evidence)。
**认知子任务**(业界共识):
1. **准备**:把 role + state + context + skills + tools 拼成 LLM prompt(纯变换)
2. **执行**:调 LLM(纯 IO)
3. **解析**:LLM 输出 → typed `Decision`(纯变换)
4. **控制**:用 Gate 校验 + 短路径(纯变换,可能 no-op)

→ **理想节点数 = 4**(prep / call / parse / control),对应 4 个边界 DTO:`ReasonerTurnRequest` / `LLMResponse` / `Decision` / `Decision`。

#### 11.2.4 think 子图现状的真实问题

按"职责彻底"原则审视每个节点:

| 节点 | 它真实做了几件事 | 问题 |
|---|---|---|
| `think.shortcut` | 1 — `brain.decision_gate.try_shortcut(state)` | 合理,但**不是 think 节点** —— 它在"决定走不走 LLM"之前,应该是**graph entry** 的一个早期分支,不是 think 内第一个节点 |
| `think.route.decide` | 1 — 读 decision, 发 routing | 合理,**但**它的"routing 决定"本身就是 think 的产物,不需要独立节点 — 应内联到 `think.shortcut` 或 graph entry |
| `think.budget.check` | 1 — 读 budget, 发 routing | 合理,但**不应在 think 内部** — budget 是 outer-loop concern,应在 `agent/main` 层做 |
| `think.context.compact` | 2 — 闸门 + truncate 策略 | 拆分后是两个节点(PR-B 已含) |
| `think.route` | 2 — `skill_router.route(state)` + `reducer.apply_skill_route(state, ...)` | 拆 router / reducer fold 两个节点,或内联到 think 入口 |
| `think.reason` (subgraph) | 1 — `concept.tool_fork` + `concept.template_select` + `concept.prompt_render` 组合 | 已经是 subgraph,合理。但 fork_tools 与 prepare 完全重复(都是 typed DTO 转换),应合并到 `reason.prepare` 一个概念节点 |
| `think.history.assemble` | 2 — 拼 messages + 拼 system prompt (3 级 fallback) | 拼 system prompt 不属于 history 节点;应是 `concept.prompt_render` 职责 |
| `think.llm.dispatch` | 2 — adapter.stream + writer.append_(assistant/tool_call) | PR-B 拆 |
| `think.decision.parse` | 1 — `LLMResponse → Decision` | 合理 |
| `think.decision.repair` | 1 — JSON 修复 + routing | 修复属于 typed-boundary 自描述,**应删**;让 LLM 失败 = 重试(retry policy) |
| `think.gate` | 1 — `decision_gate.enforce(state, decision)` | 合理 |

**节点数目标**:11 → 5(`prep` / `call` / `parse` / `gate` / `repair`-removed)

#### 11.2.5 think 信息流"应做"

```
                 ┌──────────────────────────────────────┐
                 │ graph entry (agent.main)             │
                 │   reads: bindings, role, state        │
                 │   emits: typed ReasoningRequest       │
                 └────────────┬─────────────────────────┘
                              │
                 ┌────────────┴────────────────────────┐
                 │ think.prep (1 节点)                  │
                 │   reads: ReasoningRequest, brain     │
                 │   emits: ReasonerTurnRequest         │
                 │   - role snapshot, manifest          │
                 │   - tool fork                        │
                 │   - template selection               │
                 │   - prompt render                    │
                 └────────────┬─────────────────────────┘
                              │
                 ┌────────────┴────────────────────────┐
                 │ think.call (1 节点,PR-B 拆 invoke+persist)│
                 │   reads: ReasonerTurnRequest, adapter│
                 │   emits: LLMResponse + journaled     │
                 └────────────┬─────────────────────────┘
                              │
                 ┌────────────┴────────────────────────┐
                 │ think.parse (1 节点)                 │
                 │   reads: LLMResponse                │
                 │   emits: Decision                   │
                 │   - reject malformed JSON (typed)   │
                 └────────────┬─────────────────────────┘
                              │
                 ┌────────────┴────────────────────────┐
                 │ think.gate (1 节点)                  │
                 │   reads: Decision, brain.gates      │
                 │   emits: Decision (enforced)        │
                 └──────────────────────────────────────┘
```

**5 个节点,每个 1 件事**;`reasoner.role_profile` capability 全删;信息流 typed port 一路到底;没有"从 context.runtime 偷字段"。

### 11.3 业界范式对照表(认知清晰度审计)

| 维度 | LCA 现状 | 业界共识 | LCA 应到 |
|---|---|---|---|
| think 节点数 | 11 | 3-5 | 5 (PR-A + PR-E) |
| 节点偷字段数 | 12 | 0 | 0 (PR-A 全部解决) |
| 单节点做几件事 | 最多 2-3 (think.context_compact) | 1 | 1 (PR-A/B/E 拆分) |
| Composer 数量 | 4 (Brain/Body/Perceive/Team) | 0-1 (多数框架直接 inline) | 4 (LCA 留 4 个,**但去其 Provider 包装**) |
| Composer Provider 数 | 4 (`lca-plan-brain-composer` 等) | 0 | 0 (PR-D 全删) |
| Capability 闭集数 | 99 | ~20 (业界平均) | **<50 (PR-A/C/D 收 ~15-20)** |
| Agent 装配链深度 | plan → 4 composers → RuntimeCapabilityClosure(13 字段) → ProductionRuntimeDeps(20+ 字段) → DeclarativeRuntimeBindings → CognitiveRuntime | 1-2 步 | **2 步 (CompiledPlan + Agent dataclass)** |

---

## 12. PR-D: 删 composer Provider 包装,精简 plan binding 与 runtime 装配链

### 12.1 目标

清掉"为 application-layer helper 注册 capability"的 4 个 Provider 包装,合并 `ScopeCapabilityResolver` 进 `plan_binding`,收窄 `RuntimeCapabilityClosure` 到 6 字段真有用的,改 `resolve_node_executor_bindings` 不再扫 string 约定。

### 12.2 文件清单(PR-D)

| 改动 | 文件 | 内容 |
|---|---|---|
| 删 | `lca/plugins/composer/think/brain_provider.py` | `lca-plan-brain-composer` plugin;`BrainComposer` 直接由 application 装配根调用 |
| 删 | `lca/plugins/composer/act/body_provider.py` | 同根因 |
| 删 | `lca/plugins/composer/perceive/provider.py` | 同根因 |
| 删 | `lca/plugins/composer/collaboration/team_provider.py` | 同根因 |
| 删 | `lca/plugins/composer/composition/capability_resolution.py` (110 行) | `ScopeCapabilityResolver` / `CapabilityResolutionError` / `require_exact_bindings` / `require_declared_capabilities` 内联进 `plan_binding.py` |
| 改 | `lca/plugins/composer/composition/plan_binding.py` | 把 `_composer_candidates` 内的 capability 解析从 `ScopeCapabilityResolver` 改成 dict-like local lookup;删 `_validate_capability_bindings`(已包含在 `_composer_candidates` 中) |
| 改 | `lca/plugins/composer/composition/agent_assembly.py` | 删 `AgentAssemblyPort` Protocol 与 `PlanBoundAgentAssembler` class 双重结构;`TeamComposer` 直接持有 `PlanBoundAgentAssembler` 实例,调 `assemble_agent` |
| 改 | `lca/plugins/composer/runtime/runtime/capabilities.py` | `RuntimeCapabilityClosure` 字段从 13 收窄到 6(`reducer` / `effect_dispatcher_factory` / `delta_reducer_factory` / `journal_factory` / `interpreter_factory` / `runtime_factory`);其余 7 项(`effect_handler_registry` / `delta_handler_registry` / `artifact_closure` / `idempotency_store` / `resume_input_adapter` / `checkpoint_state_resolver_factory` / `result_finalizer_factory` / `phase_observer` / `lifecycle_publisher`)改为 dict pass-through |
| 改 | `lca/plugins/composer/runtime/runtime/capabilities.py:resolve_node_executor_bindings` | 删;改由节点注册时显式构造 `dict[str, NodeExecutor]`,存 `production_deps.node_executors` |
| 改 | `lca/plugins/composer/runtime/runtime/deps.py` | `node_executors` 字段类型改为显式 `dict[str, NodeExecutor]`(非 `Mapping`);`_RUNTIME_GRAPH_FIELDS` 与 `_RUNTIME_CAPABILITY_KEYS` 收窄到 graph 真消费的 6 个 |
| 改 | `lca/plugins/composer/runtime/runtime/binding.py` | `from_runtime_graph` 不再传 `consume(...)` 包装(直接 dict access) |
| 改 | `lca/application/api/api.py` `spawn_agent` / `spawn_team` 调用链 | 直接构造 `BrainComposer` / `BodyComposer` / `PerceiveComposer` / `TeamComposer`,不走 `ctx.require("composer.brain")` 等 |
| 改 | `bundles/base.yaml` | 删 4 个 `lca-plan-*-composer` plugin 条目 |
| 改 | `tests/composer/test_composer_consumes_compiled_capability.py` | 改测试为"application 装配根直接构造 composer" |
| 删 | `tests/architecture/test_composer_factory_capability.py` (若有) | 同 PR-C |

### 12.3 验证矩阵

| 类型 | 命令 | 通过条件 |
|---|---|---|
| 单元 | `uv run pytest tests/ tests/composer/ -x` | 全部通过 |
| 静态 | `uv run ruff check lca/` | 0 errors |
| 静态 | `uv run lint-imports` | 0 errors |
| 静态 | `uv run python scripts/check_package_contracts.py` | 0 errors,且 plugin 数从 base bundle 减少 4 个 |
| 守护 | `tests/architecture/test_no_runtime_field_theft.py`(PR-A) | 仍通过 |
| 守护 | `tests/architecture/test_brain_composer_no_projection.py`(PR-A) | 仍通过 |
| 新增 | `tests/architecture/test_no_composer_provider_layer.py` | 断言 `lca.plugins.composer.*.provider` 子目录不存在 |
| 新增 | `tests/architecture/test_no_capability_resolution_abstract.py` | 断言 `ScopeCapabilityResolver` / `CapabilityResolutionError` 不再 import |
| 新增 | `tests/architecture/test_runtime_capability_closure_slim.py` | 断言 `RuntimeCapabilityClosure` 字段数 ≤ 8 |
| E2E | `./scripts/lca-ops e2e timeline` | 0 failures |
| 运行 | `./scripts/lca-ops runs create --user-text "hello"` | 一次完整 run |

### 12.4 风险与回滚

- **风险**:删 4 个 Provider 后,旧测试 fixture 直接 `ctx.require("composer.brain")` 失败 → 同步改测试
- **回滚**:恢复 4 个 Provider plugin,`bundles/base.yaml` 加 4 行

---

## 13. PR-E: think 子图重组 — 11 → 5 节点

### 13.1 目标

把 think subgraph 从 11 节点精简到 5 节点(`prep` / `call` / `parse` / `gate` + 保留入口决策),每节点 1 件事,信息流 typed port 一路到底,删除 `think.decision.repair`(改成 typed-boundary reject 与 retry policy),删除 `_system_from_role_profile` 兜底,删除 `think.budget.check`(移到 outer-loop agent/main 层)。

### 13.2 节点拆分/合并表

| 当前节点 | 处理 | 新节点 (PR-E 后) |
|---|---|---|
| `think.shortcut` | **保留**,入口节点,但 routing 责任内联 | `think.shortcut`(不变,90 行) |
| `think.route.decide` | **删除** — routing 在 graph entry 层做,或由 shortcut/route 节点承担 | (删除) |
| `think.budget.check` | **删除并外移** — budget 是 outer-loop concern | (移到 `agent/main` 图,独立节点) |
| `think.context.compact` | **PR-B 拆**,但 `think.context.compact` 名字删除,改 `think.compact.gate` + `think.compact.truncate` | (PR-B 拆分后的两个节点,改名) |
| `think.route` | **内联** — skill_router.route + reducer.apply_skill_route 合并到 `think.prep` | (删除) |
| `think.reason` subgraph | **合并** — fork_tools 不再独立节点,合到 prep;plan/render 走 `concept.template_select` + `concept.prompt_render` | `think.prep`(新,见下) |
| `think.history.assemble` | **删除** — `_system_from_role_profile` 删(随 PR-A `reasoner.role_profile` capability 已废);`_system_from_response` 留作 spec §G 真实路径但搬到 `concept.prompt_render` 内的 `_resolve_system` | (删除) |
| `think.llm.dispatch` | **PR-B 拆** `invoke` + `persist` | `think.call.invoke` + `think.call.persist`(PR-B 已含) |
| `think.decision.parse` | **保留** | `think.parse`(不变,90 行) |
| `think.decision.repair` | **删除** — typed-boundary 自描述 JSON schema 校验在 parse 节点完成;repair 逻辑挪到 retry policy | (删除) |
| `think.gate` | **保留** | `think.gate`(不变,80 行) |

### 13.3 新节点: `think/prep.py`

```python
"""phase.think.prep — single prep node: produce ReasonerTurnRequest."""

@dataclass(frozen=True, slots=True)
class ThinkPrepExecutor:
    semantic_name: str = "think.prep"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("state",)
    declared_outputs: tuple[PortName, ...] = ("turn_request",)

    async def node_execute(self, context, input):
        state = input.port_values["state"]
        brain = context.runtime.brain    # typed Protocol access

        # 1. role snapshot: brain.role_profile (constructed with Agent)
        role_snapshot = RoleSnapshot(
            profile=brain.role_profile,
            team_awareness=state.team_awareness,
        )

        # 2. tool fork: brain.tools_service.fork_for_run(bindings)
        bindings = _current_bindings()  # ContextVar seam
        forked_tools = ForkedTools(
            items=tuple(brain.tools_service.fork_for_run(bindings).list_tools()),
            binding_keys=("tools",),
        )

        # 3. template select: brain.template_selector.select(state)
        template_selection = brain.template_selector.select(state=state)

        # 4. prompt render: render_template(...) → ReasonerTurnRequest
        prompt, trace = render_template(
            template=brain.template_provider.get_template(template_selection.template_id),
            registry=brain.prompt_section_registry,
            role_profile=role_snapshot.profile,
            awareness=role_snapshot.team_awareness,
            manifest=state.context,
            tools=forked_tools.items,
            activated_skills=state.activated_skills,
            selector_decision_path=template_selection.decision_path,
        )
        return NodeOutput(port_values={
            "turn_request": ReasonerTurnRequest(
                prompt=prompt,
                system=trace.system_prompt_text,
                messages=state.messages,   # for history assembly
                tools=forked_tools.items,
            )
        })
```

`ReasonerTurnRequest` 是新 typed boundary DTO,把 prompt + system + messages + tools **一处装齐**,下游 `think.call.invoke` 直接吃。

### 13.4 新 outer-loop 节点: `agent/main/budget_check.py`

把 `think.budget.check` 移到 `agent/main` 图,**节点名 `agent.main.budget`**。在 outer loop 里跑 budget check 而不是 inner think,符合"budget 是 outer-loop concern"。

```python
@dataclass(frozen=True, slots=True)
class AgentMainBudgetExecutor:
    semantic_name: str = "agent.main.budget"
    region: str = "agent"
    declared_inputs: tuple[PortName, ...] = ("state",)
    declared_outputs: tuple[PortName, ...] = ("routing",)
    # 与 PR-B 的 think.budget.threshold_gate 同形
```

### 13.5 文件清单(PR-E)

| 改动 | 文件 |
|---|---|
| 新增 | `lca/nodes/think/prep.py` (~120 行) |
| 新增 | `lca/nodes/agent/main/budget.py` (~50 行) |
| 删 | `lca/nodes/think/route/decide.py`, `lca/nodes/think/budget_check.py`, `lca/nodes/think/context_compact.py`(已在 PR-B 拆), `lca/nodes/think/route/route.py`, `lca/nodes/think/reason/{plan,render,fork_tools}.py`(若 fork_tools 仍存在), `lca/nodes/think/history/assemble.py`, `lca/nodes/think/decision_repair.py` |
| 删 (subgraph) | `bundles/think_reason.yaml`(被 `think.prep` 取代) |
| 改 | `bundles/think/think_subgraph.yaml` — 11 节点 → 5 节点 |
| 改 | `bundles/agent/main.yaml` — 加 `agent.main.budget` 节点 + 边 |
| 改 | `bundles/agent/reasoning_turn.yaml` — `reason.*` 边重写到 `think.prep` |
| 改 | `bundles/base.yaml` — 注册新 2 plugin;删 `phase.think.reason.*` |
| 新增 contract | `lca/contracts/models/cognition/boundary.py` — `ReasonerTurnRequest` DTO |
| 改 | `lca/cognition/brain/pipeline/modular_brain.py` — 暴露 `role_profile` / `tools_service` / `template_selector` / `template_provider` / `prompt_section_registry` 字段(目前 `reasoner` + `skill_router` + `decision_gate` 之外再补) |
| 删 (test) | `tests/think/route/`, `tests/think/dispatch/`(PR-B 已删), `tests/think/history/` 的 `test_assemble.py`, `tests/think/test_decision_repair.py` |
| 新增 (test) | `tests/think/test_prep.py`, `tests/agent/main/test_budget.py` |

### 13.6 验证矩阵

| 类型 | 命令 | 通过条件 |
|---|---|---|
| 单元 | `uv run pytest tests/think/ tests/agent/ -x` | 全部通过 |
| 静态 | `uv run ruff check lca/nodes/think/ lca/nodes/agent/` | 0 errors |
| 静态 | `uv run python scripts/check_package_contracts.py` | 0 errors |
| 守护 | `tests/architecture/test_node_count.py`(新)— 断言 `think.subgraph` 节点数 ≤ 5 | 通过 |
| E2E | `./scripts/lca-ops e2e timeline` | 0 failures |
| 手工 | `./scripts/lca-ops timeline <latest_run>` | spine event 序列: `shortcut → prep → call.invoke → call.persist → parse → gate`,无 think.context.compact / think.history.assemble / think.decision.repair 事件 |

### 13.7 风险与回滚

- **风险**:大改 think 拓扑,触发 E2E 多路径回归 → E2E 必有,且 `audit-state-writers` 守护多写
- **回滚**:恢复 think.subgraph 11 节点版本,`bundles/think/think_subgraph.yaml` git revert

---

## 14. 最终 PR 串行队列

```
PR-A (typed-port 化,卸 BrainComposer 投影)
   ↓
PR-B (拆 think.llm.dispatch + think.context_compact 为单职责节点)
   ↓
PR-C (删 3 个冗余 provider plugin: phase.think.role_profile / phase.think.reasoner.compose / lca-composer-provider)
   ↓
PR-D (删 4 个 composer Provider 包装 + 精简 plan_binding + 收窄 RuntimeCapabilityClosure + 删 ScopeCapabilityResolver)
   ↓
PR-E (think subgraph 11 → 5 节点: shortcut → prep → call → parse → gate;删 budget.check / route / route.decide / history.assemble / decision.repair,外移 budget 到 agent.main)
   ↓
最终态:
   - think subgraph 节点数: 11 → 5
   - composer Provider 数: 4 → 0(BrainComposer 等直接由 application 装配)
   - capability 闭集数: 99 → 65 (估计)
   - 每个节点职责数: 1.5 → 1
   - node 平均行数: 155 → 100
   - RuntimeCapabilityClosure 字段数: 13 → 6
   - composer/helper 抽象层数: 6 → 1(只剩 composer.py,提供 4 个 cluster Composer)
```

---

## 15. 完成判据(每 PR,完整版)

### PR-A(typed-port 化)

- [ ] 15 个目标节点改完,新增 2 个守护测试通过
- [ ] `BrainComposer.compose_agent()` ≤ 35 行
- [ ] `phase_capabilities` 投影仅剩 `{}` 在 composer 出口
- [ ] `uv run pytest tests/architecture/ tests/nodes/ tests/think/ -x` 全绿
- [ ] `lint-imports` 与 `check_package_contracts.py` 0 新引入失败
- [ ] E2E 0 failures

### PR-B(拆大节点)

- [ ] 4 个新节点文件已写,`think.llm.dispatch` 与 `think.context_compact` 已删
- [ ] 节点平均行数 ≤ 130,def 数 ≤ 4
- [ ] 相关 bundle yaml 边已重
- [ ] spine timeline 能看到 `llm.invoke → llm.persist` 两段独立 event
- [ ] E2E 0 failures

### PR-C(删 3 plugin)

- [ ] 3 plugin + 3 capability key 删,bundle boot provide 次数减 3
- [ ] `application/api/api.py` 直接构造 `CordisComposer`
- [ ] `audit-plugin-shape` 与 `why reasoner.role_profile` 期望输出与 §7 一致
- [ ] E2E + 一次真实 run 通过

### PR-D(去 composer Provider 抽象)

- [ ] 4 个 `lca-plan-*-composer` plugin 删
- [ ] `ScopeCapabilityResolver` / `CapabilityResolutionError` 内联到 `plan_binding.py` 或删
- [ ] `RuntimeCapabilityClosure` 字段数 ≤ 8
- [ ] `resolve_node_executor_bindings` 改为显式注册,不再扫 string 约定
- [ ] `AgentAssemblyPort` 删,`TeamComposer` 直接持有 `PlanBoundAgentAssembler`
- [ ] 4 个新守护测试通过
- [ ] E2E 0 failures

### PR-E(think 子图 11 → 5)

- [ ] `think.prep` 节点已写,合并了 fork_tools + role_snapshot + template_select + prompt_render + system_prompt fallback
- [ ] `think.route` / `think.route.decide` / `think.history.assemble` / `think.decision.repair` 删
- [ ] `think.budget.check` 移到 `agent.main.budget`
- [ ] `bundles/think/think_subgraph.yaml` 节点数 ≤ 5
- [ ] `bundles/agent/main.yaml` 含 budget 节点
- [ ] `bundles/think_reason.yaml` 删(并入 `concept/*` + `think.prep`)
- [ ] `tests/architecture/test_node_count.py` 通过
- [ ] E2E + 一次真实 run 通过

---

## 16. 留作后续(本 plan 仍不做)

- `CognitiveRuntime` (`runtime/loop/runtime_loop.py`) 与 `DeclarativeRuntimeDriver` (`loop/driver.py`) 的关系 — 是否可以再合并一层
- `Reductions` / `DeltaReducer` / `ResultFinalizer` 的接口收窄
- 各 transport plugin 的 typed-boundary 化(lobehub / webserver)
- Per-run `RunSessionWriter` 与 `bind_run_event_session_from_store` 的 kernel-injected runtime carrier 路径是否再瘦一层

---

## 17. Boot / Run 启动验证矩阵(防御性关卡)

针对 review "重启 kernel boot 不通过 / run 有问题" 风险,逐 PR 显式给出**三类失败模式**的捕获命令与预期信号。每一类都必须在 PR merge 前**实地跑通**,不是"应该会通过"。

### 17.1 三类失败模式

| 失败模式 | 现象 | 在 LCA 中何时触发 |
|---|---|---|
| **F1: Kernel boot 不通过** | `lca-ops kernel-restart` 退出非 0,或 `lca-ops status --json` 显示 `kernel.status != running`,或 `bundles/base.yaml` resolve 阶段抛 `CapabilityResolutionError` | PR-C / PR-D 删 plugin 或 capability 时漏删 `bundles/base.yaml` 引用,或新 capability 没注册 |
| **F2: Run 创建阶段失败** | `lca-ops runs create --user-text "hello"` 退出非 0,或 `runs.create` HTTP 500 | PR-A 节点 typed-port 化漏改 yaml `inputs:` 字段名,PR-D `TeamComposer` 装配路径断裂 |
| **F3: Run 执行过程中失败** | E2E timeline 报 `node_executor_serve_error` 或 `typed-port-unset`,run 状态 `failed` | PR-E think 子图拓扑错,bundle 边指向已删节点 |

### 17.2 每 PR 的防御性验证(必须跑通)

#### 17.2.1 PR-A 防御性关卡

| 关卡 | 命令 | 期望信号 | 失败排查路径 |
|---|---|---|---|
| **Kernel boot 解析** | `./scripts/lca-ops status --json` | `{"kernel.status": "running", "profile": "web-standard"}` | 若 `kernel.status: "stopped"`,`./scripts/lca-ops kernel-restart` 看 stderr;期望错一定是 `phase.think.role_profile` 已删但 `bundles/base.yaml` 还有条目 → 回退 PR-A |
| **Profile resolve** | `uv run python -c "from lca.harness.profile.resolve.resolve import resolve_profile; p = resolve_profile('profiles/web-standard.yaml'); print(f'plugins={len(p.plugins)}')"` | `plugins ≥ 80`(原 84 减 0,PR-A 不删 plugin) | 数字不对即 resolve 失败 |
| **Run 创建路径** | `./scripts/lca-ops runs create --user-text "test boot"` | 返回 `run_id`, `state: queued` | 若 HTTP 500,查 `runs create` log 是否有 `phase.think.role_profile` 引用 |
| **Run 执行到底** | `./scripts/lca-ops timeline <run_id>` | 5+ 个 spine event,无 `error` channel | 若有 `error` 记录,是节点 typed-port 接错 |
| **Kernel 重启稳定性** | `./scripts/lca-ops kernel-restart && ./scripts/lca-ops status --json` | 二次 status 仍 `running` | 第一次启动时 boot 通过但缓存了 stale state → 检查 PR-A 改的 `_AdapterScope` 是否每次都重读 |

新增守护测试 `tests/architecture/test_pr_a_boot_invariants.py`:

```python
def test_kernel_boot_does_not_register_removed_capabilities():
    """PR-A 末态:`reasoner.role_profile` 不在 capability 闭集。"""
    from lca.contracts.capabilities import REASONER_ROLE_PROFILE
    # capability 对象本身保留(向后兼容 import),但不被 boot 路径 register
    # 通过 audit-plugin-shape 兜底

def test_node_field_theft_static_scan():
    """节点不允许从 context.runtime 偷字段(白名单外)。"""
    # 实现:AST 扫描 lca/nodes/**/*.py,匹配
    #   getattr(context.runtime, "X")
    #   context.runtime.get("X")
    #   context.runtime.X
    # 其中 X ∈ {非白名单} 即 fail
    ALLOWED = {"state", "writer", "effect_gateway", "cursor",
               "brain", "body", "memory", "perceive_hub"}
```

#### 17.2.2 PR-B 防御性关卡

| 关卡 | 命令 | 期望信号 |
|---|---|---|
| **拆分后 spine 顺序** | 创建 run,看 `timeline` | `llm.call.invoke → llm.call.persist → decision.parse` 三个独立 spine event(原来是 1 个 `llm.call`) |
| **Compact 拆分后 routing 正确** | 创建会触发 budget 用尽的 run | `routing.next_hint ∈ {"compact_done", "compact_noop", "compact_skipped_error"}` 三种都出现 |
| **Kernel 不重启** | 同 PR-A,但额外验:`uv run pytest tests/architecture/test_node_def_count.py -v` | 每个新节点 def 数 ≤ 4 |

#### 17.2.3 PR-C 防御性关卡(boot 风险最高)

| 关卡 | 命令 | 期望信号 |
|---|---|---|
| **Plugin shape** | `./scripts/lca-ops audit-plugin-shape` | 不出现 `phase.think.role_profile` / `phase.think.reasoner.compose` / `lca-composer-provider` 任何一条 |
| **Capability 不存在** | `./scripts/lca-ops why reasoner.role_profile` | "not found"(key 已被删) |
| **Boot yaml 一致** | `uv run python -c "from lca.harness.profile.resolve.resolve import resolve_profile; resolve_profile('bundles/base.yaml')"` | 无 `CapabilityResolutionError` |
| **Run 完整跑通** | `./scripts/lca-ops runs create --user-text "hello, run after plugin cleanup"` | 返回 `run_id` 且 5 分钟内 `state: succeeded` |
| **History run 重放不爆** | `./scripts/lca-ops debug-run <一个已有 run_id>` | journal 重放 OK,无 `AttributeError: 'PromptReasoner' has no attribute 'role_profile'` 之类 |

#### 17.2.4 PR-D 防御性关卡

| 关卡 | 命令 | 期望信号 |
|---|---|---|
| **Composer 实例化** | `uv run python -c "from lca.plugins.composer.think.brain_composer import BrainComposer; b = BrainComposer(); r = b.compose_agent(mock_request, mock_scope); assert r.phase_capabilities == {}"` | `phase_capabilities == {}` |
| **Plan binding 路径** | `uv run pytest tests/composer/ tests/plan/ -x` | 全绿 |
| **Team 装配路径** | 创建一个 2-Agent team 并 run | TeamComposer 直接持有 assembler,无 `AgentAssemblyPort` 间接 |
| **NodeExecutor 注册** | `uv run pytest tests/architecture/test_no_string_scan_node_executors.py` | `resolve_node_executor_bindings` 已被替换,不存在 |
| **Run 完整跑通** | 同 PR-C | |

#### 17.2.5 PR-E 防御性关卡

| 关卡 | 命令 | 期望信号 |
|---|---|---|
| **think.subgraph 节点数** | `uv run pytest tests/architecture/test_node_count.py::test_think_subgraph_leq_5 -v` | 通过 |
| **think.reason.* 边不存在** | `rg "think\.reason\.(plan|render|fork_tools|complete)" bundles/ lca/nodes/` | 0 hit |
| **Prep 节点单跑** | `uv run pytest tests/think/test_prep.py -v` | 通过 |
| **Run 完整跑通(shortcut 命中)** | 创建已知触发 `try_shortcut` 的 run | `timeline` 第一段 `think.shortcut` 直接出 `decision`,**不**经过 `think.prep` |
| **Run 完整跑通(shortcut miss)** | 普通 run | `shortcut → prep → call.invoke → call.persist → parse → gate` 顺序 |
| **Run 完整跑通(budget 超限)** | 创建会超 budget 的 run | `agent.main.budget` 触发 `terminal.commit`,**不**走 think 子图 |
| **Repair 节点不再存在** | `rg "decision\.repair\|decision_repair" bundles/ lca/nodes/` | 0 hit |
| **History.assemble 不存在** | `rg "think\.history\.assemble\|history\.derive" bundles/think/ lca/nodes/think/` | 0 hit |

### 17.3 通用兜底关卡(每 PR merge 前必跑)

```bash
# 1. 静态 — 不能引入新失败
uv run ruff check lca/ tests/
uv run lint-imports
uv run python scripts/check_package_contracts.py

# 2. Plugin shape — boot 期 fail-loud
./scripts/lca-ops audit-plugin-shape
./scripts/lca-ops notes-check
./scripts/lca-ops notes-audit

# 3. 单元 / 集成 — 类型契约不破
uv run pytest tests/architecture/ tests/concept/ tests/think/ tests/cognition/ tests/composer/ tests/plan/ -x

# 4. 真 boot — kernel 启动不挂
./scripts/lca-ops kernel-restart
./scripts/lca-ops status --json  # 必须 {"kernel.status": "running"}

# 5. 真 run — boot 完了还要能创建 + 执行
RUN_ID=$(./scripts/lca-ops runs create --user-text "boot-validate after PR-X" | jq -r .run_id)
./scripts/lca-ops timeline $RUN_ID  # 必须 ≥ 5 spine event,无 error channel

# 6. 重启稳定性 — 二次 boot 不挂
./scripts/lca-ops kernel-restart
./scripts/lca-ops status --json

# 7. 重放稳定性 — 历史 run 用新代码能重放
LATEST_RUN=$(./scripts/lca-ops runs list --limit 1 --json | jq -r '.[0].run_id')
./scripts/lca-ops debug-run $LATEST_RUN  # 必须 succeed
```

### 17.4 失败时回滚清单(PR-E 失败举例)

| 失败现象 | 第一排查动作 | 回滚路径 |
|---|---|---|
| `kernel-restart` exit 非 0 | `./scripts/lca-ops status --json --verbose` | `git revert <PR-E-sha> && ./scripts/lca-ops kernel-restart` |
| `runs create` HTTP 500 | 看 `/var/log/lca-ops/runs.error.log` | 同上 |
| `timeline` 报 `typed-port-unset` | `rg "declared_inputs" lca/nodes/think/prep.py` 对比 yaml `inputs:` | 修 `bundles/think/think_subgraph.yaml`,不需回滚代码 |
| `timeline` 报 `node-not-found` | bundle yaml 边引用了已删节点 | 改 bundle yaml |
| E2E 报 graph 错 | `uv run python scripts/check_package_contracts.py --verbose` | 修 `ProductionRuntimeDeps` 字段不一致 |
| **任何一种失败** | 看 §6.2 各自 PR 回滚路径 | 永远优先回滚 bundle yaml,后回滚节点代码,最后回滚 composer |

---

## 18. 历史兼容 / 垃圾代码清理核对

针对 review "确保清理了历史兼容或者垃圾",本节列**已知 compat shim / legacy fallback / 反射读 / TODO 残留**,并指明各 PR 是否处理、剩余事项的 owner + delete-when。

### 18.1 本 plan 范围内要清的 compat 残留

| 位置 | 类型 | 现状 | PR | 处理 |
|---|---|---|---|---|
| `lca/plugins/think/role_profile_provider.py` | **整个 plugin 是 compat shim** | ADR-0222 后 `PromptReasoner` 不再接 role_profile,但 Cordis 仍 provide 该 capability 给老图节点 | PR-C | **删整个 plugin + capability key** |
| `lca/plugins/think/reasoner/compose.py` | 同根因 | ADR-0222 后 `PromptReasoner` 构造签名简化,但 plugin 仍提供 4 个 port(llm + selector + template_provider + section_registry) | PR-C | **删 plugin,`resolve_brain` 内联构造** |
| `lca/plugins/think/composition/composer_provider.py` + `provider_provider.py` | 把 `CordisComposer` 包成 Cordis capability(Creator mode) | 这是 **Creator 用户面**,不是 compat;但当前 implementation 走 capability 查找是多余 | PR-C | **删 2 provider,`application/api/api.py` 直接构造** |
| `lca/plugins/composer/think/brain_composer.py:77-94` | "Bare-name aliases so legacy think plugins reading `context.runtime.<name>` resolve" | 这是显式的 compat:为偷字段的节点起别名 | PR-A | **整段删**(配合节点 typed-port 化) |
| `lca/plugins/composer/composition/capability_resolution.py` | 整个模块是无用户的抽象层 | profile yaml 早 fail-loud,`ScopeCapabilityResolver.require_declared_capabilities` 等没真实失败场景 | PR-D | **删整个模块,内联到 `plan_binding.py`** |
| `lca/plugins/composer/composition/agent_assembly.py:29-49` | `AgentAssemblyPort` Protocol + `PlanBoundAgentAssembler` class 双重类 | Protocol 是为 "TeamComposer 通过 port 间接调 assembler" 而造,但 assembler 自己不需要 Port | PR-D | **删 Port Protocol,TeamComposer 直接持有 assembler 实例** |
| `lca/nodes/think/reason/plan.py:62-70` | `getattr(runtime, "reasoner")` | adapter 节点偷字段 | PR-A | **改 typed-port 输入或 `runtime.brain.reasoner`** |
| `lca/nodes/think/reason/render.py:91-100` | `_resolve_role_profile` 4 重 fallback | adapter 节点兜底 | PR-A | **整函数删,改 typed-port** |
| `lca/nodes/think/history/assemble.py:182-220` | `_system_from_role_profile` | spec §G 第 3 级 fallback,真正入口已废(PR-A 删 `reasoner.role_profile`) | PR-A | **删整函数** |
| `lca/nodes/think/history/assemble.py:148-156` | `_resolve_port` 偷字段 | runtime carrier 兜底 | PR-A | **改 typed-port 输入** |
| `lca/infrastructure/session/emit/cognitive_emit.py:683` | `decision_path="legacy"` 字面量 | legacy 字面量已无 caller(都走 typed DTO) | PR-A 后置(独立小 PR)| **删该字面量,改为从 typed DTO `TemplateSelection.decision_path` 拿** |
| `lca/cognition/brain/reasoner/reasoner.py:91-119` `build_turn_plan(state)` | 还读 `AgentState` | 与 PR-A typed-port 化冲突;P4 决议 turn planning 是图节点职责 | PR-A 后置(独立小 PR)| **`build_turn_plan` 移出 `PromptReasoner`,改图节点 `concept.template.select.pick`** |
| `lca/cognition/brain/reasoner/reasoner.py:251-261` `_empty_state_for_selector` | 伪造 state 喂 selector | 兜底死路径 | PR-A 后置 | **删** |

### 18.2 已知 compat shim / legacy 标记(本 plan 不处理,但 owner + delete-when 已存在)

| 位置 | 现状 | owner | delete-when | 备注 |
|---|---|---|---|---|
| `lca/plugins/transport/webserver/routes_1/routes_assistants.py:77,82,96` | 3 处 `COMPAT(delete-when:...)` 标记 | webserver team | 已注 delete-when | 本 plan 不动 |
| `lca/plugins/transport/webserver/handlers/runs/session/session/session.py:30` | `RunStatus` alias | webserver team | 已注 delete-when 2026-12-31 | 本 plan 不动 |
| `lca/plugins/domain/assistant/catalog/plugin.py:282,289,296` | 3 处 `NotImplementedError + COMPAT` 注释 | assistant team | 2026-12-31 | 本 plan 不动 |
| `lca/plugins/observability/writable_matrix/storage/s3.py` | `S3Sink PR-10 TODO` 占位文件 | observability team | PR-10 上线时 | 本 plan 不动,但**注意**:若后续 PR-E 触发 import,需确认不会被 import |
| `lca/plugins/observability/spine/sinks/{file_sink,tracing_file_sink,routing_file_sink}.py` | 3 个 sink 标 `COMPAT(delete-when: PR-9, ADR-0181)` | observability team | PR-9 | 本 plan 不动 |
| `lca/contracts/models/observability/journal/step.py:58` | `delete-when` 注释 | observability team | 下个 minor 版本 | 本 plan 不动 |
| `lca/plugins/transport/webserver/doctor/step_check.py:591` | `delete_when` 注释 | webserver team | scan API 收窄 | 本 plan 不动 |
| `lca/plugins/events/publishers/delegation_cache/plugin.py:11` | `delete-when: plugin-shape PR-1 上线且 bundles 引用一致` | events team | PR-1 | 本 plan 不动 |
| `lca/plugins/transport/webserver/carrier/runs/resume.py:41` | `delete_when` 注释 | webserver team | transport resume e2e 不依赖 snapshot | 本 plan 不动 |
| `lca/contracts/protocols/assistant/evolve.py:72` | `COMPAT(delete-when: 2026-12-31)` | assistant team | PR-6 | 本 plan 不动 |
| `lca/infrastructure/observability/spine/spine/enrich.py:9` | `delete_when: rg 'lca.infrastructure.observability.spine.spine.enrich' lca/ = 0` | observability team | 已无人 import 时 | 本 plan 不动 |
| `lca/infrastructure/observability/spine/manifest/manifest.py:14` | `delete_when: rg ... = 0` | observability team | 已无人 import 时 | 本 plan 不动 |

### 18.3 "垃圾代码"判定与扫描

新增 4 个守护测试,**保证 plan merge 完不残留 compat shim**:

```python
# tests/architecture/test_no_compat_residue.py

def test_no_role_profile_capability():
    """PR-C 末态:`REASONER_ROLE_PROFILE` capability key 不存在。"""
    from lca.contracts import capabilities
    assert not hasattr(capabilities, "REASONER_ROLE_PROFILE"), \
        "REASONER_ROLE_PROFILE capability should be removed in PR-C"

def test_no_phase_capability_projection_in_composer():
    """PR-A 末态:`BrainComposer.compose_agent` 返回 `phase_capabilities == {}`。"""
    from lca.plugins.composer.think.brain_composer import BrainComposer
    # 通过 mock_request + mock_scope 触发,断言返回对象的 phase_capabilities 是空 dict

def test_no_composer_provider_plugin_registered():
    """PR-D 末态:4 个 `lca-plan-*-composer` plugin 不在 boot profile。"""
    import yaml
    with open("bundles/base.yaml") as f:
        base = yaml.safe_load(f)
    plugin_ids = {p["id"] for p in base.get("plugins", [])}
    forbidden = {
        "lca-plan-brain-composer",
        "lca-plan-body-composer",
        "lca-plan-perceive-composer",
        "lca-plan-team-composer",
    }
    assert not (plugin_ids & forbidden), \
        f"composer Provider plugins should be removed in PR-D: {plugin_ids & forbidden}"

def test_no_think_reason_inner_subgraph_after_pr_e():
    """PR-E 末态:`think.reason.{plan,render,fork_tools,complete}` 全部不存在。"""
    from pathlib import Path
    forbidden = [
        "lca/nodes/think/reason/plan.py",
        "lca/nodes/think/reason/render.py",
        "lca/nodes/think/reason/fork_tools.py",
        "lca/nodes/think/reason/complete.py",
    ]
    for path in forbidden:
        assert not Path(path).exists(), f"{path} should be deleted in PR-E"

def test_no_think_history_assemble_or_decision_repair():
    """PR-E 末态:history.assemble 和 decision.repair 已删。"""
    from pathlib import Path
    forbidden = [
        "lca/nodes/think/history/assemble.py",
        "lca/nodes/think/decision_repair.py",
    ]
    for path in forbidden:
        assert not Path(path).exists(), f"{path} should be deleted in PR-E"

def test_no_system_from_role_profile_function():
    """PR-A 末态:history.assemble 的 `_system_from_role_profile` 函数已删。"""
    # AST 扫描 lca/nodes/**/*.py,不应有 _system_from_role_profile 定义
    import ast, pathlib
    found = []
    for path in pathlib.Path("lca/nodes").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_system_from_role_profile":
                found.append(str(path))
    assert not found, f"_system_from_role_profile should be removed: {found}"

def test_no_empty_state_for_selector_function():
    """PR-A 后置小 PR 末态:`PromptReasoner._empty_state_for_selector` 已删。"""
    # AST 扫描 lca/cognition/brain/reasoner/reasoner.py
    import ast, pathlib
    src = pathlib.Path("lca/cognition/brain/reasoner/reasoner.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        assert not (isinstance(node, ast.FunctionDef) and node.name == "_empty_state_for_selector"), \
            "_empty_state_for_selector should be removed"

def test_no_legacy_decision_path_literal():
    """PR-A 后置小 PR 末态:cognitive_emit.py 不再有 `decision_path="legacy"` 字面量。"""
    src = pathlib.Path("lca/infrastructure/session/emit/cognitive_emit.py").read_text()
    assert 'decision_path="legacy"' not in src, \
        'literal decision_path="legacy" should be replaced by typed DTO'
```

### 18.4 dead import 扫描(本 plan merge 前必清)

```bash
# ruff 已能检测;但另外跑:
uv run pyflakes lca/ tests/ 2>&1 | tee /tmp/pyflakes.txt
# 若有 "imported but unused" 输出,本 plan 范围内由对应 PR 删

# AST 扫描:plugin 文件被 import 但 plugin manifest 没声明
uv run python scripts/audit_plugin_shape.py --dead-imports
```

### 18.5 兼容性删后验证(无 caller 残留)

每个 PR merge 前,**确保删的 compat shim 没被任何 caller 引用**:

```bash
# 例:删 phase.think.role_profile 前
rg "phase\.think\.role_profile|reasoner\.role_profile|REASONER_ROLE_PROFILE" lca/ tests/ --type py

# 例:删 _system_from_role_profile 前
rg "_system_from_role_profile|system_from_role_profile" lca/ tests/ --type py
```

两条都应只剩 `0 hit`(或只剩测试自身的删除验证)。

### 18.6 "垃圾代码" 分类(本 plan 是否清理)

| 类别 | 例子 | 本 plan 处理 |
|---|---|---|
| **Compat shim**(同 PR 删除的) | role_profile_provider、reasoner/compose、composer_provider | **清**(PR-C/D) |
| **Legacy fallback**(3 级 fallback 末端) | `_system_from_role_profile`、`_empty_state_for_selector`、legacy 字面量 | **清**(PR-A / A 后置) |
| **反射读 state 私有字段** | `getattr(state, "_xxx_ref", None)` 在 `PrimitiveCapabilityForkDispatch` 等 | **清**(已部分完成,PR-A 覆盖剩余) |
| **死代码**(if 分支永远不进) | `if False:` debug code、`sys.exit()` 在生产路径 | **扫描 + 清**(per-PR 检查) |
| **TODO 注释** | `lca/plugins/observability/writable_matrix/storage/s3.py:1,13,27,32,42` | **不动**(有 owner + delete-when) |
| **过时的 ADR reference** | `lca/contracts/diagnostics/doctor.py:40 owner: str # ADR-XXXX` | **不动**(本 plan 范围外) |
| **双写 SSOT** | `phase_capabilities` 4 处镜像(role_profile、reasoner、skill_router、adapter) | **清**(PR-A 卸投影) |
| **Stub placeholder** | `writable_matrix/storage/s3.py` 是真 stub | **不动**(有 owner) |

---

## 19. 五原则末态核对清单

针对 review "信息传递是清晰的 职责清晰 一切插件化 图节点化了 是利于 debug 的",逐原则给末态证据。

### 19.1 信息传递清晰

| 指标 | 现状 | PR-E 末态 | 验证命令 |
|---|---|---|---|
| 节点入参全部 typed-port | 12/27 节点偷字段 | **27/27 typed-port,8 个 runtime carrier 白名单** | `tests/architecture/test_no_runtime_field_theft.py` |
| 节点出参全部 typed-port | 27/27 | **27/27** | (已满足) |
| 每个 typed DTO 一处定义 | `ReasonerTurnRequest`、`Decision` 等 | **+ `ReasonerTurnRequest`(PR-E 新)** | `rg "class.*\(.*BaseModel\|@dataclass\(frozen" lca/contracts/models/cognition/` |
| 信息流可视化 | 看 bundle yaml 边 | **bundle yaml 是 SSOT** | `rg "from: " bundles/think/` |
| 无 4 重镜像 | `role_profile` / `reasoner` / `adapter` 各 4 处 | **每份事实 1 处** | `tests/architecture/test_brain_composer_no_projection.py` |

### 19.2 职责清晰

| 节点 | 现状职责数 | PR-E 末态 | 验证 |
|---|---|---|---|
| `think.context.compact` | 2 (闸门 + 策略) | **删**(PR-B 拆 + PR-E 改名外移) | 文件不存在 |
| `think.history.assemble` | 2 (拼 messages + 拼 system) | **删** | 文件不存在 |
| `think.llm.dispatch` | 2 (adapter.stream + writer.append) | **拆 invoke + persist** | `tests/architecture/test_node_def_count.py` |
| `think.route` | 2 (router + reducer fold) | **内联到 think.prep** | 文件不存在 |
| `think.reason` subgraph | 3 (fork_tools + plan + render) | **合并到 think.prep** | bundle 改 |
| `think.prep` (新) | 4 (fork + role + template + render + system) | **1 个节点 1 个职责 = 准备一个 typed Request** | 与"准备"作为单职责一致 |

### 19.3 一切插件化

| 组件 | 现状 | PR-D 末态 |
|---|---|---|
| `BrainComposer` | L1 PROVIDER plugin + Composer 类 | **Composer 类直接由 application 装配根 new,不注册 capability** |
| `BodyComposer` | L1 PROVIDER plugin + Composer 类 | 同上 |
| `PerceiveComposer` | L1 PROVIDER plugin + Composer 类 | 同上 |
| `TeamComposer` | L1 PROVIDER plugin + Composer 类 | 同上 |
| `CordisComposer` (Creator) | PROVIDER plugin | **保留**(Creator 是 user mode) |
| `CordisControlTool` | TOOL plugin | **保留** |
| `tools`、`tools_service` 等用户可换实现 | TOOL plugin | **保留** |
| **节点** | L2 PRIMITIVE plugin | **保留**(每节点 = 一个 plugin) |

**保留"插件化"判据**:一个 plugin = 一个 profile 可换实现点的最小单位。本 plan 删的是**"为 application-layer helper 注册 capability"的过度包装**,不是删插件化本身。

### 19.4 图节点化

| 概念 | 现状 | PR-E 末态 |
|---|---|---|
| think subgraph | 11 节点 + 2 subgraph | **5 节点 + 0 内部 subgraph** |
| 每个概念(感知/上下文/工具/角色/模板/渲染/调用/解析/控制) | 多数已有概念图节点 | **保留;`fork_tools` / `route` / `history.assemble` / `decision.repair` 拆/合到对应概念图** |
| 概念图节点数 | ~25 | **~22** |
| typed-port 一致 | 27/27 | **27/27 + 1 新 DTO** |
| 边驱动拓扑 | 是 | **是**(bundle yaml 是 SSOT) |

### 19.5 利于 debug

| debug 手段 | 现状 | PR-E 末态 |
|---|---|---|
| `lca-ops timeline <run_id>` | 11 spine event(可能混 fallback noise) | **5 spine event,清晰** |
| 每个 spine event 名称 = bundle 节点名 | 是 | **是** |
| node 出错时,spine event 含节点语义 | 是 | **是** |
| `audit-state-writers` | 多写时报警 | **单写** |
| `why <capability>` | 看到注册方 | **闭集更紧,定位更快** |
| `notes-check` | 全检 | **全检**(PR 不影响) |
| `debug-run <run_id>` | 重放 | **重放** |
| **节点日志字段** | `region::semantic_name` | **保留** |
| **节点行数** | 平均 155 | **平均 100** |
| **节点 def 数** | 平均 3-5 | **平均 3** |
| **节点单测 mock 难度** | 需要 mock brain + runtime + writer | **只需 mock 1-2 个 typed port 输入** |

**debug 收益总结**:每个节点**单文件 < 130 行,单职责,typed-port 输入输出,单测只需构造 typed DTO**。一个 bug 出现在某节点 → `timeline` 定位 → `git grep` 该节点 + 它消费的 typed DTO → 修。

---

## 9. 文件总清单(3 PR 合计)

### 新增文件

```
lca/nodes/think/llm/invoke.py
lca/nodes/think/llm/persist.py
lca/nodes/think/budget/threshold_gate.py
lca/nodes/think/context/truncate.py
tests/architecture/test_no_runtime_field_theft.py       # PR-A
tests/architecture/test_brain_composer_no_projection.py  # PR-A
tests/architecture/test_node_def_count.py                # PR-B
tests/architecture/test_cordis_composer_direct_construction.py  # PR-C
tests/think/llm/test_invoke.py                           # PR-B
tests/think/llm/test_persist.py                          # PR-B
tests/think/budget/test_threshold_gate.py                 # PR-B
tests/think/context/test_truncate.py                     # PR-B
```

### 删文件

```
lca/plugins/think/role_profile_provider.py              # PR-C
lca/plugins/think/reasoner/compose.py                    # PR-C
lca/plugins/think/composition/composer_provider.py      # PR-C
lca/plugins/think/composition/provider_provider.py      # PR-C
lca/nodes/think/dispatch/llm.py                          # PR-B
lca/nodes/think/context_compact.py                       # PR-B
tests/architecture/test_reasoner_role_profile_capability.py  # PR-C
tests/architecture/test_composer_factory_capability.py   # PR-C (替换)
tests/think/dispatch/                                     # PR-B (子目录)
```

### 改文件

```
# PR-A (15 个节点 + 1 composer + 1 helper)
lca/plugins/composer/think/brain_composer.py             # 缩到 ~30 行
lca/plugins/composer/think/brain.py                      # 拆 instrument_llm / apply_lead_brain
lca/nodes/think/reason/{plan,render}.py
lca/nodes/think/gate.py
lca/nodes/think/route/{route,shortcut}.py
lca/nodes/think/decision_repair.py
lca/nodes/concept/tool_fork/dispatch.py
lca/nodes/concept/decision_enforce/chain_run.py
lca/nodes/concept/decision_shortcut_try/try_shortcut.py
lca/nodes/concept/prompt_render/{assemble,fill}.py
lca/nodes/concept/memory_write/dispatch.py
lca/nodes/concept/context_compose/collect.py
lca/nodes/remember/write/write.py
lca/nodes/reflect/score/score.py
lca/nodes/act/observe/observe.py
lca/nodes/perceive/observe/observe.py
lca/nodes/think/dispatch/llm.py                          # PR-A 改 typed-port,PR-B 拆
tests/concept/ tests/think/ tests/cognition/             # 大量 fixture 改

# PR-B (4 新节点,1 删,bundle yaml 重)
bundles/think/think_subgraph.yaml                        # 边重写
bundles/primitive/llm_call.yaml                          # dispatch → invoke/persist
bundles/base.yaml                                        # 注册新 4 plugin
lca/nodes/think/history/assemble.py                      # 删 _system_from_role_profile

# PR-C (装配根改造 + 闭集清理)
lca/application/api/api.py                               # spawn_agent 直接 CordisComposer
lca/contracts/capabilities.py                            # 删 3 个 capability key
lca/plugins/composer/think/brain.py                      # resolve_brain 内联 PromptReasoner
bundles/base.yaml                                        # 删 3 个 plugin 条目
tests/test_plugin_alignment.py                           # 去掉 3 plugin id
```

---

## 10. 完成判据(每 PR)

### PR-A

- [ ] 15 个目标节点改完,新增 2 个守护测试通过
- [ ] `BrainComposer.compose_agent()` ≤ 35 行
- [ ] `phase_capabilities` 投影仅剩 `{}` 在 composer 出口
- [ ] `uv run pytest tests/architecture/ tests/nodes/ tests/think/ -x` 全绿
- [ ] `lint-imports` 与 `check_package_contracts.py` 0 新引入失败
- [ ] E2E 0 failures

### PR-B

- [ ] 4 个新节点文件已写,`think.llm.dispatch` 与 `think.context_compact` 已删
- [ ] 节点平均行数 ≤ 130,def 数 ≤ 4
- [ ] 相关 bundle yaml 边已重
- [ ] spine timeline 能看到 `llm.invoke → llm.persist` 两段独立 event
- [ ] E2E 0 failures

### PR-C

- [ ] 3 plugin + 3 capability key 删,bundle boot provide 次数减 3
- [ ] `application/api/api.py` 直接构造 `CordisComposer`
- [ ] `audit-plugin-shape` 与 `why reasoner.role_profile` 期望输出与 §7 一致
- [ ] E2E + 一次真实 run 通过
