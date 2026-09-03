"""``lca-ops runs create`` — CLI wrapper for ``POST /runs`` (carrier).

The HTTP layer (``plugins/transport/webserver/handlers/runs/api/command_endpoints.py``)
is the only seam that creates a run, allocates ``run_id``, registers the
session, and writes ``traces/runs/<id>/`` artifacts. This CLI module is a
**thin** wrapper around that seam — it does not duplicate the carrier
logic, only builds the JSON body and POSTs it.

Why this exists:

1. Coding agents should not have to remember the ``curl`` form of the carrier.
2. The legacy ``/v1/chat/completions`` endpoint is **NOT** a run-creation seam:
   it is a LobeHub UI proxy (ADR-0099) that streams OpenAI-compatible responses
   without registering a run_id or writing ``traces/runs/<id>/``. Using it as
   a "trigger a run" command silently produces zero debug artifacts, which
   is the most common user-visible failure when an agent reaches for "the
   chat API".
3. ``lca-ops runs create`` always returns the new ``run_id`` + ``trace_id``,
   so downstream tooling can immediately ``debug-run <run_id>`` without
   scraping logs.

The contract lives in :mod:`lca.plugins.transport.webserver.handlers.runs.api.command_endpoints`:
``CreateRunRequest`` (handler-side decode) → ``RunPort.create_and_dispatch``.
We deliberately do **not** re-decode the body here; we forward whatever the
agent gives us and let the carrier validate.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import typer


def register(app: typer.Typer) -> None:
    """Register the ``runs`` subcommand on the CLI app."""
    runs_app = typer.Typer(help="Run lifecycle (carrier-aligned).", no_args_is_help=True)
    runs_app.command(name="create", help=_create.__doc__ or "")(_create)
    app.add_typer(runs_app, name="runs")


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
        help="Block until the run is terminal (polls ``GET /runs/{id}/doctor`` every 2s, max 5 min).",
    ),
) -> None:
    """Create one run via the carrier; print ``run_id`` + ``trace_id`` + ``live_url``.

    Thin wrapper around ``POST /runs`` (handlers/runs/api/command_endpoints.create_run).
    Returns immediately after dispatch; use ``--wait`` if you need the terminal verdict.

    This is the canonical "trigger a run" command for coding agents. ``/v1/chat/completions``
    does NOT register a run and is NOT a substitute (it is a LobeHub UI proxy, see ADR-0099).
    """
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
    live_url = str(receipt.get("live_url", "") or f"/runs/{run_id}/live")

    if json_mode:
        typer.echo(json.dumps({"status": status_code, **receipt}, indent=2, ensure_ascii=False))
        return

    typer.echo(f"run_id    = {run_id}")
    typer.echo(f"trace_id  = {trace_id}")
    typer.echo(f"live_url  = {base_url.rstrip('/')}{live_url}")

    if not run_id:
        typer.echo("[lca-ops runs create] carrier did not return run_id", err=True)
        raise typer.Exit(code=1)

    if not wait:
        # Caller can immediately follow up with debug-run or journal trace.
        typer.echo("")
        typer.echo("Next steps:")
        typer.echo(f"  lca-ops debug-run {run_id}")
        typer.echo(f"  lca-ops journal trace {run_id}      # default --human tree view")
        return

    # --wait: poll /runs/{id}/doctor until terminal (success/failed/cancelled/paused).
    import time

    deadline = time.monotonic() + 300  # 5 min cap
    last_status: str | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(  # noqa: S310 — same justification as POST /runs above.
                f"{base_url.rstrip('/')}/runs/{run_id}/doctor", timeout=10
            ) as resp:
                doctor = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError):
            time.sleep(2)
            continue
        status = str(doctor.get("status", "") or "")
        if status and status != last_status:
            typer.echo(f"[doctor] status={status}")
            last_status = status
        if status in {"success", "failed", "cancelled", "paused"}:
            typer.echo(f"[lca-ops runs create] terminal status={status}")
            if json_mode:
                typer.echo(json.dumps(doctor, indent=2, ensure_ascii=False))
            raise typer.Exit(code=0 if status == "success" else 1)
        time.sleep(2)

    typer.echo(f"[lca-ops runs create] timed out after 300s waiting for {run_id}", err=True)
    raise typer.Exit(code=1)


__all__ = ["register"]
