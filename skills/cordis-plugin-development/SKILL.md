---
name: cordis-plugin-development
description: "Author, validate, inspect, promote, and retire Cordis plugin Artifacts with the four-face cordis_control tool. Use before authoring plugin source or invoking Creator control."
version: 2.0.0
---

# Cordis Plugin Development

Use the closed Creator lifecycle: **inspect → author → validate → promote**.
`mount`, `unmount`, `stage`, `retire`, and `publish` are not Creator actions.
Composer mounting and unmounting are internal effects of `promote`.

## Workflow

1. Call `cordis_control` with `action=inspect` before changing the capability graph.
2. Write a Python source file containing top-level `plugin_meta` and `factory()`.
3. Call `action=author, name=<plugin_name>, path=<absolute_path>` to create a DRAFT Artifact.
4. Call `action=validate, name=<plugin_name>` to transition DRAFT → VERIFIED.
5. Call `action=promote, name=<plugin_name>` to transition VERIFIED → ACTIVE and mount through Composer.
6. For a reusable preset, add `target_scope=release, preset_id=<id>` to promote.
7. Retire an ACTIVE Artifact with `action=promote, name=<plugin_name>, rollback=true`.

Do not blindly retry a rejected promotion. Inspect the `PluginMountRejected` journal fact and correct the stated invariant, metadata, or grant error.

## Required source shape

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
    class MyTool:
        name = "my_tool"
        description = "..."
        async def execute(self, args): ...
    return MyTool()
```

The factory must not cause I/O at module import time. `author` loads the source; module-level effects therefore execute inside the Cordis fiber.

## Action contract

| Action | Required arguments | State/effect |
|---|---|---|
| `inspect` | none | Reads the current capability graph and known Artifacts. |
| `author` | `name`, absolute `path` | Creates DRAFT after source and metadata load. |
| `validate` | `name` | Checks the authored source and transitions DRAFT → VERIFIED. |
| `promote` | `name`; optional `target_scope`, `preset_id`, `rollback` | VERIFIED → ACTIVE mounts through Composer; release writes a preset; `rollback=true` performs ACTIVE → RETIRED. |

`caller_grant` must cover the Artifact capabilities (C5). Promotion enforces PR12 metadata and §23.2 invariants before binding anything.

## Common failures

| Symptom | Cause | Remedy |
|---|---|---|
| `PluginMetaMissing` | No valid top-level `plugin_meta`. | Define all required metadata. |
| `InvariantViolation` | `policy_class="control"` or conflicting composition. | Use `observe`/`execute` or revise the design. |
| `CapabilityGrantExceeded` | Artifact requests a capability absent from caller grant. | Reduce requirements or obtain the grant. |
| Source load/import error | Invalid source path or unresolved import. | Use an absolute path and declare imports. |
| Artifact is not `verified` | `promote` was called before validation. | Execute `validate` first. |

See [`resources/plugin-meta-fields.md`](resources/plugin-meta-fields.md) for metadata details.
