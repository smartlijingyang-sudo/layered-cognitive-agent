---
name: lca-find-simplifications
description: Use when reviewing the LCA repo for non-obvious simplification candidates — remove redundant protocols/dataclasses, fold shadow modules, drop thin compatibility shims, audit supersedable seams, fold worthwhile simplification ideas from another branch, or write inline TODO/FIXME notes. Especially for: dead, duplicated, speculative, over-built, or hand-rolled-where-a-builtin-exists surfaces. Trigger phrases: "简化 LCA", "找死代码", "audit simplifications", "fold compatibility shim".
---

# Finding LCA Simplifications

This skill turns a broad "find things to simplify" request into evidence-backed work that removes or collapses existing LCA surface area. It is guidance, not a checklist: follow the code, keep judgement active, and prefer a few well-proven candidates over a pile of thin guesses. The `AGENTS.md` §1 "写代码顺手清理垃圾" rule is the standing directive this skill applies — it owns the *what to flag* taxonomy, this skill owns the *how to investigate* workflow.

## Start with repo context

- Read [AGENTS.md](../../../../AGENTS.md) §1 "工程思维" and §3 "架构不变量" — five-layer dependency direction, C1–C7 invariants, and the "Plugin Manifest → Seam → Provider → Registry → Plugin → Profile / Bundle" extension path are the rules every candidate must respect.
- Skim [docs/specs/harness-spine-spec.md](../../docs/specs/harness-spine-spec.md), the [cognitive primitive constitution v3](../../docs/design/2026-08-19-cognitive-primitive-constitution-v3.md), and relevant [ADR](../../docs/adr/) entries before judging anything under `lca/`. Simplifications that fight the closed cognitive set (`perceive → think → gate → act → reflect → remember → stop`), the dual-plane split (cognitive / world), or the Reducer-only state mutation rule need extra evidence.
- Use the [Agent Note tree](../../docs/notes/README.md) to understand intentional architecture. Recent examples worth reading for pattern: notes under `docs/notes/implemented/{contract,seam,primitive,profile,runbook,postmortem}/`. 老 ADR (`docs/adr/`) is the historical record — never modify it as part of a simplification, even when an ADR is itself the obstacle.
- The "thin compatibility shim" pattern is the most common LCA simplification: a Protocol / dataclass / enum-value added "for migration", guarded by `COMPAT(delete-when: ...)` block per AGENTS.md §1, and the delete-condition never lands. Flag every shim whose delete-condition window has elapsed; remove only after `rg` proves zero consumers.

## What counts as a strong candidate

A strong simplification removes, folds, or demotes something real and has clear evidence that the current design costs more than it buys. Per AGENTS.md §1, candidates should not be "obvious typo / knip run / this looks complex":

- A public Protocol method, enum value, ID type, wire field, registry key, helper module, durable Journal event, or test artifact has no production consumer (run `rg` against `lca/` excluding `tests/`).
- Two dataclasses mirror one fact, especially across wire schemas and transient in-memory models, or across the durable `Journal` event set and a transient UI/SSE projection.
- A Protocol has methods every implementation must support but no caller invokes; Protocol signature can be narrowed and registry entries dropped.
- A separate module exists only for test/demo/support code and adds import-graph overhead or circular-import risk (see [scripts/check_package_size.py](../../scripts/check_package_size.py), [scripts/check_package_contracts.py](../../scripts/check_package_contracts.py)).
- A thin compatibility shim has outlived its `delete-when` window — including: enum alias, Protocol method stub, `try/except Exception: pass` swallower, `# type: ignore[no-untyped-def]`, parallel schema, `writable.matrix` double-write path.
- Hand-rolled code reimplements what `vendor/cordis`, `vendor/cosmokit`, `vendor/schemastery`, or the Python stdlib already provides at the engine floor LCA targets — and the swap deletes the implementation plus its dedicated tests.
- An invariant, rollback path, expected-output set, or special-case test exists only to protect an unused API surface.
- The simplified behavior may differ slightly, but the new behavior is still reasonable, easier to explain, and preserves C1–C7.

### Thin compatibility shims — the LCA-specific category

LCA's `AGENTS.md` §1 templates `COMPAT(delete-when: <条件>, tracking: ADR-0xxx|issue)` for every shim. A shim is a candidate for deletion when:

1. Its delete-condition window has elapsed (e.g. "writable.matrix 单写稳定 14 天" — count days since the PR landed).
2. `rg '<symbol>'` across `lca/` excluding `tests/` returns zero non-doc references.
4. The shim's protective purpose has been replaced by a different control (a Reducer single-write path, a Protocol narrowing, an enum close-set entry).
5. Removing it does not require a wire-format version bump (Journal catalog, Profile schema version, wire schema minor/major) — if it does, that bump is the deletion plan, not a blocker.

Thin shims fail the bar when:

- They back a documented schema migration with active consumers in `lca_kernel/`, `lca/plugins/transport/`, or `profiles/`.
- They are the only thing standing between current code and a wire-format break that the team has explicitly deferred.

### Shadow modules and twin files

LCA's check scripts flag several twin patterns; they are also worth a manual scan:

- Two Python files in `lca/<layer>/` that differ only in import location (e.g. a "compat" re-export module that mirrors a sibling).
- A dataclass and its Protocol sibling that have identical fields — Protocol should reference the dataclass, not redeclare.
- A `wire/` schema that mirrors a `models/` dataclass field-by-field — wire layer should consume the dataclass and emit only the on-wire projection.

## Audit trust and lifecycle boundaries

For every defensive copy, freeze, validator, and callback capture, name where the value came from and who owns it next. Same-process typed service / plugin / Cordis-context calls ordinarily borrow readonly values; parsers, config loaders, queues, model / tool JSON, durable files, workers, processes, and wire decoders own or validate their data. Tests built around hostile getters, fake typed objects, callback replacement, or mutation after a same-process handoff are evidence of a potentially speculative contract, not automatic justification for keeping it.

For complex asynchronous code, draw the ownership graph and map each sentinel, readiness promise, cancellation path, disposer, and state flag to a distinct owner or transition. When several mechanisms mirror the same liveness or settlement fact (e.g. both a `KernelBootEvent` and a separate `boot_completed` flag fire), propose one lifecycle controller instead. Preserve separate machinery only where it protects Cordis `dispose` → quiescence, journal event single-emit arbitration, or owned subprocess termination.

## Hand-rolled code versus a dependency

Introducing a dependency (Cordis, Cosmokit, Schemastery, py import) is a valid simplification move. The vendored repos are LCA's engine floor, not third-party. When surveying, ask: does `vendor/cordis`, `vendor/cosmokit`, `vendor/schemastery`, the Python stdlib at LCA's target floor (3.11+), or a Python builtin already do this?

Prove a swap candidate like any other, plus:

- Read the hand-rolled implementation and name the exact surface the vendored package covers; residual semantics the package does not cover count against the swap.
- Check the LCA repo for an existing vendored user of that package — if Cordis's `Service` is the accepted seam, an inline lifecycle wrapper is a candidate for replacement.
- Weigh net deletion: implementation plus dedicated tests plus docs minus the glue that remains. A wrapper that relocates the same complexity is not a win.

## Prove or reject each candidate

For every symbol or behavior, classify consumers before writing:

- Production corpus: `lca/{contracts,infrastructure,cognition,runtime,agent,application,harness,plugins}/`, `lca_kernel/`, `profiles/`, `bundles/`, runtime scripts.
- Non-production corpus: `tests/`, `docs/`, `docs/notes/`, snapshots, generated expected outputs, comments.
- Ambiguous corpus: `examples/`, scenario YAMLs, `scripts/`. Inspect usage before classifying.

Use `rg` first. Good searches include the exact symbol, event name, Profile key, config key, method name with both `.name(` and `name(`, any wire strings, and the Cordis `Provides`/`Requires` strings. Then read the call sites, public interfaces, dynamic event names, Profile YAMLs, and Cordis loader paths.

Reject or downgrade a candidate when:

- A production caller exists and the simplification would be a feature decision rather than a cleanup.
- The API is explicitly justified by an ADR or an implemented Agent Note, and the new evidence does not beat that reason (note: 老 ADR 全部不动, never modify the ADR; the candidate either supersedes the obstacle elsewhere or doesn't ship).
- The removal would force unrelated churn (Schema version bumps, Profile topology changes, wire-format bumps) without actually reducing the public API or required behavior — and that churn is not the deletion plan.
- The idea is correct but tiny. Add a targeted `TODO(fold-X)` or `FIXME(dead-sym)` inline per AGENTS.md §1 hygiene rules, naming the smell and the deletion condition, rather than opening an Agent Note.

## Inline TODO/FIXME notes

Use inline notes only for small, local cleanups that are clearly useful but not durable design decisions. Per AGENTS.md §1 hygiene rules:

- Name the smell with a stable tag, e.g. `TODO(fold-compat-shim)` or `FIXME(unused-default)`.
- Explain why it is safe to revisit and what action would simplify it; give the deletion window when the candidate has a `COMPAT(delete-when: …)` parent.
- Do not add TODOs for speculative complaints or for behavior that needs an Agent Note-level decision (use [lca-write-note](../lca-write-note/SKILL.md) instead).

## Coalesce superseded Agent Notes

When the simplification being implemented makes an owning Agent Note obsolete, follow the archive judgment and mechanics in [lca-archive-notes](../lca-archive-notes/SKILL.md). Do not expand every code-simplification survey into a repository-wide note audit — only act on notes the current candidate chain touches.

## Validation and PR hygiene

Run the narrowest relevant check for the touched seam. For docs-only Agent Note work, run `python scripts/verify_md_links.py`, `python scripts/verify_doc_budgets.py`, and `git diff --check`. For code or comment changes, also run `uv run ruff check --fix <changed-path>`, `uv run ruff format <changed-path>`, and the related pytest. For seam / Protocol / wire / Schema changes, escalate per AGENTS.md §6 (Ruff + format + lint-imports + mypy + pytest + relevant check scripts + vulture).

When opening or updating a PR, summarize:

- How many Agent Notes and inline notes were added, consolidated, retained as partial supersessions, or deleted.
- Which LCA seams and which production corpus files were surveyed.
- What was intentionally excluded (老 ADR, vendor/, `docs/notes/archived/`).
- Which checks passed (name each command and the result).

Use a draft PR while the survey is still expanding; mark ready only when the candidate set, review responses, and validation are settled.