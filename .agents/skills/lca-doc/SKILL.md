---
name: lca-doc
description: Use when writing, restoring, reviewing, or placing Markdown documentation in the LCA repo — picks the owning directory from the placement map, drafts per the directory's existing format, runs the local doc gates, and enforces one-home-per-fact. Distinct from lca-prose-standard (which owns prose hygiene) and lca-trim-cot-leakage (which owns change-narration residue). Trigger phrases: "write LCA doc", "add a new spec/AGENTS.md", "documentation placement", "doc review".
---

# Writing & Placing LCA Markdown Docs

Pick the right directory, draft per its format, run the local gates, commit. This skill is guidance, not a checklist — it owns the *where does this doc live* decision and the local gate order; prose discipline is owned by [`lca-prose-standard`](../lca-prose-standard/SKILL.md) and CoT-residue cleanup by [`lca-trim-cot-leakage`](../lca-trim-cot-leakage/SKILL.md); do not restate them.

## Sources of truth

- [docs/AGENTS.md 目录归属 + 归位原则](../../../../docs/AGENTS.md) — one-home-per-fact; **link, do not restate**.
- [AGENTS.md §1 老 ADR 全部不动](../../../../AGENTS.md) — `docs/adr/` is frozen; the placement map respects this.
- [docs/notes/README.md §1 与 docs/adr/ 的分工](../../../../docs/notes/README.md) — Notes vs ADR discriminator.
- [docs/specs/documentation-map.md](../../../../docs/specs/documentation-map.md) — directory navigation.

## Placement map (one fact → one home)

Pick the smallest enclosing directory; do not invent a new top-level under `docs/`.

| Directory | Owns |
|---|---|
| `AGENTS.md` / `docs/AGENTS.md` | Standing rules; roles of repo-wide prose discipline |
| `docs/adr/` | Architecture decisions; **frozen — do not edit, do not migrate, do not re-number, do not sidecar**. Touching this directory in a "doc review" batch is out of scope |
| `docs/notes/` | New decisions: contract / primitive / seam / profile / runbook / postmortem. Path-encoded lifecycle `proposed/` / `implemented/` / `rejected/` / `archived/` |
| `docs/specs/` | Current contracts, operation guides, terminology, references (the contract-of-truth for the rest of the repo) |
| `docs/design/` | Constitution-level or long-lived design notes (e.g. the cognitive primitive constitution) |
| `docs/observability/` | Journal / Trace / Metrics / Projection specs |
| `docs/debug/` | Operation runbooks (cross-seam / cross-profile) |
| `history/` | Finished plans, research, execution records — **not** current authority |

> **Discriminator** ([docs/notes/README.md §1](../../../../docs/notes/README.md)): does the new doc change other ADRs' boundaries? Yes → ADR (existing workflow, frozen directory). No → Notes. If neither fits, it is probably a `specs/` or `history/` file.

## Style

Style is owned by [`lca-prose-standard`](../lca-prose-standard/SKILL.md) and [docs/AGENTS.md 写作要求](../../../../docs/AGENTS.md); **link them, do not restate them**. Mechanical catch: `scripts/verify_doc_slop.py` (when enabled). Each Agent Note must obey the three-line format ([docs/notes/README.md §3.1](../../../../docs/notes/README.md)): `# Agent Note: <title>` / blank line / `Status: <proposed|implemented|rejected>`; `Status:` value must equal the physical lifecycle directory. LCA does **not** enforce `.zh.md` sidecars — do not pre-generate one.

## Workflow for a new doc

1. **Decide the directory** from the placement map above. Run the ADR vs Notes discriminator before any other judgment. If the doc would touch `docs/adr/`, stop and route through the existing ADR workflow.
2. **Draft per the directory's existing format.** Open one neighbouring file in the target directory and mirror its section headings, link style, and length budget. Read [docs/AGENTS.md 写作要求](../../../../docs/AGENTS.md) once.
3. **Run the local doc gates** for the touched surface:

```sh
python scripts/verify_md_links.py            # link rot in the new doc + its inbound refs
python scripts/verify_doc_budgets.py         # size budgets per scripts/doc_budgets.json
python scripts/check_doc_layering.py         # docs/design vs docs/specs vs docs/notes layering
python scripts/check_notes_tree.py           # when notes/ is touched: class + lifecycle + Status closure
python scripts/verify_doc_slop.py            # CoT-leakage / change-narration probe (when enabled)
```

4. **Commit.** Single-topic commit per [AGENTS.md §7](../../../../AGENTS.md); conventional-commits subject naming; one paragraph body for why and which `AGENTS.md` / `docs/notes/README.md` rule the doc satisfies.

## What this skill explicitly does not own

- **Prose coverage rules** (类型 / 失败语义 / 时序 / 所有权 / 外部后果) — [`lca-prose-standard`](../lca-prose-standard/SKILL.md).
- **CoT-residue cleanup** in existing prose — [`lca-trim-cot-leakage`](../lca-trim-cot-leakage/SKILL.md).
- **Audit reports** (`audit-YYYY-MM-DD.md` in `docs/notes/`) — [`lca-audit-notes`](../lca-audit-notes/SKILL.md).
- **Agent Note body skeleton, `Alternatives considered`, propose → implement rewrite** — [`lca-write-note`](../lca-write-note/SKILL.md).
- **Editing `docs/adr/`** — frozen; this skill never opens that directory.
- **Bilingual sidecars** — LCA does not enforce `.zh.md`; add one only when a paired doc already exists.

## Reference paths

- [docs/AGENTS.md 目录归属](../../../../docs/AGENTS.md) — placement authority.
- [docs/notes/README.md](../../../../docs/notes/README.md) — Notes vs ADR discriminator and format contract.
- [docs/specs/documentation-map.md](../../../../docs/specs/documentation-map.md) — directory navigation.
- [`lca-prose-standard`](../lca-prose-standard/SKILL.md) — prose discipline.
- [`lca-trim-cot-leakage`](../lca-trim-cot-leakage/SKILL.md) — CoT residue cleanup.
- [`lca-write-note`](../lca-write-note/SKILL.md) — Agent Note body skeleton + promotion.
- [`lca-audit-notes`](../lca-audit-notes/SKILL.md) — note audit + report placement.
- [`scripts/verify_doc_slop.py`](../../../../scripts/verify_doc_slop.py), [`scripts/verify_md_links.py`](../../../../scripts/verify_md_links.py), [`scripts/verify_doc_budgets.py`](../../../../scripts/verify_doc_budgets.py), [`scripts/check_doc_layering.py`](../../../../scripts/check_doc_layering.py), [`scripts/check_notes_tree.py`](../../../../scripts/check_notes_tree.py) — the local gates; link, do not redefine.