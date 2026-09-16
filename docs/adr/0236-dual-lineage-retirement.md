# ADR-0236 — Dual Lineage Retirement (删 `agent.run.phase` + `declarative-phase-graph` + `declarative-recovery`)

**Status:** Accepted — 2026-09-16. 同 PR 落地（PR-7 of `docs/superpowers/plans/2026-09-16-act-subgraph-tightening.md`）。

> **一句话**：一次性收口三套与 outer `phase.main.outer` 并行的图 / 边 SSOT，删 `bundles/agent/run_phase.yaml`、`bundles/declarative-phase-graph.yaml`、`bundles/declarative-recovery.yaml`；`profiles/benchmark.yaml` + `profiles/cordis-creator.yaml` 迁到 region-tag path；ADR-0210 升 Accepted。**No COMPAT shim** —— six-column-0206 M1 P0 已明令 Delete，不留跨 PR 后门。

## Context

`phase-graph-node-orchestration/03-six-column-0206.md` §6.3 Merge→Delete 行已认定 dual lineage 是 M1 P0 债：

- `agent.run.phase 线性外环` → Merge→Delete（与 outer `phase.main.outer` 重复，production profile 只能选其一）
- `declarative-phase-graph 边 SSOT` → Delete（与 outer YAML 双 ControlPlan）
- `declarative-recovery 独挂恢复边` → Delete（恢复边进 outer）

事实仍存在 delete-when 债务：

| Bundle | delete-when 条件 | 状态（修复前） |
|---|---|---|
| `bundles/agent/run_phase.yaml` | `N/A`(文档陷阱 —— `N/A ≠ 永不删`，是「当时未定」) | 仍存在 |
| `bundles/declarative-phase-graph.yaml` | All production profiles migrated to region-tag path **AND** ADR-0210 升 Accepted | `profiles/benchmark.yaml:37` + `profiles/cordis-creator.yaml:31` 仍引用；ADR-0210 README 索引仍标 Proposed |
| `bundles/declarative-recovery.yaml` | (无显式 delete-when，参考 six-column-0206 Delete 行) | `web-standard-recovery.yaml` 等 recovery profile 仍引用 |

**根因**：六阶段图被三套平行声明持有 —— (A) `agent.run.phase`（线性外环，旧 ADR-0220 §3.4 Layer 3 业务图）、(B) `declarative-phase-graph`（Cordis provider 旧 SSOT，0075 阶段闭集语义残留）、(C) outer `phase.main.outer`（typed-port 改造后的 v2 BundleGraphSpec，ADR-0217/0218/0221 唯一 production control spine）。三选二 = 双 SSOT = 违反 AGENTS.md C7 control/observation separation。

ADR-0221 cutover 已隐含「outer 是唯一 production control spine」；ADR-0230 删 `stop.main` 让 `terminal.commit` 接管 → `agent.run.phase` 的 `terminal.commit` 节点本身已与 outer 重复。剩余删除条件 = 一次性收口。

## Decision

一次性收口以下五项（**同 PR**，无跨 PR 后门）：

1. **删 `bundles/agent/run_phase.yaml`**：outer `phase.main.outer` 是唯一 production control spine；该 bundle 的 5 phase + terminal.commit 节点与 outer 重复，profile 不再挂载。
2. **删 `bundles/declarative-phase-graph.yaml`**：所有 edge 走 outer YAML。typed-port 改造后 outer 自含 recovery / loop budget 边，`phase.edge.standard` + `phase.execution_policy.resilient` 双 Cordis provider 概念删除。
3. **删 `bundles/declarative-recovery.yaml`**：recovery 边进 outer YAML。`reflect.main → think.main` 边谓词走 `routing.next_hint == admit_recovery`（outer `phase_main.yaml` 注释已说明该路径，`grep "admit_recovery" bundles/outer/phase_main.yaml` 当前命中 —— 表示 typed-port 改造已经把 recovery 集成进 outer）。
4. **改 `profiles/benchmark.yaml` + `profiles/cordis-creator.yaml`**：移除 `bundles/declarative-phase-graph.yaml` 引用，production path = region-tag path（ADR-0210 §6.5 P7 region-tag path）。
5. **ADR-0210 升 Accepted**：ADR-0210 自身 §6.1 - §6.6 全部段实施完成；production path 经 `profiles/web-assistant.yaml` 的 `regions.declare` 段验证。本 PR 落地后 delete-when 全部达成。

