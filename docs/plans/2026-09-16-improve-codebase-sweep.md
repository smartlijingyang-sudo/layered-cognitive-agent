# Sweep backlog and rejected candidates

Baseline `f1e6a7867`. Queues below are machine-signalled, each row names its
evidence command. Rejected rows record why a tempting candidate is not shippable
in this sweep (per `.agents/skills/lca-improve-codebase/SKILL.md` §Reject when).

## Open queues (ordered by value)

| queue | how measured | remaining |
|---|---|---|
| pytest collection errors | `uv run pytest -q --collect-only --no-cov \| grep -cE '^ERROR tests/'` | ~33 (from 49) |
| silent-swallow inventory | `python3 scripts/check_no_silent_swallow.py` | 29 (from 35) |
| `lca.harness.composition.plan_compiler` consumers (8 test modules + 3 scripts) | `grep -rn harness.composition.plan_compiler` | v1 plan-shape migration: `phase_graph`/`phase_bindings` gone from `CompiledRunPlan`; needs `graph_spec` re-render per consumer |
| `DeclarativeRunOutcome` / `PhaseRunCursor` / `PhaseAttemptFailure` / `PhaseResult` importers (6 test modules) | collection ERROR list | legacy re-export removed from `declarative_2.declarative_phase_graph` while `tests/contracts/test_declarative_contract_modules.py` still pins it — needs a keep-or-retire decision on that COMPAT surface |
| F401 unused imports | `uv run ruff check . --select F401 --output-format=concise` | ~55 (from 69) |
| E402 module import not at top | `--select E402` | 16 |
| S112 try/except/continue | `--select S112` | 7 |
| SIM105 / S110 | `--select SIM105,S110` | 7 + 4 |
| `# type: ignore` audit | `uv run mypy --warn-unused-ignores` (per-area) | 123 sites to triage |
| `COMPAT(delete-when: …)` shims | `grep -rn "delete-when" --include=*.py lca lca_kernel scripts` | 57/59 markers to test for elapsed windows |
| doc-link rot outside `docs/adr/` | `python3 scripts/verify_md_links.py` | 116 non-ADR broken links (137 total) |
| `scripts/check_package_contracts.py`, `check_emit_single_entry.py`, `check_no_bare_strings.py`, `check_readme_filled.py`, `verify_md_links.py` | each exits 1 | one unit per finding class |
| vulture dead code | `uv run vulture lca --min-confidence 80` | unmeasured |
| stale per-file-ignores in `pyproject.toml` | `grep -n 'gateway/\|lca/infrastructure/cli/cli.py' pyproject.toml` | `"gateway/*" = ["TC002"]` (package deleted in 0af87aeb8); `"lca/infrastructure/cli/cli.py"` while the real path is `cli/cli/cli.py` |

## Rejected / blocked candidates

- **`scripts/lca-inspect-plan.py`, `scripts/e2e_smoke_test.py`,
  `scripts/snapshot_capability_tree.py`.** All three import the deleted
  `lca.harness.composition.plan_compiler` *and* read `plan.phase_graph` /
  `plan.phase_bindings`, which `CompiledRunPlan` does not expose. Fixing the
  import alone leaves each crashing a few lines later, so there is no bounded
  unit here — the candidate is "re-render these three tools onto
  `V2ExecutablePlan.graph_spec`", which is a 1–3 PR plan, not a sweep unit.
  `e2e_smoke_test.py` is reached by `lca-ops e2e timeline`
  (`lca/infrastructure/cli/commands/kernel/e2e.py:120`), so it cannot be deleted
  as dead either.
- **Stub package dirs `lca/plugins/assistant/{catalog,tools}`.** Referenced by
  plugin ids in `bundles/assistant-runtime.yaml` and by
  `lca/plugins/domain/**` (`id="lca.plugins.assistant.catalog.catalog"`);
  deleting needs the id-vs-path question settled first. The other three
  zero-reference stubs (`spine/derivers/step`, `plugins/think/loop`,
  `plugins/think/system`) are being deleted.
