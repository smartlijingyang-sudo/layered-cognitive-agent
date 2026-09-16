# act 子图收紧与卫生 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan PR-by-PR. Each PR is a separate gate. Use superpowers:test-driven-development inside each Task.

**Goal:** Close 6 act-subgraph issues surfaced by the 2026-09-16 review (audit base: `traces/runs/{run_3383288d63e7, run_3cf6e7c036b3, run_feb0f21ee770}`). Cover补齐 (4 项) + 加强 (1 项) + 垃圾清理 (5 类) + ADR/Note 立项 (3 份)。

**Architecture:** Umbrella of 7 独立 PR(6 串行 + 1 独立),每个 PR 自包含可独立 review、可独立 revert。PR-6 引用整个 run-health plan(PR-1 health contract / PR-2 B-1 multi-call / PR-3 N:N fanout);其余 5 PR 全自写;PR-7 独立处理 dual lineage 债。每 PR 含 1–3 Task,先 ADR 再 code,先 fail-test 再 implement。

**Tech Stack:** Python ≥ 3.11, Pydantic v2 frozen `extra="forbid"`, existing typed-port kernel (`lca/framework/graph/` + `lca/contracts/protocols/graph/`), existing `@plugin(...)` carrier (PR-3.7.a 路径,手写不用 `@graph_node`).

**Spec / Companion plans:**
- 评审输入(问题点源):本轮评审报告(详见 §A 「来源」)
- 已立项 + 引用:
  - `docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md` PR-3 Task 3.1–3.6 (N:N fanout / PARALLEL default)
  - `docs/superpowers/specs/2026-09-14-typed-port-graph-redesign-design.md` §0 (typed-port 5 闸外提的 typed-port 基础)
  - `docs/superpowers/specs/2026-09-15-pr3.8-borrowed-nodes-design.md` §2.6 + §3.2(spec 已预言 gate 应在 act_subgraph 内,本 PR-1 落实)
- 必须新立的 ADR/Note:
  - **ADR-0234** PipelineSafeExecutor 5 闸外提 (PR-2 前,Accepted 才合 PR-2)
  - **ADR-0235** act.envelope C13 卫生(metadata 反抽到 typed port)+ 「act 业务不知道图存在」边界硬约束 (PR-5 前)
  - **ADR-0236** dual lineage debt 收口(删 agent.run.phase + declarative-phase-graph + declarative-recovery, ADR-0210 升 Accepted)(PR-7 前)
  - **Agent Note `contract/2026-09-16-act-observe-normalize-split.md`** (PR-3 前,proposed → implemented)
  - **Agent Note `contract/2026-09-16-act-observe-commit-fact-split.md`** (PR-3 内,proposed → implemented;RunFact commit 拆到独立节点)
  - ADR-0232 / ADR-0233 引用 run-health spec,本 plan 不重写

---

## A 来源(评审事实底稿)

上一轮评审报告识别的 5 处问题点 + 1 处 C13 违反 + 5 类垃圾。本 plan 把它们结构化为 6 PR + 总垃圾清单。

| # | 问题点 | 评审节 | PR | 优先级 |
|---|---|---|---|---|
| F-1 | `act.approve.gate` 当前在 outer `phase_main.yaml` `act.main → act.approve.gate → ...` 上,位置是「副作用之后」而非 spec §3.2 与 six-column-0206 M1 §2 要求的「`act.authorize` 与 `act.envelope` 之间」(副作用之前) | 评审 §6.1 + 现场 grep 验证(bundles/outer/phase_main.yaml:128-278 + 注释 255-262 自承认) | PR-1 | P0 |
| F-2 | `PipelineSafeExecutor.execute` 150 行方法把 5 闸内化,违反 graph-visible | 评审 §6.2 | PR-2 (含 ADR-0234) | P1 |
| F-3 | `act.observe` 同时承担 normalize + terminate_decide + RunFact 3 事 | 评审 §6.3 | PR-3 (含 Agent Note) | P2 |
| F-4 | `act.fanout / join` 1:1 only,N:N + PARALLEL 默认待 M3 | 评审 §6.4 | **引用** run-health PR-3 (已立项,owner = run-health) | P1 |
| F-5 | `_FAILURE_KIND_TO_ERROR_REASON` 在节点内定义,违反 C11 闭集原则 | 评审 §6.5 | PR-4 | P2 |
| F-6 | `act.envelope` 把 `state / decision` 塞 metadata,绕过 typed-port,违反 C13 | 评审 §4.2 表第一行 | PR-5 (含 ADR-0235) | P0 |

**重复立项自检:**
- F-4 不重写——run-health plan PR-3 已经包含 Task 3.1 ADR + Task 3.2/3.3/3.4/3.5/3.6 code,本 plan 只标注 owner + 加 1 条 acceptance「act.observe 的 `next_hint="fanout_ntom"` 检测」
- F-1 修正位置错误:评审报告与原 plan 都按「outer-edge 未上」叙述,现场 grep 证实 wiring 已在 `bundles/outer/phase_main.yaml` 落地(commit `f4ee5363b` PR-3.8.6),但位置违反 spec §3.2 与 six-column-0206 M1 §2 — gate 应在 `act.authorize` 与 `act.envelope` 之间(副作用未发才可断),而非 `act.main` 之后(副作用已发才回放)。本 PR-1 任务是把 wiring 从 outer 迁到 act_subgraph 内部。

---

## Global Constraints

- **No COMPAT shim** (AGENTS.md §4):引入 compat shim 的同一 PR 必须删;无 delete-when = 红灯。
- **No new phase / no new EP name** (AGENTS.md §3 C1):本 plan 不开第七 phase,不引入 `EXECUTION_POINTS` 新成员。
- **No new EP name**:F-3 加 `next_hint="terminate_decided"` 字符串时,**仅 metadata 字段**,不注册新 EP。
- **Cognitive closed set** (C1):`act.observe` 拆节点仍在 `phase:act` 内。
- **Reducer single-write** (C4):拆出去的 `act.observe.terminate_decide` 仍只 emit typed port,Reducer 单写 State。
- **Capability monotonic** (C5):PR-1 wiring 不放宽 grant。
- **Execution narrow door** (C10):PR-2 拆 5 闸时,**dispatch / execute / safe-boundary 不变**,仅把 envelope 内部 5 闸中的「permission/grant/budget/reservation」部分移到 graph。
- **Event closed set** (C11):PR-4 移 `_FAILURE_KIND_TO_ERROR_REASON` 不新增 EP,只是 typed-闭集搬家。
- **Information lineage closed** (C13):PR-5 必须 typed-port,禁 metadata 绕。
- **Determinism** (C8):新节点无时间/PID/env 依赖。
- **Idempotency** (C9):PR-2 / PR-3 不破坏 idempotency_key 语义。
- **Conventional commits**, commit 信息 `<type>(<scope>): <subject>` + body「做了什么 / 为什么」,PR 标题引用 ADR/Note + 本 plan。
- **Lint gates per PR:** `ruff check --fix` + `ruff format` + `lint-imports` + `mypy lca` + `pytest tests/<region>/` + `./scripts/lca-ops plan tree web-standard` + `./scripts/lca-ops validate_profile_plans profiles/web-standard.yaml` + `./scripts/lca-ops audit-state-writers` (本 PR-1/2/3 引入的) + `./scripts/lca-ops why <capability>` (PR-1)。
- **No `--no-verify`**。
- **Owner + delete-when**:每条 garbage item 必须 owner + verification test。
- **每个 PR 独立 commit + 独立 review + 独立 revert**;不交叉 commit 编号。

---

## PR 依赖与执行顺序

```text
PR-1 (P0): act.approve.gate outer-edge wiring + boot fail-loud
   ↓ (不需要 PR-2/3/4/5 依赖,可并行)
PR-2 (P1, ADR-0234): PipelineSafeExecutor 5 闸外提 effect.pre_dispatch.envelope_check
   ↓
PR-3 (P2, Agent Note): act.observe 拆 normalize vs terminate_decide
   ↓
PR-4 (P2): _FAILURE_KIND_TO_ERROR_REASON 移 contracts
   ↓
PR-5 (P0, ADR-0235): act.envelope C13 卫生 metadata → typed port
   ↓
PR-6 (引用): run-health plan PR-3 已立的 N:N fanout (本 plan 不写 task,仅 acknowledgement + acceptance 校验)
```

执行策略:**PR-1 / PR-7 立刻开**(P0 / P1,owner = graph kernel team,PR-1 无 ADR 阻塞,PR-7 需先写 ADR-0236);**PR-2 / PR-5 / PR-7 等 ADR Accepted**(AGENTS.md §1 决策表「改变 SSOT / 契约 / 边界 → 先 ADR」);**PR-3 / PR-4 无 ADR 阻塞但需 Note**(Note proposed → implemented 与 PR 同合);**PR-6 引用整个 run-health plan 3 PR 落地**(PR-1 health / PR-2 multi-call / PR-3 N:N fanout)。

并行窗口:
- **PR-1 / PR-3 / PR-4 / PR-7** 可同时 dispatch(file 互锁为零)
- **PR-2 / PR-5 串行**(PR-2 改 pipeline_safe_executor.py / act_subgraph.yaml / effect_execute.yaml;PR-5 改 envelope.py / dispatch.py / composition.py / effect_execute.yaml;effect_execute.yaml + pipeline_safe_executor.py 互锁)
- **PR-6 独立**(纯引用)

并行窗口:PR-1 / PR-3 / PR-4 可同时 dispatch(无 file 互锁);PR-2 / PR-5 串行各自前后(PR-2 改 PipelineSafeExecutor.execute 内部,PR-5 改 act.envelope 签名,两者都在 effect gateway 周围但不同文件)。

---

## 总垃圾清单(garbage inventory)

每条 garbage item 必须有 owner、delete-when、verification test。所有垃圾必须在对应 PR 内删除,无跨 PR 后门。

| ID | Garbage | 当前位置 | Owner PR | Verification | Delete-when |
|---|---|---|---|---|---|
| G-1 | `_action_to_phase` dict 在 `simple_body.py:69-77` 与 ADR-0169 PR-26 task-25 重复声明 phase 推进表 | `lca/cognition/body/executor/simple_body.py:69-77` | **PR-1 收尾**(移到 `lca/nodes/act/_phase_table.py` typed-port 单源) | `grep -rn "_ACTION_TO_PHASE" lca/` 唯一源是 `lca/nodes/act/_phase_table.py` | G-1 verification: `_ACTION_TO_PHASE` 引用在 1 个文件 1 个函数内 |
| G-2 | `PipelineSafeExecutor.execute` 内 5 闸 procedure call 重复 `act.authorize` 节点职责 | `lca/cognition/body/executor/pipeline_safe_executor.py:280-330` | PR-2(ADR-0234) | 新增 `effect.pre_dispatch.envelope_check` 节点测试通过 + `PipelineSafeExecutor.execute` 减行 ≥ 80 行 | G-2 verification: PR-2 acceptance |
| G-3 | `act.observe` 内 `should_terminate` 决策与 normalize 串在 1 节点 | `lca/nodes/act/observe/observe.py:169-179` | PR-3(Note) | 新增 `act.observe.terminate_decide` 节点 + 现有 act.observe 不再有 should_terminate 决策 | G-3 verification: PR-3 acceptance |
| G-4 | `_FAILURE_KIND_TO_ERROR_REASON` 在节点内 dict,违反 C11 闭集 | `lca/nodes/act/observe/observe.py:55-65` | PR-4 | contracts 新建 `lca/contracts/observability/observability/failure_reason_map.py` + 节点导入 + 节点内 dict 删 | G-4 verification: `grep -rn "_FAILURE_KIND_TO_ERROR_REASON" lca/` 仅 contracts 1 处 |
| G-5 | `act.envelope.metadata` 把 `state / decision` 塞入,绕过 typed-port,违反 C13 | `lca/nodes/act/envelope/envelope.py:78-86` | PR-5(ADR-0235) | `act.envelope` 的 `declared_inputs` 增加 `(decision, state)`,metadata 仅保留 `effect_class / operation` typed 字段 | G-5 verification: `grep -rn "metadata=.state" lca/nodes/act/` 仅 typed-port 接受处 |
| G-6 (引用) | `act.fanout / act.join` 1:1 退化的 `next_hint="fanout_1to1"` 字面量 | `lca/nodes/act/fanout.py:92` + `lca/nodes/act/join.py:107` | **引用 run-health PR-3**(本 plan 不删) | run-health PR-3 落地后 `next_hint="fanout_ntom"` 上线 | G-6 verification: run-health PR-3 acceptance |
| G-7 | PipelineSafeExecutor 内 `executor.permission:allow` / `executor.reservation:valid` / `executor.grant:valid` / `executor.plan-boundary:valid` / `executor.pipeline:completed` 5 个本地 verdict_refs 是**第二套语义词表**,与 graph canonical `act.*` / `effect.pre_dispatch.*` 冲突 | `lca/cognition/body/executor/pipeline_safe_executor.py:284/297/303/308/327` | PR-2(随 5 闸外提同步删) | 5 闸迁到 `effect.pre_dispatch.envelope_check` 节点后,`PipelineSafeExecutor.execute` 内 5 个 `executor.*` verdict_refs 同步删除,统一由 graph 节点产出 | `grep -rn "executor\.\(permission\|reservation\|grant\|plan-boundary\|pipeline\)" lca/cognition/` = 0 matches |
| G-8 | Dual lineage debt:`agent.run.phase` + `declarative-phase-graph` + `declarative-recovery` 三套平行图 / 边 SSOT 与 outer `phase.main.outer` 共存 | `bundles/agent/run_phase.yaml:34` + `bundles/declarative-phase-graph.yaml:7-19` (delete-when) + `bundles/declarative-recovery.yaml` + `profiles/benchmark.yaml:37` / `profiles/cordis-creator.yaml:31` 仍引用 | **PR-7(独立 P1, ADR-0236)** | agent.run.phase 删除 / declarative-* bundle profile 全切到 region-tag path / ADR-0210 升 Accepted | `grep -rn "declarative-phase-graph\|declarative-recovery\|agent\.run\.phase" bundles/ profiles/ lca/` 仅 outer `phase.main.outer` 引用 |
| G-9 | `act.approve.gate` 内部用 `getattr(context.runtime, name, None)` 偷图 runtime 字段——同 L-1 性质的「act 业务不知道图存在」越界 | `lca/nodes/intervene/approve_gate.py:78-87` | **PR-5 同步扩**(PR-5 已扩边界硬约束,本项是边界验证发现的具体越界点) | approve_gate 节点只读 typed port `decision / command`,不读 `context.runtime.*` | `grep -rn "context\.runtime\|getattr.*runtime" lca/nodes/intervene/` = 0 matches |

---

## 总验收矩阵(umbrella acceptance)

| ID | Criterion | Verification |
|---|---|---|
| U-1 | PR-1 / PR-2 / PR-5 / PR-3 / PR-4 / PR-6 / PR-7 全部 landed(PR-1~6 顺序由 self-review §4 锁定,PR-7 独立并行)+ 每个 PR 通过自己 acceptance + 跑通 boot/restart 健康检查 | `./scripts/lca-ops kernel-restart` 0 退出;curl /health 200 |
| U-2 | PR-6 引用段(整个 run-health plan 3 PR + restart-safety R-1~R-5 / old-run O-1~O-5 / forward-compat F-1~F-3) 同步落地;umbrella plan 不留 ungrounded acceptance | run-health plan PR-1/2/3 全 landed;restart/old-run/forward-compat 13 guarantee 全 verified |
| U-3 | 所有 G-1 ~ G-9 garbage 在对应 PR 内删除;无跨 PR 后门;每个 garbage item 的 verification 跑通 | 各自 verification 命令 exit 0 |
| U-4 | AGENTS.md §3 C1–C13 不变量在本 plan 全部 PR 保持 | 每 PR verification matrix 加「C1–C13 持有」勾选 |
| U-5 | `web-standard` profile 15 plans validated (pre/post same) | `./scripts/lca-ops validate_profile_plans profiles/web-standard.yaml` |
| U-6 | 3 个 audit run (`run_3383288d63e7`, `run_3cf6e7c036b3`, `run_feb0f21ee770`) 仍可读 + `lca-ops runs health <run_id>` 不报新 failure | `tests/integration/test_old_runs_still_readable.py`(引用 run-health plan) |
| U-7 | ADR-0234(PR-2)/ ADR-0235(PR-5)/ ADR-0236(PR-7) status = Accepted | `docs/adr/README.md` 索引 |
| U-8 | Agent Note `contract/2026-09-16-act-observe-normalize-split.md` status = implemented | `docs/notes/` 树 |

