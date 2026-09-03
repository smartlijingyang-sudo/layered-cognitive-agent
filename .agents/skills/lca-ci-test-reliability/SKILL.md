---
name: lca-ci-test-reliability
description: Design, review, and diagnose LCA tests and fixtures that can fail nondeterministically under CI concurrency, shared host resources, clocks, process-global state, Cordis context lifecycle, Kernel lifespan, transport subprocesses, or asynchronous teardown. Use when adding or changing tests with those risks, investigating flaky CI, or reviewing test isolation; use lca-pre-push-checks separately to select outgoing commands. Trigger phrases: "flaky test", "race in pytest", "fixture leak", "test reliability".
---

# Reliable LCA CI Tests

Build tests that remain correct under LCA's real CI topology, not only when run alone on a quiet workstation. This skill owns isolation and reliability decisions; it does not replace the [tests/](../../../../tests/) layout policy or select every command for a push.

## Read the owning rules

- The [tests/](../../../../tests/) directory layout and the `conftest.py` / `fixtures/` split is the test-tier inventory — read [`tests/conftest.py`](../../../../tests/conftest.py) and the [fixtures](../../../../tests/fixtures/) before adding new fixtures, so the autouse fixtures already present (the `_ensure_no_env` LLM-key stripper and the `_block_kernel_sys_exit` K6 dispose neutralizer) are not duplicated.
- The [architecture tests](../../../../tests/architecture/) and [contract tests](../../../../tests/contract/) check invariants — use them as black-box coverage, not as starting points for new fixtures.
- For pytest config and markers, read `pyproject.toml` (the `[tool.pytest.ini_options]` block owns the `real_llm` / `e2e` / `lint_imports` markers).
- Use [lca-pre-push-checks](../lca-pre-push-checks/SKILL.md) after the test design is sound to select outgoing validation.

## Model the execution topology

Assume these layers can overlap unless the active configuration proves otherwise:

1. Tests in one pytest file / class / parametrize.
2. Separate pytest files in the same process (`pytest -n` xdist not enabled by default; check `pyproject.toml`).
3. Independent pytest invocations or `scripts/check_*.py` processes in one CI job.
4. Different CI jobs whose runners share one host (rare for LCA, but real for the `kernel-domain-isolation` importlinter job).

Process isolation does not isolate host ports, predictable filesystem paths under `tests/`, `traces/`, `profiles/`, external services (LobeHub UI, langfuse when enabled), sockets, or inherited child processes. For every acquired resource, identify its owner, atomic allocation mechanism, observable readiness signal, registered cleanup, and quiescent completion signal.

LCA-specific risks to enumerate:

- **`monkeypatch.delenv` race** — `tests/conftest.py` runs an autouse `_ensure_no_env` that strips `LLM_API_KEY` etc.; if a test re-imports the LLM resolver *after* the autouse runs, the resolver caches the empty value but later code paths that look at `os.environ` directly will still see the test-time value. The fixture is correct — the bug is in tests that bypass it.
- **`sys.exit` neutralization** — the same autouse fixture monkeypatches `sys.exit` so K6's `DefaultShutdownCoordinator.dispose` doesn't kill the test process. Tests that depend on `sys.exit` actually raising (e.g. to verify dispose semantics) need a separate, non-autouse fixture that unpatches.
- **Cordis `Context` not tearing down** — a Cordis `Context` started in one fixture and not `ctx.dispose()`'d will leave listeners and child services registered for the rest of the run. Use `try/finally` around the `ctx` block, or scope the fixture with a `pytest.fixture` finalizer.
- **Kernel lifespan tests** — the kernel's `lifespan_adapter` runs Cordis start / dispose in the test process; the `_block_kernel_sys_exit` fixture is required for any test that drives the kernel.
- **Transport subprocesses** — the webserver plugin may spawn a uvicorn-style worker. If the test depends on subprocess teardown, prove the child exited and the parent's pipe is closed.
- **Profile resolution races** — `lca_kernel.compile_profile` reads `profiles/*.yaml` and resolves `bundles/*`; tests that mutate these files must use `tmp_path` and copy, never patch in place.
- **Traces / journal side-effects** — tests that exercise the kernel leave files under `traces/runs/<run_id>/`; if a fixture doesn't clean its own run, the next test sees ghost files.

## Allocate resources atomically

Use the resource owner's allocator instead of checking availability and claiming it later.

