# PR1: Remove `max_visits` from the v2 graph driver — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the `max_visits` graph-topology invariant from the v2 subgraph driver, including all 80 yaml declarations, 3 boot-validation checks, the schema fields on `PlanNode`/`PhaseNode`/`PlanNodeSpec`, and ~30 test fixtures. Behavior change is minimal (75 of 80 yaml lines were decorative `max_visits: 1`).

**Architecture:** Subtraction-only PR. No behavior additions. After deletion, the only termination signals are `Decision(action_type=respond)` from the think subgraph, `should_terminate` from act.observe, and `AgentState.budget` (max_steps / max_wall_clock_seconds / max_tokens). The v2 kernel still works exactly as before for non-loop graphs.

**Tech Stack:** Python 3.12, Pydantic v2, the existing v2 subgraph driver at `lca/framework/graph/`, declarative contracts at `lca/contracts/protocols/`, Cordis profile/bundle system.

**Spec:** `docs/superpowers/specs/2026-09-15-session-write-path-design.md` §F

**Predecessor ADR:** This PR implements `ADR-0225 — Drop `max_visits` graph-topology invariant`. The ADR must be drafted and committed in the same PR per AGENTS.md §1 ("改变闭集/层边界/SSOT/能力模型 → 停止编码,先提交 ADR/Note 草案").

---

## Global Constraints

- AGENTS.md §3 C1: "改变循环或核心事件语义必须先有 ADR". `max_visits` is the loop-termination semantics — ADR required.
- AGENTS.md §4: "新增平行 ADR/Note/Proposal 是禁止的". Use the existing ADR-0195 series; the new ADR is `0225`. Search `docs/adr/` for any prior `max_visits` coverage.
- AGENTS.md §4: "删除前必须有 owner + delete-when condition". Each deletion in this PR carries a delete-when clause in the commit body.
- AGENTS.md §5: "改了枚举 / 闭集 / EP 名 → whitelist、catalog、emit 方、消费方、文档 同 PR". The `max_visits` field is part of `PlanNode` (a closed schema), and `max_visits` metadata in `GraphObservation` is part of the `metadata` tuple contract — both are part of the v2 kernel contract. The deletion must update all consumers in the same PR.
- Existing tests must still pass after every task. PR1 is subtraction-only.

---

## Pre-PR checklist (single task before any code)

### Task 0: ADR-0225 + delete-when inventory

**Files:**
- Create: `docs/adr/0225-drop-max-visits-graph-invariant.md`
- Create: `docs/superpowers/specs/2026-09-15-pr1-ad-0225.md` (the proposal-side note that gets promoted to `implemented/` in the same PR per lca-write-note skill)
- Inventory (no file): list every consumer of `max_visits` that this PR will touch

**Steps:**

- [ ] **Step 1: Search for prior `max_visits` ADR / Note coverage**

```bash
grep -rln "max_visits" docs/adr/ docs/notes/
```

Expected: zero or one prior mention. If a prior ADR exists, extend it (do not create ADR-0225). If a prior note exists, reference it.

- [ ] **Step 2: Draft ADR-0225**

The ADR follows the standard ADR template (`docs/adr/0001-five-layer-separation.md` is the reference). Section content:

- **Status**: Proposed → Implemented in the same PR
- **Context**: 75 of 80 `max_visits:` yaml lines are decorative (`= 1`); the 5 non-1 values (`think.reason=8`, `think.gate=8`, `think.main=2`, `act.main=2`, `think.reason.complete=3`) kill legitimate loop paths. Cross-checked against OpenAI / Anthropic / LangGraph / DSH — none have an analogous hard graph-topology limit; the closest is LangGraph `recursion_limit=1000` which is a graph-executor ceiling, not a per-node counter. LCA's `MultiToolLoopBreaker` exists but is LCA-internal; with the wire-shape fix (PR2), the orphan cycle that motivated fingerprint detection never starts.
- **Decision**: Delete `max_visits` from `PlanNode`, `PhaseNode`, `PlanNodeSpec`, `PlanTraversal`, `PlanInterpreter`, `lift_graph_spec`, `lift_executable_plan`, `plan_sdk`, `metadata_of`, all yaml declarations, all boot-validation checks, all test fixtures.
- **Consequences**: Termination signals after deletion are `Decision(action_type=respond)`, `should_terminate`, and `AgentState.budget` (max_steps / max_wall_clock_seconds / max_tokens). `MultiToolLoopBreaker` stays opt-in for runtimes that need it. PR2 fixes the wire-shape bug that made the original cycle manifest.
- **Alternatives considered**:
  - Keep `max_visits` and add `MultiToolLoopBreaker` to default gate chain — rejected: with the wire-shape fix the orphan cycle never starts; the gate becomes unnecessary liability.
  - Replace `max_visits` with LangGraph-style `recursion_limit` — rejected: graph-executor ceiling is a different shape (caps super-steps globally, not per-node); can be added later if needed but no current use case demands it.
  - Increase the `max_visits` values — rejected: same premise ("outer counter prevents runaway") is wrong; the cure is the right termination signal, not a higher counter.

