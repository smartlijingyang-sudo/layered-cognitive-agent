---
name: lca-prose-standard
description: Use when writing, reviewing, restoring, trimming, or auditing prose in the LCA repo — required coverage (类型, 失败语义, 时序, 所有权, 外部后果), mechanical slop checks via scripts/verify_doc_slop.py (when enabled), deletes narrative / test walkthrough / duplicated rationale, links docs/AGENTS.md 写作要求 instead of restating it. Trigger phrases: "trim LCA prose", "audit comment", "lca-prose", "改注释", "review 一下 docstring".
---

# LCA Prose Standard

Write enough to preserve the contract, then remove narrative, repetition, and decoration. A contract is an obligation, invariant, precondition, postcondition, or compatibility promise that a caller, callee, implementer, producer, or consumer relies on. This skill owns editorial judgment and required prose coverage in LCA Markdown, docstrings, JSDoc-equivalent comments, prompts, diagnostics, and CLI strings. It is guidance, not a script.

## Sources of truth

- [docs/AGENTS.md 写作要求](../../../docs/AGENTS.md) — the repository-wide prose discipline. **Link it, do not restate it.** This skill is the LCA-specific application of those rules plus the mechanical catches below.
- [AGENTS.md §5 编码规范](../../../AGENTS.md) — when a comment / docstring carries a Protocol / enum / registry / wire / Journal contract, treat the AGENTS.md requirement as binding and add the missing clause.
- [AGENTS.md §1 卫生清单](../../../AGENTS.md) — deletion-date discipline, COMPAT block format, no-unbounded-TODO.

`docs/AGENTS.md` owns the prose-level rules (类型 / 失败语义 / 时序 / 所有权 / 外部后果 / 删除叙事 / 唯一权威). When this skill contradicts `docs/AGENTS.md`, defer to `docs/AGENTS.md` and report the conflict.

## Required coverage

Each prose surface owes the following clauses when the surface carries a contract. Add or restore prose when code, types, and structure do not communicate the contract; do not add a comment when those facts are already obvious locally.

- **Public docstring / JSDoc** — caller-visible return distinctions, raises / rejections, side effects, ownership, timing, cancellation, durability. Examples: a `Reducer.apply_*` method's ownership and ordering; a `Body.execute_tool` method's timeout / approval gate / sandbox reference.
- **Internal comments** — orient non-local structure: invariants, race ordering, ownership boundaries, security posture, surprising failure behavior. Delete control-flow narration and code restatement.
- **Module comments** — module role, dependencies, responsibilities, non-obvious architecture choices; link architecture choices to their owning explanation (ADR / spec / Agent Note).
- **Tests** — explain only non-obvious test design: why a fixture, assertion, real entry path, or indirect observation is necessary. Delete walkthroughs and inventories.
- **Cookbooks / runbooks** — prerequisites, required actions, real entry path, observable verification, concise warnings.
- **READMEs / package READMEs** — consumer contract: configuration, semantics, failures, limitations, extension points, model-visible effects. Keep durable gaps and maintainer traps, not ordinary cleanup inventories.
- **Agent Notes** — retain unique rationale, mechanisms, alternatives, consequences, shipped verification evidence, named coverage gaps. Implemented notes state shipped reality in present tense; remove planning checklists, not evidence that pins the decision. See [`lca-write-note`](../lca-write-note/SKILL.md) for the body skeleton.
- **Prompts and visible strings** — wording is behavior. Treat tool schemas, journal templates, CLI banners, error messages as prompt-equivalent: a stable string change is a behavior change. Update the owning runnable snapshot for model-visible text; if the authorized scope has no owning scenario, leave the wording unchanged and report the deferral.
- **Diagnostics** — name the failing subject or path, violated rule, and correction when it is non-obvious. Remove internal execution narration.

Preserve searchable mechanism names and meaningful modal / temporal / negative emphasis. Normalize decorative emphasis only.

## Mechanical slop checks

`scripts/verify_doc_slop.py` (when step 3 lands — until then, manual grep) catches the LCA-flavored patterns that mechanical review can flag without semantic judgment. Run it on the changed Markdown, docstring-bearing files, and any prompt / diagnostic snippets:

```sh
# (a) Mechanical slop (when available).
uv run python scripts/verify_doc_slop.py --changed "$(git diff --name-only HEAD~1)"

# (b) Docs-tree checks always available.
uv run python scripts/verify_md_links.py
uv run python scripts/verify_doc_budgets.py
uv run python scripts/check_doc_layering.py --strict
```

Agent 优先用 `lca-ops notes-slop`(内部调 `scripts/verify_doc_slop.py`),CI / ad-hoc 调试才掉到裸脚本;该 wrapper 是 Note / docs 范围内的统一入口。

The script is a probe, not the definition. Each round of manual review finds cases the script misses, so also read the densest prose in scope (module docstrings, package READMEs, Agent Notes) without a pattern in hand. The slop categories are:

1. **Change-narration residue** — "used to", "no longer", "the old X", "this PR adds", "in this cut". State the present behavior; a fixed regression becomes present-tense counterfactual ("without X, Y happens"), never repo history ("used to Y").
2. **Reviewer-addressed justification** — "the cast is safe — it simply…", "this is correct because…". State the invariant that makes the code safe, or delete the comment if the code shows it.
3. **Restatement and derivation transcripts** — control-flow narration ("first we X, then we Y"), test walkthroughs, proofs of obvious branches. Delete; keep only a non-obvious contract or invariant.
4. **Hedges and planning residue** — "probably fine for now", "should be enough", deferrals with no marker. Promote to `TODO` / `FIXME` with a deletion date or restate as the actual bound; delete the hedge.
5. **Stack and PR vantage** — "a later PR in this stack", "the previous commit". State the shipped mechanism or the extension point; deferred work moves to a `TODO` marker or an issue reference.
6. **Authoring-language slips** — untranslated working-language fragments (端, 设计稿, `---- 私有 ----` separators) in prose whose language is otherwise English, or the reverse in a Chinese counterpart. Translate or delete.
7. **Bare `TODO` / `FIXME`** — without a deletion date or `COMPAT(block)` per [AGENTS.md §1 卫生清单](../../../AGENTS.md).

## Workflow

1. Confirm the scope, current branch, and applicable `AGENTS.md` files. Do not inspect unrelated branches.
2. Read [docs/AGENTS.md 写作要求](../../../docs/AGENTS.md) and the owning code or document before judging a passage.
3. Inspect the requested scope, not only the largest files. Use searches and word counts to find candidates, then judge passages semantically.
4. Classify each candidate as keep, add, trim, restore, restructure, or defer. Apply clear changes only when the task authorizes edits; do not manufacture edits to satisfy a deletion target.
5. Update the owner before derivative artifacts. Re-check analogous passages after learning a new rule.
6. Run the narrow relevant checks, the slop script when available, `git diff --check`, and behavior tests for visible strings. Verify the final diff contains no `vendor/` path and report any accidental vendor match.
7. Report the inspected scope, clear changes, deliberate keeps, deferred cases, and checks actually run.

## Borderline decisions

A case is borderline only when at least two versions satisfy the complete-proposition rule but trade accepted principles, and `docs/AGENTS.md 写作要求` plus this skill do not already resolve the tradeoff. Apply clear edits when authorized and report genuine borderline cases without asking. Do not weaken a proposition to make progress.