- Network fixtures bind loopback with `socket(AF_INET, SOCK_STREAM)` and read the assigned port only after `listen(0)` reports listening. Never scan for a free port and bind it later.
- Create private per-test temporary roots with `tmp_path` (pytest builtin) or `tempfile.mkdtemp`; do not acquire predictable shared paths under `traces/`, `profiles/`, or `bundles/`.
- Give shared SQLite fixtures, langfuse sockets, transport sockets, and output locations unique per-test namespaces — use `pytest`'s `tmp_path` or the `monkeypatch` fixture, never hardcoded names.
- Use exclusive creation (`O_CREAT | O_EXCL`, or `open(..., "x")` mode in Python) where a path must not already exist.
- Keep stable recorded identifiers separate from ephemeral transport addresses. Translate inside the fixture instead of forcing the live resource to use the recorded value.

Literal paths and URLs used only as parser inputs or expected values are not acquired resources. Do not rewrite them merely because they look fixed.

## Contain process-global state

Treat `os.environ`, `cwd`, fake timers, locale and timezone, module mocks, registries (`sys.modules`, Cordis `Context` registries), `globalThis`-style hooks, and pytest's own plugin cache as exclusive mutable resources.

Prefer an injected dependency or instance-local adapter. When mutation is required:

- capture whether the original value was absent or present;
- restore that exact state;
- register restoration immediately;
- use `try/finally` around the smallest mutation scope;
- keep an `afterEach`-equivalent (`request.addfinalizer` in pytest) when failure before the local `finally` is plausible;
- intercept the narrowest exact request or call that the fixture owns.

LCA's autouse fixtures are the baseline; per-test fixtures should layer on top, not duplicate. Tests that need different env values should use the standard pytest `monkeypatch.setenv` / `monkeypatch.delenv` and call the autouse's effect explicitly when the autouse is `autouse=True` and they need to override.

## Respect platform-owned semantics

CI may run the same suite on Linux and (occasionally) macOS hosts. Values the OS owns do not always come back the way the test wrote them.

- Writing a value back is safe only when the assertion tolerates the write-back failing. Restoring a file's `mtime` to prove that a fingerprint invalidates anyway holds everywhere; restoring it to prove that a record stays valid assumes a lossless round trip.
- macOS / Linux case sensitivity: a fixture seeding both `http_proxy` and `HTTP_PROXY` is fine on POSIX; Windows would fold them, but LCA targets POSIX in CI.
- POSIX releases file handles asynchronously on some filesystems; a rename or removal that completes at once on tmpfs needs a bounded retry sized to the observed contention.
- POSIX has no Windows permission / signal semantics; the LCA suite targets POSIX, so a case that depends on POSIX semantics is fine, but tests must not silently rely on specific Linux kernel behaviors beyond POSIX.

Prefer an observation that holds on every POSIX platform LCA targets. When a case genuinely cannot, exclude it on that platform explicitly with `@pytest.mark.skipif(sys.platform == ...)` naming the reason.

## Budget timeouts against the lane

A pytest `pytest.mark.timeout(N)` (where the package is installed) or a per-test `asyncio.wait_for` overrides the runner's `--timeout` instead of yielding to it, so a value below the lane's budget lowers what CI already granted. A suite bound by process creation takes the lane budget; a tighter value carries the reason it is tighter.

Raise the fixture (autouse `_ensure_no_env` / `_block_kernel_sys_exit`) budget with the test budget. Setup and teardown pay the same contention, so lifting only the case budget moves a contended failure into fixture teardown.

Where a timeout is the subject, keep the outer wait far larger than the timeout under test. A case proving that a 20 ms deadline fires must not race the harness's own wait, or load decides which deadline reports first.

## Synchronize on state

A fixed `time.sleep` is not evidence that setup completed or cleanup settled.

- Wait for an explicit readiness event, handshake, state transition, owned promise, or externally observable condition.
- Use deferred promises (`asyncio.Event`) or barriers to place a race at a deterministic point and prove the relevant operations overlap.
- Use a timeout only to bound a wait, never as the condition that makes the assertion correct.
- Do not assert scheduler-dependent ordering unless that ordering is the product behavior under test.
- When time itself is the subject, use `freezegun` / `time-machine` and always restore real time.

## Dispose to quiescence

Register cleanup immediately after acquisition so assertion failures also release the resource. Cleanup stops new callbacks or requests, detaches listeners, restores global hooks, terminates owned work, and awaits child exit, server close, worker termination, or the equivalent completion signal.

LCA-specific teardown checklist per resource owner:

- **Cordis `Context`** — `await ctx.dispose()` (or `ctx.dispose()` for sync contexts). Verify no listeners are still attached.
- **Kernel `Boot` / `lifespan_adapter`** — `await lifespan.shutdown()` or equivalent; verify `_block_kernel_sys_exit` autouse is active.
- **Transport subprocess / uvicorn worker** — `proc.terminate()`, then `await proc.wait()`, then close any sockets. A bare `terminate()` without `wait()` is incomplete.
- **Langfuse client** — `await client.flush()` and `await client.shutdown()`.
- **SQLite fixtures** — `conn.close()` then `os.unlink(path)` inside a `try/finally`.
- **Traces / journal files** — clean `traces/runs/<run_id>/` after the test asserts what it needs.

Calling `dispose()`, `close()`, or `kill()` without awaiting the owned completion signal is incomplete teardown. When late completion is possible, prove that disposal prevents it from mutating another test.

## Conftest / fixture misuse patterns

These are the most common LCA fixture bugs; flag each on review:

- **Autouse fixture that depends on order** — `conftest.py` autouse fixtures run in declaration order; if one autouse depends on the side-effect of another, declare them in the right order with the dependency documented.
- **Function-scope fixture that captures a session-scope resource** — pytest will run the session-scope resource at the first function-scope call; if that resource isn't safe across many calls, narrow the scope.
- **Fixture that doesn't `addfinalizer` for async cleanup** — sync fixtures can `yield` then cleanup; async fixtures must `yield` and `addfinalizer` for the async part, or use `pytest-asyncio` correctly with `loop_scope`.
- **`monkeypatch` not undoing module-level decoration** — `monkeypatch.setattr` on a function is fine; on a class method that another test also patches is fine; on a *module-level import* (e.g. `import x; monkeypatch.setattr(x, ...)`) sometimes doesn't propagate to places that already imported the name. Prefer `monkeypatch.setattr` at the actual call site or patch the dict directly.
- **Test reads `os.environ` without going through `monkeypatch`** — the autouse `_ensure_no_env` already strips `LLM_API_KEY`; a test that calls `os.environ["LLM_API_KEY"]` will raise `KeyError`, not the absence it expected. Use `monkeypatch` or `os.environ.get` with an explicit default.
- **Test depends on `sys.exit` raising** — the autouse `_block_kernel_sys_exit` neuters `sys.exit`; tests verifying dispose semantics need a non-autouse fixture that unpatches (or call the dispose path that doesn't go through `sys.exit`).

## Prove the intended regression

- Observe an ordinary regression fail before the fix when practical.
- For a new static or corpus guard, temporarily introduce the rejected case and observe the intended failure.
- For a race, use `asyncio.Event` barriers to prove overlap; repeated execution alone is not a race test.
- For ports, sockets, shared paths, subprocesses, or other host resources, run independent test processes concurrently when cross-process isolation is part of the fix.
- Where a fixture spawns with its own deadline, assert that no signal or timeout ended the child before asserting its exit status, so a killed child reports as a timeout instead of as a status mismatch.
- Verify external state, events, files, logs, exits, or disposal instead of trusting the component's self-report.

Stress runs (`pytest --count=N` via `pytest-repeat`) supplement a deterministic regression; they do not replace one.

## Reject flake-masking fixes

Do not present these as root-cause fixes for deterministic local tests:

- increasing a timeout without identifying the awaited state;
- adding retries (`tenacity`, `pytest-flaky`, `pytest-rerunfailures`);
- making all files serial;
- swallowing an error or unhandled rejection;
- weakening an assertion;
- normalizing away unstable behavior;
- adding a sleep before cleanup or assertion.

Retries remain valid for documented transient external-provider tests under the `real_llm` policy. Keep that exception at the external boundary.

Restoring a budget is not masking. Raising a suite to the lane budget it already had, or sizing a bounded retry to the contention actually measured on the runner, names the awaited work and returns what the lane granted.

## Diagnose existing flakes

For an existing probabilistic CI failure, the [debug runbook](../../docs/debug/run-debug-guide.md) is the first stop; combine with `./scripts/lca-ops debug-run <run_id>` and the journal view from `./scripts/lca-ops journal trace <run_id>`. A diagnosis-only request remains read-only: report the cause and evidence unless the user also asks for a fix.

## Validate and report

Run the smallest focused regression for the affected behavior. Add topology-specific evidence only when the change owns that risk:

- global mutation needs restoration evidence;
- lifecycle or subprocess work needs quiescent teardown evidence;
- ports, sockets, or shared paths need concurrent independent-process evidence;
- a new guard needs a negative control.

Before a push, use [lca-pre-push-checks](../lca-pre-push-checks/SKILL.md). Report exact commands and observed results; do not describe retries, skipped tests, or pending CI as passing.