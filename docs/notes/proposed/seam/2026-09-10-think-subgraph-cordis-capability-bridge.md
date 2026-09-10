# Agent Note: inner think subgraph capability seam 改为 cordis 消费方

Status: implemented

## Problem

`lca/plugins/think/llm/subgraph_runtime_provider.py:ThinkSubgraphRuntime` 是内层 think 子图节点的 capability 入口,有三个独立问题:

1. **Capability 模型绕开 cordis**。节点 plugin `think/shortcut.py`、`think/route.py`、`think/gate.py`、`think/reason/*.py` 各自 `@plugin(requires=("xxx",))` 显式声明依赖,但 `ThinkSubgraphRuntime.resolve()` 不走 `ctx.require()`,而是按 capability 字符串分支返回**本地构造的对象**:`DefaultReducer()` / `DefaultDecisionClassifier()` / `_NoGateEnforce()` / `_NoSkillRouter()` / `_NoShortcut()`。Profile 想替换任一个 capability 都没有 seam — `ThinkSubgraphRuntime` 是个黑盒。
2. **Reasoner 在 `__init__` 里本地构造**。`_build_reasoner()` 调 `self._llm_resolver.resolve()` 拿 adapter 后 `PromptReasoner(llm=adapter, ...)`。`PromptReasoner` 的构造从 cordis 看不到,adapter 来源不可审计。
3. **Inspect 扫描模块拼 executor 字典**。`collect_think_executors()` 用 `inspect.getmembers(_think_module, ...)` + `dataclasses.is_dataclass(cls)` + 字段 default 字符串匹配,反射捞 `(region, semantic_name) → executor` 字典。违反 AGENTS.md §5 "bundles yaml 必须显式列 plugin id,不准反射捞"。

## Decision

**消灭 `ThinkSubgraphRuntime` 整个文件,改用 cordis 单一来源**:

| 改前 | 改后 |
|---|---|
| `ThinkSubgraphRuntime` 类 + 4 个本地 fake default + `collect_think_executors` (inspect 反射) | **删除**。`SubgraphRunner.setup` 用 `PluginContextBackedRuntime(ctx=ctx)` 替代 — runtime 每次 `resolve(capability)` 直接调 `ctx.require(capability)`,缺失返回 None。 |
| `_build_reasoner()` 在 `__init__` 内本地构造 `PromptReasoner` | **删除**。新建 `lca/plugins/think/llm/reasoner_instance_provider.py` 作为独立 `@plugin(provides=("reasoner",), requires=("llm_resolver",))` — 通过 cordis 装配 `PromptReasoner`,跟 `lca/plugins/loop/reasoner/*` 系列插件同形。 |
| `setup` 里 `ctx.require("subgraph_runtime")` + `ctx.provide("subgraph_runtime", ThinkSubgraphRuntime(...))` | **删除 `subgraph_runtime` capability 键**。`SubgraphRunner.setup` 直接构造 `runtime = PluginContextBackedRuntime(ctx=ctx)`,无外部注册。 |
| `@plugin(provides=("subgraph_runtime", "phase_output_channel_factory"))` 在 `lca-subgraph-runtime-llm` entry | 拆开:`subgraph.runner` plugin `@plugin(provides=("subgraph_runner", "phase_output_channel_factory"))` — `phase_output_channel_factory` 是 framework 拥有的真实 seam (`InMemoryPhaseOutputChannel`),不是 LLM-specific。 |
| 节点 plugin `@plugin(requires=("supports_shortcut",|"skill_router",|"decision_gate",))` | **删除这三个 requires**。节点代码已经处理 None / `isinstance(None, ...)` 检查:`think/shortcut.py` `if cap is None: return NodeOutput(port_values={})`,`think/route.py` `if router is None: return NodeOutput(port_values={})`,`think/gate.py` `if state is not None and isinstance(gate, DecisionGate):`。Profile 想加真实 gate / router / shortcut 只需 `ctx.provide("decision_gate", MyGate())` 即可,节点 None-handling 已经是"缺失即无实现"的协议语义。 |
| `agent_gates` capability 键 | **整个删除**。`grep runtime.agent_gates` 零引用 — 没有节点读这个 key,`ThinkSubgraphRuntime.resolve("agent_gates")` 那个 fake default 是为"API 完整性"造的,纯属 dead path。 |
| `declarative.interpreter` `@plugin(requires=("subgraph_runner", "subgraph_runtime", ...))` + `_subgraph_runtime` 字段 + `bind_cordis_seams(subgraph_runtime=...)` | **删除 `subgraph_runtime`**。`_subgraph_runtime` 字段被 set 但从未被读(只 2 个 hits,都在 set 处)。`bind_cordis_seams` 删 `subgraph_runtime=` 参数。 |
| `runtime_seams_provider.py` 通过 `ctx.require("subgraph_runtime")` 软 fallback | **删除**。 |
| `bundles/base.yaml` 的 `lca-subgraph-runtime-llm` entry | **删除**。新增 `phase.think.reasoner` entry。 |

