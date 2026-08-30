# ADR-0108: Phase D (CI gates) + Phase E (README + cleanup) closeout

## 状态
Accepted

## 日期
2026-08-30

## 所有人
@lca-maintainers

## 依赖
ADR-0105 §12.4-12.5, ADR-0106 §10

## Context

After Phase B (split) and Phase C (rename) landed, the package-organization
discipline spec ([ADR-0105 §12][ad0105]) still requires two more phases:

1. **Phase D (§12.4)**: encode the rules as runnable CI gate scripts.
2. **Phase E (§12.5)**: clean up legacy `helpers.py / utils.py / misc.py`
   residue and fill the auto-generated `README.md` placeholders for
   high-exposure packages.

[ad0105]: ../specs/package-organization-discipline.md

## Decision

### Phase D: 8 CI gate scripts

The following scripts in `scripts/` enforce the rules from §11:

| Script | Rule | Cap |
|---|---|---|
| `check_package_size.py` | Each package ≤ 8 .py files | 8 |
| `check_no_barrel_glob.py` | Forbid `from X import *` in `__init__.py` | strict |
| `check_no_utility_modules.py` | Reject `*util*` / `*helper*` / etc. | per `_filename_rules` |
| `check_package_noun.py` | Directory names are domain nouns | regex |
| `check_known_abbrev.py` | Token abbreviations on whitelist | per APPROVED_ABBREV |
| `check_package_integrity.py` | `__init__.py` has explicit `__all__` | strict |
| `check_tests_layout.py` | `tests/<dir>/` mirrors `lca/<dir>/` | allowlist |
| `check_readme_filled.py` | No scaffold `{{placeholder}}` text | strict |

Exemptions are declared per-package via the existing
`pyproject.toml [tool.lca.package_contracts.<pkg>]` block, adding a
new `filename_whitelist = [...]` field. Five legitimately-large
packages received their whitelist entries this commit:

- `lca.infrastructure.sandbox` (sandbox) — split off subdomain one day
- `lca.infrastructure.skills` (skill_catalog) — split off registry soon
- `lca.plugins.composer.runtime` (4 fixture_*) — test-only inputs
- `lca.plugins.control_contributions` (control) — historical seam
- `lca.plugins.phase_graph` (common) — cross-cluster helpers
- `lca.runtime` (runtime) — split to L0/L1/L2/L3 subpackages next refactor

### Phase D: CLI runner

The new `diagnose package-organization` command (typer sub-app in
`lca/infrastructure/cli/commands/package_organization.py`) chains all
eight gates. It is registered in `cli.py` and exposed as the
`./scripts/lca-ops diagnose-package-organization` CLI:

```bash
./scripts/lca-ops diagnose-package-organization                  # all gates
./scripts/lca-ops diagnose-package-organization --gate readme     # one
./scripts/lca-ops diagnose-package-organization --verbose         # full output
```

The runner exits 0 if every gate passes, 1 otherwise. Output is
`stdout`-friendly for direct CI consumption.

### Phase D: CI integration

A new step was added to `.github/workflows/ci.yml`:

```yaml
- name: Package organization gates (Phase D — advisory)
  run: uv run python -m lca.infrastructure.cli.cli diagnose-package-organization --verbose || echo "::warning::package-organization gates reported issues"
```

The `|| echo "::warning::..."` is intentional for the first rollout —
we want the report but no merge blocker until the existing violations
are triaged. Once every gate passes cleanly, the fallback can be
removed.

### Phase E: helpers / utils / misc cleanup

Audit shows the codebase has **no `helpers.py` / `utils.py` / `misc.py`
modules** in `lca/` (Phase B's directory splits eliminated them all).
The only candidate is `lca/plugins/phase_graph/common.py`, which is a
domain-specific name (helper routines shared across the phase-graph
executor family) and stays. No further rename required.

### Phase E: README filling

Auto-generated README scaffold (still present in `scaffold_package_readme.py`)
contains placeholder tokens like `{{inputs}}` / `{{outputs}}` /
`{{failure_semantics}}`. `check_readme_filled.py` rejects any README
that still has these tokens. This commit filled **82 README files**
across `lca/` using a one-shot AST-driven script that introspected each
package's `__init__.py` for `__all__`, walked the directory for module
names, and pulled `allowed_dependencies` / `forbidden_dependencies`
from `pyproject.toml`. The 5 spec-named "high-exposure" packages
(`lca/contracts`, `lca/infrastructure/observability`, `lca/plugins/composer`,
`lca/cognition/brain`, `lca/harness/declarative`) received curated
descriptions; the other 77 received a generic but accurate description
plus the auto-extracted module list.

The fill script is not committed (one-shot), but the resulting READMEs
are reproducible from the source: every section maps 1-to-1 with
data already in the repo (`pyproject.toml` + `__init__.py`).

## Consequences

Positive:

- The 8 gates surface real findings on the current tree (~28 size
  violations, ~10 utility-modules flags, ~115 abbreviation hits, etc.).
  None of these block CI today (advisory step), but they now show up
  in PR conversations and `lca-ops diagnose` output.
- README coverage: 0/82 → 82/82. New contributors can read a real
  description instead of scaffold placeholders.
- CLI + CI integration is in place for tightening the gates later.

Negative:

- The Phase-D gates **report** failures but do not yet **enforce**.
  Intentional — converting each to a blocking step requires triaging
  the existing 100+ findings, which is out of scope for this commit.
- 82 READMEs were filled in one pass with a generic template for most
  packages; a follow-up should hand-curate the 5 high-exposure ones
  (already done for 5), plus 10-20 more that downstream users look at
  first.
- The fill script does not currently detect renamed subpackages, so
  any future rename will need to re-run the fill. Acceptable for one-
  shot use; the script lives in `/tmp/` and is intentionally not in
  the repo.

## References

- [ADR-0105 §12.4-12.5 — Phase D / E plan][ad0105]
- [ADR-0106 §10 — naming constitution][ad0106]
- `scripts/check_package_size.py` and 7 siblings
- `lca/infrastructure/cli/commands/package_organization.py`
- `.github/workflows/ci.yml` (package-organization step)
- 82 freshly filled `README.md` files

[ad0105]: ../specs/package-organization-discipline.md
[ad0106]: 0106-naming-constitution.md
