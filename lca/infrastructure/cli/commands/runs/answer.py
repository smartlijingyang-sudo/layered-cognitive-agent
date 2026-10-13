"""``lca-ops runs answer <run_id>`` — resume a paused run awaiting approval.

The CLI can trigger runs but has no frontend to answer approval gates. This
command wraps the same ``resume_tool_result`` carrier POST the frontend uses
(deploy/lobehub/patches/runtime/lcaGateway/executeGatewayRun.ts), so scripted
tests can complete tool-execution runs that paused on ``execute_code`` /
``run_command`` etc. It first reads ``GET /runs/{run_id}`` to discover the
pending ``approval_request``, then resumes with the operator's answer.

Idempotency: the carrier derives the resume key from ``run_id`` +
``toolCallId``, so a retry of the same command is a no-op replay instead of a
double resume.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import typer


def register(app: typer.Typer) -> None:
    """Mount ``runs answer`` under the runs sub-app."""

    @app.command(
        name="answer",
        help=(
            "Resume a paused (waiting_input) run by answering its pending "
            "tool approval. Reads GET /runs/{run_id} for approval_request, "
            "then POSTs /runs with resume_tool_result (the same carrier resume "
            "the frontend gateway uses)."
        ),
    )
    def answer_cmd(
        run_id: str = typer.Argument(..., help="run_id (例: run_xxx)"),
        answer: str = typer.Option(
            ...,
            "--answer",
            "-a",
            help="审批答复内容（例如『同意执行』）。",
        ),
        base_url: str = typer.Option(
            "http://10.36.6.252:8765",
            "--base-url",
            envvar="LCA_OPS_BASE_URL",
            help="Kernel base URL (override via env LCA_OPS_BASE_URL).",
        ),
    ) -> None:
        _answer_run(run_id=run_id, answer=answer, base_url=base_url)


def _headers() -> dict[str, str]:
    user_id = os.environ.get("LCA_USER_ID", "local-dev-user").strip() or "local-dev-user"
    auth_token = os.environ.get("LCA_AUTH_TOKEN", "lca-local").strip() or "lca-local"
    return {
        "Content-Type": "application/json",
        "x-lca-user-id": user_id,
        "Authorization": f"Bearer {auth_token}",
    }


def _get_json(url: str) -> dict:
    request = urllib.request.Request(  # noqa: S310 -- operator-controlled --base-url
        url, method="GET", headers=_headers()
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _answer_run(*, run_id: str, answer: str, base_url: str) -> None:
    base = base_url.rstrip("/")
    try:
        summary = _get_json(f"{base}/runs/{run_id}")
    except urllib.error.HTTPError as exc:
        typer.echo(f"[lca-ops runs answer] GET /runs/{run_id} failed (HTTP {exc.code})", err=True)
        raise typer.Exit(code=exc.code or 1) from None
    except urllib.error.URLError as exc:
        typer.echo(f"[lca-ops runs answer] cannot reach kernel at {base}: {exc.reason}", err=True)
        raise typer.Exit(code=1) from None

    approval = summary.get("approval_request") or {}
    tool_calls = approval.get("tool_calls") or []
    tool_call_id = ""
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if isinstance(tc, dict) and tc.get("call_id"):
                tool_call_id = str(tc["call_id"])
                break
    if not tool_call_id:
        status = str(summary.get("status") or summary.get("session_status") or "unknown")
        typer.echo(
            f"run {run_id} has no pending tool approval (status={status}); "
            "cannot resume via resume_tool_result",
            err=True,
        )
        raise typer.Exit(code=2)

    body = {
        "run_id": run_id,
        "agent": {"id": "solo", "name": "solo"},
        "messages": [],
        "resume_tool_result": {
            "content": answer,
            "toolCallId": tool_call_id,
            "run_id": run_id,
        },
    }
    request = urllib.request.Request(  # noqa: S310 -- operator-controlled --base-url
        f"{base}/runs",
        method="POST",
        headers=_headers(),
        data=json.dumps(body).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            receipt = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        typer.echo(
            f"[lca-ops runs answer] carrier rejected the resume (HTTP {exc.code}): {detail}",
            err=True,
        )
        raise typer.Exit(code=exc.code or 1) from None
    except urllib.error.URLError as exc:
        typer.echo(f"[lca-ops runs answer] cannot reach kernel at {base}: {exc.reason}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"run_id       = {receipt.get('run_id', run_id)}")
    typer.echo(f"status       = {receipt.get('status', 'resumed')}")
    typer.echo(f"tool_call_id = {tool_call_id}")


__all__ = ["register"]
