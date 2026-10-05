# Codebase Architecture Deepening Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Turn shallow modules, hypothetical seams, and leaky scans across Transport, Assistant Tools, Cron Store, and Memory ContextFiles into deep, cohesive modules backed by deterministic invariant tests.

**Architecture:** Strictly in-place deepening with clean deletion (Approach A). Coalesce micro-modules into high-leverage entry points (`RunTerminalCoordinator`, `_BaseAssistantTool.execute` template seam, `MultiAssistantCronStore` $O(1)$ index, and `contextfiles/sync.py`), removing obsolete single-file folders without retaining cross-PR compatibility shims.

**Tech Stack:** Python 3.11+, Pytest, Pydantic, Structlog, LCA Contracts & Transport/Infrastructure.

---

### Task 1: Transport Run Lifecycle & Terminalization Deepening (INV-ARCH-01, INV-ARCH-02)

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/runs/terminal/lifecycle.py`
- Delete:
  - `lca/plugins/transport/webserver/handlers/runs/terminal/outcome/outcome.py`
  - `lca/plugins/transport/webserver/handlers/runs/terminal/outcome/__init__.py`
  - `lca/plugins/transport/webserver/handlers/runs/terminal/status/status.py`
  - `lca/plugins/transport/webserver/handlers/runs/terminal/status/__init__.py`
  - `lca/plugins/transport/webserver/handlers/runs/terminal/failure/failure.py`
  - `lca/plugins/transport/webserver/handlers/runs/terminal/failure/__init__.py`
  - `lca/plugins/transport/webserver/handlers/runs/terminal/terminalizer/terminalizer.py`
  - `lca/plugins/transport/webserver/handlers/runs/terminal/terminalizer/__init__.py`
- Modify:
  - `lca/plugins/transport/webserver/carrier/runs/lifecycle/lifecycle.py`
  - `lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py`
- Test: `tests/lca_plugins/transport/webserver/test_run_terminal_coordinator.py`
- Does NOT own: `bundles/*.yaml`, `lca/contracts/`, `lca/nodes/think/` (AP-01)
- Invariants to test:
  - `INV-ARCH-01`: `terminalize()` executes terminal transition exactly once, deriving `COMPLETED` or `ERROR`, logging failure traces on error, publishing carrier terminal observation, and invoking finalizer.
  - `INV-ARCH-02`: `apply_outcome()` handles `waiting_input=True` by setting status to `WAITING_INPUT` with live handles cached, never prematurely terminalizing.

**Step 1: Write failing invariant tests**
Create `tests/lca_plugins/transport/webserver/test_run_terminal_coordinator.py` validating `RunTerminalCoordinator`:
- Test terminalize happy path (`success=True`) sets `RunLifecycleStatus.COMPLETED`.
- Test terminalize error path (`success=False`) sets `RunLifecycleStatus.ERROR` and records failure trace.
- Test `apply_outcome` with driver outcome `waiting_input=True` transitions session to `WAITING_INPUT`.

**Step 2: Run test to verify it fails**
Run: `pytest tests/lca_plugins/transport/webserver/test_run_terminal_coordinator.py -v`
Expected: FAIL (ModuleNotFoundError or cannot import `RunTerminalCoordinator`).

**Step 3: Implement `RunTerminalCoordinator` in `terminal/lifecycle.py` and update callers**
- Implement `lifecycle.py` unifying:
  - Driver & resume outcome translation (`apply_outcome`)
  - Status derivation (`derive_terminal_status`)
  - Failure trace writing (`record_failure`)
  - Terminal transition orchestration (`terminalize`)
- Update `carrier/runs/lifecycle/lifecycle.py` to use `RunTerminalCoordinator`.
- Update `terminal/registry/commands.py` import.
- Physically remove `outcome/`, `status/`, `failure/`, and `terminalizer/` subdirectories.

**Step 4: Run test to verify it passes**
Run: `pytest tests/lca_plugins/transport/webserver/test_run_terminal_coordinator.py -v`
Expected: PASS.

**Step 5: Run existing transport tests to verify zero regressions**
Run: `pytest tests/lca_plugins/transport/ -v`
Expected: PASS.

**Step 6: Commit**
```bash
git add lca/plugins/transport/webserver/ tests/lca_plugins/transport/webserver/
git commit -m "refactor(transport): deepen run lifecycle into RunTerminalCoordinator"
```

---

### Task 2: Assistant Tools Standing-Writer Seam Interception (INV-ARCH-03, INV-ARCH-04)

**Files:**
- Modify: `lca/infrastructure/tools/assistant/self_manage_tools.py`
- Test: `tests/infrastructure/tools/test_assistant_tools_standing_writer_seam.py`
- Does NOT own: `lca/contracts/models/core/execution/external_content.py` core rules, other tool suites (AP-01)
- Invariants to test:
  - `INV-ARCH-03`: All 9 mutating assistant tools (`is_mutating=True`) fail-fast at the `execute()` seam when ambient decision has `ContentOrigin.EXTERNAL`, returning an error without calling `execute_tool()`.
  - `INV-ARCH-04`: Read-only tools (`is_mutating=False`) execute normally under `ContentOrigin.EXTERNAL`.

**Step 1: Write failing invariant tests**
Create `tests/infrastructure/tools/test_assistant_tools_standing_writer_seam.py`:
- Test that executing `DeleteAssistantSkillTool`, `EditAssistantSkillTool`, `UpdateAssistantSoulTool`, etc., under `decision_scope(external_decision)` returns permission denied observation without calling underlying business logic.
- Test that executing `ListAssistantSkillsTool` and `ReadAssistantSelfConfigTool` under `decision_scope(external_decision)` succeeds.

**Step 2: Run test to verify it fails**
Run: `pytest tests/infrastructure/tools/test_assistant_tools_standing_writer_seam.py -v`
Expected: FAIL (or verify behavior before refactor to pin seam).

**Step 3: Refactor `_BaseAssistantTool` and 9 subclasses**
- In `_BaseAssistantTool`, declare `is_mutating: bool = False`.
- In `_BaseAssistantTool.execute()`:
  ```python
  async def execute(self, args: dict[str, Any]) -> Observation:
      start = time.monotonic()
      if self.is_mutating:
          refused = self._check_standing_write_permitted()
          if refused is not None:
              return self._fail(start, refused)
      return await self.execute_tool(args, start)
  ```
- Update 9 mutating tools:
  - Set `is_mutating = True`
  - Rename `execute(self, args)` -> `execute_tool(self, args, start)`
  - Delete local `self._check_standing_write_permitted()` calls.
- Update read-only tools to implement `execute_tool(self, args, start)`.

**Step 4: Run tests to verify they pass**
Run: `pytest tests/infrastructure/tools/test_assistant_tools_standing_writer_seam.py tests/infrastructure/tools/test_self_manage.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/infrastructure/tools/assistant/self_manage_tools.py tests/infrastructure/tools/test_assistant_tools_standing_writer_seam.py
git commit -m "refactor(tools): enforce standing-write checks at _BaseAssistantTool execution seam"
```

---

### Task 3: Multi-Assistant Cron Store Indexing & Encapsulation (INV-ARCH-05)

**Files:**
- Modify: `lca/domain/cron/store.py`
- Test: `tests/domain/cron/test_multi_assistant_cron_store_indexing.py`
- Does NOT own: `lca/contracts/models/cron/`, `lca/infrastructure/cron/scheduler.py` (AP-01)
- Invariants to test:
  - `INV-ARCH-05`: `MultiAssistantCronStore` resolves target store via internal `_job_to_assistant` index; mutations update the index; operations throw `CronRunConflictError` on conflicting receipt/handoff updates without touching unrelated stores.

**Step 1: Write failing invariant tests**
Create `tests/domain/cron/test_multi_assistant_cron_store_indexing.py`:
- Test job indexing: creating job under assistant A registers mapping in store.
- Test `record_handoff_runs` and `close_run_receipts` dispatch directly to indexed store without scanning assistant B.
- Test `CronRunConflictError` propagation on conflicting writes.

**Step 2: Run test to verify it fails**
Run: `pytest tests/domain/cron/test_multi_assistant_cron_store_indexing.py -v`
Expected: FAIL (missing indexed behavior assertions or methods).

**Step 3: Implement internal indexing in `MultiAssistantCronStore`**
- In `MultiAssistantCronStore`, add `_job_to_assistant: dict[str, str] = field(default_factory=dict)`.
- Implement `_resolve_store_for_job(job_id: str) -> CronStore | None`:
  - Check `_job_to_assistant`. If present, return `_stores()[asst_id]`.
  - If miss, scan once and populate `_job_to_assistant`.
- Use `_resolve_store_for_job` in `get_job`, `delete_job`, `record_handoff_runs`, `close_run_receipts`, `list_runs`.

**Step 4: Run tests to verify they pass**
Run: `pytest tests/domain/cron/test_multi_assistant_cron_store_indexing.py tests/infrastructure/cron/ -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/domain/cron/store.py tests/domain/cron/test_multi_assistant_cron_store_indexing.py
git commit -m "perf(cron): add O(1) job-to-assistant indexing to MultiAssistantCronStore"
```

---

### Task 4: Memory ContextFiles Hypothetical Seam & Layering Consolidation (INV-ARCH-06)

**Files:**
- Create: `lca/infrastructure/memory/contextfiles/sync.py`
- Delete:
  - `lca/infrastructure/memory/contextfiles/ports/file_store.py`
  - `lca/infrastructure/memory/contextfiles/adapters/disk.py`
- Modify:
  - `lca/infrastructure/memory/assistant_memory.py`
  - `lca/infrastructure/memory/contextfiles/__init__.py`
- Test: `tests/infrastructure/memory/test_contextfiles_unified_sync.py`
- Does NOT own: `MEMORY.md` markdown parsing grammar, `lca/contracts/models/memory/` (AP-01)
- Invariants to test:
  - `INV-ARCH-06`: Unified `sync.py` correctly calculates memory edit sync operations and atomicity without referencing deleted `ports/file_store.py`.

**Step 1: Write failing invariant tests**
Create `tests/infrastructure/memory/test_contextfiles_unified_sync.py`:
- Test that context file sync parses edit deltas, reconciles with active records, and replaces memory projection directly using standard file store.

**Step 2: Run test to verify it fails**
Run: `pytest tests/infrastructure/memory/test_contextfiles_unified_sync.py -v`
Expected: FAIL.

**Step 3: Consolidate sync module and remove redundant seams**
- In `contextfiles/sync.py`, unify file I/O using standard `Path` or `LocalFileStore`.
- Update `assistant_memory.py` imports and remove usage of `DiskFileStore` from `contextfiles/adapters/disk.py`.
- Delete `ports/file_store.py` and `adapters/disk.py`.

**Step 4: Run tests to verify they pass**
Run: `pytest tests/infrastructure/memory/test_contextfiles_unified_sync.py tests/infrastructure/memory/ -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/infrastructure/memory/ tests/infrastructure/memory/
git commit -m "refactor(memory): consolidate contextfiles sync and drop hypothetical file_store port"
```

---

### Task 5: Full Regression, Import Boundary Checks & Pre-push Hygiene (INV-ARCH-07)

**Files:**
- Verification only: all modified files
- Does NOT own: unrelated dirty git files

**Step 1: Check code formatting and linting**
Run: `ruff check lca/ tests/`
Expected: 0 errors.

**Step 2: Check git diff hygiene**
Run: `git diff --check`
Expected: Clean.

**Step 3: Run comprehensive regression test suite**
Run: `pytest tests/lca_plugins/transport/ tests/infrastructure/tools/ tests/domain/cron/ tests/infrastructure/memory/ -v`
Expected: 100% PASS.

**Step 4: Update task.md tracker**
Mark all tasks in `docs/plans/task.md` as Completed with concrete evidence.
