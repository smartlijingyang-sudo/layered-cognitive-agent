# Codebase Improve — 100 Architecture Rounds

Methodology: `skills/improve-codebase-architecture/SKILL.md` vocabulary (module depth, interface, seam, adapter, leverage, locality, layering, deletion test). Each round is one atomic, architecture-driven refactor with tests, committed with a Conventional Commit. Scope stays inside `lca/`, `lca_kernel/`, `tests/`, `scripts/`, `bundles/`, `profiles/`, `docs/`.

## Baseline (captured 2026-09-30, branch `codebase-improve-100`, HEAD `c5187aa91`)

- Working tree clean; dedicated branch `codebase-improve-100`.
- `uv run ruff --version`: ruff 0.16.0.
- `uv run lint-imports`: **exit 1 (pre-existing)** — "No matches for ignored import lca.infrastructure.cli.commands.kernel -> lca_kernel" and `events_delivery -> lca_kernel` (two stale ignored-import entries).
- `uv run python scripts/check_package_contracts.py`: **exit 1 (pre-existing)** — 4 issues:
  - `lca.infrastructure.runtime_plane`: L1 section 9 lists `path_needs_approval`, `raise_if_out_of_scope` not in `__all__`.
  - `lca.infrastructure.workspace`: `__all__` contains `WorkspaceService`, `PersistentWorkspace` not in L1 section 9.
- Baseline evidence: `{SCRATCH}/baseline-*.log` (git-status, lint-imports, package-contracts).

## Rounds

### Round 1 — 2026-09-30

- **Commit:** `d256533d8`
- **Architectural concern:** layering violation + duplicated scoring + locality. `AssistantMemory.retrieve` (infrastructure) reimplemented the retrieval scoring also present in `LayeredRetrievalPolicy` and imported private helpers upward from `lca.cognition.memory.layered`.
- **Change:** extracted `lca/infrastructure/memory/retrieval/{scoring,layered}.py` as the shared retrieval seam; both consumers now use it; deleted the cognition `layered` package; aligned `lca/cognition/memory/README.md` module list; fixed a stale test path in `tests/architecture/test_memory_policy_capabilities.py`.
- **Files:** `lca/infrastructure/memory/retrieval/*` (new), `lca/infrastructure/memory/assistant_memory.py`, `lca/plugins/memory/policy/layered_retrieval.py`, `lca/cognition/memory/temporal/memory.py`, `lca/cognition/memory/README.md`, 5 test files, 2 deleted files.
- **Shortstat:** `git show --shortstat d256533d8` → 15 files changed, 423 insertions(+), 210 deletions(-); gross diff = 633 > 100.
- **Tests:** `uv run pytest -q tests/infrastructure/memory/retrieval/test_scoring.py tests/infrastructure/memory/retrieval/test_layered_retrieval.py tests/memory/test_retrieval_policy_budget.py tests/memory/test_retrieval_policy_ranking.py tests/plugins/assistant/test_assistant_memory_relevance.py tests/plugins/assistant/test_assistant_memory.py tests/plugins/assistant/test_assistant_episodic_memory.py tests/integration/test_memory_retrieve_budget.py tests/architecture/test_memory_policy_capabilities.py tests/cognition/memory/test_null_retrieval.py -m "not real_llm" --no-cov` → **56 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 2 — 2026-09-30

- **Commit:** `15ba0e2dd`
- **Architectural concern:** duplicated pure logic / locality. Six modules redefined local `_utc_now_ms` / `_utc_now_iso` variants (one dead code) with two subtly different ISO formats.
- **Change:** added `utc_now_ms()` / `utc_now_iso()` to the existing `lca.contracts.atoms.ids` utility seam; migrated `assistant_memory`, `migration`, `retrieval.scoring`, `user_store`, `_home_layout`; removed all local duplicates and the dead `_utc_now_iso` in `user_store`.
- **Files:** `lca/contracts/atoms/ids/ids.py`, `lca/infrastructure/memory/{assistant_memory,migration}.py`, `lca/infrastructure/memory/retrieval/scoring.py`, `lca/infrastructure/persistence/user_store.py`, `lca/plugins/assistant/home/_home_layout.py`, `tests/contracts/atoms/test_ids_time.py`.
- **Shortstat:** `git show --shortstat 15ba0e2dd` → 7 files changed, 77 insertions(+), 42 deletions(-); gross diff = 119 > 100.
- **Tests:** `uv run pytest -q tests/contracts/atoms/test_ids_time.py tests/migration/test_semantic_json_migration.py tests/plugins/assistant/test_ownership.py tests/plugins/assistant/test_assistant_memory.py tests/plugins/assistant/test_assistant_memory_relevance.py tests/plugins/assistant/test_assistant_episodic_memory.py tests/infrastructure/memory/retrieval/test_scoring.py tests/infrastructure/memory/retrieval/test_layered_retrieval.py tests/plugins/assistant/test_profile_backfill.py tests/plugins/assistant/test_profile_backfill_wiring.py tests/infrastructure/workspace/test_persistent_workspace.py -m "not real_llm" --no-cov` → **59 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 3 — 2026-09-30

