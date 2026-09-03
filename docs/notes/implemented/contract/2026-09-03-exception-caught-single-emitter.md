# Agent Note: exception.caught 单 emitter — 删掉并行 dict payload 路径

Status: implemented

## Problem

`traces/runs/*/` 下出现 11 个 `<sha8>-Unknown.json` sidecar。sidecar 文件名的后半段来自 `payload["exception_class"]`,`FileSink.offload_sidecar_path` 在该键缺失时回落到字面量 `"Unknown"`。

缺失有两个互不相干的来源,被同一个兜底名吞掉:

1. **size-driven offload**(2 个):`step.tool_call.record` 的 payload 超过 `_ATOMIC_THRESHOLD`(4096 B,Linux `PIPE_BUF`)被 offload。这类 event 根本没有异常,`exception_class` 本就不该存在,却被命名成 `Unknown`,读者无法从目录列表判断这是正常的大 payload 还是丢了信息的异常。

2. **绕过归一化的真异常**(9 个):payload 是 `{boundary, exc_type, message, trace_id}` —— 只有 `exc_type` 没有 `exception_class`,同时没有 `traceback_text` / `call_frames` / `err_kind`。这些是 `asyncio.CancelledError` 在 `terminal_driver` 边界的真实取消,traceback 已经永久丢失。

第 2 类的根因是 **`exception.caught` 有两个 emitter**:

| Emitter | 入参 | payload |
|---|---|---|
| `lca/infrastructure/observability/spine/exception_emit.py` | `ExceptionRecord` | `record.asdict()` 全字段 |
| `lca/plugins/observability/spine/reflectors/runtime.py` | `boundary, exc_type, message, trace_id` 四个裸 str | 手搓 4 键 dict |

`exception_emit.py` 的 docstring 已经把这个谬误写成历史教训("`transport_emit.emit_carrier_exception_caught` 是个残废实现 —— payload 只带 `exc_type / message` 不带 traceback,FileSink 不触发 offload,sidecar 永远不出现 …… 两套归一化路径并存是历史回归的根因"),但同一个形状在 reflector 里活着,`lca/runtime/runtime_loop.py` 的两条 `except` 分支正是它的唯一调用方。

第二个 emitter 还让 payload 稳定停在 4 KiB 以下 —— 少了 `traceback_text` 和 `call_frames`,`FileSink` 的 size 判据不触发,所以这类异常连 `exceptions.jsonl` 索引之外的 traceback 都不落盘。**"漏字段"直接等价于"丢证据"**,不只是名字不好看。

## Decision

`exception.caught` 只有一个 emitter:`lca.infrastructure.observability.spine.exception_emit.emit_exception_caught(record: ExceptionRecord)`。任何 caller 先经 `lca.contracts.observability.exc_to_record` 归一化。

具体收口:

- **删** `lca/plugins/observability/spine/reflectors/runtime.py::emit_exception_caught`(连同 `__all__` 条目)。同文件保留 `emit_exception_finally` —— 它是 envelope,不承载异常内容。原位置留注释说明为何此处没有 `exception.caught`。
- **`lca/runtime/runtime_loop.py`** 两条 `except` 分支改走 `exc_to_record(exc, boundary=..., run_id=..., trace_id=...)` + SSOT emitter。`CancelledError` 分支同时改成 `except asyncio.CancelledError as exc` 绑定实例 —— 原来传的是硬编码字符串 `"asyncio.CancelledError"` 和 `"driver cancelled"`,不是真实异常。
- **`EnvelopeEmitter` Protocol**(`lca/contracts/protocols/runtime/envelope_emitter.py`)删掉 `emit_exception_caught` 方法,docstring 写明该 EP 不属于本 Protocol:关键字参数面无法承载 `ExceptionRecord`。`lca/runtime/envelope_emitter.py::SpineEnvelopeEmitter` 同步删实现。
- **`FileSink` 命名**(`lca/infrastructure/observability/spine/sinks/file_sink.py`)新增 `sidecar_label(record)`,按 offload 原因分流:`exception.caught` 用 `exception_class`,其它(size-driven)用 `execution_point`。`exception.caught` 缺 `exception_class` 时标签是 `UnnormalizedException` 而非通用兜底 —— **emitter 缺陷必须在文件名上可见**。`safe_class_name` 的"清洗后为空"回落改为 `Unlabelled`,与前者区分。

落盘效果:size-driven offload 得到 `<sha8>-step.tool_call.record.json`,取消得到 `<sha8>-CancelledError.json`,再没有 `Unknown`。

## Alternatives considered

### Why not 在 `FileSink` 里回落读 `exc_type`?

最小 diff,一行 `payload.get("exception_class") or payload.get("exc_type")` 就能让文件名变成 `CancelledError`。否决:**只治了名字,没治证据**。这类 payload 缺的是 `traceback_text` / `call_frames` / `err_kind`,文件名对了,sidecar 里依然没有 traceback,`err_kind` 依然无法分类。而且它把"两个 emitter 并存"这个根因固化成 sink 的永久职责 —— sink 从此要理解每个 emitter 的方言,`AGENTS.md` §1 的"不写补丁式代码"直接命中。

### Why not 给 reflector 的 emitter 补上 traceback 字段?

即让 `reflectors.runtime.emit_exception_caught` 也接 `exc` 并内部调 `exc_to_record`。否决:那就是把 `exception_emit.py` 复制一份。归一化 SSOT 的价值来自"只有一个函数能产 `exception.caught`",两个函数即使当下字段一致,也会在下次加字段时分叉 —— 这正是 `exception_emit.py` docstring 记录的历史。

