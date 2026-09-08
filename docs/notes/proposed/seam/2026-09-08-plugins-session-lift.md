# Agent Note: plugins/session/ lift plan → observability seam tree

Status: proposed

## Problem

`lca/plugins/session/` is a legacy 顶层目录 per ADR-0195 §P5-10. The directory contains 13 plugins referenced by `bundles/session-runtime.yaml` plus 3 additional utility directories (`derivers/step_tree/`, `title_llm_provider/`, `token_meter/`). These plugins span multiple semantic categories (runtime, checkpoint, projection, deriver, exporter, title, telemetry) and must be distributed to their correct seam homes in the observability tree per `docs/specs/platform-directory-architecture.md` §9.

Lifting all 16 directories in one PR is high-risk (each needs move + bundle update + import update + test update) and blocks on runtime infrastructure dependencies (many plugins import from `lca.plugins.session.runtime.*`). This note documents the full lift plan and executes one proof-of-concept lift to validate the pattern.

## Proposal

### Phase 1: Semantic mapping (this section)

For each of the 16 directories in `lca/plugins/session/`, determine the target location in the seam tree:

| # | Current directory | Bundle entry | Dependencies on `session.*` | Target seam | Rationale |
|---|---|---|---|---|---|
| 1 | `runtime/` | `lca.plugins.session.runtime` | self (internal submodules) | `lca/session/runtime/` (lift to core) | Core Session runtime: SessionStore, bus facade, spine hook, fork, resume. Per `platform-directory-architecture.md` §7, runtime submodules migrate to `lca/session/` as core infrastructure, not plugin. |
| 2 | `checkpoint_policy/` | `lca.plugins.session.checkpoint_policy` | none (only contracts + kernel) | `lca/session/lifecycle/checkpoint.py` (merge) | Already imported by `lca/session/lifecycle/checkpoint.py`. Per §7 `checkpoint.py` is core Session lifecycle, not plugin. |
| 3 | `projection_registry/` | `lca.plugins.session.projection_registry` | none visible | `lca/plugins/observability/projection/registry/` | Projection fabric is observability seam per §9 `observability/` tree. Registry is the central projection registration framework. |
| 4 | `projection_cache/` | `lca.plugins.session.projection_cache` | none visible | `lca/plugins/observability/projection/cache/` | Persistent projection cache is observability projection fabric, sibling to registry. |
| 5 | `session_model_visible/` | `lca.plugins.session.model_visible` | `runtime.messages.messages` | `lca/plugins/observability/projection/model_visible/` | Surface → messages projection is a projection unit, belongs in observability projection family. |
| 6 | `session_stats/` | `lca.plugins.session.session_stats` | none visible | `lca/plugins/observability/deriver/session_stats/` | Turn/step count fold is a deriver (pure fold from events → projection state). |
| 7 | `session_turn_outline/` | `lca.plugins.session.session_turn_outline` | none visible | `lca/plugins/observability/deriver/turn_outline/` | Turn outline fold is a deriver. |
| 8 | `token_usage/` | `lca.plugins.session.token_usage` | `runtime.messages.messages`, `token_meter.token_meter` | `lca/plugins/observability/deriver/token_usage/` | Token meter projection is a deriver. |
| 9 | `token_meter/` | NOT in bundle | none (only contracts + kernel) | `lca/plugins/observability/deriver/token_meter/` | Pure computation utility for token estimation, used by `token_usage` deriver. No plugin manifest. |
| 10 | `session_turn_control/` | `lca.plugins.session.turn_control` | none visible | `lca/plugins/observability/deriver/turn_control/` | Control-plane turn fold is a deriver. |
| 11 | `spine_anomaly/` | `lca.plugins.session.spine_anomaly` | `runtime.spine.event_projection` | `lca/plugins/observability/deriver/spine_anomaly/` | Spine anomaly detector is a deriver (observes events, detects anomalies). |
| 12 | `title_service/` | `lca.plugins.session.title_service` | none visible | `lca/plugins/observability/exporter/title/` | Title generation is an exporter (produces derived artifacts from session facts). |
| 13 | `title_llm_provider/` | NOT in bundle | none visible | `lca/plugins/observability/exporter/title/llm_provider/` | LLM title provider is a title exporter variant. |
| 14 | `telemetry_capture/` | `lca.plugins.session.telemetry_capture` | none visible | `lca/plugins/observability/exporter/telemetry/capture/` | Telemetry capture coordinator is an exporter (captures events for external systems). |
| 15 | `telemetry_otel/` | `lca.plugins.session.telemetry_otel` | none (uses `ctx.soft_get`) | `lca/plugins/observability/exporter/telemetry/otel/` | OTel telemetry backend is an exporter (exports to external OTel system). |
| 16 | `derivers/step_tree/` | NOT in bundle | none visible | Already mirrored at `lca/plugins/observability/deriver/step_tree/` | Delete legacy copy after mirror is confirmed stable. |

