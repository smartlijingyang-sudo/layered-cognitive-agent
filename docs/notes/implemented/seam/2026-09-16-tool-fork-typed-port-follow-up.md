# Agent Note: `tool.fork.dispatch` typed-port 投影 follow-up(ADR-0241 等待审)

Status: implemented

## Problem

`./scripts/lca-ops runs create --user-text "..." --profile web-standard` 在 `lca/nodes/concept/tool_fork/dispatch.py:166` 抛:

```
RuntimeError: tool.fork.dispatch: 'tools' typed port missing from input ports
```

节点 `declared_inputs=("bindings", "tools")`(PR-A 改的),但 outer plan(`bundles/outer/phase_main.yaml`)与 subgraph plans(`bundles/think/think_subgraph.yaml` → `bundles/think_reason.yaml` → `bundles/concept/tool_fork.yaml`)整条链路上**没有 plan-level `inputs:` 显式声明 `tools`,也没有 outer node 把 `tools` 当 declared_input**。kernel 在 outer plan 入口**不 seed `ToolsService` 到 port_registry**,framework 的 `translate_inputs` 只在 outer/inner 长度相等时按位置 1:1 映射,长度不等时直接 `return {}`——所以 `tool.fork.dispatch` 永远收不到 `tools` typed port。

回归引入者:`0c7f33a48 refactor(nodes/composer): typed-port inputs, drop phase_capabilities projection`(slim-composer PR-A),把 `declared_inputs=("bindings",)` 扩成 `("bindings", "tools")` 并改 `getattr(context.runtime, "tools")` 为 `input.port_values.get("tools")`,但 slim-composer plan §2.7 误判 "Bundle yaml | 不改"——这是 plan-side 与 framework-side 的协调缺失,属于 ADR-0220 §3.3 / ADR-0217 §3.3.3 typed-port 投影机制未闭合。

第一现场在 run `run_2b2f4548f3e5`(trace `trace_e145f0bb6f8c`,2026-09-16 09:38:22 UTC+8)。

## Decision

ADR-0241 已通过 + 实现落地。`lca/framework/graph/strategies/subgraph_run.py::translate_inputs` 改为 name-based 投影(ADR §Decision 1);`lca/framework/graph/adapter.py::PlanInterpreterAdapter.run` 新增 `port_registry_seed` 参数(ADR §Decision 2),`_resolve_default_port_registry_seed` 默认从 `node_executor_runtime_scope.get("tools")` + `RuntimePlane.current_bindings_view()` 拉取;`DefaultSubgraphRun.run` 分三层 seed inner plan 的 `PortRegistry`(ADR §Decision 4),kernel 通过 `context.node_config["_port_registry"]` 传递完整 outer 端口快照;`bundles/concept/tool_fork.yaml::tool.fork.dispatch.inputs` 改为 `[bindings, tools]` 防御性对齐(ADR §Decision 5)。`tests/architecture/test_typed_port_projection.py`(7 case)与 `tests/runtime/test_kernel_seeds_typed_ports.py`(4 case)新增并通过。

实际改动:

1. `lca/framework/graph/strategies/subgraph_run.py::translate_inputs` 改为 name-based 投影(ADR §Decision 1)。
2. `lca/framework/graph/adapter.py::PlanInterpreterAdapter.run` + `resume()` 新增 `port_registry_seed` 参数(ADR §Decision 2);`_resolve_default_port_registry_seed` + `_port_registry_seed_for` 辅助函数。
3. `lca/framework/graph/interpreter.py` 在每个 visit 把 `ports` 写进 `context.node_config["_port_registry"]`(ADR §Decision 4 依赖)。
4. `bundles/concept/tool_fork.yaml::tool.fork.dispatch.inputs` 改为 `[bindings, tools]` 防御性对齐(ADR §Decision 5)。
5. 新增守卫 `tests/architecture/test_typed_port_projection.py`(7 case)与 `tests/runtime/test_kernel_seeds_typed_ports.py`(4 case)(ADR §Acceptance criteria)。
6. `tests/unit/framework/graph/test_framework_graph_deepen.py::TestSubgraphRunDeepen::test_translate_inputs_positional` 改写为 `test_translate_inputs_name_based` + `test_translate_inputs_drops_outer_port_not_named_in_inner`(lock 新契约,旧 positional 期望不符合 name-based 语义)。

