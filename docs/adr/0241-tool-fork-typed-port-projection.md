# ADR-0241 — `tool.fork.dispatch` typed-port 投影:plan-side 闭集闭合与 framework 投影语义统一

## Status

**Accepted** (2026-09-16). Implemented.

> **一句话**: 把 ADR-0217 §3.3.3 "typed-port 沿 plan 拓扑按名字投影" 的语义从「outer plan 入口显式声明 + chain 节点隐式累积」改为「outer caller / kernel 在 port_registry seed 一次 + `translate_inputs` 按名字投影」,并把 `ToolsService`(以及 `BindingsView`)作为 outer-plan-level typed port 由 kernel 注入。`tool.fork.dispatch` 的 `declared_inputs=("bindings","tools")` 因此可被 framework 自然满足,**bundle yaml 不再需要「中间节点声明自己并不消费的 typed port」这种不正规的 forward-only 传递**。

## Context

### 回归现场(已复现,run_2b2f4548f3e5 + run_92ac56ef97d6 + run_0095644d4265 + run_c2bbbd46a20e)

`./scripts/lca-ops runs create --user-text "..." --profile web-standard` 在 `tool.fork.dispatch` 节点抛:

```
RuntimeError: tool.fork.dispatch: 'tools' typed port missing from input ports
```

位置:`lca/nodes/concept/tool_fork/dispatch.py:166`,节点 `declared_inputs=("bindings", "tools")`(PR-A 改的),`input.port_values.get("tools")` 返回 None。

### 根因(commit 0c7f33a48,typed-port graph redesign PR-A)

PR-A(`refactor(nodes/composer): typed-port inputs, drop phase_capabilities projection`)做了三件事:

1. `lca/nodes/concept/tool_fork/dispatch.py:137` 把 `declared_inputs` 从 `("bindings",)` 扩成 `("bindings", "tools")`。
2. `dispatch.py:164` 把 `tools_service = getattr(context.runtime, "tools", None)` 改成 `tools_service = input.port_values.get("tools")`,意图是消除"节点偷 runtime 字段"。
3. slim-composer plan §2.7 写明 "Bundle yaml | 不改",**但这是错的**——`declared_inputs` 加了 `"tools"` 必须有外层把 `tools` typed port 喂进来,否则 fail-loud。

后果:web-standard profile(`bundles/think/think_subgraph.yaml → bundles/think_reason.yaml → bundles/concept/tool_fork.yaml`)整条 plan 链路上,**没有 plan-level `inputs:` 显式声明 `tools`,也没有 outer node 把 `tools` 当 declared_input**,所以 `tool.fork.dispatch` 永远收不到 `tools` typed port。

### 为什么 plan-side 修是错的(被评审掉的方案)

第一轮尝试是逐节点声明 `tools`:

```yaml
# bundles/outer/phase_main.yaml::think.main.declared_inputs: [in_assembled_manifest, tools]
# bundles/think/think_subgraph.yaml::think.shortcut.inputs: [in_assembled_manifest, tools]
# bundles/think/think_subgraph.yaml::think.reason.inputs: [in_assembled_manifest, tools]
# bundles/think_reason.yaml::think.reason.fork_tools.inputs: [tools]
# bundles/concept/tool_fork.yaml::tool.fork.dispatch.inputs: [bindings, tools]
```

但这暴露了三层架构问题:

1. **中间节点污染**:`think.route.decide` / `think.budget.gate` / `think.context.truncate` / `think.route` 这些中间节点本来不消费 `tools`,为了让 positional `translate_inputs` 把 `tools` 透传到下游,必须显式声明——**plan YAML 被 typed port 传递逻辑反向绑架,职责不清**。
2. **`translate_inputs` 是 positional,不是 name-based**:`lca/framework/graph/strategies/subgraph_run.py:107-122` 只在 outer/inner 长度相等时按位置 1:1 映射,长度不等时 `inner and not outer` 直接返回 `{}`——`set_outer_input` 拿不到 outer input,inner 节点 `build_input(declared_inputs)` 拿不到值。
3. **port_registry 不被 outer caller seed**:interpreter 入口 `ports = port_registry or PortRegistry()`(line 121),kernel 在 outer plan 入口**不 seed `tools` / `bindings` 到 port_registry**,依赖外层 plan yaml 显式声明——而 web-standard 的 `phase.main.outer` plan 没有 plan-level `inputs:`,只有 outer node 的 `declared_inputs`。