### Phase 2: Migration order (dependency-aware)

Plugins must be lifted in dependency order to avoid breaking imports mid-migration:

**Wave 1: Independent utilities (no intra-session dependencies)**
1. `token_meter/` → `observability/deriver/token_meter/` (proof-of-concept, executed in this PR)
2. `checkpoint_policy/` → merge into `lca/session/lifecycle/checkpoint.py` (already imported there)

**Wave 2: Projection fabric (no dependencies on runtime)**
3. `projection_registry/` → `observability/projection/registry/`
4. `projection_cache/` → `observability/projection/cache/`

**Wave 3: Derivers that depend on runtime.messages**
5. `session_model_visible/` → `observability/projection/model_visible/` (depends on `runtime.messages.messages`)
6. `session_stats/` → `observability/deriver/session_stats/`
7. `session_turn_outline/` → `observability/deriver/turn_outline/`
8. `token_usage/` → `observability/deriver/token_usage/` (depends on `runtime.messages.messages` + `token_meter`)
9. `session_turn_control/` → `observability/deriver/turn_control/`
10. `spine_anomaly/` → `observability/deriver/spine_anomaly/` (depends on `runtime.spine.event_projection`)

**Wave 4: Exporters (no dependencies on runtime)**
11. `title_service/` → `observability/exporter/title/`
12. `title_llm_provider/` → `observability/exporter/title/llm_provider/`
13. `telemetry_capture/` → `observability/exporter/telemetry/capture/`
14. `telemetry_otel/` → `observability/exporter/telemetry/otel/`

**Wave 5: Runtime core (last, most dependencies)**
15. `runtime/` → `lca/session/runtime/` (lift to core, update all consumers)
16. `derivers/step_tree/` → delete (already mirrored)

### Phase 3: Bundle updates

For each wave, update `bundles/session-runtime.yaml` `$module` paths:

```yaml
# Wave 1
- id: lca.plugins.session.token_meter  # NOT in bundle, no update needed
  $module: lca.plugins.observability.deriver.token_meter.token_meter

# Wave 2
- id: lca.plugins.session.projection_registry
  $module: lca.plugins.observability.projection.registry.projection_registry
- id: lca.plugins.session.projection_cache
  $module: lca.plugins.observability.projection.cache.projection_cache

# Wave 3
- id: lca.plugins.session.model_visible
  $module: lca.plugins.observability.projection.model_visible.session_model_visible
- id: lca.plugins.session.session_stats
  $module: lca.plugins.observability.deriver.session_stats.session_stats
- id: lca.plugins.session.session_turn_outline
  $module: lca.plugins.observability.deriver.turn_outline.session_turn_outline
- id: lca.plugins.session.token_usage
  $module: lca.plugins.observability.deriver.token_usage.token_usage
- id: lca.plugins.session.turn_control
  $module: lca.plugins.observability.deriver.turn_control.session_turn_control
- id: lca.plugins.session.spine_anomaly
  $module: lca.plugins.observability.deriver.spine_anomaly.spine_anomaly

# Wave 4
- id: lca.plugins.session.title_service
  $module: lca.plugins.observability.exporter.title.title_service
- id: lca.plugins.session.telemetry_capture
  $module: lca.plugins.observability.exporter.telemetry.capture.telemetry_capture
- id: lca.plugins.session.telemetry_otel
  $module: lca.plugins.observability.exporter.telemetry.otel.telemetry_otel

# Wave 5
- id: lca.plugins.session.runtime
  $module: lca.session.runtime.plugin.plugin
- id: lca.plugins.session.checkpoint_policy
  # Merge into lca/session/lifecycle/checkpoint.py, remove from bundle
```

