# ADR-0209 — agent_lab 全量收编进 LCA plugin 体系：单一一套装饰器、Capability 与装配根

> **状态：** **Proposed — 2026-09-09**
>
> **一句话**：把 `agent_lab/` 的全部节点、hook、Body 装配、Transport、ToolRegistry、Session binding 一次性收编进 LCA 单一 plugin 体系；消灭 `agent_lab/plugins/base.py` 的第二套 `GraphPlugin` 装饰器；消灭 `act.execute.body.build_body / run_body_act` 等节点文件内的「组合根」；让 `act.yaml` 与 Profile/Bundle 上看见所有依赖；与 ADR-0206 的图内核吸收契约（[Note 2026-09-08-agent-lab-absorb-end-state](../notes/proposed/seam/2026-09-08-agent-lab-absorb-end-state.md) §delete-when）形成同一决策的另一半。
>
> **Review：** 2026-09-09 通过（设计评审通过，进入实施切片；状态保持 Proposed 待 PR-A ~ PR-E 全部合并后升 Accepted）。

**编号**：0209（0206 / 0207 / 0208 已占用；空号下推）。

**关系**：

- **Builds on**：ADR-0004 Protocol-First、ADR-0015 contracts 无行为、ADR-0061 Manifest Resolve/Boot、ADR-0062 Plugin 运行时收口、ADR-0068 CompiledRunPlan、ADR-0075 阶段图、ADR-0090/0091 Session/Follow-up 控制器、ADR-0186 Session SSOT、ADR-0194 Loop 收敛、ADR-0195 平台架构收敛、ADR-0206 信息图内核、ADR-0208 Model-Visible EP 白名单、Note `2026-09-08-agent-lab-absorb-end-state`、Note `2026-09-09-colony-runtime-architecture-review-response`。
- **Refines**：ADR-0093 §验收 §6 capability grant 不扩大（保持）。
- **Supersedes**：无（无 ADR 决定过 `agent_lab/plugins/base.py` 的双轨 plugin 体系，本 ADR 一次性关闭它）。
- **Reject**：第二套 `@plugin` 装饰器（lab 平行的 `GraphPlugin`）；节点文件内 `new SimpleBody / PipelineSafeExecutor / InternalTransport / Session`；`tools/registry.yaml` 的 lab 私有加载器；`runtime_bind.ensure_act_runtime` 的 `global _PUBLISH_TOKEN`；任何「暂时保留双轨、不收编」。

**理由**：agent_lab 是 ADR-0206 的「prototype」吸收入口，2026-09-08 已立 Note 写明 delete-when，但**收编本身从未落地**。当前节点文件（`act.execute.plugin / body.py`、`runtime_bind.py`）违反 ADR-0061 / 0062 / 0068 / 0186 的现有不变量，且违反 AGENTS.md §3 C5 / C6 / C10 / C11、C12 与 §4 禁止事。短期看是 prototype，长期保留就成第二事实源、第二 Session 入口、第二组合根——这是「不收编，等着分裂」。

**Follow-ups**：实施切片见配套 spec [`2026-09-09-lab-cordis-unification-design.md`](../specs/2026-09-09-lab-cordis-unification-design.md) §B 的 PR-A~E；P7 阶段闭集迁移由 ADR-0206 §10 P7 显式承担，本 ADR 不重复。

---

## 0. 第一性原理：问题本质

### 0.1 现状的「三套体系」

| 维度 | LCA 生产路径 | agent_lab prototype | 后果 |
|---|---|---|---|
| **插件装饰器** | `lca.harness.plugin_api.plugin`（`@plugin`，Cordis 载体 + Manifest 审计） | `agent_lab.plugins.base.GraphPlugin`（自写 `register_plugin` / `fanout_hooks`，无 Manifest，无闭包校验） | 两套插件词表、两套注册中心、两套 Manifest；不可混挂 |
| **节点定义** | `class PhaseExecutor` 实现 + `PhaseBinding` 在 Profile 选 | `class Node` + `@node(...)` 装饰器（agent_lab 自有）+ 工厂表 `NodeRegistry` | 节点也是「进程级 capability」，图 DAG 看不见 |
| **组合根** | Profile/Bundle → Cordis Context → `ctx.require` | `act.execute.body.build_body()` 在节点文件内 `new SimpleBody / PipelineSafeExecutor / InternalTransport`；`runtime_bind.ensure_act_runtime` 全局 token 绑 Session | Body / Executor / Transport / Session 装配**不在图里**；图依赖被 Python 静态依赖掩盖 |
| **Session** | `Session.append` 单轨（ADR-0186 / 0194 / 0206） | `runtime_bind` 侧信道 + `set_publish_session`（在 agent_lab 子模块） | 第二条 Session 入口风险（`session_id=agent_lab_default` 已被 Note 警告） |

