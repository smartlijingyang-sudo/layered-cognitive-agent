---
name: lca-archive-notes
description: Use when archiving, restoring, reviewing, or auditing Agent Notes in docs/notes/; classifies implemented notes by future decision value, deletes rejected notes that no longer prevent a tempting fallacy, applies the five-step manual archive procedure, and checks every new note for superseded active records. Trigger phrases: "归档 note", "archive Agent Note", "把 note 移到 archived", "reduce notes corpus".
---

# Archive LCA Agent Notes

Reduce the active decision corpus without erasing history that can still guide work. Judge every note semantically; word count and age are discovery aids, never archive criteria. The five-step manual procedure in [docs/notes/archived/AGENTS.md](../../../../docs/notes/archived/AGENTS.md) is the contract this skill applies — that file owns the freeze rules; this skill owns the judgement and the workflow.

## Read the contracts

Before classifying any note, read:

- [docs/notes/README.md](../../../../docs/notes/README.md) — the format contract (three-line header, lifecycle + class path, `## Alternatives considered` is mandatory, `Status:` ↔ path consistency).
- [docs/notes/archived/AGENTS.md](../../../../docs/notes/archived/AGENTS.md) — the freeze rules and the five allowed archive operations; this skill does not restate them.
- The active lifecycle instruction in [`docs/notes/proposed/AGENTS.md`](../../../../docs/notes/proposed/AGENTS.md) and [`docs/notes/implemented/AGENTS.md`](../../../../docs/notes/implemented/AGENTS.md) (if present) — they own the per-lifecycle rules.
- 老 ADR (`docs/adr/`) 永远不动 — archival of Agent Notes never touches an ADR; if the candidate chain crosses an ADR, stop and write a separate ADR-supersedes-Note discussion instead.

Use current code, configuration, generated catalogs (wire schemas, Journal event catalog, Profile capability map), newer Agent Notes, and inbound links to establish whether a rationale still owns or constrains anything.

## Check supersession when adding a note

Every new Agent Note triggers a scoped audit of active notes covering the same decision, mechanism, or rejected alternative. Classify each full or partial supersession while writing the new note: archive qualifying implemented triplets in the same PR, retain and cross-link partial supersessions or independently useful rationale, reject obsolete proposals, and delete rejected notes that no longer prevent a plausible mistake. Apply the consolidation rule from [docs/notes/README.md §3.3](../../../../docs/notes/README.md) when the new owner absorbs every unique proposition; do not defer a known match to a later corpus audit.

## The five outcomes

Apply these lifecycle-specific outcomes — the same matrix as the dsh equivalent, adapted to LCA's three-state lifecycle:

1. **Implemented — keep active.** Retain when the rationale, alternatives, negative guarantees, durable / wire semantics, ownership boundary, security rule, or reintroduction condition is likely to guide a future change. Length does not matter. An LCA Agent Note in this category typically cites a Protocol by name, owns an enum entry, or pins a Reducer single-write contract.
2. **Implemented — archive.** Archive when the shipped decision is complete and its body is unlikely to guide future work — one-off UI chrome, a narrow adapter, a minor closed bug, superseded implementation detail, or process history whose current behavior is obvious elsewhere (e.g. an `implemented/runbook/` note that has been replaced by `docs/debug/run-debug-guide.md`).
3. **Proposed — never archive.** Keep a live proposal active; if it is no longer worth pursuing, reject it with an honest reason and satisfy the rejected lifecycle format (`Status: rejected — <one-line reason>`).
4. **Rejected — keep only as a guardrail.** Retain a rejection only when the losing proposal remains a tempting, meaningful mistake and the note explains why it loses. A `rejected/` note that pins the "Body 不直接读 State" rule is a guardrail; one that just records "we tried X" without a losing-alternative is not.
5. **Rejected — delete.** Delete the whole triplet when the rejected idea is obsolete, superseded, no longer plausible, or unlikely to prevent re-litigation. Repair or delete inbound links.

Do not archive toward a quota. Inspect every note in scope, classify analogous groups under one principle, use best judgment for close cases, and record genuinely borderline decisions for the handoff.

## Calibrated examples (LCA-shaped)

Archive implemented notes such as:

- A `implemented/contract/` note that adds a single enum value now reflected in the wire schema — closed, current code is authoritative.
- A `implemented/runbook/` note whose content has been folded into [`docs/debug/run-debug-guide.md`](../../../../docs/debug/run-debug-guide.md) — superseded by the runbook doc.
- A `implemented/profile/` note for a Profile that has since been deleted from `profiles/`.

Keep implemented notes such as:

- A `implemented/contract/` note pinning the `ActionType` close-set or the Journal catalog — foundational authority.
- A `implemented/seam/` note that documents a Cordis `Provides` boundary the kernel relies on — ownership rule that future changes must respect.
- A `implemented/runbook/` note for a recurring Kernel failure mode still documented in the journal — durable evidence + decision.

## Archive one implemented triplet (manual procedure)

`scripts/verify_notes_archived.py` is **not yet implemented** — see [docs/notes/archived/AGENTS.md](../../../../docs/notes/archived/AGENTS.md) "门禁契约" section. Until that script lands, execute the five allowed operations from `archived/AGENTS.md` by hand:

1. **整体搬迁整组三元组** — move `.md` + `.zh.md` (if it exists) + `i18n.yaml` (if it exists) from `implemented/<class>/` to `archived/<class>/`. **Do not split, drop, or generate a missing sidecar.** LCA does not enforce `.zh.md` pairing, so do not add one just to archive.
2. **插入 `Archived:` 行** — immediately below `Status: implemented` in both `.md` and (if present) `.zh.md`, insert one line `Archived: YYYY-MM-DD`. The two files carry the **exact** same text. This is metadata-only.
3. **重新记录 `i18n.yaml` sidecar 中的 manifest hash** (if present) — recompute and overwrite the hash entries the sidecar records. If no sidecar exists, do not create one. The hash algorithm matches the convention `docs/notes/README.md §5` reserves for the future `verify_notes_archived.py` (BLAKE2b-256 or equivalent — pick the algorithm the sidecar already uses for any existing archived triplets, never change it).
4. **修复或删除 inbound 链接** — search active prose for links to the now-archived note. Redirect them to current authority, retarget them to the archived path only when the historical snapshot is intentionally cited, or delete them. **Never verify or repair links out of the archived note** — outbound links from archived notes are historical and stay frozen.
5. **追加 append-only manifest 条目** — if `archived/manifest.json` (or equivalent) exists, append the new triplet's hashes; never modify existing entries. If it does not yet exist, do not create it until `verify_notes_archived.py` ships and defines the on-disk format.

After the triplet is sealed, never edit, move, translate, reformat, or delete it. Archived notes remain valid inbound-link targets but are historical snapshots, not authority for current behavior. 老 ADR 不受归档流程影响 — archiving a Note that references an ADR does not modify the ADR.

## Validate and report

Until `scripts/verify_notes_archived.py` ships, run the standing note checks plus the LCA-wide prose gates:

```sh
python scripts/check_notes_tree.py        # class + lifecycle + Status closure
python scripts/verify_md_links.py         # inbound-link rot, including the archived note's inbound refs
python scripts/verify_doc_budgets.py      # size budgets (per scripts/doc_budgets.json)
python scripts/check_doc_layering.py      # docs/design vs docs/specs vs docs/notes layering
python scripts/verify_doc_slop.py         # CoT-leakage / change-narration probe
uv run ruff check --fix <changed-path>
git diff --check
```

Report active implemented notes kept, implemented notes archived, rejected notes kept/deleted, proposed notes rejected if any, and every genuinely borderline case with its word count and chosen outcome. Do not claim archived outbound links are valid: archive procedure never verifies them.

If the diff touched an ADR — stop, revert the ADR change, and route the supersession through the existing ADR workflow. Agent Notes never edit an ADR, even to "note the supersession"; cross-references in `proposed/`, `implemented/`, `rejected/`, or `archived/` to an ADR are inbound prose, not modifications.

## What this skill explicitly does not own

- **Adding `scripts/verify_notes_archived.py`** — that script is owned by a future PR gated on first archived triplet existing, per `docs/notes/README.md §5` and `docs/notes/archived/AGENTS.md` "门禁契约". This skill describes the manual procedure that runs until then.
- **Modifying `docs/adr/`** — 老 ADR 永远不动, period. If an archived Note's body would need to update an ADR to stay coherent, route the change through the ADR workflow and keep the Note itself frozen.
- **Editing `archived/` after the triplet is sealed** — five allowed operations only; see `docs/notes/archived/AGENTS.md` for the exact list. Even a typo fix is forbidden; the freeze is the point.

## Commands / 调用方式

定位可能归档的 `implemented/` 候选时用 `lca-ops notes-list --json`(结构化清单,给 grep / 二次过滤);搬迁完成(新增 `Archived:` 行、修 inbound link、append manifest 条目)之后跑 `lca-ops notes-check`(内部调 `scripts/check_notes_tree.py`)确认 `Status:` ↔ archived 路径、`class` 闭集、freeze 都还成立。Agent 走 wrapper,CI / ad-hoc 调试再直接调裸脚本。