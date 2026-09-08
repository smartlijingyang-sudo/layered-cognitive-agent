# Agent Note: ADR Index Governance — audit-2026-09-07 remediation

Status: proposed

## Problem

`docs/notes/audit-2026-09-07.md` reports 41 ADR files without `## 状态`, 6
duplicate-number clusters, 1 ADR absent from `docs/adr/README.md`, and 7
unreciprocated supersede edges. None of these block writes, but they make
"what's done" scans unreliable: every future audit, merge, or PR template
that asks "which ADRs are still open" must open each file to discover its
state. The audit script's `_STATUS_TOKENS` also omits `Implemented`, so
ADR-0186 / 0191 / 0192 / 0193 / 0194 / 0195 / 0196 / 0197 / 0201
(`**Implemented**` body) silently count as "no status" — same root cause.

The 6 duplicate clusters need canonicalisation so PRs that link to
"ADR-XXXX" do not fork. Per `AGENTS.md §4`, ADR files are not deleted
under this pass; instead, losers are marked `## Status: Superseded by
<winner>` with reciprocal cross-links added.

The 7 unreciprocated supersede pairs are mechanical: B is missing the
`Supersedes: ADR-A` line. Pure doc fix.

The 1 missing README row (ADR-0201) is a single-line edit.

The 1 bad-filename warning (`adr-0190-extreme-plugin-organization.md`) is
the file's only physical anomaly — its internal self-id is `ADR-0189` and
other ADRs link to it under both names; rename risk is contained but real
(see §Alternatives).

## Proposal

### Cluster decisions (Phase 1, doc-only)

| Cluster | Winner | Loser action |
|---|---|---|
| **0101** | `0101-tool-facts-and-evidence-only.md` (canonical root cause + 12-section ADR) | `0101-followup-tool-call-streaming-partial-preview.md` is a `§5.1/§5.3` follow-up. Mark `## Status: Superseded by 0101-tool-facts-and-evidence-only`; reciprocate by adding "Refines: ADR-0101 followup (2026-09-01)" to the canonical §11 metadata list. |
| **0110** | `0110-plugin-contract-unification-and-naming-convergence.md` (the substantive `Accepted` root ADR with PR-A/B/C/E/F/G/H/I落地清单) | `0110-followup-plugin-setup-generic.md` is a `TypeVar` genericisation follow-up that landed with PR-A. Mark `## Status: Superseded by 0110-plugin-contract-unification-and-naming-convergence`; add "Refines: ADR-0110 followup (PluginSetupFn 协变 + PluginDefinition 泛型化)" to the canonical PR-A落地清单 row. |
| **0119** | `0119-webserver-as-plugin.md` (canonical root: webserver 完全 plugin 化, kernel/transport boundary) | Both `0119-followup-gateway-name-map.md` (history-only stub, already declared `Superseded by 0119-followup-gateway-name-removal`) and `0119-followup-gateway-name-removal.md` (the actual full cleanup). Mark the map `## Status: Superseded by 0119-followup-gateway-name-removal` (already there — reciprocate), and add `## Companion: 0119-followup-gateway-name-removal.md` to the canonical webserver ADR. The canonical webserver ADR already says "配套 ADR: ... 0119 followup ..." in the body — no further edit needed. |
| **0165** | `0165-execution-point-enforcement.md` (the full D1–D11 content) | `0165-event-spine-unified-log.md` is a stub that already cross-links to the executor ADR; `0165-i17-traceback-and-coverage.md` is an I17-specific follow-up. Mark the stub `## Status: Superseded by 0165-execution-point-enforcement` (cross-link already present — reciprocate). The i17 file is complementary, not duplicative: add `## Companion: 0165-execution-point-enforcement.md` cross-link, no supersede. |
| **0168** | `0168-loop-step-control-and-model-visible.md` (the original step-control proposal with D1–D11) | `0168-loop-cursor-final.md` already declares `Superseded by ADR-0169` and lists `0168` as superseded by it. Mark `0168-loop-step-control-and-model-visible` `## Status: Superseded by 0169-loop-cursor-control` (already in cross-ref notes — reciprocate the reciprocal). |
| **0200** | `0200-p1-agent-gateway-bridge.md` (concrete Accepted ADR with Phase 1 PRs closed) | `0200-hermes-product-capabilities-absorption.md` is a separate `Proposed` track for Hermes product capability absorption. **Both are current** and complementary (P1 bridge vs. Hermes capability absorption). Add `## Companion: docs/adr/0200-<other>.md` cross-link in each. |