## Alternatives considered

| 提议 | 拒绝理由 |
|---|---|
| **(a) 维持 dual lineage** | 违反 AGENTS.md C7 control/observation separation + 双 SSOT（领域依赖层 §2.1「下层不得反向 import」+ 单向层）；ADR-0221 cutover 隐含「outer 是唯一 production control spine」 |
| **(b) 仅删 1 个 bundle** | 不彻底；remaining bundle 仍构成 dual SSOT；delete-when 条件分次达成 = 跨 PR 后门，违反 AGENTS.md §4「引入 compat shim 同一 PR 必须删」 |
| **(c) 一次收口 3 bundle + 2 profile + ADR-0210 升 Accepted** | **接受** —— AGENTS.md §4「引入 compat shim 同一 PR 必须删」+ six-column-0206 M1 P0 + ADR-0210 §九 Accepted 闸门（条件 8 自我循环触发） |
| **(d) 软迁移 + COMPAT shim 过渡** | 拒绝 —— six-column-0206 已明令 Delete `agent.run.phase` + `declarative-phase-graph` + `declarative-recovery`，不允许 compat 后门（PR-7 brief 顶部「No COMPAT shim」） |

## Consequences

### 删除 / 迁移

- `bundles/agent/run_phase.yaml` 删除
- `bundles/declarative-phase-graph.yaml` 删除
- `bundles/declarative-recovery.yaml` 删除
- `profiles/benchmark.yaml` 移除 `bundles/declarative-phase-graph.yaml` 引用
- `profiles/cordis-creator.yaml` 移除 `bundles/declarative-phase-graph.yaml` 引用
- ADR-0210 README 索引同步升 Accepted

### 回归保护

- `tests/integration/test_no_dual_lineage.py` 新增 —— 四条 guard：
  - `test_no_agent_run_phase_bundle`
  - `test_no_declarative_phase_graph_bundle`
  - `test_no_declarative_recovery_bundle`
  - `test_profiles_use_region_tag_path`（`benchmark.yaml` + `cordis-creator.yaml` 不再引用 `declarative-phase-graph` / `declarative-recovery` / `agent.run.phase`）

### 不在本次 PR 范围

- 其他 profile（`composio-enabled.yaml` / `oii-debug.yaml` / `web-standard-continuous.yaml` / `web-standard-recovery.yaml` / `self-improving-minimal.yaml` 等）仍引用 `declarative-*` 的问题：本次 PR 仅按 brief 范围迁移 `benchmark.yaml` + `cordis-creator.yaml`；其他 profile 由对应 owner 后续 PR 迁移（每条迁移需 owner + delete-when，符合本 ADR Consequences「分次迁移须 owner + verification」）。
- `profiles/web-standard-recovery.yaml:70` 的 `declarative-recovery.yaml` 引用：本 PR 不动（owner = recovery profile 维护者），待 follow-up。
- `lca/infrastructure/runtime_plane/capability_bindings.py:7` / `:107` 的注释 `agent.run.phase` 字面引用：仅 docstring 描述，不影响运行；后续清理。
- `tests/business/test_three_tier_graph_dispatch.py:85/91` 的注释 `agent.run.phase` 字面引用：仅 docstring 描述（ADR-0220 §3.4 三层图示意），不影响运行。

### 不变量

