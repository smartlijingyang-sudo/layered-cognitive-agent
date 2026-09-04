# Agent Note: EventBus 链路贯通 —— sink 派发 + pipeline 装载 + 集成修补

Status: implemented(2026-09-03)

## Problem

ADR-0183 的 12 PR 中,前 4 个 PR(骨架 + 单 SSOT 链)由 `0e71f6bb` 落地。剩余 8 个 PR 由 10 个并行 subagent 实现并通过各自门禁,但散落的多处补漏需要收口:

- `EventBus.register_pipeline` 仅装 hook,不挂 sink —— E2E 跑通靠手工 `bus.subscribe + build_record` 接线,非声明式
- `apply_pipeline` 实例化了 sink 但未挂到 bus,publish 期间派发链路断开
- `tests/architecture/test_event_bus_invariants.py` I-FW-BUS-2 / BUS-4 两个守护对 PR-7 的 `pipeline_loader.py bus.subscribe(` 与 `profiles/event-pipeline/web-standard.yaml` 自观察 hook 的 `emit_event` 配置产生误报
- `lca/plugins/transport/webserver/server.py` 未挂 `TraceIdMiddleware`(PR-12 跨文件债)
- `_spine_payload` 缺 `category` 字段触发 mypy 误报(pydantic before-validator 已填)

## Decision

最小改动收口,让 publish → SpineSink → spine.jsonl 走框架原生路径,并修两个架构测试误报。

### 1. bus 增 `mount_sink` + `_dispatch_sinks`(FD-1)

`lca_kernel/events/bus.py`:

- 新 `self._sinks: dict[str, tuple[SinkBackend, FailureSemantics]] = {}`
- 新 `mount_sink(sink_id, backend, *, failure=FAIL_FAST)` 方法
- 新 `_dispatch_sinks(payload, ref)` 私有方法:`build_record(payload, ref)` → `backend.append(record)`;失败按 `failure` 处理(FAIL_FAST 上抛,CONTAINED 记日志)
- `publish()` 在 ref 构造后、`_fanout` 前调 `_dispatch_sinks`(FD-1 先于 FD-2 consumer,见 ADR-0183 §3.1 流程图)

### 2. `register_pipeline` 与 sink 装载分离(生产迁移期安全)

**关键设计**:`register_pipeline` **不**挂 sink,只装 hook。原因:生产 boot 走 `register_pipeline_once(EventBus.default(), pipeline)`,若它挂 sink 则与既有 FileSink 形成 `<run_id>.spine.jsonl` 双写者(迁移期危险,需等 21 publisher 全迁 bus 后再切)。完整声明式装配走 `apply_pipeline(bus, pipeline)`,它在原 hooks + consumer_rules 之外,新增 `bus.mount_sink(spec.id, instance, failure=spec.failure)` 一行。

E2E 测试由「`_wire_sink` 手工 subscribe + build_record」改为「`bus.mount_sink` 命令式装载」,tripwire 测试翻转:登记「register_pipeline 不挂 sink」的**意图性**(COMPAT delete-when 21 publisher 全迁后改为 apply_pipeline),并新增正测试 `test_apply_pipeline_mounts_sinks_declaratively` 证明完整声明式链路。

### 3. 架构测试误报修正

`tests/architecture/test_event_bus_invariants.py`:

- I-FW-BUS-2 白名单追加 `lca/harness/profile/pipeline_loader.py`(框架装配,合法 subscribe 装配点)
- I-FW-BUS-4 重写为语义扫描:`yaml.safe_load` → 仅检查 `consumer_rules[].prefix` 与 `events[].category`,不再用 rg 文本扫。自观察 hook 的 `config.emit_event*` 是**发射**配置,不判违规

### 4. TraceIdMiddleware 接入 server.py

`lca/plugins/transport/webserver/server.py:setup` 在 routes 安装之后、`make_lifespan` 之前,新增一行 `install_trace_middleware(app)`,完成 PR-12 跨文件债。

### 5. E2E 类型卫生

`_spine_payload(seq)` 显式 `category=CAT`(pydantic before-validator 已填,但 mypy 不透过 validator 静态分析);`spine_sink` fixture 返回类型由 `SpineSink` 改为 `Iterator[SpineSink]`(pytest yield 风格);`Iterator` 从 `collections.abc` 导入。

## 影响面

| 文件 | 改动 |
|---|---|
| `lca_kernel/events/bus.py` | +`mount_sink` / `_dispatch_sinks` / `self._sinks`;publish 调 sink 派发 |
| `lca/harness/profile/pipeline_loader.py` | `apply_pipeline` 增 `bus.mount_sink` 调用 |
| `tests/architecture/test_event_bus_invariants.py` | BUS-2 白名单 +1;BUS-4 改 yaml 语义解析 |
| `tests/integration/test_event_bus_e2e.py` | `_wire_sink` 改 `mount_sink`;tripwire 翻转;新增 apply_pipeline 正向测试;类型卫生 |
| `lca/plugins/transport/webserver/server.py` | 接入 `install_trace_middleware` |

不改:`EventMechanism`(继续双轨)、21 个 publisher(后续 PR-8/9/10 收口)、`FileSink`(生产 live writer 路径不动)。

## 验收

| 检查 | 结果 |
|---|---|
| `uv run ruff check` 我改的 5 文件 | All checks passed |
| `uv run ruff format --check` | 5 files left unchanged |
| `uv run pytest tests/lca_kernel/events/ tests/integration/test_event_bus_e2e.py tests/architecture/test_event_bus_invariants.py tests/architecture/test_status_ssot_invariants.py tests/architecture/test_spine_record_single_builder.py tests/harness/test_pipeline_loader.py tests/integration/test_webserver_trace_isolation.py tests/runtime/test_runtime_loop_exception_path.py tests/runtime/test_envelope_emitter_binding.py tests/runtime/test_reducer.py tests/integration/test_loop_cursor_wiring.py tests/integration/test_no_dual_sink.py tests/observability/loop_cursor/` | **405 passed, 2 xfailed**(xfail = PR-9 cursor 直写债 4 处 + PR-4 legacy reader 104 处债,均带 delete-when) |
| `uv run mypy` 我改的 3 文件 | 0 新错(只剩与本 PR 无关的预存 lca/* 错误) |

## delete-when / 后续债

| 路径 | 触发删除条件 |
|---|---|
| `register_pipeline` 与 sink 装载分离 | 21 个 publisher 全部走 `bus.publish` 后,生产 boot 改用 `apply_pipeline`;改用即删 COMPAT 块 |
| `lca/infrastructure/observability/loop_cursor/` 内 4 处 `spine.append` 直写 | PR-9 follow-up sweep(已在 xfail 跟踪) |
| `events.jsonl` legacy reader 104 处 | PR-4 follow-up sweep |
| `EnvelopeEmitter` Protocol 的 `emit_reducer_apply_*` | PR-8 已迁 EventBus 直发,`SpineEnvelopeEmitter` 这两个方法是死代码 |
| Category 闭集扩展(`event.bus.dispatch.*`) | PR-12 自观察事件当前用 string category + DISPATCH_SELF_OBSERVATION_CATEGORIES 白名单;扩展需新 ADR |
