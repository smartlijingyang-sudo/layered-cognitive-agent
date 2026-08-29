# back-ui-821-other-keep — Locked Surface and Port Policy

**Date:** 2026-08-30
**Branch:** `back-ui-821-other-keep`
**HEAD:** `5204fd56` — `fix(gateway): 恢复 LobeHub 前端 SSE 正常可用`
**Merge-base with main:** `bae32d8c` (`test(live-sse): cover StepTextDelta text_channel filter on iter_live_sse`)
**Origin/main tip:** `0dc34a1e` — `feat(tools): flatten tool observation payload + per-tool RenderContract tuples (ADR-0102)`
**Status:** Design (draft, awaiting user review before implementation plan)

## Problem

`back-ui-821-other-keep` keeps the lobehub 8.21 frontend working on a stable core. Since the merge-base `bae32d8c`, main has accumulated **816 commits** of which:

| Area | Commits on main not in branch |
|---|---|
| `deploy/lobehub/` | 31 |
| `gateway/` | 100 |
| `lca/` | 528 |
| `docs/adr/` | 66 |
| total | 816 |

The intent is to ingest the architectural improvements from main without breaking the lobehub UI contract. The 1-commit HEAD on the branch (`5204fd56`) is itself a backend fix whose purpose is to keep lobe-chat's SSE consumer working — the lobehub frontend is the lock surface, but the backend pipe that feeds it is in the soft-lock zone.

## Section 1 — Lock Surface (the contract)

### Hard-locked (cannot touch)
- `deploy/lobehub/` — entire tree, including `patches/` (literal lobe-chat source patches + deploy + engine)
- `lobehub-ui/` — working tree, not in this repo; managed by `patch_lobehub.py`

### Soft-locked (allowed to modify, with constraints)
- `gateway/runs/api.py` — must not change the public REST/SSE shape consumed by lobe-chat
- `gateway/runs/openai_shim.py` — must not change the OpenAI-compatible wire shape
- `gateway/runs/execute.py` — finalize/closure logic can evolve, but `_emit_artifact_closure_if_needed` must emit StepTextDelta with a non-empty `RunScope` (the `5204fd56` fix is contractually required)
- `gateway/app.py`, `gateway/runs/loop_drivers.py` — adapter layer; allowed as long as contracts above are preserved

### Fully unlocked
- `lca/` (entire framework)
- `docs/adr/`, `docs/specs/`, `docs/design/`
- `tests/` (excluding lobehub-specific UI tests)
- `scripts/`, `profiles/`, `bundles/`

## Section 2 — Port Policy (value criterion)

### Lane A — default port
Cluster delta touches:
- `lca/contracts/*`
- `lca/harness/{profile,boot,session,agent,middleware,plugin_api,skills,workflow}`
- `docs/adr/*`, `docs/specs/*`, `docs/design/*`
- `lca/contracts/models/observability/*`
- `lca/contracts/capabilities.py`
- `lca/harness/plugin_api.py`
- Tests for the above

### Lane B — investigate (per-cluster judgment)
Cluster delta touches:
- `lca/layer1_cognitive/*`, `lca/layer2_runtime/*`, `lca/layer3_agent/*`, `lca/layer4_app/*`
- `gateway/runs/*` (gated by soft-lock)
- `profiles/*`, `bundles/*` (only if our profile uses it)
- `scripts/*`

### Lane C — skip by default
- `chore(...)`, `style(...)`, cosmetic reformat
- `docs(...)` except ADR / spec / design
- `fix(deploy/lobehub/...)`, `fix(lobehub-patches/...)` — locked
- `feat(lobehub-patches/...)` — locked (RenderContract/registry/main-renderer work)
- DSH-only changes (DSH is its own driver; not on this branch)
- YAGNI cleanup unless the alias exists on this branch

### Per-port evidence (in port-plan)
Every "Port" decision must carry:
1. **Why now**: which downstream commit on main depends on this landing first
2. **Risk to lock**: confirms it does not change the wire shape
3. **Test plan**: which `tests/test_*.py` covers it; if none, "porting without coverage — recommend regression test in same commit"

### Conflict-resolution policy
- If two clusters overlap, port in DAG order (depends-on-first)
- If a conflict is unreconcilable on this branch's current state, split the port and add a "future integration" note in ADR-0103