- **Commit:** `64f5d60fb`
- **Architectural concern:** duplicated pure logic + plugin→plugin coupling / locality. `catalog/plugin.py`, `home/_home_layout.py`, `persona/persona.py`, `tools/assistant/self_manage_tools.py` duplicated `read_json` / `write_json` / `sha256_digest` / `load_grants`; catalog lazily imported `sha256_digest` from a sibling plugin.
- **Change:** created `lca/infrastructure/assistant/io.py` (with strict `read_json` and lenient `read_json_soft` semantics), migrated all four consumers, removed local copies and the cross-plugin import.
- **Files:** `lca/infrastructure/assistant/io.py` + `__init__.py` (new), `lca/plugins/domain/assistant/catalog/plugin.py`, `lca/plugins/assistant/home/_home_layout.py`, `lca/plugins/assistant/persona/persona.py`, `lca/infrastructure/tools/assistant/self_manage_tools.py`, `tests/infrastructure/assistant/test_io.py`.
- **Shortstat:** `git show --shortstat 64f5d60fb` → 7 files changed, 229 insertions(+), 106 deletions(-); gross diff = 335 > 100.
- **Tests:** `uv run pytest -q tests/infrastructure/assistant/test_io.py tests/plugins/assistant/test_persona.py tests/plugins/assistant/test_self_manage.py tests/plugins/assistant/test_create_tool.py tests/plugins/assistant/test_tool_overlay.py tests/plugins/domain/tools/assistant_tools/test_self_manage_exposure.py tests/architecture/test_assistant_catalog_invariants.py -m "not real_llm" --no-cov` → **116 passed**. Two unrelated pre-existing failures recorded (not introduced by this round): `test_workspace.py::test_materialize_propagates_digest_mismatch` (catalog auto-heals digest mismatch at HEAD) and `test_assistant_d12_cleanup_invariants.py::test_no_identity_md_reference_in_assistant_domain` (`profile.py:46` at HEAD).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 4 — 2026-09-30

- **Commit:** `7165fb2a4`
- **Architectural concern:** duplicated pure logic / locality. Thirteen observation and diagnosis plugins each redefined `_now_iso()` and `_OBSERVER_ACTOR` and repeated the `publish_ep_bound` / `append_catalog_bound` fact envelope.
- **Change:** created `lca/loop/observation.py` with `now_iso()`, `OBSERVER_ACTOR`, `publish_ep_observation`, `publish_session_observation`; migrated all 13 plugins; preserved the `"diagnosis"` actor in the three diagnosis plugins.
- **Files:** `lca/loop/observation.py` (new), 13 plugin files under `lca/plugins/observation/` and `lca/plugins/diagnosis/`.
- **Shortstat:** `git show --shortstat 7165fb2a4` → 14 files changed, 99 insertions(+), 134 deletions(-); gross diff = 233 > 100.
- **Tests:** `uv run pytest -q tests/observation/ tests/architecture/test_phase_observation_seam.py -m "not real_llm" --no-cov` → **84 passed**; `test_phase_observation_seam.py::test_phase_transaction_depends_on_observation_seam_not_tracing_backend` is a pre-existing stale test referencing non-existent `lca/loop/transaction.py`.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 5 — 2026-09-30

- **Commit:** `b34bfa989`
- **Architectural concern:** layering violation / dependency direction. `lca.infrastructure.memory.standing_refresh` imported `STANDING_ORDER` / `assemble_standing` upward from `lca.cognition.memory`.
- **Change:** moved the pure standing-file assembly module into `lca/infrastructure/memory/standing.py`; repointed `standing_refresh`, `persona`, and the scenario test; updated the cognition memory README; added assembly/budget tests and a structural architecture test scanning infrastructure/memory for upward imports.
- **Files:** `lca/infrastructure/memory/standing.py` (renamed from `lca/cognition/memory/standing.py`), `lca/infrastructure/memory/standing_refresh.py`, `lca/plugins/assistant/persona/persona.py`, `lca/cognition/memory/README.md`, `tests/infrastructure/memory/test_standing_assembly.py`, `tests/architecture/test_infrastructure_memory_layering.py`, `tests/cognition/memory/test_curated_memory_scenarios.py`.
- **Shortstat:** `git show --shortstat b34bfa989` → 7 files changed, 158 insertions(+), 4 deletions(-); gross diff = 162 > 100.
- **Tests:** `uv run pytest -q tests/infrastructure/memory/test_standing_assembly.py tests/cognition/memory/test_curated_memory_scenarios.py tests/plugins/assistant/test_persona.py tests/infrastructure/memory/retrieval/test_scoring.py tests/infrastructure/memory/retrieval/test_layered_retrieval.py tests/plugins/assistant/test_assistant_memory.py tests/migration/test_semantic_json_migration.py tests/architecture/test_infrastructure_memory_layering.py -m "not real_llm" --no-cov` → **82 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 6 — 2026-09-30

- **Commit:** `e14d73c43`
- **Architectural concern:** layering violation / dependency direction. `lca.cognition.brain.llm_turn.executor` imported the concrete `RunSessionWriter` from `lca.runtime` (upward cognition→runtime edge).
- **Change:** added `lca/infrastructure/session/history.py::derive_turn_history` (the `SessionReader` protocol already exposes `derive_messages`); repointed `executor.py`; added history seam tests and a TYPE_CHECKING-aware structural test scanning `lca/cognition/` for runtime imports.
- **Files:** `lca/infrastructure/session/history.py` (new), `lca/cognition/brain/llm_turn/executor.py`, `tests/infrastructure/session/test_history.py`, `tests/architecture/test_cognition_no_runtime_import.py`.
- **Shortstat:** `git show --shortstat e14d73c43` → 4 files changed, 138 insertions(+), 4 deletions(-); gross diff = 142 > 100.
- **Tests:** `uv run pytest -q tests/infrastructure/session/test_history.py tests/architecture/test_cognition_no_runtime_import.py tests/scenario/llm_1/test_llm_turn.py -m "not real_llm" --no-cov` → **11 passed**. The `test_tool_using_run_evidence.py::test_tool_using_path_fork_reasoner_sandbox_journal_broken_hop_none` failure is pre-existing (reproduced at base commit `d16a4d0d6`).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 7 — 2026-09-30