## Boundary of new wiring

- **Framework 层**: `lca/framework/subgraph/plugins/runtime.py` 定义 `PluginContextBackedRuntime(ctx=ctx)` 实现 `SubgraphRuntime` Protocol。`resolve(capability)` 用 `ctx.require(capability)`,捕获 `KeyError` / `UndeclaredInteractionError` 转 None(soft-fail,跟 `NodeRuntimeView.__getattr__` 一致)。`resolve_factory(factory, region)` 走 `f"{region}::{factory}"` 复合键,缺失抛 `FactoryResolutionError`。
- **Node plugin 层**: 4 个 think reason node (`plan` / `render` / `complete` / `route` / `shortcut` / `gate`) 不变 — 已经正确处理 None / `isinstance` soft-fail。它们从 `context.runtime.<key>` 读 capability,framework `NodeRuntimeView` 翻译成 `runtime.resolve(key)`,新 `PluginContextBackedRuntime` 翻译成 `ctx.require(key)`。
- **Bundle 层**: `bundles/base.yaml` 显式声明 `phase.think.reasoner`(新的 reasoner provider),不再有 `lca-subgraph-runtime-llm`。

## Alternatives considered

- **A. 保留 `ThinkSubgraphRuntime`,只删 fake default 改成 `ctx.require`**。保留 wrapper 类,但 `__init__` 多接 `ctx`,`resolve` 改 `self._ctx.require(capability)`。—— 选 B(整层删除)而不是 A,因为 wrapper 类没有任何业务价值:`PluginContextBackedRuntime` 已经做了同样事且更标准。一个 `resolve(key) -> obj | None` 的 Protocol 不需要专门 wrapper 类。
- **B(本提案)。整层删除 `ThinkSubgraphRuntime` + 新建独立 reasoner plugin + 节点 plugin 删 optional requires**。—— 选这条,理由见上。**关键边界**: 不造 `NoOpDecisionGate` / `NoOpSkillRouter` / `NoOpSupportsShortcut` placeholder。节点代码本身已经实现"缺失即无实现"语义,造 placeholder 是 silent fake default(违反 AGENTS.md §4 / ADR-0076)。
- **C. 在 bundle 里 wire 真实 DecisionGate / SkillRouter / SupportsShortcut 实现**(e.g. `MustConsultAllMembers`)。—— 不在本 note 范围。inner subgraph 当前设计是"软 gate,outer pipeline 才是最终 enforcement";真实 gate 链应该在 outer brain factory (`build_standard_cognitive_brain_factory`) 装配,不在 inner subgraph 重复。后续如有需要,profile 可以 `ctx.provide("decision_gate", ChainedDecisionGate(...))` 单独 wire — 不需要改 framework。

## Acceptance criteria

- `rg "ThinkSubgraphRuntime\|_NoGateEnforce\|_NoSkillRouter\|_NoShortcut|collect_think_executors|subgraph_runtime" lca/ tests/ bundles/` 在代码层零引用(允许 docstring 提及)。
- `bundles/base.yaml` 不含 `lca-subgraph-runtime-llm` entry;含 `phase.think.reasoner`。
- `PluginContextBackedRuntime(ctx=fake_ctx).resolve(key)` 直接调 `fake_ctx.require(key)` 并 coerce 异常为 None,行为可预测。
- `SubgraphRunner` 不再 `requires=("subgraph_runtime",)`,setup 不再 require 这个 key。
- `declarative.interpreter` 不再 `requires=("subgraph_runtime",)`,`_subgraph_runtime` 字段删除。
- `think/shortcut.py` / `think/route.py` / `think/gate.py` 不再 `requires=("supports_shortcut"|"skill_router"|"decision_gate",)`;节点代码本身软处理 None。

## Verification

实施时同步运行:

```sh
python -m pytest tests/think tests/integration/think tests/harness/ tests/unit/framework/subgraph/ -q --no-cov --ignore=tests/harness/graph/execute/test_interpreter_subgraph_hooks.py --ignore=tests/harness/graph/execute/test_port_naming.py
```

baseline 跟修改后:**885 passed, 19 failed**(19 failed 全部为 baseline 既有失败,与本改动无关;详见 AGENTS.md §6 基线失败协议)。