## Section 3 — Cluster Boundaries (47 clusters)

### A. Contracts (Lane A)
1. **C1 atoms** — enums, IDs, semantic keys, telemetry attrs
2. **C2 mechanisms** — EventBus / Hook / Registry / Seam
3. **C3 models** — core / observability / team dataclasses
4. **C4 protocols** — infra / cognition / embodiment / runtime / orchestration
5. **C5 harness contracts** — plugin / middleware / projection / session / agent
6. **C6 capabilities** — capability key registry

### B. Docs (Lane A)
7. **C7 ADR cluster** — `docs/adr/0100+` additions
8. **C8 specs + design** — `docs/specs/*`, `docs/design/*`

### C. Harness (Lane A)
9. **C9 profile + boot + resolve** (ADR-0061)
10. **C10 session + agent lifecycle**
11. **C11 middleware**
12. **C12 plugin_api** (group contribution, capabilities)
13. **C13 skills + workflow**
14. **C14 diagnostics** (boot_report)

### D. Layer 0 infra (Lane B)
15. **C15 llm** — resolvers, providers
16. **C16 tools** — tool registry; render contract (wire-shape, soft-lock)
17. **C17 transport**
18. **C18 sandbox**
19. **C19 observability** — hub / bound / kill-alias
20. **C20 dsh bridge** (DSH-only; investigate)
21. **C21 plane** — event/state plane

### E. Layer 1 cognitive (Lane B)
22. **C22 brain / Reasoner / Critic / Synthesizer / decision_gates**
23. **C23 body / ActionRegistry / SafeExecutor / SimpleBody**
24. **C24 perceive_hub / perceive_sink (PR3a)**
25. **C25 sensors** (clock, journal, skill, workspace)
26. **C26 blackboard / event_bus / hook_registry**
27. **C27 memory / member_status**

### F. Layer 2 runtime (Lane B)
28. **C28 CognitiveRuntime / StopRule / OutcomePolicy / Phase Middleware**
29. **C29 guards** (RepeatToolCall, ToolLoopBreaker)

### G. Layer 3 agent (Lane B)
30. **C30 CognitiveAgent / TeamHandle / OrchestrationStrategies**

### H. Layer 4 app (Lane B)
31. **C31 composer / runtime_factory / team_wiring / harness_bridge / spawn**

### I. Plugins (Lane B)
32. **C32 seam_definitions**
33. **C33 providers** (per-seam factories)
34. **C34 brain / reasoner / synthesizer / loop_cognitive / team_lead**
35. **C35 dsh plugins**

### J. Gateway (Lane C; soft-lock)
36. **C36 gateway/runs/api.py** — soft-lock; wire-shape must not change
37. **C37 gateway/runs/execute.py** — soft-lock; closure fix must remain
38. **C38 gateway/runs/openai_shim.py** — soft-lock; OpenAI-shape must not change
39. **C39 gateway/runs/loop_drivers.py** — cognitive + dsh registration
40. **C40 gateway/app.py**

### K. Profiles / Bundles / Scripts (Lane B)
41. **C41 profiles**
42. **C42 bundles**
43. **C43 scripts** (lca-ops, check_*.py)

### L. Tests
44. **C44 tests for contracts/harness/docs** — Lane A
45. **C45 tests for layer0–4** — Lane B
46. **C46 tests for plugins** — Lane B
47. **C47 tests for gateway** — Lane C (gated by soft-lock)

## Section 4 — End-state Card Schema

### Per-cluster card (in `docs/port/main-port-plan.md`)

```markdown
### C{id}: {cluster name}

- **Lane**: {A: port | B: investigate | C: skip}
- **Path(s)**: {comma-separated paths}
- **Main commits touching this cluster**: {n} (chronological range bae32d8c..origin/main)
- **Branch HEAD**: {commit hash + subject} — what the branch currently has
- **Main tip**: {commit hash + subject} — what main has now
- **End-state delta**: {3-5 line summary of the functional/architectural change}
- **Key symbols touched**: {file:symbol list, capped at 5}
- **Lock impact**: {none | hard:path | soft:path — must preserve wire-shape X}
- **Default recommendation**: {port as-is | port with X caveat | skip with Y reason}
- **Test plan**: {which tests cover it; or "no coverage — recommend regression test"}
- **DAG deps**: {cluster IDs that must land first}
- **Mark**: [ ] port  [ ] skip  [ ] hold  [ ] investigate
```

