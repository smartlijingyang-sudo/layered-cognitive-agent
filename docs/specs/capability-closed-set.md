# Capability 闭集登记（`lab.*`）

> **归属：** ADR-0209 §1.4 / §3 I-8 · [`2026-09-09-lab-cordis-unification-design.md`](./2026-09-09-lab-cordis-unification-design.md) §C · §B.5
> **状态：** Active（agent_lab 收编 PR-E.1 落地；测试守护由 [`tests/architecture/test_lab_capability_closed_set.py`](../../tests/architecture/test_lab_capability_closed_set.py) 强制）

## §0 摘要

`lab.*` capability key 的闭集登记、命名规则与新增流程的权威 spec。任何新 `lab.*` capability 必须先经 ADR（默认引用 ADR-0209 §1.4 增列）并同 PR 同步改本 spec 闭集、提供方 `@plugin(provides=[...])`、消费方 `@plugin(requires=[...])` 或 YAML `capabilities.requires`。

## §1 闭集

闭集 Python 字面量由 §1.1 / §1.2 / §1.3 三段拼接；测试用 `ast.literal_eval` 从下方 ```text``` 块解析。

### §1.1 装配面 provider provides

每个 key 由单一 `@plugin` 提供；`lab.session` 由 `lca/plugins/lab/session/provider/plugin.py` 在 setup 阶段 `set_publish_session` 后注入。

```text
{
    "lab.session",
    "lab.plan_ref",
    "lab.body",
    "lab.tool_registry",
    "lab.safe_executor",
    "lab.transport",
}
```

### §1.2 工兵产出 `lab.<area>.<name>.out:<port>`

key 中 `out:<port>` 必须与节点 YAML `outs:` 字段对应端口一致；编译期由 agent_lab compile 阶段校验（ADR-0209 §3 I-3）。

```text
{
    "lab.act.shape.out:intent",
    "lab.act.authorize.out:authorized",
    "lab.act.execute.out:receipt",
    "lab.act.observe.out:observation",
    "lab.perceive.sense.out:sensor_items",
    "lab.perceive.resolve.out:sensors",
    "lab.perceive.policy.out:policy",
    "lab.perceive.memory.out:memory_items",
    "lab.perceive.trim.out:trimmed",
    "lab.perceive.commit.out:committed",
    "lab.think.expose.out:messages",
    "lab.think.expose.out:tools",
    "lab.think.reason.out:response",
    "lab.think.classify.out:decision",
    "lab.think.guard.out:decision",
    "lab.think.guard.out:think_signal",
    "lab.reflect.critique.out:critique",
    "lab.reflect.extract.out:lesson",
    "lab.reflect.join.out:reflection",
    "lab.remember.admit.out:fact",
    "lab.remember.commit.out:remembered",
    "lab.remember.fold_history.out:history",
    "lab.remember.snapshot.out:snapshot",
}
```

### §1.3 plugin hook 入口 `lab.hooks.*`

hook 闭集由 `lca/plugins/lab/internal/hooks.py`（`HookEvent` 枚举）持有；本节登记的 key 是 hook 注册面的 capability 表达，不写 spine EP（与 ADR-0206 §3 EventBus EP 闭集**分开**）。

```text
{
    "lab.hooks.compiletime.before_compile",
    "lab.hooks.compiletime.after_compile",
    "lab.hooks.runtime.node_start",
    "lab.hooks.runtime.node_end",
    "lab.hooks.runtime.after_node_execute",
    "lab.hooks.runtime.edge_fire",
    "lab.hooks.runtime.subgraph_enter",
    "lab.hooks.runtime.subgraph_exit",
    "lab.hooks.semantic.on_decision",
    "lab.hooks.semantic.on_observation",
    "lab.hooks.semantic.on_reflection",
    "lab.hooks.semantic.on_event",
}
```

### §1.4 总闭集

下列 set 字面量是 `tests/architecture/test_lab_capability_closed_set.py` 用 `ast.literal_eval` 解析、再 `frozenset(...)` 包一层的唯一来源；任何 `lab.*` capability 必须出现在此集合中。

```text
{
    # §1.1 装配面
    "lab.session",
    "lab.plan_ref",
    "lab.body",
    "lab.tool_registry",
    "lab.safe_executor",
    "lab.transport",
    # §1.2 工兵产出
    "lab.act.shape.out:intent",
    "lab.act.authorize.out:authorized",
    "lab.act.execute.out:receipt",
    "lab.act.observe.out:observation",
    "lab.perceive.sense.out:sensor_items",
    "lab.perceive.resolve.out:sensors",
    "lab.perceive.policy.out:policy",
    "lab.perceive.memory.out:memory_items",
    "lab.perceive.trim.out:trimmed",
    "lab.perceive.commit.out:committed",
    "lab.think.expose.out:messages",
    "lab.think.expose.out:tools",
    "lab.think.reason.out:response",
    "lab.think.classify.out:decision",
    "lab.think.guard.out:decision",
    "lab.think.guard.out:think_signal",
    "lab.reflect.critique.out:critique",
    "lab.reflect.extract.out:lesson",
    "lab.reflect.join.out:reflection",
    "lab.remember.admit.out:fact",
    "lab.remember.commit.out:remembered",
    "lab.remember.fold_history.out:history",
    "lab.remember.snapshot.out:snapshot",
    # §1.3 hook 入口
    "lab.hooks.compiletime.before_compile",
    "lab.hooks.compiletime.after_compile",
    "lab.hooks.runtime.node_start",
    "lab.hooks.runtime.node_end",
    "lab.hooks.runtime.after_node_execute",
    "lab.hooks.runtime.edge_fire",
    "lab.hooks.runtime.subgraph_enter",
    "lab.hooks.runtime.subgraph_exit",
    "lab.hooks.semantic.on_decision",
    "lab.hooks.semantic.on_observation",
    "lab.hooks.semantic.on_reflection",
    "lab.hooks.semantic.on_event",
}
```