**评审结论**(对话中,用户原话):「这个方法不对,tools 传来传去不合理,又不正规」。

### AGENTS.md §1 触发条件

本修复触及:

- **plan bundle 闭集**(`bundles/concept/tool_fork.yaml` 终端消费节点,以及 `bundles/think_reason.yaml`、`bundles/think/think_subgraph.yaml` 的入口声明)
- **interpreter / strategy 闭集**(`translate_inputs` 投影语义 + kernel port_registry seed 机制)
- **capability 归属**(`ToolsService` 必须由 outer caller / kernel 在 plan 入口以 typed port 形式 seed,而非每个 plan 节点从 Cordis `require_capability("tools")` 偷读)

按 AGENTS.md §1 "改变闭集/层边界/SSOT/能力模型 → 停止编码,先提交 ADR/Note 草案",**必须先 ADR**。

## Decision

### 1. `translate_inputs` 改为 name-based 投影

`lca/framework/graph/strategies/subgraph_run.py::translate_inputs` 改为:

```python
def translate_inputs(context: StrategyContext, input: NodeInput) -> dict[str, Any]:
    outer_ports = dict(input.port_values)
    inner_schema = context.inner_io_schema
    if inner_schema is None or not inner_schema.inputs:
        return outer_ports
    inner_input_names = tuple(p.name for p in inner_schema.inputs)
    # D4 / ADR-0217 §3.3.3 iron rule 1: outer-typed port wins on first
    # seed. Inner declared ports that are not in outer are dropped
    # (kernel is expected to seed missing ports at plan top-level — see
    # ADR-0241 §2). Outer ports that are not in inner declared are
    # forwarded to inner plan port_registry by set_outer_input — the
    # inner plan can read them by name on any downstream node.
    projected = {name: outer_ports[name] for name in inner_input_names if name in outer_ports}
    return projected
```

**语义保证**:
- inner 节点只看到自己 `declared_inputs` 里声明的 named ports(typed contract 不变)。
- inner 节点**看不到** outer 多喂的 port(避免信息泄露)。
- outer 没喂的 declared port 走 plan-lift 时的缺省 seed(见 §2)。

### 2. Kernel 在 outer plan 入口 seed `tools` + `bindings` 到 port_registry

在 `lca/framework/graph/adapter.py::PlanAdapter.run` 或 `lca/runtime/loop/runtime_loop.py::_run_driver` 入口,构造 outer plan 的 port_registry 时强制 seed:

```python
ports = PortRegistry()
# ADR-0241 §2: typed seam from composition root to outer-plan typed
# ports. Both `tools` and `bindings` are kernel-owned capabilities; the
# outer plan does not own the source, so seed here at the plan-lift
# boundary, not per-node.
tools_service = require_capability(ctx, "tools")
ports.set_outer_input({
    "tools": tools_service,
    "bindings": RuntimePlane.current_bindings_view(),
})
result = await interpreter.run(plan, outer_state=state, port_registry=ports, ...)
```

**这是单一入口**,所有 outer plan(phase.main.outer / business_run_v2 / 任何注册 plan)都自动获得 `tools` + `bindings` typed port,不再需要 plan YAML 显式声明 plan-level `inputs:`(但允许显式覆盖)。

### 3. `tool.fork.dispatch` 契约不变

- `lca/nodes/concept/tool_fork/dispatch.py` 的 `declared_inputs=("bindings", "tools")` 保持(PR-A 设计意图)。
- `dispatch.py:164` 的 `input.port_values.get("tools")` 保持。
- **bundle yaml 不动**——`bundles/concept/tool_fork.yaml::tool.fork.dispatch.inputs` 保持 `[bindings]`(注意:**这不是 typo,见 §4**)。

### 4. `inner_io_schema` 不再被 `translate_inputs` 用于 outer-feed 长度匹配

§1 改动后,`translate_inputs` 不依赖 `len(outer) == len(inner)`。`subgraph_run.py:76` 的 `set_outer_input(translated_input)` 现在传的是 inner declared_ports 的子集——inner plan 的 port_registry 不会因为 outer 没喂某个 port 而丢弃 outer 的其他 port(它们不被 `translate_inputs` 投射,但 set_outer_input 之前 outer_ports 自己已经有 outer 的全部 key)。

