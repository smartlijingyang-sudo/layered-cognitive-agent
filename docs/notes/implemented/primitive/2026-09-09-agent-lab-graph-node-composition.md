# Agent Note: agent_lab 图与工人组合律

Status: implemented

## Problem

`agent_lab` 的可执行形态是嵌套 `InfoEdgeSpec` 加工人节点，骨架已经是数据流：端口进、端口出、边点火。真正的失败不在“有没有图”，而在组合没有闭包。

打开根图看不到 control 从哪来。`graphs/configs/control/*.yaml` 已是图，但挂载发生在 `ControlSlotsPlugin.before_compile` 的 Python 接线表里：编译器改 host 的 `ins`/`outs`、塞 `SubSpecLink`。同一 host 可挂多张子图，后一张靠 host store 刷新读前一张的 OUT。子图因此依赖“父亲碰巧把谁挂在同一桩上”，而不是自己的 IN。

工人互动没有唯一合法通道。`@node` 上的 `provides` / `requires` / `relates_to` 是注释；`InfoGrant` 在 spec 里，校验只要求 ports 非空；跨 spec 读靠 `kind: project` 特例。工人若需要另一张图的能力，只能 Python import 兄弟、查 `NodeRegistry`、或读父 store。结果是第二依赖面。

横切业务走第二数据面。`semantic_router` 按 `schema_ref` 在边传播前改写 outputs；parse / observe render / memory extract / tool guard 活在 plugin hook 里，与 think/act/reflect 图上已有工人并行。Observation 可以改变 Capability。

工人内部承担多种问题。`act.execute` 同时判 verdict、调 Body、折 HIL、整形 receipt。Phase host 用 `factory: identity` 冒充工人。`execute` 从模块全局取 `lab_tools()` / Session，组合根不在 Profile。

缺了这些闭包，“能力皆图”只是目录布局：图文件在，编排真值在 Python 里。子图也无法在不偷读的前提下复用另一处能力。

## Decision

组合律是 `agent_lab` 图内核的编译期契约。它落实 [ADR-0206](../../../adr/0206-information-graph-kernel.md) 的单图种与 Grant，不改六阶段闭集、不改 Journal 词表、不把每个工人收成 Cordis `@plugin`（与 [absorb-end-state](../../proposed/seam/2026-09-08-agent-lab-absorb-end-state.md) 一致）。[ADR-0209](../../../adr/0209-agent-lab-cordis-unification.md) 拥有 Session 单轨与 Body 组合根；本 note 拥有图/工人怎么接线。

### 三平面

Kernel 不是图：Compile、Interpreter、`Session.append`、Grant 检查、SafeExecutor、时钟与随机。工人可以 `requires` 它们，不能实现它们，不能在工人里构造它们。

Capability 全部是图加工人：阶段、model_eye、effect、control、digest、parse、HIL、stop。复用是再 mount 一张 `InfoEdgeSpec`，不是调用另一个工人的 `execute`。

Observation 只记录：contained observer 或后续 lineage 子图。失败不回滚已 commit 的 append；禁止改 Artifact、禁止改拓扑。

### 工人

签名：

```text
execute(node, inputs: Map<Port, Artifact>, seams: Mapping[str, object])
    → Map<Port, Artifact>
```

`seams` 的 key 是 `manifest.requires` 的闭包，由 runner 按登记表注入，不多给。YAML `ins`/`outs` ⊆ manifest 端口；端口真值不在 `config.from` / `config.to`。输入 Artifact 只读。工人不 import 其他工人 `plugin.py`，不 `NodeRegistry.get` 兄弟，不读父 store，不读模块级 Body/Session 全局。删除 `relates_to`。

`execute` 出现第二种业务问题、可复用子流程、或控制流（`if verdict` 选下游）时，升格为图。`act.yaml` 现为：

```text
shape → authorize → dispatch(verdict)
                      ├─ allow → act.body
                      ├─ deny  → act.receipt_denied
                      └─ skip  → act.receipt_none
receipt → observe ─project→ model_eye.see
```

有 `sub_specs` 的节点是 host：恰好一张子图，无业务 factory。`identity` 只留给真 passthrough。

### 边与组合方向

| Kind | 范围 | 失败 |
|---|---|---|
| `data` | 同图 | 缺 required IN → 工人不跑 |
| `control` | 同图闸门/路由/挂起 | 未满足 → 挂起或拒绝支路 |
| `effect` | 同图副作用 | 无回执边 → 编译失败 |
| `project` | 跨 spec，进入 model-visible | 效应输出未 project 且未 discard → 编译失败 |
| `borrow` | 跨 spec 读，必须引用 Grant | 无 Grant / 超 Grant → 编译失败 |

向下：`sub_specs` + `input_map` / `output_map`。横向：父图边，或 Grant + `borrow`。向上：非法。跨任意位置：只有编排者（父图）发 Grant；孩子只见自己的 IN。

同图多写者必须经显式 join。并行必须经 Barrier/Join。

### Control 挂载

Control 图（`graphs/configs/control/*.yaml`）保持为 `InfoEdgeSpec`。挂载写在父图：每个 control 是 **兄弟 host**，用父图 `data` 边喂 IN，不是同一 host 的第二张 `sub_spec`。

```yaml
nodes:
  - id: remember
    # host → remember.yaml；outs 含 state_ref
  - id: stop_decide
    # host → stop_decide.yaml
edges:
  - from: { spec: agent_loop, node: remember, port: state_ref }
    to:   { spec: agent_loop, node: stop_decide, port: in_state }
    kind: data
sub_specs:
  - node: remember
    sub_spec: remember
    ...
  - node: stop_decide
    sub_spec: stop_decide
    input_map: { in_state: in_state, ... }
    output_map: { stop_decision: stop_decision, terminal: terminal }
```