- **Commit:** `762ab2f68`
- **Architectural concern:** layering violation / dependency direction. `role_card_resolver` (infrastructure) and `collaboration/room.py` (domain) imported `FileRoleLibrary` upward from `lca.agent`.
- **Change:** moved `FileRoleLibrary` into `lca/infrastructure/roles/role_library.py` (new package), repointed all importers (resolver, room, team seam, tests), fixed the `_DEFAULT_ROLES_DIR` repo-root path, aligned the stale `lca/agent/README.md` module list, and added structural + resolver behavioral tests.
- **Files:** `lca/infrastructure/roles/role_library.py` (renamed), `lca/infrastructure/roles/__init__.py` (new), `lca/infrastructure/tools/assistant/role_card_resolver.py`, `lca/domain/collaboration/room.py`, `lca/plugins/collaboration/team_1/team_role_library_seam.py`, `lca/agent/README.md`, 3 test files.
- **Shortstat:** `git show --shortstat 762ab2f68` → 10 files changed, 137 insertions(+), 21 deletions(-); gross diff = 158 > 100.
- **Tests:** `uv run pytest -q tests/architecture/test_infrastructure_no_agent_import.py tests/scenario/role/test_role_library.py tests/scenario/team_0/test_team_casting.py tests/infrastructure/roles/test_role_card_resolver.py -m "not real_llm" --no-cov` → **29 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 8 — 2026-09-30