### 0.2 本质命题

1. **唯一插件入口** = `@plugin`。任何 `register_*` / `class GraphPlugin` / `@node_factory` 都是第二词表，与 AGENTS.md §4 「禁止平行 ADR/Note/Proposal」同罪。
2. **节点不是进程级 capability**；它是「图内 factory + 配置驱动的工兵」。它**消费** capability，**不装配** capability。
3. **组合根唯一** = Profile/Bundle → Cordis Context → `ctx.require`。节点文件正文只调「已 require 的句柄」，永不 `new` 装配品。
4. **依赖闭包**在 YAML/Bundle 上完整可见；任何 `from lca.cognition` 在 `agent_lab/` 节点文件内出现 = 编译失败（lint-imports 守护）。
5. **Session** 单轨：`set_publish_session` 已是 `lca.plugins.events.publishers._session_publish` 的单入口；`runtime_bind.global` 是历史债务，本 ADR 关闭。

### 0.3 删除条件

若全部满足：
1. `agent_lab.plugins.base` 不再导出 `GraphPlugin` / `register_plugin`（仅留 `HookEvent` 枚举与内部 helper；helper 也只给 LCA plugin 内调用）
2. `agent_lab.nodes/**/plugin.py` 无 `from lca.cognition.body|executor|session` import
3. `act.yaml` / 全部 phase YAML 上的 `factory:` 字段值都能在 `lca.plugins.lab.*` 找到对应 `@plugin`
4. `rg 'agent_lab\\.runtime\\.runner' lca/ lca_kernel/ profiles/ bundles/` = 0
5. `python -m agent_lab.run` 仅作为「图 B 自检 CLI」存在，不进 Gateway/生产入口
6. `web-standard` Profile 与 `agent-lab-infoedge` Profile 的 capability 闭集之差只剩 `lab.*` 前缀；其余完全等价
7. `bundles/agent-lab-infoedge.yaml` 与 `profiles/agent-lab-infoedge.yaml` 已带 delete-when，可整组删除

本文降为附录。

---

## 1. 决策（最终采纳什么）

### 1.1 唯一插件入口：`@plugin`

- LCA 的 `@plugin`（`lca.harness.plugin_api`）是 plugin 的唯一入口。
- `agent_lab.plugins.base` 仅保留两类符号：
  - `HookEvent` 枚举（编译期/runner 期 hook 闭集），作为内部常量使用；不导出 plugin 注册面。
  - helper 函数（`fanout_hooks` / `Bind`）只在 LCA plugin 的 `setup()` 内被调用。
- **删除**：`register_plugin` / `register_instance` / `get_plugin_class` / `resolve_plugin` / `discover` 全部对外符号。
- 新 `@plugin` 写于 `lca/plugins/lab/<kind>/plugin.py`，import 由 `lca/plugins/lab/<kind>/__init__.py` 暴露。

### 1.2 节点即 LCA plugin

- 每个 `agent_lab.nodes.<area>.<name>.plugin` 迁移到 `lca.plugins.lab.<area>.<name>.plugin`。
- 每个节点对应一个 `@plugin`：
  - `id = "lab.<area>.<name>"`
  - `provides = ["lab.<area>.<name>.out:<port>"]`（每个 out 端口一个 capability key）
  - `requires = [...]`（见 §1.4 capability 词表）
  - `effects = EffectClass.WORLD`（真副作用层）/ `EffectClass.NONE`（纯变换）
  - `layer = "L4"`，`kind = PluginKind.PRIMITIVE`（工人）/ `PROVIDER`（仅供给）