`before_compile` 不得改拓扑、不得补端口、不得扫目录把 yaml 塞进 registry。图来自加载器显式列表。`ControlSlotsPlugin` 接线表删除。

### 失败与幂等

工人把失败写成 Artifact（receipt / verdict / EXCEPTION 端口）。解释器按 `on_error` 选边。`on_error=route` 先 invoke，失败后再把 EXCEPTION 送到 `route_to` 的 IN；不是调用前跳过。确定性错误不重试；瞬时错误才 `retry`。缺 required IN 在运行时仍缺 = 解释器 bug（编译期应已失败）。

子图中途失败：已写出的 Artifact 留在子图 trace，**不**经 `output_map` 渗进父 OUT。父图只看见 host 失败。

同一 `(plan_hash, subgraph_path, node_id)` 一次 Run 只 invoke 一次。恢复钉死 `plan_hash`。`Session.append` 的去重是 seam 幂等键，不是工人分支。Observer 可重复、失败 contained。Effect 工人不声称幂等。

### 编译追加不变量

ADR-0206 C1–C14 保持。下列 N* 由 `agent_lab.graph.validate` 硬失败：

| ID | 不变量 |
|---|---|
| N1 | YAML `ins`/`outs` ⊆ manifest 端口 |
| N2 | 每个 `requires` 有提供者（上游 `provides` 经边，或 kernel seam 登记表） |
| N3 | 一个 host 恰好一张 `sub_spec` |
| N4 | host 无业务 factory |
| N5 | 跨 spec 边只允许 `project` 或 `borrow` |
| N6 | Observation hook 不得出现在能改 outputs 的路径 |
| N7 | 工人 `plugin.py` 不得 import 其他工人 `plugin.py` |
| N8 | 禁止新增 `relates_to` |

`plan_hash` 覆盖 nodes / edges / sub_specs / grants / seams 绑定。运行只认 `CompiledGraphBundle`。

未声明 seam、borrow 超 `max_bytes` / 命中 `redact`、effect 绕过 SafeExecutor：运行拒绝，走 deterministic / control 拒绝支路。

不把 Kernel 图化。不引入 compile 期“图产生图”。不把每个 `@node` 收成 Cordis `@plugin`。lineage 子图由 [ADR-0206](../../../adr/0206-information-graph-kernel.md) §10 P8 拥有，本 note 不引入。

## Alternatives considered

### Why not 工人互调 / 运行时服务发现?

子图直接 `execute` 任意位置节点，能少写边。代价是子图不可搬家、不可单测、编译器无法回答模型可见闭包与 effect 授权。那是共享黑板，与 ADR-0206 C4 / C11 冲突。否决。能力只经父图边或 Grant 注入到 IN；Kernel 只经声明 `seams`。

### Why not compile 期 compose 图（图产生图）?

slot 政策本身做成一张 compile 图，输出 `SubSpecLink[]`，更接近“万物皆图”。当前只有一个根图、一套 control 挂载；compose 解释器是第二套编译器，根 YAML 不再是拓扑真值（除非强制 dump 展开图）。YAGNI。出现 ≥3 个根图且政策要切换时另开 note。

### Why not `slots:` 清单 + 目录展开?

父图写 `slots: [stop_decide]` 更短。展开仍是隐式，只是从 Python 搬到约定，并新增平行于 `sub_specs` 的词表。糖可以后加；第一规范是父图诚实声明。

### Why not 保留 `before_compile` 幂等插入 control?

接线表已经能跑，改 YAML 更长。打开 `agent_loop.yaml` 看不见 stop 从哪根边读 `state_ref`；`plan_hash` 对插件改写敏感却对读者不透明。Observation/Capability 平面混在 hook 里。否决。插入政策若要换，改父图，不改 Python。

### Why not 把 Kernel 也做成图?

Compile / Interpreter / `Session.append` 再图化，图会改写自己的解释器，违反 ADR-0206 Reject「口号化万物皆图」与 C9 Kernel-Closed。Kernel 保持闭集；Capability 才是图。

## Consequences

根图 YAML 更长，拓扑真值可读。Body 装配仍与 ADR-0209 重叠：`act.body` 继续调 `execute.body` 助手；`tools/registry.py` 未恢复。C1 只检查 act 是否有出站 `project` 边，不是全图可达。`observe_checkpoint` / `observe_wildcard` 未挂（无 event-log 生产者）。

## Verification

- `python -m agent_lab.run --describe --target graph:agent_loop` 列出 `stop_decide` 与 `remember.state_ref` 边。
- `rg ControlSlotsPlugin agent_lab/` = 0；`rg PHASE_OWNER_WIRING agent_lab/` = 0；`rg semantic_router agent_lab/` = 0。
- `tests/agent_lab/test_validate_composition.py` 覆盖 N1–N8 / C4 / C1 金丝雀 / 子图失败不渗漏。
- `scripts/check_agent_lab_node_imports.py` 拦截工人 `plugin.py` 互 import。

## Related

- [ADR-0206](../../../adr/0206-information-graph-kernel.md) — 单图种、Grant、嵌套子图。
- [ADR-0209](../../../adr/0209-agent-lab-cordis-unification.md) — Cordis 收编、Session 单轨、禁止节点内组合根。
- [agent_lab absorb-end-state](../../proposed/seam/2026-09-08-agent-lab-absorb-end-state.md) — 双挂桥接与工人不逐个 Cordis 化。
- [agent_lab/README.md](../../../../agent_lab/README.md) — 进程外入口与图布局。
