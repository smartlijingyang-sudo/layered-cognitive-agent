# Loop control contribution contracts (ADR-0194 P4-L04)

> **Decision:** [ADR-0194 §2.1 control/](../../docs/adr/0194-cognitive-loop-architecture-convergence.md) · [ADR-0074](../../docs/adr/0074-declarative-control-contributions.md)

## Purpose

`lca/loop/control/` documents the **declarative control contribution contract** that
Think/Act/Stop phases consume through harness graph governance. Concrete plugins
live under `lca/plugins/loop/control/` (migration target for `control_contributions/`).

## Slots (capability keys)

| Slot | Role | Reads | Writes |
|---|---|---|---|
| `control.think.guard` | Think TRANSFORM/GOVERN | `gate.decided.v1` fold, prior Decision artifact | `ControlVerdict` on phase result |
| `control.act.chain` | Act contribution chain | Act decision artifact | Act governance verdict |
| `control.stop.policy` | Stop GOVERN | budget + goal signals | terminal `StopDecision` |

Slot names are **stable capability keys**, not graph nodes. Gate remains a Think
primitive sub-chain (`lca/cognition/brain/cognitive_pipeline.py`).

## Contribution roles (harness graph)

Harness `PhaseGovernance` (`lca/harness/graph/governance/`) invokes contributions
by `ContributionRole`:

| Role | When | Loop owner |
|---|---|---|
| `PREPARE` | Before executor | Graph transaction prepare path |
| `TRANSFORM` | After executor, before govern | Control plugin |
| `GOVERN` | Terminal control decision | Control plugin + governance interpreter |
| `OBSERVE` | Observation seam | Phase observer plugins |
| `FINALIZE` | Post-commit hooks | Reserved |

## Invariants

1. Control plugins **must not** call `Session.append` for durable execution facts.
2. ThinkGuard **must not** re-fold Session for Gate when Decision already carries rewrite.
3. MTK (`lca/harness/graph/`) **must not** embed concrete plugin ids — only slot prefixes
   and `ContributionRole` semantics (see `test_mtk_no_business_ids`).

## Related code

| Concern | Canonical path |
|---|---|
| Governance interpreter | `lca/harness/graph/governance/phase_governance.py` |
| Phase visit transaction | `lca/loop/transaction.py` |
| Control verdict contract | `lca/contracts/protocols/gate/control_verdict.py` |
| Example think guard plugin | `lca/plugins/control_contributions/think_guard.py` |
