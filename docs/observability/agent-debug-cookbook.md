# Agent Debug Cookbook — ADR-0065 §六

## 4 阶段诊断流程

### Stage 1: 看耗时分布(30 秒)

读 `<run>/manifest.json` 拿 `ledger_high_watermark` + `started_at` / `closed_at`。
对比预期耗时;显著超时 → 继续。

### Stage 2: 找瓶颈(top-N)

```sh
lca-ops cost <run_id> --by phase
```

或 Coding Agent tool:

```python
coding_agent_optimization_finder.find_optimization_candidates(run_id=..., limit=10)
```

输出按 `latency_ms` 降序的事件;聚焦 LLM / 工具 / Plugin。

### Stage 3: 看决策 + 时间线 + 代码

```sh
lca-ops graph-run <run_id>      # mermaid 插件交互图
lca-ops trace <run_id> --focus llm|tools|delegation --depth 24
```

或:

```python
coding_agent_trace_inspector.inspect_trace(run_id=..., focus="latency")
```

### Stage 4: 失败路径 + 插件交互

```sh
lca-ops explain <run_id>           # 失败因果链
lca-ops graph <run_id>            # 插件交互图
lca-ops minimal-repro <run_id>    # 最小复现包
```

## 内置 diagnose alias(PR-9)

```sh
lca-ops diagnose model_not_seen     # LLM_MODEL_NOT_FOUND / PLUGIN_BOOT_FAILED
lca-ops diagnose loop_stuck         # LOOP_STUCK / LOOP_OSCILLATING / LOOP_MAX_STEPS
lca-ops diagnose memory_poisoned   # MEMORY_POISONED / MEMORY_FULL
lca-ops diagnose approval_rejected  # GATE_DENIED / TOOL_PERMISSION_DENIED / AUTH_INSUFFICIENT
```

每个 alias 输出:
- `ErrorCode` 列表
- 可执行的修复建议(由 `DIAGNOSE_HINTS` 提供)

## 7 个 Coding Agent 工具(bundle)

| Tool | 用途 |
|---|---|
| `trace_inspector` | inspect_trace(focus, depth) |
| `failure_explainer` | explain_failure(depth) |
| `optimization_finder` | find_optimization_candidates(limit) |
| `plugin_graph_renderer` | render() → Mermaid |
| `minimal_reproduction` | export() → 因果链 + evidence refs |
| `diff_context` | diff(run_id, step) |
| `run_diff` | diff(run_id_a, run_id_b, step) |

**全部 read-only**;`check_no_journal_write_in_coding_agent.py` AST 兜底,无 `RunLedger.append` / `record()` 旁路。

## 错误码字典

10 大类 ~30 稳定码(闭集):
- `LLM` (RATE_LIMIT / CONTEXT_OVERFLOW / CONTENT_BLOCKED / MODEL_NOT_FOUND)
- `TOOL` (TIMEOUT / PERMISSION_DENIED / INVALID_ARGUMENT / NOT_FOUND)
- `GATE` (DENIED / REWRITTEN)
- `LOOP` (STUCK / OSCILLATING / MAX_STEPS)
- `PLUGIN` (BOOT_FAILED / MISSING_DEPENDENCY)
- `MEMORY` (POISONED / FULL)
- `SANDBOX` (OFFLINE / IO_ERROR)
- `NETWORK` (TIMEOUT / DNS)
- `AUTH` (EXPIRED / INSUFFICIENT)
- `USER` (CANCELLED / ABANDONED)

新增 code 必须 ADR 评审(0065 §六 + ADR-0064 §9)。