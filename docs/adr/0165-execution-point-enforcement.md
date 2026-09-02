# ADR-0165: Execution Point 强制织入、零字段声明、自发现、Source Trace

- 状态: Accepted（原 ADR-0165-execution-point-enforcement；编号并入 0165 系列；SSOT 表述见 [ADR-0167](0167-spine-ssot-and-step-materialization.md)）
- 日期: 2026-09-01
- 作者: coding-agent
- 扩展: [ADR-0165](0165-event-spine-unified-log.md)（Event Spine stub）
- **耐久 SSOT / journal 物化 / Model-visible 布局: [ADR-0167](0167-spine-ssot-and-step-materialization.md)**
- 相关: ADR-0164(step-tree),ADR-0096(Journal Protocol Layer 一切插件化),ADR-0112(webserver-4-routes-plugin),ADR-0119(webserver-as-plugin),ADR-0115(K1-K8)
- spec: `docs/superpowers/specs/2026-09-01-spine-execution-points-design.md`

## 一句话

LCA 在 ADR-0165 把"日志"从业务方主动调用改成框架自动触发后,**还缺四个强制度的承诺**:(1) 哪些执行点必须埋? —— **EXECUTION_POINTS 白名单**;(2) 业务方不写一行代码,所有事件字段**从 signature / runtime / context / manifest 反射派生**;(3) edge case **不可枚举**,异常时通过三层发现机制**自增长**;(4) 每个执行点**携带源代码位置 + 调用栈 + locals 快照**,让 source-level trace 在生产事故排查里可用。

## 背景

ADR-0165 的三个未充分回答的硬缺口 + 你追问引出的三个新承诺:

| # | 缺口 | 来源 |
|---|---|---|
| 1 | 没有**执行点白名单** —— 哪些点必须埋?散落 ADR 行文 | ADR-0165 留下 |
| 2 | 没有**织入主路径** —— 装饰器 vs effect 二选一不强制 | ADR-0165 §三路径 A/B 模糊 |
| 3 | 没有**build-time hard fail 校验** —— 只能事后 grep | ADR-0165 §不变量 C-new1/2 缺执行 |
| 4 | 业务方不愿手写埋点字段;要求**全自动** | 用户追问 |
| 5 | edge case 不可枚举,要求**自发现**环境 | 用户追问 |
| 6 | spine 内部 monolith 6 个反射器,**违反 LCA plugin 原则** | 用户追问 |
| 7 | 缺 source-level 维度(文件/行/变量) —— trace 才有真正排查力 | 用户追问 |

## 决策

### D1-D11(继承 ADR-0165 + 强化,见 spec § 1)

EXECUTION_POINTS 白名单(`spine/manifest.py`,~50 项覆盖 10 个执行层),5 层 build-time hard fail 校验:L1 registry 完整 / L2 wrap_fn 绑定 / L3 phase graph runnable 已包 / L4 importlinter `business-event-isolation` / L5 每个 EP 一个测试。

### D9 — 事件是 stateful claim 不是 log

每个事件是"frame N 上的事实 M 发生了",而非"对象 call 了 spine"。事件必含 `sequence` / `epoch` / `causality_id` / `prev_event_hash`,让事件本身可独立审计。

### D10 — outcome 是 enum 不是 bool

`success / failure / timeout / cancelled / rejected / retrying / partial / exhausted / void`。

### D11(双轴) — 全自动字段 + 自发现 case

**Part A** 业务方零字段声明。所有字段从四类信号源自动派生:
- **TypeAnnotation** —— `inspect.signature` / `get_type_hints`
- **运行时观察** —— return type / 异常 type / 帧 inspect
- **ContextVar / framework 层** —— `BudgetContext` / `CircuitBreakerRegistry` / `FrameworkObserver`
- **Plugin Manifest** —— 仅 `tiebreak_rule` / `policy_id`(真·领域知识,plugin 作者本来就要写)

**Part B** edge case 不列举,三层发现:
- **Layer-A** 已知异常(BUILTIN_MAP ~60 stdlib 类型)→ typed event
- **Layer-B** 不变量违例检测(8 类 detector)→ AnomalyDetected
- **Layer-C** open-domain 兜底 → `UnclassifiedError` + 自动建索引;3 次重复后自动建议入 BUILTIN_MAP

### D12 — spine 内部 18+ plugin 化(可插拔 spine)

放弃 `lca/infrastructure/observability/spine/instrumentation/` 单包 6 反射器 monolith。每个反射器 / classifier / deriver / sink / wrap 都是 `@plugin`(`lca/plugins/observability/spine/` 下)。

完整 18 plugin 表格:

| Plugin ID | Layer | 提供 |
|---|---|---|
| `spine.core` | L2 | `event_spine`, `spine_context` |
| `spine.emit_pipeline` | L1 | `emit_pipeline` |
| `spine.reflector.signature` | L0 | `field_producer.signature` |
| `spine.reflector.context` | L0 | `field_producer.context` |
| `spine.reflector.runtime` | L0 | `field_producer.runtime` |
| `spine.reflector.source` | L0 | `field_producer.source` |
| `spine.classifier.exception.builtin` | L0 | `field_producer.classifier_builtin` |
| `spine.classifier.exception.unclass` | L0 | `field_producer.classifier_unclass` |
| `spine.spantree` | L0 | `field_producer.spantree` |
| `spine.deriver.anomaly` | L0 | `field_producer.anomaly` |
| `spine.deriver.step_tree` | L0 | `step_tree` |
| `spine.deriver.narrative` | L0 | `narrative` |
| `spine.deriver.graph` | L0 | `graph` |
| `spine.deriver.live_tail` | L0 | `live_tail` |
| `spine.sink.file` | L0 | `file_sink` |
| `spine.sink.console` | L0 | `console_sink` |
| `spine.wrap.ctx_effect` | L0 | `ctx_effect_wrap` |
| `spine.wrap.ctx_intercept` | L0 | `ctx_intercept_wrap` |
| `spine.wrap.assembler` | L0 | `assembler_wrap` |

Profile 决定装配(`profiles/web-standard.yaml` / `profiles/oii-debug.yaml` / `profiles/benchmark.yaml`)。

### D13 — Source-level trace(文件 + 行号 + 函数 + 变量值)

每个 `*.start` 事件必含:
- `source_location`: `{file, line, function, class_name, method_qualifier}` —— `inspect.currentframe().f_back` + `co_qualname`
- `call_frames`(10 帧):`{file, line, function, local_var_keys}`
- `locals_snapshot`:`{pre_call: dict[key→repr(value)]}`,截断 4KB、256 char per value、secret auto-redact、不可 repr → `<unreprable:ClassName>`

每个 `*.end` 事件含 `locals_diff`:`{diff_added, diff_changed, diff_removed}`。

`lca-ops journal trace <run_id> --locals` 直接在 trace 输出 4 列:ep / source / call_frames / locals。

## 不变量(I1-I17)

| ID | 内容 | 验证 | PR |
|---|---|---|---|
| I1-I8 | 继承 ADR-0165 + 新增 I8(EXECUTION_POINTS close set) | importlinter + 5 层 | PR-5、PR-3 |
| I9 | 业务代码只能 `import EventSpine` + `emit_event()` helper,不进 deriver | Layer-4 | 持续 |
| I10 | O_APPEND 原子;单事件 ≤ 4KB | FileSink 单元 | PR-1 |
| I11 | deriver recursion depth ≤ 8 | FD-2 自检 | PR-2 |
| I12 | 事件字段必填;`auto_source ∈ {signature, runtime, context, framework_observer, plugin_manifest_decl}` —— `manual` 不允许(除 `tiebreak_rule`/`policy_id`)| FieldSourceRule | PR-7 |
| I13 | start → N×progress → end 严格链 | PhaseMachine | PR-7 |
| I14 | outcome ≠ success 时 `failure_envelope` 必全(含 `what_was_tried` / `what_was_NOT_tried` / `recoverable` / `retry_recommended`)| EnvelopeCompleteness | PR-7 |
| I15 | 未列举 case 必须自动被 UnclassifiedError 兜底 + 全 context 保留 | EdgeCaseDiscovery | PR-7 |
| I16 | AnomalyDeriver 必订阅 + UI 默认显示 anomaly banner | AnomalyDetector plugin | PR-7 |
| I17 | 每个 `*.start` 必含 `source_location` / `call_frames` / `locals_snapshot`;缺则 fail-fast | SourceAttacher plugin | PR-9 |

## 决策汇总

| 决策 | 旧 | 新 | 影响 |
|---|---|---|---|
| 织入主路径 | decorator + effect 并列 | effect(ctx.effect / ctx.intercept / assembler wrap)为主 | 业务方零改动 |
| 埋点字段 | 业务方手填 | 框架通过 4 类信号源反射自动派生 | 100% 自动 |
| Edge case 列举 | 12 类表 + I15 hard fail 全列 | 三层发现 + 自增长索引 | 永不沉默 |
| 异常兜底 | 业务方写 `StructuredDiagnostic` | framework `ExceptionClassifier` 通用 | 零业务改 |
| spine 内部结构 | 6 个 monolith 类 | 18 个 plugin(profile 装配) | 全 framework 一致 plugin 模式 |
| trace 维度 | 协议级(ep / span) | + 源码级(file:line:fn + locals repr) | 生产事故排查够用 |

## 实施时间线

9 PR,24-42 天(单线):

```text
PR-1 spine-foundations              (~2-3 天)
PR-2 spine-derivers                 (~3-5 天)
PR-3 spine-execution-points         (~5-7 天,sub-PR 1-4)
PR-4 spine-phase-graph-wrap         (~3-5 天)
PR-5 spine-lint-hardfail            (~3-5 天)
PR-6 spine-orphan-events            (~3-5 天)
PR-7 spine-auto-fields              (~5-8 天)
PR-7.1 spine-auto-fields-wiring     (~2-4 天)
PR-8 spine-plugin-extraction        (~3-5 天,D12 落地)
PR-9 spine-source-attacher          (~3-5 天,D13 / I17 落地)
```