## Alternatives considered

### A. Plan yaml 逐节点声明 `tools`(本会话已试,否决)

```yaml
phase.main.outer::think.main.declared_inputs: [in_assembled_manifest, tools]
think.shortcut.inputs: [in_assembled_manifest, tools]
think.reason.inputs: [in_assembled_manifest, tools]
think.reason.fork_tools.inputs: [tools]
tool.fork.dispatch.inputs: [bindings, tools]
```

**否决**:
- `think.route.decide` / `think.budget.gate` / `think.context.truncate` / `think.route` 这些**中间节点本来不消费 `tools`**,为了让 positional `translate_inputs` 把 `tools` 透传到下游必须显式声明——plan YAML 被 typed port 传递逻辑反向绑架,**职责不清,不正规**(用户原话:"这个方法不对,tools 传来传去不合理")。
- 即使逐节点声明,`think.reason.fork_tools.inputs=[tools]` 与 `tool.fork.dispatch.inputs=[bindings,tools]` 长度不等,`translate_inputs` 仍走 `return {}`,fix 不彻底。
- 触及 plan bundle 闭集 + interpreter 闭集,按 AGENTS.md §1 必须先 ADR——不能直接改。

### B. 删除 concept fork dispatch,统一到 primitive fork dispatch

把 `lca/nodes/concept/tool_fork/dispatch.py` 删掉,plan yaml 指向 `lca/plugins/primitive/capability_fork/dispatch.py`(`declared_inputs=("bindings",)`,`requires=("tools",)` 通过 Cordis 取)。

**否决**:绕开 PR-A typed-port redesign,违反 ADR-0217 §3.3.3 闭集;primitive fork 用 Cordis `requires`,concept fork 用 typed port,两套机制并存导致未来发散。

### C. 给 `tool.fork.dispatch` 加 `@plugin(requires=("tools",))` 通过 Cordis 取

**否决**:节点偷 Cordis 字段会被 `tests/architecture/test_no_runtime_field_theft.py` 抓。

### D(本提案):framework 改动 + ADR-0241 评审

走 ADR-0241 §Decision 1/2/4,在 kernel 入口 seed tools/bindings + name-based translate_inputs。**触及 framework 闭集,需要 ADR**——本 note 等待 ADR 审。

## Acceptance criteria

- ADR-0241 评审 **Accepted**(状态已改)。
- ADR-0241 §Acceptance criteria 测试项全绿(`tests/architecture/test_typed_port_projection.py` 7 case + `tests/runtime/test_kernel_seeds_typed_ports.py` 4 case + 既有 4 个回归测试)。
- e2e `lca-ops runs create --user-text "echo hello-from-tool" --profile web-standard --wait --json` **仍失败**(`tool.fork.dispatch: 'tools' typed port missing`)——R-1 命中,见 §Consequences 与 ADR-0241 §Consequences R-1 命中 + 缓解。Timeline 上 `tool.fork.dispatch` 仍是 `node.end FAIL`,**未**走到 `think.reason.plan` / `think.reason.render`。e2e unblock 留独立 follow-up ADR。
- 本 note 已从 `proposed/seam/` 迁到 `implemented/seam/`,§Consequences 已回填实际改动。

## Risks

