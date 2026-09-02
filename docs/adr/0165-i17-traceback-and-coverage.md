# ADR-i17-tb: I17 回溯零遮蔽、SourceAttacher 失败可观测、生产 profile 强制覆盖

- 状态: Accepted(2026-09-02)
- 日期: 2026-09-02
- 作者: coding-agent
- 父规范: [ADR-0165](0165-execution-point-enforcement.md)(执行点强制织入 + I17)
- 相关: [ADR-0165-event-spine-unified-log](0165-event-spine-unified-log.md), [ADR-0167-spine-ssot](0167-spine-ssot-and-step-materialization.md), [ADR-0065](0065-error-handling.md)
- 触发证据: `traces/runs/run_c713591304e6`(2026-09-02 15:07:11) `terminal_event_seq=13 status=failed`,`/tmp/lca-kernel.log` 中 `wrap_instrument: pipeline emit failed ep=phase_graph.node.start err=I17: ...` 后续无 Python traceback,`manifest.extra.doctor_report.hops.H6.error` 被推断为 `error_kind=internal attempts=1[1:permanent:AttributeError]` 而源码与 journal 中实际不存在 `AttributeError`。

## 一句话

把 ADR-0165 §I17 三个落地漏洞一次性钉住:(1) 失败链路零遮蔽 —— `I17Violation` 走 `exc_info=True` 路径,且作为 `phase_graph.node.start.rejected` 事件落到 journal 可恢复;(2) `SourceAttacher.produce` 失败可观测 —— `inspect` 出错时记 ERROR 日志 + 计数器,并在 envelope 上区分 "无帧" 与 "帧损坏";(3) `web-standard` 与 `spine-default` profile 强制启用 `spine.reflector.source`,把 ADR-0165 §173 "不让业务方关 I17" 的承诺落到实处。

## 背景

PR-9 (`spine.reflector.source` + I17) 落地后留下了三条裂缝,事故 (`run_c713591304e6`) 同时撞上:

| # | 裂缝 | 文件:行 |
|---|---|---|
| A | `wrap_instrument._safe_append` 用同一个 `except Exception` 兜底一切(包含 `I17Violation`),既不 `exc_info=True`,也不持久化 | `lca/harness/declarative/compile/instrument_wrap.py:208-211,228-241` |
| B | `SourceAttacher.produce` 对 `OSError / AttributeError / KeyError / TypeError` 静默吞掉,返回 `("", 0, "")` 的伪帧 | `lca/plugins/observability/spine/reflectors/source.py:247-253` |
| C | `web-standard.yaml` 与 `bundles/spine-default.yaml` 显式不启用 `spine.reflector.source`,但 `wrap_instrument.assembler_wrap` 在标准 profile 下也会发出需 I17 的 `*.start` 事件——I17 与生产 profile 当前是互相矛盾的设计 | `profiles/web-standard.yaml:6`,`bundles/spine-default.yaml:24` |
| D | `run_doctor` 在 `I17Violation` 时按启发式拼出 `error_kind=internal attempts=1[1:permanent:AttributeError]`,把运行时异常硬贴上 `AttributeError` 标签——源码与 journal 中无此异常类 | `lca/runtime/run_doctor.py`(投影层) |
| E | `apply_stop` 在 terminal_driver 路径上跑两次且 `run_id=""`;`kernel.run.stopped` 事件从未发出,H2 失败时 doctor 拿不到 `run_finished` 闭合标志 | `traces/runs/run_c713591304e6/events.jsonl seq 12-15` |
| F | `run_doctor.H2.last_seq` 报 0,journal 已经写到 seq 13——投影源不一致 | `manifest.extra.doctor_report.hops.H2.last_seq` |

裂缝 A 是最严重的:incident 现在在 `/tmp/lca-kernel.log` 里**没有任何 Python 堆栈**,只能看到一串拼接的 `err=...`,完全无法定位 `wrap_instrument` 调用方或 assembler 节点。

## 决策

按 LCA 五层职责分工:**Journal 是事实流(附加观察),Reducer 是状态控制,Runtime/Plugin 是控制时序,Profile 是组合根,Doctor 是观察派生**。每条修复只动自己那一层。

### D1 — 异常分类与回溯(裂缝 A,Journal 面)

`wrap_instrument._safe_append` 区分两类:

1. `I17Violation` —— 走 `EmitPipeline.emit(spine.i17.rejected, channel="error", payload={attempted_ep, exception_class, reason, traceback_text, span_id}, outcome="failure")` 一次性持久化;继续原 swallow 路径,但**额外** `log.error(..., exc_info=True)` 让 stderr 也可见。
2. 其他异常 —— 维持现有 `log.warning(..., exc_info=True)` 语义。Doctor 把这类归纳为 `error_kind=sink_failure`。

