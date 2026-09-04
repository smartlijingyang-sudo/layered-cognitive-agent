# Agent Note: 子 note 3 — emit 入口收口到 1 个 + 删平行 emitter(L4 调用点约束)

Status: implemented

> 根 note 与元决策:[observation-convergence-root.md](../../proposed/seam/2026-09-03-observation-convergence-root.md) / [ADR-0178](../../../adr/0178-observation-control-state-convergence.md)。本 note 承接 L4 调用点约束,扩展 ADR-0177。修法见 [exception-caught-single-emitter.md](../contract/2026-09-03-exception-caught-single-emitter.md)。

## Problem

`exception.caught` EP 有 3 个并行 emitter,签名不一致,各自消费方各走各的:

| # | 入口 | 签名 | payload | 调用点 |
|---|---|---|---|---|
| 1 | `lca.infrastructure.observability.spine.exception_emit.emit_exception_caught` | `(record: ExceptionRecord) -> EventRecord \| None` | `record.asdict()` 全字段 | lifecycle / outcome_projection / instrument_wrap |
| 2 | `lca.plugins.events.publishers.spine_reflector_runtime.emit_exception_caught` | `(boundary: str, exc_type: str, message: str, trace_id: str \| None)` | 4 键裸 dict(无 traceback_text / call_frames / err_kind) | 平行 helper |
| 3 | `EnvelopeEmitter.emit_exception_caught` | 与 #2 同形或转发 record | 把观测职责挂在 envelope Protocol 上 | Protocol + `SpineEnvelopeEmitter` |

后果:

- 4 键 payload < 4 KiB 时 FileSink 不 offload,traceback 不落盘
- `CancelledError` 路径若手写类名,真实异常对象不进入 `exc_to_record`
- Protocol 关键字参数面无法穿过 `ExceptionRecord`,caller 被迫填裸 str
- 加字段时 #2 / #3 与 SSOT 分叉

## Decision

`exception.caught` 只有一个函数入口:`lca.infrastructure.observability.spine.exception_emit.emit_exception_caught(record: ExceptionRecord)`。任何 caller 先经 `lca.contracts.observability.exc_to_record` 归一化。

- `EnvelopeEmitter` Protocol 与 `SpineEnvelopeEmitter` 不含 `emit_exception_caught`。该 EP 携带结构化内容,不属于 envelope 转发(其余方法是 reducer apply / resume / lifecycle finally 等空 envelope)。
- `lca.plugins.events.publishers.spine_reflector_runtime` 不含 `emit_exception_caught`;同模块保留 `emit_exception_finally`(空 envelope)。原位置注释说明 `exception.caught` 走 SSOT emitter。
- `lca/runtime/runtime_loop.py` 两条 `except` 绑定真实异常,走 `exc_to_record(exc, boundary=..., run_id=..., trace_id=...)` + SSOT emitter。`except asyncio.CancelledError as exc` 绑定实例,不手写类名。

FileSink `_FORCE_OFFLOAD_EPS` / sidecar 命名不在本 note 范围。

## Alternatives considered

### Why not 保留 3 个 emitter,只加 lint?

3 个 emitter 功能上不可区分——同一个 EP 同一套 payload schema。保留兼容分支会在加字段时分叉。lint 标记 3 个入口互相打架,不如只留 1 个。

### Why not 把 reflector helper 也走 `exc_to_record`,但保留入口?

`emit_exception_caught(boundary, exc_type, message, trace_id)` 的 4 个 str 参数无法表达 `ExceptionRecord`(11 字段)。保留入口等于把 SSOT 工厂藏在实现里——caller 仍填裸 str,字段缺失仍可能发生。

### Why not 把 `EnvelopeEmitter` 改接收 `ExceptionRecord`?

`EnvelopeEmitter` 的其余方法都是空 envelope。让 Protocol 接收 `ExceptionRecord` 等于再包一层与 SSOT emitter 相同的转发,职责从 envelope 转发变成异常归一化。删除该方法比改签名更干净。

## Consequences

- `def emit_exception_caught` 在 `lca/` 下只有 `exception_emit.py` 一处定义。
- `EnvelopeEmitter` 方法集不含 `exception.caught`;runtime / agent 失败路径直接调 SSOT emitter。
- `runtime_loop` 失败与取消路径的 `exception.caught` payload 含 `traceback_text` / `call_frames` / `err_kind`。
- EventBus catalog 仍登记 `spine.exception.caught`(鉴权面);该 category 的生产写入走 spine SSOT,不经 reflector helper。

## Verification

```sh
uv run ruff check lca/contracts/protocols/runtime/envelope_emitter.py lca/runtime/envelope_emitter.py lca/plugins/events/publishers/spine_reflector_runtime lca/runtime/runtime_loop.py tests/runtime/test_envelope_emitter_binding.py tests/runtime/test_runtime_loop_exception_path.py tests/plugins/events/publishers/test_spine_reflector_runtime.py tests/observability/spine/test_exception_capture.py
uv run pytest --no-cov -q tests/runtime/test_envelope_emitter_binding.py tests/runtime/test_runtime_loop_exception_path.py tests/plugins/events/publishers/test_spine_reflector_runtime.py tests/observability/spine/test_exception_capture.py tests/observability/test_observation_ssot_regression.py
```

回归锁:

- `tests/observability/spine/test_exception_capture.py::test_emit_exception_caught_has_single_definition`
- `tests/runtime/test_envelope_emitter_binding.py::test_envelope_emitter_does_not_own_exception_caught`
- `tests/runtime/test_runtime_loop_exception_path.py` — `RuntimeError` / `CancelledError` 路径 payload 含 traceback 字段
- `tests/plugins/events/publishers/test_spine_reflector_runtime.py` — plugin 无 `emit_exception_caught`

## Related

- [observation-convergence-root.md](../../proposed/seam/2026-09-03-observation-convergence-root.md) — 根 note
- [ADR-0178](../../../adr/0178-observation-control-state-convergence.md) — 元决策
- [ADR-0177](../../../adr/0177-envelope-emitter-binding.md) — EnvelopeEmitter binding(本 note 缩小其 surface)
- [exception-caught-single-emitter.md](../contract/2026-09-03-exception-caught-single-emitter.md) — 已定修法
- `lca/contracts/observability/exception_capture.py` — `ExceptionRecord` / `exc_to_record` SSOT
- `lca/runtime/runtime_loop.py` — 失败 / 取消路径
- `lca/plugins/events/publishers/spine_reflector_runtime` — envelope helper,不含 `exception.caught`
- `lca/infrastructure/observability/spine/exception_emit.py` — 唯一 emitter
