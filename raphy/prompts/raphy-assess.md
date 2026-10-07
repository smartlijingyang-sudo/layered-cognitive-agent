# Raphy Assess Agent Instructions

You are an autonomous coding agent. This is a fresh session: you have no memory of previous iterations. The repository and `raphy/prd.json` / `raphy/progress.txt` / `raphy/assessment.md` carry the state.

## Your Task (this session): ASSESS ONLY, do not implement

Follow `skills/improve-codebase-architecture/SKILL.md` faithfully. That skill's referenced
helper skills (`codebase-design`, `grilling`, `domain-modeling`) do NOT exist in this repo —
the deepening vocabulary and the grilling discipline below replace them. Do not skip depth
because the helpers are missing.

### Deepening vocabulary (use these terms exactly)

- **module**: a unit of code with an interface and an implementation.
- **interface**: what callers see; **depth** = (functionality provided) / (interface complexity). Deep modules are good.
- **seam**: the place where two modules meet; **adapter**: code that translates across a seam.
- **leverage**: how much future work a change unlocks; **locality**: related behavior living in one place.
- **deletion test**: would deleting this module concentrate complexity, or just move it? "Concentrates" = it earns its existence.
- "The interface is the test surface": if you can't test through the interface, the interface is wrong.
- "One adapter = hypothetical seam, two = real": don't abstract on the first occurrence.

### Phase 1 — Explore (this is the bulk of your work; do not rush it)

1. **Scope via YAGNI**: `git log --oneline` back ~40 commits; find hot spots (recently changed areas). Read `CONTEXT.md` and relevant `docs/adr/` first. Avoid areas owned by other active rounds (see `## Codebase Patterns` in `raphy/progress.txt` for the current禁区 list — if `raphy/progress.txt` doesn't exist yet, avoid `ralph/` Round 2 areas: DecisionGates, Ingest, ContextFiles shims, Read Runs micro-dirs, `lca/cognition/memory/`).

2. **Organic friction walk (mandatory, not optional)**: pick the 3 hottest areas and READ the modules end-to-end — not grep, READ. Open the files, follow the imports, understand one concept and notice where it hurts. For each area, write down answers to ALL FIVE:
   - Where does understanding one concept force bouncing between many small modules? (shallow-module sprawl)
   - Which modules are **shallow** — interface nearly as complex as the implementation? (apply the deletion test)
   - Where were pure functions extracted just for testability, but the real bugs hide in how they're called? (no locality)
   - Where do tightly-coupled modules leak across their seams? (leaky abstractions: DB errors in domain logic, framework types in contracts, etc.)
   - Which parts are untested, or can only be tested by reaching past the interface?
   
   If you cannot answer a question for an area, say which files you read and why the question doesn't apply — "didn't look" is not an answer.

3. **Duplication scan (secondary, not primary)**: only AFTER the friction walk, grep for mechanical duplication. Duplication is the weakest finding class — it must not be the only class you return (see quota below).

### Phase 2 — Self-grilling (replaces the skill's interactive grilling loop)

For EACH candidate, write out (in `raphy/assessment.md`, not just in your head):
- **Constraints**: what must not change (behavior, contracts, ADR decisions)?
- **Dependencies**: who calls this, who does it call? What breaks if the seam moves?
- **Shape of the deepened module**: what does the new interface look like? What sits behind the seam?
- **Test survival**: which existing tests pin the current behavior? What new test would prove the deepening?
- **Deletion test verdict**: concentrates or just moves?

### Phase 3 — Present and record

1. Candidate table (Files / Problem / Solution / Benefits in locality+leverage terms / Strength: Strong | Worth exploring | Speculative) + Top recommendation paragraph. Use the deepening vocabulary exactly; don't drift into "component/service/API/boundary".
2. **Diversity quota**: the final story list must not be all-duplication. At least one story must come from the friction walk (shallow module / leaky seam / testability gap) — or document which files you read and why no such finding exists.
3. Write stories to `raphy/prd.json` (`RA-001`..., `passes: false`, concrete acceptanceCriteria, `branchName` as instructed by the driver), full assessment to `raphy/assessment.md`, summary to `raphy/progress.txt` (with `## Codebase Patterns` at top).
4. Commit `raphy/prd.json` + `raphy/assessment.md` + `raphy/progress.txt`: `chore: [raphy] assess - N architecture candidates`.
5. End with one line: "Assessment complete: N stories written, top is RA-00X."

## Rules

- ASSESS ONLY. Do not modify any code outside `raphy/`.
- If a candidate contradicts an existing ADR, mark it and include only if friction is real.
- Do NOT output `<promise>COMPLETE</promise>`.
- Before ending: `git status --short` clean (ignored files fine).
