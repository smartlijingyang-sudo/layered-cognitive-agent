# DESLOP-100 Wave 1 — Assessment

Branch: `raphy/deslop-100` (worktree `/home/lichao/.lca-worktrees/raphy-deslop-100`)
Date: 2026-10-10
Mode: ASSESS ONLY (no code changes outside `raphy/`)

## Scope

This wave combines the two round mandates:
1. **deslop** — remove AI-generated slop: change-narration residue in current-state docs/comments, filler words, unnecessary comments inconsistent with local style.
2. **real architecture deepening** per `skills/improve-codebase-architecture` (deep modules, locality, deletion test, seams).

Stories continue from RA-104 (`passes: false`, `branchName: raphy/deslop-100`). Prior RA-001..RA-103 are all `passes=true` or dropped.

## 禁区 compliance

Respected: `lca/cognition/memory/` (frozen), `lca/plugins/transport/webserver/` (lca-1000 territory), `gate_chain_strategy.py` (hands-off), `preamble.py` (user iterating), ralph Round 2 areas. The comment-deslop story explicitly excludes the frozen dirs.

## Hot spots (git log)

The last ~40 commits are dominated by raphy rounds (RA-097..RA-103), iter merges, and ADR/doc commits — the codebase's own raphy loop is the recent "hot spot". The production files touched recently outside raphy are `lca/framework/graph/` (port_reader, interpreter), `lca/agent/`, `lca/runtime/loop/`. The deslop lens is new for this round: `scripts/verify_doc_slop.py` exists and is read-only runnable.

## Runtime verification (mandatory, executed)

Probe (`/tmp/raphy_probe_deslop100.py`, MockLLMAdapter + a scripted tool-call adapter, `LLM_API_KEY=dummy`, `PYTHONPATH=<worktree>`):

| Scenario | Result |
|---|---|
| (a) basic run | **completed** |
| (b) run with a tool call (custom marker tool) | **completed**, marker file written → tool actually executed |
| (c) two sequential runs on one agent | **completed** / **completed** |

No crash, hang, or silent failure. The earlier inline `Agent(...)` attempt failed only because the raphy-assess prompt's API snippet is outdated (`Agent` now requires `role/goal/backstory`); with the current public API all three minimum scenarios pass. No new P0/P1. RA-023's non-convergence path was not re-run this wave (verified in prior rounds; basic scenarios pass).

## Friction walk (5 questions per area)

### Area A — `lca/application/runtime/` (composition root)

Read end-to-end: `plan_resolution.py`, `default_facade.py`, `runtime_coordinator.py`, `session_catalog_map.py`, `harness/runtime/proposal_activator.py`.

- **Q1 shallow-module sprawl?** Low. Each module is single-purpose with a clear seam.
- **Q2 shallow modules (deletion test)?** None obviously shallow.
- **Q3 pure functions extracted for testability, bugs in call sites?** `plan_resolution.py` cache gating (`use_cache = bool(assistant_id and manifest_digest and plan_overlay is not None)`) is subtle but has no observed bug; the cache key ignores `plan_overlay`, which is safe only because the composition root always derives overlay from the same `assistant_id`. No story.
- **Q4 leaky abstractions?** **Yes — the main finding.** `pyproject.toml` `[tool.lca.package_contracts."lca.application"]` declares `forbidden_dependencies = ["lca.harness", "lca.plugins", "gateway"]`, yet `default_facade.py` imports `lca.harness.runtime.activation_ref.compute_activation_ref` and `plan_resolution.py` imports `lca.harness.plan` + `lca.harness.profile.resolve.resolve` + `lca.harness.profile.validate.errors`. `scripts/check_package_contracts.py` only checks README mentions, not actual imports → the declared contract is silently violated. `default_facade.py`'s docstring admits the "soft-layering deviation" and tracks promoting `compute_activation_ref` to contracts as a P1 backlog. → **RA-107**.
- **Q5 untested / hard to test through interface?** The application→harness boundary has no enforcement; nothing catches a new harness import in `lca/application/`.

### Area B — `lca/infrastructure/observability/adapters/` + `stream/`

