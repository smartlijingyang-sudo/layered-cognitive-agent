# profiles/

Profile YAML files: each profile composes bundles (via the `bundles:` list)
and applies `patch:` overrides on top of the resolved Manifest. The default
profile is **`profiles/web-standard.yaml`**; it is the production target for
the web app (gateway + lobehub) deployment.

## web-standard.yaml — default production profile

```yaml
bundles:
  - bundles/base.yaml                # Tier-1 services + Tier-2 providers
  - bundles/web-app.yaml             # Tier-3 behaviors + transport stack
  - bundles/scenario-cordis-creator.yaml
  - bundles/declarative-phase-graph.yaml

patch:
  - id: lca-llm-resolver
    config:
      default_model: qwen3.7-plus
      load_dotenv: true
```

The resolved bundle list now picks up the new transport plugins
(`lca-gateway-router` + 4 routes providers) from `bundles/web-app.yaml`
(PR-4) and the boot event observability from
`bundles/declarative-phase-graph.yaml` (PR-3).

## New in PR-1 ~ PR-5

- **Bundles**: same `web-app.yaml` now wires `lca/plugins/transport/`
  (5 plugins — see `bundles/README.md`). Boot order is enforced by the
  `Manifest requires → provides` DAG, not YAML line order.
- **Startup trace**: `lca-kernel/` now emits typed journal events
  (`BootProfileResolved`, `BootPluginFiberSpawned`, `BootObservabilityAssembled`)
  on the resolved boot DAG. Inspect via:
  - `./scripts/lca-ops inspect-tree profiles/web-standard.yaml`
  - `./scripts/lca-ops kernel-compose profiles/web-standard.yaml --json`
- **Process lifecycle + env whitelist**: `lca/infrastructure/env/` layers
  boot-time env filtering through `BOOTSTRAP_NAMES` (whitelist / prefix /
  forbidden) per ADR-0117 K7. The default profile inherits the layer.
- **Default ctx**: `lca.application.default_context.set_default_ctx` is
  deprecated (target retire 2027-02-28); the new path is to call
  `lca_kernel.run_kernel()` explicitly and pass the returned ctx as
  `Agent(scope=...)` / `Team(scope=...)`.
- **Kernel subcommands**: `./scripts/lca-ops kernel {boot,serve,stop,compose}`
  are now available; full HMR / K8 wiring lands in ADR-0118.

## Run a profile

```bash
# Inspect the resolved plugin tree (no boot)
./scripts/lca-ops inspect-tree profiles/web-standard.yaml

# Dump the resolved redacted Manifest
./scripts/lca-ops dump-profile profiles/web-standard.yaml

# Boot a profile (no webserver transport)
./scripts/lca-ops kernel-boot profiles/web-standard.yaml

# Boot a profile + compose the CompiledRunPlan
./scripts/lca-ops kernel-compose profiles/web-standard.yaml --json

# Boot + serve via Starlette (the production entry point)
uvicorn gateway.app:create_app --factory
```

Other profiles in this directory are specialized: `coding-agent.yaml`,
`cordis-creator.yaml`, `genai-traced.yaml`, `self-improving-minimal.yaml`,
`test-minimal.yaml`, `web-standard-continuous.yaml`, `web-standard-recovery.yaml`.