- 节点 YAML `factory:` 字段值 = plugin id；不再有 `class NodeRegistry` 的内层工厂表。
- `@node(...)` 装饰器保留作为**内部**自描述 helper（描述 `NodeManifest` 元数据），但不再注册到全局；元数据由 `@plugin` 装饰器的 Manifest 取代。

### 1.3 装配唯一：Profile/Bundle

- `act.execute` 所需的 Body / ToolRegistry / plan_ref / SafeExecutor / Transport **全部**由 Bundle 上的 `@plugin` provider 提供。
- 节点文件 `plugin.py` 的 `execute(...)` 函数**只消费** `ctx.require(...)` 在 setup 阶段拿到的句柄；不再在调用现场 new。
- `act.yaml` 上增加 `capabilities:` 段（已在 `graph:` 顶层有 schema），声明图级的 `requires / provides`；编译期校验所有 `requires` 都在 Profile 解析出的 capability 闭集内（`CapabilityGrantExceededError`，与 AGENTS.md C5 三维单调一致）。

### 1.4 Capability 词根（lab.* 闭集）

```text
lab.session                # 当前活动的 Session（注入；由 SetPublishSession 持有）
lab.plan_ref              # 字符串 plan_ref（agent_lab_act 等）
lab.body                  # SimpleBody（来自 lca.plugins.composer.act.body_provider）
lab.tool_registry         # LabToolRegistry（合并自 tools/registry.yaml）
lab.safe_executor         # PipelineSafeExecutor
lab.transport             # InternalTransport + 已注册 agent（lab_echo 等）
lab.hook_dispatcher       # HookEvent fanout（替代当前 fanout_hooks 的「全局注册面」）

# 工兵产出（capability key = "lab.<area>.<name>.out:<port>"）
lab.act.shape.out:intent
lab.act.authorize.out:authorized
lab.act.execute.out:receipt
lab.act.observe.out:observation
lab.perceive.sense.out:sensor_items
# ... 其他按 YAML port 推
```

> 任何新增 `lab.*` capability 必须同时改：
> 1. `lca.contracts.capabilities` 闭集（如新增则提 ADR；本 ADR 草案内一并声明）
> 2. 对应 provider 的 `@plugin(provides=[...])`
> 3. 消费方的 `@plugin(requires=[...])` 或 YAML `capabilities.requires`
> 4. `docs/specs/capability-closed-set.md`（待建）

### 1.5 Session 单轨

- 删除 `agent_lab.nodes.act.execute.runtime_bind.ensure_act_runtime` 的 `global _PUBLISH_TOKEN`。
- 由 Bundle 内一个 `@plugin(provides=["lab.session"])` provider 在 setup 阶段 `set_publish_session(run_session.event_session)`；节点不再触碰 `set_publish_session`。
- `session_id="agent_lab_default"` 在 `lca/plugins/lab/session/provider/plugin.py` 中**禁止构造**；如 active session 缺失，抛 `RuntimeError`（与 `lca-loop-infoedge` 已有的 `infoedge_driver_runtime_requires_session` 同形）。

### 1.6 删除清单（不留跨 PR 后门）

| 文件 | 删除 |
|---|---|
| `agent_lab/plugins/base.py` | `register_plugin` / `register_instance` / `register_fixture_instance` / `unregister_instance` / `unregister_fixture_instance` / `get_instance` / `get_fixture_instance` / `get_plugin_class` / `discover` / `resolve_plugin` |
| `agent_lab/nodes/act/execute/body.py` | 整文件（`build_body` / `run_body_act` / `decision_from_intent` / `_lab_transport` / `as_lca_tool_registry` / `observation_to_receipt`） |
| `agent_lab/nodes/act/execute/runtime_bind.py` | `ensure_act_runtime`（`plan_ref()` 常量保留为 provider 的 config 默认值） |
| `agent_lab/nodes/act/execute/runtime_bind.py` | `reset_act_runtime_for_tests`（改由 LCA Session test fixture） |
| `agent_lab/adapters/` | 整目录（合并进对应 LCA plugin） |
| `agent_lab/tools/registry.py` / `agent_lab/tools/registry.yaml` | `LabToolRegistry`（替换为 `lca.plugins.lab.tools.provider`，YAML 由 bundle 携带） |

### 1.7 留存清单

