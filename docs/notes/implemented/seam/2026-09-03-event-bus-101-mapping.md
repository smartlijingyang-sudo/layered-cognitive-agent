# Agent Note: ADR-0183 附录 A — 101 category namespace 重映射

Status: implemented(2026-09-03)

## Problem

ADR-0183 的三个 PR 需要 101 个 category 的完整清单作为单一参照:

- **PR-3** 把部分 prefix 的 plane 归属重映射(`Plane` 扩 CONTROL / DERIVED),并给每个 EP 绑定类型化 payload
- **PR-6** 把 yaml 逐 category 的 `subscribers:` 列举折叠为 Pipeline `consumer_rules:` 前缀规则,授权集合必须逐 category 等价
- **PR-7** 之后的 producer 收口(PR-8/9/10)按本清单核对 publisher 鉴权

ADR §10 指定本附录承载该清单。清单以两份注册表 yaml 的实测值为真值;PR-3+PR-6 合入后,本附录 A.1/A.3 仍为唯一参照,未出现重命名/归并/删除事件,A.6 未定稿项已转 A.7 实施态记录。

## Decision

### A.1 清单来源(2026-09-03 实测)

| 注册表 | 路径 | category 数 |
|---|---|---:|
| spine 注册表 | `lca_kernel/events/config/observability/spine.yaml` | 100 |
| team 注册表 | `lca_kernel/events/config/business/team.yaml` | 1 |
| 合计 | | **101** |

事实(2026-09-03 落地态):

- ADR §1.3 写的 `business/team.yaml` 是 `lca_kernel/events/config/` 之下的相对路径。
- 101 个 `payload_class` 已全部必填:99 个 = `lca_kernel.events.payloads_spine.SpineEventPayload`(单类共用);2 个 = `lca_kernel.events.payloads.TeamDelegationCacheHit`(`spine.team.delegation.cache_hit` 与 `team.delegation.cache_hit`)。
- `EventSpec.fields` 类型仍为 `dict[str, str]`(`lca_kernel/events/registry.py`);PR-3 仅落地 `FieldType` enum + `EventPayload` 基类 + `PayloadSchemaError`,未把 `fields` 由 `str` 升级为 `FieldType` 枚举值——本附录 A.7 记录为遗留债。

### A.2 prefix 分布(实测,优先于 ADR §1.4)

| prefix | 数量 | plane(实测) | publisher(实测,`lca.plugins.events.publishers.` 前缀省略) |
|---|---:|---|---|
| `spine.cognition` | 16 | OBSERVABILITY | `spine_reflector_cognition.plugin.ReflectorClass` |
| `spine.phase` | 12 | OBSERVABILITY | `spine_reflector_phase.plugin.ReflectorClass` + `spine_loop_cursor.plugin.LoopCursorPlugin` |
| `spine.control` | 11 | STRUCTURAL | `spine_reflector_control.plugin.ReflectorClass` |
| `spine.writable` | 7 | OBSERVABILITY | `spine_reflector_writable.plugin.ReflectorClass` + `spine_writable_matrix.plugin.WritableMatrixPlugin` |
| `spine.team` | 7 | STRUCTURAL | `spine_reflector_team.plugin.ReflectorClass` |
| `spine.runtime` | 6 | OBSERVABILITY | `spine_reflector_runtime.plugin.ReflectorClass` |
| `spine.perception` | 6 | OBSERVABILITY | `spine_reflector_perception.plugin.ReflectorClass` |
| `spine.body` | 5 | OBSERVABILITY | `spine_reflector_body_llm.plugin.ReflectorClass` |
| `spine.llm` | 5 | OBSERVABILITY | `spine_reflector_body_llm.plugin.ReflectorClass` |
| `spine.kernel` | 5 | OBSERVABILITY | boot 2 个 = `spine_reflector_kernel_loop.plugin.ReflectorClass`;run 3 个 = `spine_reflector_transport.plugin.ReflectorClass` |
| `spine.phase_graph` | 4 | OBSERVABILITY | `spine_reflector_phase_graph.plugin.ReflectorClass` |
| `spine.agent` | 3 | OBSERVABILITY | `spine_reflector_agent_spawn.plugin.ReflectorClass` |
| `spine.boot` | 3 | STRUCTURAL | `spine_reflector_boot.plugin.ReflectorClass` |
| `spine.transport` | 3 | OBSERVABILITY | `spine_reflector_transport.plugin.ReflectorClass` |
| `spine.agent_loop` | 2 | OBSERVABILITY | `spine_reflector_agent_spawn.plugin.ReflectorClass` |
| `spine.exception` | 2 | OBSERVABILITY | `spine_reflector_runtime.plugin.ReflectorClass` |
| `spine.lifecycle` | 1 | OBSERVABILITY | `spine_reflector_runtime.plugin.ReflectorClass` |
| `spine.loop` | 1 | OBSERVABILITY | `spine_reflector_kernel_loop.plugin.ReflectorClass` |
| `spine.perceive` | 1 | OBSERVABILITY | `spine_reflector_phase.plugin.ReflectorClass` + `spine_loop_cursor.plugin.LoopCursorPlugin` |
| `team.delegation` | 1 | STRUCTURAL | `delegation_cache.plugin.DelegationCachePlugin` |