---

# PR-1: act.approve.gate 位置修正 — 迁回 act_subgraph 内部 + boot fail-loud

> **Owner**: graph kernel team
> **Priority**: P0
> **Closes**: 评审 §6.1(事实修正版 — 现场 grep 验证 wiring 已在 `bundles/outer/phase_main.yaml:128-278` 落地,但位置违反 spec §3.2 与 six-column-0206 M1 §2「副作用未发才可断」)
> **Predecessor**: PR-3.8.6 已落(commit `f4ee5363b`;节点 + 测试 + outer wiring + 注释自承「The ideal integration puts the gate INSIDE act.subgraph — outside this PR's edit scope」)
> **No ADR required**(纯 graph wiring 位置修正 + 已有 typed-port `approval_required` 字段新增;`approval_resume_node` boot fail-loud 是 plan_sdk.py:256 已有字段的「强校验」扩展,不破坏契约)
> **事实差异**:评审报告 §6.1 把 wiring 描述成「未落地」,现场事实是「落地但位置错」;本 PR 任务从「加 wiring」改为「迁 wiring」+「boot fail-loud」+「顺手 G-1」

## PR-1 真实任务清单

1. **Task 1: 从 outer `phase_main.yaml` 删除 `act.main → act.approve.gate` 与 `act.approve.gate → {intervene.interrupt / reflect.main / terminal.commit}` 边**(位置错误的 wiring);保留 `intervene.resume → act.approve.gate` 边(resume 跨子图,必须在 outer)。
2. **Task 2: 在 `bundles/act/act_subgraph.yaml` 加 `act.authorize → act.approve.gate` + `act.approve.gate → intervene.interrupt / act.envelope / terminal.commit`**(spec §3.2 真正要求的「副作用前中断」位置);`act.approve.gate` 节点 id 不变,只改 wiring 位置。
3. **Task 3: `act.authorize` 节点加 typed `approval_required: bool` 输出**(`envelope.py:78-86` 里 `state / decision` 在 PR-5 抽 typed,本 PR 不动 metadata,只增加 typed-port `approval_required` 让边谓词可 typed 读);`act.envelope` 的 typed-port 同步升级在 PR-5 做。
4. **Task 4: boot fail-loud — `validate_profile_plans` 检测 `act.approve.gate` 存在但 `intervene.resume → act.approve.gate` 边缺失 → raise `PlanLiftError(reason="missing approval_resume_node edge for act.approve.gate", node_id="act.approve.gate")`**。
5. **Task 5: G-1 收尾 — `_ACTION_TO_PHASE` 移到 `lca/nodes/act/_phase_table.py` typed-port 单源**。
6. **Task 6: 跑整体 verify**(`ruff / lint-imports / plan tree / validate_profile_plans / pytest / audit-state-writers / why approve`)。

## PR-1 Task 1: 从 outer bundle 删除错位 wiring

> **关键背景**:当前 `bundles/outer/phase_main.yaml:128-278` 的 wiring 错位(`act.main` 之后,违反 spec §3.2)。本 Task 把 wiring 从 outer 迁到 act_subgraph 内部;**不**重新加 5 条 outer edge,因为已经有。

**Files:**
- Modify: `bundles/outer/phase_main.yaml`(删 4 条错位边:`act.main → act.approve.gate`、`act.approve.gate → intervene.interrupt`、`act.approve.gate → reflect.main`、`act.approve.gate → terminal.commit`;**保留** `intervene.resume → act.approve.gate` resume 跨子图边)
- Modify: `bundles/outer/phase_main.yaml`(删除 `act.approve.gate` 节点本身的 outer 声明,因为它迁到 act_subgraph 内部)
- Modify: `bundles/outer/phase_main.yaml`(删 commit `f4ee5363b` 引入的注释 128-162 + 228-262;保留 resume 边与 `intervene.interrupt/resume` sub_spec_ref)

**Step 1.1: 写 failing test — outer 不再有错位边**

```python
# tests/act/test_approve_gate_outer_edge_relocated.py
from pathlib import Path
from lca.framework.graph.subgraph_resolver import BundleSubgraphResolver


def test_outer_phase_main_has_no_approve_gate_relocated_edges():
    """PR-1: 错位 wiring 必须从 outer 迁走。"""
    plan = BundleSubgraphResolver().resolve(
        "bundles/outer/phase_main.yaml", runtime=None,
    )
    edges = {(e.source, e.target) for e in plan.phase_graph.edges}
    # 错位边: act.main → act.approve.gate
    assert ("act.main", "act.approve.gate") not in edges
    # 错位边: act.approve.gate → {reflect.main, terminal.commit, intervene.interrupt}
    assert ("act.approve.gate", "reflect.main") not in edges
    assert ("act.approve.gate", "terminal.commit") not in edges
    assert ("act.approve.gate", "intervene.interrupt") not in edges
    # 保留: resume 跨子图边
    assert ("intervene.resume", "act.approve.gate") in edges
```

Run: `pytest tests/act/test_approve_gate_outer_edge_relocated.py -v`
Expected: FAIL — 当前 outer 还有这些错位边

**Step 1.2: 从 `phase_main.yaml` 删错位边 + 节点声明**

`bundles/outer/phase_main.yaml:128-162`(`act.approve.gate` 节点声明块 + 注释)整段删除。

`bundles/outer/phase_main.yaml:228-262`(`act.main → act.approve.gate` outer edge + 注释)删除。

`bundles/outer/phase_main.yaml:264-282`(`act.approve.gate` → 4 个下游的 4 条边)删除,但**保留** resume 跨子图边(在文件后续 resume 块)。

**Step 1.3: 跑测试 verify pass**

Run: `pytest tests/act/test_approve_gate_outer_edge_relocated.py -v`
Expected: PASS

## PR-1 Task 2: 把 wiring 落到 act_subgraph 内部(spec §3.2 真正要求的位置)

**Files:**
- Modify: `bundles/act/act_subgraph.yaml`(在 `act.authorize` 与 `act.envelope` 之间插入 `act.approve.gate` 节点 + 5 条边)
- Modify: `lca/nodes/act/authorize/authorize.py`(新增 typed `approval_required: bool` 输出)

**Step 1.4: 写 failing test — act_subgraph 内部 wiring 正确**

```python
# tests/act/test_approve_gate_subgraph_wiring.py
def test_act_subgraph_has_approve_gate_between_authorize_and_envelope():
    plan = BundleSubgraphResolver().resolve("bundles/act/act_subgraph.yaml", runtime=None)
    edges = {(e.source, e.target) for e in plan.phase_graph.edges}
    assert ("act.authorize", "act.approve.gate") in edges
    assert ("act.approve.gate", "act.envelope") in edges
    assert ("act.approve.gate", "intervene.interrupt") in edges
    assert ("act.approve.gate", "terminal.commit") in edges
```

Run: `pytest tests/act/test_approve_gate_subgraph_wiring.py -v`
Expected: FAIL — act_subgraph 还没插

**Step 1.5: 改 `act.authorize` 节点加 typed `approval_required` output**

`lca/nodes/act/authorize/authorize.py:50-51`:
```python
declared_inputs: tuple[PortName, ...] = ("decision",)
declared_outputs: tuple[PortName, ...] = ("decision", "approval_required")
```

并在 `node_execute` 末尾:
```python
approval_required = bool(decision.extra.get("needs_approval", False))
return NodeOutput(
    port_values={"decision": decision, "approval_required": approval_required},
)
```

**Step 1.6: 改 `act_subgraph.yaml` 插入节点 + 边**

在 `bundles/act/act_subgraph.yaml` 中,定位到 `act.authorize` 节点后,插入 `act.approve.gate`:

```yaml
# PR-1: spec §3.2 真正位置 — act.authorize 与 act.envelope 之间
- id: act.approve.gate
  region: intervene
  factory: act.approve.gate
  inputs: [decision]
  outputs: [decision, routing]
  config:
    emit_on_enter: []
    emit_on_exit: []
```

并在 edges 段加 5 条边:
```yaml
- from: act.authorize
  to: act.approve.gate
  when:
    kind: eq
    port: { name: approval_required }
    value: true
- from: act.authorize
  to: act.envelope
  when:
    kind: eq
    port: { name: approval_required }
    value: false
- from: act.approve.gate
  to: act.envelope
  when:
    kind: in
    port: { name: routing, field: next_hint }
    values: [approve_skipped, approve_approved]
- from: act.approve.gate
  to: intervene.interrupt
  when:
    kind: eq
    port: { name: routing, field: next_hint }
    value: approve_interrupt
- from: act.approve.gate
  to: terminal.commit
  when:
    kind: eq
    port: { name: routing, field: next_hint }
    value: approve_rejected
```

(注:`intervene.interrupt` 与 `terminal.commit` 是 outer plan 节点;act_subgraph 的边引用它们是允许的,因为 `sub_spec_ref` 把外层节点暴露给内层。)

**Step 1.7: 跑测试 verify pass**

Run: `pytest tests/act/test_approve_gate_subgraph_wiring.py -v`
Expected: PASS

## PR-1 Task 3: boot fail-loud — `approval_resume_node` 边缺失检测

**Files:**
- Modify: `lca/framework/graph/lifter.py`(新增 `_validate_approval_resume_node` 函数,在 `lift_plan` 链中调用)

**Step 1.8: 写 failing test — boot fail-loud**

```python
# tests/integration/test_outer_edge_fail_loud_missing_resume.py
import pytest
from lca.framework.graph.subgraph_resolver import BundleSubgraphResolver
from lca.framework.graph.errors import PlanLiftError


def test_missing_approval_resume_node_raises_planlifterror(tmp_path):
    """profile 含 act.authorize 但缺 intervene.resume → act.approve.gate 边 → PlanLiftError。"""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("""
id: bad.subgraph
region: act
nodes:
  - id: act.authorize
    factory: act.authorize
    inputs: [decision]
    outputs: [decision, approval_required]
  - id: act.envelope
    factory: act.envelope
    inputs: [decision]
    outputs: [envelope]
  - id: act.approve.gate
    factory: act.approve.gate
    inputs: [decision]
    outputs: [decision, routing]
edges:
  - {from: act.authorize, to: act.approve.gate, when: true}
  - {from: act.approve.gate, to: act.envelope, when: true}
  # 故意缺 intervene.resume → act.approve.gate 跨子图 resume 边
""", encoding="utf-8")

    with pytest.raises(PlanLiftError) as exc:
        BundleSubgraphResolver().resolve(f"bundles/{bad_yaml.name}", runtime=None)
    assert "approval_resume_node" in str(exc.value)
```

Run: `pytest tests/integration/test_outer_edge_fail_loud_missing_resume.py -v`
Expected: FAIL — lifter 还没识别 missing resume edge

**Step 1.9: 改 `lca/framework/graph/lifter.py`**

在 `lifter.py` 顶部 import 后,新增:

```python
def _validate_approval_resume_node(plan: CompiledRunPlan) -> None:
    """If plan contains act.approve.gate, must have cross-subgraph resume edge.

    Fail-closed: HITL without resume edge is unsafe — interrupt can
    pause but never recover.
    """
    node_ids = {n.id for n in plan.phase_graph.nodes}
    if "act.approve.gate" not in node_ids:
        return
    resume_edge_present = any(
        e.source == "intervene.resume" and e.target == "act.approve.gate"
        for e in plan.phase_graph.edges
    )
    if not resume_edge_present:
        raise PlanLiftError(
            "missing approval_resume_node edge for act.approve.gate "
            "(intervene.resume → act.approve.gate required; HITL without "
            "resume edge is unsafe — interrupt can pause but never recover)",
            plan_id=getattr(plan, "profile_path", None),
            node_id="act.approve.gate",
        )
```

在 `lift_plan()` 调用链(从 yaml 路径 lift 到 CompiledRunPlan 后)插入 `_validate_approval_resume_node(plan)`。

**Step 1.9.1: 同步改 `plan_sdk.py` `approval_resume_node` 字段语义(L-8)**

> **为什么**:`approval_resume_node` 字段定义在 `lca/framework/graph/plan_sdk.py:256-263` + `:536`,但**语义是「optional metadata」**。Step 1.9 lifter 校验后,字段语义应升级为「required when act.approve.gate in plan」,否则 yaml 顶层 `approval_resume_node: foo` 与 lifter 校验会双 SSOT,boot 时不一致。

**Files:**
- Modify: `lca/framework/graph/plan_sdk.py`(`approval_resume_node` 字段定义加 docstring 说明语义)
- Modify: `lca/framework/graph/plan_sdk.py:_parse_plan`(`approval_resume_node` 字段读取同步)

```python
# plan_sdk.py plan() 函数 docstring 增:
"""Build a :class:`Plan`.

``approval_resume_node`` 字段语义(PR-1 升级):
- 当 plan 含 ``act.approve.gate`` 节点时,此字段 MUST 设置(值 = resume 边 target 节点 id)
- 当 plan 不含 ``act.approve.gate`` 节点时,此字段 ignored(yaml 可省)
- lifter 校验:`_validate_approval_resume_node(plan)` 强制(Step 1.9)
"""
```

```python
# _parse_plan() 函数,读取 approval_resume_node 后,加注释:
# PR-1: 字段语义升级——lifter 阶段会强制要求 act.approve.gate 存在时非空。
# 这里只读不强制(避免破坏 yaml 解析链;强制在 lifter)。
```

**Step 1.9.1 verification:**

```bash
grep -n "approval_resume_node" lca/framework/graph/plan_sdk.py
```

Expected: 3 处引用(plan() docstring / Plan 字段 / _parse_plan 读取),lifter 在 Step 1.9 引用,无第二 SSOT。

**Step 1.10: 跑测试 verify pass**

Run: `pytest tests/integration/test_outer_edge_fail_loud_missing_resume.py -v`
Expected: PASS

## PR-1 Task 4: G-1 收尾 — `_ACTION_TO_PHASE` 单源化

**Files:**
- Create: `lca/nodes/act/_phase_table.py`
- Modify: `lca/cognition/body/executor/simple_body.py:69-77`(改为 import)

**Step 1.11: 新建 typed-port 单源**

```python
# lca/nodes/act/_phase_table.py
"""Single-source phase-advance table (G-1 garbage).

PR-1 closes the duplicated _ACTION_TO_PHASE dict that lived both in
lca/cognition/body/executor/simple_body.py (advance target lookup)
and conceptually in the act node waterfall. After this PR, the typed-
port advance table is the single SSOT.
"""
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.observability.cursor.loop_cursor import PhaseName

ACTION_TO_PHASE: dict[str, PhaseName] = {
    ActionType.USE_TOOL.value: "act",
    ActionType.DELEGATE.value: "act",
    ActionType.HANDOFF.value: "act",
    ActionType.STOP.value: "stop",
    ActionType.ASK_HUMAN.value: "stop",
}
```

**Step 1.12: 改 `simple_body.py`**

`lca/cognition/body/executor/simple_body.py:1-3` import 区加:
```python
from lca.nodes.act._phase_table import ACTION_TO_PHASE
```

`lca/cognition/body/executor/simple_body.py:69-77` 删除整个 `_ACTION_TO_PHASE: dict[str, PhaseName] = {...}` dict,改为 `from lca.nodes.act._phase_table import ACTION_TO_PHASE`。

`_advance_cursor_for_action` 函数(行 308-315)改用 `ACTION_TO_PHASE.get(action_type)`。

**Step 1.13: G-1 verification**

```bash
grep -rn "_ACTION_TO_PHASE\|ACTION_TO_PHASE" lca/
```

Expected: 仅 `lca/nodes/act/_phase_table.py:14` 一处定义 + `simple_body.py` 一处 import,无重复 dict。

## PR-1 Task 5: 整体 verify + commit

**Step 1.14: 整体 verify**

```bash
ruff check --fix
ruff format
./scripts/lint-imports.sh
./scripts/lca-ops plan tree web-standard
./scripts/lca-ops validate_profile_plans profiles/web-standard.yaml
pytest tests/act tests/intervene tests/lca_kernel/boot -q
./scripts/lca-ops audit-state-writers
./scripts/lca-ops why approve
```

Expected: 全 exit 0;`why approve` 显示 monotonicity lineage。

**Step 1.15: Commit**

```bash
git add bundles/outer/phase_main.yaml bundles/act/act_subgraph.yaml
git add lca/nodes/act/authorize/authorize.py
git add lca/nodes/act/_phase_table.py lca/cognition/body/executor/simple_body.py
git add lca/framework/graph/lifter.py
git add tests/act/test_approve_gate_outer_edge_relocated.py
git add tests/act/test_approve_gate_subgraph_wiring.py
git add tests/integration/test_outer_edge_fail_loud_missing_resume.py
git commit -m "feat(graph): relocate act.approve.gate into act_subgraph + boot fail-loud (PR-1)

Closes 评审 §6.1 (事实修正版): wiring 已存在但位置错(spec §3.2 要求
act.authorize 与 act.envelope 之间,实现在 act.main 之后,导致 HITL
是副作用之后回放而非副作用之前中断)。

Moves act.approve.gate outer-edge → act_subgraph internal (5 edges).
Adds PlanLiftError when approval_resume_node edge absent (fail-closed).
Adds approval_required typed-port to act.authorize.
Moves _ACTION_TO_PHASE single-source (G-1 garbage)."
```

## PR-1 acceptance

| ID | Criterion | Verify |
|---|---|---|
| P1.A1 | outer `phase_main.yaml` 不再有 4 条错位边(`act.main → act.approve.gate` 等);保留 `intervene.resume → act.approve.gate` 跨子图 resume 边 | `pytest tests/act/test_approve_gate_outer_edge_relocated.py -v` |
| P1.A2 | act_subgraph 内部 `act.authorize → act.approve.gate → act.envelope / intervene.interrupt / terminal.commit` 5 条边全部存在 | `pytest tests/act/test_approve_gate_subgraph_wiring.py -v` |
| P1.A3 | 缺 `intervene.resume → act.approve.gate` 边 → `PlanLiftError` 在 `validate_profile_plans` 触发 | `pytest tests/integration/test_outer_edge_fail_loud_missing_resume.py -v` |
| P1.A4 | `act.authorize` 节点新增 typed `approval_required: bool` output,`act.approve.gate` 通过 typed port 读取(不读 metadata) | `grep "approval_required" lca/nodes/act/authorize/authorize.py` |
| P1.A5 | G-1 `_ACTION_TO_PHASE` 唯一源移到 typed-port 层 `lca/nodes/act/_phase_table.py` | `grep -rn "ACTION_TO_PHASE" lca/` |
| P1.A6 | `web-standard` 15 plans validated 仍通过 | `validate_profile_plans profiles/web-standard.yaml` |
| P1.A7 | C1–C13 不变量持有(无新 phase / EP;HITL 位置 spec 合规) | PR verification matrix checklist |
| P1.A8 | `./scripts/lca-ops why approve` 显示 monotonicity | grep output |
| P1.A9 | **L-8 plan_sdk.py 字段语义同步**:`approval_resume_node` docstring 说明「required when act.approve.gate in plan」,避免 yaml 顶层字段与 lifter 校验双 SSOT | `grep "approval_resume_node" lca/framework/graph/plan_sdk.py` = 3 处(field / _parse_plan / docstring) |

---

# PR-2: PipelineSafeExecutor 5 闸外提 — effect.pre_dispatch.envelope_check (ADR-0234)

> **Owner**: graph kernel + cognition/body team
> **Priority**: P1
> **Closes**: 评审 §6.2 + G-2 garbage
> **Predecessor**: ADR-0234 Accepted(本 PR Task 1)
> **No COMPAT shim**(5 闸迁到 graph 节点后,旧 procedure 路径直接删除)

## PR-2 Task 1: 写 ADR-0234

**Files:**
- Create: `docs/adr/0234-effect-pre-dispatch-envelope-check.md`

**Interfaces (ADR content outline):**
- Status: Proposed → Accepted(本 PR review 通过后改 Accepted)
- Context: `PipelineSafeExecutor.execute` 150 行把 5 闸内化;graph 不可见;`act.authorize` 节点做 surface 层 budget/constraint/safe-boundary,SE 内部再做一遍 → 双层结构违反 C13 + typed-port 完整化债。
- Decision: 把 envelope mint 后、tool dispatch 前的 5 闸(permission / grant / budget / safe-boundary / envelope-shape)抽到 graph 节点 `effect.pre_dispatch.envelope_check`,输入 `(envelope, tool, runtime)`,输出 `(envelope, verdict_refs)`。`PipelineSafeExecutor.execute` 退化为薄壳,只负责调用 graph 节点 + 包 Observation。
- Alternatives considered:
  - (a) 维持 procedure call——拒绝:graph 不可见,debug 半径大,违反 typed-port 完整化债
  - (b) 把 5 闸分散到 5 个 graph 节点——拒绝:5 个独立节点产生 5 个 typed port,fan-out 增加延迟,但实际只 1 次 envelope-shape check;过度切分违反 C6 最小化
  - (c) 单节点 `effect.pre_dispatch.envelope_check`——接受:5 闸是 envelope-shape 一次性 atomic check,单节点符合 C6 + 单一职责
- Consequences:
  - `act.dispatch` 节点 declared_inputs 从 `(envelope,)` 扩展到 `(envelope, verdict_refs)`(verdict_refs 由 `effect.pre_dispatch.envelope_check` 产出)
  - `PipelineSafeExecutor.execute` 减行 ≥ 80 行(G-2 verification)
  - architecture test `scripts/check_command_envelope_required.py` 仍然通过(stack trace 仍含 `mint_envelope`)

**Step 2.1.1: 写 ADR 草稿 → 评审 → Accepted**

按 `docs/adr/README.md` 流程走;不写完这一步不进 PR-2 Task 2。

## PR-2 Task 2: 实现 `effect.pre_dispatch.envelope_check` 节点 + 改造 `PipelineSafeExecutor`

> Pre-flight:ADR-0234 status = Accepted

**Files:**
- Create: `lca/nodes/effect/pre_dispatch_envelope_check.py`
- Create: `tests/effect/test_pre_dispatch_envelope_check.py`
- Modify: `lca/cognition/body/executor/pipeline_safe_executor.py:240-395`(退化为薄壳)
- Modify: `bundles/act/act_subgraph.yaml`(在 `act.dispatch` 前插 `effect.pre_dispatch.envelope_check` 节点)
- Modify: `bundles/concept/effect/effect_execute.yaml`(`effect.execute` declared_inputs 增加 `verdict_refs`)
- Modify: `lca/contracts/protocols/act/command/envelope.py`(`verdict_refs` 加 typed-port 注解 `tuple[str, ...]`)

**Interfaces:**
- `effect.pre_dispatch.envelope_check` node:
  - `semantic_name`: `"effect.pre_dispatch.envelope_check"`
  - `region`: `"effect"`
  - `declared_inputs`: `("envelope", "tool")`
  - `declared_outputs`: `("envelope", "verdict_refs")`
  - `node_execute`:
    - 5 闸一次性 atomic check:
      - **envelope-shape**:`plan_ref / scope_ref / decision_ref / provider` 非空(否则 raise `EnvelopeShapeError`)
      - **permission**:`tool.name in permission_manifest.allowed_tools`
      - **grant**:`envelope.grant.capability == tool.name AND envelope.grant.effect_class == "tools"`
      - **budget**:`envelope.budget_reservation` 各项 ≥ 0
      - **safe-boundary**:`envelope.plan_ref / scope_ref` 非空(无 wildcard)
    - 通过 → emit `(envelope, verdict_refs=tuple("effect.pre_dispatch.permission:allow", "effect.pre_dispatch.grant:valid", "effect.pre_dispatch.budget:valid", "effect.pre_dispatch.safe-boundary:valid", "effect.pre_dispatch.envelope-shape:valid"))`
    - 任意闸失败 → raise 对应 `EnvelopeVerdict.{DENIED|BUDGET_EXHAUSTED|...}` 类型(由 envelope_aggregate_verdict 决定),`verdict_refs` 不 emit(`NodeOutput({})`),让 outer edge predicate 走 `terminal.commit`

**Step 2.2.1: 写 failing test — 节点 5 闸 happy path**

```python
# tests/effect/test_pre_dispatch_envelope_check.py
import pytest
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.team.role.team import ToolPermissionManifest
from lca.contracts.protocols.act.command.envelope import (
    BudgetReservation, CapabilityGrant, CommandEnvelope, mint_envelope,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeContext, NodeInput
from lca.nodes.effect.pre_dispatch_envelope_check import EffectPreDispatchEnvelopeCheckExecutor

@pytest.mark.asyncio
async def test_pre_dispatch_envelope_check_all_gates_pass():
    tool = type("Tool", (), {"name": "read_file"})()
    envelope = mint_envelope(
        plan_ref="plan-xyz",
        scope_ref="turn-1",
        decision=new_id("dec"),
        provider="effect.body",
        grant=CapabilityGrant(capability="read_file", scope="turn", effect_class="tools"),
        budget_reservation=BudgetReservation(tool_calls=1),
        idempotency_key="dec:read_file",
        metadata={"effect_class": "tools", "operation": "body.act", "tool_name": "read_file"},
    )
    node = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=ToolPermissionManifest(allowed_tools=("read_file",)),
    )
    out = await node.node_execute(
        NodeContext(runtime=None, metadata={"plan_ref": "plan-xyz", "node_id": "effect.pre_dispatch.envelope_check"}),
        NodeInput(port_values={"envelope": envelope, "tool": tool}),
    )
    assert out.port_values["envelope"] == envelope
    assert "effect.pre_dispatch.permission:allow" in out.port_values["verdict_refs"]
    assert len(out.port_values["verdict_refs"]) == 5
```

Run: `pytest tests/effect/test_pre_dispatch_envelope_check.py::test_pre_dispatch_envelope_check_all_gates_pass -v`
Expected: FAIL — node not implemented

**Step 2.2.2: 写 failing test — permission 闸 fail**

```python
@pytest.mark.asyncio
async def test_pre_dispatch_envelope_check_permission_denied_raises():
    tool = type("Tool", (), {"name": "rm_rf_root"})()  # 未授权
    envelope = mint_envelope(
        plan_ref="plan-xyz", scope_ref="turn-1", decision=new_id("dec"),
        provider="effect.body",
        grant=CapabilityGrant(capability="rm_rf_root", scope="turn", effect_class="tools"),
        budget_reservation=BudgetReservation(tool_calls=1),
        idempotency_key="dec:rm_rf_root",
        metadata={"effect_class": "tools", "operation": "body.act"},
    )
    node = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=ToolPermissionManifest(allowed_tools=("read_file",)),
    )
    with pytest.raises(ValueError, match="permission"):
        await node.node_execute(
            NodeContext(runtime=None, metadata={"plan_ref": "plan-xyz", "node_id": "x"}),
            NodeInput(port_values={"envelope": envelope, "tool": tool}),
        )
```

Run: 同上,Expected: FAIL

**Step 2.2.3: 实现节点(满足 C13 typed-port contract)**

```python
# lca/nodes/effect/pre_dispatch_envelope_check.py
"""phase.concept.effect.pre_dispatch_envelope_check — 5-gate atomic envelope check.

ADR-0234: 把 PipelineSafeExecutor 内部的 5 闸(envelope-shape / permission
/ grant / budget / safe-boundary)抽到 typed-port graph 节点。PipelineSafeExecutor
退化薄壳。

Inputs: envelope (CommandEnvelope), tool (Tool)
Outputs: envelope (CommandEnvelope), verdict_refs (tuple[str, ...])

5 闸失败抛对应 EnvelopeVerdict 对应异常(由 envelope_aggregate_verdict 决定);
verdict_refs 不 emit → outer edge 走 terminal.commit (fail-loud)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract, AuthorityContract, EvidenceContract,
    LifecycleContract, PluginContract, PluginIdentity,
)
from lca.contracts.models.team.role.team import ToolPermissionManifest
from lca.contracts.protocols import Tool
from lca.contracts.protocols.act.command.envelope import CommandEnvelope
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext, NodeInput, NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_VERDICT_PERMISSION = "effect.pre_dispatch.permission:allow"
_VERDICT_GRANT = "effect.pre_dispatch.grant:valid"
_VERDICT_BUDGET = "effect.pre_dispatch.budget:valid"
_VERDICT_SAFE_BOUNDARY = "effect.pre_dispatch.safe-boundary:valid"
_VERDICT_ENVELOPE_SHAPE = "effect.pre_dispatch.envelope-shape:valid"


@dataclass(frozen=True, slots=True)
class EffectPreDispatchEnvelopeCheckExecutor:
    semantic_name: str = "effect.pre_dispatch.envelope_check"
    region: str = "effect"
    declared_inputs: tuple[PortName, ...] = ("envelope", "tool")
    declared_outputs: tuple[PortName, ...] = ("envelope", "verdict_refs")
    permission_manifest: ToolPermissionManifest | None = None

    async def node_execute(self, context: NodeContext, input: NodeInput) -> NodeOutput:
        del context
        envelope = input.port_values.get("envelope")
        tool = input.port_values.get("tool")
        if not isinstance(envelope, CommandEnvelope):
            raise TypeError("effect.pre_dispatch.envelope_check: 'envelope' must be CommandEnvelope")
        if not hasattr(tool, "name"):
            raise TypeError("effect.pre_dispatch.envelope_check: 'tool' must have .name attribute")

        refs: list[str] = []

        # envelope-shape
        if not (envelope.plan_ref and envelope.scope_ref and envelope.decision_ref and envelope.provider):
            raise ValueError("effect.pre_dispatch.envelope_check: envelope-shape incomplete")
        refs.append(_VERDICT_ENVELOPE_SHAPE)

        # permission
        if self.permission_manifest is None or tool.name not in self.permission_manifest.allowed_tools:
            raise ValueError(f"effect.pre_dispatch.envelope_check: permission denied for tool {tool.name!r}")
        refs.append(_VERDICT_PERMISSION)

        # grant
        if envelope.grant.capability != tool.name or envelope.grant.effect_class != "tools":
            raise ValueError(
                f"effect.pre_dispatch.envelope_check: grant mismatch "
                f"(capability={envelope.grant.capability!r}, tool={tool.name!r})"
            )
        refs.append(_VERDICT_GRANT)

        # budget
        res = envelope.budget_reservation
        if min(res.tokens, res.cost_cents, res.wall_clock_ms, res.tool_calls) < 0:
            raise ValueError("effect.pre_dispatch.envelope_check: budget reservation negative")
        refs.append(_VERDICT_BUDGET)

        # safe-boundary
        if not envelope.plan_ref or not envelope.scope_ref:
            raise ValueError("effect.pre_dispatch.envelope_check: safe-boundary incomplete")
        refs.append(_VERDICT_SAFE_BOUNDARY)

        return NodeOutput(port_values={"envelope": envelope, "verdict_refs": tuple(refs)})


@plugin(
    id="phase.concept.effect.pre_dispatch_envelope_check",
    Config=None,
    provides=("effect::effect.pre_dispatch.envelope_check",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_concept_effect_pre_dispatch_envelope_check.checked",
                "phase_concept_effect_pre_dispatch_envelope_check.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    del config
    from lca.cognition.body.executor.safe_executor import SimpleSafeExecutor  # 注入 permission
    # 通过 cordis 拿 permission_manifest；实现细节见 PR-2 落地
    permission_manifest = ctx.inject("permission_manifest")
    executor = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=permission_manifest,
    )
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)
```

**Step 2.2.4: 跑测试 verify pass**

Run: `pytest tests/effect/test_pre_dispatch_envelope_check.py -v`
Expected: PASS

**Step 2.2.5: 改 `act_subgraph.yaml` 插入新节点**

在 `bundles/act/act_subgraph.yaml` `act.dispatch` 节点之前插入:

```yaml
- id: effect.pre_dispatch.envelope_check
  region: effect
  factory: effect.pre_dispatch.envelope_check
  inputs: [envelope]
  outputs: [envelope, verdict_refs]
  config:
    emit_on_enter: []
    emit_on_exit: []

# act.dispatch 现在多一个 verdict_refs 输入
- id: act.dispatch
  factory: act.dispatch.ref
  inputs: [envelope, verdict_refs]
  outputs: [receipt]
  ...
```

并加 edge `effect.pre_dispatch.envelope_check → act.dispatch`。

**Step 2.2.6: 改 `effect.execute` 节点接收 `verdict_refs`**

`bundles/concept/effect/effect_execute.yaml`:
```yaml
- id: effect.execute
  factory: effect.execute
  inputs: [envelope, verdict_refs]   # 加 verdict_refs
  outputs: [receipts]
```

**Step 2.2.7: 退化 `PipelineSafeExecutor.execute` 薄壳**

`lca/cognition/body/executor/pipeline_safe_executor.py:240-395` 删除 5 闸 procedure call,只保留 envelope mint + graph node 调用 + Observation 包装:

```python
async def execute(self, tool, args, ..., invocation_id=""):
    # envelope mint(保留,stack trace 仍含 mint_envelope,architecture test 守护)
    envelope = mint_envelope(...)
    # 调用 graph 节点 effect.pre_dispatch.envelope_check
    result = await self._envelope_check_node.node_execute(
        NodeContext(...),
        NodeInput(port_values={"envelope": envelope, "tool": tool}),
    )
    # 调用 effect.execute node(已含 SafeExecutor 内部 tool 调用 + retry)
    receipt = await self._effect_execute_node.node_execute(
        NodeContext(...),
        NodeInput(port_values={"envelope": envelope, "tool": tool, "verdict_refs": result.port_values["verdict_refs"]}),
    )
    return _wrap_as_observation(receipt)
```

预计减行 ≥ 80 行(G-2 verification)。

**Step 2.2.7a: 删 `PipelineSafeExecutor.execute` 内 5 个 `executor.*` 本地 verdict_refs(G-7 收尾)**

> **为什么**:PR-2 把 5 闸迁到 `effect.pre_dispatch.envelope_check` 节点后,graph 节点产出 `effect.pre_dispatch.permission:allow` / `effect.pre_dispatch.grant:valid` / `effect.pre_dispatch.budget:valid` / `effect.pre_dispatch.safe-boundary:valid` / `effect.pre_dispatch.envelope-shape:valid`(已在 Step 2.2.3 实现)。`PipelineSafeExecutor.execute` 内 5 个 `executor.permission:allow` / `executor.reservation:valid` / `executor.grant:valid` / `executor.plan-boundary:valid` / `executor.pipeline:completed` 是**第二套语义词表**,与 graph canonical `effect.pre_dispatch.*` 冲突。本步同步删除,统一走 graph 节点产出。

`lca/cognition/body/executor/pipeline_safe_executor.py:284-328` 改造:

```python
# 旧代码(删除):
verdict_refs = ["executor.permission:allow"]
...
verdict_refs.append("executor.reservation:valid")
...
verdict_refs.append("executor.grant:valid")
...
verdict_refs.append("executor.plan-boundary:valid")
...
verdict_refs.append("executor.pipeline:completed")
envelope = replace(envelope, policy_verdict_refs=tuple(verdict_refs))

# 新代码:
# verdict_refs 不再由 SE 内部维护——交给 effect.pre_dispatch.envelope_check 节点产出。
# SE 只调用 graph 节点 + 把节点产出的 verdict_refs 透传到 envelope。
verdict_refs = result.port_values["verdict_refs"]  # 来自 Step 2.2.7 的 graph 节点调用
envelope = replace(envelope, policy_verdict_refs=tuple(verdict_refs))
```

**Step 2.2.7a verification(G-7):**

```bash
grep -rn "executor\.\(permission\|reservation\|grant\|plan-boundary\|pipeline\)" lca/cognition/
```

Expected: 0 matches(5 个本地 verdict_refs 全部删除,统一由 graph 节点产出)

**Step 2.2.8: 跑整体 verify**

```bash
ruff check --fix
ruff format
./scripts/lint-imports.sh
./scripts/lca-ops plan tree web-standard
./scripts/lca-ops validate_profile_plans profiles/web-standard.yaml
pytest tests/effect tests/act tests/lca_kernel/boot -q
./scripts/lca-ops audit-state-writers
# architecture test 仍通过(检查 mint_envelope 仍在 stack trace):
python -c "
from lca.cognition.body.executor.pipeline_safe_executor import PipelineSafeExecutor
import inspect
src = inspect.getsource(PipelineSafeExecutor.execute)
assert 'mint_envelope' in src
print('OK: mint_envelope in stack trace')
"
```

Expected: 全 exit 0

**Step 2.2.9: Commit**

```bash
git add docs/adr/0234-effect-pre-dispatch-envelope-check.md
git add lca/nodes/effect/pre_dispatch_envelope_check.py tests/effect/test_pre_dispatch_envelope_check.py
git add bundles/act/act_subgraph.yaml bundles/concept/effect/effect_execute.yaml
git add lca/cognition/body/executor/pipeline_safe_executor.py
git commit -m "feat(graph): extract 5-gate envelope check to typed-port node (PR-2, ADR-0234)

Closes 评审 §6.2 + G-2 garbage.
PipelineSafeExecutor.execute reduces ≥80 lines (G-2 verification).
5-gate atomic check now graph-visible; architecture test
check_command_envelope_required.py still green."
```

## PR-2 acceptance

| ID | Criterion | Verify |
|---|---|---|
| P2.A1 | ADR-0234 status = Accepted | `docs/adr/README.md` |
| P2.A2 | `effect.pre_dispatch.envelope_check` 节点 5 闸测试全过(happy + 4 fail cases) | `pytest tests/effect/test_pre_dispatch_envelope_check.py -v` |
| P2.A3 | `PipelineSafeExecutor.execute` 行数减 ≥ 80 行 | `wc -l pipeline_safe_executor.py` (post ≤ 270 行) |
| P2.A4 | `mint_envelope` 仍在 `PipelineSafeExecutor.execute` stack trace(architecture test 守护) | 上述 python script |
| P2.A5 | `act.dispatch` 节点 declared_inputs 含 `verdict_refs` | `grep "verdict_refs" bundles/act/act_subgraph.yaml` |
| P2.A6 | C1–C13 持有 | PR verification matrix |
| P2.A7 | G-2 garbage verification: `grep -rn "permission\|safe-boundary" lca/cognition/body/executor/pipeline_safe_executor.py` 仅 stack trace 残留 | exit 0 |
| P2.A8 | **G-7 verdict_refs 词表去重**:`executor.permission:allow` 等 5 个本地 verdict_refs 全部删除,统一由 graph `effect.pre_dispatch.*` 节点产出 | `grep -rn "executor\.\(permission\|reservation\|grant\|plan-boundary\|pipeline\)" lca/cognition/` = 0 matches |
| P2.A9 | envelope.policy_verdict_refs 来自 graph 节点调用结果,不再来自 SE 内部 dict | `grep "policy_verdict_refs" lca/cognition/body/executor/pipeline_safe_executor.py` 仅 `replace(envelope, policy_verdict_refs=tuple(verdict_refs))` 一处赋值 |

---

# PR-3: act.observe 拆 normalize vs terminate_decide

> **Owner**: graph kernel team
> **Priority**: P2
> **Closes**: 评审 §6.3 + G-3 garbage
> **Predecessor**: Agent Note `contract/2026-09-16-act-observe-normalize-split.md` proposed → implemented(本 PR 同步)
> **No ADR required**(纯节点拆分,在 `phase:act` 内,不跨层)

## PR-3 Task 1: 写 Agent Note(proposed → implemented)

**Files:**
- Create: `docs/notes/proposed/contract/2026-09-16-act-observe-normalize-split.md`
- 最终状态:本 PR 落地后移到 `docs/notes/implemented/contract/`

**Note outline:**
- Status: proposed → implemented
- Problem: `act.observe` 一节点同时承担 receipt normalize + should_terminate 决策 + RunFact commit 3 件事;违反 AGENTS.md §2.2 「事实源 ≠ 决策」分类原则。
- Decision: 拆为 2 节点:
  - `act.observe.normalize`:`receipt → receipt`(纯归一化)
  - `act.observe.terminate_decide`:`receipt → receipt + should_terminate`(纯路由决策)
- Alternatives considered:
  - (a) 维持 3 事合一——拒绝:违反事实源 ≠ 决策;future 接 `terminal_predicate` 不清晰
  - (b) 拆 3 节点(加 RunFact emit 独立)——拒绝:RunFact 是 observation plane 落库,不是 act 子图节点职责;留 observe 内部
  - (c) 拆 2 节点(选这个)——接受:符合 AGENTS.md §2.2 分类 + typed-port 边界清晰 + 不动 RunFact
- Consequences:
  - `act.observe` 节点文件保留为 `observe.py`(语义「normalize + commit_fact」),但 `declared_outputs` 移除 `should_terminate`
  - 新增 `lca/nodes/act/observe/terminate_decide.py`
  - bundle edge:`act.observe.normalize → act.observe.terminate_decide → reflect.main / terminal.commit`

**Step 3.1.1: 写 Note 草稿 → 评审 → accepted by reviewer → 落地后移 implemented/**

按 `docs/notes/README.md` 流程走;同 PR 内 proposed → implemented。

## PR-3 Task 2: 拆节点 + 改 wiring

> Pre-flight:Note status = implemented

**Files:**
- Create: `lca/nodes/act/observe/terminate_decide.py`
- Modify: `lca/nodes/act/observe/observe.py`(移除 should_terminate 决策;改为 `act.observe.normalize` 命名 + declared_outputs 改)
- Create: `tests/act/test_observe_terminate_decide.py`
- Modify: `bundles/act/act_subgraph.yaml`(节点改名 + 加 edge + observe 不再有 should_terminate)
- Modify: `bundles/outer/phase_main.yaml`(outer edge 改读 `terminate_decide` 的 `should_terminate` port)

**Interfaces:**
- `act.observe.normalize`(原 `act.observe` 文件保留,语义改为 normalize):
  - `declared_inputs`: `("receipt",)`
  - `declared_outputs`: `("receipt",)`(移除 `should_terminate`)
  - `node_execute`:原 normalize 部分 + RunFact commit(保留 RunFact 在此,因为是 observation 落库)
- `act.observe.terminate_decide`(新节点):
  - `semantic_name`: `"act.observe.terminate_decide"`
  - `region`: `"act"`
  - `declared_inputs`: `("receipt",)`
  - `declared_outputs`: `("receipt", "should_terminate")`
  - `node_execute`:
    ```python
    should_terminate = (
        receipt.failure_kind == FAILURE_KIND_EXECUTION
        or (receipt.failure_kind is None and receipt.outcome.value == "failed")
    )
    return NodeOutput(port_values={"receipt": receipt, "should_terminate": should_terminate})
    ```

**Step 3.2.1: 写 failing test — terminate_decide 决策**

```python
# tests/act/test_observe_terminate_decide.py
import pytest
from lca.contracts.atoms.enums.enums import EffectOutcome
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND_EXECUTION
from lca.contracts.harness.act.effect_receipt import EffectReceipt
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeContext, NodeInput
from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor

@pytest.mark.asyncio
async def test_terminate_decide_on_execution_failure_kind():
    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.FAILED,
        idempotency_key="k",
        provider="p",
        failure_kind=FAILURE_KIND_EXECUTION,
    )
    node = ActObserveTerminateDecideExecutor()
    out = await node.node_execute(
        NodeContext(runtime=None, metadata={}),
        NodeInput(port_values={"receipt": receipt}),
    )
    assert out.port_values["should_terminate"] is True


@pytest.mark.asyncio
async def test_terminate_decide_on_success_no_failure_kind():
    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key="k",
        provider="p",
    )
    node = ActObserveTerminateDecideExecutor()
    out = await node.node_execute(
        NodeContext(runtime=None, metadata={}),
        NodeInput(port_values={"receipt": receipt}),
    )
    assert out.port_values["should_terminate"] is False
```

Run: `pytest tests/act/test_observe_terminate_decide.py -v`
Expected: FAIL — node not implemented

**Step 3.2.2: 实现 terminate_decide 节点(代码如上 Interfaces)**

文件:`lca/nodes/act/observe/terminate_decide.py`,与 `observe.py` 同样模式(`@plugin(...)` carrier + `ActObserveTerminateDecideExecutor` dataclass)。

**Step 3.2.3: 改 observe.py 移除 should_terminate**

`lca/nodes/act/observe/observe.py`:
- `semantic_name` 改为 `"act.observe.normalize"`
- `declared_outputs` 改为 `("receipt",)`
- `node_execute` 末尾删除 `should_terminate` 决策
- 保留 RunFact commit

**Step 3.2.4: 改 act_subgraph.yaml**

```yaml
# act.observe 改名 + declared_outputs 改
- id: act.observe
  region: act
  factory: act.observe  # factory 名不变;内部语义为 normalize
  inputs: [receipt]
  outputs: [receipt]   # 移除 should_terminate
  config:
    emit_on_enter: []
    emit_on_exit: [phase.tool.call.end]

# 新增 terminate_decide 节点
- id: act.observe.terminate_decide
  region: act
  factory: act.observe.terminate_decide
  inputs: [receipt]
  outputs: [receipt, should_terminate]
  config:
    emit_on_enter: []
    emit_on_exit: [phase.act.fold.end]

edges:
  ...
  - from: act.observe
    to: act.observe.terminate_decide
    when: true
  - from: act.observe.terminate_decide
    to: reflect.main
    when: true
  - from: act.observe.terminate_decide
    to: terminal.commit
    when:
      kind: eq
      port:
        name: should_terminate
      value: true
```

**Step 3.2.5: 改 outer edge `phase_main.yaml`**

原 `act.main → terminal.commit` 谓词 `should_terminate == true`,现在 `should_terminate` 来自 `act.observe.terminate_decide`,边需要源节点改写。

实际方案:`should_terminate` 是 typed port,在 outer edge predicate 中直接读对应节点:

```yaml
- from: act.observe.terminate_decide
  to: terminal.commit
  when:
    kind: eq
    port:
      name: should_terminate
    value: true
```

(原 `act.main → terminal.commit` 边移除;`act.observe.terminate_decide` 直接 emit 给 outer 终端。)

**Step 3.2.6: 跑整体 verify**

```bash
ruff check --fix
ruff format
./scripts/lint-imports.sh
./scripts/lca-ops plan tree web-standard
./scripts/lca-ops validate_profile_plans profiles/web-standard.yaml
pytest tests/act tests/loop -q
./scripts/lca-ops audit-state-writers
```

Expected: 全 exit 0

**Step 3.2.7: G-3 garbage verification**

```bash
grep -n "should_terminate" lca/nodes/act/observe/observe.py
```

Expected: 0 matches(should_terminate 已从 observe.py 移除)

**Step 3.2.7a: 拆 RunFact commit 到独立节点 `act.observe.commit_fact`(L-1 / 「图不知道 act 业务」边界)**

> **为什么**:原 `act.observe` 节点内部通过 `getattr(context.runtime, "journal", None)` 偷图 runtime 的 journal capability(observe.py:149),违反「act 业务不知道图存在」边界(PR-5 boundary P5.A7)。RunFact commit 应独立成节点 `act.observe.commit_fact`,通过 typed port `receipt` + 图 kernel 自己注入 `journal` capability,**act 业务节点不再偷 context.runtime**。

**Files:**
- Create: `lca/nodes/act/observe/commit_fact.py`
- Modify: `lca/nodes/act/observe/observe.py`(移除 RunFact commit 段)
- Modify: `bundles/act/act_subgraph.yaml`(插入 `act.observe.commit_fact` 节点 + edge)
- Create: `tests/act/test_observe_commit_fact.py`

**Interfaces:**
- `act.observe.commit_fact` 节点:
  - `semantic_name`: `"act.observe.commit_fact"`
  - `region`: `"act"`
  - `declared_inputs`: `("receipt",)`
  - `declared_outputs`: `("receipt",)`(passthrough)
  - `node_execute`:
    - 通过 `context.runtime.journal` 拿到 journal capability(图 kernel 注入,act 业务不偷)
    - 构造 `RunFact(kind="effect.observed", payload={...})`,`journal.commit_fact(fact, plan_ref, node_ref)`
    - 透传 receipt

**Step 3.2.7a.1: 写 failing test**

```python
# tests/act/test_observe_commit_fact.py
import pytest
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.harness.act.effect_receipt import EffectReceipt
from lca.contracts.atoms.enums.enums import EffectOutcome
from lca.contracts.protocols.act.command.envelope import RunFact
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeContext, NodeInput
from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

class FakeJournal:
    def __init__(self):
        self.committed: list[RunFact] = []
    def commit_fact(self, fact: RunFact, plan_ref: str, node_ref: str) -> None:
        self.committed.append(fact)

@pytest.mark.asyncio
async def test_commit_fact_runs_observed_kind():
    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key="k",
        provider="p",
    )
    journal = FakeJournal()
    node = ActObserveCommitFactExecutor()
    out = await node.node_execute(
        NodeContext(runtime=type("R", (), {"journal": journal})(),
                    metadata={"plan_ref": "plan-xyz", "node_id": "act.observe.commit_fact"}),
        NodeInput(port_values={"receipt": receipt}),
    )
    assert out.port_values["receipt"] == receipt
    assert len(journal.committed) == 1
    assert journal.committed[0].kind == "effect.observed"
    assert journal.committed[0].plan_ref == "plan-xyz"
```

Run: `pytest tests/act/test_observe_commit_fact.py -v`
Expected: FAIL — node not implemented

**Step 3.2.7a.2: 实现节点**

`lca/nodes/act/observe/commit_fact.py`(用 `@plugin(...)` carrier + `ActObserveCommitFactExecutor` dataclass,与 `observe.py` 同模式)。

**Step 3.2.7a.3: 改 `observe.py` 移除 RunFact commit 段**

`lca/nodes/act/observe/observe.py:148-167` 删除 RunFact commit 块,observe 节点仅做 normalize + 透传 receipt。

**Step 3.2.7a.4: 改 act_subgraph.yaml**

```yaml
# act.observe.commit_fact 在 normalize 后、terminate_decide 前
- id: act.observe.commit_fact
  region: act
  factory: act.observe.commit_fact
  inputs: [receipt]
  outputs: [receipt]
  config:
    emit_on_enter: []
    emit_on_exit: [phase.tool.call.end]

# 边调整:observe.normalize → observe.commit_fact → observe.terminate_decide
- from: act.observe
  to: act.observe.commit_fact
  when: true
- from: act.observe.commit_fact
  to: act.observe.terminate_decide
  when: true
```

**Step 3.2.7a.5: 跑测试 verify pass + 「act 业务不知道图存在」verification**

Run: `pytest tests/act/test_observe_commit_fact.py tests/act/test_observe_terminate_decide.py -v`
Expected: PASS

```bash
grep -rn "context\.runtime\|getattr.*runtime" lca/nodes/act/ lca/nodes/intervene/
```

Expected: 仅 PR-5 扩展允许的 typed port 访问(本 PR 不新增偷图点),`context.runtime` 直接调用 = 0 matches

**Step 3.2.8: 移 Note 到 implemented/**

```bash
git mv docs/notes/proposed/contract/2026-09-16-act-observe-normalize-split.md docs/notes/implemented/contract/2026-09-16-act-observe-normalize-split.md
# 改 Status 行
sed -i 's/Status: proposed/Status: implemented/' docs/notes/implemented/contract/2026-09-16-act-observe-normalize-split.md
```

**Step 3.2.9: Commit**

```bash
git add lca/nodes/act/observe/observe.py lca/nodes/act/observe/terminate_decide.py
git add tests/act/test_observe_terminate_decide.py
git add bundles/act/act_subgraph.yaml bundles/outer/phase_main.yaml
git add docs/notes/implemented/contract/2026-09-16-act-observe-normalize-split.md
git commit -m "feat(graph): split act.observe into normalize + terminate_decide (PR-3)

Closes 评审 §6.3 + G-3 garbage.
Aligns with AGENTS.md §2.2 (事实源 ≠ 决策).
Note 2026-09-16-act-observe-normalize-split moved to implemented/."
```

## PR-3 acceptance

| ID | Criterion | Verify |
|---|---|---|
| P3.A1 | `act.observe.normalize` + `act.observe.terminate_decide` 两节点独立 | `pytest tests/act/test_observe_terminate_decide.py -v` |
| P3.A2 | `should_terminate` 已从 `observe.py` 移除 | `grep "should_terminate" lca/nodes/act/observe/observe.py` = 0 |
| P3.A3 | bundle wiring 正确:observe → terminate_decide → reflect.main / terminal.commit | `validate_profile_plans` 绿 |
| P3.A4 | Note status = implemented | `docs/notes/README.md` 树 |
| P3.A5 | C1–C13 持有(observe 拆节点仍在 `phase:act` 内,无新 EP) | PR verification matrix |

---

# PR-4: `_FAILURE_KIND_TO_ERROR_REASON` 移到 contracts

> **Owner**: observability + cognition/body team
> **Priority**: P2
> **Closes**: 评审 §6.5 + G-4 garbage
> **No ADR / Note required**(纯 typed-闭集搬家,符合 C11)

## PR-4 Task 1: 建 contracts map + 改节点导入

**Files:**
- Create: `lca/contracts/observability/observability/failure_reason_map.py`
- Modify: `lca/nodes/act/observe/observe.py`(删除 dict,改为 import)
- Create: `tests/contracts/observability/test_failure_reason_map.py`

**Interfaces:**
- contracts 模块:
  ```python
  # lca/contracts/observability/observability/failure_reason_map.py
  """Closed-set failure_kind → error_reason map (PR-4, closes G-4).

  Single source of truth for receipt failure classification.
  Add new entries by extending the dict (closed-set by C11).
  Nodes import from here, never define their own.
  """
  from lca.contracts.atoms.semantic.keys import (
      FAILURE_KIND_EXECUTION, FAILURE_KIND_TRANSIENT,
      FAILURE_KIND_VALIDATION, FAILURE_KIND_TOOL_WIRE,
  )

  FAILURE_KIND_TO_ERROR_REASON: dict[str, str] = {
      FAILURE_KIND_EXECUTION: FAILURE_KIND_EXECUTION,
      FAILURE_KIND_TRANSIENT: FAILURE_KIND_TRANSIENT,
      FAILURE_KIND_VALIDATION: FAILURE_KIND_VALIDATION,
      FAILURE_KIND_TOOL_WIRE: FAILURE_KIND_TOOL_WIRE,
  }

  def resolve_error_reason(failure_kind: str | None) -> str | None:
      return FAILURE_KIND_TO_ERROR_REASON.get(failure_kind) if failure_kind else None
  ```
- 节点 `observe.py:55-65` 删除 dict,改为 `from lca.contracts.observability.observability.failure_reason_map import resolve_error_reason`

**Step 4.1.1: 写 failing test — contracts map 单一源**

```python
# tests/contracts/observability/test_failure_reason_map.py
from lca.contracts.atoms.semantic.keys import FAILURE_KIND_EXECUTION, FAILURE_KIND_TRANSIENT
from lca.contracts.observability.observability.failure_reason_map import (
    FAILURE_KIND_TO_ERROR_REASON, resolve_error_reason,
)


def test_failure_reason_map_contains_all_known_kinds():
    assert FAILURE_KIND_EXECUTION in FAILURE_KIND_TO_ERROR_REASON
    assert FAILURE_KIND_TRANSIENT in FAILURE_KIND_TO_ERROR_REASON


def test_resolve_error_reason_unknown_returns_none():
    assert resolve_error_reason("unknown_kind_xyz") is None


def test_resolve_error_reason_none_returns_none():
    assert resolve_error_reason(None) is None
```

Run: `pytest tests/contracts/observability/test_failure_reason_map.py -v`
Expected: FAIL — module not exist

**Step 4.1.2: 实现 contracts 模块**

如上 Interfaces 代码块。

Run: `pytest tests/contracts/observability/test_failure_reason_map.py -v`
Expected: PASS

**Step 4.1.3: 改 observe.py 删 dict + import**

`lca/nodes/act/observe/observe.py`:
- 删除 `_FAILURE_KIND_TO_ERROR_REASON: dict[str, str] = {...}`(行 55-65)
- 删除 imports `FAILURE_KIND_EXECUTION / FAILURE_KIND_TRANSIENT / FAILURE_KIND_VALIDATION / FAILURE_KIND_TOOL_WIRE` 的 dict-key 使用
- 顶部加 `from lca.contracts.observability.observability.failure_reason_map import resolve_error_reason`
- `_normalize_receipt` 内 `reason = _FAILURE_KIND_TO_ERROR_REASON.get(receipt.failure_kind)` 改为 `reason = resolve_error_reason(receipt.failure_kind)`

**Step 4.1.4: 跑整体 verify**

```bash
ruff check --fix
ruff format
./scripts/lint-imports.sh
./scripts/lca-ops plan tree web-standard
./scripts/lca-ops validate_profile_plans profiles/web-standard.yaml
pytest tests/contracts/observability tests/act -q
```

Expected: 全 exit 0

**Step 4.1.5: G-4 garbage verification**

```bash
grep -rn "_FAILURE_KIND_TO_ERROR_REASON" lca/
```

Expected: 仅 `lca/contracts/observability/observability/failure_reason_map.py:14` 1 处

**Step 4.1.6: Commit**

```bash
git add lca/contracts/observability/observability/failure_reason_map.py
git add tests/contracts/observability/test_failure_reason_map.py
git add lca/nodes/act/observe/observe.py
git commit -m "refactor(contracts): move failure_kind→error_reason map to contracts (PR-4, G-4)

Closes 评审 §6.5 + G-4 garbage.
Single source of truth for receipt failure classification (C11 closed-set).
Node imports from contracts; no node-local dict."
```

## PR-4 acceptance

| ID | Criterion | Verify |
|---|---|---|
| P4.A1 | `FAILURE_KIND_TO_ERROR_REASON` 唯一源在 contracts | `grep -rn "FAILURE_KIND_TO_ERROR_REASON" lca/` = 1 处 |
| P4.A2 | `resolve_error_reason` 对未知 kind 返回 None | `pytest tests/contracts/observability/test_failure_reason_map.py -v` |
| P4.A3 | `observe.py` 不再持有 dict | `wc -l lca/nodes/act/observe/observe.py` 减少 |
| P4.A4 | C1–C13 持有(无新 EP / 无新 phase) | PR verification matrix |

---

# PR-5: act.envelope C13 卫生 — metadata 反抽到 typed port (ADR-0235)

> **Owner**: graph kernel + cognition/body team
> **Priority**: P0
> **Closes**: 评审 §4.2 表第一行 + G-5 garbage + **「图不知道 act 业务 / act 业务不知道图存在」边界审视**(user 评审 2026-09-16 第二轮)
> **Predecessor**: ADR-0235 Accepted(本 PR Task 1)
> **No COMPAT shim**(typed-port 改造后旧 metadata 路径直接删除)

## PR-5 边界硬约束(由 user 评审第二轮明确,本 PR 必须同时守住)

| 边界 | 含义 | 现状违反点 | 本 PR 修复 |
|---|---|---|---|
| **act 业务不知道图存在** | Body / SimpleBody / PipelineSafeExecutor / ActionRegistry 不应 import 或依赖 typed-port kernel、`lca/framework/graph/`、PortRef、Predicate、RoutingDecision | `pipeline_safe_executor.py:251-258` 调用 `get_current_plan_ref()` / `get_current_run_scope()`(observability 注入,目的是 mint_envelope);`envelope.py:85` 把 `context.runtime.state` 塞 metadata(通过图 kernel 的 `NodeContext` 偷 state) | 本 PR 把图边界收口为「仅 envelope mint 工厂接收 plan_ref / scope_ref 字符串」;Body / ActionRegistry 不感知图。 |
| **图不知道 act 业务** | typed-port kernel、`lca/framework/graph/`、`EffectDispatcher` Protocol 不应 import 或依赖 cognition/body 内部 type(Action / ActionRegistry / Tool 内部字段) | `declarative_execution.py:97` `EffectDispatcher.execute(envelope, policy)` 已只接收 envelope + policy(纯 typed),符合 | PR-5 维持此约束,不引入 Action / ActionRegistry 类型。 |
| **envelope 单据只承载 effect gateway 单据** | envelope 是世界副作用的「唯一收据」;不应该承载 cognition 内部数据(state / decision) | `envelope.py:78-86` `metadata={"state": ..., "decision": ...}` 严重违反 | 本 PR 抽走 state / decision 到 typed port;metadata 仅留 op-relative 字段。 |
| **typed Contract 跨边界 = fail-loud** | ADR-0195 §1.4 C13:跨边界传递必须 typed Contract;无 Contract 跨边界 = fail | `metadata` 是 Mapping[str, Any],与 typed Contract 相反 | typed port 透传替换 metadata。 |

## PR-5 Task 1: 写 ADR-0235

**Files:**
- Create: `docs/adr/0235-act-envelope-typed-port-hygiene.md`

**Interfaces (ADR content outline):**
- Status: Proposed → Accepted
- Context: `act.envelope` 当前 `metadata={"state": context.runtime.state, "decision": decision, "effect_class": "tools", "operation": "body.act"}` 把 typed 数据(state / decision)塞 metadata,违反:
  - ADR-0195 §1.4 C13「typed Contract 跨边界 = fail-loud,无 Contract 跨边界」
  - 「act 业务不知道图存在」边界(state / decision 本属 cognition 内部,经 metadata 跨越 cognition→act 边界时无 Contract)
  - envelope 单据污染(违反 C2 双平面 — cognition 内部数据进入 effect gateway 单据)
- Decision:
  1. `act.envelope` 节点 `declared_inputs` 从 `("decision",)` 扩展到 `("decision", "state")`(typed)
  2. `act.envelope.declared_outputs` 扩展到 `("envelope", "decision", "state")`(透传)
  3. `act.envelope.node_execute` 不再读 `context.runtime.state`;metadata 仅保留 `effect_class / operation` typed 字段
  4. `act.dispatch` 节点 `declared_inputs` 增加 `("envelope", "state", "decision")`(透传)
  5. `effect.execute` 节点 `declared_inputs` 扩展到 `(envelope, decision, state)`(PR-2 已加 verdict_refs,PR-5 顺序在 PR-2 后)
  6. `EffectDispatcher.execute` Protocol 签名扩展为 `async def execute(envelope, policy, *, state=None, decision=None) -> object`,typed keyword-only 参数
  7. `RegistryEffectDispatcher.execute` 实现同步扩展;**删除** `_existing_effect_receipt` / `_validated_effect_class` 内部对 metadata 偷读 state / decision 的逻辑(代码审 grep 应得 0 matches)
  8. `EffectDispatcherFactory` Protocol 与 `lca/contracts/protocols/runtime/runtime/composition.py:148-157` / `:95` 同步扩展(typed injection 不破坏)
- Alternatives considered:
  - (a) 维持 metadata——拒绝:违反 C13 + act 业务边界 + envelope 单据污染三重
  - (b) 把 state/decision 直接进 envelope 字段——拒绝:envelope 是 effect gateway 单据,不该承载 cognition 内部数据(违反 C2 双平面)
  - (c) typed port 透传(选这个)——接受:符合 C13 + act 业务边界 + typed-port kernel native
- Consequences:
  - `act.envelope.node_execute` 不再读 `context.runtime.state`
  - `RegistryEffectDispatcher.execute` 签名改;**所有调用点**同步改(grep `dispatcher.execute(` 全仓需要更新)
  - `effect.execute` yaml 节点 declared_inputs 增加 typed `decision / state`
  - `_existing_effect_receipt` / `_validated_effect_class` 不再依赖 metadata 偷读
  - **architecture test `scripts/check_command_envelope_required.py` 仍通过**(mint_envelope 仍在调用 stack)
  - **act 业务不感知图**:`PipelineSafeExecutor` / `SimpleBody` / `ActionRegistry` / `Action` / `UseToolOperation` 等不 import `lca/framework/graph/`;PR-5 verification 命令:`grep -rn "lca.framework.graph\|from lca.framework" lca/cognition/ lca/plugins/cognitive/body/` 期望 0 matches

**Step 5.1.1: 写 ADR 草稿 → 评审 → Accepted**

## PR-5 Task 2: 改造 act.envelope + RegistryEffectDispatcher

> Pre-flight:ADR-0235 status = Accepted

**Files:**
- Modify: `lca/nodes/act/envelope/envelope.py`(declared_inputs / node_execute)
- Modify: `lca/harness/declarative/execute/dispatch.py`(`RegistryEffectDispatcher.execute` 签名)
- Modify: `lca/contracts/protocols/declarative/declarative_1/declarative_execution.py`(`EffectDispatcher.execute` Protocol 签名)
- Modify: `bundles/act/act_subgraph.yaml`(`act.envelope` 节点 inputs / outputs)
- Modify: `bundles/concept/effect/effect_execute.yaml`(`effect.execute` 节点 inputs)
- Modify: outer edge bundle yaml 路径(若 outer edge 跨 envelope 与 dispatch,需传 state / decision typed port)
- Create: `tests/act/test_envelope_typed_port_hygiene.py`

**Interfaces:**
- `act.envelope` 新 `declared_inputs`: `("decision", "state")`
- `act.envelope.node_execute`:
  ```python
  decision = input.port_values["decision"]
  state = input.port_values["state"]  # 新 typed-port 输入
  envelope = mint_envelope(
      plan_ref=..., scope_ref=..., decision=decision,
      provider="effect.body",
      grant=CapabilityGrant(...),
      idempotency_key=...,
      metadata={"effect_class": "tools", "operation": "body.act"},  # 仅 typed-port 难表达的字段
  )
  return NodeOutput(port_values={"envelope": envelope, "decision": decision, "state": state})
  ```
- `act.envelope` 新 `declared_outputs`: `("envelope", "decision", "state")`(透传)
- `EffectDispatcher.execute` Protocol 新签名:
  ```python
  async def execute(
      self,
      envelope: CommandEnvelope,
      policy: EffectPolicyPlan,
      *,
      state: AgentState | None = None,
      decision: Decision | None = None,
  ) -> object: ...
  ```
- `effect.execute` 节点 inputs: `[envelope, decision, state]`

**Step 5.2.1: 写 failing test — metadata 不再含 state/decision**

```python
# tests/act/test_envelope_typed_port_hygiene.py
import pytest
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeContext, NodeInput
from lca.nodes.act.envelope.envelope import ActEnvelopeExecutor

@pytest.mark.asyncio
async def test_envelope_metadata_does_not_contain_state_or_decision():
    decision = Decision(decision_id=new_id("dec"), action_type="use_tool")
    state = AgentState()  # typed;实际测试用最小实例
    node = ActEnvelopeExecutor()
    out = await node.node_execute(
        NodeContext(
            runtime=None,
            metadata={"plan_ref": "plan-xyz", "node_id": "act.envelope"},
        ),
        NodeInput(port_values={"decision": decision, "state": state}),
    )
    envelope = out.port_values["envelope"]
    assert "state" not in envelope.metadata
    assert "decision" not in envelope.metadata
    assert envelope.metadata == {"effect_class": "tools", "operation": "body.act"}
    assert out.port_values["decision"] == decision
    assert out.port_values["state"] == state
```

Run: `pytest tests/act/test_envelope_typed_port_hygiene.py -v`
Expected: FAIL — metadata still contains state/decision

**Step 5.2.2: 改 act.envelope(envelope.py)**

- 改 `declared_inputs / declared_outputs`
- `node_execute` 移除 `context.runtime.state` 读取
- metadata 仅保留 typed-port 难表达字段

**Step 5.2.3: 改 EffectDispatcher Protocol + RegistryEffectDispatcher + EffectDispatcherFactory + composition.py**

`lca/contracts/protocols/declarative/declarative_1/declarative_execution.py`:
```python
class EffectDispatcher(Protocol):
    async def execute(
        self,
        envelope: CommandEnvelope,
        policy: EffectPolicyPlan,
        *,
        state: AgentState | None = None,
        decision: Decision | None = None,
    ) -> object: ...
```

`lca/contracts/protocols/runtime/runtime/composition.py:148-157`(`EffectDispatcherFactory` Protocol):
```python
class EffectDispatcherFactory(Protocol):
    def create(
        self,
        *,
        state: AgentState | None = None,
        decision: Decision | None = None,
    ) -> EffectDispatcher: ...
```

`lca/contracts/protocols/runtime/runtime/composition.py:95`(`effect_gateway: EffectDispatcher` typed injection)同步扩展,确保 factory 通过 typed kwargs 注入,不依赖 metadata 偷读。

`lca/harness/declarative/execute/dispatch.py`:
```python
class RegistryEffectDispatcher(EffectDispatcher):
    async def execute(
        self,
        envelope: CommandEnvelope,
        policy: EffectPolicyPlan,
        *,
        state: AgentState | None = None,
        decision: Decision | None = None,
    ) -> object:
        # state / decision 通过 typed keyword-only 参数,不从 envelope.metadata 偷
        ...
```

`lca/harness/declarative/execute/dispatch.py` 内 `_existing_effect_receipt` / `_validated_effect_class` 函数删除所有 `envelope.metadata.get("state", ...)` / `envelope.metadata.get("decision", ...)` 偷读路径;若需要 state / decision,从 typed 参数取。

并在 `effect.execute` 节点执行时(`bundles/concept/effect/effect_execute.yaml` 调起 graph kernel)把 state / decision 通过 typed kwargs 传进 `RegistryEffectDispatcher.execute`。

**Step 5.2.4: 改 effect_execute.yaml**

```yaml
- id: effect.execute
  factory: effect.execute
  inputs: [envelope, decision, state]
  outputs: [receipts]
```

**Step 5.2.5: PipelineSafeExecutor 不再读图(`act 业务不知道图存在`边界守护)**

`lca/cognition/body/executor/pipeline_safe_executor.py` 当前在 execute 内调用 `get_current_plan_ref()` / `get_current_run_scope()`(observability scope seam,目的 mint_envelope)。这是图边界渗透。

修复:把 plan_ref / scope_ref 改为构造时注入(typed kwargs),而不是从 observability scope 偷:

```python
class PipelineSafeExecutor(SafeExecutor):
    def __init__(
        self,
        permission_manifest: ToolPermissionManifest,
        *,
        plan_ref_provider: Callable[[], str | None] | None = None,
        scope_ref_provider: Callable[[], str] | None = None,
    ):
        # 构造时注入 plan_ref / scope_ref provider;测试可注入 mock;
        # 生产可注入「读 contextvar」adapter(observability 仍是 single seam)
        ...
```

并在 `PipelineSafeExecutor.execute(...)`:
```python
plan_ref = self._plan_ref_provider() if self._plan_ref_provider else None
scope_ref = self._scope_ref_provider() if self._scope_ref_provider else "default"
```

**「act 业务不感知图」verification:**

```bash
grep -rn "from lca.framework.graph\|from lca.contracts.protocols.graph\|from lca.framework" lca/cognition/ lca/plugins/cognitive/body/ 2>/dev/null
```

Expected: 0 matches(`Body / SimpleBody / PipelineSafeExecutor / ActionRegistry / Action / UseToolOperation` 等 act 业务模块不 import 图 kernel)。

```bash
grep -rn "context.runtime.state\|context.runtime.plan_ref\|NodeContext\|NodeInput\|NodeOutput" lca/cognition/body/ 2>/dev/null
```

Expected: 0 matches(act 业务不直接操作 NodeContext / port_values,只通过 SafeExecutor / Body 接口)。

**Step 5.2.6: 跑整体 verify**

```bash
ruff check --fix
ruff format
./scripts/lint-imports.sh
./scripts/lca-ops plan tree web-standard
./scripts/lca-ops validate_profile_plans profiles/web-standard.yaml
pytest tests/act tests/effect tests/harness/declarative -q
./scripts/lca-ops audit-state-writers
# PR-1 同步验证(ensure 整体 plan 不互锁):
./scripts/lca-ops why approve
```

Expected: 全 exit 0

**Step 5.2.7a: 抽 `needs_approval` 到 typed port + G-9 修 `act.approve.gate` 偷图(L-2 / G-9)**

> **为什么**:PR-1 Step 1.5 + 现有 `act.approve.gate` 内部都通过 `decision.extra.get("needs_approval", False)` 读 metadata,违反 C13「typed Contract 跨边界 = fail-loud」。同时 `act.approve.gate` 内部 `_resolve_port` 函数(`approve_gate.py:78-87`)用 `getattr(context.runtime, name, None)` 偷图 runtime,违反「act 业务不知道图存在」边界。本步同步修两处。

**Files:**
- Modify: `lca/contracts/models/core/execution/decision.py`(Decision 加 typed `needs_approval: bool` 字段,替代 `extra["needs_approval"]`)
- Modify: `lca/nodes/act/authorize/authorize.py`(emit typed `approval_required: bool` from `decision.needs_approval`)
- Modify: `lca/nodes/intervene/approve_gate.py`(删除 `getattr(context.runtime, ...)` 偷图;改读 typed `decision.needs_approval`)
- Create: `tests/contracts/test_decision_needs_approval_typed.py`
- Create: `tests/intervene/test_approve_gate_no_runtime_grab.py`

**Step 5.2.7a.1: 写 failing test — Decision.needs_approval typed**

```python
# tests/contracts/test_decision_needs_approval_typed.py
from lca.contracts.models.core.execution.decision import Decision


def test_decision_has_typed_needs_approval_field():
    """L-2: needs_approval 应是 typed 字段,不是 extra dict."""
    d = Decision(decision_id="dec-1", action_type="use_tool", needs_approval=True)
    assert d.needs_approval is True


def test_decision_needs_approval_defaults_false():
    d = Decision(decision_id="dec-2", action_type="use_tool")
    assert d.needs_approval is False
```

Run: `pytest tests/contracts/test_decision_needs_approval_typed.py -v`
Expected: FAIL — Decision 没有 typed needs_approval 字段

**Step 5.2.7a.2: 改 Decision**

`lca/contracts/models/core/execution/decision.py` 在 Decision dataclass 加:
```python
needs_approval: bool = False
```

并把现有 `extra.get("needs_approval", False)` 调用点全部改为 `decision.needs_approval`。

**Step 5.2.7a.3: 改 `act.authorize` 用 typed**

`lca/nodes/act/authorize/authorize.py` PR-1 加的 `approval_required = bool(decision.extra.get("needs_approval", False))` 改为:
```python
approval_required = bool(decision.needs_approval)
```

**Step 5.2.7a.4: 写 failing test — approve_gate 不偷 context.runtime**

```python
# tests/intervene/test_approve_gate_no_runtime_grab.py
import pytest
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeContext, NodeInput
from lca.nodes.intervene.approve_gate import ActApproveGateExecutor


@pytest.mark.asyncio
async def test_approve_gate_reads_only_typed_ports_not_runtime():
    """G-9: approve_gate 应只读 typed ports,不偷 context.runtime.*"""
    decision = Decision(decision_id=new_id("dec"), action_type="use_tool", needs_approval=True)
    # runtime 故意不提供 decision / 也不提供 needs_approval 字段
    runtime = type("R", (), {})()
    node = ActApproveGateExecutor()
    out = await node.node_execute(
        NodeContext(runtime=runtime, metadata={}),
        NodeInput(port_values={"decision": decision, "command": None}),
    )
    # 应从 typed port decision 读 needs_approval
    assert out.port_values["decision"] == decision
```

Run: `pytest tests/intervene/test_approve_gate_no_runtime_grab.py -v`
Expected: FAIL — approve_gate 偷 context.runtime

**Step 5.2.7a.5: 改 `act.approve.gate` 删 `_resolve_port`**

`lca/nodes/intervene/approve_gate.py:78-87` 删除 `_resolve_port(context, name)` 函数(用 `getattr(context.runtime, name, None)` 偷图)。

`node_execute` 内 `decision.extra.get("needs_approval", False)` 改为 `decision.needs_approval`。

**Step 5.2.7a.6: 跑测试 verify pass + 「act 业务不知道图存在」verification**

Run: `pytest tests/intervene/test_approve_gate_no_runtime_grab.py tests/contracts/test_decision_needs_approval_typed.py -v`
Expected: PASS

```bash
grep -rn "context\.runtime\|getattr.*runtime\|decision\.extra" lca/nodes/intervene/ lca/nodes/act/ lca/cognition/body/executor/
```

Expected: 仅「typed port 反查 typed field」的间接引用(如 `decision.needs_approval` 这类 typed 属性访问),0 个 `context.runtime.*` / `getattr.*runtime` / `decision.extra.get` 直接调用

**Step 5.2.7: G-5 garbage verification**

```bash
grep -rn "metadata=.state\|metadata={\"state" lca/nodes/act/ lca/harness/declarative/
```

Expected: 0 matches(state 不再进 metadata)

```bash
grep -rn "metadata=.decision\|metadata={\"decision" lca/nodes/act/ lca/harness/declarative/
```

Expected: 0 matches(decision 不再进 metadata)

**Step 5.2.8: Commit**

```bash
git add docs/adr/0235-act-envelope-typed-port-hygiene.md
git add lca/nodes/act/envelope/envelope.py
git add lca/harness/declarative/execute/dispatch.py
git add lca/contracts/protocols/declarative/declarative_1/declarative_execution.py
git add lca/contracts/protocols/runtime/runtime/composition.py
git add lca/cognition/body/executor/pipeline_safe_executor.py
git add bundles/act/act_subgraph.yaml bundles/concept/effect/effect_execute.yaml
git add tests/act/test_envelope_typed_port_hygiene.py
git commit -m "refactor(graph): extract state/decision from envelope.metadata to typed port (PR-5, ADR-0235)

Closes 评审 §4.2 C13 violation + G-5 garbage + 「act 业务不知道图存在」边界.
Aligns with ADR-0195 §1.4 C13 (typed Contract across boundary = fail-loud).
metadata now only holds op-relative fields; state/decision via typed ports.
PipelineSafeExecutor stops reading graph runtime state via observability scope.
EffectDispatcherFactory typed-injection extended for state/decision."
```

## PR-5 acceptance

| ID | Criterion | Verify |
|---|---|---|
| P5.A1 | ADR-0235 status = Accepted | `docs/adr/README.md` |
| P5.A2 | `act.envelope.metadata` 不含 `state` / `decision` | `grep "metadata=.state\|metadata={\"state\|metadata=.decision" lca/nodes/act/ lca/harness/declarative/` = 0 matches |
| P5.A3 | `act.envelope.declared_inputs` = `("decision", "state")` | `grep "declared_inputs" lca/nodes/act/envelope/envelope.py` |
| P5.A4 | `EffectDispatcher.execute` Protocol 新签名带 typed `state / decision` keyword-only | `grep "state:\|decision:" lca/contracts/protocols/declarative/declarative_1/declarative_execution.py` |
| P5.A5 | `EffectDispatcherFactory` Protocol + `composition.py:95` 同步扩展 typed injection | `grep "state\|decision" lca/contracts/protocols/runtime/runtime/composition.py` |
| P5.A6 | `effect.execute` 节点 declared_inputs 含 typed `decision / state` | bundle yaml |
| P5.A7 | **「act 业务不知道图存在」**:Body / SimpleBody / PipelineSafeExecutor / ActionRegistry / Action / UseToolOperation 不 import `lca/framework/graph/` 或 typed-port kernel | `grep -rn "from lca.framework.graph\|from lca.contracts.protocols.graph\|NodeContext\|NodeInput\|NodeOutput" lca/cognition/ lca/plugins/cognitive/body/` = 0 matches |
| P5.A8 | **PipelineSafeExecutor 不再通过 observability scope 偷图运行时数据**:构造时注入 `plan_ref_provider / scope_ref_provider` typed kwargs | `grep "get_current_plan_ref\|get_current_run_scope" lca/cognition/body/executor/pipeline_safe_executor.py` = 0 matches |
| P5.A9 | C1–C13 持有(C13 修复是本 PR 的目标) | PR verification matrix |
| P5.A10 | **L-2 + G-9 typed 卫生**:`Decision.needs_approval: bool` 是 typed 字段(非 `extra["needs_approval"]`);`act.approve.gate` 不再读 `context.runtime.*` / `decision.extra.get("needs_approval")` | `pytest tests/contracts/test_decision_needs_approval_typed.py tests/intervene/test_approve_gate_no_runtime_grab.py -v`;`grep "decision.extra.get.\"needs_approval\"" lca/` = 0 matches |
| P5.A11 | `web-standard` 15 plans validated | validate_profile_plans |

---

# PR-6: (引用) run-health plan PR-3 — N:N fanout + PARALLEL default

> **Owner**: run-health team(本 plan 不重写 Task,仅作为 acceptance 引用)
> **Closes**: 评审 §6.4 + G-6 garbage
> **Predecessor**: run-health plan `docs/superpowers/plans/2026-09-16-run-health-and-execution-closure.md` PR-3 Task 3.1–3.6 + ADR-0232

## PR-6 本 plan 中的角色

本 plan **不写 task**,仅作为 umbrella acceptance 的引用段;确保评审 §6.4 + G-6 的 verification 跟随 run-health PR-3 落地。

## PR-6 acceptance(本 plan 引用 — 涵盖整个 run-health plan 3 个 PR 而非仅 PR-3)

### PR-6 acceptance · run-health PR-3(N:N fanout + PARALLEL,F-4 / G-6)

| ID | Criterion | Verify(跟随 run-health plan) |
|---|---|---|
| P6.A1 | ADR-0232 status = Accepted | run-health plan PR-3 Task 3.1 落地 |
| P6.A2 | `act.fanout` 真支持 N:N(5 envelope in → `next_hint="fanout_ntom"`) | run-health plan PR-3 Task 3.3 acceptance |
| P6.A3 | `act.join` 真支持 N:N partial-failure policy(全停 / 部分承认+审计 / HITL) | run-health plan PR-3 Task 3.4 acceptance |
| P6.A4 | `ToolBatchExecutor` PARALLEL default(read-only tools) | run-health plan PR-3 Task 3.5 acceptance |
| P6.A5 | audit `run_feb0f21ee770` 5 read-only runCommand 在 <200ms 完成(vs 220ms serial) | run-health plan PR-3 acceptance |
| P6.A6 | G-6 garbage:`next_hint="fanout_ntom"` 在 act_deriver 报 `ok` | run-health plan PR-3 deriver 表 |

### PR-6 acceptance · run-health PR-1(Health contract + 9 derivers + 4 consumers,L-6 / L-7 / B-2/B-4/B-5/B-6/B-7/B-8/B-9)

| ID | Criterion | Verify |
|---|---|---|
| P6.A7 | `RunHealthReport` typed contract frozen `extra="forbid"` + 7 derivers via `importlib.metadata.entry_points` | run-health plan PR-1 Task 1.1-1.4 |
| P6.A8 | `act_deriver` 把 `next_hint="fanout_ntom"` 映射到 `ok`,`fanout_1to1` → `degraded`(与 PR-6.A6 联动) | run-health plan PR-1 Task 1.3 act_deriver |
| P6.A9 | `tool_deriver` 修 B-2:`emit_diagnostic` default `status="failed"` → `"info"` + 5 call sites 显式 `status=DiagnosticStatus.*` | run-health plan PR-1 Task 1.5 |
| P6.A10 | C11 escape hatch ADR-0233:`AgentRunFinished` → `spine.lifecycle.run_finished`(修 B-5 `terminal_event_seq=0`) | run-health plan PR-1 ADR-0233 |
| P6.A11 | `manifest.json` 加 `health_summary: RunHealthSummary` 字段;`record_terminal_materialization` 加 per-run-id flock(C9 幂等,修 X-3) | run-health plan PR-1 Task 1.5 + C9-1 |
| P6.A12 | `lca-ops runs health <run_id>` 新 CLI | run-health plan PR-1 Task 1.5 |

### PR-6 acceptance · run-health PR-2(SimpleBody multi-call,B-1 / L-4)

| ID | Criterion | Verify |
|---|---|---|
| P6.A13 | `SimpleBody.dispatch_tool_calls` (复数):1 个 `surface/assistant_message` + N 个 `surface/tool_result` per decision cycle | run-health plan PR-2 Task 2.1 |
| P6.A14 | B-1 历史注入 broken 修复:orphan tool result 在 `derive_messages` 仍被 orphan-drop 守护,但 `_drop_orphan_tool_results` 不再静默删 4/5 | run-health plan PR-2 Task 2.2 |
| P6.A15 | `act.observe` 接收 N 个 receipt(N:N 时)而非单 receipt | run-health plan PR-2 Task 2.3 |

### PR-6 acceptance · restart-safety / old-run / forward-compat

| ID | Criterion | Verify |
|---|---|---|
| P6.A16 | R-1 ~ R-5 restart-safety(本 plan 所有 PR 落地后 `kernel-restart` 0 退出) | `tests/integration/test_old_runs_still_readable.py` |
| P6.A17 | O-1 ~ O-5 old-run safety(3 个 audit run 仍可读) | 同上 |
| P6.A18 | F-1 ~ F-3 forward-compat(每个 PR 单独合并,无相互依赖) | 每 PR `verify-pr.sh` |

---

# PR-7: Dual lineage 债收尾 — 删 `agent.run.phase` + declarative-* edge SSOT (ADR-0236)

> **Owner**: graph kernel + agent team
> **Priority**: P1(独立 PR,与 6 个 act 子图 PR 解耦)
> **Closes**: 评审报告 §1.4 dual lineage + G-8 + `02-proposed-graph.md` §6.3 Merge→Delete 行 + `03-six-column-0206.md` Delete 行 + `bundles/agent/run_phase.yaml` 的 `delete-when: N/A` 文档陷阱
> **Predecessor**: ADR-0236 Accepted(本 PR Task 1;写「`agent.run.phase` delete-when 重新评估」理由)
> **No COMPAT shim** —— six-column-0206 已明令 Delete `agent.run.phase` + `declarative-phase-graph` + `declarative-recovery`,不允许 compat 后门

## PR-7 必要性

`phase-graph-node-orchestration/03-six-column-0206.md` Merge→Delete 行明确:
- `agent.run.phase 线性外环` → `Merge→Delete`(本图与 outer `phase.main.outer` 重复,production profile 只能选其一)
- `declarative-phase-graph 边 SSOT` → `Delete`(与 outer YAML 双 ControlPlan)
- `declarative-recovery 独挂恢复边` → `Delete`(恢复边进 outer)

但当前事实:
- `bundles/agent/run_phase.yaml:34` `id: agent.run.phase` 仍存在,`delete-when: N/A`(**文档陷阱:N/A ≠ 永不删,而是「当时未定」**)
- `bundles/declarative-phase-graph.yaml:7-19` delete-when 列了「All production profiles migrated to region-tag path AND ADR-0210 升 Accepted」—— 实际 `profiles/benchmark.yaml:37` + `profiles/cordis-creator.yaml:31` 仍引用,**两个条件都没达成**
- `bundles/declarative-recovery.yaml` 仍被 recovery profile 引用

PR-7 落地后:outer `phase.main.outer` 是唯一 control spine,recovery 进 outer YAML(declarative-recovery 删除条件达成)。

## PR-7 Task 1: 写 ADR-0236

**Files:**
- Create: `docs/adr/0236-dual-lineage-retirement.md`

**Interfaces (ADR content outline):**
- Status: Proposed → Accepted
- Context: phase-graph-node-orchestration §6.3 + §7 已认定 dual lineage A vs B vs C 是 M1 P0 债,但当前:`agent.run.phase` 仍在(`delete-when: N/A` 文档陷阱)+ `declarative-phase-graph` + `declarative-recovery` 仍被 `benchmark.yaml` + `cordis-creator.yaml` 引用 + ADR-0210 未升 Accepted。3 个 delete-when 条件任一未达成。
- Decision: 一次性收口:
  1. `agent.run.phase` bundle 删除,仅保留 `phase.main.outer` 作为 production control spine(ADR-0221 cutover 已隐含)
  2. `declarative-phase-graph.yaml` 删除,所有 edge 走 outer YAML(typed-port 改造后 outer 自含 recovery / loop budget 边)
  3. `declarative-recovery.yaml` 删除,recovery 边进 outer YAML(`reflect.main → think.main` 边谓词走 `routing.next_hint == admit_recovery`)
  4. `profiles/benchmark.yaml` + `profiles/cordis-creator.yaml` 改为只用 region-tag path(ADR-0210 §6.5 P7 region-tag path)
  5. ADR-0210 升 Accepted(若尚未)
- Alternatives considered:
  - (a) 维持 dual lineage——拒绝:违反 C7 control/observation separation + 双 SSOT
  - (b) 仅删 1 个 bundle——拒绝:不彻底;remaining bundle 仍构成 dual SSOT
  - (c) 一次收口 3 bundle + 2 profile + ADR-0210 升 Accepted(选这个)——接受:AGENTS.md §4「引入 compat shim 同一 PR 必须删」+ six-column-0206 M1 P0
- Consequences:
  - `bundles/agent/run_phase.yaml` 删除
  - `bundles/declarative-phase-graph.yaml` 删除
  - `bundles/declarative-recovery.yaml` 删除
  - `profiles/benchmark.yaml` + `profiles/cordis-creator.yaml` 改用 region-tag path
  - ADR-0210 升 Accepted
  - `lca/concept/* / primitive/* / agent/*` 等所有 bundle 重新 validate

**Step 7.1.1: 写 ADR 草稿 → 评审 → Accepted**

## PR-7 Task 2: 删 3 个 bundle + 改 2 个 profile + ADR-0210 升 Accepted

> Pre-flight:ADR-0236 status = Accepted

**Files:**
- Delete: `bundles/agent/run_phase.yaml`(commit `rm`)
- Delete: `bundles/declarative-phase-graph.yaml`(commit `rm`)
- Delete: `bundles/declarative-recovery.yaml`(commit `rm`)
- Modify: `profiles/benchmark.yaml`(删除 `bundles/declarative-phase-graph.yaml` 引用,改用 region-tag path)
- Modify: `profiles/cordis-creator.yaml`(同上)
- Modify: `docs/adr/0210-*.md` Status: Proposed → Accepted(若尚未)
- Create: `tests/integration/test_no_dual_lineage.py`(regression test)

**Step 7.2.1: 写 failing test — dual lineage 不存在**

```python
# tests/integration/test_no_dual_lineage.py
import pytest
from pathlib import Path


def test_no_agent_run_phase_bundle():
    """PR-7: agent.run.phase bundle 已删(G-8 + dual lineage debt 收口)"""
    assert not Path("bundles/agent/run_phase.yaml").exists()


def test_no_declarative_phase_graph_bundle():
    """PR-7: declarative-phase-graph bundle 已删(outer YAML 自含 edges)"""
    assert not Path("bundles/declarative-phase-graph.yaml").exists()


def test_no_declarative_recovery_bundle():
    """PR-7: declarative-recovery bundle 已删(recovery 边进 outer YAML)"""
    assert not Path("bundles/declarative-recovery.yaml").exists()


def test_profiles_use_region_tag_path():
    """PR-7: benchmark.yaml + cordis-creator.yaml 不再引用 declarative-*"""
    for profile in ("benchmark.yaml", "cordis-creator.yaml"):
        content = Path(f"profiles/{profile}").read_text()
        assert "declarative-phase-graph" not in content
        assert "declarative-recovery" not in content
        assert "agent.run.phase" not in content
```

Run: `pytest tests/integration/test_no_dual_lineage.py -v`
Expected: FAIL — 3 个 bundle 仍存在

**Step 7.2.2: 删 3 个 bundle + 改 2 个 profile + ADR-0210 升 Accepted**

```bash
git rm bundles/agent/run_phase.yaml
git rm bundles/declarative-phase-graph.yaml
git rm bundles/declarative-recovery.yaml
# 改 2 profile
sed -i '/declarative-phase-graph\|declarative-recovery\|agent\.run\.phase/d' profiles/benchmark.yaml
sed -i '/declarative-phase-graph\|declarative-recovery\|agent\.run\.phase/d' profiles/cordis-creator.yaml
# 改 ADR-0210 status
sed -i 's/Status: Proposed/Status: Accepted/' docs/adr/0210-*.md
git add docs/adr/0210-*.md
```

**Step 7.2.3: 跑测试 verify pass**

Run: `pytest tests/integration/test_no_dual_lineage.py -v`
Expected: PASS

**Step 7.2.4: 跑整体 verify**

```bash
ruff check --fix
ruff format
./scripts/lint-imports.sh
./scripts/lca-ops plan tree web-standard
./scripts/lca-ops validate_profile_plans profiles/web-standard.yaml
./scripts/lca-ops validate_profile_plans profiles/benchmark.yaml
./scripts/lca-ops validate_profile_plans profiles/cordis-creator.yaml
./scripts/lca-ops audit-state-writers
pytest tests/integration -q
```

Expected: 全 exit 0;3 个 profile 都 validate 通过

**Step 7.2.5: Commit**

```bash
git add docs/adr/0236-dual-lineage-retirement.md
git rm bundles/agent/run_phase.yaml
git rm bundles/declarative-phase-graph.yaml
git rm bundles/declarative-recovery.yaml
git add profiles/benchmark.yaml profiles/cordis-creator.yaml
git add docs/adr/0210-*.md
git add tests/integration/test_no_dual_lineage.py
git commit -m "refactor(graph): retire dual lineage A/B/C debt (PR-7, ADR-0236)

Closes 评审 §1.4 dual lineage + G-8 + 02-proposed-graph §6.3 Merge→Delete
+ 03-six-column-0206 Delete 行.
Removes bundles/agent/run_phase.yaml + bundles/declarative-phase-graph.yaml
+ bundles/declarative-recovery.yaml;profiles/benchmark.yaml +
profiles/cordis-creator.yaml migrate to region-tag path;ADR-0210 → Accepted.
outer phase.main.outer becomes sole control spine."
```

## PR-7 acceptance

| ID | Criterion | Verify |
|---|---|---|
| P7.A1 | ADR-0236 status = Accepted | `docs/adr/README.md` |
| P7.A2 | `bundles/agent/run_phase.yaml` 已删 | `pytest tests/integration/test_no_dual_lineage.py::test_no_agent_run_phase_bundle -v` |
| P7.A3 | `bundles/declarative-phase-graph.yaml` 已删 | `pytest tests/integration/test_no_dual_lineage.py::test_no_declarative_phase_graph_bundle -v` |
| P7.A4 | `bundles/declarative-recovery.yaml` 已删 | `pytest tests/integration/test_no_dual_lineage.py::test_no_declarative_recovery_bundle -v` |
| P7.A5 | `profiles/benchmark.yaml` + `cordis-creator.yaml` 不再引用 `declarative-*` / `agent.run.phase` | `pytest tests/integration/test_no_dual_lineage.py::test_profiles_use_region_tag_path -v` |
| P7.A6 | ADR-0210 status = Accepted | `grep "Status: Accepted" docs/adr/0210-*.md` |
| P7.A7 | `outer phase_main.yaml` 自含 recovery 边(`reflect.main → think.main when routing.next_hint == admit_recovery`) | `grep "admit_recovery" bundles/outer/phase_main.yaml` |
| P7.A8 | C1–C13 持有(outer single spine;Gate 位置不变;effect gateway 单轨) | PR verification matrix |
| P7.A9 | `web-standard` 15 plans validated 仍通过 | validate_profile_plans |
| P7.A10 | `benchmark.yaml` + `cordis-creator.yaml` validate 通过 | 同上 2 profile |

---

# Umbrella Self-Review

## 1 Spec coverage(对照 §A 来源 + 总验收矩阵 + L-* 漏点补齐)

| 来源 | 对应 PR / acceptance | 状态 |
|---|---|---|
| F-1 评审 §6.1 outer-edge wiring 位置修正 | PR-1 P1.A1–A9 | ✅ |
| F-2 评审 §6.2 5 闸外提 | PR-2 P2.A1–A9 | ✅ |
| F-3 评审 §6.3 observe 拆 normalize + terminate_decide | PR-3 P3.A1–A5 | ✅ |
| F-4 评审 §6.4 N:N fanout + PARALLEL | PR-6 P6.A1–A6(引用 run-health PR-3) | ✅ |
| F-5 评审 §6.5 闭集移到 contracts | PR-4 P4.A1–A4 | ✅ |
| F-6 评审 §4.2 C13 卫生 | PR-5 P5.A1–A11 | ✅ |
| **L-1 act.observe 偷图 runtime.journal** | **PR-3 Step 3.2.7a 新增 `act.observe.commit_fact` 节点** | ✅ |
| **L-2 act.authorize 读 `decision.extra["needs_approval"]`** | **PR-5 Step 5.2.7a 抽 `Decision.needs_approval: bool` typed 字段** | ✅ |
| **L-3 PipelineSafeExecutor 5 个本地 `executor.*` verdict_refs 第二套词表** | **PR-2 Step 2.2.7a 同步删除** | ✅(G-7) |
| **L-4 SimpleBody.dispatch_tool_call 直连 RunSessionWriter(B-1 multi-call)** | **PR-6 P6.A13–A15 引用 run-health PR-2** | ✅ |
| **L-5 dual lineage A vs B vs C 债** | **PR-7(独立 P1,ADR-0236)** | ✅ |
| **L-6 RunHealthReport 全套 contract + 9 deriver + 4 consumer** | **PR-6 P6.A7–A12 引用 run-health PR-1** | ✅ |
| **L-7 _TERMINAL_EVENT_TYPES 词表冲突 / C11 escape hatch ADR-0233** | **PR-6 P6.A10** | ✅ |
| **L-8 plan_sdk.py `approval_resume_node` 字段语义未与 lifter 同步** | **PR-1 Step 1.9.1** | ✅ |
| **L-9 act.approve.gate 偷 `context.runtime` 字段** | **PR-5 Step 5.2.7a 一并修(G-9)** | ✅ |
| G-1 ACTION_TO_PHASE 重复 | PR-1 Step 1.8 顺手收尾 | ✅ |
| G-2 PipelineSafeExecutor 5 闸 procedure | PR-2 P2.A3 + Step 2.2.7a(G-7) | ✅ |
| G-3 observe should_terminate 内嵌 | PR-3 P3.A2 | ✅ |
| G-4 _FAILURE_KIND_TO_ERROR_REASON 节点内 | PR-4 P4.A1 | ✅ |
| G-5 act.envelope metadata 反抽 | PR-5 P5.A2 | ✅ |
| G-6 fanout 1:1 退化 | PR-6 P6.A6 | ✅ |
| **G-7 verdict_refs 第二套词表** | **PR-2 Step 2.2.7a P2.A8** | ✅ |
| **G-8 dual lineage debt** | **PR-7 G-8 acceptance** | ✅ |
| **G-9 act.approve.gate 偷图 runtime** | **PR-5 Step 5.2.7a P5.A10** | ✅ |
| 总验收 U-1 ~ U-8 | 每 PR acceptance 加和 + 总 G 9 项 verification | ✅ |

## 2 Placeholder scan

搜索本 plan 的 placeholder 标志:
- "TBD" — 0
- "TODO" — 0
- "implement later" — 0
- "fill in details" — 0
- "add appropriate error handling" — 0
- "类似 Task N"(用具体步骤替代)
- 引用 types/functions 必须在前序 task 定义 — ✅(每 Step 列具体 import / signature)

## 3 Type consistency

| Type | 定义处 | 引用处 | 一致? |
|---|---|---|---|
| `ActApproveGateExecutor`(已存在) | `lca/nodes/intervene/approve_gate.py` | PR-1 wiring | ✅(不改签名,只改 wiring 位置) |
| `EffectPreDispatchEnvelopeCheckExecutor` | PR-2 Step 2.2.3 | 测试 + bundle | ✅ |
| `ActObserveTerminateDecideExecutor` | PR-3 Step 3.2.2 | 测试 + bundle | ✅ |
| `resolve_error_reason(failure_kind: str \| None) -> str \| None` | PR-4 Step 4.1.2 contracts | PR-4 observe.py 改造 | ✅ |
| `EffectDispatcher.execute` 新签名 `async def execute(envelope, policy, *, state=None, decision=None)` | PR-5 Step 5.2.3 | RegistryEffectDispatcher / `EffectDispatcherFactory.create(*, state, decision)` / `composition.py:95 effect_gateway` typed injection / effect.execute 节点 | ✅ |
| `decision / state` typed-port | PR-5 declared_inputs | effect_execute.yaml inputs | ✅ |
| `_validate_approval_resume_node(plan)` | PR-1 Step 1.9 lifter.py | `lift_plan()` 调用链 | ✅ |

## 4 重叠 / 冲突自检

- **PR-2 与 PR-3 文件互锁?** PR-2 改 `pipeline_safe_executor.py` + `act_subgraph.yaml` + `effect_execute.yaml`(新增 `effect.pre_dispatch.envelope_check` 节点);PR-3 改 `observe.py` + `terminate_decide.py` + `act_subgraph.yaml` + `phase_main.yaml`。`act_subgraph.yaml` 两个 PR 都改 → **串行**(PR-2 → PR-3)。
- **PR-3 与 PR-4 文件互锁?** PR-3 改 `observe.py` 拆节点;PR-4 也改 `observe.py`(删 dict)。→ **串行**(PR-3 → PR-4)。
- **PR-2 与 PR-5 文件互锁?** PR-2 改 `pipeline_safe_executor.py`;PR-5 改 `envelope.py` + `dispatch.py` + `composition.py` + `effect_execute.yaml`。`effect_execute.yaml` 都改(PR-2 加 `verdict_refs` 输入,PR-5 加 `decision / state` 输入);`pipeline_safe_executor.py` 两个 PR 都改(PR-2 拆 5 闸 → graph 节点;PR-5 不再读 observability scope 偷图)。→ **串行**(PR-2 → PR-5)。
- **PR-5 与 PR-3 顺序?** PR-5 改 `effect.execute` declared_inputs;PR-3 改 `act.observe`。无直接互锁,但 PR-3 的 bundle 边需要 outer edge 配合 PR-5 的 typed port — 串行更安全。
- **PR-1 与 PR-5 顺序?** PR-1 改 `act.authorize` 新增 `approval_required` typed output;PR-5 改 `act.envelope` 新增 `state / decision` typed input。两者都在 `act_subgraph.yaml` 节点 inputs/outputs — PR-1 先(act.authorize 紧靠 act.validate),PR-5 后(act.envelope 紧靠 act.authorize → act.approve.gate → act.envelope 链路)。→ **串行**(PR-1 → PR-5)。

**修订最终顺序(7 PR):PR-1 → PR-2 → PR-5 → PR-3 → PR-4 → PR-6 → PR-7。**

- **PR-7 与 6 PR 解耦**(独立 P1,触及 outer plan SSOT,需 ADR-0236);可与 PR-2 ~ PR-6 任意并行 dispatch(file 互锁为零)
- **PR-6 与 PR-1 ~ PR-5 解耦**(纯引用 run-health plan);可并行
- **PR-1 / PR-2 / PR-3 / PR-4 / PR-5 串行**(已在 §4 列出互锁点)

## 5 事实底稿偏差自检(本次 plan 重写发现的偏差)

| # | 原 plan 描述 | 现场事实 | 偏差后果 | 修订 |
|---|---|---|---|---|
| D-1 | PR-1「outer-edge wiring 收尾」 | `bundles/outer/phase_main.yaml:128-278` 已落地 wiring(commit `f4ee5363b`),但位置错(在 act.main 之后,违反 spec §3.2) | 加 5 条 outer edge 是重复 + 错误位置 | PR-1 重写为「删除错位 wiring + 迁到 act_subgraph 内部 + boot fail-loud + Step 1.9.1 plan_sdk 字段语义同步(L-8)」 |
| D-2 | PR-5 `EffectDispatcher.execute` 签名改 | `EffectDispatcherFactory` Protocol(`composition.py:148-157`)与 `composition.py:95 effect_gateway: EffectDispatcher` 注入边界会被 broken | 「修改一个签名破坏多处注入」 | PR-5 Task 2 新增 `EffectDispatcherFactory.create(*, state, decision)` + `composition.py:95` typed injection 同步扩展 |
| D-3 | Self-review §4 已重排 PR 顺序 | plan 标题和执行顺序段仍是 `PR-1 → PR-2 → PR-3 → PR-4 → PR-5 → PR-6` | 内部不一致 | 同步重排 plan 头部 + 执行策略 + Handoff 段的 PR 顺序 |
| D-4 | PR-3 只拆 normalize + terminate_decide,漏掉 RunFact commit 偷图 | `act.observe.py:149` `getattr(context.runtime, "journal", None)` 偷图 runtime | 「act 业务不知道图存在」边界违反 | PR-3 Step 3.2.7a 新增 `act.observe.commit_fact` 独立节点(L-1) |
| D-5 | PR-5 boundary grep 只查 `metadata=.*state`,漏 `context.runtime.* / getattr.*runtime / decision.extra.get` | `act.authorize` + `act.approve.gate` 同样越界 | PR-5 修复不彻底 | PR-5 Step 5.2.7a 扩 grep + 抽 `Decision.needs_approval` typed + 删 `_resolve_port`(L-2 / L-9 / G-9) |
| D-6 | PR-2 只拆 5 闸到 graph,漏 5 个 `executor.*` 本地 verdict_refs 词表 | `pipeline_safe_executor.py:284/297/303/308/327` 第二套语义词表 | 与 graph canonical `effect.pre_dispatch.*` 冲突 | PR-2 Step 2.2.7a 同步删除 + G-7 入清单 |
| D-7 | PR-6 只引用 run-health PR-3,漏 PR-1(health contract) / PR-2(B-1 multi-call) | run-health plan 3 个 PR 全是 act 子图债 | L-4 / L-6 / L-7 未覆盖 | PR-6 扩到 18 条 acceptance(P6.A1–A18)+ PR-6 加 restart-safety / old-run / forward-compat |
| D-8 | plan 完全漏 dual lineage debt | `agent.run.phase` + `declarative-phase-graph` + `declarative-recovery` 仍存在 + ADR-0210 未升 Accepted | L-5 dual SSOT 债无主 | 新增 PR-7(独立 P1,ADR-0236)+ G-8 入清单 |

---

# 执行 Handoff

Plan 已落地到 `docs/superpowers/plans/2026-09-16-act-subgraph-tightening.md`,umbrella **7 PR**(自检全过,覆盖所有 F-* / G-* / L-* / U-*):

- **6 PR 串行组**:`PR-1 → PR-2 → PR-5 → PR-3 → PR-4 → PR-6`(act 子图收紧,file 互锁已解开)
- **1 PR 独立组**:`PR-7`(dual lineage 债,ADR-0236,与 6 PR 无 file 互锁,可任意并行)

**修复后边界对照:**

| 边界 | 修复前 | 修复后 |
|---|---|---|
| 「act 业务不知道图存在」 | 4 处越界(envelope.state / observe.journal / approve_gate.runtime / authorize.extra) | **0 处** — 全 typed port + Step 5.2.5 / Step 5.2.7a grep 守护 |
| 「图不知道 act 业务」 | 0 处 | 0 处(维持) |
| envelope 单据污染(C2) | `metadata={state, decision}` | 仅 `effect_class / operation` |
| C13 typed Contract 跨边界 | 4 处 metadata 反读 | **0 处** |
| 词表一致性 | 5 个 `executor.*` 第二套语义词表 | **统一** graph canonical `effect.pre_dispatch.*` |
| Dual SSOT(control + observation) | agent.run.phase / declarative-* 三套并行 | **outer phase.main.outer 唯一** |

**两个执行选项:**

1. **Subagent-Driven (推荐)** — 每个 PR dispatch 一个 fresh subagent,review between PRs,快速迭代。需要我开 `superpowers:subagent-driven-development`。
2. **Inline Execution** — 当前 session 顺序跑每个 PR,checkpoint review。需要我开 `superpowers:executing-plans`。

**额外提示:** PR-1 P0 立刻可开(无 ADR 阻塞);PR-2 / PR-5 需先写 ADR-0234 / ADR-0235,Accepted 才合 PR。建议先开 PR-1 同时起草 2 份 ADR 草案并行。

---

# 执行期修订(2026-09-16,SDD wave 1 后)

## R-1 PR-1 Step 1.6 是 plan 缺陷,已按实际发布范围重写

Plan 原文断言「act_subgraph 的边引用 outer 的 `intervene.interrupt` / `terminal.commit`
是允许的,因为 `sub_spec_ref` 把外层节点暴露给内层」。**该断言错误**:

- `bundles/act/act_subgraph.yaml` 由 `lca/harness/declarative/compile/subgraph_resolver.py`
  的 `_load_bundle_graph_spec` 加载,其中 `factory=str(n["factory"])` 对**每个节点**硬性要求;
- outer `bundles/outer/phase_main.yaml` 由 `lca/framework/graph/plan_sdk.py` 的
  `parse_plan_yaml` 加载,`binding` 默认 `node_executor`,允许无 `factory` 节点。

两套 loader 的节点 schema 不同,所以子图**不能**命名其他 plan 的节点;照 Step 1.6 实施会让
`./scripts/lca-ops plan tree profiles/web-standard.yaml` 直接 `KeyError: 'factory'`。
实测:基线 `✓ all layers inflated and validated`,按 Step 1.6 改后崩。

**连带风险**:搬迁实现把 outer 的 `act.approve.gate` 变成 delegate 后,删掉了
`act.main → act.approve.gate` 进边与该 gate 的全部出边,只剩 `intervene.resume →` 一条进边
——HITL 在 outer 层完全断连(没有边能到达 `intervene.interrupt`)。这比原先「位置错误但连通」
更危险,且原有单测只断言 yaml 里边存在,测不出来。

**实际发布的 PR-1 范围**(commit `d9deb7952`):
1. `lift_graph_spec` 加 `_validate_approval_resume_node`:声明 gate 而缺 resume 边 → `PlanLiftError`;
2. `plan_sdk.plan()` docstring 固化 `approval_resume_node` 字段语义,避免 yaml 与 lifter 双规则;
3. 新增 5 条 wiring 不变量护栏,把上述两个回归钉死(`tests/act/test_approve_gate_wiring_invariants.py`);
4. 删 `_ACTION_TO_PHASE` 上方重复的注释块。

## R-2 G-1 是伪问题,已降级

Plan 称 `_ACTION_TO_PHASE` 与「act node waterfall」重复声明。全仓核查:
`grep -rn "ACTION_TO_PHASE" --include=*.py .` 仅 `simple_body.py:69` 一处定义 + `:309` 一处使用,
**没有任何第二份**。搬到 `lca/nodes/act/_phase_table.py` 反而会新增 `cognition → nodes` 跨层依赖,
与 lint-imports 方向相反。真实残渣只是那段注释被逐字复制两遍,已删。G-1 关闭方式改为注释去重。

## R-3 L-1 只完成一半,剩余明确划归 PR-5

PR-3(commit `0377d2ac4`)把 RunFact 落库拆成独立 `act.observe.commit_fact`,
职责分离达成。但该节点仍以 `getattr(runtime, "journal", None)` 取 kernel capability,
并在缺失时静默跳过落库——**边界与隐式降级都还在**。已在 Node 与 commit message 中如实记录,
归 PR-5(ADR-0235)处理,未在 PR-3 里虚报修复。

## 新增 PR-1b:把 gate 移到 act.authorize 与 act.envelope 之间(spec §3.2 原位)

前置 **ADR-0237**(子图输出冒泡 + outer 边互斥判定)。必须解决的设计点:

1. `act.approve.gate` 留在 act_subgraph 内(authorize 之后、envelope 之前),
   非批准分支(interrupt / rejected)在子图内**不出边**,让子图结束;
2. gate 的 `routing`(或 `approval_routing`)需冒泡为 `act.main` 的 declared_output
   ——沿用 PR-3 注释所述 kernel-wide port registry 传播机制,并验证确实可用;
3. outer 现有 `act.main → think.main`(按 `decision.action_type == use_tool`)与
   `act.main → reflect.main`(always)必须与新分支**互斥**,否则一次 act 会同时命中
   「进 interrupt」和「回 think」——这正是本仓反复治理的静默失败类;
4. `act.authorize` 需产出 typed `approval_required: bool`(替代 `decision.extra["needs_approval"]`
   的 metadata grep),该端口在本 PR 才有消费者,故不与 PR-1 一起提前发布死端口;
5. `lifter._validate_approval_resume_node` 改为对 outer plan 求值(resume 边在 outer)。

## 基线失败登记(AGENTS.md §6:以下为既有失败,非本次引入)

| 项 | 现象 | 验证方式 |
|---|---|---|
| `tests/loop/test_phase_registry.py` | `ModuleNotFoundError: lca.loop.phases` | 干净提交树同样报错 |
| `tests/loop/test_fact_gateway.py::test_cognitive_emit_context_manifested_via_gateway` | 失败 | 基线复现 |
| `tests/loop/test_tool_surface_commit.py::test_commit_body_tool_execute_end_appends_tool_role_message` | `Observation.content` AttributeError | 基线复现 |
| `tests/architecture/test_learning_review_lifecycle.py` | `ModuleNotFoundError: lca.harness.composition.plan_compiler` | 基线复现 |
| `ruff check lca/ tests/` | 352 errors | 本次改动 0 新增(3 处命中均在 `lifter.py` 既有行 461/695/707) |
| `./scripts/lca-ops validate_profile_plans` | 子命令不存在 | 用 `plan tree profiles/web-standard.yaml` 替代 |

## 执行事故登记

控制器一次 `ruff check --fix lca/ tests/` 作用域过宽,自动修复污染 140 个无关文件;
已用白名单方式还原(保留 7 个本次文件),工作树恢复为 0 意外改动。教训:门禁命令的
lint/format 修复类操作必须限定在 diff 文件集,不得对全仓跑 `--fix`。