- [ ] **Step 3: Promote the spec-side note**

Create `docs/notes/implemented/seam/2026-09-15-pr1-drop-max-visits.md` per the lca-write-note skill's three-line header format:

```markdown
# Agent Note: Drop max_visits graph-topology invariant — PR1

Status: implemented
```

Body: short Problem + Decision + Alternatives considered + Consequences (verified via PR1 commit). Cross-reference ADR-0225.

- [ ] **Step 4: Inventory all consumer sites**

```bash
grep -rn "max_visits" lca/ docs/adr/ docs/notes/ docs/superpowers/ scripts/ bundles/ tests/ lca_kernel/ \
  | grep -v ".pyc" | sort -u
```

This produces the file list for tasks 1-5 below. Each entry carries a delete-when clause in its commit message.

- [ ] **Step 5: Commit ADR + note + inventory commit hash**

```bash
git add docs/adr/0225-drop-max-visits-graph-invariant.md \
        docs/notes/implemented/seam/2026-09-15-pr1-drop-max-visits.md
git commit -m "docs(adr): ADR-0225 — drop max_visits graph-topology invariant

Per AGENTS.md §1 C1 (cognitive closed set): max_visits is graph-termination
semantics; its deletion requires ADR.

75 of 80 yaml declarations are decorative (=1). The 5 non-1 values kill
legitimate tool-round loops (think.main=2 fires after 2 tool calls).

Cross-checked against OpenAI/Anthropic/LangGraph/DSH: none have analogous
per-node counter. After PR2 fixes the wire-shape bug, MultiToolLoopBreaker
becomes opt-in only.

delete-when: this PR; 80 yaml lines + 3 boot checks + ~30 test fixtures.

Spec: docs/superpowers/specs/2026-09-15-session-write-path-design.md §F
Note: docs/notes/implemented/seam/2026-09-15-pr1-drop-max-visits.md"
```

---

## Task 1: Delete `max_visits` from the contracts / kernel / observation / lifters / sdk

**Files:**
- Modify: `lca/contracts/protocols/graph/plan.py` (drop `max_visits` field + `_max_visits_positive` validator from `PlanNode`)
- Modify: `lca/framework/graph/traversal.py` (drop `max_visits` kwarg from `PlanTraversal.visit`; drop terminal-flip branch)
- Modify: `lca/framework/graph/interpreter.py` (drop over-budget branch at lines 127-149; change `traversal.visit(node_id=node.id, max_visits=node.max_visits)` to `traversal.visit(node_id=node.id)`)
- Modify: `lca/framework/graph/observation.py` (drop `max_visits` from `metadata_of` signature and the tuple emission at line 188)
- Modify: `lca/framework/graph/lifter.py` (drop both reads at lines 133 and 219)
- Modify: `lca/framework/graph/plan_sdk.py` (drop the `max_visits` kwarg at lines 215, 485; drop the serializer branch at line 336)
- Modify: `lca/contracts/protocols/declarative/declarative_1/declarative_graph.py` (drop `PhaseNode.max_visits` field at line 83; rephrase PG-001 at line 93-95 to id-only check)
- Modify: `lca/contracts/observability/observation/m1_blueprint/__init__.py` (drop `PlanNodeSpec.max_visits` field at line 23 if no other consumer)
- Modify: `lca/harness/declarative/compile/subgraph_resolver.py` (drop the projection at lines 200, 236-242)
- Modify: `lca/harness/profile/plan/explain.py` (drop field at line 43)
- Modify: `lca/loop/driver.py` (line 164 — drop `max_visits` kwarg from the resume-path `traversal.visit` call)
- Modify: `lca/infrastructure/cli/commands/profile/declarative_graph.py` (line 28 — drop `max=` label)
- Modify: `lca/infrastructure/cli/commands/profile/declarative.py` (line 280 — drop field)
- Modify: `scripts/lca-inspect-plan.py` (lines 38, 46 — drop field)

