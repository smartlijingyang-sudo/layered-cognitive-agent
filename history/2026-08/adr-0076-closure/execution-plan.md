# ADR 74/75 Declarative Cutover Execution Plan

## Current Status

**Completed (Tasks 1-5 Part 1):**
- ✅ Task 1: Characterization baseline locked
- ✅ Task 2: PhaseRunCursor + interpreter resume
- ✅ Task 3: DeclarativeRunOutcome with typed errors
- ✅ Task 4: DeclarativeRuntimeDriver.resume() integration
- ✅ Task 5 Part 1: Control contribution executors (10 executors created)

**In Progress:**
- 🔄 Task 5 Part 2: Legacy cleanup and test fixes
  - Issue: `test_act_budget_exhausted` failing

**Remaining:**
- ⏳ Task 6: Delete legacy runtime, v1 composer fallback, dual write
- ⏳ Task 7: Effect idempotency, recovery graph, plan revision
- ⏳ Task 8: ADR status updates and final gates

---

## Task 5 Part 2: Complete Control Contributions Migration

### 5.1 Fix Failing Test

**Problem:** `test_act_budget_exhausted` expects EXHAUSTED but gets ALLOW

**Root Cause Analysis Needed:**
- Check `Budget.exceeded()` implementation
- Verify test setup correctly creates exhausted budget state
- Ensure `ActBudgetExecutor` properly checks budget state

**Action:**
```bash
# Investigate Budget.exceeded() logic
grep -n "def exceeded" lca/contracts/models/core/budget.py

# Check test setup
cat tests/declarative/test_control_contributions.py::test_act_budget_exhausted

# Run test with verbose output
uv run pytest tests/declarative/test_control_contributions.py::test_act_budget_exhausted -xvs
```

**Fix:** Adjust executor logic or test setup to ensure correct verdict

### 5.2 Delete Legacy Control Policies

**Files to Delete:**
- `lca/layer2_runtime/control_policies.py`
- `tests/layer2_runtime/test_control_policies.py`

**Action:**
```bash
git rm lca/layer2_runtime/control_policies.py
git rm tests/layer2_runtime/test_control_policies.py
```

### 5.3 Clean Up runtime_loop.py

**Remove Imports (L48-58):**
```python
# DELETE these lines:
from lca.runtime.control_policies import (
    ControlPolicyContext,
    DefaultControlPolicyEngine,
)
from lca.runtime.control_runtime import (
    ControlEvaluation,
    ControlSelection,
    ControlVerdictKind,
    aggregate_control_verdicts,
    select_control_entries,
)
```

**Remove Constructor Parameter (L89):**
```python
# DELETE:
control_policies: DefaultControlPolicyEngine | None = None,
```

**Remove Initialization (L105-107):**
```python
# DELETE:
self.control_policies = (
    control_policies if control_policies is not None else DefaultControlPolicyEngine()
)
```

**Remove Methods:**
- `select_control()` (L185-189)
- `evaluate_control()` (L191-215)
- `_finish_control_stop()` (L357-367)

**Remove Calls in _loop() (L228-320):**
- Remove all `self.evaluate_control(...)` calls
- Remove all `if _must_stop(...)` blocks
- Remove all `await self._finish_control_stop(...)` calls

### 5.4 Update __init__.py Re-exports

**File:** `lca/layer2_runtime/__init__.py`

**Action:** Remove any re-exports of `control_policies` symbols

### 5.5 Run Full Test Suite

```bash
uv run pytest tests/declarative/ -v
uv run pytest tests/layer2_runtime/ -v
uv run pytest tests/architecture/test_new_architecture_closure.py -v
```

**Expected:** All tests pass except environmental failures (read-only filesystem)

### 5.6 Commit

```bash
git add -A
git commit -m "feat(adr-074): complete control contributions migration

- Remove DefaultControlPolicyEngine and legacy control runtime
- Clean up runtime_loop.py control policy references
- Delete obsolete test_control_policies.py
- Update __init__.py re-exports
- All control verdicts now handled by phase contributions

Completes Task 5 of ADR 74/75 declarative cutover plan."
```

---

## Task 6: Delete Legacy Runtime and v1 Composer Fallback

### 6.1 Remove _loop() Method

**File:** `lca/layer2_runtime/runtime_loop.py`

**Delete Entire Method:** `_loop()` (L255-331)

**Replace Calls:**
- `run()` method: Replace `return await self._loop(state, max_steps)` with delegation to declarative driver
- `resume()` method: Already delegates to declarative driver (Task 4), verify no fallback

### 6.2 Remove Checkpoint Methods

**Delete Methods:**
- `_checkpoint()` (L371-393)
- `_finish_control_stop()` (L395-410)

### 6.3 Remove Helper Functions

**Delete Functions (L370-430):**
- `_is_blocking()`
- `_must_stop()`
- `_control_stop_decision()`
- `_control_denied_observation()`
- `_drain_newly_activated()`

