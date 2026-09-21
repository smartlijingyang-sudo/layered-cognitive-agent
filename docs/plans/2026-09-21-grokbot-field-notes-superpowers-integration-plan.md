# Grokbot Field Notes & Superpowers Integration Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Seamlessly inject Grokbot Field Notes operational discipline (negative boundaries, invariants in tests, anti-pattern knowledge base, automated review gates) into the Antigravity Superpowers workflow so it runs 100% automatically.

**Architecture:** Augment existing Superpowers skill templates and review gates (`.agent/AGENTS.md`, `brainstorming`, `writing-plans`, `code-reviewer`) and establish `docs/antipatterns/lca-antipatterns.md` as the SSOT for project anti-patterns. Zero changes to LCA kernel code.

**Tech Stack:** Markdown skill manifests, bash verification scripts, git.

---

### Task 1: Seed the Anti-pattern Knowledge Base

**Files:**
- Create: `docs/antipatterns/lca-antipatterns.md`

**Step 1: Write the initial catalog file**
Create `docs/antipatterns/lca-antipatterns.md` containing 6 core anti-patterns formatted strictly as:
`[Name] -> [Observed Failure] -> [Root Cause] -> [Principle / Standing Rule]`.

**Step 2: Verify file existence and structure**
Run: `head -n 30 docs/antipatterns/lca-antipatterns.md`
Expected: Title and first anti-patterns properly formatted.

**Step 3: Commit**
```bash
git add docs/antipatterns/lca-antipatterns.md
git commit -m "docs(antipatterns): seed LCA anti-pattern catalog from grokbot field notes"
```

---

### Task 2: Augment `.agent/AGENTS.md` with Negative Scoping & Test Invariants

**Files:**
- Modify: `.agent/AGENTS.md`

**Step 1: Add Core Rules 6 and 7 to `.agent/AGENTS.md`**
Inject:
- Rule 6: **Negative Scope (Does Not Own)**: Every plan task MUST declare and honor what it does NOT own. Never perform opportunistic refactors or touch unassigned modules.
- Rule 7: **Invariants in Tests**: Invariants must be asserted in automated tests (pytest/assert), never merely stated in prompts or comments.
- Update **Verification Discipline** to require verifying non-zero exit on invalid inputs.

**Step 2: Run profile check**
Run: `bash .agent/tests/check-antigravity-profile.sh`
Expected: PASS

**Step 3: Commit**
```bash
git add .agent/AGENTS.md
git commit -m "feat(agent): inject negative scope and invariant testing rules into AGENTS.md"
```

---

### Task 3: Inject `Does NOT own` and `Autopilot Ladder` into Brainstorming Skill

**Files:**
- Modify: `.agent/skills/brainstorming/SKILL.md`

**Step 1: Update design presentation section in `.agent/skills/brainstorming/SKILL.md`**
Add mandatory requirements in `Presenting the design`:
- Must state `Owns` (what this builds)
- Must state `Does NOT own` (what this explicitly does not touch)
- Must state `Autopilot Level` (`INVESTIGATE` / `DRAFT` / `AUTOPILOT`) based on blast radius.

**Step 2: Run profile test**
Run: `bash .agent/tests/run-tests.sh`
Expected: PASS

**Step 3: Commit**
```bash
git add .agent/skills/brainstorming/SKILL.md
git commit -m "feat(skills): require Owns, Does-not-own and Autopilot level in brainstorming"
```

---

### Task 4: Inject Negative Scope & Invariant Testing into Plan Writing Skill

**Files:**
- Modify: `.agent/skills/writing-plans/SKILL.md`

**Step 1: Update Task Template in `writing-plans/SKILL.md`**
In `## Task Structure`, add:
- `Does NOT own:` [Strict list of files/directories/layers this task must not touch]
- `Invariants to test:` [Specific invariants that MUST have assertions]

**Step 2: Run profile test**
Run: `bash .agent/tests/run-tests.sh`
Expected: PASS

**Step 3: Commit**
```bash
git add .agent/skills/writing-plans/SKILL.md
git commit -m "feat(skills): embed negative boundaries and test invariants into plan template"
```

---

### Task 5: Inject Boundary & Anti-pattern Guard into Code Reviewer

**Files:**
- Modify: `.agent/skills/requesting-code-review/code-reviewer.md`
- Modify: `.agent/skills/single-flow-task-execution/code-quality-reviewer-prompt.md`

**Step 1: Add Boundary & Anti-pattern Checklist to `code-reviewer.md`**
Add section `### Boundary & Anti-pattern Guard (Grokbot Field Notes)`:
- Negative boundary check (did diff touch `Does NOT own`?)
- Single source of truth check (did code duplicate calculation of derived values?)
- Tested invariants check (are invariants verified with assertions?)
- Anti-pattern check against `docs/antipatterns/lca-antipatterns.md`.

**Step 2: Run profile test**
Run: `bash .agent/tests/run-tests.sh`
Expected: PASS

**Step 3: Commit**
```bash
git add .agent/skills/requesting-code-review/code-reviewer.md .agent/skills/single-flow-task-execution/code-quality-reviewer-prompt.md
git commit -m "feat(skills): add automated boundary and antipattern checks to code-reviewer"
```

---

### Task 6: Full Suite Verification and Integration Validation

**Files:**
- Test execution across all `.agent/` and docs validation.

**Step 1: Run comprehensive tests**
Run: `bash .agent/tests/check-antigravity-profile.sh && bash .agent/tests/run-tests.sh`
Expected: All exit with code 0.

**Step 2: Update tracking**
Update `docs/plans/task.md` marking tasks completed.

**Step 3: Commit & Status Report**
```bash
git add docs/plans/task.md docs/plans/2026-09-21-grokbot-field-notes-superpowers-integration-plan.md
git commit -m "docs(plans): complete grokbot field notes superpowers integration plan"
```