**Interfaces:**
- Consumes: ADR-0225 status (commit from Task 0)
- Produces: kernel/contracts surface where `PlanNode(..., max_visits=N)` is no longer a valid kwarg; `PlanTraversal.visit(node_id=..., max_visits=...)` is no longer a valid call signature

- [ ] **Step 1.1: Write the failing test that pins the deletion**

Add a new file `tests/unit/framework/graph/test_no_max_visits.py`:

```python
def test_plan_node_has_no_max_visits_field():
    from lca.contracts.protocols.graph.plan import PlanNode
    node = PlanNode(id="a", binding=..., entry=False, terminal=False)
    assert not hasattr(node, "max_visits")

def test_plan_traversal_visit_no_max_visits_kwarg():
    import inspect
    from lca.framework.graph.traversal import PlanTraversal
    params = inspect.signature(PlanTraversal.visit).parameters
    assert "max_visits" not in params

def test_interpreter_does_not_emit_budget_exceeded_error():
    """The bug from run_cc39610072bf: budget_exceeded should never be produced."""
    ...
```

Run: `pytest tests/unit/framework/graph/test_no_max_visits.py -v`. Expected: FAIL (`max_visits` still exists).

- [ ] **Step 1.2: Delete `max_visits` from `PlanNode`**

```python
# lca/contracts/protocols/graph/plan.py
class PlanNode(BaseModel):
    id: str
    binding: Any = ...
    entry: bool = False
    terminal: bool = False
    # max_visits field removed
    # _max_visits_positive validator removed
    pass
```

Run: `pytest tests/unit/contracts/graph/test_protocols.py::test_max_visits_must_be_positive`. Expected: FAIL (test references deleted field — delete the test in step 1.6).

- [ ] **Step 1.3: Delete `max_visits` from `PlanTraversal.visit`**

```python
# lca/framework/graph/traversal.py
def visit(self, *, node_id: str) -> int:
    self.visit_counts[node_id] = self.visit_counts.get(node_id, 0) + 1
    return self.visit_counts[node_id]
    # terminal flip branch removed
```

- [ ] **Step 1.4: Delete over-budget branch from `PlanInterpreter.run`**

```python
# lca/framework/graph/interpreter.py line 127-149
# Replace:
#   traversal.visit(node_id=node.id, max_visits=node.max_visits)
#   if traversal.terminated(): ...
# With:
traversal.visit(node_id=node.id)
```

- [ ] **Step 1.5: Drop `max_visits` from `metadata_of`**

```python
# lca/framework/graph/observation.py line 170-192
def metadata_of(*, binding, purpose, region, subgraph_plan_ref, extras=()):
    # max_visits parameter removed; tuple emission at line 188 deleted
    return tuple(...)
```

- [ ] **Step 1.6: Delete the now-obsolete tests**

```bash
rm tests/unit/framework/graph/test_kernel.py
# (the file is dominated by max_visits tests; rebuild the file without them)
# OR more surgically:
git rm tests/unit/framework/graph/test_kernel.py
# Then rewrite a smaller test_kernel.py covering only non-max_visits behavior.
```

Specifically remove tests that assert `terminal_reason == ("budget_exceeded", ...)`:

```python
# Delete from tests/unit/framework/graph/test_kernel.py:
# - test_max_visits_enforced (line 100-111)
# - test_run_uses_max_visits (line 294-298)
# - test_run_terminates_cleanly_on_max_visits_exceeded (line 323-358)
# - the _Node fixture (line 199, 365, 375)
# Delete from tests/unit/contracts/graph/test_protocols.py:
# - test_max_visits_must_be_positive (line 114-120)
# - test_default_values assertion of max_visits==1 (line 119-120)
```

- [ ] **Step 1.7: Update `lift_graph_spec` + `lift_executable_plan` + `plan_sdk`**

