# Grokbot Field Notes & Superpowers Seamless Integration Design

> **Document:** Design Specification  
> **Date:** 2026-09-21  
> **Status:** Approved  
> **Reference:** [grokbot-analysis.md](file:///home/lichao/.gemini/antigravity-cli/brain/a2cfce98-c1a3-4c67-9cec-97a87a333013/grokbot-analysis.md) & [grokbot-field-notes-analysis.md](file:///home/lichao/.gemini/antigravity-cli/brain/8b78ad7a-d210-47da-b88b-abf8cd883594/grokbot-field-notes-analysis.md)

---

## 1. Executive Summary & Philosophy

This design integrates the operational discipline and anti-pattern guardrails from xAI Grok Bot team's 72-hour live-stream (`grokbot-field-notes`) directly into the local Antigravity **Superpowers workflow** (`brainstorming` → `writing-plans` → `single-flow-task-execution` → `verification`).

### The Core Paradigm Shift
- **Superpower** provides the **temporal workflow (how to move forward)**: single-flow execution, red-green TDD, review checkpoints.
- **Grokbot Field Notes** provides the **operational discipline (boundaries & defenses)**: "Does not own", "Verification is the job", "Invariants in tests", "Principle not incident".
- **Goal:** Zero extra mental overhead for the user. When the user initiates standard Superpower workflows, Grokbot guardrails are triggered and enforced **100% automatically** across all phases.

---

## 2. Boundaries (Owns & Does NOT Own)

### Owns (In Scope)
1. **Core Antigravity Rules**: Enhancing `.agent/AGENTS.md` with negative scoping and machine-verifiable invariant rules.
2. **Brainstorming Template**: Injecting `Owns`, `Does NOT own`, and `Autopilot Ladder` definitions into `.agent/skills/brainstorming/SKILL.md`.
3. **Plan Writing Template**: Injecting `Does NOT own` and `Invariants tested` sections into `.agent/skills/writing-plans/SKILL.md`.
4. **Automated Review Checklist**: Injecting Boundary Guard and SSOT checks into `.agent/skills/requesting-code-review/code-reviewer.md` and `.agent/skills/single-flow-task-execution/`.
5. **Anti-pattern Knowledge Base**: Creating `docs/antipatterns/lca-antipatterns.md` with an initial catalog of 6 core anti-patterns derived from Grokbot failures and LCA lessons.

### Does NOT Own (Strictly Out of Scope)
- No modifications to LCA runtime kernel code (`lca/`, `lca_kernel/`, `contracts/`).
- No creation of parallel coding skills (e.g. no `grok-coder` or parallel execution framework).
- No alterations to single-flow execution semantics (strictly maintaining 1 task at a time).

---

## 3. Four Automated Integration Seams

```
[User Request] 
      │
      ▼
1. Brainstorming Phase (.agent/skills/brainstorming/)
      • Auto-generates: Owns, Does NOT own, Autopilot Level
      │
      ▼
2. Plan Writing Phase (.agent/skills/writing-plans/)
      • Auto-embeds per task:
        - Task-level "Does NOT own" (files/layers forbidden to touch)
        - "Invariants tested" (assertions that MUST be present in test files)
      │
      ▼
3. Single-Flow Task Execution (.agent/skills/single-flow-task-execution/)
      • Task completed → triggers code-reviewer (.agent/skills/requesting-code-review/)
      • Reviewer Checklist automatically audits:
        [ ] Negative Scope: Did commit touch anything in "Does NOT own"? (Critical)
        [ ] SSOT: Did code duplicate calculation of any derived values?
        [ ] Invariant Tests: Are invariants tested with actual assertions?
        [ ] Anti-pattern: Does it violate docs/antipatterns/lca-antipatterns.md?
      │
      ▼
4. Post-Mortem & Debugging (.agent/skills/systematic-debugging/)
      • On bug resolution, Phase 4 (Prevent) prompts:
        "Abstract the principle, delete the story" → append rule to docs/antipatterns/
```

---

## 4. Detailed Component Specifications

### 4.1 `.agent/AGENTS.md` Augmentation
Add two foundational standing rules to `.agent/AGENTS.md`:
- **Rule 6 (Negative Scope / Does Not Own)**: Every plan task MUST declare and honor what it does NOT own. Sprawling refactors or touching out-of-scope files without explicit instruction is strictly forbidden.
- **Rule 7 (Invariants in Tests)**: Code invariants and constraints must be asserted in executable tests, never merely stated in comments or conversation prompts.

### 4.2 `.agent/skills/brainstorming/SKILL.md` Augmentation
Update section `Presenting the design`:
- Designs presented to the user must explicitly include:
  1. `Owns` (What this design implements)
  2. `Does NOT own` (What is explicitly out-of-scope / forbidden to touch)
  3. `Autopilot Level` (`INVESTIGATE` / `DRAFT` / `AUTOPILOT`) based on blast radius.

### 4.3 `.agent/skills/writing-plans/SKILL.md` Augmentation
Update Task Template in `writing-plans`:
```markdown
### Task N: [Component Name]
**Files:**
- Create/Modify: ...
- Does NOT own: [Strict list of files/directories/layers this task must not touch]
- Invariants to test: [Specific mathematical/architectural invariants that MUST have assertions]
...
```

### 4.4 `.agent/skills/requesting-code-review/code-reviewer.md` Augmentation
In `## Review Checklist`:
Add `### Boundary & Anti-pattern Guard (Grokbot Field Notes)`:
- **Negative Boundary Check**: Did the git diff modify any file or layer listed in `Does NOT own`? If yes, classify as **Critical (Must Fix)**.
- **SSOT Integrity**: Is any derived state calculated in multiple places rather than single-source-of-truth?
- **Tested Invariants**: Are all business and architecture invariants verified with deterministic assertions?

### 4.5 `docs/antipatterns/lca-antipatterns.md`
Seed the repository anti-pattern database following the Grokbot format:
Each entry has:
1. **Name and Category**
2. **What happened (The failure incident)**
3. **Why it happened (Root cause)**
4. **The Principle / Standing Rule (Abstract the principle, delete the story)**

Initial 6 Seed Patterns:
1. *AP-01: Scope Sprawl via Missing Negative Boundary (Does Not Own)*
2. *AP-02: Invariants Only in Prompts, Missing in Assertions*
3. *AP-03: Multiple Sources Computing the Same Derived State*
4. *AP-04: Testing the Wrong Execution Path (Mock-Only Delusion)*
5. *AP-05: Premature Autopilot on High Blast Radius Changes*
6. *AP-06: Overfitting Rules to Incidents Instead of Principles*

---

## 5. Verification Plan

1. **Profile Syntax Check**:
   Run `.agent/tests/check-antigravity-profile.sh` to ensure all `.agent/` rule files and skills remain compliant and valid.
2. **Dry Run on Plan Generation**:
   Verify that plan templates correctly render with `Does NOT own` and `Invariants to test`.
3. **Reviewer Checklist Inspection**:
   Verify that `code-reviewer.md` checklist includes boundary-guard checks.