Read end-to-end: `adapters.py`, `policy.py`, `view.py`, `stream_event_manager.py`, `llm_stream_activity.py`, `response_text_stream.py`, `graph_timeline.py`, `loop/emit/spine/ep.py`.

- **Q1 shallow-module sprawl?** Low; modules are focused.
- **Q2 shallow modules?** None strong.
- **Q3 pure functions for testability?** `_stream_observability_kwargs`, `_model_label` are pure and fine, but see Q4.
- **Q4 leaky abstractions?** **Yes.** `_model_label` does `getattr(inner, "_model", None)` — a private field of `openai_compat` — before falling back to the declared `name`. The `LLMAdapter` protocol declares `name` (adapter display name) but **no model identifier**; the `model=` value in `llm.call.start/end` telemetry is therefore not contractual. A future adapter that stores its model differently silently yields fallback/empty labels. → **RA-106**.
- **Q5 untested / hard to test?** `_model_label` is only indirectly tested through telemetry tests; a fake adapter with no `_model` is not covered.

### Area C — `lca/infrastructure/cli/commands/journal*` + `observation/`

Read end-to-end: `journal/journal.py`, `journal/session.py`, `journal/step.py`, `journal_extra/journal_steps.py`, `observation/trace_show.py`, `observation/run_replay.py`.

- **Q1 shallow-module sprawl?** **Yes.** Two step-viewer commands: `journal step --step N` (single-step human render of `journal.json`) and `journal steps --step N` (single-step markdown via `StepNarrativeWriter`), both under the `journal` group, both reading the same `journal.json`. Duplicated reading + rendering of the same document. → **RA-108**.
- **Q2 shallow modules?** The commands are thin CLI shells; the overlap is the friction.
- **Q3 pure functions for testability?** `_render_event`/`_format_step_human` etc. are fine.
- **Q4 leaky abstractions?** Minor: `session.py`/`step.py` each re-derive `_spine_path` with function-level imports of `spine_filename_for_run`; folded into RA-108's shared-seam goal.
- **Q5 untested?** CLI commands are mostly thin; `journal step` has tests. The overlap itself is unpinned.

### Area D — `lca/framework/graph/`

Read: `observation.py`, `recorder.py`, plus context from RA-101/102 (port_reader, interpreter).

- **Q1 shallow-module sprawl?** Low; `_PHASE_ALIAS_OF` is well-converged.
- **Q2 shallow modules?** None.
- **Q3 pure functions for testability?** `phase_of()` is a pure convention mapping but **has zero test references** (`grep phase_of|LCA_TOP_PHASES|_PHASE_ALIAS_OF tests/` → empty). Any bundle node whose first segment is neither a top phase nor an alias silently renders `phase=""` in NodeEnter/NodeExit facts. → **RA-109**.
- **Q4 leaky abstractions?** None observed.
- **Q5 untested?** Yes — the phase vocabulary is untested against real `bundles/**/*.yaml`.

## Duplication scan (secondary)

- **RA-108** (`journal step` vs `journal steps`) is the wave's one duplication-class story.
- Minor `_spine_path` re-derivation across CLI commands is folded into RA-108.
- `AutoReviewWrappedTool.effect_kind` getattr probe: matches the recorded pattern "类型保证 vs 防御式读取...见到可直接按诚实化修，不必开 story" (progress.txt) — **not opened** as a standalone story.

## Deslop classification (`scripts/verify_doc_slop.py` — 123 hits, probe not definition)

