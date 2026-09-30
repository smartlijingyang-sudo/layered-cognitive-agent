# LCA improve-codebase Campaign Ledger

- Campaign start: 2026-10-01
- Branch: `main`
- Goal: ≥100 substantial optimization iterations, each ≥50 `.py` lines (git numstat), all committed on this branch.
- Skill chain: `lca-find-simplifications` (sweep) → `lca-improve-codebase` (per-candidate drill-down) → `lca-pre-push-checks` (narrow checks) → `lca-code-review` (standing-rule review).
- Gate: every 10th iteration diff is audited for genuine structural/logic/type/perf improvement; no rename/format/comment/revert padding.

## Candidate backlog

The candidate backlog is populated by a repo-wide `lca-find-simplifications` sweep (AST dead-module scan + `rg` consumer verification + COMPAT shim audit). Evidence column records the `rg` command and result used to classify the candidate.

| # | Candidate (module/area) | Category | Evidence (rg) | Est .py lines | Status |
|---|---|---|---|---|---|
| 1 | `lca/plugins/observability/spine/reflectors/` (source.py + __init__.py) | dead module (retired reflectors) | `rg 'reflectors.source\|reflectors import\|from \.source' lca/ lca_kernel/ tests --glob '*.py'` → zero production consumers; core.py soft-imports 4 module paths (runtime/cognition/body_llm/agent_spawn) that do not exist | 582 | planned |
| 2 | `lca/plugins/observability/spine/core.py` `_REFLECTOR_SET_ACTIVE_MODULES` loop | dead fallback (imports non-existent modules) | `ls lca/plugins/observability/spine/reflectors/` → only __init__.py + source.py; the 4 module paths in the tuple don't exist | ~30 | planned |
| 3 | `lca/plugins/transport/webserver/handlers/runs/session/event/session.py` | COMPAT re-export shim | COMPAT(delete-when: no webserver-local imports remain) — verify consumers | ~15 | planned |
| 4 | `lca/infrastructure/observability/spine/spine/enrich.py` | COMPAT re-export shim | COMPAT(delete-when: rg 'lca.infrastructure.observability.spine.spine.enrich' lca/ = 0) — verify | ~30 | planned |
| 5 | `lca/contracts/models/core/state/state.py` `history` property | COMPAT alias | COMPAT(owner: ADR-0194 P4-R02): use `control_turns` — verify consumers | ~20 | planned |
| 6 | `lca_kernel/events/bus/bus.py` EventBus legacy class | COMPAT shim | COMPAT(delete-when: rg '\\bEventBus\\b' lca/ lca_kernel/ ... = 0) — verify | ~200 | planned |
| 7 | `lca/infrastructure/cli/commands/runs/runs.py` cli_direct resolve | COMPAT shim | COMPAT(delete-when: --facade default + parity test + zero cli_resolve hits) — verify | ~40 | planned |
| 8 | `lca/plugins/transport/webserver/doctor/steps/hops.py` stub-ok-True fallback | COMPAT shim | COMPAT(delete-when: scan.step_ids/indexes no empty-tuple fallback) — verify | ~30 | planned |
| 9 | `lca/plugins/domain/assistant/catalog/handlers.py` `retire` placeholder | COMPAT placeholder | COMPAT(delete-when: 2026-12-31, retire 入口落地后删除); method raises NotImplementedError — verify | ~15 | planned |
| 10 | `lca/infrastructure/observability/spine/sinks/naming.py` SPINE_FILE_SUFFIX | COMPAT constant | COMPAT(delete-when: spine_filename 默认稳定 ≥14 天) — verify | ~15 | planned |