plane 小计:OBSERVABILITY 79,STRUCTURAL 22(`spine.control` 11 + `spine.team` 7 + `spine.boot` 3 + `team.delegation` 1)。

与 ADR §1.4 的偏差(本附录以实测 yaml 为准):

- `spine.kernel` 实测 5;ADR §1.4 记 3。差额 = `spine.kernel.run.stop` 与 `spine.kernel.run.cancelled`,yaml 中 publisher 为 `spine_reflector_transport.plugin.ReflectorClass`。ADR §1.4 表合计 99,与总数 101 不符;实测合计 101。
- `spine.loop.fork` 实测 publisher = `spine_reflector_kernel_loop.plugin.ReflectorClass`;ADR §1.4 记 LoopCursorPlugin。
- `spine.perceive.phase.fold` 实测 publisher = `spine_reflector_phase.plugin.ReflectorClass` + `spine_loop_cursor.plugin.LoopCursorPlugin`;ADR §1.4 记 ReflectorCognition。

### A.3 完整 101 category 映射表

**目标处理**取值:**保留** = category 字符串、publisher 授权、consumer 授权集合均不变。两条补充语义:

- **plane 重映射**(ADR §3.7,PR-3):`spine.control.*` → `Plane.CONTROL`;`spine.phase_graph.*` → `Plane.DERIVED`。category 字符串不变。
- **配置折叠**(PR-6):逐 category `subscribers:` 块折叠为前缀规则;每个 category 的 consumer 授权集合必须等价,由 `scripts/verify_consumer_rules_equivalence.py` 守护。

