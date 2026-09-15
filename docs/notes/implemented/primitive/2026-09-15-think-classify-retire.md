# Agent Note: Retire `think.classify` phase primitive

Status: implemented

## Problem

`bundles/think.yaml` declares `think.classify` as a node, but commit `2ee56fdc8` ("split think.reason.complete into llm.dispatch + decision.parse") rewired `history.assemble → llm.dispatch → decision.parse → gate` and removed the only edges that reached `think.classify`. The comment block on the node (`bundles/think.yaml`, lines 88–93) framed the node as a "temporary outer-facing entry to be merged into `think.decision.parse` in a follow-up task"; that follow-up never landed, leaving the node as a dead declaration. Boot-time plan-lift invariant `lca_kernel.boot.plan_validation.validate_profile_plans` (commit `03dc0def0`, "validate every plan-level graph invariant at startup") rejects unreachable nodes, so `lca_kernel serve` raises `PlanLiftError("think.classify unreachable from entry think.shortcut")` ~1.2s after the boot log line and never binds `:8765`. The integration test `tests/integration/test_run_with_tool_use.py` has been bypassing the invariant by monkey-patching `validate_profile_plans` to a no-op since PR2; that workaround hides the defect from CI and from `lca-ops status`.

## Decision

Delete the `think.classify` primitive in this PR — node, plugin, manifest entry, plugin-level tests, docstring references, and the `validate_profile_plans` no-op bypass in the integration test. `think.decision.parse` already covers the same responsibility (it consumes the typed `response` port and produces the typed `decision` port that `think.gate` enforces), so the merge the comment promised has effectively already happened; `think.classify` is duplicate functionality without any caller.

Concrete removals:

- `bundles/think.yaml` — drop the `think.classify` node block (lines 82–101).
- `bundles/base.yaml` — drop the `phase.think.classify` plugin manifest entry (lines 74–77).
- `lca/plugins/think/classify.py` — delete the file (`ThinkClassifyExecutor` + `setup`).
- `lca/plugins/think/__init__.py` — drop `from lca.plugins.think.classify import …`, the `_setup_classify` re-export, and `ThinkClassifyExecutor` / `_setup_classify` from `__all__`.
- `tests/think/test_classify_phase_plugin.py` — delete the file.
- `tests/infrastructure/cli/test_plan_tree.py` — drop `think.classify` from the two expected node-id lists.
- `tests/integration/test_run_with_tool_use.py` — delete the `import lca_kernel.boot.plan_validation as _pv; _pv.validate_profile_plans = lambda _resolved: None` bypass and its 6-line explanatory comment.
- `lca/framework/graph/plan_sdk.py` — comment update: `decision` port now comes from `think.decision.parse / think.gate` (was `think.classify / think.gate`).
- `lca/framework/graph/nodes/decision_parse.py` — docstring update: the node produces `Decision` for `think.gate` and the outer interpreter (was `think.classify / think.gate`).

Out of scope (kept intentionally; flag for `lca-find-simplifications` follow-up):

- `lca/plugins/composer/think/brain_composer.py:72` still populates `phase.think.classify` from `brain.classifier` when present, and `:85` still aliases `brain.classifier → decision_classifier`. Both lines become dead because the only consumer (`think/classify.py`) is gone, but `brain.classifier` may still be set by upstream callers and the alias is consumed by other legacy think plugins. Removing them in this PR would expand blast radius beyond the boot-fix; defer.

## Alternatives considered

- **Keep `think.classify`, add a `history.assemble → think.classify` edge** — rejected: `think.classify` and `think.decision.parse` both project `response → decision`. Restoring the edge would route LLM output through two consecutive parse-classifier nodes that produce the same port, duplicating work and re-introducing the "what's the difference between these two?" question that ADR-0221 explicitly closed. The TODO the comment refers to ("把它和 decision.parse 合并") already happened by another path.
- **Keep `think.classify`, wire it as an alternate `outer-facing` entry distinct from `decision.parse`** — rejected: no current consumer asks for two parallel `LLMResponse → Decision` projections; `agent.reasoning_turn.yaml` uses its own `reason.classify.response` for the agent reasoning subgraph, not `think.classify`. No semantics left to preserve.
- **Disable the unreachable-node invariant in `validate_profile_plans`** — rejected: AGENTS.md §4 ("无 delete-when 的兼容分支 = 红灯") plus the invariant's explicit purpose ("validate every plan-level graph invariant at startup" — `03dc0def0`). Disabling it would silently accept every future dead-node regression; this PR is the second time the invariant has caught a defect.
- **Do nothing (baseline)** — rejected: kernel stays unbootable, the integration test continues to monkey-patch the validator, and `lca-ops status` keeps reporting `kernel_serve: stopped` because no profile resolves. Effectively broken.