| Category | Hits | Verdict |
|---|---|---|
| `docs/plans/*` (dated planning docs) | ~90 | **keep** — time capsules; extend the linter to exclude `docs/plans/` like `docs/design/2026-*` |
| `docs/port/main-classification.md` | 3 | **keep** — commit-hash / change-log table |
| `docs/specs/glossary.md` | 10 | **keep** — glossary entries (explicitly not to be deleted) |
| `docs/architecture/optimization-iterations.md` | 3 | **keep** — iteration log |
| `docs/specs/0194-0195-implementation-plan.md`, `docs/specs/2026-09-07-lca-p1-agent-gateway-bridge.md`, `docs/specs/2026-09-10-nested-bundle-graph-spec.md`, `docs/specs/adr-0254-scenario-testing-specification.md` | many | **keep** — dated specs / implementation plans |
| `docs/specs/0199-delete-when-inventory.md` | 1 | **keep** — legitimate checklist instruction ("now-obsolete exemption") |
| `docs/specs/architecture.md` line 185 | 1 | **keep** — resolvable commit-hash reference (`cc17d8f81`); per instructions not deleted |
| `docs/observability/architecture-overview.md` (lines 3/49/53/54) | 4 | **fix** — rewrite "不再走 / 已退役" as present-tense do-not-use tables |
| `docs/observability/platform-readme.md` (lines 23/24) | 2 | **fix** — rewrite "遗留 / 退役 →" as present-tense replacement table |
| `docs/guides/phase-graph-and-act-tool-path.md` line 28 | 1 | **fix** — rewrite "旧名...已退役" as current-state pointer |

Fix-worthy current-state prose is small and bounded → **RA-104**.

## Candidate table

| # | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|---|
| RA-104 | `docs/observability/*`, `docs/guides/phase-graph-and-act-tool-path.md`, `scripts/verify_doc_slop.py` | 123 slop hits; linter scans time-capsule plans; current-state docs carry change narration | classify keep/fix, exclude `docs/plans/`, rewrite fix-worthy prose in present tense | current-state docs become honest without history archaeology; linter output becomes meaningful | **Strong** |
| RA-105 | ~21 modules in `lca/` with change-narration comments | raphy-era docstrings/comments narrate "used to / previously / this PR" | rewrite to present-tense; keep load-bearing why + invariant RA refs | reading a module states current truth; future edits don't need history | **Strong** |
| RA-106 | `observability/adapters/adapters.py`, `contracts/protocols/runtime/infra/infra.py`, `llm_adapter/openai_compat` | `_model_label` probes private `adapter._model`; model id not on protocol | declare `model_name` accessor on LLMAdapter; remove getattr | model identity becomes contractual; new adapters can't silently break telemetry | **Worth exploring** |
| RA-107 | `pyproject.toml`, `application/runtime/default_facade.py`, `application/runtime/plan_resolution.py`, `scripts/check_package_contracts.py` | declared `forbidden_dependencies` violated by 2 files; unenforced | spike: move small seams to contracts / update contract with evidence; add enforcement | layer boundary stops lying; harness refactors can't silently break composition root | **Strong** |
| RA-108 | `cli/commands/journal/step.py`, `journal_extra/journal_steps.py` | two overlapping step-viewer commands, duplicated reading/rendering | spike: converge or cross-reference with one shared seam | one clear step-viewing surface; single journal-read seam | **Worth exploring** |
| RA-109 | `framework/graph/observation.py`, `tests/framework/graph/`, `bundles/**/*.yaml` | `phase_of` vocabulary untested; unrecognized prefixes silently yield `phase=""` | pin alias vocabulary against real bundle YAMLs with documented keep-list | observability phase facts verified against real plans; alias table earns its existence | **Worth exploring** |

## Top recommendation

**RA-107** is the top architecture story: a declared package contract (`lca.application` must not depend on `lca.harness`) is violated in two files, nothing enforces it, and the violating module's own docstring documents the deviation plus the backlog. That is a "declared interface lying" shape — the same class as RA-031/RA-051/RA-059. It is the most load-bearing: it sits on the run-creation path (facade + plan resolution) and its fix (moving the small pure seam functions to contracts or correcting the contract with evidence) unlocks honest enforcement for every future application-layer change.

For the deslop mandate, **RA-104** is the top prose story: it makes `verify_doc_slop.py` meaningful (exclude time-capsule plans) and fixes the small set of genuinely current-state change-narration lines.

## Self-grilling (per candidate)