| # | 旧 category | 所属前缀组 | plane(实测) | 目标处理 |
|---:|---|---|---|---|
| 1 | `spine.cognition.brain.perceive.start` | spine.cognition | OBSERVABILITY | 保留 |
| 2 | `spine.cognition.brain.perceive.end` | spine.cognition | OBSERVABILITY | 保留 |
| 3 | `spine.cognition.brain.think.start` | spine.cognition | OBSERVABILITY | 保留 |
| 4 | `spine.cognition.brain.think.end` | spine.cognition | OBSERVABILITY | 保留 |
| 5 | `spine.cognition.brain.gate.start` | spine.cognition | OBSERVABILITY | 保留 |
| 6 | `spine.cognition.brain.gate.end` | spine.cognition | OBSERVABILITY | 保留 |
| 7 | `spine.cognition.critic.eval.start` | spine.cognition | OBSERVABILITY | 保留 |
| 8 | `spine.cognition.critic.eval.end` | spine.cognition | OBSERVABILITY | 保留 |
| 9 | `spine.cognition.reasoner.reason.start` | spine.cognition | OBSERVABILITY | 保留 |
| 10 | `spine.cognition.reasoner.reason.end` | spine.cognition | OBSERVABILITY | 保留 |
| 11 | `spine.cognition.prompt_assembler.assemble.start` | spine.cognition | OBSERVABILITY | 保留 |
| 12 | `spine.cognition.prompt_assembler.assemble.end` | spine.cognition | OBSERVABILITY | 保留 |
| 13 | `spine.cognition.synthesizer.merge` | spine.cognition | OBSERVABILITY | 保留 |
| 14 | `spine.cognition.skill_router.route` | spine.cognition | OBSERVABILITY | 保留 |
| 15 | `spine.cognition.memory.read` | spine.cognition | OBSERVABILITY | 保留 |
| 16 | `spine.cognition.memory.write` | spine.cognition | OBSERVABILITY | 保留 |
| 17 | `spine.phase.perceive.fold` | spine.phase | OBSERVABILITY | 保留 |
| 18 | `spine.phase.think.fold` | spine.phase | OBSERVABILITY | 保留 |
| 19 | `spine.phase.gate.fold` | spine.phase | OBSERVABILITY | 保留 |
| 20 | `spine.phase.remember.fold` | spine.phase | OBSERVABILITY | 保留 |
| 21 | `spine.phase.stop.fold` | spine.phase | OBSERVABILITY | 保留 |
| 22 | `spine.phase.reflect.fold` | spine.phase | OBSERVABILITY | 保留 |
| 23 | `spine.phase.act.fold.start` | spine.phase | OBSERVABILITY | 保留 |
| 24 | `spine.phase.act.fold.end` | spine.phase | OBSERVABILITY | 保留 |
| 25 | `spine.phase.act.fold` | spine.phase | OBSERVABILITY | 保留 |
| 26 | `spine.phase.tool.call.start` | spine.phase | OBSERVABILITY | 保留 |
| 27 | `spine.phase.tool.call.end` | spine.phase | OBSERVABILITY | 保留 |
| 28 | `spine.phase.tool.denied` | spine.phase | OBSERVABILITY | 保留 |
| 29 | `spine.control.dispatch` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 30 | `spine.control.invoke` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 31 | `spine.control.signal` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 32 | `spine.control.approve.request` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 33 | `spine.control.approve.response` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 34 | `spine.control.deny` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 35 | `spine.control.revoke` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 36 | `spine.control.pause` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 37 | `spine.control.resume` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 38 | `spine.control.stop` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 39 | `spine.control.accept` | spine.control | STRUCTURAL | 保留;plane → CONTROL(PR-3) |
| 40 | `spine.writable.step.start` | spine.writable | OBSERVABILITY | 保留 |
| 41 | `spine.writable.step.end` | spine.writable | OBSERVABILITY | 保留 |
| 42 | `spine.writable.segment.start` | spine.writable | OBSERVABILITY | 保留 |
| 43 | `spine.writable.segment.end` | spine.writable | OBSERVABILITY | 保留 |
| 44 | `spine.writable.iteration.halt` | spine.writable | OBSERVABILITY | 保留 |
| 45 | `spine.writable.iteration.closing` | spine.writable | OBSERVABILITY | 保留 |
| 46 | `spine.writable.iteration.close` | spine.writable | OBSERVABILITY | 保留 |
| 47 | `spine.team.casting.started` | spine.team | STRUCTURAL | 保留 |
| 48 | `spine.team.casting.completed` | spine.team | STRUCTURAL | 保留 |
| 49 | `spine.team.casting.failed` | spine.team | STRUCTURAL | 保留 |
| 50 | `spine.team.delegation.issued` | spine.team | STRUCTURAL | 保留 |
| 51 | `spine.team.delegation.completed` | spine.team | STRUCTURAL | 保留 |
| 52 | `spine.team.delegation.cache_hit` | spine.team | STRUCTURAL | 保留 |
| 53 | `spine.team.message.published` | spine.team | STRUCTURAL | 保留 |
| 54 | `spine.runtime.reducer.apply` | spine.runtime | OBSERVABILITY | 保留 |
| 55 | `spine.runtime.checkpoint.create` | spine.runtime | OBSERVABILITY | 保留 |
| 56 | `spine.runtime.resume.start` | spine.runtime | OBSERVABILITY | 保留 |
| 57 | `spine.runtime.resume.end` | spine.runtime | OBSERVABILITY | 保留 |
| 58 | `spine.runtime.event_publisher.publish` | spine.runtime | OBSERVABILITY | 保留 |
| 59 | `spine.runtime.observed` | spine.runtime | OBSERVABILITY | 保留 |
| 60 | `spine.perception.observe` | spine.perception | OBSERVABILITY | 保留 |
| 61 | `spine.perception.attention.focus` | spine.perception | OBSERVABILITY | 保留 |
| 62 | `spine.perception.attention.blur` | spine.perception | OBSERVABILITY | 保留 |
| 63 | `spine.perception.signal.detected` | spine.perception | OBSERVABILITY | 保留 |
| 64 | `spine.perception.fused` | spine.perception | OBSERVABILITY | 保留 |
| 65 | `spine.perception.artifact.built` | spine.perception | OBSERVABILITY | 保留 |
| 66 | `spine.body.tool.execute.start` | spine.body | OBSERVABILITY | 保留 |
| 67 | `spine.body.tool.execute.end` | spine.body | OBSERVABILITY | 保留 |
| 68 | `spine.body.tool.retry` | spine.body | OBSERVABILITY | 保留 |
| 69 | `spine.body.sandbox.enter` | spine.body | OBSERVABILITY | 保留 |
| 70 | `spine.body.sandbox.exit` | spine.body | OBSERVABILITY | 保留 |
| 71 | `spine.llm.call.start` | spine.llm | OBSERVABILITY | 保留 |
| 72 | `spine.llm.call.end` | spine.llm | OBSERVABILITY | 保留 |
| 73 | `spine.llm.stream.token` | spine.llm | OBSERVABILITY | 保留 |
| 74 | `spine.llm.stream.stall` | spine.llm | OBSERVABILITY | 保留 |
| 75 | `spine.llm.request.header` | spine.llm | OBSERVABILITY | 保留 |
| 76 | `spine.kernel.boot.start` | spine.kernel | OBSERVABILITY | 保留 |
| 77 | `spine.kernel.boot.completed` | spine.kernel | OBSERVABILITY | 保留 |
| 78 | `spine.kernel.run.start` | spine.kernel | OBSERVABILITY | 保留 |
| 79 | `spine.kernel.run.stop` | spine.kernel | OBSERVABILITY | 保留 |
| 80 | `spine.kernel.run.cancelled` | spine.kernel | OBSERVABILITY | 保留 |
| 81 | `spine.phase_graph.node.start` | spine.phase_graph | OBSERVABILITY | 保留;plane → DERIVED(PR-3) |
| 82 | `spine.phase_graph.node.end` | spine.phase_graph | OBSERVABILITY | 保留;plane → DERIVED(PR-3) |
| 83 | `spine.phase_graph.edge.transit` | spine.phase_graph | OBSERVABILITY | 保留;plane → DERIVED(PR-3) |
| 84 | `spine.phase_graph.instrument.coverage` | spine.phase_graph | OBSERVABILITY | 保留;plane → DERIVED(PR-3) |
| 85 | `spine.agent.spawn` | spine.agent | OBSERVABILITY | 保留 |
| 86 | `spine.agent.iteration` | spine.agent | OBSERVABILITY | 保留 |
| 87 | `spine.agent.final` | spine.agent | OBSERVABILITY | 保留 |
| 88 | `spine.boot.profile.resolved` | spine.boot | STRUCTURAL | 保留 |
| 89 | `spine.boot.plugin.fiber.spawned` | spine.boot | STRUCTURAL | 保留 |
| 90 | `spine.boot.observability.assembled` | spine.boot | STRUCTURAL | 保留 |
| 91 | `spine.transport.route.enter` | spine.transport | OBSERVABILITY | 保留 |
| 92 | `spine.transport.route.exit` | spine.transport | OBSERVABILITY | 保留 |
| 93 | `spine.transport.sse.publish` | spine.transport | OBSERVABILITY | 保留 |
| 94 | `spine.agent_loop.iteration.start` | spine.agent_loop | OBSERVABILITY | 保留 |
| 95 | `spine.agent_loop.iteration.end` | spine.agent_loop | OBSERVABILITY | 保留 |
| 96 | `spine.exception.caught` | spine.exception | OBSERVABILITY | 保留 |
| 97 | `spine.exception.finally` | spine.exception | OBSERVABILITY | 保留 |
| 98 | `spine.lifecycle.finally` | spine.lifecycle | OBSERVABILITY | 保留 |
| 99 | `spine.loop.fork` | spine.loop | OBSERVABILITY | 保留 |
| 100 | `spine.perceive.phase.fold` | spine.perceive | OBSERVABILITY | 保留 |
| 101 | `team.delegation.cache_hit` | team.delegation | STRUCTURAL | 保留;JournalSink 订阅授权随 PR-4 删 journal sink 移除 |