## 兼容性矩阵

| 时点 | events.jsonl 形态 | deriver | 派生文件 | user 行为 |
|---|---|---|---|---|
| 现在 | 4 个并列真值 | LiveTail / StepTree / Writer | 4 文件 | 找问题翻 7 个文件 |
| PR-1 | 新增,4 个并列真值 | LiveTail | 5 文件 | 略缓解 |
| PR-2 | 主真值 + 老 rename 到 legacy | LiveTailDeriver | 3 文件(events.jsonl + journal.json + narrative + graph) | 单文件 view |
| PR-3 | + execution_point 强制织入 | LiveTailDeriver | 同上 | 框架 100% 覆盖 |
| PR-4 | + phase graph node 自动 wrap | LiveTail + AnomalyDeriver | + anomaly_report.json | stuck/cycle 可查 |
| PR-5 | + importlinter hard fail | 同 | 同 | CI 强制 |
| PR-6 | + phase=orphan 显式化 | 同 | 同 | 取消场景可查 |
| PR-7 | + 全自动字段 + 8 类 anomaly | 同 | 同 | 业务方零字段 |
| PR-7.1 | + 反射装配线接入 | 同 | 同 | wrap 自动化 |
| **PR-8** | + 18 plugin 模式替换 monolith | 同 | 同 | framework plugin 一致模式 |
| **PR-9** | + source_location + locals 快照 | 同 | 同 | `trace --locals` 直接看每事件当时的代码与变量 |

## 上线阶段

1. **Stage 1**(单 user internal):PR-1 + PR-2 + PR-3 sub 1-2 → benchmark
2. **Stage 2**(高级 user opt-in):PR-3 完整 + PR-4 → `spine.enabled=true` 开关
3. **Stage 3**(默认):PR-5 + PR-6 + PR-7 → 所有 CI 强制
4. **Stage 4**(默认增强):PR-7.1 + PR-8 → framework 一致 plugin 模式
5. **Stage 5**(强制):PR-9 → 默认 source-level trace 全开

每阶段 7 天 soak,跑 `lca-ops journal sanity`。

## 不做的事

- ❌ 不让业务方手写埋点字段(I12 / D11);所有字段从 reflection / runtime / context / manifest 派生
- ❌ 不允许业务方写 `@declarative_emit` / `@instrument` / raise `StructuredDiagnostic`;framework wrap 全包
- ❌ 不让 profile 写 payload schema;profile 只声明 expected behavior
- ❌ 不让 spine 子系统是 monolith;每个部件都是 plugin(§ 7.6 / D12)
- ❌ 不在 `lca/infrastructure/observability/spine/instrumentation/` 写 6+ 类;PR-8 删
- ❌ 不让业务方关 `spine.reflector.source`(I17 强制);但可配置 `max_locals_bytes` / `redact_patterns`
- ❌ 不在生产默认开 `source_snippet` 原文;OII-Debug profile 开
- ❌ 不做 deep serialization(locals 只 repr + 浅 dict)
- ❌ 不列举 edge case;三层发现机制处置所有异常(I15)
- ❌ 不允许 opt-out;延迟敏感路径走 spine batch/async 模式或改源码

## 替代方案考虑

| 方案 | 否决理由 |
|---|---|
| 业务方手动 emit(原状)| 漏洞源头 |
| `sys.settrace` 全局 | 性能不可控,生产不可用 |
| 只在 SSE flush | 解决 30% 问题 |
| OpenTelemetry 替代 spine | OTel 是外部 sink,不是真值流 |
| 重写 cognition/runtime 为 plugin | 违背 LCA 分层依赖 |
| 装饰器为主 effect 兜底 | 装饰器漏一个就没事件,违反"牢靠" |
| **edge case 列举全**(spec 第一轮)| **不可列举**;违反用户"无法列举完全" |
| **spine 内部 monolith 单包**(spec 第二轮)| **违反 LCA plugin 原则** |
| **trace 仅协议级 ep**(spec 第三轮)| **生产排查缺维度**;用户追问要求 file/line/locals |

## 引用

- spec: `docs/superpowers/specs/2026-09-01-spine-execution-points-design.md`(1811 行,16 节,9 PR 时间线)
- ADR-0165: `docs/adr/0165-event-spine-unified-log.md`(本 ADR 扩展)
- ADR-0164: step-tree;PR-2 用 Deriver 取代 StepGroupedBackend
- ADR-0096: Journal Protocol Layer 一切插件化;本 ADR 让 spine 自己也插件化
- ADR-0112 / ADR-0119: webserver-4-routes-plugin + webserver-as-plugin template;spine plugin 复用此 pattern
- deepseek-harness `core/session` + `AGENTS.md §107` "Model-visible ⟺ logged" —— 本 ADR 翻译为 "执行可见 ⟺ 入 spine + spine 可见 ⟺ plugin 化 + spine 信息 ⟺ 可查询源码位"
