# Event mechanism config SSOT

YAML under this tree is the **compile-time authority** for LCA observability.
Python code loads, validates, and executes; it does not hard-code field mappings.

## Layout

| Path | Schema | Role |
|---|---|---|
| `observability/spine.yaml` | EventRegistry | Category auth matrix + payload fields (ADR-0183) |
| `observability/closure_catalog.yaml` | `lca.observability.closure/1` | Per-EP layer, producer seam, consumers, durability |
| `compile/global_policies.yaml` | `lca.observability.compile/1` | Cross-layer merge policies |
| `projections/*.yaml` | `lca.observability.projection/1` | Deriver registry + binding file refs |
| `projections/bindings/*.yaml` | `lca.observability.bindings/1` | Field extract + merge rules |
| `outputs/run_artifacts.yaml` | `lca.observability.outputs/1` | Artifact paths + source projections |
| `business/*.yaml` | EventRegistry | Domain catalog events |

## Compile

```bash
uv run python scripts/verify_observability_compile_plan.py
# or (when wired): ./scripts/lca-ops observability-compile --json
```

Boot and CI run the same validator; errors block compile plan use.

## Extend

1. Add closure row in `closure_catalog.yaml` (layer + producer + consumers).
2. Register category in `spine.yaml` if new spine EP.
3. Add binding rules under `projections/bindings/`.
4. Reference projection in `outputs/run_artifacts.yaml` if new artifact.
5. Run verify script + architecture tests.

See [ADR-0198](../../../docs/adr/0198-observability-compile-graph.md).
