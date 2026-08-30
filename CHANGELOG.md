# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-08-30

### Breaking Changes (Phase 2: ADR-0104)

Per [ADR-0104](docs/adr/0104-semantic-layer-rename.md), the following layer
name renames are effective **immediately upon merge**, with **no shim or
deprecation period**:

| Old | New |
|---|---|
| `lca.layer0_infra` | `lca.infrastructure` |
| `lca.layer1_cognitive` | `lca.cognition` |
| `lca.layer2_runtime` | `lca.runtime` |
| `lca.layer3_agent` | `lca.agent` |
| `lca.layer4_app` | `lca.application` |

**Unchanged** (not renamed): `lca.contracts`, `lca.harness`, `lca.plugins`, `gateway`.

### Migration

- **Migration script**: `scripts/migrate_layer_rename.py`
  - `--report`: count references
  - `--dry-run`: preview changes
  - `--execute`: actually rename
  - `--only <layerN>`: only process specific mapping
  - `--rollback <sha>`: revert with `git revert -m 1`
- **Total references updated**: 2801
- **Total files changed**: ~1074

### Impact on external consumers

- **Profile YAML** (`profiles/*.yaml`): No changes needed. Profiles reference
  `lca.contracts.*` and `lca.harness.plugin_api`, not `lca.layer*` directly.
- **Plugin developers**: All `from lca.layer*` imports must be updated to the
  semantic names. Search and replace is safe (`lca.layer0_infra` is a unique
  prefix; no other valid identifier starts with it).
- **LobeHub patches** (`deploy/lobehub/patches/`): Already synchronized.
- **External SDK consumers** (`packages/gateway-client/`, `packages/lca-cli/`):
  Should pull latest after this release.

### Background

The numeric layer names (`layer0_infra`, `layer1_cognitive`, etc.) communicated
order but not responsibility. New contributors had to memorize the layer
sequence, then look up ADR-0001 to learn what each layer actually does. The
semantic names (`infrastructure`, `cognition`, `runtime`, `agent`,
`application`) communicate responsibility directly.

### Predecessor

ADR-0001 ("五层单向依赖分层") is preserved as historical archive but
**superseded by ADR-0104**. The five-layer structure itself is unchanged;
only the naming convention has shifted.

### Verification

- `uv run lint-imports`: 16 kept, 0 broken
- `uv run python scripts/check_package_contracts.py`: 90 packages, 0 issues
- `grep -rn "lca\.layer[0-4]_[a-z_]*"`: 0 results
- `uv run python scripts/migrate_layer_rename.py --report`: 0 remaining references

## Phase 1 (2026-08-30, completed)

- 90 packages have L1 README (9 fields) + L2 pyproject sections
- 16 import-linter contracts (5 baseline + 10 new forbidden + 1 independence
  rule deferred to Phase 2/3)
- `scripts/check_package_contracts.py` (L1↔L2↔L3↔actual import 4-way
  consistency check) with 9 passing unit tests
- CI step added to `.github/workflows/ci.yml`
- `docs/architecture/checks.md` with 24+ script index
- See [spec](../docs/superpowers/specs/2026-08-30-lca-modularization-design.md)
  and [Phase 1 plan](../docs/superpowers/plans/2026-08-30-lca-phase1-package-contracts.md)
