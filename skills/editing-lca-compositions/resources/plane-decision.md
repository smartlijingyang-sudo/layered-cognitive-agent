# Plane Decision Quick Reference

Sourced from `docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`
§13.1 + §13.2.4 (HOST vs AGENT PRESET) and §2.1 (5-layer dependency).

## Decision tree

```
Is the row's service consumed outside the agent plane?
├── YES  → HOST composition. Do not move into a preset.
└── NO   → Can the row live in PRESET?
          ├── Does it call ctx.provide(...) for a brand-new service?
          │   ├── YES → HOST, OR wrap in a group with isolate scope.
          │   └── NO  → Safe in PRESET.
          └── Does it consume a service the preset does not provide?
              ├── YES → Will not resolve; move to HOST.
              └── NO  → Safe in PRESET.
```

## Concrete examples

| Row | Plane | Reason |
|---|---|---|
| `lca-llm-resolver` | HOST | Sole owner of LLM credentials and chat adapter; consumed by every session |
| `lca-sandbox-*` | HOST | Cross-session sandbox pool |
| `lca-run-loop-driver-registry` | HOST | One instance process-wide |
| `lca-tool-bash` | HOST (default) | Multiple sessions share the tool registry |
| `lca-tool-file-write` | HOST (default) | Same reason as `bash` |
| `lca-tool-cordis-control` | PRESET (cordis-creator only) | Creator-specific; no other session needs it |
| `lca-role-cordis-creator` | PRESET (cordis-creator only) | Persona is per-session |

## Anti-patterns

| Pattern | Why wrong |
|---|---|
| Move `lca-llm-resolver` into `scenario-cordis-creator.yaml` | Two sessions both mount the same LLM resolver → second one collides on the seam key |
| Add a new `lca-tool-foo` to the host composition for a single persona | Bloats the tool catalog for every other session; use PRESET |
| Wrap a host-side row in a preset group | The consumer outside the preset cannot resolve the provider |
| Put `lca-event-descriptor-registry` in a preset | Event descriptor catalog is process-wide |

## Layer check

Before writing to any layer, confirm the dependency direction:

```
contracts     → no imports of any LCA layer
layer0_infra  → may import contracts
layer1_cognitive → may import contracts, layer0_infra
layer2_runtime → may import contracts, layer0_infra, layer1_cognitive
layer3_agent   → may import contracts, layer0_infra, layer1_cognitive, layer2_runtime
layer4_app     → may import any layer (composition root only)
```

If a file in `layerN` imports from `layerM` where `M > N`, the import-linter
rejects. Use `: import-linter` to verify:

```sh
uv run lint-imports
```

## Reducer boundary

| Writes AgentState? | Allowed? | How |
|---|---|---|
| `Reducer.apply_*` | yes | The only writer |
| Sensor / Gate / Body in-place mutation | NO | Wrap as a reducer action |
| Tool that mutates state directly | NO | Return an Observation; reducer translates |
| Plugin that hooks `agent.*` to rewrite Decisions | NO | C4 boundary; runtime rejects |

## Capability boundary

| Operation | Required capability |
|---|---|
| `cordis_control.mount` with `capabilities: ["tool_fs.read"]` | caller must have `tool_fs.read` |
| `cordis_control.publish` (writes to `$LCA_AGENT_PRESETS_HOME`) | caller must have `file_write` |
| `bash.run` (subprocess) | caller must have `tool_bash` |
| `file_write.write` | caller must have `tool_fs.write` |

Capability decay (C5) is enforced at every boundary. A child agent can
never gain a capability the parent does not have, regardless of what the
child's profile declares.