### Per-commit classification (in `docs/port/main-classification.md`)

Lightweight — 816 rows in a table:

| sha | subject | cluster | lane | notes |
|-----|---------|---------|------|-------|
| 0dc34a1e | feat(tools): flatten tool observation ... | C16 (tools) | A | render contract tuples |
| 90b00f7d | fix(lobehub-patches): preserve streaming ... | locked | C | touches deploy/lobehub/ |
| ... | ... | ... | ... | ... |

### Aggregate stats (top of port-plan.md)

```markdown
## Summary

- Total main commits since merge-base: 816
- Hard-locked (skipped): 31
- Soft-locked (gated): 100
- Fully unlocked: 685
- Cluster count: 47
- Lane A (default port): 12
- Lane B (investigate): 28
- Lane C (skip): 7
- Expected port commits on this branch: ~15-25 (one per cluster marked)
```

### Workflow
1. Run classification pass → write `main-classification.md` (816 rows, automated)
2. For each cluster, compute end-state delta → write `main-port-plan.md` (47 cards)
3. User marks each card; ADR-0103 finalizes
4. Execute port per marked card (one commit per cluster); `check_locked_surface.py` enforces hard-lock; soft-lock diff noted in commit body

## Section 5 — Execution & Verification

### Apply mode (per user feedback: "不是傻傻的一个个回放")
- **Mode A (Lane A)**: end-state delta — `git diff bae32d8c..origin/main -- <cluster paths>`, apply as one commit
- **Mode B (Lane B)**: end-state delta + cluster-specific review if conflicts
- **Mode C (Lane C)**: not applied unless user overrides

In all modes, the commit on this branch is **one commit per cluster**, with attribution to the source commit(s) in the body.

### Per-port-commit lifecycle

For each cluster marked `[ ] port`:

1. **Stage** the cluster's end-state delta onto a working branch off `back-ui-821-other-keep`
2. **Run gates** in order:
   - `uv run ruff check --fix <paths>` + `uv run ruff format <paths>`
   - `uv run lint-imports` (layer-boundary check; non-negotiable)
   - `uv run pytest --no-cov <matching test files>` (per AGENTS.md §3.2)
   - `uv run python scripts/check_locked_surface.py` (new — hard-lock enforcement)
3. **Commit** with a structured message:
   ```
   port(cluster-{id}): {cluster name}
   Source: N commits from origin/main ({first_sha}..{last_sha}).
   Lane: {A|B|C}.
   Lock impact: {none|soft:api.py — wire-shape preserved by X}.
   Test plan: {test paths or "no coverage"}.
   ```
4. **Advance** to next cluster in DAG order

### New guard script

`scripts/check_locked_surface.py`:
- Reads the hard-lock list from `docs/adr/0103-locked-surface-and-port-policy.md` (parses the markdown table) or a small `locked-surface.yaml`
- `git diff HEAD` — fails if any path in the hard-lock list shows a non-whitespace change
- Soft-lock paths: emit a warning + require commit body to mention `wire-shape preserved` or equivalent phrase

### DAG & order

1. Contracts (C1–C6)
2. ADR + spec + design (C7–C8)
3. Harness (C9–C14)
4. Layer 0 (C15–C21), including soft-locked `tools` (C16) with care
5. Layer 1 (C22–C27)
6. Layer 2 (C28–C29)
7. Layer 3 (C30)
8. Layer 4 (C31)
9. Plugins (C32–C35)
10. Profiles/Bundles/Scripts (C41–C43)
11. Tests for the above (C44–C47)
12. Gateway last (C36–C40) — after everything else is stable, then layer gateway adaptors on top with extra verification

### Full-verification trigger

After all marked clusters port:

```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
uv run python scripts/check_locked_surface.py
```

## Section 6 — ADR-0103 Structure

The companion ADR (to be written after spec approval):

