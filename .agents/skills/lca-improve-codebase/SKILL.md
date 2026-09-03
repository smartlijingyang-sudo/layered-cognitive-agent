---
name: lca-improve-codebase
description: Use when a concrete LCA module or area has already been picked for restructuring and the request is to turn it from a "candidate" into a small plan with a delete-when condition — not a multi-day rewrite. Distinct from lca-find-simplifications (which sweeps the whole repo for candidates): this skill owns the per-candidate drill-down, companion-skill chain, and 1–3 PR plan. Trigger phrases: "improve codebase", "candidate for restructure", "codebase audit", "legacy cleanup", "重构这块".
---

# Improving a Single LCA Codebase Area

Take one bounded candidate from "值得重构" to "小计划 + delete-when 条件", running the LCA standing rules against it. This skill is guidance, not a checklist — the work is judgement over a single seam or module, not a repository-wide survey. The taxonomy of what counts as a candidate is owned by [`lca-find-simplifications`](../lca-find-simplifications/SKILL.md); this skill owns the per-candidate flow that runs once a candidate has been picked.

## Distinction from siblings

- **`lca-find-simplifications`** — the sweep skill; finds candidates across the whole repo and triages them. **Always run it first** when the scope is unclear. If the candidate fails its "bounded / measurable / 1–3 PR / delete-when" gates, route back here.
- **`lca-improve-codebase`** (this skill) — given *one* candidate, scope it, run the companions, write a small plan. Does not re-scan the repo for more candidates.
- **`lca-code-review`** — applies after PRs exist; reviews the candidate against standing rules.
- **`lca-pre-push-checks`** — selects the local evidence each PR must clear before push.

## Scope (when to invoke)

Invoke when **all four** gates hold:

1. **Bounded** — one module, one seam, or one narrow slice (e.g. `lca/plugins/transport/webserver/handlers/runs/execute/`); not a whole layer.
2. **Measurable benefit** — a concrete artefact changes: Protocol field count, dependency direction, dual-write window, shadow-module count, Journal event count, etc.
3. **1–3 PRs** — the change fits a small stack, each PR independently pushable and revertable.
4. **Has a delete-when condition** — every compatibility shim, parallel schema, or migration path that survives the PRs carries a concrete deletion clause per [AGENTS.md §1 兼容路径模板](../../../../AGENTS.md). No clause → the PR is not finished.

Reject the candidate (route back to `lca-find-simplifications` or document why it is out of scope) when any gate fails.

## Companion workflow (use as a chain)

Run in order. Each step's output is the next step's input; do not skip ahead.

1. **`lca-find-simplifications`** — first sweep; pick the one candidate that survives the four gates above.
2. **`lca-trim-cot-leakage`** — clean CoT residue in the candidate's prose/comments so the plan stands on current state (no "曾 / 退役 / 本批 PR-N 后"). Apply before planning, not after.
3. **`lca-code-review`** — review the candidate against the standing rules: five-layer single direction (C2 closed set, C4 Reducer, C5 capability decay, C7 control/observation split). The review's blockers become the plan's acceptance criteria.
4. **`lca-pre-push-checks`** — select the local evidence each PR must satisfy. Any new Agent Note (see [docs/notes/README.md §3](../../../../docs/notes/README.md)) must clear `lca-ops notes-check` and `lca-ops notes-audit`.

## Output shape

Write the plan as a single Markdown file. Recommended home: `docs/notes/proposed/<class>/YYYY-MM-DD-<topic>.md` (the plan may itself become a Note after the first PR lands), or as a free-floating plan under `history/` if the change is purely local with no cross-ADR boundary effect per [docs/notes/README.md §1](../../../../docs/notes/README.md).

Sections, in order:

- **候选范围** — module / seam / files; one paragraph, no implementation words.
- **当前症状** — file:line evidence; each symptom ties to a standing rule (AGENTS.md §1 / §3) or an existing Agent Note.
- **不变量** — what **must NOT** break: list each by name (five-layer direction, Reducer discipline, capability grant ⊆ parent, closed cognitive set, Journal catalog, Profile `provides → requires`).
- **1–3 PR 列表** — for each PR: title, files in scope, acceptance criteria, and a `Delete-when: <concrete condition>` line per shim, parallel schema, or migration path it leaves behind. The clause must be either "stable N days in production" or "rg returns zero non-doc consumers" — never a vague "不再需要时".
- **复盘触发** — after each PR lands: run [`lca-audit-notes`](../lca-audit-notes/SKILL.md) (or, when the candidate touched Agent Notes, run `scripts/audit_adr_health.py` and re-check inbound links). Update the plan with the actual outcome; collapse the plan into an implemented Note or archive it.

## Reject when

- Scope is broader than one seam (a whole layer, multiple Profile topologies, cross-cutting event-catalog edits) → route to `lca-find-simplifications` for re-scoping, or stop and write an ADR per [docs/notes/README.md §1](../../../../docs/notes/README.md) before any code.
- No measurable benefit (the change is "looks cleaner" with no public API, Reducer, seam, or capability surface reduction) → fold it into a single-line `TODO(fold-…)` per [lca-find-simplifications §inline TODO/FIXME notes](../lca-find-simplifications/SKILL.md) and stop.
- No delete-when condition can be written for a surviving compatibility shim → the candidate is not ready; either redesign until a deletion window exists, or document the deferral with a tracked ADR / issue and re-enter the workflow later.

## Reference paths

- [AGENTS.md §1 工程思维 / 总闸 4 问 / 卫生清单](../../../../AGENTS.md) — the four-gate source.
- [AGENTS.md §3 五层单向依赖 + C1–C7](../../../../AGENTS.md) — the invariants every plan's "不变量" section cites.
- [docs/notes/README.md](../../../../docs/notes/README.md) — `新决策` path; a plan may itself become `docs/notes/proposed/<class>/...md`.
- [docs/AGENTS.md 目录归属](../../../../docs/AGENTS.md) — where the plan file physically lives.
- [`lca-find-simplifications`](../lca-find-simplifications/SKILL.md) — companion for sweep; taxonomy of strong candidates.
- [`lca-trim-cot-leakage`](../lca-trim-cot-leakage/SKILL.md) — companion for prose hygiene.
- [`lca-code-review`](../lca-code-review/SKILL.md) — companion for standing-rule review.
- [`lca-pre-push-checks`](../lca-pre-push-checks/SKILL.md) — companion for selecting local evidence.
- [`lca-audit-notes`](../lca-audit-notes/SKILL.md) — post-PR retrospective trigger.

## What this skill explicitly does not own

- **Repository-wide sweep** — that is `lca-find-simplifications`; do not re-scan the repo from here.
- **Editing 老 ADR (`docs/adr/`)** — frozen; if the candidate conflicts with an ADR, route through the ADR workflow per [AGENTS.md §1 老 ADR 全部不动](../../../../AGENTS.md).
- **Picking new note `class`** — closed set per [docs/notes/README.md §2.2](../../../../docs/notes/README.md); this skill does not expand it.