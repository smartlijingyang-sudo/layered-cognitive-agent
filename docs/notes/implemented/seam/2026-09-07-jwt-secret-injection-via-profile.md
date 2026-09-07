# Agent Note: JWT secret injection via the webserver Profile seam

Status: implemented

## Problem

`lca/plugins/transport/webserver/handlers/runs/terminal/streaming/auth.py`
historically loaded the RS256 signing key by calling
`os.environ.get("LCA_JWT_SECRET")` (and `LCA_JWT_PUBLIC_KEY` for the
verification path). Two violations of AGENTS §4 follow from this:

1. **Plugin reads `os.environ` directly.** The standing rule is "密钥只能经
   Profile `{from_env: ...}` 进入;插件不得自行读取 `os.environ`."
2. **Boot path silently degrades to 500.** When the kernel process is
   started without `LCA_JWT_SECRET` (e.g. local dev where the env was
   never exported), `mint_user_jwt` raises
   `InvalidTokenError("LCA_JWT_SECRET not set")` from inside the
   `POST /runs` handler. Starlette's default exception handler converts
   the raise to a generic `500 Internal Server Error`, while `/health`
   keeps answering 200 because it does not touch the auth path. The
   result is a "service looks healthy but every chat returns 500"
   failure mode that took a 30-minute manual trace to disambiguate.

The agent-gateway WS handshake has the same defect on the verify side:
`_load_public_key` reads `LCA_JWT_PUBLIC_KEY` directly, so the
WS-handshake path becomes unbootable for the same reason.

## Decision

The JWT keypair is injected through the `webserver.jwt_keys` capability
seam; `os.environ` is no longer read by any webserver plugin. The
concrete shape:

1. **New plugin `lca-webserver-jwt-keys`** lives at
   `lca/plugins/transport/webserver/jwt_keys_seam/jwt_keys.py`. It accepts
   a `JwtConfig` with three resolution paths, in order:
   - `private_pem` / `public_pem` — literal PEM string **or**
     `{from_env: NAME}` reference (the harness resolves `from_env` to a
     string before the plugin setup runs; see
     `lca/harness/profile/plan/declarations.py:expand_env_refs`).
   - `dev_mode: true` — generate a fresh RS256-2048 keypair in-process.
     The keypair is valid only for the lifetime of the kernel process;
     WS clients reconnect on the next restart.
   - Both missing → plugin setup raises `RuntimeError` so the kernel
     fails fast at boot instead of producing a half-functional server.
2. **`auth.py` no longer reads `os.environ`.** `_load_private_key` and
   `_load_public_key` are deleted; `mint_user_jwt` /
   `verify_user_jwt` require an explicit PEM argument and raise
   `JwtSecretUnconfiguredError` (a subclass of `InvalidTokenError`) when
   the argument is empty.
3. **`render_create_run_receipt` translates the missing-key error into
   a 503.** `command_endpoints.py` reads `request.app.state.jwt_keys`
   (installed by `lca-webserver-bootstrap` from
   `carrier_ctx.inject("jwt_keys")`) and catches
   `JwtSecretUnconfiguredError` to return
   `{"error":{"code":"jwt_secret_unconfigured","message":"..."}}`
   with status 503.
4. **`bundles/web-app.yaml` registers the new plugin** with
   `dev_mode: true` so the current local-dev path keeps working without
   any environment setup. Production profiles override with
   `private_pem: {from_env: LCA_JWT_SECRET}` and
   `dev_mode: false`.
5. **`lca-ops kernel-restart` preflight** lives at
   `lca/infrastructure/cli/services/kernel/serve.py:_preflight_jwt_secret`
   and reads the active Profile before spawning the kernel:
   - `dev_mode: true` and no PEM → print a `[WARN]` line so the operator
     knows dev keys rotate on every restart.
   - Neither `dev_mode` nor `private_pem.from_env` with the env var
     actually set → refuse to spawn, print an `[ERROR]` line with the
     missing env name, return `False`.
6. **Debug runbook** at `docs/debug/README.md#post-runs-500` documents
   the reproduction curl, the traceback keyword, and the two-step fix.

## Wire contract

| Caller | Receives |
|---|---|
| `lca.plugins.transport.webserver.jwt_keys_seam.jwt_keys.setup` | `PluginContext.provide("jwt_keys", JwtKeys)` — only path that puts a keypair on `app.state`. |
| `render_create_run_receipt(receipt, agent, jwt_keys=...)` | 202 envelope with `ws_token` (dev-mode or env-injected) **or** 503 with `code="jwt_secret_unconfigured"` when `jwt_keys` is `None`. |
| `verify_user_jwt(token, public_key_pem=...)` | Decoded payload **or** `JwtSecretUnconfiguredError` when `public_key_pem` is empty. |