## Consequences

- `lca_kernel serve` boots past plan-lift: `validate_profile_plans` runs to completion and `:8765` binds in < 5s; `lca-ops status` reports `kernel_serve: running`.
- The integration test `tests/integration/test_run_with_tool_use.py` exercises the real plan-lift path; if a future PR reintroduces a dead node, the test fails on profile boot rather than passing through the no-op bypass.
- `phase.think.classify` capability key disappears from `Ctx.capabilities`; any profile / bundle that wires `phase.think.classify` would now fail at plan-lift with `unresolved capability`. None do today (only `brain_composer` populates it, and `brain_composer`'s lookup is guarded by `if value is not None`).
- The dead-alias line in `brain_composer.py:85` survives as a known minor cleanup item; tracked for `lca-find-simplifications`.

## Verification

- `python -m lca_kernel serve --profile profiles/web-standard.yaml --port 8765 --allow-unknown-env` binds `:8765` within 5s and `lca-ops status --json` reports `kernel_serve.status = "running"`.
- `tests/infrastructure/cli/test_plan_tree.py::test_plan_tree_think_subgraph_profile_default` and `::test_plan_tree_think_subgraph_profile_json_structure` pass with the trimmed node-id lists.
- `tests/integration/test_run_with_tool_use.py` runs without monkey-patching `validate_profile_plans`.
- `pytest tests/think/` (no `test_classify_phase_plugin.py`) — all remaining think-plugin tests pass.
- Regression test `tests/unit/test_think_subgraph_no_dead_nodes.py` (added in this PR) resolves `profiles/web-standard.yaml`, runs `validate_profile_plans`, and asserts it returns without raising.

## Cross-references

- ADR: none (this retire closes a comment-block TODO from ADR-0220 P6 / ADR-0221; no new boundary).
- Plans: `docs/superpowers/plans/2026-09-15-pr2-session-write-path.md` (PR2 already noted the bypass as a known gap).
- Commits:
  - `2ee56fdc8 feat(graph): split think.reason.complete into llm.dispatch + decision.parse` — origin of the unreachable node.
  - `03dc0def0 feat(boot): validate every plan-level graph invariant at startup` — invariant that surfaced the defect.
  - `725447d78 feat(graph): add think.history.assemble (spec §D orphan-drop)` — sibling change that further isolated `think.classify`.

## Related follow-ups (not in this PR)

- **`boot.pending_event` lines dropped after PR3 merge (`d38522617`).**
  Observed while running `lca-ops kernel-restart` after this retire:
  `kernel logs` reports `no boot.pending_event lines in
  /tmp/lca-kernel.stderr.<pid>.<stamp>.log` even though `plugin_count=242`
  in `/health`. Pre-retire baseline log (`/tmp/k-after.log`, captured
  17:35) had **242** `boot.pending_event` lines; the post-PR3 boot logs
  (`/tmp/lca-kernel.stderr.<pid>.<stamp>.log`) have **0**. The structlog
  fallback in `lca_kernel.boot.boot._emit_boot_events` (the `for event in
  pending_events: _log.info("boot.pending_event", ...)` block at lines
  ~396–404) is still present but no longer fires — most likely PR3's
  `@graph_node` DSL moves plugin loading off the path that populates
  `pending_events`. `kernel logs` accurately reports the empty state, so
  the diagnostic command itself is healthy; the **gap is operator
  visibility into plugin fiber spawn** during boot. Owner: PR3 author.
  Possible fixes: re-emit `boot.pending_event` from the new graph-node
  setup path; or migrate `kernel logs` to read from the Journal rather
  than the per-spawn stderr file (Journal already records every fiber
  spawn via `BootPluginFiberSpawned`).
- **`lca/plugins/composer/think/brain_composer.py:72` dead capability
  lookup** (`("phase.think.classify", "classifier")` line) — now that
  `phase.think.classify` has no provider, the `if value is not None`
  guard makes the line a no-op. Defer to a `lca-find-simplifications`
  sweep; harmless as-is.
- **`kernel-supervisor` refactor landed (post-this-retire, same session).**
  The `boot.pending_event` gap is now closed operationally:
  `lca-ops kernel-supervisor {start,stop,restart,status,events,logs}`
  reads from a cross-process state file (atomic JSON at
  `/tmp/lca-supervisor.state.json`), and `kernel-supervisor logs
  --follow` tails the actual stderr file. The `kernel_restart` CLI
  command now delegates to `kernel-supervisor restart`. Suggested
  long-term fix for the missing boot events themselves remains
  upstream (PR3 graph-node DSL).