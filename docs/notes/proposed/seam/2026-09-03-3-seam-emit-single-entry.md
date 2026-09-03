# Agent Note: 子 note 3 — emit 入口收口到 1 个 + 删平行 emitter(L4 调用点约束)

Status: proposed

> 根 note 与元决策:[observation-convergence-root.md](2026-09-03-observation-convergence-root.md) / [ADR-0178](../../../adr/0178-observation-control-state-convergence.md)。本 note 承接 L4 Protocol 调用点约束,扩展 ADR-0177。

## Problem

`exception.caught` EP 有 **3 个并行 emitter**,签名不一致,各自消费方各走各的:

| # | 入口 | 签名 | payload | 调用点 |
|---|---|---|---|---|
| 1 | `lca.infrastructure.observability.spine.exception_emit.emit_exception_caught` | `(record: ExceptionRecord) -> EventRecord \| None` | `record.asdict()` 全字段(11 键) | `lifecycle.py:123/151`、`outcome_projection.py:363`、`instrument_wrap.py:209/353` |
| 2 | `lca.plugins.observability.spine.reflectors.runtime.emit_exception_caught` | `(boundary: str, exc_type: str, message: str, trace_id: str \| None) -> EventRecord \| None` | 4 键裸 dict(无 traceback_text / call_frames / err_kind) | `runtime_loop.py:281/296` |
| 3 | `lca.contracts.protocols.runtime.envelope_emitter.EnvelopeEmitter.emit_exception_caught` | `(boundary: str, exc_type: str, message: str, trace_id: str \| None)` | 4 键裸 dict(与 #2 同形) | `envelope_emitter.py:88`(`SpineEnvelopeEmitter` 默认实现) |

证据(grep 结果):

```bash
rg "emit_exception_caught" lca/ | wc -l    # 16 处
rg "from .*spine.exception_emit import" lca/ # 4 处(走对的)
rg "from .*reflectors.runtime import.*emit_exception_caught" lca/ # 2 处(runtime_loop.py,走错的)
rg "from .*envelope_emitter import" lca/contracts/  # 1 处(Protocol 自身,签名错误)
```

后果:

- **`runtime_loop.py:281` 的两条 `except` 分支调 emitter #2**:payload = `{boundary, exc_type, message, trace_id}` 4 键 < 4 KiB → `_ATOMIC_THRESHOLD` 不触发 → FileSink 不 offload → **traceback 永久丢失**(用户 2026-09-03 反馈)
- **`runtime_loop.py:281` 还传 `"asyncio.CancelledError"` 硬编码字符串**:实际异常对象绑定为 `exc` 但没用,`type(exc).__qualname__` 应取真实异常类名
- **`EnvelopeEmitter.emit_exception_caught` Protocol 收 4 个 str**:`ExceptionRecord` SSOT 数据结构无法穿过该 Protocol,**Protocol 与 SSOT 类型不一致**——任何 caller 拿到 Protocol 都被迫手填 4 键
- **emitter #3 与 emitter #2 字段完全相同**:完全是平行实现,加字段时分叉概率 100%(这是根 note §"Acceptance criteria" 提到的"historical regression"路径)

## Proposal

按 `docs/notes/implemented/contract/2026-09-03-exception-caught-single-emitter.md` 已定的修法,**完整落地**(该 note 当前只标 `implemented/` 但 git 上 reflector + runtime_loop 还没动):

### PR-1:删 emitter #3

- `lca/contracts/protocols/runtime/envelope_emitter.py` 删 `emit_exception_caught` 方法,docstring 写明该 EP 不属于本 Protocol(异常归一化是观测职责,不是 envelope 转发)
- `lca/runtime/envelope_emitter.py::SpineEnvelopeEmitter` 同步删实现
- ADR-0177 状态改(扩展而非新 ADR)
- `tests/runtime/test_envelope_emitter_binding.py` 删除 `emit_exception_caught` 相关 case

### PR-2:删 emitter #2 + runtime_loop 走 exc_to_record

- `lca/plugins/observability/spine/reflectors/runtime.py` 删 `emit_exception_caught` 函数(连同 `__all__` 条目),保留 `emit_exception_finally`(envelope 无内容)
- `lca/runtime/runtime_loop.py:281/296` 两条 `except` 改走 `exc_to_record(exc, boundary=..., run_id=..., trace_id=...)` + emitter #1
- `asyncio.CancelledError` 分支改成 `except asyncio.CancelledError as exc`,**真实异常绑定**而非硬编码字符串

### PR-3:补 lint 守门(承接 note 5)

- `scripts/check_observation_ssot.py` 加规则:`rg "emit_exception_caught" lca/ | wc -l = 1`(只 emitter #1)
- `scripts/check_runtime_invariants.py`(note 5)加规则:`runtime_loop.py` 必须 `except` 后调 `envelope.emit_exception_caught(exc_to_record(...))`,**不允许裸 dict**

### PR-4:FileSink `_FORCE_OFFLOAD_EPS` + sidecar label 修复

- `_FORCE_OFFLOAD_EPS`(`file_sink.py:47`)保持 `{"exception.caught"}`,**强制 offload**(承接根 note PR-1)
- `offload_sidecar_path`(`file_sink.py:77`)新增 `sidecar_label(record)`:按 offload 原因分流,`exception.caught` 用 `exception_class`,size-driven 用 `execution_point`,缺字段标 `UnnormalizedException`
- 承接根 note `docs/notes/implemented/contract/2026-09-03-exception-caught-single-emitter.md` 已定的 sidecar 命名规则

## Decision criteria

- `rg "emit_exception_caught" lca/` = 1(只 `exception_emit.py` SSOT)
- `rg "from .*reflectors.*emit_exception_caught" lca/` = 0
- `EnvelopeEmitter` Protocol 不含 `emit_exception_caught` 方法
- `runtime_loop.py` 两条 `except` 调 `envelope.emit_exception_caught(exc_to_record(...))`,**真实异常绑定**
- `traces/runs/<run_id>/` 下 `exception.caught` sidecar 必带 `traceback_text` 字段(若 payload > 4 KiB 自动 offload)

## Alternatives considered

### Why not 保留 3 个 emitter,只加 lint?

3 个 emitter **功能上不可区分**——同一个 EP 同一套 payload schema。任何"保留兼容"分支都会在未来加字段时分叉。**只加 lint = 让 lint 标记 3 个 emitter 互相打架**,不如直接删 2 个。

### Why not 把 emitter #2 也走 `exc_to_record`,但保留入口兼容?

`reflectors/runtime.emit_exception_caught(boundary, exc_type, message, trace_id)` 的 4 个 str 参数**无法表达** `ExceptionRecord`(11 字段)。保留入口等于把 SSOT 工厂藏在实现里——`runtime_loop` 仍然填裸 str,字段缺失仍可能发生。

### Why not 把 `EnvelopeEmitter` 改接收 `ExceptionRecord`?

`EnvelopeEmitter` 的 10 个其他方法都是 envelope 无内容(reducer apply / resume / lifecycle finally),`exception.caught` 是唯一携带结构化内容的。**让 Protocol 接收 `ExceptionRecord` 等于让 Protocol 偏离"envelope 转发"职责**。删 #3 更干净。

## Acceptance criteria

PR-1 ~ PR-4 合后:

- `scripts/check_observation_ssot.py` 9 + 1(emit_exception_caught 单一)= 10 条规则,0 命中
- `scripts/check_runtime_invariants.py` ≥ 3 条 invariant,0 命中
- `tests/runtime/test_runtime_loop_exception_paths.py` 新增:给 `runtime_loop` 注入抛 `RuntimeError` 与 `asyncio.CancelledError` 的 runner,断言 spine 里收到 `exception.caught` event 带 `traceback_text` / `call_frames` / `err_kind`
- `tests/lca_plugins/observability/spine/test_reflector_runtime.py` 删除 `emit_exception_caught` 相关 case
- `tests/observability/spine/test_exception_capture.py` 补 3 case:`UnnormalizedException` 兜底 / `exc_type` 字段串行 / size-driven offload 不借异常类槽位
- ADR-0177 状态从 Proposed → Accepted(扩展而非 supersede)

## Risks

- **PR-2 改 `runtime_loop.py`** 是 hot path,任何 regression 立即影响所有 run。需要回归:`uv run pytest tests/runtime tests/observability tests/lca_plugins/observability tests/lca_kernel`
- **emitter #2 删除后**反射器路径不能 fallback:`reflectors/runtime.py` 删除 `emit_exception_caught` 后,任何残留 `from .runtime import emit_exception_caught as ...` 会 import 失败。需要 `rg "from .*reflectors.runtime import.*emit_exception_caught" lca/` = 0 强制守门
- **`exc_to_record(exc)` 在 `except asyncio.CancelledError` 分支里**:Python 3.8+ `CancelledError` 继承自 `BaseException` 而非 `Exception`,`exc_to_record` 必须接受 `BaseException`。当前 `exc_to_record(exc: BaseException, ...)` 签名已支持,无需改动

## Delete-when

- **`EnvelopeEmitter.emit_exception_caught` Protocol 方法**:删除后不可恢复,本 PR 一次性落地(无 compat 分支)
- **`reflectors.runtime.emit_exception_caught` 函数**:同 PR-2 删除,无 compat
- **runtime_loop 4 键裸 dict 路径**:同 PR-2 改 `exc_to_record`,无 compat
- **`_FORCE_OFFLOAD_EPS = {"exception.caught"}` 兜底**:若保留 list 形式(而非 frozenset 或 enum),`# COMPAT(delete-when: 改 enum 且全 caller 迁完, tracking: ADR-0178-note-3)`

## Related

- [observation-convergence-root.md](2026-09-03-observation-convergence-root.md) — 根 note
- [ADR-0178](../../../adr/0178-observation-control-state-convergence.md) — 元决策
- [ADR-0177](../../../adr/0177-envelope-emitter-binding.md) — EnvelopeEmitter binding(扩展)
- [`docs/notes/implemented/contract/2026-09-03-exception-caught-single-emitter.md`](../../implemented/contract/2026-09-03-exception-caught-single-emitter.md) — 已定的修法,本 note 落地
- `lca/contracts/observability/exception_capture.py` — `ExceptionRecord` / `exc_to_record` SSOT
- `lca/runtime/runtime_loop.py` — hot path 改造点
- `lca/plugins/observability/spine/reflectors/runtime.py` — 平行 emitter 删除点
- `lca/infrastructure/observability/spine/sinks/file_sink.py` — `_FORCE_OFFLOAD_EPS` + sidecar label