The `mint_user_jwt` / `verify_user_jwt` public signatures already accept
the `private_key_pem` / `public_key_pem` keyword; this proposal only
changes the default behaviour when the keyword is missing.

## Alternatives considered

### Why not keep the env-direct path and only fix the 500?

The 500 is the symptom; the env-direct read is the cause. Patching the
handler to return a 4xx on `InvalidTokenError("LCA_JWT_SECRET not set")`
still leaves the plugin in violation of AGENTS §4. Every later
contributor will re-introduce the same bug because the failing mode
("env var not set") is invisible from the plugin's own surface — the
kernel boots, `/health` answers, and only the first chat call reveals
the misconfiguration. The preflight check exists specifically to make
the failure visible at boot.

### Why not have `lca-webserver-bootstrap` read `LCA_JWT_SECRET` itself?

The bootstrap is the wrong layer: AGENTS §4 says *no* plugin may read
`os.environ`, and the bootstrap is a plugin. The seam-level plugin
(`lca-webserver-jwt-keys`) is the correct owner because it advertises
`requires=()` and its config is fully resolved by the harness before
`setup` runs — it can advertise the seam without taking a dependency
on env access.

### Why not pull from a remote secret manager (Vault / KMS)?

Out of scope. The current bug is "seam missing" — the seam must exist
first. Once `jwt_keys` is a real capability, a future ADR can replace
the in-process dev generator with a `vault://...` resolver without
touching the handler contract. Delete-when below records the intended
hand-off.

### Why not short-circuit by always returning 503 when the key is missing?

Already happens: `render_create_run_receipt` returns 503
`jwt_secret_unconfigured` on `JwtSecretUnconfiguredError`. The point of
the preflight is to avoid the 503 at all — if the operator forgot the
env, fail at spawn, not at first request.

## Verification

- `tests/lca_plugins/transport/webserver/jwt_keys_seam/test_jwt_keys_seam.py`:
  dev-mode produces a keypair whose `public_pem` is derived from
  `private_pem`; missing private + missing dev_mode raises
  `RuntimeError`; invalid PEM raises `RuntimeError` with a "not a valid
  PEM-encoded PKCS8 private key" message.
- `tests/lca_plugins/transport/webserver/handlers/runs/terminal/streaming/test_auth.py`:
  `mint_user_jwt(private_key_pem="")` and
  `verify_user_jwt(token, public_key_pem="")` raise
  `JwtSecretUnconfiguredError`; mint + verify round-trip works with
  real PEM; tampered signature is rejected.
- `tests/integration/test_post_runs_no_secret.py`:
  `render_create_run_receipt(..., jwt_keys=<real>)` returns 202 with a
  three-part JWT in `ws_token`; the same call with `jwt_keys=None`
  returns 503 with `code="jwt_secret_unconfigured"`.
- Manual: `curl -X POST -d '{...}' http://127.0.0.1:8765/runs` returns
  202 when the web-app bundle's `dev_mode: true` is active.

## Risks

- **WS clients in flight at kernel restart get disconnected** because
  the dev-mode keypair rotates every restart. This is acceptable for
  local development; production profiles must disable `dev_mode`.
  `lcaGateway/execute.ts` and the lobehub-side reconnect logic are
  expected to absorb the brief outage; an end-to-end test exercising
  restart-during-stream is out of scope for this note.
- **Profile schema addition.** `jwt.private_pem` / `jwt.public_pem` /
  `jwt.dev_mode` are new keys under the webserver plugin config. Old
  profiles without them continue to work in dev-mode (the web-app
  bundle supplies the default), but the addition needs the harness
  DAG validator to ignore unknown keys at the leaf level — confirmed
  by inspection; `lca/harness/profile/plan/declarations.py` only flags
  unknown keys at top-level entries, not under plugin `config`.

## Delete-when

The dev-mode fallback and the Profile-injected path together are the
interim form. Delete-when a remote-secret-manager plugin (e.g.
 `lca-webserver-jwt-vault`) provides `jwt_keys` with stable, multi-replica
 semantics, **and** a follow-up ADR retires `dev_mode`. Until then this
 note remains `proposed`. The implementation PR moves it to
 `implemented/seam/`.

## Related

- AGENTS §4 ("插件不得自行读取 `os.environ`").
- `lca/harness/profile/plan/declarations.py:expand_env_refs` —
  harness-level `from_env` resolver that this proposal relies on.
- `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/agent_gateway.py`
  — WS handshake that consumes `verify_user_jwt(public_key_pem=...)`.
- `docs/debug/README.md#post-runs-500` — operator-facing recovery steps
  added alongside this proposal.