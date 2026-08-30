# ADR-0056: 群服务投稿 — 签名即依赖，配置即装箱单

## 状态

Accepted

Amends: [ADR-0004](0004-protocol-first-pluggability.md)、[ADR-0005](0005-composition-root-l4.md)

Withdraws: 宪法 v3「Composer 点名 `sensor.*` / `gate.*` 钥匙并组装 Hub / Gate 链」那一句（见 [认知原语宪法 v3](../design/2026-08-19-cognitive-primitive-constitution-v3.md) 双平面落点）。六步闭集、双平面、Reducer 唯一写、Journal 唯一事实源、插件不听 `agent.*` 做控制，全部保留。

## 背景

Agent 运行时是一份**闭集循环上的可替换贡献**：感知、判决、推理、工具、prompt 节都可以换，循环本身不能换（宪法 C1 / C6）。

曾把「可替换」做成第三种东西：每个贡献一个 `ctx` 钥匙（`sensor.clock`、`gate.repeat-tool-call`），插件 `provide` 工厂，Composer 再按硬编码名单 `_SENSOR_ORDER` 等去 `inject`。YAML 里的 `inject:` 与 `@plugin(requires=...)` 不参与加载。[`boot_entries`](../../lca/harness/profile/boot.py) 按列表顺序 `await setup`，绕开了 vendored Cordis 已有的 Fiber / `inject` 挂起。

结果是三套真相：配置说装了谁，插件说挂了什么钥匙，Composer 说实际拼了什么。最小粒度每加一项，就要同时改插件文件、bundle 行、Composer 名单。读配置看不到关系；读插件看不到契约；读 Composer 才能猜装配。

这不是插件太多，是**装配权放错了地方**。一个只为了被中心组装者查找而存在的名字，不是契约，是缺失的注册表。

## 第一性原理

从「一个运行中的 Agent 是什么」推导，不从 DSH 的包布局推导。

| # | 不变量 | 含义 | 违反后果 |
|---|---|---|---|
| **A1** | **循环闭集，贡献开放** | 六步不是插件；一步之内的 Sensor / Gate / Tool / prompt 节是插件 | 在循环上开洞，或反过来把 clock 做成「缝」 |
| **A2** | **投稿到活服务** | 插件把实现挂到已经存在的群服务或缝上，不发明查找用钥匙 | 中心组装者与插件双重维护同一份名单 |
| **A3** | **签名即依赖** | 加载期依赖 = 插件函数的类型注解；Loader 强制满足 | YAML / meta 里的 `inject` 漂成注释，缺依赖变成 `None` |
| **A4** | **配置即装箱单** | Profile / Bundle / Patch 只回答启用了谁、覆盖什么 config | 配置与代码各写一遍依赖，读任一页都残缺 |
| **A5** | **群服务组装** | 概念群拥有 `assemble()`：顺序、slot、缺省 no-op（C7）住在群里 | 顺序藏在 Composer，slot 藏在 meta 插件 |
| **A6** | **L4 闭合对象图** | `spawn_agent` / `spawn_team` fork 隔离、把已经 assemble 好的 Protocol 放进 Runtime；**无 Composer 类** | L4 点名贡献 id，或保留会列零件的 Composer |

Python 在这条设计上的优势（DSH 用 TS 做不到、也不该抄的部分）：

- **模块就是插件身份**。`lca.plugins.perceive.clock` 即 id，不需要 npm 包 + `package.json` + declaration merging。
- **类型注解就是 inject 图**。函数参数类型映射到群服务 key，与 FastAPI / pytest fixture 同一心智。
- **Protocol 是契约，类是实现，函数是挂钩**。三件套都是语言原语，不必再发明 PluginManifest（宪法已否决第三套 schema）。
- **Config 可缺省**。无可配项就不声明 schema；有则 Pydantic `extra="forbid"`。禁止空 `class Config` 模板。

## 决定

### 1. 插件只有两种形态

**缝（Seam）** — 可换的世界能力。三角角色，变的速率不同才拆文件，不预防性拆：