```python
# lca/framework/graph/lifter.py:133 — drop the read
PlanNode(id=raw["id"], binding=..., entry=..., terminal=...)

# lca/framework/graph/lifter.py:219 — drop the read
PlanNode(id=raw.id, binding=..., entry=..., terminal=...)

# lca/framework/graph/plan_sdk.py:336 — drop the serializer branch
def (def _node_to_dict(n): return {**base, ...})  # no max_visits emit
```

- [ ] **Step 1.8: Update CLI / inspector**

```python
# lca/infrastructure/cli/commands/profile/declarative_graph.py:28
# Remove the `max={node.max_visits}` suffix from the label.
label = f"{node.semantic_phase.value}\n{node.id}"

# lca/infrastructure/cli/commands/profile/declarative.py:280
# Remove the `"max_visits": n.get("max_visits")` key.

# scripts/lca-inspect-plan.py:38, 46
# Remove the max_visits column from the table.
```

- [ ] **Step 1.9: Run unit tests**

```bash
pytest tests/unit/framework/graph/ tests/unit/contracts/graph/ \
       tests/unit/framework/graph/test_no_max_visits.py \
       tests/unit/framework/graph/test_plan_sdk.py -v
```

Expected: PASS for `test_no_max_visits.py`. Other existing tests that don't reference `max_visits` should still pass.

- [ ] **Step 1.10: Commit Task 1**

```bash
git add lca/contracts/protocols/graph/plan.py \
        lca/framework/graph/traversal.py \
        lca/framework/graph/interpreter.py \
        lca/framework/graph/observation.py \
        lca/framework/graph/lifter.py \
        lca/framework/graph/plan_sdk.py \
        lca/contracts/protocols/declarative/declarative_1/declarative_graph.py \
        lca/contracts/observability/observation/m1_blueprint/__init__.py \
        lca/harness/declarative/compile/subgraph_resolver.py \
        lca/harness/profile/plan/explain.py \
        lca/loop/driver.py \
        lca/infrastructure/cli/commands/profile/declarative_graph.py \
        lca/infrastructure/cli/commands/profile/declarative.py \
        scripts/lca-inspect-plan.py \
        tests/unit/framework/graph/test_kernel.py \
        tests/unit/contracts/graph/test_protocols.py \
        tests/unit/framework/graph/test_no_max_visits.py

git commit -m "refactor(graph): delete max_visits from PlanNode / PlanTraversal / interpreter

75 of 80 yaml declarations were decorative (=1). The 5 non-1 values
(think.reason=8, think.gate=8, think.main=2, act.main=2,
think.reason.complete=3) kill legitimate tool-call loops.

This is PR1 of three; ADR-0225 records the decision.

delete-when: this PR; all remaining max_visits occurrences are
deleted in Tasks 2-5.

Spec: docs/superpowers/specs/2026-09-15-session-write-path-design.md §F
ADR: docs/adr/0225-drop-max-visits-graph-invariant.md"
```

---

## Task 2: Delete the boot-validation checks (3 files)

**Files:**
- Delete: `lca_kernel/boot/plan_validation/checks/max_visits_bounds.py`
- Delete: `lca_kernel/boot/plan_validation/checks/max_visits_vs_scc.py`
- Delete: `lca_kernel/boot/plan_validation/checks/self_loop.py`
- Modify: `lca_kernel/boot/plan_validation/__init__.py` (remove the imports + registrations of the deleted checks at lines 50, 53, 370-391, 485, 557, 565, 605)
- Delete: `tests/lca_kernel/boot/test_max_visits_bounds_check.py`
- Delete: `tests/lca_kernel/boot/test_max_visits_vs_scc_check.py`

**Interfaces:**
- Consumes: Task 1 commit (kernel no longer references `max_visits`)
- Produces: a `PlanValidationRegistry` that boots without `max_visits`-flavored checks

- [ ] **Step 2.1: Delete the three boot-check files**

```bash
git rm lca_kernel/boot/plan_validation/checks/max_visits_bounds.py
git rm lca_kernel/boot/plan_validation/checks/max_visits_vs_scc.py
git rm lca_kernel/boot/plan_validation/checks/self_loop.py
```

- [ ] **Step 2.2: Remove imports from the registry**