| ID | 不变量 | 落点 |
|---|---|---|
| **0236-I-1** | outer `phase.main.outer` 是唯一 production control spine | `bundles/outer/phase_main.yaml`；C1 认知闭集六阶段闭包 |
| **0236-I-2** | 所有 edge（含 recovery / loop budget）走 outer YAML 单 SSOT | C7 控制 / 观察分离；typed-port 契约 |
| **0236-I-3** | region 标签不绑定 capability 闭集（继承 ADR-0210 P7-I-2） | `bundles/outer/phase_main.yaml::region` 字段 = `phase:<name>`；C5 能力三维单调 |
| **0236-I-4** | production profile 不再挂载 `declarative-*` 或 `agent.run.phase` | `profiles/benchmark.yaml` + `profiles/cordis-creator.yaml` 迁移完成；follow-up 迁移其他 profile |
| **0236-I-5** | 回归测试守护：3 个 bundle + 2 个 profile 不再含 dual lineage 字面 | `tests/integration/test_no_dual_lineage.py` |

## Refines / Fixes

- ADR-0075（Superseded by 0210 partial）—— `declarative-phase-graph` 是 0075 阶段闭集 SSOT 的残留；本 ADR 删 bundle 完成 0075 闭集退出。
- ADR-0194（Superseded by 0210 partial）—— `declarative-recovery` 是 0194 Loop 收敛中独挂恢复边的残留；本 ADR 删 bundle 完成 0194 恢复边退出。
- ADR-0210（Accepted — 2026-09-09）—— §6.6 production path 验证 = `profiles/web-assistant.yaml` 的 `regions.declare` 段（独立路径）；本 ADR 关闭 §6.6 后续的「其他 production profile 迁到 region-tag path」章节。
- ADR-0220 §3.4 三层图 —— Layer 3 业务图 `agent.run.phase` 删除；Layer 2 subgraph 引用通过 outer `phase.main.outer` 的 `sub_spec_ref` 间接挂载（语义不变）。
- ADR-0221 cutover —— 「outer 是唯一 production control spine」原则正式化为 ADR（cutover 已隐含；本 ADR 明示）。
- ADR-0230 stop-decision retirement —— `terminal.commit` 节点已接管 `stop.main`；本 ADR 让 `terminal.commit` 在 outer plan 内唯一持有，消除 `agent.run.phase` 的同节点重复。

## Acceptance

| ID | 条件 | 验证 |
|---|---|---|
| 0236-Accepted-1 | 3 个 bundle 删除 | `ls bundles/agent/run_phase.yaml bundles/declarative-phase-graph.yaml bundles/declarative-recovery.yaml` 均不存在 |
| 0236-Accepted-2 | 2 个 profile 迁移完成 | `grep "declarative-phase-graph\|declarative-recovery\|agent\.run\.phase" profiles/benchmark.yaml profiles/cordis-creator.yaml` 无命中 |
| 0236-Accepted-3 | ADR-0210 README 索引升 Accepted | `docs/adr/README.md` 中 0210 行 status 字段 = Accepted |
| 0236-Accepted-4 | outer `phase.main.outer` 含 recovery 路径说明 | `grep "admit_recovery" bundles/outer/phase_main.yaml` 命中（typed-port 改造后注释已说明） |
| 0236-Accepted-5 | 回归测试四条 guard 全绿 | `pytest tests/integration/test_no_dual_lineage.py -v` |
| 0236-Accepted-6 | PR-7 acceptance P7.A1–A10 全绿 | `docs/superpowers/plans/2026-09-16-act-subgraph-tightening.md` PR-7 acceptance 表 |

## commit 链（PR-7 单 PR）

```
docs(adr): ADR-0236 dual lineage retirement (Accepted 同 PR)
refactor(graph): retire dual lineage A/B/C debt (PR-7, ADR-0236)
```

PR-7 完整 commit 信息见 brief `Step 7.2.5`。