| 文件 | 保留原因 |
|---|---|
| `agent_lab/graph/` | 图编译器（ADR-0206 §5 CompiledGraphBundle）；被 LCA `Compile` 阶段调用 |
| `agent_lab/runtime/runner.py` | 递归解释器（ADR-0206 §5.2 `GenericPlanInterpreter`）；通过 `lca.plugins.loop.driver.infoedge` 暴露 |
| `agent_lab/primitives/` | Artifact / Port / Edge；可由 `lca.contracts` 引入（属于 contracts 层无 I/O） |
| `agent_lab/nodes/` | 仅保留「图内 factory helper」（`peel_manifest` / `complete_turn` 等纯函数），由 LCA plugin `setup()` 调用；不再做 plugin 注册 |

---

## 2. 词汇表（受控命名）

| 词根 | 定义 | 不变量 |
|---|---|---|
| `lab.*` | agent_lab prototype 收编后产出的 capability key 前缀 | 仅本 ADR §1.4 列出的闭集可写；新增需 ADR |
| `lab.<area>.<name>.out:<port>` | 工兵产出端口的 capability key | 编译期校验 `out:<port>` 与节点 YAML `outs:` 一致 |
| `HookEvent` | 编译期/runner 期 hook 闭集 | 与 ADR-0206 §3 EventBus EP 闭集**分开**；hook 不写 spine |
| `LabToolRegistry` | lab 工具 registry（YAML 装载） | 由 `lab.tool_registry` provider 持有；不再有 module-level 全局 |

---

## 3. 不变量

| ID | 不变量 | 落点 |
|---|---|---|
| **I-1** | 唯一插件装饰器：`lca.harness.plugin_api.plugin`；`agent_lab.plugins.base` 不导出 `register_*` | lint-imports + audit-plugin-shape |
| **I-2** | 节点文件 `plugin.py` 内 `from lca.cognition` / `from lca.cognition.body` / `from lca.cognition.body.executor` / `from lca.session` 出现 = 编译失败 | lint-imports `lab-node-purity` 规则 |
| **I-3** | `act.yaml` 与所有 phase YAML 的 `factory:` 字段值都能解析到 `@plugin`（compile 阶段解析） | `agent_lab.graph.compile` 扩展 `resolve_plugin_id` 失败 → `UnknownFactoryError` |
| **I-4** | Profile/Bundle 的 capability 闭集 ⊇ 所有 phase YAML `capabilities.requires`；否则 `CapabilityGrantExceededError` | agent_lab compile + Cordis resolve |
| **I-5** | 节点 `execute()` 函数无 `new <装配品>`；只调已注入句柄 | ruff AST 规则 + 静态扫描（`rg "= (SimpleBody|PipelineSafeExecutor|InternalTransport|Session)\\(" agent_lab/nodes/` = 0） |
| **I-6** | Session 单轨：`set_publish_session` 唯一入口在 `lca/plugins/lab/session/provider/plugin.py`；节点文件正文不再调 `set_publish_session` | rg `set_publish_session` 在 `agent_lab/nodes/` = 0 |
| **I-7** | `agent_lab_default` session_id 不被任何 plugin 主动构造；如 active session 缺失，fail-loud | `rg 'agent_lab_default' agent_lab/ lca/` = 0（除 lab session provider 注释中的禁止声明） |
| **I-8** | 闭集：lab capability key 前缀 `lab.*`；新 key 必须先在本 ADR 增列 + 在 spec `capability-closed-set.md` 登记 | ADR 索引 + spec 测试 |
| **I-9** | `Bundles/agent-lab-infoedge.yaml` 与 `profiles/agent-lab-infoedge.yaml` 头注释必须保留 delete-when（本 ADR §6） | rg 头注释 + audit-plugin-shape |

---

## 4. Bundle 拓扑（吸收后目标）

