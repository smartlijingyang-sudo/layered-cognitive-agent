# ADR-0160：撤销 —— LlmCallCompleted 平衡保证已由 TelemetryLLMAdapter 闭合

## 状态

**Withdrawn — 2026-09-01**

subagent 深度评审发现:本 ADR 提议的"问题"根本不存在,提议的"修复"反而引入双发事件、字段错位、CancelledError 遮蔽、脱敏泄漏四类新问题。本 ADR 不再落地,改为在 `tests/test_telemetry_llm_adapter.py` 加 1 条不变量断言即可。

## 评审发现的事实

### 1. "4 个 LlmCallStarted × 2 个 LlmCallCompleted 不平衡"诊断是错的

ADR-0160 引用 `run_b1294a33e55d` 中 `LlmCallStarted ×4 / LlmCallCompleted ×2` 作为根因,定位 `executor.py:127-130`。

事实:`executor.py` 全文(150 行)**完全没有 `record(LlmCallCompleted)` 调用**:

- 无 import LlmCallCompleted
- 无 record(...) 调用 LlmCallCompleted
- 注释明确:happy path 只 break,然后走 retry 或 merged_stream

`executor.py:62` 和 `:96` 通过 `llm.stream(...)` 调用,而 `llm` 已经被 `instrument_llm` 装饰过的 `TelemetryLLMAdapter`(`brain_composer.py:36` → `brain.py:22-26`)。

**LlmCallCompleted 的唯一发射点一直是 TelemetryLLMAdapter.stream()**。

### 2. TelemetryLLMAdapter 三条路径已完整闭合

读 `lca/infrastructure/observability/adapters/adapters.py:107-208`:

| 路径 | 实现位置 | 状态 |
|---|---|---|
| COMPLETED 帧到达 | `adapters.py:139-149` → `_record(ok=True, recorded=True)` | ✅ |
| 异常抛出 | `adapters.py:188-193` → `_record(ok=False)` 然后 raise | ✅ |
| 流自然结束但无 COMPLETED | `adapters.py:198-208` → `_record(ok=True)` 配 warning | ✅ |

测试 `tests/test_telemetry_llm_adapter.py:148-170`(`test_stream_failure_records_stream_true`)已直接覆盖 ConnectionError/TimeoutError/RuntimeError 异常路径,断言 `len(completed) == 1` 且 `ok=False`。

### 3. ADR-0160 的"修复"反而引入五类新问题

| 问题 | 严重度 | 触发条件 |
|---|---|---|
| 双发 LlmCallCompleted | P0 | executor.py 加 try/finally + TelemetryLLMAdapter 已有的 try/finally 同时发 |
| 字段错位 | P0 | `record_completion` 签名 (call_id, started_at, ok, stream, error, response_preview) 与 `LlmCallCompleted` dataclass 字段 (model / ok / latency_ms / prompt_preview / response_preview / prompt_tokens / completion_tokens / stream) 一一对应不上 |
| CancelledError 遮蔽 | P1 | `except (asyncio.CancelledError, ConnectionError, TimeoutError) + raise` 让 finally 块把真正的 CancelledError 遮蔽 |
| 脱敏泄漏 | P1 | narrative_sidecar._rich 只截断不脱敏,加 error 字段会把 provider 异常消息原样写 markdown |
| journal 字段缺失 | P0 | `LlmCallCompleted` 没有 error 字段,提议代码引用不存在的字段 |

### 4. ADR-0160 自相矛盾

- §「与 ADR-0156-D 的偏离」拒绝 Protocol 过度工程是对的
- 但 §一 又写了"executor.py 加 try/finally"+ §二 给 TelemetryLLMAdapter 加 `record_completion` 方法
- **本质还是新增能力,只是把 Protocol 降到方法签名**
- 没解决过度工程的核心(二次发射 + 字段错位)

## 评审结论

| 提案 | 评审结果 |
|---|---|
| §一 executor.py 加 try/finally + telemetry.record_completion | **撤销** —— executor.py 不直接发 LlmCallCompleted;TelemetryLLMAdapter 已发 |
| §二 TelemetryLLMAdapter 加 record_completion 方法 | **撤销** —— `_record` 已存在 |
| §三 删 happy path 直发 | **撤销** —— 当前代码无直发,描述不存在的问题 |
| §四 ADR-0038 §三 兑现 | **不需要** —— TelemetryLLMAdapter.stream 已兑现 COMPLETED-response == complete() 等价 |
| §五 narrative 加 error 字段 | **撤销** —— 除非同时给 narrative_sidecar 接入 AttributePolicy.prepare,否则引入脱敏泄漏 |

## 真正需要做的1 件事

`tests/test_telemetry_llm_adapter.py` 加 1 条不变量断言:

```python
# tests/test_telemetry_llm_adapter.py
async def test_llm_call_started_completed_balance():
    """任意 run:count(LlmCallStarted) == count(LlmCallCompleted)。"""
    adapter = make_adapter(...)
    started = 0
    completed = 0
    async for event in adapter.stream(...):
        if isinstance(event, LlmCallStarted):
            started += 1
        if isinstance(event, LlmCallCompleted):
            completed += 1
    assert started == completed, f"{started} started vs {completed} completed"
```

如果这条断言在生产中真的失败,说明**有某条路径绕开了 TelemetryLLMAdapter**(未走 `instrument_llm`),或 `record()` 在某个 fork 下被替换为 no-op。**那才是真正需要新 ADR 的场景**;现在的"修复"是凭空发明 lifecycle 接口。

## 替代方案(已采纳)

| 方案 | 理由 |
|---|---|
| 撤销本 ADR + 加 1 条不变量断言 | TelemetryLLMAdapter 已闭合;真有不平衡先定位绕过点 |
| 修复 narrative_sidecar 接入 AttributePolicy | 独立工作;与本 ADR 主题不同,应走单独 ADR |

## 不落地清单

以下提案全部撤回,不实现:

- §一 executor.py:88-140 加 try/finally
- §二 TelemetryLLMAdapter.record_completion 方法签名
- §三 删除 happy path 直发(本身不存在)
- §五 narrative_sidecar.interesting keys 加 error 字段(脱敏泄漏)
- §五 LlmCallCompleted docstring 补 error 字段引用(字段不存在)

## 风险

- **风险 1**:若真有 `LlmCallStarted × N / LlmCallCompleted × M` 不平衡,本 ADR 撤销后无人跟进。**缓解**:`test_llm_call_started_completed_balance` 断言守门;若 CI 翻红,贴 trace 找到绕开 `instrument_llm` 的代码路径再开 ADR。
- **风险 2**:TelemetryLLMAdapter 的 `try/except/finally` 在 fork 替换 `record()` 时可能失效。**缓解**:诊断工具加 `count_record_calls_by_class` metric,跨 fork 监控。

---

## 附录 A:v2 评审后的诊断加固方案(subagent 评审补充)

第二轮 subagent 评审认为:仅 1 条 `test_llm_call_started_completed_balance` 断言虽然守门,但**断言失败时只能告诉运维「坏了」,不能告诉运维「为什么坏」**。若 CI 翻红,排查者需要重新跑全文 grep + 读 TelemetryLLMAdapter 三条路径才能定位绕过点 —— 把诊断成本从现在推到未来。

为补足这条建议,**在不修改产品修复路径的前提下**加 1 个运行时 metric 工具,与断言形成"测试守门 + 运行时观测"双层守护。

### A.1 新增 `count_record_calls_by_class` metric

`lca/infrastructure/observability/diagnostics/diagnostic_emitters.py` 与现有 `record_llm_completion` / `record_memory_operation` 同位,新增:

```python
def record_call_balance(
    *,
    event_class: str,
    started: int,
    completed: int,
) -> None:
    """运行时上报 LlmCallStarted / LlmCallCompleted 计数差。

    由 TelemetryLLMAdapter.stream() 在 finally 块调用;Otel/Meter SDK
    通过 counter 暴露 dashboard 指标 `lca.llm.call_balance{event_class}`。
    """
    ...
```

### A.2 TelemetryLLMAdapter 三条路径集成

`lca/infrastructure/observability/adapters/adapters.py:107-208` 三个 `_record` 调用后(成功 / 异常 / 自然结束),分别 emit 一次 `record_call_balance(event_class="LlmCall", started=1, completed=1)` 或不平衡状态。

### A.3 测试断言升级

`tests/test_telemetry_llm_adapter.py` 保留原 `test_llm_call_started_completed_balance` 断言,新增:

```python
async def test_telemetry_emits_call_balance_metric():
    """每次 stream() 结束时 emit 一次 record_call_balance,started == completed。"""
    ...
```

### A.4 落地性质

**本附录不修改产品修复路径**;TelemetryLLMAdapter 已闭合三条路径,本附录仅加**诊断观测**,与"撤销"状态兼容。

**新增代码量**:~25 行(metric 函数 15 行 + TelemetryLLMAdapter 三处集成 6 行 + 测试 10 行)。

### A.5 依赖

本附录落地前需确认:项目是否已绑定 OpenTelemetry Meter SDK(grep `from opentelemetry.metrics` 验证)。若未绑定,本附录应推迟到引入 OTel metric 时一并提交。

### A.6 与 Withdrawn 状态的关系

Withdrawn 仅表示"**撤销 §一至 §五的修复**";附录 A 是诊断观测,与撤销不冲突。**不撤销的修复 = 加诊断**;这是 subagent 评审认为 v1 留下的小遗漏。

---

## 历史

- **2026-09-01 v1**:本文初始撤销状态,仅 1 条断言。
- **2026-09-01 v2**:增加附录 A(subagent 评审补充,补诊断观测 metric)。