- **R-1**: ADR §Decision 1 改动可能影响既有依赖 positional 行为的 subgraph(比如 `bundles/outer/phase_main.yaml` 8 条 outer 边)。缓解:实现 PR 跑 `tests/architecture/` + `tests/integration/test_run_with_tool_use.py` 全量。
- **R-2**: ADR §Decision 2 强制 kernel 从 `require_capability(ctx, "tools")` 取 ToolsService——未来 profile 不提供 `tools` capability 时 boot 阶段 fail-loud(`MissingCapabilityError`)。`test_runtime_phase_capabilities.py` 已覆盖 fail-loud。
- **R-3**: `lca/plugins/primitive/capability_fork/dispatch.py` 与本 ADR 修后的 `tool.fork.dispatch` 职责重复(Cordis vs typed port 两套取 tools 机制)。本 ADR 不删,留独立 follow-up ADR(命名空间合并议题)。

## Verification

```sh
# ADR 通过后,实现 PR 的验证命令
uv run pytest tests/architecture/test_typed_port_projection.py tests/runtime/test_kernel_seeds_typed_ports.py --no-cov
uv run pytest tests/concept/test_tool_fork_dispatch.py tests/architecture/test_no_runtime_field_theft.py tests/runtime/test_runtime_phase_capabilities.py tests/integration/test_run_with_tool_use.py --no-cov
./scripts/lca-ops kernel-restart --json
./scripts/lca-ops runs create --user-text "echo hello-from-tool" --wait --json
./scripts/lca-ops timeline <run_id> | grep -E 'tool.fork.dispatch|think.reason|history.assemble'
uv run ruff check
uv run mypy lca/framework/graph/strategies/subgraph_run.py lca/framework/graph/adapter.py lca/runtime/loop/runtime_loop.py
```

## Consequences

ADR-0241 R-1 follow-up 已实现。

**根因重述**:kernel 的 typed-port 投影机制在 ADR-0241 已落地,但**填值动作只发生在测试与旧 `PlanInterpreterAdapter.run` 路径上**。生产 v2 driver(`lca/loop/driver.py::DeclarativeExecution.execute`)绕过 adapter,直接调 `PlanInterpreter.run(plan_obj, outer_state=state)`,不传 `port_registry_seed`。`tools` 由 `lca-tools-service` plugin 经 `ctx.provide("tools", ...)` 提供到 Cordis ctx,不经过 phase_capabilities;`current_bindings_view()` 在生产未填充。

**改动**(5 处):

1. `lca/infrastructure/runtime_plane/capability_bindings.py` — 新增 `set_current_tools_service(token)` / `reset_current_tools_service(token)` / `current_tools_service()`,对称现有 bindings ContextVar 协议(re-binding 不 reset 会跨 turn 泄漏,fail-loud)。
2. `lca/framework/graph/interpreter.py` — `PlanInterpreter.run` 新增 `port_registry_seed` 参数(对称 `PlanInterpreterAdapter.run` 同一签名)。`port_registry_seed=None` 默认从 `RuntimePlane.current_tools_service()` + `RuntimePlane.current_bindings_view()` 拉取,作为 canonical production seam。
3. `lca/plugins/transport/webserver/carrier/runs/execute/execution_environment.py::RunExecutionEnvironment.prepare` — 在已有的 `set_capability_bindings(...)` 之后追加 `set_current_tools_service(require_capability(self._ctx, "tools"))`,finally 块配套 `reset_current_tools_service(token)`。同一 task、同一次 enter/exit 边界,ContextVar 在 `prepared.driver.execute` 调用栈上保持 live。
4. 新增测试 `tests/architecture/test_typed_port_seeding_runtime_plane.py`(4 case)— 锁住 `PlanInterpreter.run` 的三种 seed 输入模式(Mapping / Callable / RuntimePlane default)+ 空 seam 边界。
5. 新增测试 `tests/runtime/test_runtime_plane_tools.py`(4 case)— 锁住 ContextVar API 契约(default None / set+current / nested reset / 双 reset fail-loud)。

**验证**:

- 新增 8 个测试 + 既有的 4 个回归测试 + 既有的 7 个 typed-port projection 测试 + 23 个 no-runtime-field-theft 测试 + 3 个 phase_capabilities 测试 + 11 个 tool_fork_dispatch 测试全绿。
- ruff check 全绿。
- mypy:`lca/framework/graph/interpreter.py` 17 errors(baseline 17,本 PR net 0);`lca/infrastructure/runtime_plane/capability_bindings.py` 0 errors;`lca/plugins/transport/webserver/carrier/runs/execute/execution_environment.py` 0 errors。
- e2e 端到端:`./scripts/lca-ops runs create --user-text "echo hello via tool"` 在 `tool.fork.dispatch` 节点 `node.end ok 1ms dispatch=terminal in=bindings,tools out=forked_tools`,**typed port `tools` 第一次到达 dispatch 节点**。后续 `think.reason.plan` / `think.reason.render` / `think.history.assemble` 全部 `node.end ok`。

**剩余**:下游 `think.llm.invoke` 节点在新 run 中失败(`NodeExecutor lookup miss: 'think.llm.invoke' not in node_executors`)——这是 *独立 bug*:think subgraph 节点的 executor 注册路径(PR-A 留下的另一条缝),不在本 note 范围。

**关键设计决定**:

- **不修改 `RuntimePhaseCapabilities.with_extra`**:phase_capabilities 是 composition-time 闭集,`with_extra` 语义是"post-composition 一次性 layer per-run 单例"(如 writer)。`tools` 是 per-turn mutable typed reference,放 phase_capabilities 会污染闭集语义。RuntimePlane 是已有的 per-turn typed carrier,职责正确。
- **不修改 `lca/loop/driver.py`**:PlanInterpreter.run 的 production-seam 默认已经读取 RuntimePlane,无需 v2 driver 显式传 seed。driver 的"传 / 不传 `port_registry_seed`"对称不变。
- **不修改 `lca/runtime/loop/runtime_loop.py`**:CognitiveRuntime 不持有 Cordis ctx,无法直接读 `tools`。carrier (RunExecutionEnvironment) 是唯一同时持有 ctx + 同 task 内 set ContextVar 的位置。
- **不新增 Protocol / 不新增 module**:RuntimePlane 已有 ContextVar + token reset 协议范式,mirror `tools_service` 是同协议扩展。
- **保留 adapter 的 `node_executor_runtime_scope` fallback**:既有 `test_kernel_seeds_typed_ports.py` 4 case + 旧 v1 兼容路径不破坏,adapter 默认 seam 与 interpreter 默认 seam 双轨存在(ranked: RuntimePlane > scope)。

## Related

- ADR [`0241-tool-fork-typed-port-projection.md`](../../adr/0241-tool-fork-typed-port-projection.md)(本 note 等它审)
- ADR-0217 §3.3.3 typed-port 模型 iron rules
- ADR-0220 §3.3 / §4.1 / §7.3 `ToolsService` + `ForkedTools` typed boundary
- ADR-0228 §Decision 4 typed seam 沿 outer 走(本 ADR 借同一手法处理 `tools` / `bindings`)
- ADR-0235 act.envelope typed-port hygiene
- 回归 commit `0c7f33a48`(slim-composer PR-A)
- Note [`../implemented/seam/2026-09-16-dead-reasoner-fallback-close-out.md`](../implemented/seam/2026-09-16-dead-reasoner-fallback-close-out.md) §Consequences 标记的 "第二个 bug,plan yaml 拓扑问题,触及 plan bundle 闭集,需独立 PR"——本 note + ADR-0241 是该 follow-up 的正式化
- 现场 run:`run_2b2f4548f3e5`(trace `trace_e145f0bb6f8c`,2026-09-16 09:38:22 UTC+8)、`run_92ac56ef97d6`、`run_0095644d4265`、`run_c2bbbd46a20e`(皆同根因,plan 改动未达 framework 闭集);`run_e05ba0d415f7`(本 follow-up 修复后 `tool.fork.dispatch` 节点 ok,验证 typed port `tools` 第一次到达 dispatch)
