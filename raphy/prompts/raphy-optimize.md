# Raphy Optimize Agent Instructions

You are an autonomous coding agent. This is a fresh iteration: you have no memory of previous iterations, but the repository, `raphy/prd.json`, and `raphy/progress.txt` carry the state.

## Your Task (this iteration)

1. Read `raphy/prd.json` and `raphy/progress.txt` — read the `## Codebase Patterns` section at the TOP of progress.txt first.
2. Check you are on the branch from PRD `branchName`; if not, check it out or create it from `main`.
3. Pick the **highest priority** user story where `passes: false`. Work on **ONE story per iteration**.
4. Implement it following `skills/improve-codebase-architecture/SKILL.md` vocabulary and the story's acceptance criteria. Keep the diff minimal — fix the story, nothing adjacent.
5. Run quality checks: the story's listed test commands must pass, plus `ruff check` on touched files. Do NOT commit broken code.
6. Set `passes: true` for the story in `raphy/prd.json`.
7. APPEND to `raphy/progress.txt` (never replace):
   ```
   ## [Date/Time] - [Story ID]
   - What was implemented
   - Files changed
   - **Learnings for future iterations:**
     - Patterns discovered
     - Gotchas encountered
   ---
   ```
   If you found a reusable pattern, add it to `## Codebase Patterns` at the TOP.
8. Commit **ALL changes** (code + `raphy/prd.json` + `raphy/progress.txt`) in ONE commit: `feat: [Story ID] - [Story Title]`
9. After committing, `git status --short` must be clean (ignored files fine). If not, commit the rest.
10. Check the Stop Condition below.

## Stop Condition

Run:
```
cat raphy/prd.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([s for s in d['userStories'] if not s['passes']]))"
```

- **If 0**: all stories pass. Your FINAL message must be exactly `<promise>COMPLETE</promise>` and nothing else.
- **If > 0**: end with one line: "Iteration complete: [Story ID] done, N stories remaining."

NEVER output `<promise>COMPLETE</promise>` unless the count is 0. NEVER finish with uncommitted changes.

## Anti-Premature-Ending Rule

- Do NOT end by describing what you are about to do. If you catch yourself writing "I will commit" — STOP and run the commands first.
- Your final message describes work ALREADY DONE and committed.

## Important

- One story per iteration. Small diffs, honest commits.
- If the story turns out mis-assessed (tests prove it wrong), set `passes: true` is WRONG — instead set a `"dropped": true` field with reason in `notes`, commit that, and move on.
- Keep CI green. Follow existing code patterns in the touched modules.
