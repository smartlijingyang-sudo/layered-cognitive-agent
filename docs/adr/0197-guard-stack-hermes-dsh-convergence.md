# ADR-0197 — Guard Stack：Hermes 分层收敛 + DSH Guard 插件化融合

## 状态

**Implemented**（2026-09-07）。P1+P2 已落地：`LoopGuardPolicy`（`lca/cognition/brain/guard/loop_policy.py`）、`ToolGuardService` + `wrapped_executor`（`lca/cognition/body/guard/`）、`RepeatToolCallGate` 精确 args 指纹（`lca/cognition/brain/decision_gates/repeat/tool_call.py`），`bundles/guard-stack.yaml` 组合包就绪。

## 0. 决策摘要

将 Hermes **分层收敛栈** 与 DSH **guard 插件族** 编译进 LCA 既有 seam，不新增第七 phase、不引入平行 loop。

| 平面 | DSH 对标 | Hermes 对标 | LCA 机制 |
|---|---|---|---|
| **think** | repeat-tool-reminder | ToolCallGuardrailController | `GateService` slot=loop |
| **semantic** | — | verify-on-stop / delivery | `ConvergencePolicy` + delivery gate |
| **stop** | — | iteration_budget + finalizer | `state.stop-policy` + convergence runtime |
| **act** | timeout-policy, spill-policy | — | `ToolGuardService` + guarded SafeExecutor |
| **graph** | — | IterationBudget | `lca-declarative-loop-guard` |

## 1. 三层 enforcement ladder（借 DSH）

```text
advisory     → PolicyFact / gate warn（不 rewrite）
cooperative  → 结构化 synthetic result（TOOL_TIMEOUT, spill preview）
hard         → Decision rewrite RESPOND / monotonic deny
semantic     → delivery satisfied → force respond
```

## 2. 插件与 capability

| Capability | 插件 | 配置 |
|---|---|---|
| `loop_guard_policy` | `loop.policy.default` | repeat_warn, break_*, progress_* |
| `convergence_policy` | `convergence.policy.default` | producer_nudge_threshold |
| `tool_guards` | `tool.guards.service` | — |
| — | `guard.tool-timeout` | enabled |
| — | `guard.tool-result-spill` | max_inline_bytes |

Gate 插件 `requires=["loop_guard_policy"]`；`safe_executor.simple` `requires=["tool_guards"]`。

## 3. Think 链顺序（不变）

```text
10 repeat → 20 loop-breaker → 30 progress → 35 delivery → 40 terminal → 50 artifact
```

阈值来自 Profile `loop.policy.default` config，非硬编码 `DEFAULT_LOOP_POLICY`。

## 4. 不变量

| ID | 不变量 |
|---|---|
| GS1 | Guard 只读 Session fold / manifest；不 live-scan workspace |
| GS2 | Act guard 在 SafeExecutor 边界执行；不 bypass Body |
| GS3 | Advisory guard 不得 rewrite Decision（仅 GateDecided warn） |
| GS4 | 无效 guard config fail-loud at plugin load |
| GS5 | _catalog 在 `guard_stack.py`；新 guard 必须登记 tier/plane |

## 5. 关联

- [ADR-0196](0196-convergence-control-plane-and-prompt-surface.md) — 语义收敛
- [ADR-0191](0191-runtime-loop-dsh-convergence-and-control-plane.md) — 事实层 DSH 对齐
- `bundles/guard-stack.yaml` — 可选 guard 组合包
