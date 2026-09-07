# External Plugin Trust Rubric (ADR-0199 Phase 5)

> **Status:** Living — owned by [ADR-0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) Phase 5.
> **Audience:** Plugin authors + operators deciding where a plugin runs.
> **Rule:** Every external plugin gets ONE `ExternalPluginKind`. The kind drives runtime isolation, not the plugin's contract.

## 0. Why a rubric?

Per [ADR-0199 §3.4](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md#34-pluginorigin--trust-model):
plugins with `source` in `{"project", "pip"}` default to `untrusted` and disabled. The runtime cannot silently admit them — they need explicit profile provenance + a runtime isolation tier.

This rubric answers: **once a plugin is admitted, where does it run?**

## 1. The four trust tiers

| Kind | Process boundary | Latency | Trust level | Default for | Privileges allowed |
|---|---|---|---|---|---|
| `inprocess` | shared cordis fiber (trusted core) | low | core / trusted | bundled, user | full privilege set |
| `mcp` | Model Context Protocol (separate process) | medium | untrusted | pip mcp-served tools | tool invocations only |
| `sandbox` | OS-level sandbox (e.g. Firecracker / gVisor) | high | untrusted | project plugins needing local file/network | restricted privilege set |
| `worker` | Separate Python worker (subprocess) | medium | trusted / untrusted | plugins needing full Python but isolated memory | full privilege set with audit log |

## 2. Decision matrix

| Plugin wants... | Trust tier | Why |
|---|---|---|
| `journal.append` | inprocess or worker | core capability; sandbox cannot hold the journal |
| `network.egress` | mcp or sandbox | both isolate network via OS boundary |
| `state.write` | inprocess | Reducer 单写 invariant — only inprocess reducers can write |
| `tools.<domain>` | mcp or inprocess | tools are the canonical mcp use case |
| `process.spawn` | sandbox only | OS-level isolation required |
| `fs.write` (outside workspace) | sandbox only | workspace-local writes can be inprocess |

## 3. Manifest declaration

Plugins declare their preferred kind in `manifest.yaml`:

```yaml
id: my-plugin
kind: provider
runtime:
  external_kind: mcp   # one of: inprocess | mcp | sandbox | worker
privileges:
  - tools.search
  - network.egress
```

`runtime.external_kind` is **advisory**; the operator decides the actual
runtime isolation tier via Profile provenance. Plugins declared with
`external_kind` other than `inprocess` MUST NOT run in the cordis fiber.

Per ADR-0199 I-HPC-11: default for `project` / `pip` source is `mcp`
unless explicitly overridden.

## 4. Operator profile provenance

```yaml
# profiles/my-deployment.yaml
plugins:
  - id: my-plugin
    external_kind: sandbox   # operator override
    enabled_by: profiles/my-deployment.yaml
    trust: untrusted
```

The `external_kind` here is the operator's decision; it overrides the
plugin author's advisory.

## 5. Audit / discovery

- `lca.harness.diagnostics.doctor.PluginShapeDoctor` emits
  `DOC-TRUST-*` findings when a plugin's `external_kind` conflicts
  with its privilege declarations (e.g. `network.egress` without
  `external_kind in {mcp, sandbox}` → DOC-TRUST-001).
- `lca-ops doctor plugin <path>` audits a single plugin's kind vs
  privileges before the author submits a PR.

## 6. Failure model

| Failure | Detection | Recovery |
|---|---|---|
| Plugin declared `inprocess` but uses `network.egress` | setup fail-loud (I-HPC-5 / AuditedPluginContext) | operator relocates via profile |
| Plugin declared `mcp` but tries `journal.append` | setup fail-loud | operator admits via worker or inprocess |
| Sandbox crashes mid-execution | health check + restart | task retry with backoff |

## 7. Cross-references

- [ADR-0199 §3.4 PluginOrigin & trust model](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md#34-pluginorigin--trust-model)
- [ADR-0199 §10 Phase 5 external plugin isolation](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md#10-分阶段实施计划)
- [Implementation plan §8 P5-01..P5-06](../specs/0199-implementation-plan.md#8-p5--external-plugin-trust)
- [ExternalPluginKind contract](../contracts/runtime/trust.py) (P5-02)