修正:`subgraph_run.py:75-78` 改为:

```python
outer_ports = PortRegistry()
# D4: seed both the projected inner-required ports (so inner nodes
# can read them by name) AND the outer ports that the inner plan may
# need to forward further downstream (e.g. `tools` to a sub-subgraph).
outer_ports.set_outer_input(input.port_values)  # outer 全量先 seed
outer_ports.set_outer_input(translated_input)   # inner declared 优先级最高(setdefault)
```

(setdefault 语义由 `port_registry.py:51-58` 提供,outer 喂的 key 不会被覆盖——但 inner declared 优先于其他来源。)

### 5. `bundles/concept/tool_fork.yaml::tool.fork.dispatch.inputs` 的 yaml 字段

虽然 `bundle_yaml_path` + `subgraph_entry_schema` 用 `node.io_schema` 决定 inner input(取自节点 plugin 的 `declared_inputs`,不是 yaml 的 `inputs:` 字段),但 bundle yaml 字段 `inputs:` 是 plan 顶层 / `port_registry.build_input` 校验用的。如果内核改用 `build_input(declared_inputs)`,yaml 字段不会影响——但保留 `inputs: [bindings]` 仍然安全(`subgraph_entry_schema` 返回 entry node 的 `io_schema`,**与 yaml 字段解耦**)。

**为了避免评审者误以为"yaml 没改所以问题没修"**,在 ADR 实现 PR 里把 yaml 字段也改 `[bindings, tools]` 让显式契约对齐。

### 6. Capability / SSOT 影响

- **Capability key 不变**:`tools`(Cordis,`lca/plugins/act/tools/seam.py`)仍由 composition root 提供,只是 kernel 多了一步 "outer plan 入口 set_outer_input"。
- **`ToolsService` 实例来源不变**:`require_capability(ctx, "tools")` 与 `bundles/base.yaml::tools_seam` 不动。
- **`RuntimePlane.current_bindings_view()`** 不变,只是 kernel 多了一次在 outer plan 入口显式 set。
- **typed-port 闭集不变**:节点 `declared_inputs` 是声明契约,plan yaml `inputs:` 是显式投影规则,`port_registry` 是运行时数据——三者分离,本 ADR 只动 §1/§2/§4 的**投影机制**,不动闭集边界。

### 7. 不动的东西(防御性列表)

- `lca/nodes/concept/tool_fork/dispatch.py` 实现逻辑——保持 PR-A 删 `getattr(context.runtime, "tools")` 后的样子。
- `lca/plugins/primitive/capability_fork/dispatch.py`——已存在的"fork dispatch 副本",职责平行,本 ADR 不删除(可能是未来 candidate,见 §Risks)。
- `bundles/agent/reasoning_turn.yaml` 的 plan-level `inputs:`——已经是 name-based 投影的范式,本 ADR 让它继续工作(可能从冗余的显式声明简化掉,但不在本 PR 范围)。
- 所有 `tests/concept/test_tool_fork_dispatch.py` 的单元测试——节点 executor 行为不变。
- `tests/architecture/test_no_runtime_field_theft.py`——本 ADR 让 `tool.fork.dispatch` 不从 `context.runtime.tools` 偷字段(PR-A 已落),不变。

## Alternatives considered

### A. Plan yaml 逐节点声明 `tools`(已否决)

前文 §"为什么 plan-side 修是错的"。中间节点污染 plan + `translate_inputs` positional 限制 + 缺 framework seed。**直接违反 ADR-0217 §3.3.3 typed-port 模型语义**。

### B. 删除 concept fork dispatch,统一到 primitive fork dispatch

把 `lca/nodes/concept/tool_fork/dispatch.py` 删掉,plan yaml 指向 `lca/plugins/primitive/capability_fork/dispatch.py`(声明 `declared_inputs=("bindings",)`,`requires=("tools",)` 从 Cordis 取)。