### 6.4 Update plan_binding.py

**File:** `lca/plugins/composer/plan_binding.py`

**Remove v1 Fallback Logic (L158-164):**
```python
# DELETE this else branch:
else:
    # v1 fallback candidates
    candidates = (
        ("composer.brain", "composer.body", "composer.perceive")
        if not plan.is_declarative
        else ("composer.team",)
    )
```

**Replace With:**
```python
# Fail-closed: require explicit declarative bindings
raise BindPlanError(
    f"Non-declarative plan {plan.plan_ref} has no composer bindings. "
    "All production plans must use ADR-0075 declarative phase graph."
)
```

### 6.5 Delete Dual Write Infrastructure

**Files to Delete:**
- `lca/harness/command/dual_write.py`
- `tests/harness/test_dual_write.py`

**Action:**
```bash
git rm lca/harness/command/dual_write.py
git rm tests/harness/test_dual_write.py
```

### 6.6 Create Architecture Closure Tests

**New File:** `tests/architecture/test_declarative_production_closure.py`

**Tests to Add:**
1. `test_no_legacy_loop_in_runtime()` - Verify `_loop()` removed
2. `test_no_legacy_control_policies()` - Verify `control_policies.py` removed
3. `test_no_v1_composer_fallback()` - Verify `plan_binding.py` v1 logic removed
4. `test_no_dual_write()` - Verify dual write removed
5. `test_all_runs_use_declarative_driver()` - Verify `run()` always uses driver

### 6.7 Run Tests and Commit

```bash
uv run pytest tests/architecture/ -v
uv run pytest tests/declarative/ -v
uv run pytest tests/layer2_runtime/ -v

git add -A
git commit -m "refactor(adr-075): delete legacy runtime and v1 composer fallback

- Remove _loop(), _checkpoint(), _finish_control_stop() from runtime_loop.py
- Remove legacy control helper functions
- Delete v1 composer fallback from plan_binding.py (fail-closed)
- Delete dual_write.py and tests
- Add architecture closure tests to prevent regression

Completes Task 6 of ADR 74/75 declarative cutover plan."
```

---

## Task 7: Effect Idempotency and Recovery

### 7.1 Implement Idempotency Claim Store

**File:** `lca/layer2_runtime/effect_idempotency.py` (NEW)

**Implementation:**
```python
@dataclass
class EffectClaimStore:
    """Track effect execution claims to ensure idempotency."""
    
    _store: dict[str, EffectReceipt] = field(default_factory=dict)
    
    def claim(self, idempotency_key: str) -> EffectReceipt | None:
        """Return existing receipt if already claimed, else None."""
        return self._store.get(idempotency_key)
    
    def record(self, idempotency_key: str, receipt: EffectReceipt) -> None:
        """Record completed effect execution."""
        self._store[idempotency_key] = receipt
```

**Integration:**
- Add to `DeclarativeRuntimeDriver` constructor
- Use in effect gateway to check claim before execution
- Return existing receipt if already claimed

### 7.2 Implement Recovery Profile

**File:** `profiles/web-standard-recovery.yaml` (NEW)

**Content:**
```yaml
# Recovery profile with bounded retry loops
phase_graph:
  nodes:
    - id: perceive.main
      semantic_phase: perceive
      terminal: false
    - id: think.main
      semantic_phase: think
      terminal: false
    - id: act.main
      semantic_phase: act
      terminal: false
    - id: reflect.main
      semantic_phase: reflect
      terminal: false
    - id: remember.main
      semantic_phase: remember
      terminal: false
    - id: stop.main
      semantic_phase: stop
      terminal: true
  
  edges:
    - source: perceive.main
      target: think.main
      when: "true"
    - source: think.main
      target: act.main
      when: "result.should_act"
    - source: act.main
      target: reflect.main
      when: "true"
    - source: reflect.main
      target: think.main
      when: "result.needs_correction"
      loop:
        max_iterations: 2  # Bounded recovery loop
    - source: reflect.main
      target: remember.main
      when: "not result.needs_correction"
    - source: remember.main
      target: stop.main
      when: "true"
    - source: think.main
      target: stop.main
      when: "not result.should_act"
```

### 7.3 Implement Plan Revision Safe Boundary

**File:** `lca/harness/declarative/plan_revision.py` (NEW)

**Implementation:**
- Add plan versioning to `CompiledRunPlan`
- Check plan version at each phase boundary
- Only adopt new plan at safe boundaries (after reflect, before perceive)

### 7.4 E2E Tests

**New File:** `tests/e2e/test_declarative_long_horizon_recovery.py`

**Tests:**
1. `test_resume_after_crash_does_not_reissue_effect()` - Verify idempotency
2. `test_recovery_profile_retries_within_budget()` - Verify bounded recovery
3. `test_plan_revision_adopted_at_safe_boundary()` - Verify safe boundary

