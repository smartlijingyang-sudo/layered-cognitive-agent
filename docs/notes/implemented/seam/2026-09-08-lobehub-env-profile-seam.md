# Agent Note: LobeHub env Profile seam classification (PR-5 / ADR-0202 followup)

Status: implemented

## Problem

`bundles/assistant-runtime.yaml` declared only 2 env vars via `{from_env: ...}` (`LCA_ASSISTANTS_ROOT`, `LCA_LOBEHUB_URL`). Python-side code in `lca/` and `lca_kernel/` reads 32 distinct env var names via `os.environ` / `os.getenv` / `os.environ.get`. Per AGENTS.md §4, env must enter via Profile `{from_env: ...}` seam. This note classifies all 32 names against the ADR-0117 three-layer bootstrap whitelist and identifies which need bundle declarations.

## Decision

Classify each env name against `BOOTSTRAP_NAMES`, `BOOTSTRAP_PREFIXES`, `BOOTSTRAP_FORBIDDEN` (defined in `lca/infrastructure/env/bootstrap.py`). Only names outside all bootstrap categories need `{from_env: ...}` bundle declarations.

## Classification table

Sources: `lca/infrastructure/env/bootstrap.py` (constants), `lca/infrastructure/env/layered.py` (prefix match = `key.startswith(prefix)`).

| # | Env name | Class | Matching rule | Action |
|---|---|---|---|---|
| 1 | `COMPOSIO_API_KEY` | BOOTSTRAP_PREFIXES | `COMPOSIO_` | No action |
| 2 | `COMPOSIO_AUTH_CONFIG_IDS` | BOOTSTRAP_PREFIXES | `COMPOSIO_` | No action |
| 3 | `DATABASE_URL` | **Plugin config** | No prefix match (`DB_` ≠ `DATABASE_URL`) | **Add `from_env:` to bundle** |
| 4 | `GATEWAY_BIND` | BOOTSTRAP_PREFIXES | `GATEWAY_` | No action |
| 5 | `GATEWAY_HOST` | BOOTSTRAP_PREFIXES | `GATEWAY_` | No action |
| 6 | `GATEWAY_PORT` | BOOTSTRAP_PREFIXES | `GATEWAY_` | No action |
| 7 | `LCA_AGENT_PRESETS_HOME` | BOOTSTRAP_PREFIXES | `LCA_` | No action |
| 8 | `LCA_COMPOSIO_CALLBACK_URL` | BOOTSTRAP_PREFIXES | `LCA_` | No action |
| 9 | `LCA_COMPOSIO_CONNECTIONS_PATH` | BOOTSTRAP_PREFIXES | `LCA_` | No action |
| 10 | `LCA_COMPOSIO_USER_ID` | BOOTSTRAP_PREFIXES | `LCA_` | No action |
| 11 | `LCA_GATEWAY_PUBLIC_URL` | BOOTSTRAP_PREFIXES | `LCA_` | No action |
| 12 | `LCA_KERNEL_SERVE_BIND` | BOOTSTRAP_PREFIXES | `LCA_KERNEL_SERVE_` | No action |
| 13 | `LCA_KERNEL_SERVE_HOST` | BOOTSTRAP_PREFIXES | `LCA_KERNEL_SERVE_` | No action |
| 14 | `LCA_KERNEL_SERVE_PORT` | BOOTSTRAP_PREFIXES | `LCA_KERNEL_SERVE_` | No action |
| 15 | `LCA_PROFILE` | BOOTSTRAP_FORBIDDEN | Explicit (argv-sourced per ADR-0115 D5) | No action |
| 16 | `LCA_REDIS_URL` | BOOTSTRAP_PREFIXES | `LCA_` | No action |
| 17 | `LCA_SESSION_SPINE` | BOOTSTRAP_PREFIXES | `LCA_` | No action |
| 18 | `LCA_SPINE_CHAIN_PATH` | BOOTSTRAP_PREFIXES | `LCA_` | No action |
| 19 | `LCA_SPINE_STREAM` | BOOTSTRAP_PREFIXES | `LCA_` | No action |
| 20 | `LLM_API_KEY` | BOOTSTRAP_PREFIXES | `LLM_` | No action |
| 21 | `LLM_API_STYLE` | BOOTSTRAP_PREFIXES | `LLM_` | No action |
| 22 | `LLM_BASE_BASE` | BOOTSTRAP_PREFIXES | `LLM_` | No action |
| 23 | `LLM_MODEL` | BOOTSTRAP_PREFIXES | `LLM_` | No action |
| 24 | `LOBE_DEV_PORT` | BOOTSTRAP_PREFIXES | `LOBE_` | No action |
| 25 | `LOBE_HOST` | BOOTSTRAP_PREFIXES | `LOBE_` | No action |
| 26 | `LOBEHUB_RELEASE` | BOOTSTRAP_PREFIXES | `LOBEHUB_` | No action |
| 27 | `MARKET_CLIENT_ID` | BOOTSTRAP_PREFIXES | `MARKET_` | No action |
| 28 | `MARKET_CLIENT_SECRET` | BOOTSTRAP_PREFIXES | `MARKET_` | No action |
| 29 | `ONLYBOXES_TERMINAL_IMAGE` | BOOTSTRAP_PREFIXES | `ONLYBOXES_` | No action |
| 30 | `ONLYBOXES_WORKER_SERVICE` | BOOTSTRAP_PREFIXES | `ONLYBOXES_` | No action |
| 31 | `REDIS_URL` | BOOTSTRAP_PREFIXES | `REDIS_` | No action |
| 32 | `SHELL` | BOOTSTRAP_NAMES | Exact match | No action |