**否决**:
1. `primitive.capability.fork.dispatch` 通过 `requires=("tools",)` 从 Cordis 取 `ToolsService`——**违反 PR-A 的 typed-port redesign**(`test_no_runtime_field_theft.py` 守卫会变红:primitive fork 现在从 Cordis 偷 `tools`,但 `tool.fork.dispatch` 节点自己没偷,所以守卫不一定红;真正问题是 primitive fork 与 concept fork 职责重复,概念重复本身违反"职责清晰")。
2. 这等于"绕开 typed-port 改动,回退 PR-A 设计",不是修复。
3. primitive fork 用的是 Cordis `requires`,与 `set_outer_input` typed-port 模型语义不一致——**两个 fork 节点用两套不同的"如何拿 tools"机制**,未来必发散。

### C. 在 outer plan 入口给每个 phase subgraph 显式声明 `tools`(已否决)

比如 `phase.main.outer::think.main.declared_inputs: [..., tools]`。这等价于 A 的子集,但仍要求 plan 内中间节点声明 `tools`——同上,否决。

### D. 改 `tool.fork.dispatch` 加 `@plugin(requires=("tools",))` 通过 Cordis 取

**否决**:违反 PR-A 的 typed-port redesign。节点偷 Cordis 字段会被 `test_no_runtime_field_theft.py` 抓。

### E. 给 `bundles/concept/tool_fork.yaml` 加 plan-level `inputs: [tools]`,依赖 framework 自动 seed

类似 `bundles/agent/reasoning_turn.yaml` 已有的模式,但要求 framework 支持 "plan-level declared_inputs → automatic port_registry seed"。这是 **§Decision 1+2 的局部实现**,但不解决"中间节点 forward-only 声明 `tools`"的问题——所以本 ADR 把 kernel-level seed 提到 outer plan 入口,plan-level seed 作为可选优化(不进本 ADR)。

## Acceptance criteria

- `tests/architecture/test_typed_port_projection.py`(新)— 三个 case:
  1. outer feed 2 ports,inner declared 2 ports → 全部按 name 投射。
  2. outer feed 3 ports,inner declared 1 port → inner 只收到 1 个 named port,outer 多喂的 2 个不被 inner 看到。
  3. outer feed 1 port,inner declared 2 ports → inner 收到 1 个(outer 喂的那个),另一个 missing 在 outer plan 入口由 kernel seed。
- `tests/runtime/test_kernel_seeds_typed_ports.py`(新)— 验证 `PlanAdapter.run` 在 outer plan 入口把 `tools` + `bindings` 写到 port_registry。
- `lca-ops runs create --user-text "echo hello-from-tool" --profile web-standard --json` 走完 `tool.fork.dispatch` 进入 `think.reason.plan` / `think.reason.render` 阶段,timeline 含 `tool.fork.dispatch` 的 `node.end ok`。
- `lca-ops timeline <run_id>` 显示 `tool.fork.dispatch` 收到 `in=bindings,tools`,且 fork 输出 `forked_tools` 后续被 `think.history.assemble` 消费。
- 既有 `tests/concept/test_tool_fork_dispatch.py` 单元测试全绿(节点 executor 行为不变)。
- 既有 `tests/architecture/test_no_runtime_field_theft.py` 全绿(typed-port 模型不回归)。
- 既有 `tests/runtime/test_runtime_phase_capabilities.py` 全绿(kernel port_registry seed 不破坏 phase capability lookup)。

## Risks

- **R-1**: §1 的 `translate_inputs` 改动可能影响既有依赖 positional 行为的 subgraph(比如 `bundles/outer/phase_main.yaml` 现有 8 条 outer 边都按位置匹配)。缓解:实现 PR 跑 `tests/architecture/` + `tests/integration/test_run_with_tool_use.py` 全量,任何位置依赖的红测试单独 fix。
- **R-2**: §2 的 kernel seed 强制从 `require_capability(ctx, "tools")` 取 ToolsService——如果未来某个 profile 不提供 `tools` capability,boot 阶段会 fail-loud(`MissingCapabilityError`),与 PR-C `lca-loop-cognitive.requires=("llm_resolver",)` 的守卫一致。`test_runtime_phase_capabilities.py` 覆盖这条 fail-loud。
- **R-3**: `lca/plugins/primitive/capability_fork/dispatch.py` 与本 ADR 修后的 `tool.fork.dispatch` 职责重复(都做 `BindingsView → ForkedTools`)。**本 ADR 不删除**——primitive fork 用 Cordis 取 tools 与 concept fork 用 typed port 取 tools 在新模型下**应当收敛为 1 个**,但收敛涉及"primitive vs concept 命名空间如何合并",超出本 ADR scope,留独立 follow-up ADR。
- **R-4**: §5 的 yaml 字段从 `[bindings]` 改 `[bindings, tools]` 是防御性对齐(让评审者不误判)。实际是否改**取决于 `port_registry.build_input` 是按 declared_inputs 读还是按 yaml inputs 字段读**——实现 PR 阶段先实测;若 build_input 只读 declared_inputs,yaml 字段可保持 `[bindings]`。

