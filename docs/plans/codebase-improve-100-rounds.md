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