### Phase 4: Test import updates

For each lifted plugin, update test imports:

```python
# token_meter (Wave 1)
# Old:
from lca.plugins.session.token_meter.token_meter import HeuristicTokenMeter, estimate_text_tokens
# New:
from lca.plugins.observability.deriver.token_meter.token_meter import HeuristicTokenMeter, estimate_text_tokens

# projection_registry (Wave 2)
# Old:
from lca.plugins.session.projection_registry.projection_registry import ProjectionRegistry
# New:
from lca.plugins.observability.projection.registry.projection_registry import ProjectionRegistry

# ... (similar pattern for all other plugins)
```

## Alternatives considered

1. **Single mega-PR lifting all 16 directories**: Rejected — high risk, hard to review, blocks on runtime dependencies. Many plugins import from `lca.plugins.session.runtime.*`, so lifting them before runtime causes circular dependencies.

2. **Lift runtime first**: Rejected — runtime has the most internal dependencies (submodules reference each other) and the most external consumers (13+ files import from `lca.plugins.session.runtime.*`). Lifting it first requires updating all consumers simultaneously, which is the high-risk scenario we're trying to avoid.

3. **Create COMPAT shims at old locations**: Rejected — AGENTS.md §4 forbids new COMPAT shims without owner and delete-when. The lift plan already has a clear delete-when (empty directory + no bundle references), so shims would add complexity without benefit.

## Acceptance criteria

- [ ] `lca/plugins/session/` directory is empty (all 16 subdirectories lifted or deleted)
- [ ] `bundles/session-runtime.yaml` has no `$module` paths containing `lca.plugins.session.*` (except runtime, which becomes `lca.session.runtime.*`)
- [ ] `rg "from lca\.plugins\.session\." lca/ tests/` returns zero hits (all imports updated)
- [ ] `pytest tests/plugins/session/` passes (tests moved to new locations)
- [ ] `pytest tests/architecture/test_platform_directory.py` passes
- [ ] `./scripts/lca-ops audit-plugin-shape` passes

## Risks

1. **Circular imports during migration**: If a plugin is lifted before its dependencies, imports break. Mitigation: strict wave ordering based on dependency analysis.

2. **Bundle references become stale**: If a `$module` path is updated but the plugin id is not, Profile resolution fails. Mitigation: update bundle and plugin id in the same commit per wave.

3. **Test fixtures break**: Some tests import from multiple plugins; lifting one mid-test causes failures. Mitigation: lift all plugins in a wave together, run full test suite after each wave.

4. **Runtime lift is the hardest**: `lca/plugins/session/runtime/` has 11 subdirectories and is imported by 13+ files. Mitigation: defer to final wave, after all other plugins are lifted and dependencies are clear.

## Consequences

- **Positive**: `lca/plugins/session/` legacy directory is eliminated, completing ADR-0195 P5-10.
- **Positive**: Each plugin is in its semantic home, making the seam tree self-documenting.
- **Positive**: Future plugins follow the seam tree pattern by default, preventing new legacy directories.
- **Negative**: Multi-wave migration requires sustained effort across multiple PRs.
- **Negative**: Runtime lift (Wave 5) is a large, complex change that may need its own ADR if scope grows.

## Verification

Proof-of-concept lift executed in this PR:

- [x] `lca/plugins/session/token_meter/` → `lca/plugins/observability/deriver/token_meter/`
- [x] Updated imports in `lca/plugins/session/token_usage/token_usage.py`
- [x] Updated imports in `tests/observability/token_meter/test_heuristic_meter.py`
- [x] Updated imports in `tests/plugins/session/test_token_usage.py`
- [x] `pytest tests/observability/token_meter/` — 3 passed
- [x] `pytest tests/plugins/session/test_token_usage.py` — 2 passed
- [x] `ruff check lca/plugins/observability/deriver/token_meter/` — exit 0
- [x] `git diff --check` — exit 0

delete-when for full lift completion:

```bash
# 1. Directory is empty
test -z "$(ls -A lca/plugins/session/ 2>/dev/null)"

# 2. Bundle has no legacy references
rg 'lca\.plugins\.session\.' bundles/session-runtime.yaml = 0

# 3. No imports from legacy paths
rg 'from lca\.plugins\.session\.' lca/ tests/ = 0
```