**Run:**
```bash
uv run pytest tests/e2e/test_declarative_long_horizon_recovery.py -v
```

### 7.5 Commit

```bash
git add -A
git commit -m "feat(adr-075): implement effect idempotency and bounded recovery

- Add EffectClaimStore for idempotent effect execution
- Create web-standard-recovery.yaml with bounded retry loops
- Implement plan revision safe boundary logic
- Add E2E tests for long-horizon recovery scenarios

Completes Task 7 of ADR 74/75 declarative cutover plan."
```

---

## Task 8: ADR Status Updates and Final Gates

### 8.1 Update ADR-0075 Status

**File:** `docs/adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md`

**Changes:**
- Update status: `Proposed` → `Accepted`
- Update implementation section to reference completed work
- Add "Implementation Completed" note with commit references

### 8.2 Update ADR-0074 Tracker

**File:** `docs/plans/adr-0074-plugin-everything-tracker.md`

**Changes:**
- Mark all items as completed
- Add final verification date
- Reference ADR-0075 completion

### 8.3 Update ADR README

**File:** `docs/adr/README.md`

**Changes:**
- Update ADR-0075 status to `Accepted`

### 8.4 Run Validation Scripts

```bash
# Check ADR supervision
uv run python scripts/check_adr_supervision.py

# Verify markdown links
uv run python scripts/verify_md_links.py docs/adr/

# Check documentation budgets
uv run python scripts/verify_doc_budgets.py

# Run full test suite
uv run pytest tests/ -v --tb=short

# Check imports
uv run lint-imports

# Type check
uv run mypy lca/

# Check code quality
uv run vulture lca --min-confidence 80
uv run ruff check .
```

**Expected:** All checks pass

### 8.5 Commit Documentation Updates

```bash
git add -A
git commit -m "docs(adr-075): mark ADR as accepted after complete implementation

- Update ADR-0075 status to Accepted
- Update ADR-0074 tracker with completion date
- Update ADR README with new status
- All validation scripts pass

Completes Task 8 of ADR 74/75 declarative cutover plan.
All 8 tasks now complete."
```

---

## Final Verification Checklist

### Code Quality Gates
- [ ] All tests pass (`uv run pytest`)
- [ ] No import violations (`uv run lint-imports`)
- [ ] Type checking passes (`uv run mypy lca/`)
- [ ] No dead code (`uv run vulture lca --min-confidence 80`)
- [ ] Code style compliant (`uv run ruff check .`)

### Architecture Gates
- [ ] No `_loop()` references in production code
- [ ] No `control_policies.py` references
- [ ] No v1 composer fallback in `plan_binding.py`
- [ ] No dual write infrastructure
- [ ] All runs use declarative driver

### Functional Gates
- [ ] Default profile runs via declarative driver
- [ ] Resume uses `PhaseRunCursor` and declarative driver
- [ ] Control verdicts handled by phase contributions
- [ ] Effect idempotency enforced
- [ ] Recovery profiles work correctly
- [ ] Plan revisions respect safe boundaries

### Documentation Gates
- [ ] ADR-0075 status is `Accepted`
- [ ] ADR-0074 tracker shows completion
- [ ] All markdown links valid
- [ ] Documentation budgets not exceeded

---

## Execution Strategy

**Approach:** Sequential task completion with validation at each step

**Methodology:**
1. Fix current failing test (Task 5 Part 2)
2. Complete legacy cleanup (Task 5 Part 2)
3. Delete legacy runtime (Task 6)
4. Implement idempotency and recovery (Task 7)
5. Update documentation (Task 8)
6. Final verification and commit

**Testing Strategy:**
- Run affected tests after each major change
- Run full test suite before each commit
- Use `-x` flag to stop on first failure
- Verify architecture closure tests pass

**Risk Mitigation:**
- Investigate failing test before proceeding
- Verify each deletion doesn't break dependencies
- Ensure all imports updated after deletions
- Run full test suite after each task completion

---

## Commit Sequence

1. `feat(adr-074): complete control contributions migration` (Task 5 Part 2)
2. `refactor(adr-075): delete legacy runtime and v1 composer fallback` (Task 6)
3. `feat(adr-075): implement effect idempotency and bounded recovery` (Task 7)
4. `docs(adr-075): mark ADR as accepted after complete implementation` (Task 8)

**Total:** 4 commits to complete the entire plan

---

## Time Estimate

- Task 5 Part 2: 1-2 hours (fix test, cleanup, verify)
- Task 6: 2-3 hours (delete legacy code, update bindings, tests)
- Task 7: 3-4 hours (implement idempotency, recovery, tests)
- Task 8: 1-2 hours (documentation, validation, final commit)

**Total:** 7-11 hours

---

## Notes

- Environmental test failures (read-only filesystem) are expected and can be ignored
- Focus on functional correctness over test count
- Each commit should be independently testable
- Architecture closure tests prevent regression