### Why not 保留 `EnvelopeEmitter.emit_exception_caught`,只改实现?

否决。`ExceptionRecord` 无法穿过 `(boundary, exc_type, message, trace_id)` 这组关键字参数;要么把 Protocol 方法签名改成收 `ExceptionRecord`,那它就跟 `exception_emit.emit_exception_caught` 完全重复、只多一层转发;要么让 Protocol 收 `BaseException` 并在实现里归一化,那 Protocol 就从"envelope 转发"变成"异常归一化",职责跑偏。`EnvelopeEmitter` 的其余 10 个方法都是无内容 envelope(reducer apply / resume / lifecycle finally),`exception.caught` 是唯一携带结构化内容的,不属于这里。

ADR-0177 状态是 Proposed,该 Protocol 目前没有生产调用方(只有 `tests/runtime/test_envelope_emitter_binding.py` 引用),删一个未接线的方法不影响任何运行路径。

### Why not 顺手把 `ExceptionRecord.asdict()` 里的 legacy alias(`exc_type` / `reason`)也删掉?

否决 —— 超出本 seam。`trace_inspector` / `spine.producer.failure` / `journal_trace.py:649` 仍在消费旧键,`asdict()` 同时给两套键正是为了它们。删 alias 是独立的 reader 迁移任务,有自己的删除条件("`rg exc_type` 在 reader 侧归零"),不该混进本次修复。本次只保证 **writer 侧字段齐全**。

### Why not 什么都不做(基线)?

否决。`terminal_driver` 边界的取消是最需要 traceback 的场景之一(用户中断、上游断流、idle timeout),而这条路径恰好是唯一丢证据的。`docs/notes/implemented/seam/2026-09-03-observation-ssot-registry.md` 已经把"消费方各绕各的"定为根因并建立守门,本条是同一根因在 writer 侧的残留。

## Consequences

- `exception.caught` 的 writer 侧只剩一个入口;新增捕获边界必须先 `exc_to_record`,漏字段在 sidecar 文件名上直接暴露成 `UnnormalizedException`。
- sidecar 目录列表现在可区分三种情况:异常类名(正常)、`execution_point`(size-driven offload)、`UnnormalizedException`(emitter 缺陷)。
- `runtime_loop` 的取消事件从"硬编码字符串"变成真实异常快照,payload 因带 `traceback_text` / `call_frames` 而超过 4 KiB,因此**开始**产生 traceback sidecar —— 这是本次修复的可观察目标。
- 历史 `-Unknown.json` 文件不迁移。它们记录的是当时真实落盘的残缺 payload,重命名会伪造历史;`traces/` 不是代码产物。

### 双 spine accessor 的测试含义

`exception_emit` 经 `instrument_wrap.resolve_active_spine()` 取 spine,reflector 经 `_spine_safety.set_active_spine` 取 —— 两套进程局部存储。生产路径由 `lca/plugins/observability/spine/core.py::_activate_process_local_spine` 把二者指向同一个 `EventSpine`,所以运行时一致;但只 wire 其中一个的测试会看不到对侧事件。`tests/lca_plugins/observability/spine/test_reflector_runtime.py` 里跨两侧的用例显式装两个 accessor 并在 `finally` 里复原。

## Verification

```sh
uv run ruff check <9 files>            # All checks passed
uv run ruff format --check <9 files>   # 9 files already formatted
uv run lint-imports                    # 通过(runtime → contracts.observability 合法)
uv run pytest --no-cov -q tests/observability tests/runtime tests/lca_plugins/observability tests/lca_kernel
# 802 passed, 1 failed
uv run python scripts/check_no_silent_swallow.py  # 3 findings,与基线同,均不在本次文件
```

`tests/lca_plugins/observability/spine/test_core.py::test_setup_soft_subscribes_optional_derivers_and_console_sink` 与 `tests/architecture/test_capability_snapshot.py::test_golden_plan_ref_snapshot` 在 `git stash` 基线上同样失败,与本改动无关。mypy 在 `runtime_loop.py` / `file_sink.py` 的报错数量与基线逐条相同(仅行号偏移)。

回归锁在 `tests/observability/spine/test_exception_capture.py`:

- `test_sidecar_label_names_size_offload_by_execution_point` — 非异常 offload 不借异常类槽位。
- `test_sidecar_label_flags_exception_that_bypassed_exc_to_record` — 手搓 `{boundary, exc_type}` payload 得到 `UnnormalizedException`。
- `test_exception_class_populated_by_exc_to_record_drives_sidecar_label` — 走 SSOT 必命中真实异常类。

`tests/lca_plugins/observability/spine/test_reflector_runtime.py::test_cognitive_runtime_run_driver_emits_exception_events` 断言 `runtime_loop` 失败路径的 payload 带 `exception_class` / `exception_message` / `traceback_text`。

## Related

- [`docs/notes/implemented/seam/2026-09-03-observation-ssot-registry.md`](../seam/2026-09-03-observation-ssot-registry.md) — 观测面 SSOT 收口;本条是其 writer 侧残留
- `lca/infrastructure/observability/spine/exception_emit.py` — 唯一 emitter
- `lca/contracts/observability/exception_capture.py` — `ExceptionRecord` / `exc_to_record` / `ErrKind`
- ADR-0169、ADR-2026-09-02-i17-stream-align §B — 异常归一化 SSOT
- ADR-2026-09-03-debug-clarity — `ErrKind` + by-frame traceback cap
- ADR-0177(Proposed)— `EnvelopeEmitter` binding;本条缩小其 surface