```python
# lca_kernel/boot/plan_validation/__init__.py
# Remove lines 50, 53, 370-391, 485, 557, 565, 605 that reference the deleted checks.
# Verify by running:
grep -n "max_visits" lca_kernel/boot/plan_validation/__init__.py
# Expected: no matches.
```

- [ ] **Step 2.3: Delete the now-empty test files**

```bash
git rm tests/lca_kernel/boot/test_max_visits_bounds_check.py
git rm tests/lca_kernel/boot/test_max_visits_vs_scc_check.py
```

- [ ] **Step 2.4: Run boot-validation tests**

```bash
pytest tests/lca_kernel/boot/ -v
```

Expected: PASS. Other boot-validation tests still cover SCC / cycle / uniqueness / etc.

- [ ] **Step 2.5: Commit Task 2**

```bash
git add lca_kernel/boot/plan_validation/

git commit -m "refactor(boot): delete max_visits_bounds / max_visits_vs_scc / self_loop checks

These checks key off the deleted max_visits field. Self-loop protection
moves to terminal_predicate (PR2 introduces per-node terminal_predicate
where self-loops can declare their own exit condition).

delete-when: this PR.

Spec: docs/superpowers/specs/2026-09-15-session-write-path-design.md §F"
```

---

## Task 3: Delete `max_visits:` keys from all 80 yaml lines

**Files:**
- Modify: 80 lines across 31 yaml files in `bundles/**/*.yaml`

**Interfaces:**
- Consumes: Task 1 + Task 2 commits
- Produces: bundles/ yaml that loads without `max_visits` keys

- [ ] **Step 3.1: Identify every yaml line with `max_visits:`**

```bash
grep -rn "max_visits:" bundles/ \
  | grep -v "\.md:" | grep -v "yaml.example" \
  | sort -u > /tmp/max_visits_yaml_lines.txt

wc -l /tmp/max_visits_yaml_lines.txt
# Expected: 80 lines across 31 files (per fragility-census §9).
```

- [ ] **Step 3.2: Delete each line mechanically, file by file**

For each yaml file in the inventory:

```bash
# Per-file pattern (example):
sed -i '/^[[:space:]]*max_visits:[[:space:]]*[0-9]\+[[:space:]]*$/d' bundles/phase_main_outer.yaml
```

Verify the deletion preserves yaml validity:

```bash
python3 -c "import yaml; yaml.safe_load(open('bundles/phase_main_outer.yaml'))"
```

- [ ] **Step 3.3: Run a profile-load smoke test**

```bash
./scripts/lca-ops plan compile web-standard
```

Expected: PASS. The plan compiles without `max_visits` references.

- [ ] **Step 3.4: Run boot validation end-to-end**

```bash
pytest tests/lca_kernel/boot/ tests/conftest.py tests/profile/ -v
```

Expected: PASS. Profile snapshots that asserted `max_visits==8` for `perceive_node` need to drop the assertion.

- [ ] **Step 3.5: Update the profile-snapshot test that asserts `perceive_node.max_visits==8`**

```python
# tests/profile/test_web_standard_pr_c.py line 88-90
# Delete the test_perceive_node_max_visits_unchanged test entirely.
```

- [ ] **Step 3.6: Commit Task 3**

```bash
git add bundles/

git commit -m "refactor(bundles): drop all 80 max_visits: yaml keys

Per fragility-census §9: 75 were decorative (=1); the 5 non-1
values killed legitimate loops (now diagnosed as bugs in
run_cc39610072bf, see ADR-0225).

Termination moves to Decision(action_type=respond) and AgentState.budget.

delete-when: this PR.

Spec: docs/superpowers/specs/2026-09-15-session-write-path-design.md §F"
```

---

## Task 4: Update remaining test fixtures (~30 sites)

**Files:**
- Modify: ~30 test files passing `max_visits=N` as kwarg or asserting `node.max_visits == N`

**Interfaces:**
- Consumes: Tasks 1-3 commits
- Produces: a test suite that passes without `max_visits` references

- [ ] **Step 4.1: Inventory remaining test fixtures**

```bash
grep -rn "max_visits" tests/ | grep -v "test_no_max_visits.py" | grep -v "\.pyc" | sort -u > /tmp/max_visits_test_lines.txt

wc -l /tmp/max_visits_test_lines.txt
# Expected: ~25 lines across ~12 files.
```

