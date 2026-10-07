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
| 4 | `lca/infrastructure/observability/spine/spine/enrich.py` | COMPAT re-export shim | **rejected 2026-10-07**: not a re-export shim — holds the live `enrich_spine_payload` with 4 production importers (`loop/fact_gateway.py:128`, `plugins/observability/spine/emit_pipeline.py:57`, `plugins/session/runtime/spine/hook.py:30`, + 2 dynamic-path refs). Its `delete_when` retires a module *path*, not dead code | ~30 | rejected |
| 5 | `lca/contracts/models/core/state/state.py` `history` property | COMPAT alias | **rejected 2026-10-07**: 5 production consumers — `cognition/body/executor/simple_body.py:355`, `cognition/brain/llm_turn/policy.py:30,32`, `cognition/brain/reasoner/critic.py:107,109`, and a write at `plugins/loop/reducer/plugin.py:190` | ~20 | rejected |
| 6 | `lca_kernel/events/bus/bus.py` EnvelopeBus / EventBus split | inverted canonical-compat pair | **re-scoped 2026-10-07** — original framing was backwards and unsafe: `EventBus` (`:356-808`, 453 lines) *is* the delivery path (`subscribe` / `mount_sink` / `_dispatch_sinks` / `_fanout` / hooks); `EnvelopeBus` (`:181-350`, 170 lines) is the hollow base whose `publish` never dispatches, with zero construction sites repo-wide. Deleting `EventBus` deletes the bus. Plan: [docs/notes/plans/2026-10-07-envelope-bus-single-class.md](../../../docs/notes/plans/2026-10-07-envelope-bus-single-class.md) | ~620 (3 PRs) | planned → see plan |
| 7 | `lca/infrastructure/cli/commands/runs/runs.py` cli_direct resolve | COMPAT shim | COMPAT(delete-when: --facade default + parity test + zero cli_resolve hits) — verify | ~40 | planned |
| 8 | `lca/plugins/transport/webserver/doctor/steps/hops.py` stub-ok-True fallback | COMPAT shim | COMPAT(delete-when: scan.step_ids/indexes no empty-tuple fallback) — verify | ~30 | planned |
| 9 | `lca/plugins/domain/assistant/catalog/handlers.py` `retire` placeholder | COMPAT placeholder | COMPAT(delete-when: 2026-12-31, retire 入口落地后删除); method raises NotImplementedError — verify | ~15 | planned |
| 10 | `lca/infrastructure/observability/spine/sinks/naming.py` SPINE_FILE_SUFFIX | COMPAT constant | COMPAT(delete-when: spine_filename 默认稳定 ≥14 天) — verify | ~15 | planned |

## Iteration log

Each row: iteration → commit SHA → module/files → `.py` numstat (add+del) → benefit → checks run.

| # | SHA | Module/File | .py lines (A+D) | Benefit | Checks |
|---|---|---|---|---|---|
| 1 | 6f44ab70e | `lca/plugins/observability/spine/reflectors/` + `spine/core.py` | 619 (6+613) | Delete retired 582-line reflector package (zero consumers) + dead soft-import loop over 4 non-existent modules in core.py | ruff core.py OK; pytest spine subset 85 passed / 27 failed = baseline (5 pre-existing reproduced on clean stash); lint-imports unchanged |