```text
profiles/web-standard.yaml           (生产)
  bundles/base.yaml
  bundles/session-runtime.yaml
  bundles/observability-default.yaml
  bundles/declarative-phase-graph.yaml
  bundles/web-app.yaml
  bundles/loop_cursor.spine_default.yaml
  bundles/event-bus-components.yaml

profiles/agent-lab-infoedge.yaml      (图 B 专用)
  bundles/base.yaml
  bundles/session-runtime.yaml
  bundles/observability-default.yaml
  bundles/declarative-phase-graph.yaml      # 0075 作为 dead Plan region 仅过 compile
  bundles/web-app.yaml
  bundles/loop_cursor.spine_default.yaml
  bundles/event-bus-components.yaml
  bundles/lab-plugins.yaml                 # NEW: lab 工兵 plugin 集
  bundles/lab-act.yaml                     # NEW: Body / ToolRegistry / plan_ref / Transport
  bundles/lab-session.yaml                 # NEW: lab session provider
  bundles/agent-lab-infoedge.yaml          # 保留：loop driver 注册 + delete-when
```

`bundles/lab-act.yaml` 入口：

```yaml
name: lab-act
description: |
  agent_lab 图 B 的 act 阶段装配（lab 专用，不挂 web-standard）。
  提供 Body / ToolRegistry / plan_ref / Transport；act.* 工兵 require 它们。
entries:
  - id: lab-act-body
    $module: lca.plugins.lab.act.body_provider
    config:
      plan_ref: agent_lab_act
      allow_tools: [bash, file_write, read_file]
  - id: lab-tool-registry
    $module: lca.plugins.lab.tools.provider
    config:
      tools_yaml: agent_lab/tools/registry.yaml
  - id: lab-transport
    $module: lca.plugins.lab.transport.provider
    config:
      agents:
        - { role: lab_echo, kind: echo }
```

`bundles/lab-plugins.yaml` 入口：所有 `lab.<area>.<name>` 工兵 plugin（`act.shape` / `act.authorize` / `act.execute` / `act.observe` / `perceive.*` / `think.*` / `reflect.*` / `remember.*` / `session_log.*`）。

`bundles/lab-session.yaml` 入口：`lca.plugins.lab.session.provider`，setup 阶段 `set_publish_session`。

---

## 5. 节点迁移示例（`act.execute`）

**Before**（`agent_lab/nodes/act/execute/plugin.py`）：

```python
class ActExecute(Node):
    def execute(self, node, inputs):
        ...
        if verdict == "allow":
            obs = act_body.run_body_act(content, allowed_tools=allowed)
            ...
```

`act_body.run_body_act` → 内部 `build_body` → `new SimpleBody(PipelineSafeExecutor(...), ..., transport_registry=...)`。

**After**（`lca/plugins/lab/act/execute/plugin.py`）：

```python
class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tools: tuple[str, ...] = ("bash", "file_write", "read_file")
    allow: tuple[str, ...] = ("bash", "file_write", "read_file")
    plan_ref: str = "agent_lab_act"


@plugin(
    id="lab.act.execute",
    Config=Config,
    requires=[
        "lab.body",
        "lab.tool_registry",
        "lab.safe_executor",
        "lab.transport",
        "lab.plan_ref",
        "lab.session",
    ],
    provides=["lab.act.execute.out:receipt"],
    implements=[],
    layer="L4",
    effects=EffectClass.WORLD,
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lab.act.execute.checked", "lab.act.execute.served")
        ),
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Wire authorized Intent → Body.act → Receipt; nothing more."""
    _handle = _ExecHandle(
        body=ctx.require("lab.body"),
        tools=ctx.require("lab.tool_registry"),
        executor=ctx.require("lab.safe_executor"),
        transport=ctx.require("lab.transport"),
        plan_ref=ctx.require("lab.plan_ref"),
        session=ctx.require("lab.session"),
        allow=tuple(config.allow),
    )
    ctx.provide("lab.act.execute.handle", _handle)  # 仅供给 lab runner 调用

    # 在 lab runner 侧：按 verdict 分岔后调 body.act；不在节点正文 new


def invoke(handle, *, intent, decision_id, action_type, ...):
    """Lab runner calls this; verdict 分岔仍在这里（不是 Body 装配）。"""
    ...
    obs = asyncio.run(handle.body.act(decision, state, plan_ref=handle.plan_ref))
    ...
```

> **节点正文只剩「分岔 + 收 receipt」**；Body / Executor / Transport 在 setup 阶段 require；`set_publish_session` 在 lab session provider 的 setup 内完成。

---

## 6. delete-when（同 PR 可删）