## §2 命名规则

| 模式 | 适用 | 校验 |
|---|---|---|
| `lab.<area>.<name>` | 装配面 provider / hook 注册面 | `<area>` 取自 `lca/plugins/lab/<area>/` 实际目录；`<name>` 与 plugin id 一致 |
| `lab.<area>.<name>.out:<port>` | 工兵产出 capability key | `<port>` 必须与节点 YAML `outs:` 字段对端口字符串一致；编译期校验 |
| `lab.hooks.<phase>.<event>` | hook 注册面 | `<phase>` ∈ `compiletime` / `runtime` / `semantic`；`<event>` ∈ `HookEvent` 枚举 |

**拒绝模式**（散落命名 = 红灯）：

- `lab.<PascalCase>` —— `<area>` 与 `<name>` 须 `snake_case`；
- `lab.*-mix` / `lab.<verb>` —— capability 是名词键，非动词；行为由 plugin 自身实现；
- `lab.<area>.<name>` 中 `<area>` 不存在于 `lca/plugins/lab/<area>/` —— 必须先建目录并注册 `@plugin`；
- `out:<port>` 拼写漂移（同一节点 YAML 与 capability key 不一致）—— 编译期 `UnknownFactoryError`。

## §3 新增流程

新增 `lab.*` capability 必须**同 PR** 同步以下四项；缺一项 = 测试红灯或 lint 失败。

1. **先 ADR**：在 `docs/adr/` 新增或修改 ADR（默认引用 ADR-0209 §1.4 增列），写明新 key 语义、提供方、消费方与 effects；新 ADR 不得与 ADR-0209 §3 不变量 I-1 ~ I-9 冲突。
2. **改本 spec §1 闭集**：在 §1.1 / §1.2 / §1.3 与 §1.4 总闭集同步增列；测试用 `ast.literal_eval` 解析 §1.4 块，缺失即 fail。
3. **提供方 `@plugin(provides=[...])`**：在 `lca/plugins/lab/<area>/<name>/plugin.py` 装饰器参数 `provides` 中列出新 key；plugin id 与 `provides` 第一项保持 `lab.<area>.<name>` 命名一致。
4. **消费方声明**：消费方 `@plugin(requires=[...])` 或 YAML `capabilities.requires` 同步列出新 key；Profile/Bundle 解析期 `CapabilityGrantExceededError` 守护三维单调（AGENTS.md C5）。

强类型 `Capability` 闭集（如需在 `lca/contracts/capabilities.py` 中以 `Capability[object]("lab.*", ...)` 注册）属 PR-E.2 范围；本 PR-E.1 不引入该层登记，仅以本 spec 字符串闭集 + 测试守护。

## §4 测试

[`tests/architecture/test_lab_capability_closed_set.py`](../../tests/architecture/test_lab_capability_closed_set.py) 强制四项断言：

1. `test_lab_capability_keys_are_closed` — 解析 §1.4 `frozenset` 字面量，与 ADR-0209 §1.4 + design spec §C 列出的 `lab.*` 闭集硬编码期望一致。
2. `test_no_undeclared_lab_capability_in_provides` — `lca/plugins/lab/**/*.py` 的 `provides=[...]` 中所有 `lab.*` key 必须在闭集内。
3. `test_no_undeclared_lab_capability_in_requires` — `lca/plugins/lab/**/*.py` 的 `requires=[...]` 同上。
4. `test_no_undeclared_lab_capability_in_yaml` — `bundles/*.yaml` / `profiles/*.yaml` 中所有 `lab.*` capability 声明同上。

测试自跑命令：

```bash
pytest tests/architecture/test_lab_capability_closed_set.py -v
```

## §5 相关

- [ADR-0209 §1.4 Capability 词根](../adr/0209-agent-lab-cordis-unification.md#14-capability-词根lab-闭集) · [ADR-0209 §3 I-8](../adr/0209-agent-lab-cordis-unification.md#3-不变量)
- [`2026-09-09-lab-cordis-unification-design.md` §C](./2026-09-09-lab-cordis-unification-design.md#c-capability-闭集首批)
- [ADR-0110 命名宪法](../adr/0110-plugin-contract-unification-and-naming-convergence.md)
- [`naming-conventions.md`](./naming-conventions.md)
