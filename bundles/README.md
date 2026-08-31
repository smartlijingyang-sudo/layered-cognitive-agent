# bundles/

Profile-bundle YAML files (Tier-1 services + Tier-2 providers + Tier-3
behaviors). Bundles are composed by `profiles/*.yaml`; boot order is derived
from each plugin's `Manifest requires → provides` (ADR-0061), not YAML line
order.

## web-app.yaml — Tier-3 web app behaviors (with Gateway transport stack)

The `bundles/web-app.yaml` bundle extends `bundles/base.yaml` with cognitive
primitives (perceive / gates / body / runtime / think / loop drivers) and
**the new Gateway transport stack (PR-4, ADR-0112 + ADR-0115)**:

| id | module | role |
|---|---|---|
| `lca-gateway-router` | `lca.plugins.transport.webserver.router` | L0 seam: provides `gateway_router` capability |
| `lca-gateway-routes-health-options` | `lca.plugins.transport.webserver.routes_health_options` | L3 provider: `/health` + OPTIONS handlers |
| `lca-gateway-routes-runs-sessions` | `lca.plugins.transport.webserver.routes_runs_sessions` | L3 provider: `/runs/*` + `/v1/sessions/*` |
| `lca-gateway-routes-openai-compat-files` | `lca.plugins.transport.webserver.routes_openai_compat_files` | L3 provider: `/v1/models` + `/v1/chat/completions` + `/v1/embeddings` + `/v1/responses` + `/files/*` |
| `lca-gateway-routes-device` | `lca.plugins.transport.webserver.routes_device` | L3 provider: `/api/device/*` + WS |

Order matters: `lca-gateway-router` must boot **before** any routes
provider because the routes plugins require the `gateway_router`
capability. The boot DAG enforces this via `requires → provides`.

See ADR-0112 (Gateway routes plugin 化修订版) and ADR-0115 (Kernel /
Transport boundary) for the design rationale.

## Other bundles

See file headers for `base.yaml`, `coding-agent-tools.yaml`,
`declarative-phase-graph.yaml`, `runtime-core.yaml`, and the
`scenario-*.yaml` family. Each scenario bundle adds only the behavior
plugins required for one named workflow.