- **`tests/scenario/code/test_code_conventions.py` revived fully.** Its
  `_SCAN_PACKAGES` names the deleted top-level `gateway` package (removed in
  0af87aeb8), and its `_PROJECT_ROOT` is two levels short, so `_LCA_ROOT` points
  at `tests/scenario/lca` and the glossary path at
  `tests/scenario/docs/specs/glossary.md`. Fixing the root makes the 250-line
  guard scan the real `lca/` tree, where 100 non-exempt files exceed the limit,
  and re-enables two glossary-coverage tests. Landing that needs a
  freeze-and-ratchet decision on the 100 oversized files plus a naming decision on
  `SpineHandler` (named in AGENTS.md §3 C11, matched by the banned-suffix
  pattern) — an ADR/note, not a sweep unit. The `LcaStreamEventManager` half of
  the naming violation is already fixed.
- **`tests/unit/framework/test_phase_registry.py`.** Imports
  `lca.loop.phases.registry` (`SEMANTIC_PHASE_ORDER`, `PhaseExecutorRegistry`,
  `is_semantic_phase_closed_set`, `phase_executor_capability_key`,
  `PHASE_EXECUTOR_CAPABILITY_PREFIX`); none of those names exists anywhere in the
  repo. The read model was retired with ADR-0194 P4, so the test is for a deleted
  subsystem — deleting it is a judgement about whether the semantic-phase
  closed-set invariant still needs a guard, which belongs in a note.
- **`tests/scenario/llm_0/test_llm_failover.py` (2 sites in
  `tests/scenario/plugin/test_plugin_wiring_e2e.py` too).** Reference
  `lca.plugins.think.llm…` / `lca.plugins.loop.state.stop_policy.plugin`, both
  gone: `lca/plugins/think/` holds `cognitive|composition|loop|null|reasoner|system`
  and StopPolicy was retired (docs/plans/2026-09-14-stop-decision-retirement.md).
  Each is a "does this guard still have a subject?" decision.
- **`tests/infrastructure/cli/test_kernel_serve_probe_lan.py`.** Targets a
  module-level `_probe_lan`, a symbol the package does not define; the current code has
  `KernelSupervisor._probe_health`. The test's own header says it was rewritten
  for the module-level function, so reviving it means re-deriving what the LAN
  fail-fast behavior turns out to be — not an import fix.
- **`tests/infrastructure/test_assistant_merged_skill_store.py` sibling
  `tests/scenario/operational/...::test_file_write_rejects_unwritable_path_as_execution`.**
  Visible only because the module collects: it asserts a `write_file` to
  `/mnt/data/some-file.py` fails, and the shipped path returns `success=True`.
  Real behavior question (path policy), left failing rather than adjusted.
- **`profiles/*.yaml: id: lca-llm-resolver` (5+ profiles).**
  `resolve_profile` rejects it: "patch id 'lca-llm-resolver' does not match any
  bundled plugin". Blocks
  `tests/scenario/sqlite/test_sqlite_state_store.py::test_continuous_profile_enables_sqlite_state_and_control_plane`
  and `tests/scenario/plugin/test_plugin_tree_single_owner.py`
  parametrizations. Needs the replacement plugin id for the LLM resolver seam.
- **Whole-tree `ruff format` (393 files) and `I001`/`W292`/`RUF022`
  single-rule sweeps.** Disqualified by the plan's AC1: reformatting-only diffs.
  Formatting is folded in only where a file is already being changed for a real
  reason.
- **`--select RUF100 --fix` mass pass.** Reverted within this session: with
  `--select` the config's rule set is replaced, so every directive for a rule
  outside that one selection reads as "unused" and 181 files lost live
  suppressions (`ruff check .` jumped 502 → 959). The correct form is
  `ruff check . --fix --fixable RUF100`, which is what drained the real 18.
- **Renaming `SpineHandler`** (and any other public name that a frozen ADR or
  AGENTS.md §3 cites). AGENTS.md §4 forbids editing old ADRs and §1 routes
  closed-set/vocabulary changes to an ADR first; `docs/adr/0200` naming
  `LcaStreamEventManager` was the near-miss here (that rename was safe because
  the class is not part of the ADR's normative contract; `SpineHandler` is named
  in AGENTS.md itself).

## Landed since the first ledger snapshot

- 4 dead `# type: ignore`-adjacent and F401 sites in `scripts/` (yaml/sys/shutil/re)
  and `lca/runtime/projection/result_finalizer.py`, `lca/plugins/composer/runtime/
  runtime/{capabilities,assembly}.py`.