无**归并**、无**删除**的 category:101 个字符串全部保留。ADR-0183 不含任何 category 改名决定。

### A.4 failure 语义(仅 ADR §3.3 已给定的前缀)

ADR §3.3 Pipeline 示例给出的前缀分配:

| prefix | failure | ADR 依据 |
|---|---|---|
| `spine.llm.` | fail_fast | 模型可见事实必须落盘 |
| `spine.exception.` | fail_fast | 异常事实必须落盘 |
| `spine.writable.` | fail_fast | ADR-0170 关键事实 |
| `spine.cognition.` | contained | 允许部分派生失败 |
| `spine.phase.` | contained | 派生事实 |
| `team.` | contained | 团队委派业务 |
| `spine.`(兜底) | fail_fast | 全部落 `spine-fact-chain` |
| `event.bus.dispatch.*` | 不订阅 | I-FW-BUS-4 |

其余前缀(`spine.body.` / `spine.control.` / `spine.runtime.` / `spine.transport.` / `spine.kernel.` / `spine.boot.` / `spine.agent*` / `spine.perception.` / `spine.perceive.` / `spine.loop.` / `spine.lifecycle.` / `spine.phase_graph.`)的 failure 归属在 PR-6 的 `consumer_rules` 中定稿,由等价性脚本守护;本附录不预填结论。

