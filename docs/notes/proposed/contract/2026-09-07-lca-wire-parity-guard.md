# Agent Note: LCA wire-parity guard for the agent-gateway WS

Status: proposed

## Problem

PR-3 (commit `975416f0` "feat(p1): lcaGateway/ front-end WS client +
lca_runtime_agent_gateway patch") shipped `lcaConnectToGateway` that
delegated to the upstream `AgentStreamClient`. The upstream
`buildWsUrl()` (in `packages/agent-gateway-client/src/client.ts:205-214`)
hard-codes `<base>/ws?operationId=...`, which is the lobehub-native
gateway wire path. LCA's server-side WS path is locked by ADR-0200 §1
in `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/routes.py`
as `WS_PATH = "/v1/runs/{run_id}/ws"`.

The two paths never matched; chat silently fell back to the native
`/webapi/chat/<provider>` dispatch in `streamingExecutor.ts` because
`isLcaGatewayMode()` defaults to false when `NEXT_PUBLIC_LCA_GATEWAY_URL`
is unset, and `isLcaGatewayMode()` was unset in `.env.lca`. The LCA WS
path was never exercised end-to-end.

PR-3's L3 e2e suite (commit `29a7637d`) covered the server side using
a Python test client (`tests/e2e/p1/_lca_gateway_client.py`) that
bypassed the front-end entirely. Server-side wire was correct; the
TS front-end was a silent dead path.

The two surfaces that must align:

| Surface | Owner | Value |
|---|---|---|
| Server WS path | `lca/.../wire/routes.py` | `/v1/runs/{run_id}/ws` |
| Front WS URL builder | `lcaGateway/LcaAgentStreamClient.ts` | `${base}/v1/runs/${runId}/ws` |

## Why a guard

Reusing native vendored libraries is fine in general (ADR-0200 §6.1.2
forbids patching `lobehub-ui/packages/*` source). It is not fine when
the reused library pins a wire URL that belongs to a different
server. Reusing `AgentStreamClient` while assuming it would honour
ADR-0200 §1 was the failure mode; nothing in the patch boundary
checked the assumption.

## Decision

1. LCA's front-end WS client is a hand-rolled transport
   (`LcaAgentStreamClient.ts`) with the URL path hard-coded against
   the SSOT. It exports the same `on/off/connect/disconnect/sendInterrupt/sendToolResult/updateToken`
   surface as the upstream client so `createLcaGatewayEventHandler`
   (a re-export of the upstream event handler) keeps working.
2. `audit_lca_legacy_path.py` adds a `forbidden_imports` rule that
   fails CI on any value import of `AgentStreamClient` inside
   `lcaGateway/*`. Type-only imports of event shapes
   (`AgentStreamEvent`, `ConnectionStatus`, `AgentStreamClientEvents`)
   remain allowed — those mirror the wire schema in
   `lca/contracts/transport/`.
3. `streamingExecutor.ts` (patched by `lca_runtime_agent_gateway.py`)
   throws explicitly when `isLcaGatewayMode()` is false instead of
   silently falling through to `GeneralChatAgent`. Native
   `/webapi/chat/<provider>` dispatch becomes unreachable from
   LCA's runtime.
4. A new architecture test
   (`tests/architecture/test_lca_wire_parity.py`) reads
   `routes.py:WS_PATH` and asserts:

   - The literal is exactly `/v1/runs/{run_id}/ws`.
   - `LcaAgentStreamClient.ts` still references `/v1/runs/`.
   - No value-import of the upstream `AgentStreamClient` class
     exists inside `lcaGateway/*`.

## Alternatives considered

- **Server-side reverse proxy**: ASGI middleware that rewrites
  `/ws?operationId=<id>` → `/v1/runs/<id>/ws`. Rejected: would change
  ADR-0200 §1 server-side SSOT to accommodate a client that should
  never have been used here. SSOTs flow from server → client, not the
  other way.
- **Patch the upstream `AgentStreamClient.buildWsUrl()`**: rejected
  by ADR-0200 §6.1.2 ("patch modules only insert `/* LCA-P1: <purpose> */`
  marker, do not modify native exports").
- **Trust `lcaConnectToGateway` to wrap `AgentStreamClient` correctly
  by validating URL pre-connect**: rejected; would still ship a wire
  mismatch that the test gate would have to police on every call. The
  transport itself must be aligned at construction time.

## Migration plan

- This note is the PR boundary. Same PR closes:
  - `lcaGateway/LcaAgentStreamClient.ts` (new)
  - `lcaGateway/connect.ts` (return LCA client, drop native
    `AgentStreamClient` value import)
  - `deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py`
    (`_RUN_BLOCK` adds hard fail; `_NEW_FILES` adds the LCA client)
  - `lobehub-ui/src/features/LcaHostConsole/index.tsx` + matching
    `deploy/lobehub/patches/ui/host_console.py` + `LcaHostConsole.tsx`
    (env gate on `NEXT_PUBLIC_LCA_HOST_CONSOLE`)
  - `deploy/lobehub/.env.lca` (`NEXT_PUBLIC_LCA_GATEWAY_URL` injected)
  - `scripts/audit_lca_legacy_path.py` (forbidden_imports rule)
  - `tests/architecture/test_lca_wire_parity.py` (new)
  - `lca/infrastructure/cli/services/lobehub/lobehub.py`
    (`_child_env()` injects `NEXT_PUBLIC_LCA_GATEWAY_URL` /
    `NEXT_PUBLIC_LCA_HOST_CONSOLE` into the bun subprocess env so
    vite's DefinePlugin sees them at dev start; `_ensure_env()` writes
    the same values to `lobehub-ui/.env` as a fallback for manual
    `bun run dev:*`)
  - `tests/infrastructure/cli/test_lobehub_child_env_lca.py` (new — pins
    `_child_env()` contract)
- Delete-when (the audit exit 0 + the wire parity test pass is the
  gate that tells future maintainers the guard is in place; removal
  must touch ADR-0200 §1 + routes.py in the same commit).

## Verification

- `python scripts/audit_lca_legacy_path.py` exits 0.
- `pytest tests/architecture/test_lca_wire_parity.py
  tests/infrastructure/cli/test_lobehub_child_env_lca.py -q` exit 0.
- Manual: `./scripts/lca-ops lobehub restart` produces a vite dev
  process whose environment contains `NEXT_PUBLIC_LCA_GATEWAY_URL`
  (`cat /proc/$(pgrep -f vite)/environ | tr '\0' '\n' | grep
  NEXT_PUBLIC_LCA`).
- Manual: with `NEXT_PUBLIC_LCA_GATEWAY_URL` unset, opening chat
  throws the hard-fail error (no `/webapi/chat/<provider>` network
  call observed in the browser devtools network panel).
- Manual: with `NEXT_PUBLIC_LCA_GATEWAY_URL` set to the LCA kernel
  serve WS base, chat opens a WebSocket to
  `<base>/v1/runs/<run_id>/ws`, not to `/ws?operationId=...`.