- 3 reasoner renderers repointed to `lca/cognition/brain/sections/types.py`
  (`render_teammates`, `render_member_reports`, `render_prior_conversation_from_state`)
  — the characterization module's 8 golden text assertions run again; the routing
  module's remaining failure drives the removed `PromptReasoner.generate_thoughts`
  and needs a DTO rewrite (candidate below).
- Link rot: 140 → 84 broken links. Classes fixed — layer-table prefix one level
  short (`docs/specs/platform-directory-architecture.md`), doubled `adr-` filename
  prefix (`docs/specs/hermes-lca-semantic-reference.md`), anglicised heading
  fragments recomputed with `scripts/verify_md_links.py:slugify_heading`
  (`docs/specs/external-plugin-trust-rubric.md`), and `../adr/` written from
  three-levels-deep notes (`docs/notes/{archived,implemented}/seam/*`,
  `docs/notes/plans/2026-09-09-colony-runtime-architecture-review-response.md`).

## Additional rejected / blocked candidates

- **Deleted-link targets.** `docs/adr/0209-agent-lab-cordis-unification.md` and the
  sibling note `2026-09-09-lab-cordis-unification-landing.md` do not exist; the
  archived P7 record links them. Repairing that means deciding whether ADR-0209 was
  withdrawn or renamed — a docs-ownership question, not a link fix.
- **`tests/scenario/routing/test_routing_prompt_reports.py`'s last failure** drives
  `PromptReasoner.generate_thoughts(state)`; the current surface is
  `build_turn_plan` / `render_turn` / `complete_turn` over `ReasonerContext`,
  `TemplateSelection`, `RoleSnapshot`. Rewiring needs the prompt-template provider,
  so it is a candidate, not a sweep unit.

## Marker triage (COMPAT / delete-when), run against each marker's own clause

Executed, condition met:
- `lca/contracts/observability/registry/status.py` `CANCELED = CANCELLED`
  (clause: `rg "\.CANCELED\b"` 生产引用归零). 12 production + 11 test readers
  migrated to the canonical member first, then the alias deleted; members,
  `_name_`, `str()` and the `"canceled"` wire value were verified unchanged, and
  `RunLifecycleStatus.CANCELED` now raises `AttributeError`.

Evaluated, condition NOT met (kept, with the measurement that says so):
- `journal/engine/reducer.py` `RunStatus` alias — the *statement* reads
  `rg "\bRunStatus\." 生产引用归零`, which is 0, but the same clause continues
  "全部改走 RunLifecycleStatus", and the name is still re-exported by two
  production barrels (`journal/__init__.py` import + `__all__`, and the
  `observability/__init__.py` PEP 562 lazy map) that ~20 test modules import
  through. Deleting it without those barrels is a half-migration, so the shim
  stays; the barrel sweep is the unit that unlocks it.
- `handlers/runs/session/session/session.py` `RunStatus` — clause asks for
  `rg 'RunStatus' tests/ lca/plugins/transport/ = 0 except alias`; 71 hits.
- `spine/sinks/naming.py` — clause is "默认稳定 ≥ 14 天"; the file's last change
  is 2026-09-03, i.e. 13 days at this writing. One day short, so not deleted.
- `journal/step.py` deprecated `arguments_summary` — clause "所有 caller 迁移完毕";
  55 references remain.
- `sinks/{file_sink,routing_file_sink,tracing_file_sink}.py` — clause "PR-9";
  consumers are 118 / 6 / 5, and these are live implementations, not shims.
- `contracts/protocols/assistant/evolve.py`, `plugins/domain/assistant/catalog/plugin.py`,
  `routes_assistants.py`, `assistant/evolve/evolve.py` — fixed date
  `delete-when: 2026-12-31`, in the future.
- `cli/cli.py:138,174` — explicit `delete-when: never` (documented entry points).
- `prompt_assembly.py:189`, `loop_cursor_payloads.py:52` — explicit
  `delete-when: N/A(纯加法)`.
- `harness/declarative/__init__.py:67` — the string is inside a fail-loud
  `AttributeError` message for already-retired v1 symbols, not a live shim.