### A.5 框架新增 category(自观察,随 PR-12 进入落盘链)

| category | payload_class | 用途 |
|---|---|---|
| `event.bus.dispatch.sinks.end` | `lca_kernel.events.payloads.MechanismDispatchEventPayload`(已落地) | 机制自观察 |
| `event.bus.dispatch.consumers.end` | 同上 | 机制自观察 |

这两个 category 构成字符串闭集 `DISPATCH_SELF_OBSERVATION_CATEGORIES`(`lca_kernel/events/payloads.py`),不在 `Category` 枚举内、不进注册表鉴权矩阵;流转走 `EventBus._emit_self_observation` 内部路径。I-FW-BUS-4:Pipeline `consumer_rules` 不订阅 `event.bus.dispatch.*`,架构测试守护。

### A.6 实施态记录(2026-09-03)

PR-3+PR-6 落地后,本附录 A.6 原"未定稿项"转实施态记录:

- **namespace 重命名**:101 个 category 字符串全部保留,无重命名/归并/删除事件。`spine.team.delegation.cache_hit` 与 `team.delegation.cache_hit` 双登记按 A.3 表维持并存。
- **类型化 payload 子类命名**:仅落地 3 个具体类(`lca_kernel.events.payloads_spine.SpineEventPayload`、`lca_kernel.events.payloads.TeamDelegationCacheHit`、`lca_kernel.events.payloads.MechanismDispatchEventPayload`)。其余 99 个 category 共用 `SpineEventPayload` 基类——`bus.publish` 的 schema 校验当前对 99 个 category 仅做 `EventPayload` 基类校验,字段级 `FieldType` 校验未实装。
- **`EventSpec.fields` 由 `dict[str, str]` 升级 `dict[str, FieldType]`**:未落地,列为 A.7 遗留债。