`spine.i17.rejected` 字段契约:同 ADR §D 段 markdown 内的 JSON 模板。Register 到 `EXECUTION_POINTS` 白名单;走 `EmitPipeline` 而不是直接 `spine.append`,这样下游反射器(anomaly detector)按既有路径处理。

### D2 — SourceAttacher 失败可观测(裂缝 B,Journal 面)

三个内部 helper(`_source_location` / `_call_frames` / `_locals_snapshot`)的契约从 "raise-or-return-value" 改为 "返回 (value, did_fail, exc)",不再 try/except 包裹整段 `produce()`。`produce()` 仍返回**同一份 envelope** —— 不增加 envelope 字段,不变 schema。

`EmitPipeline.emit(...)` 在调用 `produce()` 后,检查返回值中"哪些 field 是 did-failed":
对每个 failed field,K 一次 EmitPipeline 内部 emit 一个 `spine.producer.failure` 事件,`channel="error"`,`payload={producer_name, key, exc_class, traceback_text, span_id}`。

这样 SourceAttacher 模块**无全局状态、无 counter、无 status 字段**;失败事实自动落到 journal,doctor / run / explain 既有查询路径全部能拿到。Journal 是 SSOT,职责单一清晰。

**emitted events 形状**

```json
{
  "execution_point": "phase_graph.node.start.rejected",
  "channel": "error",
  "outcome": "failure",
  "payload": {
    "attempted_execution_point": "phase_graph.node.start",
    "exception_class": "lca.plugins.observability.spine.emit_pipeline.I17Violation",
    "reason": "I17: ...",
    "traceback_text": "<完整 traceback,4KB cap>",
    "call_site": {"file": "...", "line": ..., "function": "..."},
    "span_id": "<外层 span>"
  }
}
```

```json
{
  "execution_point": "spine.producer.failure",
  "channel": "error",
  "outcome": "failure",
  "payload": {
    "producer": "spine.reflector.source",
    "key": "locals_snapshot",
    "exception_class": "OSError",
    "traceback_text": "...",
    "span_id": "<外层 span>"
  }
}
```

两个 ep 一并加入 `EXECUTION_POINTS` 白名单。

### D3 — I17 协议修正(裂缝 C,Profile + Plugin 面)

**关键第一性原理判定**: I17 是 spine 的全局合约,必须有;不能用"profile 选择关闭"。所以 fix 不是"我让 SourceAttacher 在 web-standard 上线",而是"我让 web-standard 与 spine-default bundle 同时启用 SourceAttacher"。

- `bundles/spine-default.yaml` / `profiles/web-standard.yaml` 在 plugin 列表中加入 `spine.reflector.source`。
- 移除"introspection disabled" 注释;改写头注释说明 I17 始终启用。
- `bundles/spine-oii-debug.yaml` 作为单测 fixture 保留,生产 profile 不再走它。
- 走 `compile_profile` 启动诊断(`kernel_boot_diagnostic source_attacher=on`),写到 `.lca/spine/boot-events.jsonl`。

### D4 — I17 检查是协商而非强制(裂缝 C-bis,Plugin 面)

I17 检查仅当 `SourceAttacher` 在场时要求 `source_location`;否则 `wrap_instrument` 走快速路径,`EmitPipeline.emit` 在合并 payload 后将缺省 `source_location=None` 视为合法,并自动追加 `phase_graph.instrument.coverage` 事件一次(每 run 一次而非每事件,避免刷屏)。

这样设计: 当 I17 在 SourceAttacher 参与下是**强**;I17 在没有 SourceAttacher 参与下是**弱**(事件本身不拒绝,但记录一次 coverage gap)。生产 profile 现在总是开,不会出现"weak 路径"。OII 调试 profile 后续如需关闭可单独配置。

### D5 — terminal_driver 与 reducer 不变量(裂缝 E,Control 面)

- `runtime_loop` 的 `lifecycle.finally` 末尾发**一次** `kernel.run.stopped` 事件,`outcome=success|failed`,与 `kernel.run.stop` 一致。这一条是 H2 的 SSOT 闭合信号。
- `reducer.apply_stop`: idempotent 守卫:若 `run_id` 与 `state.run_id` 不匹配或为空,抛 `ReducerInvariantViolation`。`terminal_driver` 在调该 reducer 之前通过一个 thread-local 上下文管理器(canary name:`_terminal_driver_active`)证明自己有"再调用一次"的合法身份。这是 control-plane 不变量,仅在该 reducer 内部作用域内观察。

### D6 — Doctor 派生源统一(裂缝 D + F,Observation 派生面)

`run_doctor` 改造为单 SSOT 源读取:

- 所有 `*.rejected` / `*.failure` / `*_stopped` / 终止事件 → 读 `run_manifest.terminal_event_seq` 与 `extra.doctor_evidence_refs` 链。
- `H6.error`:从 `phase_graph.node.start.rejected`/`spine.producer.failure` 直接读 `exception_class` 与 `reason`,**不再用 `AttributeError` 启发式**。
- `H2.last_seq`:统一读 `terminal_event_seq`,而不是独立 tail journal 后又抹成 0。
- `H6.evidence_refs`:列出对应 `causality_id` 数组,供 `explain` 工具直接拉取。

Doctor 不查任何在 journal 里已经存在的事实 —— 这是派生层的本职。

## 不变量扩展(更新 ADR-0165 表)

| ID | 描述 | 实现 | 出处 |
|---|---|---|---|
| I17.a | `*.start` 失败必落 `phase_graph.node.start.rejected` 事件 | `EmitPipeline.emit` | 本 ADR |
| I17.b | `SourceAttacher.produce` 失败必落 `spine.producer.failure` 事件 | `EmitPipeline.emit` | 本 ADR |
| I17.c | 任何启用了 `spine.emit_pipeline` 的 profile 必须同时启用 `spine.reflector.source`(否则 coverage gap) | `compile_profile` startup diagnostic | 本 ADR |

## 后果

### 兼容性

- **新事件类型** `phase_graph.node.start.rejected`、`spine.producer.failure`、`phase_graph.instrument.coverage` 加入 `EXECUTION_POINTS` 白名单;既有消费方忽略未知 ep 即可,Journal EventRecord schema 不变。
- **manifest schema 轻微 bump**:`hops.H6.error` 附 `exception_class` 与 `evidence_refs`;读取端忽略未识别键即可。
- **SourceAttacher envelope 不变** —— 这一条是设计上的回归("we don't grow the contract for the failure case")。
- **profile change**: 生产 profile 启用 `spine.reflector.source`,带来约 30-50µs/phase 反射开销。备注写入 `profiles/web-standard.yaml` 头部。

### 风险与回退

- 反射开销放大不会破坏 SLA(单 phase 0.03ms 量级)。
- `ReducerInvariantViolation` 抛出会冒泡到 `terminal_driver` —— terminal_driver 已有的 `except BaseException` 路径会兜底并转 `kernel.run.stopped outcome=failed`,H2 投影依然闭合。
- Doctor schema bump 由消费方 `journal_trace --schema=1` 兼容开关处理一个发布周期。

### 测试矩阵

| 文件 | 新增断言 |
|---|---|
| `tests/lca_plugins/observability/spine/test_runtime_hooks.py`(本批已增) | I17 错误走 stderr traceback 路径 |
| `tests/lca_plugins/observability/spine/test_source_attacher.py` | helper raise 时 EmitPipeline 真的发了 `spine.producer.failure` 事件;envelope 不变 |
| `tests/lca_plugins/observability/spine/test_emit_pipeline.py` | `*.start` 在 SourceAttacher 缺席但 pipeline 启用时仍可通过,自动追加 `phase_graph.instrument.coverage`;在场时 `spine.producer.failure` 路径不影响 `source_location` 主路径 |
| `tests/lca_kernel/test_run_doctor.py` | `H6.error` 读到真实 `exception_class`;`H2.last_seq == terminal_event_seq` |
| `tests/lca_kernel/test_reducer.py` | `apply_stop` run_id 空 / 不匹配时抛 `ReducerInvariantViolation`,terminal_driver 路径不抛 |
| `tests/lca_kernel/test_terminal_driver.py` | finally 路径发出 `kernel.run.stopped`,且仅发一次 |
| `tests/lca/application/test_profile_resolution.py` | `web-standard.yaml` 启动后 diagnostic 含 `source_attacher=on` |
| `tests/integration/test_web_standard_i17_coverage.py` | 整进程 POST /runs → events.jsonl 含 source_location,无 rejected 事件,doctor verdict clean |

### 验证门禁

按 AGENTS.md §6 行级矩阵触发本批验证:

```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
scripts/check_kernel_boundary.py
# kernel-domain-isolation & transport-isolation (pyproject.toml)
```

## 参考

- 触发 run: `traces/runs/run_c713591304e6`(同时 `run_f18a19acc3d7`)
- 父规范: [ADR-0165](0165-execution-point-enforcement.md) §I17
- 设计: `docs/superpowers/specs/2026-09-01-spine-execution-points-design.md`
- 实现位置: `lca/harness/declarative/compile/instrument_wrap.py`(已增 §D1 入口,等 §D1-full 完成)、`lca/plugins/observability/spine/reflectors/source.py`、`lca/plugins/observability/spine/emit_pipeline.py`、`lca/runtime/runtime_loop.py`、`lca/runtime/reducer.py`、`lca/runtime/run_doctor.py`、`profiles/web-standard.yaml`、`bundles/spine-default.yaml`