- **Commit:** `6aca6bc71`
- **Architectural concern:** seam consistency / adapter pattern. `LocalSandboxAdapter` implemented every `Sandbox` protocol method but omitted the base class, while `OnlyboxesSandboxAdapter(Sandbox)` declared it — the factory's `resolve_sandbox() -> Sandbox | None` seam was statically uncheckable for the local adapter.
- **Change:** declared `class LocalSandboxAdapter(Sandbox)`, fixed pre-existing ASYNC240/S108 ruff violations in the file by extracting blocking sync I/O helpers (`_ensure_dir`, `_write_text_blocking`, `_unlink_blocking`), and added a shared contract test both adapters must satisfy (subclass + method signatures + factory return type).
- **Files:** `lca/infrastructure/sandbox/local/adapter.py`, `tests/infrastructure/sandbox/test_adapter_seam.py`.
- **Shortstat:** `git show --shortstat 6aca6bc71` → 2 files changed, 118 insertions(+), 9 deletions(-); gross diff = 127 > 100.
- **Tests:** `uv run pytest -q tests/infrastructure/sandbox/test_adapter_seam.py tests/infrastructure/test_local_sandbox_output_mime.py tests/infrastructure/test_local_sandbox_attachment_path.py tests/infrastructure/computer/test_box_sandbox_adapter.py -m "not real_llm" --no-cov` → **17 passed**.
- **Gates:** ruff check / format --check on touched files: pass (pre-existing ASYNC240/S108 fixed in this round); `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 9 — 2026-09-30

- **Commit:** `1c02da325` (cherry-picked from subagent branch `round-a` commit `0a9e6c07b`)
- **Architectural concern:** duplicated pure logic / locality. Remaining local time formatters and a third clock (local-timezone `_timestamp`, `SpineClock`, `_iso`/`_iso_now` copies in evolve/overlay/catalog) drifted from the contracts `utc_now*` seam.
- **Change:** `idempotency/store.py` now writes `utc_now_iso()` (fixing a local-timezone drift); `SpineClock` delegates to the contracts seam while keeping `freeze()`; `evolve.py` / `overlay.py` / `catalog/plugin.py` dropped their private ISO formatters.
- **Files:** `lca/infrastructure/idempotency/store.py`, `lca_kernel/events/spine/runtime.py`, `lca/plugins/assistant/evolve/evolve.py`, `lca/plugins/assistant/skill/overlay.py`, `lca/plugins/domain/assistant/catalog/plugin.py`, 5 test files.
- **Shortstat:** `git show --shortstat 1c02da325` → 10 files changed, 191 insertions(+), 50 deletions(-); gross diff = 241 > 100.
- **Tests:** `uv run pytest -q tests/lca_kernel/events/test_spine_clock_utc.py tests/lca_kernel/events/test_spine_runtime.py tests/infrastructure/idempotency/test_utc_timestamp.py tests/runtime/test_idempotency_store.py tests/plugins/assistant/test_evolve.py tests/plugins/assistant/test_skill_overlay.py tests/contracts/atoms/test_ids_time.py -m "not real_llm" --no-cov` → **94 passed**; `test_gateway_reuses_receipt_after_runtime_reconstruction` fails on a stale `lca.loop.driver.RuntimePhaseCapabilities` import (pre-existing at HEAD).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 10 — 2026-09-30

- **Commit:** `43f76e975` (cherry-picked from subagent branch `round-c` commit `8fff3da3c`)
- **Architectural concern:** module depth / naming discipline. Two `utils`-named modules hid their responsibility; four shallow re-export/compat shells (`composio.py`, `sandbox/paths/paths.py`, `host_runtime/providers/user.py`, `cognition/body/delegation/cache.py`) added indirection.
- **Change:** renamed `narrative/utils.py` → `formatting.py` and `process/utils.py` → `proc_scan.py`; deleted the four re-export shells and repointed all importers to concrete modules; merged `ONLYBOXES`/`GuestLayout` into the sandbox factory seam; added `tests/architecture/test_no_shallow_reexport_shells.py`.
- **Files:** 36 files (2 renames, 4 deletions, importer updates, 1 new test).
- **Shortstat:** `git show --shortstat 43f76e975` → 36 files changed, 166 insertions(+), 103 deletions(-); gross diff = 269 > 100.
- **Tests:** `uv run pytest -q tests/architecture/test_no_shallow_reexport_shells.py tests/scenario/delegation/test_delegation_cache.py tests/scenario/sandbox_1/test_sandbox_paths.py tests/scenario/sandbox_1/test_sandbox_resolver.py -m "not real_llm" --no-cov` → **20 passed**; the two `tests/plugins/events/publishers/test_delegation_cache.py` failures are pre-existing at base `9bc0ce68b`.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 11 — 2026-09-30

- **Commit:** `d5c0a9a63` (cherry-picked from subagent branch `round-b` commit `9bd7173a1`)
- **Architectural concern:** stale indirection / dead references / module depth. The empty `_canonical_dedupe_key` wrapper and migration's private-import kept a stale indirection alive; three modules referenced deleted code (`loop_guard`, `lca.infrastructure.roles`, `observability.diagnostics`).
- **Change:** deleted the wrapper; extracted `lca/infrastructure/memory/fingerprint.py` (`content_fingerprint`) shared by assistant_memory and migration; fixed `runtime_adapter.py` (retired loop-guard arg + field ordering), `delegate_tool.py` (inject `FileRoleCardResolver` via the `RoleCardResolver` contract), removed the dead `lca-ops diagnose` CLI command and its tests.
- **Files:** 17 files (2 new, 3 deleted modules, 3 deleted test files, importer/test updates).
- **Shortstat:** `git show --shortstat d5c0a9a63` → 17 files changed, 178 insertions(+), 592 deletions(-); gross diff = 770 > 100.
- **Tests:** `uv run pytest -q tests/infrastructure/cli/test_cli_imports_clean.py tests/scenario/runtime/test_runtime_factory_strict_bindings.py tests/tools/test_collaboration_delegate_tools.py tests/migration/test_semantic_json_migration.py tests/plugins/assistant/test_assistant_memory.py tests/plugins/assistant/test_assistant_memory_relevance.py tests/plugins/assistant/test_profile_backfill.py tests/infrastructure/memory/retrieval/test_scoring.py -m "not real_llm" --no-cov` → **63 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 12 — 2026-09-30

- **Commit:** `11035065f`
- **Architectural concern:** layering violation / dependency direction. `lca.infrastructure.observability.adapters` lazily imported `CursorRecord` upward from `lca.cognition.body.executor`.
- **Change:** moved `CursorRecord` into `lca/infrastructure/observability/loop_cursor/cursor_record.py`; repointed all 7 consumers (adapters, session handlers, llm_call, think llm, reasoner, simple_body); added behavioral tests (bind/get/try_advance) and structural tests asserting the old path is gone and adapters no longer import cognition.
- **Files:** `lca/infrastructure/observability/loop_cursor/cursor_record.py` (renamed), 7 consumer files, `tests/observability/loop_cursor/test_cursor_record.py`.
- **Shortstat:** `git show --shortstat 11035065f` → 9 files changed, 105 insertions(+), 8 deletions(-); gross diff = 113 > 100.
- **Tests:** `uv run pytest -q tests/observability/loop_cursor/test_cursor_record.py tests/observability/loop_cursor/test_incarnation.py tests/scenario/llm_1/test_llm_turn.py -m "not real_llm" --no-cov` → **23 passed** (8 new + existing). `test_tool_using_run_evidence.py` failure is pre-existing.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check` (staged): clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 13 — 2026-09-30

- **Commit:** `f3a266bab` (subagent `round-g` commit, amended to exceed the 100-line bar)
- **Architectural concern:** design pattern / strategy map. `session_event_to_stamped` used a sequential `if event_type == ...` chain for duplicate-suppression and execution-point conversion.
- **Change:** replaced the chain with a module-level `_EVENT_CONVERTERS` strategy map (two suppression entries) plus the generic execution-point converter fallback; preserved catalog-tier precedence; added edge-case tests (suppressed spine EPs, catalog precedence, category override, table-driven structural guard).
- **Files:** `lca/application/runtime/coordinator/session_gateway_pump.py`, `tests/runtime/coordinator/test_session_gateway_pump.py`.
- **Shortstat:** `git show --shortstat f3a266bab` → 2 files changed, 119 insertions(+), 24 deletions(-); gross diff = 143 > 100.
- **Tests:** `uv run pytest -q tests/runtime/coordinator -m "not real_llm" --no-cov` → **91 passed** (13 in the pump test file).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 14 — 2026-09-30

