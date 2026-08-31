# Plugin Authoring Guide

> **First line: always start with `contract=PluginContract(...)` when you write a new plugin.**
> `functional_group=` and `logic_address=` keys still work but are **deprecated** —
> they alias through a 6-month deprecation window (delete: 2027-03-01).

This guide covers the canonical, recommended way to author a plugin in LCA after
ADR-0110. If you have an existing plugin, the "Migration" section at the end
shows the mechanical codemod.

---

## Quickstart: canonical plugin template

```python
"""One-line description of what this plugin does."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.harness.plugin_api import PluginContext, plugin


class Config(BaseModel):
    """Strict configuration — `extra=\"forbid\"` blocks unknown fields."""

    model_config = ConfigDict(extra="forbid")
    # your fields here


@plugin(
    id="my-plugin.unique-id",
    Config=Config,
    provides=("my-plugin.unique-id",),        # capability key(s) you expose
    requires=(),                            # capability key(s) you consume
    layer="L2",                             # L0–L4 (see ArchitectureContract below)
    kind="primitive",                       # seam | provider | primitive | composite | driver | bridge
    effects="none",                         # none | tools | memory | network | filesystem | world
    test_suite="tests/your/test_file.py",

    # ── ADR-0110 D1: the SINGLE canonical contract surface ──
    # This replaces the older 6-dim ``logic_address=LogicAddress(...)`` flat struct.
    contract=PluginContract(
        identity=PluginIdentity(
            id="my-plugin.unique-id",
            version="v1",
            owner="team-name",
        ),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION,            # G0–G12 (see ADR-0069 §一)
            role="brain_standard",                        # noun describing this plugin's role
            control_slots=(ControlSlot.THINK_GUARD,),     # when this plugin's executor runs
        ),
        capabilities=__import__(                           # see "Why this snippet" below
            "lca.contracts.harness.composition.plugin_contract",
            fromlist=["CapabilityContract"],
        ).CapabilityContract(
            provides=("my-plugin.unique-id",),
            requires=(),
            effect_classes=(),
        ),
        authority=AuthorityContract(
            grants=("brain.read",),                       # capability grants this plugin receives
            risk_level="low",                             # low / medium / high / critical
            requires_approval=False,
        ),
        lifecycle=LifecycleContract(
            allowed_scopes=(Scope.RUN,),                 # release | profile | agent | run | turn | invocation | experiment | device
            lease_seconds=None,                          # None = no lease
            dispose_strategy="graceful",                 # graceful | force | noop
        ),
        observability=EvidenceContract(
            descriptors=("my_plugin.checked", "my_plugin.served"),  # journal catalog EventDescriptor names
            privacy_class="internal",                                # public | internal | sensitive | secret
            replay_safe=True,
        ),
        verification=VerificationContract(
            test_suite="tests/your/test_file.py",
            schemas=(),
            fixtures=(),
            property_tests=(),
        ),
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """The Cordis setup() callback — register whatever this plugin exposes."""
    ctx.provide("my-plugin.unique-id", ...)
```

> **Why the `__import__` for CapabilityContract?** Older plugin definitions need
> it because `CapabilityContract` lives in the same module as `PluginContract`
> but the top‑level import statement is **already at module top**; the snippet
> above shows it inline so the example fits in a self‑contained block.
> In production code write `from lca.contracts.harness.composition.plugin_contract
> import CapabilityContract` at the top of your file.

---

## The 5 sections — what each one means

| Section | Question it answers | Required for compilation? |
|---|---|---|
| `identity`            | "Who am I?" (`id` / `version` / `owner`)                        | `id` strongly recommended; `version` defaults to `""` |
| `architecture`       | "What cognitive role / control slot?" (`group` / `role` / `control_slots`) | **`group` is mandatory for `lca plugin check --strict`** |
| `capabilities`        | "What do I provide / consume?" (`provides` / `requires` / `effect_classes`) | Used by Profile Resolve; failure to declare ⇒ boot fails |
| `authority`           | "What capability grant + risk + approval?" (`grants` / `risk_level` / `requires_approval`) | At least the matching `plugin.X` grant for what you call |
| `lifecycle`           | "Where do I live?" (`allowed_scopes` / `lease_seconds` / `dispose_strategy`) | All fields tolerate empty tuple / None |
| `observability`       | "What events do I emit / how private?" (`descriptors` / `privacy_class` / `replay_safe`) | **`descriptors` should reference real `journal_catalog` EventDescriptors** |
| `verification`        | "Where do my tests live?" (`test_suite` / `schemas` / `fixtures` / `property_tests`) | `test_suite` enforced by ADR-0109 D1 |

Three additional fields at `@plugin(...)` decorator level (not inside `contract`):
`layer`, `kind`, `effects`. These pair with `architecture` to define the plugin's
DI taxonomy. Fold them into `architecture` over time (per ADR-0110 D4) — they
are not part of `PluginContract` yet; they remain on the decorator.

---

## Migration: from legacy `logic_address=` to canonical `contract=`

If you have code like:

```python
@plugin(
    id="legacy.plugin",
    Config=Config,
    provides=("legacy.plugin",),
    layer="L2",
    kind="primitive",
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.ACT_EXECUTE,
        scope=Scope.TURN,
        authority=("decision.read",),
        evidence=("legacy.checked",),
        revision="v3",
    ),
)
async def setup(...): ...
```

…run this codemod at the repo root (PR-C, commit 794f9629):

```bash
uv run python scripts/codegen_plugin_contract.py path/to/your_plugin.py
```

It produces (always‑idempotent; safe to re-run):

```python
@plugin(
    id="legacy.plugin",
    Config=Config,
    provides=("legacy.plugin",),
    layer="L2",
    kind="primitive",
    contract=PluginContract(
        identity=PluginIdentity(version="v3"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.ACT_EXECUTE,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("decision.read",)),
        observability=EvidenceContract(descriptors=("legacy.checked",)),
    ),
    # layer/kind/effects preserved; ``functional_group=`` shorthand dropped
    # (still tolerated as alias during deprecation window).
)
async def setup(...): ...
```

`scripts/codegen_plugin_contract.py` accepts the standard column-aligned form
found in `lca/plugins/control_contributions/`, `lca/plugins/composer/`, etc.
It rewrites the imports too. For unusual formats, run it on a copy first and
inspect the diff.

---

## What still works in the deprecation window

These two forms are still legal but generate a `DeprecationWarning` at
construction or a `warning:` line in `lca plugin check` output:

```python
# Form A: bare shorthand
@plugin(..., functional_group=FunctionalGroup.G5_COGNITION)

