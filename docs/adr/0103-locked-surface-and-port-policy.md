# ADR-0103: back-ui-821-other-keep — Locked Surface and Port Policy

## Status
Accepted (2026-08-30).

## Context
Branch `back-ui-821-other-keep` keeps the lobehub 8.21 frontend working
on a stable core. Since the merge-base `bae32d8c27ee2b59312303fbfa68d4738c2f316f`,
main has accumulated 816 commits of which 528 touch `lca/`, 100 touch
`gateway/`, 31 touch `deploy/lobehub/`, and 66 touch `docs/adr/`. The
branch tip is `5204fd56` (`fix(gateway): 恢复 LobeHub 前端 SSE 正常可用`),
a one-commit fix that makes lobe-chat's SSE consumer honour the run scope.

We want to ingest the architectural improvements from main without
breaking the lobehub UI contract. The current plan is a hybrid:

- Hard-lock the lobehub frontend and its deploy/patch surface.
- Soft-lock the gateway SSE / REST / OpenAI-shim layer; ports must
  preserve the wire shape.
- Default-port the contracts and harness work; investigate the rest
  per-cluster.

## Decision

### 1. Hard-lock
- `deploy/lobehub/` (entire tree, including `patches/`)
- `lobehub-ui/` (working tree, not in this repo; managed by `patch_lobehub.py`)

Any commit touching these paths must be rejected by
`scripts/check_locked_surface.py` (which parses this ADR's hard-lock
table).

### 2. Soft-lock
- `gateway/runs/api.py` — public REST/SSE shape consumed by lobe-chat
- `gateway/runs/openai_shim.py` — OpenAI-compatible wire shape
- `gateway/runs/execute.py` — finalize/closure logic can evolve, but
  `_emit_artifact_closure_if_needed` StepTextDelta must carry a
  non-empty `RunScope`. The `5204fd56` fix is contractually required.
- `gateway/app.py`, `gateway/runs/loop_drivers.py` — adapter layer;
  allowed provided the contracts above are preserved.

Any port commit that touches a soft-lock path must include a
"wire-shape preserved by X" note in the commit body; the guard emits
a warning otherwise.

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
- ADR-0061 — manifest resolve/boot, harness profile semantics
- ADR-0037 — journal-as-truth, journal catalog reference
- ADR-0099, ADR-0100, ADR-0101, ADR-0102 — examples of architecture-decision ADRs this policy covers
- ADR-0056 — `lca/harness/plugin_api.py` reference
- `docs/superpowers/specs/2026-08-30-back-ui-821-port-policy-design.md` — design spec
- `docs/superpowers/plans/2026-08-30-back-ui-821-port-policy-impl.md` — implementation plan