### Status annotation (Phase 2)

Insert `## 状态\n\n**Accepted** (YYYY-MM-DD).\n` (or `Implemented` / `Superseded` / `Proposed` as appropriate) into 41 missing-status ADRs, immediately after the H1 line. Yields:

- **Accepted (落地)**: 0081 (audit), 0082 (review), 0084 (audit), 0085 (explained), 0071 (Partially Accepted), 0109, 0115, 0116, 0117, 0118, 0121, 0122
- **Revised**: 0157, 0158, 0159 (current versions), 0176 (Accepted with §D4段被 supersede)
- **Withdrawn**: 0160, 0161
- **Superseded**: 0119-followup-gateway-name-map (already says so in body — promote to header), 0175 (body says supersede by 0185 — promote to header), 0110 followup (after cluster decision), 0101 followup (after cluster decision), 0165-event-spine-unified-log stub (after cluster decision)
- **Proposed**: 0071, 0105, 0106, 0107, 0177, 0178
- **Implemented**: 0164, 0166, 0167, 0167.1, 0186, 0191, 0192, 0193, 0194, 0195, 0196, 0197, 0201, 0119-followup-gateway-name-removal

### Reciprocal supersedes (Phase 3)

Add `Supersedes: ADR-XXXX` to the **target** ADR for each unreciprocated pair. Concretely:

| Source (already claims) | Target (needs `Supersedes:`) |
|---|---|
| ADR-0001 → 0104 | 0104-semantic-layer-rename.md add `Supersedes: ADR-0001` |
| ADR-0097 → 0099 | 0099-runs-live-openai-stream.md add `Supersedes: ADR-0097` |
| ADR-0098 → 0099 | 0099-runs-live-openai-stream.md add `Supersedes: ADR-0098` |
| ADR-0099 → 0100 | 0100-chat-command-is-agent-run.md add `Supersedes: ADR-0099` |
| ADR-0101 followup → 0101 canonical | 0101-tool-facts-and-evidence-only.md add `Supersedes: ADR-0101-followup` (already partially present via §11关联 ADR list — promote to formal `Supersedes:`) |
| ADR-0111 → 0115 | 0115-kernel-transport-boundary.md add `Supersedes: ADR-0111` |
| ADR-0112 → 0115 | 0115-kernel-transport-boundary.md add `Supersedes: ADR-0112` |
| ADR-0113 → 0116 | 0116-boot-event-observability-convergence.md add `Supersedes: ADR-0113` |
| ADR-0114 → 0116 | 0116-boot-event-observability-convergence.md add `Supersedes: ADR-0114` |
| ADR-0120 → 0120 (self-supersede) | 0120-retire-dsh-driver.md — inspect for self-loop (likely a doc error; either de-dupe or formalise) |
| ADR-0168 → 0169 | 0169-loop-cursor-control.md add `Supersedes: ADR-0168` (already mentioned in body — promote) |
| ADR-0168.1 → 0169 | 0169-loop-cursor-control.md add `Supersedes: ADR-0168.1` |
| ADR-0185 → 0185 (self-loop, 3×) | 0185-model-visible-event-bus-alignment.md — strip duplicate `Superseded by` claims |

### Audit script patch (Phase 2.5)

`_STATUS_TOKENS` in `scripts/audit_adr_health.py` omits `Implemented`. The
9 `Implemented` ADRs (0186, 0191, 0192, 0193, 0194, 0195, 0196, 0197,
0201) currently count as no-status. Add `Implemented` to `_STATUS_TOKENS`
so they parse. This is the single source of the "41" → "42" discrepancy
seen in `audit-2026-09-07.md` vs. fresh audit run.