| 角色 | 职责 | 例子 |
|---|---|---|
| Definition | 拥有 `ctx.<key>` 与词汇表，是活的服务 / 注册表 | `LlmService`、`ToolsService` |
| Provider | inject 该 key，`register` 实现 | `llm/deepseek.py` |
| Consumer | inject 服务，挂到另一个表面（通常是 tools 或 system_prompt） | `tools/bash.py` |

「一个调用工具是插件」= 一个 Consumer：inject `tools` 与它需要的世界能力，`tools.register(...)`。Loop / Composer 零改动。

**投稿（Contribution）** — 认知原语对概念群的贡献。不是新缝。clock 没有第二套 provider，不配 Definition。

```python
@plugin
def clock(perceive: PerceiveService) -> None:
    from lca.cognition.sensors.clock import ClockSensor
    perceive.add(ClockSensor(), id="clock", order=10)
```

禁止 `ctx.provide("sensor.clock", ClockSensor)`。`ctx.provide` 只留给 Definition / 群服务本身。

### 2. 群服务是装配权所在

每个开放投稿的概念群有且仅有一个服务。服务住在实现层（L0 / L1），插件模块只把它 `provide` 出去。

| 群 | 服务 key | `add` 的是 | `assemble()` 得到 |
|---|---|---|---|
| Perceive | `perceive` | `Sensor`（id + order） | `PerceiveHub` |
| Gate | `gates` | `DecisionGate`（id + slot + order） | `ChainedDecisionGate` |
| Think | `brain` | 工厂（已 inject critic / reasoner / gates） | `Brain`（compose 时 create） |
| Act | `body` | Body / SafeExecutor 工厂 | `Body` |
| Prompt | `system_prompt` | 一节可渲染文本 | 模型可见 prompt |

顺序、slot、缺省空链（C7）是群服务的契约，不是 Composer 的名单，也不是 `gate.workspace-agent` 这种 meta 插件。Hub 可用自己的 `config.order` 覆盖投稿上的默认 `order`。未出现在装箱单里的投稿不加载，加载了但未 `add` 的不进入 `assemble()`。

实现类继续留在 `lca/layer1_cognitive/` 等层内（[ADR-0001](0001-five-layer-separation.md)、[ADR-0015](0015-contracts-no-behavior-classes.md)）。插件文件只回答：挂到哪个服务、贡献什么、id / order / slot。

### 3. `@plugin` 从签名派生契约

`@plugin` 读取函数签名：

- 类型为群服务 / 缝 Definition 的参数 → `inject` 列表（字符串 key 由服务类上的 `key` 提供）。
- 名为 `config` 且为 Pydantic 模型的参数 → Cordis `Config` schema。
- 返回 disposer callable → Fiber 卸载时调用。
- 函数所在模块路径 → 默认插件 id；`@plugin(name=...)` 仅在需要稳定 id、与模块路径不同时使用。

Loader **执行** 这份 inject：对应服务未 `provide` 则 Fiber 挂起；profile 结束时仍未满足则 boot 失败。禁止 `try: inject except: return None`。YAML **不得** 再写一遍 `inject`（会漂）。`provides` / `requires` / `layer` 等 DSH 风 meta 若仍需给 inspect 用，从签名与群服务登记派生，不手填。

Boot 走 `ctx.registry.plugin(...)`（vendored Cordis Fiber），不走「按 YAML 顺序 `await setup`」。YAML 行序给人读，激活序由 inject 图决定。

### 4. L4 组合根是 `spawn_*`，不是 Composer

[ADR-0005](0005-composition-root-l4.md) 仍然成立：跨层闭合留在 L4。`AgentComposer` / `TeamComposer` **删除**。开发者门面是 `Agent(...)` / `Team(...)`；对象图闭合是：

```text
spawn_agent(spec, scope=...)
  hub   = scope.inject("perceive").assemble(...)
  brain = scope.inject("brain_factory")(spec…)
  body  = scope.inject("body.simple")(…)
  runtime = build_cognitive_runtime(...)

spawn_team(spec, scope=...)
  # 共享记忆 / transport / 把 TeamSpec.governance 编成封闭策略
```

`spec.llm` / `spec.tools` / `RoleProfile` 仍在 spawn 时进入工厂：boot 登记投稿，带 spec 的对象在 agent 路径里 create。

