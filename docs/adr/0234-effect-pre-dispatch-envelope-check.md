# ADR-0234 — `effect.pre_dispatch.envelope_check` Graph Node (PipelineSafeExecutor 5-Gate Extraction)

**Status:** Accepted — 2026-09-16. PR-2 of `2026-09-16-act-subgraph-tightening`.

> **一句话**: 把 `PipelineSafeExecutor.execute` 内化的 5 闸(envelope-shape / permission / grant / budget / safe-boundary)抽到 typed-port graph 节点 `effect.pre_dispatch.envelope_check`,输入 `(envelope, tool)`,输出 `(envelope, verdict_refs)`。`PipelineSafeExecutor.execute` 退化为薄壳,只负责 envelope mint + graph 节点调用 + Observation 包装。

**Refines / Fixes:**
- ADR-0068 §五 — CommandEnvelope 是 5 闸的载具;PipelineSafeExecutor 把 5 闸内化,违反"graph 可见性"与 C13 typed-port 完整化债。
- ADR-0220 §3.3 — `effect.execute` 节点已 graph 化 envelope dispatch,但前置 5 闸仍留在 procedure call;补完 typed-port 完整化债。

## Problem

`PipelineSafeExecutor.execute` (lca/cognition/body/executor/pipeline_safe_executor.py) 把 5 闸(permission / grant / budget / safe-boundary / envelope-shape)内化为 procedure call;graph 不可见。`act.authorize` 节点已经在 surface 层做 budget/constraint/safe-boundary,SE 内部再做一遍 → 双层结构违反 C13 + typed-port 完整化债;debug 半径大,verdict_refs 是第二套语义词表(`executor.*`)与 graph canonical `effect.pre_dispatch.*` 冲突。

### 现状（修复前实测）

`PipelineSafeExecutor.execute` 内化 5 闸(Procedure Call 内):

| 闸 | 检查 | 失败抛 |
|---|---|---|
| envelope-shape | `plan_ref / scope_ref / decision_ref / provider` 非空 | `ToolExecutionError` |
| permission | `tool.name in permission_manifest.allowed_tools` | `ToolExecutionError` (经 `_check_permission_and_args`) |
| grant | `envelope.grant.capability == tool.name AND effect_class == "tools"` | `ToolExecutionError` |
| budget | `envelope.budget_reservation` 各项 ≥ 0 | `ToolExecutionError` |
| safe-boundary | `envelope.plan_ref / scope_ref` 非空 | `ToolExecutionError` |

5 闸产出 5 个本地 `executor.*` verdict_refs:

```
verdict_refs = ["executor.permission:allow"]
verdict_refs.append("executor.reservation:valid")
verdict_refs.append("executor.grant:valid")
verdict_refs.append("executor.plan-boundary:valid")
verdict_refs.append("executor.pipeline:completed")
```

与 graph canonical `act.*` / `effect.*` 词表冲突;违反 AGENTS.md §2.2 "单一事实源"。

## Decision

### 1. 新 graph 节点 `effect.pre_dispatch.envelope_check`

| 字段 | 值 |
|---|---|
| `semantic_name` | `"effect.pre_dispatch.envelope_check"` |
| `region` | `"effect"` |
| `declared_inputs` | `("envelope", "tool")` |
| `declared_outputs` | `("envelope", "verdict_refs")` |
| `node_execute` 行为 | 5 闸一次性 atomic check;通过 → emit `(envelope, verdict_refs=tuple("effect.pre_dispatch.permission:allow", "effect.pre_dispatch.grant:valid", "effect.pre_dispatch.budget:valid", "effect.pre_dispatch.safe-boundary:valid", "effect.pre_dispatch.envelope-shape:valid"))`;任一闸失败 → raise `ValueError`,`verdict_refs` 不 emit(`NodeOutput({})`),outer edge 走 `terminal.commit` |

5 闸的语义全部搬到 graph 节点:

| 闸 | graph verdict_ref | 检查 |
|---|---|---|
| envelope-shape | `effect.pre_dispatch.envelope-shape:valid` | `plan_ref / scope_ref / decision_ref / provider` 非空 |
| permission | `effect.pre_dispatch.permission:allow` | `tool.name in permission_manifest.allowed_tools` |
| grant | `effect.pre_dispatch.grant:valid` | `envelope.grant.capability == tool.name AND effect_class == "tools"` |
| budget | `effect.pre_dispatch.budget:valid` | `envelope.budget_reservation` 各项 ≥ 0 |
| safe-boundary | `effect.pre_dispatch.safe-boundary:valid` | `envelope.plan_ref / scope_ref` 非空 |