### A.7 遗留债(2026-09-03)

| 债 | delete-when |
|---|---|
| `EventSpec.fields` 仍为 `dict[str, str]`,非 `FieldType` 枚举 | 101 个 category 字段类型全部升级为 `FieldType` 枚举值,且 `lca-ops validate-events web-standard` exit 0 |
| 99 个 category 共用 `SpineEventPayload` 基类,字段级 `FieldType` 校验未实装 | `bus.publish()` pre_dispatch hook chain 接入 `PayloadSchemaHook` 完整字段校验,`FieldType` 不符抛 `PayloadSchemaError` |
| `spine.team.delegation.cache_hit` 与 `team.delegation.cache_hit` 双登记 | 后续 ADR 决定归并或保留;本附录不预设 |

## Alternatives considered

1. **沿用 `SpineEventPayload` 单类承载全部 101 个 category** — 当前实现状态。**否决**:ADR-0183 §3.7 要求每个 EP 绑定类型化 dataclass,单类使 `bus.publish` 的 schema 校验失效。
2. **按认知闭集 7 步批量改名** — 需要重命名 101 个 category,破坏 Langfuse/OTel 导出已有的 query 路径。**否决**:保留字符串,只折叠配置与重映射 plane。
3. **在本附录一次性定稿全部前缀的 failure 语义** — 超出 ADR §3.3 已给定的范围,会与 PR-6 的等价性验证脱节。**否决**:只记录 ADR 已给定的前缀,其余留给 PR-6。

## Acceptance criteria

- ✅ `spine.control.*`(11)与 `spine.phase_graph.*`(4)的 plane 重映射生效(PR-3 commit `0e71f6bb`)
- ✅ `scripts/verify_consumer_rules_equivalence.py` 退出码与归档由 PR-6 commit `f8032be0` 维护;本附录 A.3 表中每个 category 的 consumer 授权集合与折叠后的 `consumer_rules` 一致(逐 category 由机械等价性测试守护)
- ✅ 本附录 A.3 表与两份注册表 yaml 逐条一致:101 个,无增、无删、无改名(2026-09-03 实施态确认)
- ⏳ 101 个 category 字段级 `FieldType` 校验见 A.7 遗留债
- ⏳ `lca-ops validate-events web-standard` exit 0 由 main controller 升 Accepted 前复跑

## Risks

1. **实测与 ADR §1.4 存在 3 处偏差**(spine.kernel 计数、spine.loop 与 spine.perceive 的 publisher 归属,见 A.2)。**缓解**:本附录以 yaml 为准;PR-6 合并前由等价性脚本机械复核。
2. **99 个 category 共用单类 `SpineEventPayload`**,PR-3 一次性类型化工作量大。**缓解**:PR-3 按前缀组分批,每批过 `lca-ops validate-events` 后再进下一批。

## delete-when

- ADR-0183 Status 升 Accepted、A.7 全部遗留债 delete-when 触发、A.3 表内容完全落入两份注册表 yaml 与 `lca-ops inspect-pipeline` 输出:本附录转 `archived/`
- 命名空间出现新提案(归并 / 重命名 / 删除):另开 ADR 走原流程,本附录不退
