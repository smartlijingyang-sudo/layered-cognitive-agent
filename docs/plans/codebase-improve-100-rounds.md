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