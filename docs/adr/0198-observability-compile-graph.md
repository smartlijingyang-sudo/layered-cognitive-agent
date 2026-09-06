# ADR-0198 — Observability Compile Graph

## 状态

Accepted（2026-09-06）。**P0–P3 已落地**：config SSOT + `ObservabilityCompiler` + `JournalBindingEngine` + boot compile gate + doctor 读 CompiledPlan + journal fold yaml 驱动 merge。

**延伸**：ADR-0183/0186（Session SSOT）、0185（model-visible fold）、0193（Projection Fabric）、0195（四段链）。

## 0. 决策摘要

观测层采用与 MTK **同构**的 compile graph：

```text
yaml SSOT (config/)
    → ObservabilityCompiler.compile()
        → CompiledObservabilityPlan
            → FactGateway / Session / Persistence (生产)
            → FoldEngine + merge policies (消费)
            → OutputCoordinator (物化 journal / narrative / spine)
```

**固定骨架（G0）**：`FactGateway → Session.append → PersistenceObserver → FoldEngine`。

**可配置（yaml + 插件 Strategy）**：事件闭包、字段 binding、merge 策略、projection 注册、artifact manifest。

## 1. 配置目录

见 [`lca_kernel/events/config/README.md`](../../lca_kernel/events/config/README.md)。

| 层 | 文件 | 职责 |
|---|---|---|
| Closure | `observability/closure_catalog.yaml` | EP 语义层、producer seam、consumers、durable |
| Policy | `compile/global_policies.yaml` | 跨层 merge 禁止/降级 |
| Projection | `projections/registry.yaml` | deriver 注册 + bindings 引用 |
| Bindings | `projections/bindings/*.yaml` | 字段 extract + merge + precedence |
| Outputs | `outputs/run_artifacts.yaml` | artifact 路径 + source projection |

`observability/spine.yaml` 保留 EventRegistry 鉴权矩阵；closure_catalog **扩展**语义，不重复 category 行。

## 2. 不变量

| ID | 内容 |
|---|---|
| **I-OCG-1** | durable EP 必须在 closure_catalog 登记且 `durable: true` |
| **I-OCG-2** | 每 EP 语义上单一 `producer_seam` |
| **I-OCG-3** | journal 字段 merge 策略来自 bindings yaml，禁止硬编码 overwrite |
| **I-OCG-4** | L5 invocation span 不得覆盖 L3 evidence rich 字段（`fill_empty_only`） |
| **I-OCG-5** | `ObservabilityCompiler.compile()` 错误 → verify 脚本 exit 1 |
| **I-OCG-6** | `replay_projection(id, events)` 与 live fold 同一插件路径 |

## 3. 验证

```bash
uv run python scripts/verify_observability_compile_plan.py
uv run pytest tests/lca_kernel/events/test_observability_compile_plan.py -q
uv run pytest tests/lca_kernel/events/test_fold_merge.py -q
uv run pytest tests/lca_kernel/events/test_binding_engine.py -q
uv run pytest tests/lca_kernel/events/test_observability_boot_compile.py -q
```

## 4. 分期

| 阶段 | 内容 |
|---|---|
| P0 | config + compiler + merge + journal fold 接入 + verify |
| P1 | FoldEngine 全规则解释；declarative 路径补 llm.request.header |
| P2 | boot 门禁；doctor 读 CompiledPlan |
| P3 | 删 journal_fold 硬编码分支 |

**状态（2026-09-06）**：P1–P3 已实现；journal tool/thinking merge 走 `JournalBindingEngine`；`compile_observability_boot_plan()` 在 profile boot 门禁；doctor H-xref 从 closure_catalog 派生 phase fold EP 集。

## 5. delete-when

```text
journal_fold hardcoded tool merge:
  delete_when: FoldEngine 覆盖全部 journal.step_tree bindings 且有 parity 测试
```
