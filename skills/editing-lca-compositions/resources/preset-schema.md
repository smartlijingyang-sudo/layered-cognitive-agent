# Preset Bundle YAML Schema

Authoritative schema for the `bundle.yaml` file inside an LCA preset.
Sourced from `lca/layer4_app/preset_authoring.py:_build_bundle_yaml`.

## Top-level shape

```yaml
entries:
  - id: <plugin_id>
    name: <plugin_name>
    $module: <python module path>
    config:
      plugin_meta: {...}        # PluginMeta TypedDict
      source_path: <rel path>   # relative to preset root
      preset_id: <preset_id>
```

`entries` is a list. Each entry has exactly one plugin source. Multiple
plugins in one preset = multiple entries.

## Field reference

| Field | Required | Format | Meaning |
|---|---|---|---|
| `id` | yes | kebab-case string | Plugin instance id; unique within the preset |
| `name` | yes | kebab-case string | Plugin name; must equal the directory name under `plugins/` |
| `$module` | yes | dotted Python path | Importable module path. Auto-generated form: `lca_agent_presets.<preset_id>.plugins.<plugin_name>` |
| `config.plugin_meta` | yes | PluginMeta TypedDict | Full plugin metadata (see cordis-plugin-development skill, resources/plugin-meta-fields.md) |
| `config.source_path` | yes | POSIX path | Path to the `.py` file, relative to preset root. Convention: `plugins/<plugin_name>.py` |
| `config.preset_id` | yes | kebab-case string | Parent preset id; must match the directory name |

## Validation rules

| Rule | Where enforced | Symptom when violated |
|---|---|---|
| `<preset_id>` matches `^[A-Za-z0-9_\-\.]{1,64}$` | `PresetAuthoring.publish` (`_SAFE_ID`) | `ValueError: preset_id 非法` |
| Plugin module path resolves on `sys.path` | boot loader | `ModuleNotFoundError` |
| `plugin_meta` is non-empty dict | `CordisComposer.mount` (PR12) | `PluginMetaMissing` |
| `plugin_meta.policy_class != "control"` | `build_default_invariant_checker` (§23.2) | `InvariantViolation` |
| `caller_grant` ⊇ `plugin_meta.capabilities` | mount (C5) | `CapabilityGrantExceeded` |
| `plugin_meta.name` matches directory name | `sanitize_skill_id` / convention | `IllegalSkillId` (when treated as skill) |

## Generation vs hand-authoring

`PresetAuthoring.publish` is the only writer. Hand-authoring is allowed for
fixtures and tests, but the publish flow always regenerates the YAML to
match what is actually on disk — a hand-authored YAML will be overwritten
on the next `cordis_control.publish`.

## Reading path on disk

```python
from lca.layer4_app.preset_authoring import PresetAuthoring

layout = PresetAuthoring.publish(
    preset_id="my-preset",
    plugin_name="csv_stats",
    plugin_id="csv-stats-v1",
    plugin_source=open("csv_stats.py").read(),
    plugin_meta={"name": "csv_stats", ...},
)
# layout.bundle_path, layout.plugin_path are absolute Paths
```

## Examples

### Minimal preset (one tool)

`~/.agent-presets/csv-stats/bundle.yaml`:

```yaml
entries:
  - id: csv-stats
    name: csv_stats
    $module: lca_agent_presets.csv-stats.plugins.csv_stats
    config:
      plugin_meta:
        name: csv_stats
        layer: behavior
        implements: ["Tool"]
        capabilities: ["tool_fs.read"]
        side_effects: none
        policy_class: execute
        test_suite: tests/test_csv_stats.py
      source_path: plugins/csv_stats.py
      preset_id: csv-stats
```

`~/.agent-presets/csv-stats/plugins/csv_stats.py`: see
`tests/test_cordis_creator_real_scenario.py` for a working end-to-end
example (csv_stats computing mean / median / std for `monthly_total`).

## Common failure shapes

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: lca_agent_presets.<id>.plugins.<name>` | Preset root not on `sys.path` | Boot-time injection must include the preset root; check `lca/harness/profile/boot.py` |
| Mount rejects with `PluginMetaMissing` | `plugin_meta` absent from `.py` | Add `plugin_meta = {...}` at module top |
| `IllegalSkillId` on skill-side | `preset_id` contains `..` or `/` | Strip to alphanumeric + dash/underscore/dot |
| Bundle loads but no tools appear | `factory()` returned None or wrong type | Verify `factory()` returns an object with `name` attribute matching the manifest |
