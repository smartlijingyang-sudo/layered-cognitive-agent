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