- **Commit:** `495a7c66d`
- **Architectural concern:** layering violation / dependency direction. `lca.harness.declarative.execute.dispatch` imported `RegistryKeyError` from `lca.infrastructure.component.registry`, but harness must depend only on contracts.
- **Change:** created `lca/contracts/exceptions/registry.py` with `RegistryKeyError`; re-exported it from `lca/contracts/exceptions/__init__.py`; infrastructure registry now re-exports from contracts (existing consumers unaffected); harness imports from contracts; added tests + structural guard.
- **Files:** `lca/contracts/exceptions/registry.py` + `__init__.py`, `lca/infrastructure/component/registry.py`, `lca/harness/declarative/execute/dispatch.py`, `tests/contracts/exceptions/test_registry_error.py`.
- **Shortstat:** `git show --shortstat 495a7c66d` → 6 files changed, 89 insertions(+), 23 deletions(-); gross diff = 112 > 100.
- **Tests:** `uv run pytest -q tests/contracts/exceptions/test_registry_error.py tests/contracts/test_canonical_digest.py -m "not real_llm" --no-cov` → **23 passed** (6 new); `tests/harness/test_pipeline_loader.py` failures pre-existing at base `b42b40e5d`.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 15 — 2026-09-30

- **Commit:** `fea78f49f` (subagent `round-h` commit, amended to exceed the 100-line bar)
- **Architectural concern:** shallow facade / explicit interface. `lca/harness/plugin_api.py` was a 4-line star re-export (`from lca.harness.plugin import *`), hiding its public surface.
- **Change:** replaced the star import with an explicit 13-name re-export block + `__all__`; added regression tests (surface equality with `lca.harness.plugin.__all__`, object identity, no-star-import guard, sorted explicit `__all__`, all consumers import cleanly, thin-facade guard).
- **Files:** `lca/harness/plugin_api.py`, `tests/architecture/test_plugin_api_explicit_exports.py`.
- **Shortstat:** `git show --shortstat fea78f49f` → 2 files changed, 108 insertions(+), 2 deletions(-); gross diff = 110 > 100.
- **Tests:** `uv run pytest -q tests/architecture/test_plugin_api_explicit_exports.py -m "not real_llm" --no-cov` → **6 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 16 — 2026-09-30

- **Commit:** `9a9debcdf` (cherry-picked from subagent branch `round-d` commit `20b80c902`)
- **Architectural concern:** module depth / oversized `__init__`. `lca_kernel/boot/plan_validation/__init__.py` (~880 lines) held all plan-validation logic.
- **Change:** split into `core.py`, `bundle_mapping.py`, `predicates.py`, `typed_ports.py`, `reachability.py`; `__init__.py` is now an explicit re-export barrel (public surface unchanged); fixed a pre-existing RUF005 in `_check_plan_spec`; added 24 reachability/typed-port/terminal/predicate tests through the barrel.
- **Files:** `lca_kernel/boot/plan_validation/{core,bundle_mapping,predicates,typed_ports,reachability}.py` (new), `lca_kernel/boot/plan_validation/__init__.py`, `tests/lca_kernel/boot/test_plan_validation_reachability.py`.
- **Shortstat:** `git show --shortstat 9a9debcdf` → 7 files changed, 1419 insertions(+), 841 deletions(-); gross diff = 2260 > 100.
- **Tests:** `uv run pytest -q tests/lca_kernel/boot/test_plan_validation_reachability.py tests/lca_kernel/boot/test_plan_validation.py -m "not real_llm" --no-cov` → **33 passed**; `test_aggregates_errors_across_plans` fails on a stale `lifter_mod._bundle_yaml_path` monkeypatch (pre-existing at base).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 17 — 2026-09-30

- **Commit:** `fce60fc18`
- **Architectural concern:** layering violation / dependency direction. `lca.harness.declarative.lifecycle.phase_observation` imported the infrastructure `span` function, violating harness-depends-only-on-contracts.
- **Change:** added the `SpanOpener` port in `lca/contracts/protocols/telemetry/span_opener.py`; `TracingPhaseObserver` now takes an injected opener (default no-op); both plugin composition points (`observer_tracing_provider`, `runtime_input` fixture) pass the infrastructure `span`; added tests + structural guard.
- **Files:** `lca/contracts/protocols/telemetry/span_opener.py` (new), `lca/harness/declarative/lifecycle/phase_observation.py`, 2 plugin files, `tests/harness/declarative/lifecycle/test_tracing_phase_observer.py`.
- **Shortstat:** `git show --shortstat fce60fc18` → 5 files changed, 138 insertions(+), 5 deletions(-); gross diff = 143 > 100.
- **Tests:** `uv run pytest -q tests/harness/declarative/lifecycle/test_tracing_phase_observer.py tests/architecture/test_phase_observation_seam.py -m "not real_llm" --no-cov` → **5 passed**; `test_phase_transaction_depends_on_observation_seam_not_tracing_backend` is the pre-existing stale `lca/loop/transaction.py` test.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 18 — 2026-09-30