`profiles/agent-lab-infoedge.yaml` + `bundles/agent-lab-infoedge.yaml` + `lca/plugins/loop/driver/infoedge/` 在以下条件**同时**满足时可删除（合并入生产路径）：

1. `agent_lab.plugins.base` 不导出 `register_*` / `GraphPlugin`（helper 仅保留为内部）
2. `agent_lab.nodes/**/plugin.py` 无 `from lca.cognition|executor|session` import
3. `lca/plugins/lab/<area>/<name>/plugin.py` 全量覆盖图 B 所有 `factory:`
4. `rg 'agent_lab\\.runtime\\.runner' lca/ lca_kernel/ profiles/ bundles/` = 0
5. `web-standard` 与 `agent-lab-infoedge` Profile 的 capability 闭集之差只剩 `lab.*`
6. `python -m agent_lab.run` 不再进 Gateway/生产入口（仅保留自检 CLI）
7. ADR-0206 §10 P7 阶段闭集迁移完成（`region=phase:*` 全量使用）

前置条件（满足后**任何一条**触发即应启动合并）：
- 用户明确「开始实施合并」
- ADR-0206 P7 已启动（plan/owner 已登记）
- 团队评审通过本 ADR + 配套 design spec

---

## 7. Reject（显式拒绝）

| 提议 | 拒绝理由 |
|---|---|
| 保留 `agent_lab.plugins.base.GraphPlugin` 作为「内部 helper」 | helper 仍允许散在节点文件里 → 第二插件体系尾巴；保留导入面 = 保留逃避路径。只能保留为 `lca.plugins.lab.internal` 私有 helper，且不能从 `@plugin` 外部导入 |
| 在 `act.execute` 里继续 `new SimpleBody`，只把 registry 抽出去 | 半改不收敛；下一次想换 executor 时仍要改节点文件；违反 §0.2 命题 3 |
| 把 Body / Executor 放进 `lca/plugins/lab/act/execute/plugin.py` 同文件 setup | 同文件 setup ≠ 在图里；隐式依赖仍存在；违规 ADR-0068（CompiledRunPlan 不接受 implicit assembly） |
| 新增 `colony/` / `Pheromone` / `ActionValue` 来「解决」组合根可见性 | 已由 [Note 2026-09-09-colony-runtime-architecture-review-response](../notes/plans/2026-09-09-colony-runtime-architecture-review-response.md) §"Reject" 显式驳回；AGENTS.md C1 / C5 / C6 拒绝 |
| 通过 plugin 暴露 `tools/registry.yaml` 后还在 lab 内部保留一份 | 双 SSOT；违反 ADR-0195 §4；删除 `agent_lab/tools/registry.yaml` |
| 「双轨运行、不收编」 | 第二事实源 / 第二 Session 入口 / 第二组合根；直接违反 ADR-0186 / ADR-0194 / ADR-0206 |
| 把 `set_publish_session` 留在 lab 的 `runtime_bind.py` 里，标记「deprecated」 | 「deprecated」不删除 = 留下跨 PR 后门；AGENTS.md §4 兼容 shim 原则明确反对；同 PR 必须删 |
| 让 `web-standard` Profile 也挂 `bundles/lab-plugins.yaml` | 违反 Note `2026-09-08-agent-lab-absorb-end-state` §delete-when：lab 留出厂树外；合并 PR 才进 |

---

## 8. 验收（PR 实施前/中/后）

**每个 PR 完成时**：

| # | 验证 | 命令 |
|---|---|---|
| 1 | lint-imports | `./scripts/lca-ops lint-imports`（无新增失败） |
| 2 | plugin shape | `./scripts/lca-ops audit-plugin-shape`（新增 `lab.*` plugin 全部通过 Manifest 校验） |
| 3 | capability 闭包 | `python -m agent_lab.run --describe --target graph:act` 列出所有 `requires` / `provides` |
| 4 | 节点纯度 | `rg "from lca\\.cognition\\|executor\\|session" agent_lab/nodes/` = 0 |
| 5 | 节点纯度 | `rg "= (SimpleBody\\|PipelineSafeExecutor\\|InternalTransport\\|Session)\\(" agent_lab/nodes/` = 0 |
| 6 | Session 单轨 | `rg "set_publish_session\\|global _PUBLISH_TOKEN" agent_lab/nodes/` = 0 |
| 7 | 第二 plugin 体系 | `rg "from agent_lab\\.plugins\\.base import" agent_lab/ lca/plugins/lab/` 仅在 helper 内部使用 |
| 8 | 拓扑 | `./scripts/lca-ops inspect-tree profiles/agent-lab-infoedge.yaml` 出现 `lab.*` plugin |
| 9 | Profile 差集 | `python -c "diff_capabilities(web_standard, agent_lab_infoedge)"` 仅 `lab.*` 差异 |
| 10 | lab CLI 自检 | `python -m agent_lab.run act` 通过；`python -m agent_lab.run --describe --target graph:agent_loop` 列出全部 capability 关系 |