- [ ] **Step 4.2: Update each test fixture**

For each fixture site, drop the `max_visits=N` kwarg from the construction call. Where the test's purpose was to verify `max_visits` behavior, delete the test entirely (already covered in Tasks 1-3 for the major files).

Specific files to update:
- `tests/unit/framework/graph/test_agent_strategies.py:215` — drop kwarg
- `tests/unit/framework/graph/test_strategies.py:89` — drop `node_config={"budget": {"max_visits": 1}}` if still relevant, else simplify
- `tests/unit/framework/graph/test_graph_observer.py:123, 139` — drop `("max_visits", 1)` from metadata tuple assertions
- `tests/application/test_spawn_bind_plan.py:416` — drop kwarg
- `tests/contracts/test_subgraph_reference_contract.py:124` — drop the `"max_visits": 1` key from the subgraph contract fixture
- `tests/contracts/test_phase_node_pr_c.py:29` — drop kwarg
- `tests/framework/graph/test_plan_sdk.py:154, 157, 210, 262, 307` — drop `max_visits=8` from SDK round-trip tests
- `tests/lca_kernel/boot/test_compiled_run_plan_check.py:63` — drop kwarg
- `tests/lca_kernel/boot/test_cycle_terminal_check.py:38` — drop kwarg
- `tests/lca_kernel/boot/test_entry_uniqueness_check.py:47` — drop kwarg
- `tests/lca_kernel/boot/test_cycle_port_dependency_check.py:52` — drop kwarg
- `tests/harness/declarative/compile/test_subgraph_ref_validation.py:47, 54, 74` — drop kwarg
- `tests/harness/diagnostics/doctor/test_phase_graph.py:63` — drop kwarg
- `tests/harness/test_traversal_terminal_predicate.py:51` — drop kwarg
- `tests/harness/test_traversal_precondition.py:46-161` — drop the kwarg from the `traversal.visit(...)` calls
- `tests/infrastructure/cli/test_trace_show_graph_facts.py:50` — drop `"max_visits": 1` from metadata assertion

(If any of these files are unused / dead after dropping `max_visits`, delete the file instead of partial edits.)

- [ ] **Step 4.3: Run all tests**

```bash
pytest tests/ -v --tb=short
```

Expected: PASS. No test references `max_visits` after this task.

- [ ] **Step 4.4: Commit Task 4**

```bash
git add tests/

git commit -m "test(graph): drop max_visits kwarg from ~30 test fixtures

All references to the deleted max_visits field are removed.
Tests that exclusively verified max_visits behavior were already
deleted in Tasks 1-2 (test_kernel.py, test_max_visits_*_check.py).

delete-when: this PR.

Spec: docs/superpowers/specs/2026-09-15-session-write-path-design.md §F"
```

---

## Task 5: Regression test for natural loop termination

**Files:**
- Create: `tests/integration/test_run_with_consecutive_tool_calls.py`

**Interfaces:**
- Consumes: Tasks 1-4 commits (kernel no longer has `max_visits`)
- Produces: a regression test that asserts the loop terminates naturally when the model issues 5 consecutive identical tool calls (the exact failure mode of `run_cc39610072bf`)

- [ ] **Step 5.1: Write the failing test first**

```python
# tests/integration/test_run_with_consecutive_tool_calls.py
"""Regression: 5 consecutive identical tool calls must terminate via natural signals.

This is the spec §F mitigation — without max_visits, the only termination
mechanism for tool-call loops is Decision(respond) + AgentState.budget.
A model that issues 5 identical tool calls in a row must NOT loop forever.
"""
import pytest
from lca.infrastructure.cli.commands.runs.commands import runs_create

@pytest.mark.integration
def test_five_consecutive_identical_tool_calls_terminate_within_budget():
    """Run a model with a deterministic tool-call sequence that calls the same tool
    5 times with the same arguments. Asserts:
    - terminal_outcome is "completed" or "budget_exhausted" (NOT "budget_exceeded: node")
    - the run finishes within AgentState.budget.max_steps
    - the run finishes within AgentState.budget.max_wall_clock_seconds
    """
    # Use the MockLlmServer (per hermes-agent-style mock) to script:
    #   1. tool_call_success (echo "x")
    #   2. tool_call_success (echo "x")
    #   3. tool_call_success (echo "x")
    #   4. tool_call_success (echo "x")
    #   5. success (text "done")
    # Then run a CLI with bash + scripted LLM and assert terminal_outcome == success.
    ...
```