### 2. `PipelineSafeExecutor.execute` 退化为薄壳

- **保留**: envelope mint(`mint_envelope()`)— stack trace 仍含 mint_envelope,architecture test `scripts/check_command_envelope_required.py` 守护通过
- **新增**: graph 节点 `effect.pre_dispatch.envelope_check` 调用
- **新增**: graph 节点 `effect.execute` 调用(已含 SafeExecutor 内部 tool 调用 + retry)
- **删除**: 5 闸 procedure call + 5 个本地 `executor.*` verdict_refs(G-7 收尾)
- **保留**: Observation 包装 + Journal record(act_closed / record_step_tool_call / record_step_tool_result)

预计减行 ≥ 80 行(G-2 verification)。

### 3. `act.dispatch` typed-port 扩展

`bundles/act/act_subgraph.yaml` 在 `act.dispatch` 前插入 `effect.pre_dispatch.envelope_check`:

```yaml
- id: effect.pre_dispatch.envelope_check
  region: effect
  factory: effect.pre_dispatch.envelope_check
  inputs: [envelope, tool]
  outputs: [envelope, verdict_refs]
  config:
    emit_on_enter: []
    emit_on_exit: []

- id: act.dispatch
  factory: act.dispatch.ref
  inputs: [envelope, verdict_refs]   # 新增 verdict_refs 输入
  outputs: [receipt]
```

edge `effect.pre_dispatch.envelope_check → act.dispatch` 由 `act.fanout` 的 envelope 端口继续供 envelope,而 verdict_refs 由新节点产出。

### 4. `effect.execute` declared_inputs 扩展

`bundles/concept/effect/effect_execute.yaml`:

```yaml
- id: effect.execute
  factory: effect.execute
  inputs: [envelope, verdict_refs]   # 加 verdict_refs 输入
  outputs: [receipts]
```

### 5. typed-port 注解

`lca/contracts/protocols/act/command/envelope.py` 在 `policy_verdict_refs: tuple[str, ...]` 已有 typed-port 注解(PR-7 V4 acceptance),无需新增。

## Alternatives Considered

- **(a) 维持 procedure call** — 拒绝:graph 不可见,debug 半径大,违反 typed-port 完整化债。
- **(b) 把 5 闸分散到 5 个 graph 节点** — 拒绝:5 个独立节点产生 5 个 typed port,fan-out 增加延迟,但实际只 1 次 envelope-shape check;过度切分违反 C6 最小化。
- **(c) 单节点 `effect.pre_dispatch.envelope_check`** — **接受**:5 闸是 envelope-shape 一次性 atomic check,单节点符合 C6 + 单一职责。

## Consequences

- `act.dispatch` 节点 declared_inputs 从 `(envelope,)` 扩展到 `(envelope, verdict_refs)`(verdict_refs 由 `effect.pre_dispatch.envelope_check` 产出)
- `PipelineSafeExecutor.execute` 减行 ≥ 80 行(G-2 verification)
- 5 个本地 `executor.*` verdict_refs 全部删除(G-7),统一由 graph 节点产出 `effect.pre_dispatch.*`
- architecture test `scripts/check_command_envelope_required.py` 仍然通过(stack trace 仍含 `mint_envelope`)
- `tests/effect/test_pre_dispatch_envelope_check.py` 新建(happy + permission fail)

## Verification

- `ruff check` + `ruff format` 0 introduced violations
- `pytest tests/effect tests/act -q` 全绿
- `pytest tests/act tests/intervene tests/contracts/observability tests/integration/test_no_dual_sink.py tests/lca_kernel/plan/test_phase_main_outer_lift.py -q` 仍 ≥ 80 passed
- architecture test `scripts/check_command_envelope_required.py` 通过(stack trace 仍含 `mint_envelope`)
- `grep -rn "executor\.\(permission\|reservation\|grant\|plan-boundary\|pipeline\)" lca/cognition/` 返回 0 matches

## delete-when

N/A — `effect.pre_dispatch.envelope_check` 是新节点;`PipelineSafeExecutor` 内化 5 闸的 procedure call 同步删除,无遗留。