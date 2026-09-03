---
name: lca-audit-notes
description: Use when running, interpreting, or acting on Agent Note audits in LCA — runs scripts/check_notes_tree.py (when enabled) and scripts/audit_adr_health.py, distinguishes real findings from noise, decides fix-in-place vs exception, and rejects unlimited-TODO residue per LCA AGENTS.md. Trigger phrases: "跑一下 check_notes_tree", "audit ADR", "note 体检", "lca-notes-audit", "体检报告", "fix the audit findings".
---

# Auditing LCA Agent Notes

A note audit is read-mostly until the agent picks a remediation. The two scripts have different scopes and read different trees; read both before deciding. This skill is guidance, not a script. The standing reference for unbounded TODO residue is [AGENTS.md §1 卫生清单](../../../AGENTS.md#1-开始前必须知道) — "无新增无期限 TODO"; if an audit surfaces one, fix or attach an explicit deletion date, do not wave it through.

## Run the audits

```sh
# (a) Notes-only structural check — runs once steps 3+ lands; until then manual.
uv run python scripts/check_notes_tree.py

# (b) ADR corpus health — read-only, never modifies docs/adr/.
uv run python scripts/audit_adr_health.py --out docs/notes/audit-<YYYY-MM-DD>.md
```

`audit_adr_health.py` is intentionally read-only by design ([script header](../../../scripts/audit_adr_health.py)); the output file is a diagnostic, not a migration plan. Save reports under `docs/notes/` as `audit-YYYY-MM-DD.md` so they show up in tree audits without polluting `docs/adr/`. The `audit-2026-09-03.md` already in the tree is the seed report that this workflow produced.

## Interpret findings

`audit_adr_health.py` surfaces five classes of finding (per its docstring):

1. **Status coverage** — every ADR declares its lifecycle in `## 状态` / `## Status` / inline `Superseded by` / `Status: …`. A missing field is a real finding; an unrecognized token (`Audit`, `Review`, `Explained`) is a second-class status, flagged but not a blocker.
2. **Status normalization** — the dominant token distribution; a spike in `Audit` / `Review` / `Explained` usually means a working draft is parked in `docs/adr/` instead of `docs/notes/proposed/`. That is a routing bug, not a status bug — the fix is to move the file, not to relabel the header.
3. **Numbering** — gaps, out-of-range ids, duplicate slugs. Gaps older than the Notes system are usually intentional (`docs/notes/` is now the off-ramp); flag them as informational, not failures.
4. **Cross-references** — `Superseded by` / `Supersedes` chains must resolve. A 404 here is a real finding and blocks the change; a chain pointing at a Notes path is correct and should be re-checked once the Notes class table grows.
5. **README index reconciliation** — every ADR is in [`docs/adr/README.md`](../../../docs/adr/README.md) and every file is in the index. Drift is a real finding; the fix is one PR editing the index.

`check_notes_tree.py` (when step 3 lands) checks header三行, `Status:` ↔ path consistency, `archived/` freeze, and the closed `class` set. Treat its findings as structural; the only valid response is fix the note or amend the README + script in lockstep.

## Real finding vs noise

Apply this split before touching any file:

- **Real finding** — broken cross-reference, drift between `Status:` and physical path, `class` value outside the closed set, README index missing an entry, archived note edited, ADR moved into `docs/notes/` by mistake. Each of these blocks the change.
- **Noise / informational** — tokenized `Status:` words that fall outside the dominant three (`Accepted` / `Proposed` / `Superseded`), gaps in the ADR numbering that predate the Notes system, second-class tokens (`Audit`, `Review`, `Explained`) on working drafts. Record these in the report; do not act on them in the audit PR.

Rule of thumb: if the fix would force a content change in `docs/adr/`, it is either a real finding that requires its own PR with ADR justification, or it is a routing bug (move the file, not rewrite the ADR).

## Fix in place vs add an exception

The default is **fix in place**. Three exceptions are valid; each must be recorded in the PR description, not in the file:

1. **Predicate drift across an unrelated refactor.** If the audit catches a token or path that a recent dependency rename produced (e.g. ADR references a module renamed in step 2), fix in place — the script run is the PR that owns it.
3. **Closed `class` expansion.** If a note needs a `class` outside the [README §2.2](../../../docs/notes/README.md#22-class嵌套闭集) closed set, expand the set in three places at once: the README table, `scripts/check_notes_tree.py`, and a one-line entry in the PR description naming the new class and one example note. No silent additions.
4. **Unbounded TODO residue** surfaced by the audit (per [AGENTS.md §1 卫生清单](../../../AGENTS.md)). Each residue gets either (a) an explicit deletion date written next to it, or (b) a `COMPAT(delete-when: <condition>, tracking: <ADR | issue>)` block per [AGENTS.md 兼容路径模板](../../../AGENTS.md). Bare `TODO` strings without a deletion condition are out-of-scope to fix in an audit PR — open a follow-up.

Anything else is fix-in-place. "Add an exception" is not a permission to defer to a future PR; either the finding is real and fixed here, or it is informational and stays in the report.

## Reporting and follow-up

The audit report should end with a table:

| Finding class | Count | Real? | Action |
|---|---|---|---|
| Status coverage | N | yes / no | fixed in this PR / left in report |
| Numbering gaps | N | no | informational |
| Cross-references | N | yes | fixed / follow-up issue |
| README index drift | N | yes | fixed in this PR |
| Unbounded TODO | N | yes | deletion date added / COMPAT block added / follow-up |

Do not delete the report. `docs/notes/audit-<date>.md` is the audit trail; the next audit cites it to show what changed since last run.

## Commands / 调用方式

默认走 `lca-ops notes-check`(结构体检,内部调 `scripts/check_notes_tree.py`);需要 ADR 全量审计用 `lca-ops notes-audit`(内部调 `scripts/audit_adr_health.py`);要拿机器可消费的 note 清单给 grep / 后续脚本用,加 `--json` 的 `lca-ops notes-list --json`。三条都是 agent 优先入口,CI / ad-hoc shell 调试才掉到裸脚本路径。