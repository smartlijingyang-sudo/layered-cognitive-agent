---
name: cordis-plugin-development
description: "Author, mount, debug, and unmount Cordis plugins at runtime via the cordis_control tool. Covers PluginFactory shape, plugin_meta TypedDict (PR12), §23.2 invariant, capability grant decay (C5), and the publish-to-preset flow. Load this skill before invoking cordis_control.mount or authoring plugin source."
version: 1.0.0
---

# Cordis Plugin Development

Author and operate dynamic Cordis plugins in a running session. This skill is the
authoritative reference for the `cordis_control` tool actions (`inspect`,
`mount`, `unmount`, `publish`) and the contract that authored plugins must
satisfy before mount will succeed.

## Standard workflow

1. **Decide the plane.** A row that publishes a service belongs in **HOST**
   composition; a row that only contributes tools / persona / prompt sections
   belongs in **PRESET**. See the companion skill `editing-lca-compositions`.
2. **Inspect first.** Call `cordis_control` with `action=inspect` to see the
   current capability graph. Never infer API shape from a service name.
3. **Author the plugin source.** Write a Python file with `plugin_meta`
   (TypedDict) + `factory()` (callable). Place it under
   `$LCA_AGENT_PRESETS_HOME/<preset_id>/plugins/<plugin_name>.py`.
4. **Mount.** Call `cordis_control` with `action=mount, name=<plugin_name>,
   path=<absolute_path>` and pass `caller_grant` ⊆ your own grant.
5. **Use or assert.** Invoke the new tool, or read `ctx.own_bindings`
   (`plugin:<name>`) for non-Tool artifacts.
6. **Publish for reuse.** Call `cordis_control` with `action=publish,
   preset_id=<id>` to write `bundle.yaml` + the plugin source under
   `$LCA_AGENT_PRESETS_HOME/<preset_id>/`. Next session that loads this bundle
   auto-mounts without any `cordis_control` call.
7. **Unmount when done.** Call `cordis_control` with `action=unmount,
   name=<plugin_name>`. Unmount disposes bindings and journal-logs the event.

Do not loop on `mount` retries; if the first mount fails, read the journal
fact (`ToolInvoked` + `PluginMountRejected`) for the exact rejection reason.

## Hard invariants (PR12 + §23.2)

A mount will reject with `PluginMetaMissing` if the source file does not
declare `plugin_meta` at module level. The PR12 TypedDict lives at
`lca/contracts/harness/plugin_meta.py` and has these useful fields:

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Kebab-case plugin identifier; must match the directory name |
| `layer` | yes | One of `service / provider / behavior / guard / sensor` |
| `implements` | yes | Protocol names (`Tool`, `Sensor`, `Brain`, etc.) |
| `capabilities` | when `side_effects != none` | Grant keys required; checked against `caller_grant` |
| `side_effects` | recommended | `none / tools / memory / world` |
| `policy_class` | yes | `observe / control / execute` — controls §23.2 gating |
| `test_suite` | recommended | pytest node id prefix for inspection |
| `description` | recommended | Human-readable summary |
| `version` | optional | Semver string; surfaces in journal |

§23.2 invariant (default checker in
`lca/plugins/providers/composition_composer.py`) rejects any mount whose
`policy_class == "control"`. Tools and behaviors must declare
`policy_class=execute` or `observe`. If your plugin needs to mutate
`AgentState` or rewrite Decisions, it does not — that is `C4` of the
constitution and the mount will be rejected.

## factory() contract

```python
plugin_meta = {
    "name": "my_tool",
    "layer": "behavior",
    "implements": ["Tool"],
    "capabilities": ["tool_fs.read"],
    "side_effects": "none",
    "policy_class": "execute",
    "test_suite": "tests/test_my_tool.py",
}

def factory():
    """Return the plugin artifact.

    For a Tool: return an object implementing the Tool Protocol
    (name / description / parameters / execute / validate).
    For a Sensor: return a callable (ctx) -> None that registers
    via ctx.inject('perceive').add(...).
    For a Provider: return an object with the seam's expected interface.
    """
    class _MyTool:
        name = "my_tool"
        description = "..."
        async def execute(self, args): ...
    return _MyTool()
```

The factory may close over module-level helpers and config; it must not
perform I/O or side effects at import time. `importlib.import_module` runs
during mount and any module-level side effect will fire inside the Cordis
fiber.

## cordis_control actions

| Action | Required args | Effect |
|---|---|---|
| `inspect` | none | Returns the current capability graph: services, bindings, mounts |
| `mount` | `name`, `path` (absolute), `caller_grant` tuple | Imports module, runs `factory()`, registers binding under `plugin:<name>`; runs PR12 + §23.2 + C5 checks |
| `unmount` | `name` | Disposes binding, logs `PluginUnmounted`, returns the bound service to its previous state |
| `publish` | `preset_id`, `name` | Writes `bundle.yaml` + plugin source under `$LCA_AGENT_PRESETS_HOME/<preset_id>/`; logs `PresetPublished` |

`caller_grant` must be a subset of the calling session's grant (C5). Mount
fails fast with `CapabilityGrantExceeded` if you ask for a capability you do
not hold.

## Tool wrapping after mount

A plugin whose `factory()` returns a `Tool` Protocol object is automatically
registered with the `tools` seam when the cordis-creator profile boots. The
tool appears in the agent's `<tools>` block under its `name`. To use it
later from non-creator sessions, publish the plugin and load the bundle.

For non-Tool artifacts (e.g. a Provider returning an LLM adapter), the
binding is reachable as `ctx.own_bindings["plugin:<name>"]` only inside
the mounting scope. Cross-session access requires publish + bundle load.

## Common failure shapes

| Symptom | Cause | Fix |
|---|---|---|
| `PluginMetaMissing: plugin 'X' 缺少 plugin_meta (PR12 强制)` | Module has no top-level `plugin_meta` dict | Add `plugin_meta = {...}` at module level |
| `InvariantViolation: policy_class='control' rejected (§23.2)` | Declared `policy_class="control"` | Change to `observe` or `execute`; do not try to mutate State |
| `CapabilityGrantExceeded: requires 'X'` | Caller's grant does not include required capability | Reduce required capabilities, or request grant from the user |
| `ModuleNotFoundError` on mount | `path` is wrong or Python sys.path does not include the parent | Use absolute path; check `$LCA_AGENT_PRESETS_HOME` is on sys.path (it is, by default) |
| `ImportError: cannot import name 'X'` | factory() references an import the module does not perform | Add the import at module top; do not rely on transitive imports |

For the complete field-by-field reference, see
[`resources/plugin-meta-fields.md`](resources/plugin-meta-fields.md).

## Versioning

This skill applies to LCA v0.x with `CordisComposer` in
`lca/plugins/providers/composition_composer.py` and `PluginMeta` TypedDict in
`lca/contracts/harness/plugin_meta.py`. Schema changes to either file bump
this skill's `version` field in the frontmatter.