[ADR-0004](0004-protocol-first-pluggability.md) 仍然成立：可替换单位是 Protocol。本 ADR 补上 Protocol **如何进入运行时**：实现类经投稿或 Provider 挂到群 / 缝，而不是经 Composer 名字字符串与 L4 注册表双轨。

### 5. 配置三层只装箱，不画依赖

保持 Profile → Bundle → Patch。读配置 = 读启用集合。

```yaml
# bundles/web-app.yaml  — 出现的 id = 这个 agent 启用的认知行为
entries:
  - id: perceive
    $module: lca.plugins.perceive

  - id: sensor.clock
    $module: lca.plugins.perceive.clock

  - id: gates
    $module: lca.plugins.gates

  - id: gate.repeat-tool-call
    $module: lca.plugins.gates.repeat_tool_call

  - id: tool.bash
    $module: lca.plugins.tools.bash
    config:
      timeout_s: 30
```

覆盖语义保持：同 id 的 `config` merge；`disabled: true` 跳过该 Fiber。disable 一个 sensor，Hub 里就没有它，不必改 Composer。

`dump-profile` 打印装箱单（与 boot 加载集合相等）。`inspect-tree` 打印 Loader 的真 inject 图（谁等谁、谁 `add` 到哪个群），不是手填 meta 的投影。

### 6. 定位地图

按概念群分目录。找行为先看群，找算法再下层。

| 问题 | 打开 |
|---|---|
| 感知了什么 | `bundles/*.yaml` 里 `sensor.*` 行；契约在 `lca/plugins/perceive/` |
| clock 怎么感知 | `lca/layer1_cognitive/sensors/clock.py` |
| 工具面对模型是什么 | `lca/plugins/tools/<name>.py`（Consumer） |
| 工具背后的世界能力 | 对应缝的 Definition + Provider |
| Protocol | `lca/contracts/protocols/` |
| 这次部署启用了谁 | `profiles/*.yaml` → 它引用的 bundles + patch |
| 依赖图 | `lca-ops inspect-tree`（Loader 真图） |

投稿插件与实现类一对一、同名、不同层：`plugins/perceive/clock.py` 挂钩，`layer1_cognitive/sensors/clock.py` 实现。禁止第三处再列 `clock`。

## 放弃的方案

- **整仓搬 DSH**（一 npm 包一插件、declaration merging、事件瀑布驱动控制）。循环闭集与五层单向是 LCA 的地基；Python 的模块与类型注解已经是插件系统。抄包布局会换一种不可读。
- **只把 YAML / meta 写圆**。不改 boot、不改 Composer，inject 仍是注释，名单仍在 L4。
- **第三套 PluginManifest / PrimitiveManifest**。宪法已否决。契约 = Protocol + 签名 + 群服务。
- **YAML 重复 inject**。装箱单与依赖图必须单一事实源：前者是 entry 列表，后者是签名。
- **把六步循环插件化**。C1 / C6。
- **每个投稿升格为缝**。缝是「合同 + 多实现 + 消费者」三件套；clock 没有第二套 provider。
- **预防性拆包**。只有第二套 Provider 或第二套 Consumer 出现才拆文件。

## 后果

- 加一个 sensor / gate / tool：一个实现类、一个 `@plugin` 函数、bundle 一行。零 Composer 编辑。
- 读 bundle 能回答「启用了什么」；读插件函数能回答「挂到谁、贡献什么」；读群服务能回答「如何排序 / 缺省」。三页互补，不再重叠。
- `seam_definitions` 批量子弹不再必要：每个 Definition 自己 `provide` 自己的 key。`gate.workspace-agent` 消失，链由 `GateService.assemble()` 按 slot 排出。
- `AgentComposer` / `TeamComposer` 已删除；闭合入口是 `spawn_agent` / `spawn_team`。
- Perceive / Gate 群服务已落地；sensor / gate 插件 `add()`，不再 `provide("sensor.*")` / `gate.workspace-agent`。
- 仍待本 ADR 收尾：`boot_entries` 改走 Fiber inject；body / stop_rule / hook 等单钥匙收成群服务；签名即依赖的 `@plugin`。
- 必须能验证：`spawn.py` 无贡献 id 名单；disable 某一 sensor 后 Hub 不含它；缺 `perceive` / `gates` 群服务则 spawn 失败。