**ADR 升 Accepted 条件**（同 PR 系列全部完成时）：
- PR-A ~ PR-E 全部落地（见 design spec §B）
- §6 delete-when 全 7 条满足
- §8 验收 1–10 全部绿

---

## 9. 风险与代价

**正**：
- agent_lab 与 LCA 工厂合并；组合根唯一；Session 单轨；Manifest 闭包校验
- 调试路径清晰：哪个 plugin 没拿到 capability → 启动审计立刻给出
- 与 ADR-0206 §10 P7 阶段闭集迁移准备完整 dependency DAG
- 与 ADR-0206 §8 Reject 「拒绝第二 Runtime」对齐

**代价**：
- 一轮大规模 plugin codemod（≈96 个 plugin 文件逐个迁移）
- `agent_lab` 目录结构重整：`plugins/` 删除、`adapters/` 删除、`tools/registry.yaml` 删除
- lab CLI（`python -m agent_lab.run`）需在迁移后仍可作为图 B 自检入口；与生产路径解耦
- 5 个新 Bundle（`lab-plugins` / `lab-act` / `lab-session` / lab body / lab transport provider）

**风险与缓解**：
- 迁移中破坏 `web-standard` → **永远双轨 PR-A~E**（每 PR 仅影响 lab Profile），web-standard 始终不动
- `from lca.cognition` 散落难以全扫 → lint-imports `lab-node-purity` 规则 + pre-push grep
- capability key 名漂移 → §1.4 闭集 + spec `capability-closed-set.md` 测试守护
- 新 Bundle 体积膨胀 → Bundle 内 plugin 全部 `@plugin` 化，`why-plugin` 一键回答归属

---

## 10. 决策记录

**Adopt**：
- §1.1 唯一插件入口 `@plugin`
- §1.2 节点即 LCA plugin（`factory:` = plugin id）
- §1.3 装配唯一 = Profile/Bundle
- §1.4 `lab.*` capability 闭集
- §1.5 Session 单轨（删除 `runtime_bind.global`）
- §1.6 删除清单 / §1.7 留存清单
- §3 不变量 I-1 ~ I-9
- §4 Bundle 拓扑
- §5 节点迁移示例（`act.execute`）
- §6 delete-when
- §7 Reject
- §8 验收
- §9 风险与代价

**Absorb into LCA seams**：
- `agent_lab.graph.compile` 扩展 `resolve_plugin_id` → `UnknownFactoryError`
- `agent_lab.runtime.runner` 通过 `lca.plugins.loop.driver.infoedge` 暴露（已存在）
- `HookEvent` 闭集维持 lab 内部（不外溢）
- LabToolRegistry 经 `lca.plugins.lab.tools.provider` 收编

**Supersedes**：无（无 ADR 决定过第二 plugin 体系）

**Required follow-ups**：
- spec [`2026-09-09-lab-cordis-unification-design.md`](../specs/2026-09-09-lab-cordis-unification-design.md) 含 PR-A ~ PR-E 拆分
- spec `capability-closed-set.md`（待建）登记 `lab.*` capability key
- ADR-0206 §10 P7 阶段闭集迁移独立 ADR（本 ADR 仅为前置准备）

**Accepted 条件**：
- PR-A ~ PR-E 全部合并
- §6 delete-when 全 7 条满足
- §8 验收 1–10 全部绿
- spec `capability-closed-set.md` 落地 + 测试守护
- `web-standard` Profile capability 闭集审计：`why-plugin lca-loop-infoedge` 在 `web-standard` 下 = "not in this profile"