- **Commit:** `f473a3aec` (cherry-picked from subagent branch `round-i` commit `8fb3f7435`)
- **Architectural concern:** module depth / oversized module. `lca/infrastructure/cli/services/kernel/supervisor.py` (1237 lines) mixed config parsing, state I/O, result builders, process helpers, restart decisions, and the supervisor class.
- **Change:** split into a `supervisor/` package (`types`, `config`, `state`, `results`, `process`, `decisions`, `supervisor` submodules) with an explicit re-export barrel; updated tests to patch submodule globals; added `test_supervisor_barrel.py` pinning the public surface.
- **Files:** 11 files (7 new submodules + barrel + test + test updates).
- **Shortstat:** `git show --shortstat f473a3aec` → 11 files changed, 1544 insertions(+), 1289 deletions(-); gross diff = 2833 > 100.
- **Tests:** `uv run pytest -q tests/infrastructure/cli/test_supervisor_barrel.py tests/infrastructure/cli/test_kernel_supervisor.py tests/infrastructure/cli/test_kernel_restart_report.py -m "not real_llm" --no-cov` → **46 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 19 — 2026-09-30

- **Commit:** `0f31ac638`
- **Architectural concern:** module depth / oversized module. `lca/nodes/think/decision_repair.py` (600 lines) mixed the plugin carrier, executor, pure schema validation, deterministic argument repair, and routing sentinels.
- **Change:** split into a `decision_repair/` package: `constants.py` (outcome sentinels), `schema.py` (tool-call JSON-schema matching), `repair.py` (deterministic repair mechanics), `executor.py` (plugin carrier + executor + routing), and an explicit re-export barrel.
- **Files:** `lca/nodes/think/decision_repair/{__init__,constants,schema,repair,executor}.py` (new), `lca/nodes/think/decision_repair.py` (deleted).
- **Shortstat:** `git show --shortstat 0f31ac638` → 6 files changed, 620 insertions(+), 600 deletions(-); gross diff = 1220 > 100.
- **Tests:** `uv run pytest -q tests/think/test_decision_repair_phase_plugin.py tests/observability/health/test_run_health_fold.py tests/observability/health/test_derivers/test_think_deriver.py -m "not real_llm" --no-cov` → **56 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 20 — 2026-09-30

- **Commit:** `573352239` (cherry-picked from subagent branch `round-e` commit `1461ab71b`)
- **Architectural concern:** layering violation / dependency direction. `lca.infrastructure.session.context.turn_control_reader` imported `observation_files_created` and `view_tool_fingerprint` upward from cognition.
- **Change:** moved `ControlTurnView` and the fingerprint projection into contracts (`lca/contracts/models/core/execution/{control_turn,fingerprint}.py`); `view_tool_fingerprint` now imports from contracts; `observation_files_created` is injected as a callback at the composition boundary; added `tests/architecture/test_infrastructure_session_no_cognition.py`.
- **Files:** 14 files (2 new contracts modules, 1 new structural test, reader + cognition + composition callers).
- **Shortstat:** `git show --shortstat 573352239` → 14 files changed, 343 insertions(+), 174 deletions(-); gross diff = 517 > 100.
- **Tests:** `uv run pytest -q tests/architecture/test_infrastructure_session_no_cognition.py tests/infrastructure/test_turn_control_reader.py tests/infrastructure/test_turn_control_files_created.py -m "not real_llm" --no-cov` → **13 passed** (subagent ran 54 across the full affected set).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 21 — 2026-09-30

- **Commit:** `446c3200d` (cherry-picked from subagent branch `round-f` commit `cb73130db`)
- **Architectural concern:** design pattern / duplicated logic. Three nearly identical `InMemory*HandlerRegistry` classes each re-declared `register`/`resolve` over `UniqueOperationRegistry`.
- **Change:** added `GenericInMemoryRegistry[T, TProtocol]` + `make_inmemory_registry(kind, protocol)` in `lca/infrastructure/handler/registry.py`; the three act providers now declare their registries as factory calls; public names preserved; added `tests/infrastructure/handler/test_generic_registry.py`.
- **Files:** `lca/infrastructure/handler/registry.py` + `__init__.py`, 3 act provider files, `tests/infrastructure/handler/test_generic_registry.py`.
- **Shortstat:** `git show --shortstat 446c3200d` → 6 files changed, 205 insertions(+), 69 deletions(-); gross diff = 274 > 100.
- **Tests:** `uv run pytest -q tests/infrastructure/handler/test_generic_registry.py -m "not real_llm" --no-cov` → **6 passed** (subagent ran 74 across the affected set; 3 failures pre-existing).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 22 — 2026-09-30

- **Commit:** `ba00c5a45`
- **Architectural concern:** shallow re-export shell / dead indirection. `lca/plugins/assistant/tools.py` re-exported `filter_tools_by_assistant` but had zero production consumers (only one test imported it).
- **Change:** deleted the alias; repointed the test at `lca.infrastructure.tools.assistant.filter` and moved it next to the implementation; fixed the stale docstring reference in `io.py`; added a structural guard + behavioral edge-case tests (box tools, string home path, grant interactions).
- **Files:** `lca/plugins/assistant/tools.py` (deleted), `lca/infrastructure/assistant/io.py`, `tests/infrastructure/tools/assistant/test_filter_tools.py` (moved + extended), `tests/architecture/test_no_assistant_tools_alias.py`.
- **Shortstat:** `git show --shortstat ba00c5a45` → 3 files changed, 111 insertions(+), 2 deletions(-); gross diff = 113 > 100.
- **Tests:** `uv run pytest -q tests/infrastructure/tools/assistant/test_filter_tools.py tests/architecture/test_no_assistant_tools_alias.py -m "not real_llm" --no-cov` → **33 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 23 — 2026-09-30