# Form B: full flat struct
@plugin(..., logic_address=LogicAddress(
    functional_group=..., control_slot=...,
    scope=..., authority=..., evidence=..., revision=...,
))
```

Both are folded into the same canonical `contract` via the back-compat shim
from PR-A (commit `5727ef5a`). They will be deleted in PR-D (2027-03-01).

`definition.logic_address` (the synthesized reader view) is a pure projection of
`definition.contract` and is the last piece to retire.

---

## What fails the plugin check (matrix)

| # | Check | Default | `--strict` |
|---|---|---|---|
| 1 | No `contract=` AND no `functional_group=` AND no `logic_address=` | warning | error |
| 2 | `contract=` uses a 10th section not in PluginContract | error | error |
| 3 | Capability grant referenced but not in your `authority.grants` | error | error |
| 4 | `observability.descriptors` not in `journal_catalog` | warning | error |
| 5 | Conflicting `layer` + `kind` + `tier` combinations | warning | error |
| 6 | Capability grant of child ⊄ parent (delegation) | error | error |

Details: `docs/architecture/plugin-check-matrix.md`.

---

## Onward

- PluginContract v2 (post‑6‑month deprecation): see ADR-0110 §十.
- The 13 群 ↔ 9 群 mapping decision is captured in `docs/architecture/functional-group-mapping.md`.
- Hard / soft matrix is in `docs/architecture/plugin-check-matrix.md`.
- If you find a check in `lca plugin check` that you cannot find any entry for in the matrix, file an issue — the matrix is the single source of truth.