```markdown
# ADR-0103: back-ui-821-other-keep — Locked Surface and Port Policy

## Status
Accepted (2026-08-30).

## Context
Branch `back-ui-821-other-keep` keeps the lobehub 8.21 frontend working
on a stable core. Since the merge-base `bae32d8c`, main has accumulated
816 commits of which 528 touch `lca/`, 100 touch `gateway/`, 31 touch
`deploy/lobehub/`, and 66 touch `docs/adr/`. We want to ingest the
architectural improvements from main without breaking the lobehub UI
contract.

## Decision

### 1. Hard-lock
- `deploy/lobehub/` (entire tree, including `patches/`)
- `lobehub-ui/` (working tree, not in repo; managed by `patch_lobehub.py`)
- Any commit touching these paths must be rejected by `scripts/check_locked_surface.py`.

### 2. Soft-lock
- `gateway/runs/api.py` — public REST/SSE shape consumed by lobe-chat
- `gateway/runs/openai_shim.py` — OpenAI-compatible wire shape
- `gateway/runs/execute.py` — finalize/closure logic can evolve, but
  `_emit_artifact_closure_if_needed` StepTextDelta must carry a
  non-empty `RunScope`. The `5204fd56` fix is contractually required.
- `gateway/app.py`, `gateway/runs/loop_drivers.py` — adapter layer;
  allowed provided the contracts above are preserved.

Any port commit that touches a soft-lock path must include a
"wire-shape preserved by X" note in the commit body.

### 3. Port policy
- Default-lane (A) clusters: `lca/contracts/*`, `lca/harness/*`,
  `docs/adr/*`, `docs/specs/*`, `docs/design/*`, tests matching those.
- Investigate-lane (B) clusters: `lca/layer{0,1,2,3,4}/*`, `lca/plugins/*`,
  `gateway/runs/*` (gated by soft-lock), `profiles/*`, `bundles/*`,
  `scripts/*`.
- Skip-lane (C) clusters: chore/cleanup/format, fix(lobehub*),
  feat(lobehub-patches/*), DSH-only changes, YAGNI cleanup unless the
  alias exists on this branch.
- One commit per cluster on this branch; source commit(s) attributed in
  the body.
- DAG order: contracts → docs → harness → layer0 → layer1 → layer2 →
  layer3 → layer4 → plugins → profiles/bundles/scripts → tests →
  gateway.

### 4. Out of scope
- Wire-format rewrites (those are an ADR-0104+ conversation).
- Unlocking the hard-lock surface (would require a new ADR).

## Consequences

- `scripts/check_locked_surface.py` is added and wired into pre-commit.
- The branch's CI runs the same gates as main + the lock check.
- Every port to this branch must declare in its commit body:
  (a) cluster ID, (b) lock surface (if any) it touches, (c) how it
  preserves compatibility.
- If a port requires touching the soft-lock surface in a way that
  changes wire shape, that port is rejected; the workarounds (e.g.,
  adapter layer, dual-emit) become the new soft-lock contract.

## References

- `docs/port/main-classification.md` — commit-level classification of the 816 commits
- `docs/port/main-port-plan.md` — 47 cluster cards with end-state deltas and per-cluster user marks
- AGENTS.md §3.2 verification rules
- ADR-0061 (manifest resolve/boot) — harness profile semantics
- ADR-0037 (journal canonical) — journal catalog reference
- ADR-0099, ADR-0100, ADR-0101, ADR-0102 — examples of architecture-decision ADRs this policy covers
- ADR-0056 (plugin group contribution) — `lca/harness/plugin_api.py` reference
```

## Final-deliverable checklist

- [ ] `docs/adr/0103-locked-surface-and-port-policy.md` — the ADR
- [ ] `docs/port/main-classification.md` — 816-row classification
- [ ] `docs/port/main-port-plan.md` — 47 cluster cards
- [ ] `scripts/check_locked_surface.py` — guard script
- [ ] (optional) `docs/port/main-port-apply.log.md` — execution log as we work through marked clusters

## Self-review

After writing this spec, before handing to the user:

1. **Placeholder scan**: no TBD/TODO/incomplete sections
2. **Internal consistency**: lock surface ↔ port policy ↔ cluster boundaries ↔ execution all agree
3. **Scope check**: focused on port policy + locked surface; not broader refactor
4. **Ambiguity check**: each Lane A/B/C has explicit inclusion criteria; cluster count fixed at 47