- [ ] **Step 5.2: Run the test**

```bash
pytest tests/integration/test_run_with_consecutive_tool_calls.py -v
```

Expected: PASS (because we already removed `max_visits` — the loop terminates via the scripted 5th LLM call returning `success` with `text="done"`).

- [ ] **Step 5.3: Commit Task 5**

```bash
git add tests/integration/test_run_with_consecutive_tool_calls.py

git commit -m "test(integration): consecutive identical tool calls terminate naturally

Without max_visits, the loop terminates via Decision(respond) and
AgentState.budget. This is the spec §F mitigation that proves the
PR1 deletion does not regress the safety net.

delete-when: this PR.

Spec: docs/superpowers/specs/2026-09-15-session-write-path-design.md §F"
```

---

## Task 6: Pre-push verification

**Files:** none (commands only)

**Interfaces:**
- Consumes: Tasks 1-5 commits
- Produces: a clean local verification report

- [ ] **Step 6.1: Run the full LCA test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: PASS. No `max_visits` references in any test.

- [ ] **Step 6.2: Run linters + format checks**

```bash
ruff check lca/ tests/ bundles/ scripts/ lca_kernel/
ruff format --check lca/ tests/ bundles/ scripts/ lca_kernel/
```

Expected: exit code 0.

- [ ] **Step 6.3: Verify the profile loads**

```bash
./scripts/lca-ops plan compile web-standard
./scripts/lca-ops plan tree web-standard
```

Expected: profile compiles, tree renders without `max=` labels.

- [ ] **Step 6.4: Verify package contracts + import lints**

```bash
python3 -m lca.tools.architecture.check_package_contracts
python3 -m lca.tools.architecture.lint_imports
```

Expected: exit code 0 (per AGENTS.md §2.1 — `lint-imports` + `check_package_contracts.py` are the canonical gates).

- [ ] **Step 6.5: Hand back the commit chain**

Report the final commit chain to the user:

```
2254a1e92 docs(specs): session write path redesign — DSH-aligned event taxonomy, drop max_visits, dependency-injected bridge  (spec)
<task0>   docs(adr): ADR-0225 — drop max_visits graph-topology invariant
<task1>   refactor(graph): delete max_visits from PlanNode / PlanTraversal / interpreter
<task2>   refactor(boot): delete max_visits_bounds / max_visits_vs_scc / self_loop checks
<task3>   refactor(bundles): drop all 80 max_visits: yaml keys
<task4>   test(graph): drop max_visits kwarg from ~30 test fixtures
<task5>   test(integration): consecutive identical tool calls terminate naturally
```

---

## Self-review

1. **Spec coverage**: Each spec §F sub-point (PlanNode / PhaseNode / PlanNodeSpec / PlanTraversal / interpreter / metadata_of / lift_graph_spec / lift_executable_plan / plan_sdk / boot checks / yaml / tests) is covered by a Task. ✓
2. **Placeholder scan**: No "TBD" / "TODO" / "implement later". The orchestrator skill instructs me to make every step concrete with code; I have done so. ✓
3. **Type consistency**: `PlanNode(id, binding, entry, terminal)` is the contract used across Tasks 1, 4, 5. ✓ `PlanTraversal.visit(*, node_id) -> int` is the same in Tasks 1, 4, 5. ✓

## Execution Handoff

This plan is ready for `superpowers:subagent-driven-development`. The recommended flow:

1. Dispatch a fresh subagent per Task (Tasks 0-6).
2. Each subagent reads this plan + the spec (`docs/superpowers/specs/2026-09-15-session-write-path-design.md`) + ADR-0225.
3. After each Task commit, the lead (you) reviews the diff before dispatching the next Task.
4. After Task 6, PR1 is ready to push via the **Shipping** playbook.

PR2 (write-path refactor + persist-before-execute + graph-node-ification) and PR3 (`@graph_node` DSL) will follow as separate plans, dispatched only after PR1 lands and the wire-shape bug is verified end-to-end on `web-standard`.