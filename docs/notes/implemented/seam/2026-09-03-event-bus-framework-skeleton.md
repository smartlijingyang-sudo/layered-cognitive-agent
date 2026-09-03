# Agent Note: 事件总线框架骨架 —— EventBus + 4 hook + Pipeline + 单 SSOT 链

Status: implemented(2026-09-03)

## Problem

ADR-0183(事件总线框架 SSOT,Proposed,2026-09-03)把 10 篇 ADR(0167/0170/0172/0175/0176/0177/0178/0180/0181/0182)合并为单一收敛。其 12 PR 依赖图最底部的"基本框架层"是 PR-1+PR-2+PR-3+PR-4,没有这层,后续 8 个 PR(reducer/cursor/runtime_loop 收口、状态机、trace_id、自观察)无统一基础可迁。

落地范围:
- **新增** `EventBus`(机制壳 + 4 hook + Pipeline 编排),与旧 `EventMechanism` 双轨共存
- **新增** `SinkBackend` Protocol + `SpineSink` 默认实现 + `SpineReader` 唯一读取入口
- **新增** `spine_runtime.build_record(payload, ref)` 统一 record 构造入口,替代旧 `spine_file_sink._build_event_record` 反推路径
- **新增** 5 条架构不变量(I-FW-BUS-1/2/4 + I-FW-SSOT-1 + 部分 I-FW-SSOT-2)的机械守护

## Decision

**双轨过渡,不破旧路径。** EventBus 与 EventMechanism 共存;旧 publisher 仍走 `EventMechanism.default().send(...)`,新机制是未来路径。本 PR 不动 21 个 publisher manifest、不动 reducer 装饰器、不动 cursor / runtime_loop 调用,只把"基本框架"层落地 + 守护测试。

### 框架边界

| 模块 | 职责 | 谁可改 |
|---|---|---|
| `lca_kernel/events/bus.py` `EventBus.publish / subscribe / register_pipeline` | producer 唯一入口 / consumer 唯一入口 / 装载声明式编排 | 框架 |
| `lca_kernel/events/hooks.py` 4 hook Protocol | `PreDispatchHook` / `SpecResolverHook` / `PostDispatchHook` / `FailureHook` | 框架定协议,plugin 写实现 |
| `lca_kernel/events/pipeline.py` `Pipeline / HookSpec / SinkSpec / ConsumerRule` | 声明式 YAML 编排 | Profile/Bundle 作者 |
| `lca_kernel/events/sinks/spine_sink.py` `SpineSink(SinkBackend)` | 事实链 SSOT 默认实现 | 框架定 to_dict() 字节布局,plugin 可换 backend |
| `lca_kernel/events/reader.py` `SpineReader` | 事实链唯一读盘入口 | 框架 |
| `lca_kernel/events/spine_runtime.py` `build_record` | 单一 record 构造入口 | 框架 |

### 失败语义

- `subscribe(failure=FAIL_FAST)` → consumer 抛错直接上抛给 publisher
- `subscribe(failure=CONTAINED)` → consumer 抛错被吞,继续后续 consumer(默认,与旧 `EventMechanism._dispatch_subscribers` 行为一致)
- `failure_hook` 返 `FailureAction.RETHROW` 时整条 publish 链上抛
- sink-like subscriber(subscribe with `FAIL_FAST`)是事实链的"必须落盘"语义承载者

### 不变量(I-FW-BUS-1/2/4 + I-FW-SSOT-1)

| ID | 内容 | 守护测试 |
|---|---|---|
| I-FW-BUS-1 | producer 唯一入口 = `EventBus.publish`;reducer/cursor/runtime_loop 禁直写 spine / 直调 sink | `test_i_fw_bus_1_no_direct_spine_append_in_runtime` + `test_i_fw_bus_1_no_direct_sink_call_in_runtime`(cursor 直写 5 处暂标 xfail,等 PR-9 收口) |
| I-FW-BUS-2 | consumer 唯一入口 = `EventBus.subscribe(*, failure=...)`;不允许 `.subscribe(` / `.register_sink(` 在 EventBus 框架外使用 | `test_i_fw_bus_2_subscribe_outside_framework_blocked` |
| I-FW-BUS-4 | 业务不订阅 `event.bus.dispatch.*`(PR-12 自观察事件) | `test_i_fw_bus_4_no_business_subscribe_dispatch_event` |
| I-FW-SSOT-1 | `<run_id>.spine.jsonl` 唯一 SSOT;`SpineSink` 唯一写、`SpineReader` 唯一读 | `test_i_fw_ssot_1_no_legacy_events_jsonl_writer` + `test_i_fw_ssot_1_spine_jsonl_writer_is_single`(legacy reader 105 处暂标 xfail,等 PR-4 follow-up sweep) |

### 与现有 ADR 的吸收