- **Commit:** `7d60cc10a`
- **Architectural concern:** shallow retired stub / dead compatibility shell. The ADR-0163 sibling re-export `routes.py` existed only for legacy `mock.patch` strings; no live code referenced them.
- **Change:** deleted the stub; simplified the api `__init__.py` (removed `routes` from exports); repointed docstring/comment references in `command_endpoints.py`, `diagnostics.py`, and a scenario test; added a structural guard.
- **Files:** `lca/plugins/transport/webserver/handlers/runs/api/routes.py` (deleted), `lca/plugins/transport/webserver/handlers/runs/api/__init__.py`, `command_endpoints.py`, `diagnostics.py`, 2 test files.
- **Shortstat:** `git show --shortstat 7d60cc10a` → 7 files changed, 74 insertions(+), 77 deletions(-); gross diff = 151 > 100.
- **Tests:** `uv run pytest -q tests/architecture/test_runs_api_routes_stub_retired.py -m "not real_llm" --no-cov` → **4 passed**. `test_catalog_registers_profile_route` fails on a stale `ROUTES` import (pre-existing at HEAD).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 24 — 2026-09-30

- **Commit:** `3f28556a4` (cherry-picked from subagent branch `round-j` commit `4ff8eee8f`)
- **Architectural concern:** module depth / oversized plugin. `lca/plugins/domain/assistant/catalog/plugin.py` (1397 lines) mixed Home CRUD, SOUL validation, plan-overlay parsing, manifest digest, and event emission.
- **Change:** split into a `catalog/` package (`handlers.py`, `soul.py`, `manifest.py`, `events.py`, `plan_overlay.py`, `plugin.py`, barrel `__init__.py`); public surface preserved; added a barrel-path regression test.
- **Files:** 8 files (6 new submodules + barrel + test updates).
- **Shortstat:** `git show --shortstat 3f28556a4` → 8 files changed, 1397 insertions(+), 1219 deletions(-); gross diff = 2616 > 100.
- **Tests:** `uv run pytest -q tests/plugins/assistant/test_catalog.py -m "not real_llm" --no-cov` → **87 passed** (5 digest-mismatch failures pre-existing at HEAD).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 25 — 2026-09-30

- **Commit:** `190ea3994` (cherry-picked from subagent branch `round-n` commit `2d61b5214`)
- **Architectural concern:** module depth / oversized module. `narrative_writer.py` (670 lines) mixed per-primitive section renderers, fold-chapter renderers, and the writer.
- **Change:** split into a `narrative_writer/` package (`sections.py`, `fold.py`, `writer.py`, barrel `__init__.py`); tightened 3 bare `Any` annotations to `object`; added `tests/scenario/step/test_narrative_writer_sections.py`.
- **Files:** 6 files (3 new submodules + barrel + test), 1 deleted module.
- **Shortstat:** `git show --shortstat 190ea3994` → 6 files changed, 761 insertions(+), 670 deletions(-); gross diff = 1431 > 100.
- **Tests:** `uv run pytest -q tests/scenario/step/test_narrative_writer_sections.py -m "not real_llm" --no-cov` → **3 passed** (subagent ran 61 passed / 7 pre-existing failures across the affected set).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 26 — 2026-09-30

- **Commit:** `0c3e4a630` (cherry-picked from subagent branch `round-p` commit `7ef705f78`)
- **Architectural concern:** module depth. `lca_kernel/events/registry/registry.py` (620 lines) mixed the yaml-driven catalog loading with the registry class.
- **Change:** extracted `lca_kernel/events/registry/catalog.py` (229 lines) with `EventSpec` + yaml loading; `registry.py` delegates `load` to `catalog.load_catalog`; added `tests/lca_kernel/events/test_catalog_loader.py` and `test_registry_load.py`.
- **Files:** 4 files (1 new module + 2 test files + registry updates).
- **Shortstat:** `git show --shortstat 0c3e4a630` → 4 files changed, 395 insertions(+), 193 deletions(-); gross diff = 588 > 100.
- **Tests:** `uv run pytest -q tests/lca_kernel/events/test_catalog_loader.py tests/lca_kernel/events/test_registry_load.py -m "not real_llm" --no-cov` → **13 passed**.
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 27 — 2026-09-30

- **Commit:** `575bc70f8`
- **Architectural concern:** layering violation / dependency direction. `lca.harness.observability.assemble` imported infrastructure concrete types, violating harness-depends-only-on-contracts.
- **Change:** relocated `assemble_observability`, `make_minimal_bound`, `default_policy` into `lca_kernel.runtime.observability` (the kernel composition boundary); repointed the plugin `binding.py` and three test consumers; deleted `lca/harness/observability/`; added a structural test.
- **Files:** `lca_kernel/runtime/observability.py`, `lca/plugins/transport/webserver/carrier/runs/binding.py`, `lca/harness/observability/*` (deleted), 4 test files.
- **Shortstat:** `git show --shortstat 575bc70f8` → 9 files changed, 170 insertions(+), 224 deletions(-); gross diff = 394 > 100.
- **Tests:** `uv run pytest -q tests/architecture/test_harness_observability_moved_to_kernel.py tests/lca_kernel/test_boot_events_emitted.py -m "not real_llm" --no-cov` → **7 passed** (2 boot-event failures pre-existing at HEAD `d645b6ea7`).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 28 — 2026-09-30

