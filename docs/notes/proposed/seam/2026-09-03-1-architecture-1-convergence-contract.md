# Agent Note: 子 note 1 — 观测面 SSOT 收口剩余消费方迁移(L1 收尾)

Status: proposed

> 根 note 与元决策:[observation-convergence-root.md](2026-09-03-observation-convergence-root.md) / [ADR-0178](../../../adr/0178-observation-control-state-convergence.md)。本 note 承接 L1 SSOT 收口的剩余 PR-3 ~ PR-7 消费方迁移,与根 note L2 表对齐。

## Problem

`docs/notes/implemented/seam/2026-09-03-observation-ssot-registry.md` PR-1 ~ PR-2 已合(ssot.py + RunLocator Protocol + check_observation_ssot.py 9 条 lint)。但 PR-3 ~ PR-7 描述的消费方迁移**未实施**——根 note L2 表标记它们为"必发"但实际 git 上没动。

具体未迁移的反模式位置(根 note §L2 表复制):

- **反模式 2a**(30+ 处 Status 枚举字面字符串):`lca/contracts/models/observability/journal_doc.py:34/181`、`lca/contracts/protocols/declarative/declarative_execution.py:71/78`、`lca/harness/declarative/compile/phase_governance.py:290/332`、`lca/runtime/result_finalizer.py:70/93`、`lca/plugins/providers/run_ui_encoder/_encoder.py:118/122/124`、`lca/harness/projection/web.py:71`、`lca/harness/projection/agent_state.py:156`、`lca/harness/diagnostics/normalizer.py:126`、`lca/infrastructure/observability/stream/trace_inspector.py:194`、`lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py:283/289/290`、`lca/plugins/transport/webserver/handlers/runs/terminal/materialization.py:153`、`lca/plugins/transport/webserver/handlers/runs/session/session.py:66-71`、`lca/infrastructure/cli/commands/runs.py:157` 等
- **反模式 2c**:`lca/cognition/member_status/in_memory.py:54/55/63`、`lca/cognition/member_status/consult_policy.py:184` 用 `== RoleStatus.(DONE|FAILED)` 字面比较(自身注释禁止字面)
- **反模式 4**(`to_jsonable` 双份):根 note PR-3 标记合并,但 git 上 `_capture_io.py:33` 与 `projector.py:23` 仍并存

证据:`rg '"paused"' lca/ scripts/ tests/ | wc -l` 返回 > 30;`rg 'def to_jsonable' lca/ | wc -l` = 2(应 = 1)。

## Proposal

PR-3 + PR-4 合并为 1 个 PR(因 2a 全段走 `RunLifecycleStatus` + `ExecutionOutcome` enum 一次到位):

1. **PR-A(this note)** — `RunLifecycleStatus` 上提 contracts;30+ 处 Status 字面改 `is_terminal` / `is_success` / `is_failure`;`_capture_io.to_jsonable` + `projector.to_jsonable` 合并到 `ssot.to_jsonable`
2. **PR-B(this note)** — reader / writer / cli / declarative / projection 共 30+ 处改走 enum + Locator;新增 `kernel_log_path` / `exceptions_path` / `profile_snapshot_path` 3 个 RunLocator 方法
3. **PR-C(this note)** — `seam_key: str` → `CapabilityKey` enum

每个 PR 自带 acceptance criterion 子集 + test + lint 命中数降低。

## Decision criteria(可观察)

- `scripts/check_observation_ssot.py` 9 条规则 + 本 note 新增 4 条,合并后命中数从 9 → 0
- `rg 'def to_jsonable' lca/` = 1
- `rg '"paused"' lca/ scripts/ tests/ | grep -v ssot.py` = 0
- `rg '== RoleStatus\.(DONE|FAILED)' lca/ | grep -v role_status_rules.py` = 0
- `rg 'seam_key: str' lca/contracts/` = 0
- `rg 'from lca.plugins.transport.webserver.handlers.runs.session.session import RunStatus' lca/` = 0

## Alternatives considered

### Why not 直接合根 note 全部 PR-1 ~ PR-7?

违反 AGENTS.md §1 "1-3 PR 列表"。根 note 7 个 PR 跨 contracts / infrastructure / plugin / scripts 4 个 seam,**单 PR 不可审、不可回滚**。本 note 把 PR-3 ~ PR-7 拆 3 个 PR-A/B/C,各自 ≤ 200 行 diff,各自独立 delete-when。

### Why not 不收 `RoleStatus` 字面比较?

`lca/cognition/member_status/in_memory.py` 自身注释已写"禁止字面比较";`is_terminal_status` / `is_success_status` / `is_full_success_status` 已存在。**留字面 = 让代码继续违反自身注释**。

## Acceptance criteria

PR-A 合后:

- `lca/contracts/observability/ssot.py` `RunLifecycleStatus` 7 值 + 3 个判定函数已存在(根 note PR-1 已建)
- `lca/runtime/result_finalizer.py:70/93` 改走 `is_terminal_run_status(...)`,删除字面 `{"paused", "completed", "failed"}` 集
- `tests/runtime/test_result_finalizer.py` 新增 3 case 覆盖字面集迁移

PR-B 合后:

- `RunLocator` Protocol 补 `kernel_log_path` / `exceptions_path` / `profile_snapshot_path` 3 个方法(根 note PR-1 已建)
- `FilesystemRunLocator` 实现 3 个新方法
- `lca/plugins/transport/webserver/handlers/runs/doctor/step_check.py` 改走 `RunLocator.events_path`(承接根 note PR-7 `events_jsonl_exists` → `spine_file_exists`)

PR-C 合后:

- `lca/contracts/harness/composition/plugin.py:82/88/106` `seam_key: str` → `seam_key: CapabilityKey`
- 所有 Plugin Manifest `seam_keys` 字段同步

## Risks

- **30+ 处 Status 字面迁移**可能漏。**lint 守门**是唯一保险:`rg '"paused"' lca/ scripts/ tests/ | grep -v ssot.py` 必为 0。
- `RunLifecycleStatus` 与 `ExecutionOutcome` 语义边界:**前者是 run lifecycle 状态**,**后者是 step/phase/declarative 单次 outcome**。强行合并会让"run 在 phase 失败时是 FAILED 还是 RUNNING"语义模糊。**不合并**。
- `kernel_log_path` 的命名是 `kernel.log`(无 run_id 前缀),与 `spine_filename_for_run` 模板不一致。需要在 `naming.py` 显式声明这是"非 per-run 命名空间独立"。

## Delete-when

- **PR-A compat**(若保留旧 enum 字面比较):`# COMPAT(delete-when: 全 rg 命中 = 0 且稳定 ≥ 14 天, tracking: ADR-0178-note-1-A)`
- **PR-B compat**(若保留旧 `events.jsonl` 字符串):`# COMPAT(delete-when: 全部 reader 迁完且 rg zero non-doc, tracking: ADR-0178-note-1-B)`
- **PR-C compat**(若保留 `seam_key: str` 字段):`# COMPAT(delete-when: Profile / Bundle 全部重生成且 Capabilities SSOT 注册通过, tracking: ADR-0178-note-1-C)`

无 delete-when = 红:PR 必须补 ADR 或删除。

## Related

- [observation-convergence-root.md](2026-09-03-observation-convergence-root.md) — 根 note(实施编排)
- [ADR-0178](../../../adr/0178-observation-control-state-convergence.md) — 元决策
- [`docs/notes/implemented/seam/2026-09-03-observation-ssot-registry.md`](../../implemented/seam/2026-09-03-observation-ssot-registry.md) — 根 note 实施 status(本 note 承接 PR-3 ~ PR-7)