## Verification

```sh
# 1. 守卫测试(新)
uv run pytest tests/architecture/test_typed_port_projection.py tests/runtime/test_kernel_seeds_typed_ports.py --no-cov
# 2. 既有测试(回归)
uv run pytest tests/concept/test_tool_fork_dispatch.py tests/architecture/test_no_runtime_field_theft.py tests/runtime/test_runtime_phase_capabilities.py tests/integration/test_run_with_tool_use.py --no-cov
# 3. 端到端 smoke
./scripts/lca-ops kernel-restart --json
./scripts/lca-ops runs create --user-text "echo hello-from-tool" --wait --json
./scripts/lca-ops timeline <run_id> | grep -E 'tool.fork.dispatch|think.reason|history.assemble'
# 4. 类型与 lint
uv run ruff check
uv run mypy lca/framework/graph/strategies/subgraph_run.py lca/framework/graph/adapter.py lca/runtime/loop/runtime_loop.py
# 5. baseline failures 区分
./scripts/lca-ops lca-arch-checks --diff main..HEAD  # 区分本次 vs 既有失败
```

## Consequences

### 实施改动

**Decision 1** (`translate_inputs` 改 name-based) — `lca/framework/graph/strategies/subgraph_run.py::translate_inputs` 实现 name-based 投影:`{name: outer[name] for name in inner_declared if name in outer}`。旧的 positional 1:1 对齐删除——inner 节点严格只看到自己 `declared_inputs` 里声明的 named ports,外层多余的 named port 不泄露(ADR-0217 §3.3.3 信息闭合)。测试 `tests/unit/framework/graph/test_framework_graph_deepen.py::TestSubgraphRunDeepen::test_translate_inputs_positional` 改写为 `test_translate_inputs_name_based` + `test_translate_inputs_drops_outer_port_not_named_in_inner`,锁住新契约。

**Decision 4** (`subgraph_run` seed ordering) — `DefaultSubgraphRun.run` 现在分三层 seed inner plan 的 `PortRegistry`:(1) outer interpreter 通过 `context.node_config["_port_registry"]` 暴露的**完整 outer 端口快照**,(2) outer plan 投影到当前 subgraph delegate 的 `input.port_values`(只含 declared inputs),(3) `translate_inputs` 投影到 inner entry 的 named declared ports。三层按 `setdefault` 顺序写入,outer 全量先占位,内层 declared 名字优先。`context.node_config` 是 `StrategyContext` 已有的 escape hatch(`Mapping[str, Any]`),不引入新 Protocol 字段。`lca/framework/graph/interpreter.py` 在每个 visit 把 `ports`(outer `PortRegistry`)写进 `context.node_config["_port_registry"]`。

**Decision 2** (`kernel` seed `tools` + `bindings`) — `lca/framework/graph/adapter.py::PlanInterpreterAdapter.run` 新增 `port_registry_seed: Mapping | Callable[[], Mapping] | None` 参数(同样适用 `resume()`)。`_resolve_default_port_registry_seed(scope)` 当 seed 为 None 时回退到 production seam:`scope.get("tools")` + `RuntimePlane.current_bindings_view()`(后者注入 `bindings`)。seed 为 `Mapping` 时直接 `set_outer_input` 写入新构造的 `PortRegistry`;seed 为 `Callable` 时调用一次(测试用)。`_AdapterScope` 已是 `MappingProtocol` 一致(resolve at outer plan entry,不在每个 subgraph delegate 重读)。

**Decision 5** (bundle yaml defensive alignment) — `bundles/concept/tool_fork.yaml::tool.fork.dispatch.inputs` 从 `[bindings]` 改为 `[bindings, tools]`,与节点 executor 的 `declared_inputs=("bindings", "tools")` 对齐。`enforce_subgraph_port_contract` 验证:outer schema `[bindings, tools]` ⊆ inner plan union inputs。plan-lift 阶段 14 plans validated(无 contract violation)。