### RA-104 (docs deslop)
- **Constraints**: no glossary entry or resolvable commit-hash reference may be deleted; historical docs (`docs/plans`, `docs/adr`, `docs/notes`, `docs/debug`, `docs/port`, dated specs, `docs/design/2026-*`) stay untouched; do-not-use tables keep their informational value.
- **Dependencies**: `verify_doc_slop.py` is read-only lint; extending its exclusions changes only the scan scope, not any runtime behavior.
- **Deepened module**: the linter's exclusion set + the current-state docs become the honest "how it is" surface.
- **Test survival**: no tests pin doc prose; the script itself has no tests (add none — it's a lint script). Verification is re-running the script and `git diff --check`.
- **Deletion test**: the fix concentrates — a reader no longer needs to reconstruct history to understand the present.

### RA-105 (comment deslop)
- **Constraints**: no behavior change; `lca/cognition/memory/`, `lca/plugins/transport/webserver/`, `gate_chain_strategy.py` excluded; load-bearing why-comments and invariant-carrying RA refs kept.
- **Dependencies**: the comments are in modules with existing tests; prose-only edits cannot break them (verify with ruff + targeted tests).
- **Deepened module**: each touched docstring/comment becomes a current-state statement.
- **Test survival**: existing tests pin behavior, not prose; a grep-based acceptance documents the keep-list.
- **Deletion test**: rewording is not deletion — the *concept* stays, the *narrative* goes.

### RA-106 (model identity seam)
- **Constraints**: `LLMAdapter` protocol change is additive (new declared member); production adapters already have the value (`_model`); telemetry `model=` values unchanged.
- **Dependencies**: `TelemetryLLMAdapter` is the only `_model_label` caller; openai_compat/mock/anthropic adapters implement the new member.
- **Deepened module**: `LLMAdapter` gains a shallow-but-real `model_name` member; `_model_label` becomes a thin adapter.
- **Test survival**: existing telemetry tests pin `model=`; add a fake-adapter test (no `_model`) proving the declared accessor is used.
- **Deletion test**: concentrates — model identity lives in the contract, not in a getattr probe.

### RA-107 (application→harness)
- **Constraints**: ADR-0199 P1-06 says activation_ref hashing is owned by harness; moving `compute_activation_ref` to contracts changes ownership and may need an ADR note (the code's own backlog already proposes this). `resolve_profile`/`compile_plan` are large harness functions — likely stay behind an injected protocol.
- **Dependencies**: `PlanResolutionService`/`DefaultRuntimeFacade` are consumed by CLI/HTTP/tests; refs must remain byte-identical.
- **Deepened module**: the seam between composition root and harness becomes either contracts-owned (small pure functions) or an injected resolver; enforcement makes the boundary real.
- **Test survival**: `tests/application/runtime/` + package-contract check; add a pin that `lca/application/` has no harness imports.
- **Deletion test**: concentrates — the declared contract stops being a lie.

### RA-108 (journal step CLI)
- **Constraints**: CLI is user-facing; `journal step` and `journal steps` are both referenced in docs; choose merge vs cross-reference with evidence.
- **Dependencies**: both commands read `journal.json` via different paths; docs/`lca-ops` help reference them.
- **Deepened module**: one step-viewing command + one journal-read seam (or an explicit shared loader).
- **Test survival**: existing journal CLI tests; add a pin for the chosen surface.
- **Deletion test**: if merged, the duplicate rendering is deleted and complexity concentrates in one command.

### RA-109 (phase alias vocabulary)
- **Constraints**: `phase_of` semantics unchanged; legitimate unknowns recorded in a test keep-list, not forced into the alias table.
- **Dependencies**: `phase_of` is consumed by observers/NodeEnter/NodeExit facts; the test only reads bundle YAMLs.
- **Deepened module**: `phase_of` + `_PHASE_ALIAS_OF` gain a test surface (the interface is the test surface).
- **Test survival**: existing graph observation tests; new corpus test walks all bundle node ids.
- **Deletion test**: the alias table earns its existence by being pinned against real plans.

## Learnings for future iterations

- The runtime probe works in this worktree (`PYTHONPATH=<worktree>` + `python3 /tmp/...py`); the raphy-assess prompt's `Agent(tools=[], llm=...)` snippet is outdated — the public `Agent` requires `role`/`goal`/`backstory` and `ensure_default_ctx` is async.
- `check_package_contracts.py` only checks README mentions, not imports — "declared forbidden dependency" stories must verify actual imports and the checker's capabilities before asserting enforcement.
- `verify_doc_slop.py` hits are mostly time-capsule planning docs; a meaningful deslop story should first fix the linter's scope, then the small current-state residue.