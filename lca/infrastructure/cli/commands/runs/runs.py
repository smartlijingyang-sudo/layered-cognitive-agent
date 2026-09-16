"""``lca-ops runs create`` — CLI wrapper for ``POST /runs`` (carrier).

Per ADR-0199 §10 Phase 1 and §12.2 the CLI is L0 — it only emits a
``RunIntent`` and consumes the resulting ``SessionActivation`` /
``RunHandle`` from the L1 :class:`RuntimeFacade`. Two execution paths
are exposed:

* **Default (production):** HTTP shell-out to ``${base_url}/runs``. The
  HTTP layer
  (``plugins/transport/webserver/handlers/runs/api/command_endpoints.py``)
  is the only seam that creates a run, allocates ``run_id``, registers
  the session, and writes ``traces/runs/<id>/`` artifacts. This CLI
  module is a **thin** wrapper around that seam — it does not duplicate
  the carrier logic, only builds the JSON body and POSTs it.

* **Offline / dev / test (``--facade``):** in-process dispatch through
  :class:`DefaultRuntimeFacade`. Used to prove CLI↔HTTP cross-surface
  parity — the same ``RunIntent`` yields the same ``plan_ref`` /
  ``activation_ref`` across both surfaces (P1-13 + the architecture
  acceptance test). Per ADR-0199 I-HPC-1 the CLI parser never resolves
  a profile or compiles a plan directly; the facade owns K1+K2.

Why both paths:

1. Coding agents should not have to remember the ``curl`` form of the
   carrier (default path).
2. The legacy ``/v1/chat/completions`` endpoint is **NOT** a
   run-creation seam: it is a LobeHub UI proxy (ADR-0099) that streams
   OpenAI-compatible responses without registering a run_id or writing
   ``traces/runs/<id>/``. Using it as a "trigger a run" command
   silently produces zero debug artifacts, which is the most common
   user-visible failure when an agent reaches for "the chat API".
3. ``lca-ops runs create`` always returns the new ``run_id`` +
   ``trace_id``, so downstream tooling can immediately
   ``debug-run <run_id>`` without scraping logs.
4. ``--facade`` proves parity without requiring the HTTP carrier; tests
   and offline runs use it to verify the same RunIntent produces the
   same plan_ref on both surfaces (acceptance test #1, ADR-0199 §10).

The HTTP contract lives in
:mod:`lca.plugins.transport.webserver.handlers.runs.api.command_endpoints`:
``CreateRunRequest`` (handler-side decode) →
``RunPort.create_and_dispatch``. We deliberately do **not** re-decode
the body there; we forward whatever the agent gives us and let the
carrier validate.

The in-process contract lives in
:mod:`lca.application.runtime.default_facade` (P1-09 + P1-10).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import typer

from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.infrastructure.cli.commands.kernel._shared import spine_terminal_outcome
from lca.plugins.observability.health.run_health_fold import fold_run_health

_DEFAULT_TRACES_ROOT = Path("traces")
_POST_CREATE_POLL_CAP_S = 300  # mirrors --wait 5 min cap
_POST_CREATE_POLL_INTERVAL_S = 2

# doctor ``--wait`` 终态词表:doctor status 是 journal outcome / doctor
# verdict 投影词表。``"success"`` / ``"cancelled"`` 是历史 doctor verdict
# 拼写,不属于 RunLifecycleStatus,保留字面量。
_TERMINAL_DOCTOR_STATUSES = frozenset(
    {
        "success",
        RunLifecycleStatus.FAILED.value,
        "cancelled",
        RunLifecycleStatus.PAUSED.value,
    }
)


def register(app: typer.Typer) -> None:
    """Register the ``runs`` subcommand on the CLI app."""
    runs_app = typer.Typer(help="Run lifecycle (carrier-aligned).", no_args_is_help=True)
    runs_app.command(name="create", help=_create.__doc__ or "")(_create)
    from lca.infrastructure.cli.commands.runs import debug as runs_debug
    from lca.infrastructure.cli.commands.runs import health as runs_health

    runs_debug.register(runs_app)
    runs_health.register(runs_app)
    app.add_typer(runs_app, name="runs")


# ── CLI↔HTTP in-process dispatcher (PR-0199-P1-13) ──────────────────────


class CLIInProcessDispatcher:
    """In-process :class:`RunDispatcher` for ``--facade`` mode.

    Per ADR-0199 §10 Phase 1 + I-HPC-1 the CLI must not start a real
    run; in offline / test / dev mode the dispatcher only records the
    activation so the CLI can echo the activation_ref back to the
    operator for parity verification. The real run-startup seam stays
    in the HTTP→carrier→coordinator path (default mode).
    """

    def __init__(self) -> None:
        self._runs: dict[str, str] = {}

    async def dispatch_run(self, activation, intent):  # type: ignore[no-untyped-def]
        """Return a synthetic handle correlated with the activation."""
        from lca.contracts.runtime.facade import RunHandle

        synthetic = f"cli_facade_{activation.activation_ref[:16]}"
        self._runs[synthetic] = synthetic
        return RunHandle(synthetic)

    async def dispatch_resume(self, activation, run_id):  # type: ignore[no-untyped-def]
        """Resume handle for an existing run (offline mode)."""
        from lca.contracts.runtime.facade import RunHandle

        return RunHandle(f"cli_facade_resume_{run_id[:16]}")


def _create(
    user_text: str = typer.Option(..., "--user-text", help="User message (the prompt)."),
    mode: str = typer.Option(
        "solo",
        "--mode",
        help="Run mode. Default ``solo`` (LobeHub proxy path); other modes require a registered adapter.",
    ),
    agent: str = typer.Option(
        "agt_aVxY6ag9MbMc",
        "--agent",
        help="Agent id (default: LobeHub's default solo 助手).",
    ),
    profile: str = typer.Option(
        "web-standard",
        "--profile",
        help="Profile name passed to ``POST /runs`` (default: web-standard).",
    ),
    base_url: str = typer.Option(
        "http://127.0.0.1:8765",
        "--base-url",
        envvar="LCA_OPS_BASE_URL",
        help="Kernel base URL (override via env LCA_OPS_BASE_URL when shelling out from another host).",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Print the raw carrier receipt as JSON."),
    wait: bool = typer.Option(
        False,
        "--wait",
        help=(
            "Block until the run is terminal (polls ``GET /runs/{id}/doctor`` every 2s, max 5 min). "
            "Debug run 的工作流:不加 --wait,create 立即返回 → ``lca-ops timeline <run_id>`` 看图。"
            "只在脚本需要 terminal verdict 再继续时才加。"
        ),
    ),
    facade: bool = typer.Option(
        False,
        "--facade",
        help=(
            "Run in-process via RuntimeFacade (ADR-0199). Skips HTTP carrier. "
            "For tests, offline mode, and CLI↔HTTP parity verification."
        ),
    ),
    no_sop: bool = typer.Option(
        False,
        "--no-sop",
        help=(
            "Skip the post-create SOP (terminal polling + exceptions sidecar check). "
            "Default behavior follows SKILL lca-debug-run step 4: poll until terminal, "
            "then surface any ``<run_id>.exceptions.jsonl`` records. Set this flag when "
            "you want the original 'return immediately, follow up manually' flow."
        ),
    ),
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help=(
            "Optional session id for the facade path (P1-13). When omitted, "
            "the facade mints a fresh ``sess_<16hex>`` id."
        ),
    ),
) -> None:
    """Create one run via the carrier; print ``run_id`` + ``trace_id`` + ``ws_url``.

    Thin wrapper around ``POST /runs`` (handlers/runs/api/command_endpoints.create_run).
    Returns immediately after dispatch; pass ``--wait`` only if you need the terminal
    verdict in-script. For debugging, follow up with
    ``lca-ops timeline <run_id>`` (or ``observation run-replay --show-graph``)
    instead of waiting — the timeline works even when ``journal.json`` has not
    materialized (which happens on runs that exit via ``lifecycle.finally``
    without ``RunTerminalizer.terminalize``).

    This is the canonical "trigger a run" command for coding agents. ``/v1/chat/completions``
    does NOT register a run and is NOT a substitute (it is a LobeHub UI proxy, see ADR-0099).

    Pass ``--facade`` to bypass the HTTP carrier and resolve the activation
    in-process via :class:`DefaultRuntimeFacade` (ADR-0199 P1-13). The
    facade path is intended for tests, offline mode, and CLI↔HTTP parity
    verification; it does NOT start a real run.
    """
    if facade:
        _create_via_facade(
            user_text=user_text,
            mode=mode,
            agent=agent,
            profile=profile,
            session_id=session_id,
            assistant_id=None,
            attachment_ids=(),
            execution_target="",
            options={},
            device_id="",
        )
        return

    body = {
        "messages": [{"role": "user", "content": user_text}],
        "mode": mode,
        "agent": agent,
        "profile": profile,
    }
    request = urllib.request.Request(  # noqa: S310 — CLI to local kernel; LCA_OPS_BASE_URL is operator-controlled.
        f"{base_url.rstrip('/')}/runs",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(body).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 — CLI to local kernel; LCA_OPS_BASE_URL is operator-controlled.
            request, timeout=15
        ) as response:
            receipt = json.loads(response.read().decode("utf-8"))
            status_code = response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        typer.echo(
            f"[lca-ops runs create] carrier rejected the request (HTTP {exc.code}): {detail}",
            err=True,
        )
        raise typer.Exit(code=exc.code or 1) from None
    except urllib.error.URLError as exc:
        typer.echo(
            f"[lca-ops runs create] cannot reach kernel at {base_url}: {exc.reason}. "
            f"Is ``lca_kernel serve`` running? Start with ``lca-ops kernel-restart``.",
            err=True,
        )
        raise typer.Exit(code=1) from None

    run_id = str(receipt.get("run_id", "") or "")
    trace_id = str(receipt.get("trace_id", "") or "")

    if json_mode:
        # JSON 模式也要走 SOP,否则 agent 用 --json 时仍会漏掉 sidecar 异常。
        report = _build_post_create_report(run_id, base_url) if not no_sop else None
        payload = {"status": status_code, **receipt}
        if report is not None:
            payload["post_create_report"] = report
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    # P1: live streaming is via WebSocket at /v1/runs/{run_id}/ws.
    # The receipt still carries ``live_url`` for byte-compat, but it
    # points at a retired SSE path. Show the user the working WS URL.
    http_base = base_url.rstrip("/")
    ws_base = http_base.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
    ws_url = f"{ws_base}/v1/runs/{run_id}/ws" if run_id else ""

    typer.echo(f"run_id    = {run_id}")
    typer.echo(f"trace_id  = {trace_id}")
    typer.echo(f"ws_url    = {ws_url}")

    if not run_id:
        typer.echo("[lca-ops runs create] carrier did not return run_id", err=True)
        raise typer.Exit(code=1)

    if not wait and no_sop:
        # Caller can immediately follow up with debug-run or journal trace.
        typer.echo("")
        typer.echo("Next steps:")
        typer.echo(f"  lca-ops debug-run {run_id}")
        typer.echo(f"  lca-ops journal trace {run_id}      # default --human tree view")
        return

    # Post-create SOP (default; SKILL lca-debug-run step 4).
    report = _build_post_create_report(run_id, base_url)
    _render_post_create_report(run_id, report)

    if wait:
        # --wait 老路径:除 SOP 外,仍按旧 exit-code 语义退出(success=0,其他非零)。
        terminal = report.get("terminal_status") or "unknown"
        raise typer.Exit(code=0 if terminal == "success" else 1)


def _create_via_facade(
    *,
    user_text: str,
    mode: str,
    agent: str,
    profile: str,
    session_id: str | None,
    assistant_id: str | None,
    attachment_ids: tuple[str, ...],
    execution_target: str,
    options: dict,
    device_id: str,
) -> None:
    """CLI in-process facade path (ADR-0199 P1-13).

    Demonstrates CLI↔HTTP plan_ref parity: the same ``RunIntent``
    content yields the same ``plan_ref`` + ``activation_ref`` that the
    HTTP path would. Per ADR-0199 I-HPC-1 the CLI parser never
    resolves a profile or compiles a plan directly — the facade owns
    K1+K2 (I-HPC-1 + I-HPC-2).

    The ``agent`` field is L0 principal metadata (UI hint, see
    I-HPC-1's surface contract) and is intentionally not part of
    :class:`CliRunArgs` / :class:`RunIntent`; the HTTP path encodes it
    in the JSON body, the facade path drops it (intentional parity
    with the contract).
    """
    # COMPAT(owner: ADR-0199, from: CLI-direct-resolve, to: RuntimeFacade,
    #        delete_when: --facade becomes default + CLI↔HTTP parity test in CI
    #        + zero hits in scripts/route_legacy_patterns.py for "cli_resolve",
    #        forbidden_new_usage: cli-direct resolve_profile calls)
    del agent  # HTTP-only field; not part of RunIntent per I-HPC-1.
    # Lazy imports — facade lives in ``lca.application.runtime``; keep
    # them out of module import time so we don't pull application /
    # harness into ``lca.infrastructure`` modules that import this one.
    from lca.application.runtime.adapters.intent_from_cli import (
        CliRunArgs,
        cli_args_to_intent,
    )
    from lca.application.runtime.default_facade import DefaultRuntimeFacade
    from lca.application.runtime.plan_resolution import PlanResolutionService

    args = CliRunArgs(
        profile=profile,
        user_text=user_text,
        mode=mode,
        session_id=session_id,
        assistant_id=assistant_id,
        attachment_ids=attachment_ids,
        execution_target=execution_target,
        options=options,
        device_id=device_id,
    )
    intent = cli_args_to_intent(args)
    facade_obj = DefaultRuntimeFacade(
        plan_resolution_service=PlanResolutionService(),
        run_dispatcher=CLIInProcessDispatcher(),
    )
    activation = facade_obj.resolve_activation(intent)
    typer.echo(f"plan_ref         = {activation.plan_ref}")
    typer.echo(f"graph_ref        = {activation.graph_ref}")
    typer.echo(f"plugin_set_ref   = {activation.plugin_set_ref}")
    typer.echo(f"activation_ref   = {activation.activation_ref}")
    typer.echo(f"session_id       = {activation.session_id}")


# ── Post-create SOP helpers (SKILL lca-debug-run step 4) ────────────────


def _poll_terminal_status(run_id: str, base_url: str) -> tuple[str | None, float]:
    """Poll ``GET /runs/{id}/doctor`` until terminal or cap.

    Returns ``(terminal_status_or_None, elapsed_seconds)``. None means
    we hit the 5 min cap without observing a terminal status.
    """
    deadline = time.monotonic() + _POST_CREATE_POLL_CAP_S
    last_status: str | None = None
    started = time.monotonic()
    url = f"{base_url.rstrip('/')}/runs/{run_id}/doctor"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
                doctor = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError):
            time.sleep(_POST_CREATE_POLL_INTERVAL_S)
            continue
        status = str(doctor.get("status", "") or "")
        if status and status != last_status:
            typer.echo(f"[doctor] status={status}")
            last_status = status
        if status in _TERMINAL_DOCTOR_STATUSES:
            return status, time.monotonic() - started
        time.sleep(_POST_CREATE_POLL_INTERVAL_S)
    return None, time.monotonic() - started


# Live-SOP tail loop and EP-formatting helpers (spec §15 G-1..G-5)
# were removed in PR-1 Task 1.5; ``_build_post_create_report`` below
# now reads the post-terminal state by folding the spine through the
# registered ``HealthDeriver`` set (entry-point discovered). Operators
# who want real-time streaming should use the WS path at
# ``/v1/runs/{run_id}/ws`` documented in ``--help``.


def _build_post_create_report(run_id: str, base_url: str) -> dict:
    """Build the post-create report by folding the spine.

    Per spec
    ``docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md``
    §2.4: the report carries ``health`` (the frozen
    ``RunHealthReport.model_dump(mode="json")``) and ``health_summary``
    (the worst status across all conditions + per-type breakdown),
    replacing the eight scattered live-SOP fields deleted in
    spec §15 G-1..G-5.

    ``base_url`` is accepted for signature parity with the previous
    CLI surface; it is no longer polled (the spine is the truth).
    """
    del base_url  # spine is the truth; no HTTP polling

    started = time.monotonic()
    spine_path = _DEFAULT_TRACES_ROOT / "runs" / run_id / f"{run_id}.spine.jsonl"

    typer.echo("[post-create] folding spine into RunHealthReport…")
    report = fold_run_health(spine_path)
    elapsed = time.monotonic() - started

    from lca.plugins.observability.health.run_health_fold import _worst_status

    overall = _worst_status(report)
    summary_payload: dict = {
        "overall": overall,
        "by_type": dict(report.summary.by_type),
    }
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "terminal_status": spine_terminal_outcome(spine_path),
        "elapsed_s": round(elapsed, 1),
        "health": report.model_dump(mode="json"),
        "health_summary": summary_payload,
    }


def _render_post_create_report(run_id: str, report: dict) -> None:
    """Human-friendly post-create summary for non-JSON output.

    Renders the ``RunHealthReport`` shape introduced by PR-1 (the
    ``health`` + ``health_summary`` fields); the previous live-SOP
    field shape (``events_streamed``, ``new_exceptions_streamed``,
    ``tail_cap_s``, ``exceptions``) was deleted in spec §15 G-1..G-5.
    """
    typer.echo("")
    typer.echo("[post-create health summary]")
    terminal = report.get("terminal_status") or "unknown"
    elapsed = report.get("elapsed_s")
    summary = report.get("health_summary") or {}
    overall = summary.get("overall") or "unknown"
    by_type = summary.get("by_type") or {}
    typer.echo(f"  terminal status : {terminal}  ({elapsed}s)")
    typer.echo(f"  health overall  : {overall}")
    if by_type:
        breakdown = ", ".join(f"{name}={status}" for name, status in sorted(by_type.items()))
        typer.echo(f"  by type         : {breakdown}")

    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  lca-ops debug-run {run_id}")
    typer.echo(f"  lca-ops timeline {run_id}            # phase_graph tree")
    typer.echo(f"  lca-ops journal trace {run_id}        # default --human tree view")
    if terminal != "success" or overall in {"degraded", "failed"}:
        typer.echo(
            f"  lca-ops explain {run_id}               # ← recommended (non-success/healthy)"
        )


__all__ = ("CLIInProcessDispatcher", "register")