- ADR-0167 spine SSOT → 字节布局由 `SpineEventRecord.to_dict()` 唯一决定
- ADR-0177 `EnvelopeEmitter` → Protocol 升级为 `EventBus[T]` + 4 hook Protocol(本 PR 留骨架,具体 emit_* 绑定留 PR-10)
- ADR-0181 publishers/subscribers → 22 manifest 双轨中保留 EventMechanism 入口,EventBus 是新增并行入口
- ADR-0182 EventMechanism 框架化 D2/D3/D7 → D2 (FieldType 字符串)暂未落地,留 PR-3;D3(自指派)改走 hook 协议,留 PR-12;D7(yaml 前缀)暂未落地,留 PR-6

## Alternatives considered

1. **一次性替换 EventMechanism** — 21 publisher + 9 真订阅方同步迁,改动面太大。旧机制已承载生产事件链路,合并风险不可控。**否决**,留双轨过渡。
2. **在旧 mechanism.py 内新增 EventBus,不新建模块** — EventMechanism 是 frozen 的 SSOT,新机制要明确"新 SSOT",物理分离更易守护(测试可定位"`lca_kernel/events/bus.py` 是框架面,`mechanism.py` 是兼容面")。**采纳**,物理分离。
3. **`build_record` 放在新模块** — ADR §3.5 写"框架自带",但旧 spine_runtime.py 已含 `SpineEventRecord`。物理上追加 `build_record` 到同文件避免拆分 `to_dict()` 配套(同 dataclass 同 lifecycle)。**采纳**,加在 `spine_runtime.py` 末尾。
4. **不写架构不变量测试** — 5 条不变量是关键门禁,机械守护是唯一可信屏障。**采纳**,本 PR 加 8 个测试 + 2 个 xfail(已知债)。

## delete-when / 兼容性

| 路径 | 兼容窗口 | 删除触发器 |
|---|---|---|
| `lca_kernel/events/mechanism.py` `EventMechanism.send / subscribe / register_sink` | 本 PR → PR-7 装载 Pipeline 之后 | `rg "EventMechanism" lca/ lca_kernel/ tests/` = 0(允许 archive/ 与 tests/architecture/ 负向断言) |
| `lca/infrastructure/observability/spine/event_spine.py` `append` + `bind.py:80 append` | 本 PR → PR-9 cursor 收口 | `rg "def append" lca/infrastructure/observability/spine/event_spine.py lca/infrastructure/observability/loop_cursor/bind.py` = 0 |
| `lca/plugins/events/sinks/spine_file_sink/_build_event_record` + 2 处 `except ValueError` | 本 PR → PR-5 record 单一入口 | `rg "_build_event_record" lca/` = 0 且 `rg "except ValueError" lca/plugins/events/sinks/` = 0 |
| `events.jsonl` legacy reader 全仓(105 处) | 本 PR → PR-4 follow-up sweep | `rg "events\.jsonl" lca/ lca_kernel/` = 0(允许负向断言与 tests/fixtures) |
| `TraceContextHook` / `MechanismDispatchObserver` stub | 本 PR → PR-12 | trace_id contextvars 注入 + 自指派观察事件 |

## 落地清单

| 文件 | 操作 | 行数 |
|---|---|---|
| `lca_kernel/events/bus.py` | 新建 | 331 |
| `lca_kernel/events/hooks.py` | 新建 | 197 |
| `lca_kernel/events/pipeline.py` | 新建 | 202 |
| `lca_kernel/events/sinks/__init__.py` | 新建 | 45 |
| `lca_kernel/events/sinks/spine_sink.py` | 新建 | 124 |
| `lca_kernel/events/reader.py` | 新建 | 94 |
| `lca_kernel/events/spine_runtime.py` | 追加 `build_record` + `SpineEventRecord.from_dict` | +86 |
| `tests/lca_kernel/events/test_event_bus.py` | 新建 | 28 测试 |
| `tests/architecture/test_event_bus_invariants.py` | 新建 | 8 测试(6 passed + 2 xfailed) |

测试: `34 passed, 2 xfailed`(`uv run pytest tests/lca_kernel/events/test_event_bus.py tests/architecture/test_event_bus_invariants.py -v --no-cov`)。

ruff / format / mypy: `All checks passed!`(mypy 仅 pre-existing 错,与本 PR 新增文件无关)。

## 后续 PR 触发器

- **PR-7(SinkBackend + Profile 装载 Pipeline)**:本 PR 的 Pipeline dataclass + HookSpec/SinkSpec/ConsumerRule 已就绪,PR-7 只需加 `pipeline_loader.py` 装载段到 Profile
- **PR-5(record 单一入口)**:本 PR 的 `build_record` 已就绪,PR-5 只需删 `spine_file_sink._build_event_record` + 2 处 `except ValueError`,并让 `spine_chain_sink` / `spine_file_sink` 改调 `build_record`
- **PR-6(yaml 前缀规则)**:`ConsumerRule` dataclass 已就绪,本 PR 测试已覆盖 `test_consumer_rule_matches_prefix`,PR-6 只需把 yaml 100 处 `subscribers:` 折叠为前缀规则 + 删 `default_subscribers:` 死配置
- **PR-12(trace_id + 自观察)**:`TraceContextHook` / `MechanismDispatchObserver` stub 已就绪,PR-12 启用 contextvars 注入 + 自指派观察事件