### README (Phase 4)

- Add row for ADR-0201 (Implemented).
- Verify row order is numeric ascending (currently rows 0101, 0104, 0101, 0110, 0119, 0119 are interleaved by file-creation order; preserve as-is per existing README footnote and just ensure new row lands at correct position).
- Confirm ADR-0190 row stays at position 190 with `Keep` status.

### Bad filename (Phase 5)

`adr-0190-extreme-plugin-organization.md` → rename to
`0190-extreme-plugin-organization.md`. **Pre-rename check**: grep for
`adr-0190` (with the lowercase prefix) across the repo — if any code /
spec / config references the lowercase path, the rename breaks them and
should be deferred to a separate change with explicit `COMPAT` shim.

## Acceptance criteria

- `python scripts/audit_adr_health.py` reports **0** `no-status` warnings (was 41).
- Same script reports **0** `duplicate-number` warnings (was 6).
- Same script reports **0** `file-not-in-readme` warnings (was 1, ADR-0201).
- Same script reports **0** `unreciprocated-supersede` warnings (was 7, plus 6 already-known that this PR also closes).
- Same script reports **0** `bad-filename` warnings (was 1) — only if Phase 5 rename passes grep check.
- `git diff --check` clean.
- `ruff check` unchanged (no code edited).
- No new ADR files created (Phase 1 is consolidate-only; losers stay).

## Alternatives considered

- **Delete losing ADR files** — explicitly out of scope per
  `docs/notes/audit-2026-09-07.md` ("existing ADRs are not modified,
  migrated, re-numbered, or assigned sidecars"). Reject.
- **Re-number losers** (e.g., 0101-followup → 0101.1) — same source
  forbids it; also breaks every incoming deep link.
- **Move losers to `docs/adr/archive/`** — same source forbids it; we
  follow the `Superseded by` path instead.
- **Treat all 6 duplicate clusters as 1:1 consolidation** — wrong for
  0165 (i17 follow-up is genuinely complementary, not duplicative) and
  0200 (Hermes absorption is a separate track from P1 bridge). Cluster
  decisions above are 1:1 supersede for 0101 / 0110 / 0119 / 0168,
  companion cross-link for 0165 / 0200.
- **Patch `_STATUS_TOKENS` to add `Implemented`** — chosen. The audit
  script is the validation tool; if it can't read the corpus correctly,
  every report it emits is suspect. Adding the token is the minimum fix.
- **Rename `adr-0190-…` → `0190-…`** — chosen conditionally on grep
  safety. ADR-0200 §14 references the lowercase path; if that reference
  is the only one, the rename + reference update is mechanical; if not,
  defer with `COMPAT` shim.

## Risks

- The cluster decision for 0119 (webserver-as-plugin canonical, name-removal
  followup complements it) requires that the canonical ADR not also claim
  to be the "gateway name removal" entry point. The canonical's body says
  "ADR-0119 followup 把 gateway 命名按 6 类分类" — accurate, so the
  Companion cross-link is additive only.
- Adding `Supersedes:` lines to 0104 / 0099 / 0100 / 0115 / 0116 / 0169
  may surface in PR review as "did the author really intend to supersede
  this old ADR?". The fix is mechanical: ADR-A explicitly says "Superseded
  by B" in its own header; B's reciprocal is just bookkeeping.
- Status headers for ADRs that say "Partially Accepted" (0071) or
  "Revised" (0157/0158/0159) or "Withdrawn" (0160/0161) require custom
  status tokens. Two options:
  (a) Add `Partially Accepted` / `Revised` / `Withdrawn` to
      `_STATUS_TOKENS`. Cleaner.
  (b) Keep custom phrasing inside the header body but use a recognised
      token (`Accepted` / `Rejected`) for the script, with the custom
      phrasing as a sub-line. Less clean but no script change.
  This note commits to (b) for 0071 (token=Accepted), 0160/0161
  (token=Rejected), 0157/0158/0159/0176 (token=Accepted) — the audit
  script counts Accepted/Proposed/Superseded/Rejected/Deprecated/Audit/Review/Explained.