- **Commit:** `158200073` (cherry-picked from subagent branch `round-l` commit `9d567b314`)
- **Architectural concern:** module depth / oversized module. `lca/plugins/prompts/sections.py` (1060 lines, ~30 section classes) mixed all prompt sections in one file.
- **Change:** split into a `sections/` package (`base`, `role`, `time`, `tools`, `skills`, `task`, `text`, `context`, `teammates`, `member_status`, `evidence`, `vocal`, `plugin` + barrel); bundle `$module` updated; added a barrel-coverage test.
- **Files:** 18 files (13 new submodules + barrel + plugin + test updates), 1 deleted module.
- **Shortstat:** `git show --shortstat 158200073` → 18 files changed, 1546 insertions(+), 1063 deletions(-); gross diff = 2609 > 100.
- **Tests:** `uv run pytest -q tests/plugins/prompts/test_sections_package_barrel.py -m "not real_llm" --no-cov` → **3 passed** (subagent ran 69 passed across the affected set; remaining failures pre-existing).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 29 — 2026-09-30

- **Commit:** `bc0e80704` (cherry-picked from subagent branch `round-k` commit `65094483a`)
- **Architectural concern:** module depth / oversized module. `routes_assistants.py` (1323 lines) held nine `/v1/assistants` endpoints with inline JSON shaping.
- **Change:** split into a `routes_assistants/` package (`codecs`, `profile`, `skills`, `jobs`, `lobehub`, `router` + barrel); added `test_assistants_codecs.py` (16 codec tests).
- **Files:** 9 files (6 new submodules + barrel + test), 1 deleted module.
- **Shortstat:** `git show --shortstat bc0e80704` → 9 files changed, 1585 insertions(+), 1323 deletions(-); gross diff = 2908 > 100.
- **Tests:** `uv run pytest -q tests/plugins/transport/webserver/routes_1/test_assistants_codecs.py -m "not real_llm" --no-cov` → **16 passed** (subagent ran 96 passed / 8 pre-existing failures).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 30 — 2026-09-30

- **Commit:** `2b36fc885` (cherry-picked from subagent branch `round-o` commit `0a85d5492`)
- **Architectural concern:** module depth / oversized module. `safe_executor.py` (609 lines) mixed retry classification, evidence staging, and the executor pipeline.
- **Change:** split into a `safe_executor/` package (`retry.py`, `evidence.py`, `executor.py` + barrel); added `test_safe_executor_retry_policy.py`.
- **Files:** 5 files (2 new submodules + barrel + test), 1 renamed module.
- **Shortstat:** `git show --shortstat 2b36fc885` → 5 files changed, 335 insertions(+), 130 deletions(-); gross diff = 465 > 100.
- **Tests:** `uv run pytest -q tests/cognition/body/test_safe_executor_retry_policy.py -m "not real_llm" --no-cov` → **7 passed** (subagent ran 106 passed / 0 new failures).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 31 — 2026-09-30

- **Commit:** `b821e6bec` (cherry-picked from subagent branch `round-q` commit `455576263`)
- **Architectural concern:** retired deprecated module / layering. `lca/harness/profile/boot/boot.py` was a deprecated COMPAT shim importing infrastructure (harness→infrastructure violation).
- **Change:** moved its two surviving helpers into `lca_kernel.boot.boot`; migrated all callers onto `lca_kernel.run_kernel` / `run_resolved_kernel` / `boot_entries`; dropped `boot_*` re-exports from harness/profile; deleted the module; added a structural regression test.
- **Files:** 24 files (25 Python files migrated, 1 deleted module, 1 new structural test).
- **Shortstat:** `git show --shortstat b821e6bec` → 24 files changed, 204 insertions(+), 260 deletions(-); gross diff = 464 > 100.
- **Tests:** `uv run pytest -q tests/architecture/test_profile_boot_module_retired.py -m "not real_llm" --no-cov` → **2 passed** (subagent verified the affected-set failures are pre-existing `typesafe_sdk` ModuleNotFoundError).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.

### Round 32 — 2026-09-30

- **Commit:** `147331659`
- **Architectural concern:** stale references / dead code. The retired `lca/loop/transaction.py` (pre-kernel `PhaseExecutionTransaction`) was still referenced by two architecture tests and two READMEs; `scripts/lca-inspect-plan.py` imported two nonexistent modules.
- **Change:** rewrote the phase-observation seam test against the current lifecycle module; repointed the production-closure test at the composer runtime package; updated the loop READMEs; fixed `lca-inspect-plan.py` to use `lca_kernel.plan.plan_compile`; added a structural guard scanning production+scripts for retired module paths.
- **Files:** `tests/architecture/test_phase_observation_seam.py`, `tests/architecture/test_declarative_production_closure.py`, `tests/architecture/test_no_stale_module_references.py` (new), `scripts/lca-inspect-plan.py`, `lca/loop/README.md`, `lca/loop/control/README.md`.
- **Shortstat:** `git show --shortstat 147331659` → 6 files changed, 94 insertions(+), 19 deletions(-); gross diff = 113 > 100.
- **Tests:** `uv run pytest -q tests/architecture/test_phase_observation_seam.py tests/architecture/test_no_stale_module_references.py -m "not real_llm" --no-cov` → **5 passed** (the profile-boot rejection test in `test_declarative_production_closure.py` is pre-existing).
- **Gates:** ruff check / format --check on touched files: pass; `git diff --check`: clean; `lint-imports` and `check_package_contracts.py`: same pre-existing failures as baseline, no new ones.