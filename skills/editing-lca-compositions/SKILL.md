---
name: editing-lca-compositions
description: "Author, edit, and publish LCA compositions — bundles, profiles, presets. Covers the 5-layer unidirectional dependency rule, HOST vs PRESET plane decision, reducer-only-writes-State (C4), journal-single-source (C3), capability decay (C5), preset directory layout under $LCA_AGENT_PRESETS_HOME, and the bundle YAML entry schema. Load this skill before editing bundles/*.yaml, profiles/*.yaml, or publishing a preset."
version: 1.0.0
---

# Editing LCA Compositions

Every capability in LCA is a plugin row. Changing what an agent can do means
changing which rows are composed for it. There is no separate configuration
language.

## Off-limits

Never edit or overwrite a preset that ships with the deployment
(`bundles/scenario-*.yaml`, `profiles/web-standard.yaml`, etc.). An upgrade
overwrites that install. Copy the bundle via `lca-ops` or create a new
profile in `profiles/`.

## The two planes

**HOST composition** (`lca/layer0_infra/` and the base bundles):
- Cross-session services: llm / memory / tools / transport / sandbox / state_store / observability
- One instance for the process
- Lives in `bundles/base.yaml`, `bundles/web-app.yaml`

**PRESET composition** (a `bundles/scenario-*.yaml` or a published preset):
- Per-session contributions: tools, persona, prompt sections, role profiles
- One instance per session, mounted under that session's scope
- Lives in `bundles/scenario-cordis-creator.yaml`, `profiles/cordis-creator.yaml`, and the user-authored `~/.agent-presets/<id>/`

The rule:

> A row whose service has a consumer **outside** the agent plane cannot
> move into a preset. A preset row contributes the **tools**; the registry
> itself stays host-side.

Concretely: `lca-run-loop-driver-registry`, `lca-llm-resolver`, `lca-sandbox-*`
are host-only. `lca-tool-bash`, `lca-tool-file-write`, `lca-tool-cordis-control`
can move into a preset (and do, for cordis-creator).

## Five-layer unidirectional dependency

```
contracts → layer0_infra → layer1_cognitive → layer2_runtime → layer3_agent
                                  ↑
                            layer4_app (composition root, reads down)
```

A lower layer must not import a higher layer. `layer4_app` is the only
layer that may combine across. Enforced by `lint-imports`
(`pyproject.toml`'s import-linter contracts).

| Change | Required test scope |
|---|---|
| `contracts/` (any Protocol, dataclass, enum) | full `pytest` (closed schema, blast radius = whole repo) |
| `layer0_infra/` (any service / provider / seam) | this layer + `layer1_cognitive` + `layer4_app` |
| `layer1_cognitive/` (any primitive) | this layer + `layer2_runtime` |
| `layer2_runtime/` | this layer + `layer3_agent` |
| `layer3_agent/` | this layer only + spawn tests |
| `layer4_app/` (composition root) | spawn tests + e2e |

## Reducer-only-writes-State (C4)

No sensor / gate / body may mutate `AgentState` in place. The reducer is the
only writer. Violations:

- A sensor that returns an enriched state — wrap the enrichment as a
  `Reducer.apply_*` action instead
- A gate that toggles a flag directly — emit a `Decision` that the
  reducer translates
- A tool that patches state — return an `Observation` whose payload the
  reducer translates

If a path looks like "I need to mutate state here", the answer is: write a
new reducer action, do not bypass the gate.

## Journal-single-source (C3)

Model-visible facts must be reproducible from the journal. Every state
change goes through `SessionService.record(EventType, ...)`. A model output
that the journal cannot reproduce is a bug.

| Symptom | Likely cause |
|---|---|
| Model sees an event that is not in `read_journal()` | Direct state mutation bypassed journal |
| Two consecutive runs produce different model-visible output from identical prompts | A non-journaled side effect (file write, env var) is the source of truth instead of the journal |

## Capability decay (C5)

A child agent's `caller_grant` must be a subset of its parent's grant.
Mount, Tool invocation, and Tool call all check this. The composer enforces
it on every mount; the executor enforces it on every tool call.

Concretely: if a tool requires `["tool_fs.read", "tool_bash"]` and the
session has `["tool_fs.read"]`, the call is rejected with
`CapabilityGrantExceeded`. There is no implicit upgrade.

## Preset directory layout

```
${LCA_AGENT_PRESETS_HOME:-~/.agent-presets}/<preset_id>/
    bundle.yaml                       # bundle entry referencing the plugin module
    plugins/<plugin_name>.py          # plugin source (plugin_meta + factory)
```

`LCA_AGENT_PRESETS_HOME` env var overrides the default (`~/.agent-presets`).
The directory is plane-aware: the same env var resolves to `/mnt/data/.agent-presets`
inside a sandbox guest and to `/home/sandbox-user/.agent-presets` on the host.

`<preset_id>` must match `^[A-Za-z0-9_\-\.]{1,64}$` (alphanumeric +
dash/underscore/dot; no path-traversal characters).

`bundle.yaml` is auto-generated by release promotion through
`cordis_control` (which calls `PresetAuthoring.publish` in
`lca/layer4_app/preset_authoring.py`). Its schema:

```yaml
entries:
  - id: <plugin_id>
    name: <plugin_name>
    $module: lca_agent_presets.<preset_id>.plugins.<plugin_name>
    config:
      plugin_meta:
        name: <plugin_name>
        layer: behavior
        # ... full PluginMeta TypedDict ...
      source_path: plugins/<plugin_name>.py
      preset_id: <preset_id>
```

The module path is the `lca_agent_presets.*` namespace; boot-time injection
puts the preset root on `sys.path`. See
[`resources/preset-schema.md`](resources/preset-schema.md) for the full
entry schema and validation rules.

## Plane decision — quick test

For each row you are considering adding to a preset, ask:

1. Does it call `ctx.provide(<some_service>)`? If yes → must be HOST (or
   wrap in a group with isolate scope). A preset cannot own a service.
2. Does it consume a service the preset does not also provide? If yes →
   the consumer must stay where the provider can be reached.
3. Is it a tool, persona row, or prompt section? If yes → safe in PRESET.
4. Does it mutate `AgentState`? If yes → wrong layer entirely (C4).

When in doubt, copy `bundles/scenario-cordis-creator.yaml` and start
from there. A composition written from scratch usually forgets a host
row the consumer depends on; a copy starts loadable.

## Versioning

This skill applies to LCA v0.x. Schema changes to the bundle YAML,
preset layout, or any C3/C4/C5 invariant bump this skill's `version`
field.