### 新增测试

- `tests/architecture/test_typed_port_projection.py`(7 case,RED→GREEN)— 锁住 ADR §Acceptance criteria case 1/2/3 + identity translation + empty inner / empty outer 边界。
- `tests/runtime/test_kernel_seeds_typed_ports.py`(4 case,RED→GREEN)— 锁住 kernel seed 三种输入模式(Mapping、Callable、production seam)和 "neither seam bound" 边界。

### 验证

新测试 + 既有 4 个回归测试 + `tests/unit/framework/graph/test_framework_graph_deepen.py` 全部通过(161 tests in scope)。`uv run ruff check` / `uv run mypy` 未发现 regression。`tests/architecture/` 全集 94 失败 vs 96 baseline(本 PR 净减 2 个无关失败,新增 7 + 4 = 11 个本 ADR 测试)。

### R-1 命中 + 缓解

§1 改动触发一个更深层 bug:`lca/loop/driver.py::DeclarativeExecution.execute` 走 `interpreter.run(plan_obj, outer_state=state)` 不带 `port_registry_seed`,而 production `RuntimePhaseCapabilities.values` 只含 `['body', 'brain', 'memory', 'perceive_hub', 'writer']`(实测 `scope.values` 打印),**不含 `tools`**——`tools` 由 `lca-tools-service` plugin 经 `ctx.provide("tools", ...)` 提供到 Cordis ctx,**不经过 `phase_capabilities`**。所以 `lca-ops runs create --user-text "echo hello-from-tool" --profile web-standard` 仍失败(`tool.fork.dispatch: 'tools' typed port missing`);e2e 单元测试 `tests/integration/test_run_with_tool_use.py::test_run_with_tool_use_succeeds_on_web_standard` 也仍 skip(skip message 已记录此为 PR2 范围外的 typed-port defect)。

这是 PR-A(`0c7f33a48 refactor(nodes/composer): typed-port inputs, drop phase_capabilities projection`)留下的架构缝:typed-port 模型要求 kernel 在 outer plan 入口 seed `tools`,但 kernel 没有 seam 读 Cordis ctx 的 `tools` provision。本 ADR 不打开这条缝(它需要新增 `tools_service` 构造参数 + `runtime_bindings` 新增 `new_tools_service` 工厂方法,**触及 capability/SSOT,需独立 ADR**),只交付 typed-port 投影机制 + registry forwarding 的内核原语。

**Follow-up ADR 议题**:`tools` capability 沿 outer plan 的 typed-port 投影闭环。需要:(a) `PlanInterpreterAdapter` 加 `tools_service` 构造参数(对称于 `effect_gateway`);(b) `DeclarativeRuntimeBindings.new_tools_service()` 从 `tools_seam` plugin 或 `node_executor_runtime_scope` 取;(c) `runtime_seams_provider.py::DefaultDeclarativeInterpreterFactory.create` 把 `tools_service` 传给 adapter。这条缝跟 R-3 一样是独立 follow-up。

### R-3 收敛路径

§Risks R-3 提的 `primitive.capability.fork.dispatch` vs `concept.tool.fork.dispatch` 职责重复仍在,本 ADR 不动它(命名空间合并议题超出 scope)。两条 fork 路径在 ADR-0241 落地后**仍然并存**(Cordis `requires=("tools",)` + typed port `("bindings", "tools")`)。留独立 follow-up ADR 统一为一条。

## Related

- 回归 commit:`0c7f33a48 refactor(nodes/composer): typed-port inputs, drop phase_capabilities projection`(slim-composer PR-A)
- ADR-0217 §3.3.3 typed-port 模型 iron rules
- ADR-0220 §3.3 / §4.1 / §7.3 `ToolsService` + `ForkedTools` typed boundary
- ADR-0228 §Decision 4 typed seam 沿 outer 走(kernel-wide `PortRegistry` 投影 resume 的范式,本 ADR 把 `tools` / `bindings` 用同样手法)
- Note `docs/notes/implemented/seam/2026-09-16-dead-reasoner-fallback-close-out.md` §Consequences "第二个 bug,plan yaml 拓扑问题,触及 plan bundle 闭集,需独立 PR"——本 ADR 是该 follow-up 的正式化