**Result:** 30 of 32 names are BOOTSTRAP_PREFIXES-compliant, 1 is BOOTSTRAP_NAMES (`SHELL`), 1 is BOOTSTRAP_FORBIDDEN (`LCA_PROFILE`, argv-sourced). Only `DATABASE_URL` falls outside all bootstrap categories.

## Why DATABASE_URL is plugin config

`DATABASE_URL` does not match any `BOOTSTRAP_PREFIXES` entry. The `DB_` prefix covers keys like `DB_HOST` / `DB_PORT` / `DB_NAME` (Freedesktop-style split params), but `DATABASE_URL` is a single connection-string var that starts with `DATABASE`, not `DB_`. The `filter_env_keys` function uses `key.startswith(prefix)`, so `DATABASE_URL` does not match `DB_`.

## Bundle declaration

`DATABASE_URL` is read by `lca/infrastructure/persistence/postgres.py:database_url_from_env()` and consumed by LobeHub composio migration (`lca/infrastructure/integrations/composio/migrate/lobehub.py`), running operation store, and tool message state store. The composio-tools bundle is the semantic home since the LobeHub integration is the primary named consumer.

Added to `bundles/composio-tools.yaml`:

```yaml
- id: lca-composio-provider
  name: lca_composio_provider
  $module: lca.plugins.integrations.composio_provider
  config:
    database_url:
      from_env: DATABASE_URL
      required: false
```

`required: false` because Postgres is optional — the code falls back to SQLite when `DATABASE_URL` is unset.

## Reader migration (out of scope, followup PR)

This PR only adds the bundle declaration. The reader code (`database_url_from_env()` etc.) still calls `os.environ.get("DATABASE_URL")` directly. A followup PR will migrate the reader to consume the value from Profile config via the composio provider's resolved config.

## Verification

- `grep -hE "from_env:" bundles/*.yaml | wc -l` → 3 (was 2; +1 for `DATABASE_URL`)
- `grep -rnE "os\.environ|os\.getenv" lca/ lca_kernel/ deploy/lobehub/ --include="*.py" | grep -v __pycache__ | wc -l` → unchanged (reader migration is followup)
- `ruff check` on touched files exits 0
- `git diff --check` exits 0

## Related

- ADR-0202 (Transport/UI env SSOT)
- ADR-0117 (Process lifecycle + env whitelist)
- AGENTS.md §4 (env three-layer whitelist)
- `docs/notes/implemented/seam/2026-09-08-transport-ui-env-ssot.md` (sibling note)
