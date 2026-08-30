# PluginMeta TypedDict Field Reference

Authoritative schema for the `plugin_meta` declaration that every Cordis
plugin module must export at top level (PR12). Sourced from
`lca/contracts/harness/plugin_meta.py`.

## Identity

| Field | Type | Required | Meaning |
|---|---|---|---|
| `layer` | `Literal["service","provider","behavior","guard","sensor"]` | yes | Taxonomy tier (spec §3.5). Use `behavior` for plugins that contribute tools / middleware; `service` for Tier-1 seams; `provider` for Tier-2 factories; `sensor` for `PerceiveService` contributors; `guard` for DecisionGate middleware |
| `name` | `str` | yes | Kebab-case plugin identifier. Must equal the directory name when published as a preset plugin |
| `version` | `str` | no | Semver string; surfaces in journal catalog and inspect output |
| `description` | `str` | recommended | Human-readable summary; rendered by `inspect` CLI |

## Capability graph

| Field | Type | Required | Meaning |
|---|---|---|---|
| `implements` | `list[str]` | yes | Protocol names this plugin implements. Common values: `["Tool"]`, `["Sensor"]`, `["Brain"]`, `["Reasoner"]`, `["Critic"]`, `["SkillRouter"]`, `["DecisionGate"]` |
| `provides` | `list[str]` | optional | Capability keys this plugin publishes via `ctx.provide(...)`. Used by `inspect` to compute the capability graph |
| `requires` | `list[str]` | optional | Capability keys this plugin depends on. Used by DAG resolution at boot |

## Event surface

| Field | Type | Required | Meaning |
|---|---|---|---|
| `emitted_events` | `list[str]` | recommended | Journal event class names this plugin emits |
| `consumed_events` | `list[str]` | optional | Journal event class names this plugin reads |

## Context surface

| Field | Type | Required | Meaning |
|---|---|---|---|
| `context_fields` | `list[str]` | recommended | Manifest item keys this plugin produces (e.g. `clock`, `workspace_artifacts`, `skill_catalog`) |

## Security and policy

| Field | Type | Required | Meaning |
|---|---|---|---|
| `capabilities` | `list[str]` | when `side_effects != "none"` | Grant keys this plugin requires. Mount fails if `caller_grant` does not contain them (C5 capability decay) |
| `side_effects` | `Literal["none","tools","memory","world"]` | recommended | Coarse classification. `none` for pure computation; `tools` for filesystem / network; `memory` for journal / state writes; `world` for sandbox / subprocess |
| `policy_class` | `Literal["observe","control","execute"]` | yes | `observe` is read-only; `execute` performs side effects within its grant; **`control` is rejected by §23.2 default invariant** — never use this value |

## Wiring

| Field | Type | Required | Meaning |
|---|---|---|---|
| `seam_keys` | `list[str]` | optional | For middleware / guard plugins: cognitive seam keys bound to (e.g. `["think.pre"]`) |
| `test_suite` | `str` | recommended | Pytest node id prefix for this plugin. Used by the inspect CLI to link to tests |

## Minimal example

```python
plugin_meta = {
    "name": "csv_stats",
    "layer": "behavior",
    "implements": ["Tool"],
    "capabilities": ["tool_fs.read"],
    "side_effects": "none",
    "policy_class": "execute",
    "test_suite": "tests/test_csv_stats.py",
    "description": "Compute count/mean/median/std for a numeric CSV column",
}
```

## Common rejection causes

| Symptom | Likely missing/incorrect field |
|---|---|
| Mount rejects with `PluginMetaMissing` | Whole `plugin_meta` dict absent at module level |
| Mount rejects with §23.2 invariant violation | `policy_class` is `"control"` or absent |
| Mount rejects with `CapabilityGrantExceeded` | `capabilities` lists a key not in `caller_grant` |
| Inspect CLI shows no capability edges | `implements` empty or `provides`/`requires` not declared |
| Journal shows no events from the plugin | `emitted_events` empty AND the plugin forgot to call `record(...)` |
