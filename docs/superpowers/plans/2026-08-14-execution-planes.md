# Execution Planes Implementation Plan

> **For agentic workers:** Same-session implementation. Tasks are tightly coupled (identity → bind → adapters → host paths). Do not dual-bind by default.

**Goal:** One primary product environment per Run; Host is a machine transport, not a Sandbox; true paths; two computer adapters.

**Architecture:** `PlaneRef` / `PlaneBindings` (pure data) freeze at `execute_run`. Tools consume bindings. `MachineComputer` and `SandboxComputer` are separate adapters. Sidecar stops remapping `/mnt/data`.

**Tech Stack:** existing LCA contracts / L0 / gateway / host sidecar.

**Spec:** `docs/superpowers/specs/2026-08-14-execution-planes-design.md`

---

## Chunk 1 — Identity and freeze

**Create**
- `lca/contracts/models/core/plane.py`
- `lca/layer0_infra/plane/__init__.py`
- `lca/layer0_infra/plane/resolve.py`
- `lca/layer0_infra/plane/scope.py` (contextvar + path audit)
- `tests/test_plane_bindings.py`

**Modify**
- `lca/layer0_infra/sandbox/factory.py` — `resolve_sandbox` no longer prefers Host; override stays for real Sandbox tests
- `gateway/app.py` — stop `set_sandbox_resolver(HostSandbox)`
- `gateway/host_sandbox.py` — `for_device`; keep `computer_op`
- `gateway/presence/models.py` — `platform`, `home`, `root`
- `gateway/presence/registry.py` — `online_with`, `remember_success`
- `gateway/runs/session.py` — `bindings`, `device_id`, `plane`, `extra_plane`
- `gateway/runs/execute.py` — resolve → freeze → tools; sandbox runtime only if sandbox bound
- `gateway/assemble.py`, `lca/layer4_app/casting.py` — `build_*_tools(bindings=)`
- `lca/layer0_infra/tools/default_set.py` — eat bindings; default one face
- `tests/test_sandbox_resolver.py`, `tests/test_execution_surface.py`

## Chunk 2 — Two adapters + true paths

**Create**
- `lca/layer0_infra/computer/ops.py`
- `lca/layer0_infra/computer/machine.py`
- `lca/layer1_cognitive/brain/prompts/machine_system_role.md`
- `tests/test_machine_computer.py`
- `tests/test_machine_path_scope.py`

**Modify**
- `lca/layer0_infra/computer/runtime.py` — delete `_maybe_local`; sandbox guest only
- `lca/layer0_infra/tools/computer/tool_set.py` — `ops=` + `build_machine_computer_tools`
- `lca/layer0_infra/tools/computer/handlers.py` — empty path defaults to adapter root
- `gateway/runs/wire.py` — `local_*` → `lobe-local-system`
- `host/paths.py`, `host/exec.py`, `host/local_shell/**` — no guest remap, no clamp-to-workspace
- `host/client.py` + presence hello — `platform`, `home`, `root`
- `lca/layer0_infra/sandbox/surface.py` — prompt from primary `PlaneRef`
- `tests/test_host_exec.py`, `tests/test_computer_tools.py`

## Chunk 3 — Publish + context

**Modify**
- `gateway/runs/api.py` — parse `device_id` / `plane` / `extra_plane`; `GET /context`
- `gateway/app.py` — route `/context`
- `lca/layer0_infra/computer/machine.py` — after write/run, publish `outputs_dir` via transport read
- `deploy/lobehub/patches/proxy/file_proxy_rewrite.py` — `/lca-api/context` if missing (proxy already covers `/lca-api`)

## Out of this landing

- SSH transport, SRT
- Skill exec rewrite onto sidecar (machine-only keeps today’s no-exec skill set; sandbox primary unchanged)
- Dedicated journal event type (plane goes on computer Observation.extra + `/context`)

## Verify

```
uv run ruff check --fix lca/contracts/models/core/plane.py lca/layer0_infra/plane lca/layer0_infra/computer lca/layer0_infra/tools gateway host/paths.py host/exec.py host/local_shell host/client.py
uv run ruff format <same>
uv run pytest --no-cov tests/test_plane_bindings.py tests/test_machine_computer.py tests/test_machine_path_scope.py tests/test_sandbox_resolver.py tests/test_execution_surface.py tests/test_host_exec.py tests/test_computer_tools.py tests/test_host_sandbox.py tests/test_run_api.py tests/test_gateway*.py -q
```
