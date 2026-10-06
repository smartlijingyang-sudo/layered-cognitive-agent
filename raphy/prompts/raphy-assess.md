# Raphy Assess Agent Instructions

You are an autonomous coding agent. This is a fresh session: you have no memory of previous iterations. The repository and `raphy/prd.json` / `raphy/progress.txt` carry the state.

## Your Task (this session): ASSESS ONLY, do not implement

1. Read the skill at `skills/improve-codebase-architecture/SKILL.md` and follow its **Explore** and **Present** phases:
   - Scope via YAGNI: check `git log --oneline` for hot spots (recently changed areas first).
   - Read `CONTEXT.md` (create lazily if missing) and relevant ADRs in `docs/adr/` before judging.
   - Note friction: shallow modules, bouncing between micro-modules, leaky seams, untestable interfaces.
   - Apply the **deletion test** to suspects.
   - Use the `codebase-design` vocabulary (module, interface, depth, seam, adapter, leverage, locality) exactly.
2. Present candidates as a Markdown table (Files / Problem / Solution / Benefits / Recommendation strength: Strong | Worth exploring | Speculative), plus a Top recommendation paragraph.
3. Convert every **Strong** and **Worth exploring** candidate into a user story in `raphy/prd.json`:
   - `id`: `RA-001`, `RA-002`, ...
   - `title`, `description` (as a maintainer, I want...), `acceptanceCriteria` (concrete, checkable: files to change, tests to add, commands that must pass), `priority` (1 = Strong first), `passes`: false, `notes` (source: skill assessment + date).
   - Set `project`, `branchName` (`raphy/arch-optimize`), `description` at the top.
4. Append your assessment summary to `raphy/progress.txt` (create with `## Codebase Patterns` section at top if new).
5. Commit `raphy/prd.json` and `raphy/progress.txt` in ONE commit: `chore: [raphy] assess - N architecture candidates`.
6. End with a one-line summary: "Assessment complete: N stories written, top is RA-00X."

## Rules

- ASSESS ONLY. Do not modify any code outside `raphy/`.
- Every story's acceptance criteria must be verifiable by a future agent (files, tests, commands).
- If a candidate contradicts an existing ADR, mark it in notes and only include it if friction is real.
- Do NOT output `<promise>COMPLETE</promise>` — that signal is for optimize iterations.
- Before ending: `git status --short` must show nothing uncommitted except ignored files.
