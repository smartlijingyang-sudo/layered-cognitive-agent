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
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import typer

from lca.contracts.observability.registry.status import RunLifecycleStatus

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
    runs_debug.register(runs_app)
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


# Live SOP events. We deliberately tail <run_id>.spine.jsonl and
# <run_id>.exceptions.jsonl directly — these are the append-only
# SSOTs that FileSink flushes synchronously per-EP (see
# lca/infrastructure/observability/spine/sinks/file_sink.py).
# Tail latency = next file-poll tick (200ms), not "wait for run
# terminal", so the agent sees `phase_graph.node.start phase=None`
# and the `exception.caught` traceback while the run is still
# running, not after.
_LIVE_SOP_EP_PREFIXES: tuple[str, ...] = (
    "phase_graph.",
    "phase.",
    "llm.call.",
    "body.tool.",
    "body.sandbox.",
    "step.tool_",
    "kernel.run.",
    "lifecycle.",
    "exception.",
    "transport.route.",
)
_LIVE_SOP_EP_SUPPRESS: frozenset[str] = frozenset({"llm.stream.token"})
_LIVE_SOP_POLL_INTERVAL_S = 0.2  # tight enough to feel live
_LIVE_SOP_TAIL_CAP_S = 600  # hard ceiling regardless of doctor


def _tail_append_only(path: Path, offset: int) -> tuple[int, bytes]:
    """Return ``(new_offset, new_bytes)`` from an append-only file.

    Treats truncation (size < offset) as "file was rotated" and
    rewinds to 0. Treats absence (file not yet created) as empty.
    Never raises; the SSOT sink guarantees atomic append but a
    short read mid-write is benign (last line is dropped next tick).
    """
    if not path.exists():
        return offset, b""
    try:
        size = path.stat().st_size
        if size < offset:
            offset = 0  # rotated; restart
        if size == offset:
            return offset, b""
        with path.open("rb") as fp:
            fp.seek(offset)
            return size, fp.read(size - offset)
    except OSError:
        return offset, b""


def _parse_jsonl_lines(blob: bytes) -> list[dict]:
    out: list[dict] = []
    for raw in blob.splitlines():
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw.decode("utf-8", errors="replace")))
        except json.JSONDecodeError:
            continue
    return out


def _live_sop_run(run_id: str, on_event, on_exception) -> tuple[int, str | None, int]:
    """Single-thread live SOP: tail spine + sidecar until terminal.

    Returns ``(spine_events_streamed, terminal_status, exceptions_surfaced)``.
    ``terminal_status`` is the outcome of ``kernel.run.stop`` (durable
    spine truth); ``None`` means the cap was hit before terminal.
    Threading, doctor polling, and parallel sub-streams are deliberately
    avoided — FileSink flushes are synchronous, so a single tight tail
    loop is faster and simpler than orchestrating three pollers.
    """
    spine_path = _DEFAULT_TRACES_ROOT / "runs" / run_id / f"{run_id}.spine.jsonl"
    sidecar_path = _DEFAULT_TRACES_ROOT / "runs" / run_id / f"{run_id}.exceptions.jsonl"
    spine_offset = 0
    sidecar_offset = 0
    streamed = 0
    surfaced = 0
    terminal: str | None = None
    seen_exc: set[tuple[str, int, str]] = set()
    deadline = time.monotonic() + _LIVE_SOP_TAIL_CAP_S

    while time.monotonic() < deadline:
        # 1) Sidecar first — observer failures are the most
        #    urgent signal; surface them within ~200ms of being
        #    written, well before run terminal.
        sidecar_offset, new = _tail_append_only(sidecar_path, sidecar_offset)
        for rec in _parse_jsonl_lines(new):
            p = rec.get("payload") or rec
            cls = p.get("exception_class") or "?"
            src = p.get("source_location") or {}
            try:
                line = int(src.get("line") or 0)
            except (TypeError, ValueError):
                line = 0
            key = (p.get("boundary") or "?", line, cls)
            if key in seen_exc:
                continue
            seen_exc.add(key)
            msg = (p.get("exception_message") or "").splitlines()[0]
            on_exception(cls, msg, src)
            surfaced += 1

        # 2) Spine — phase_graph / llm / tool / lifecycle / exception.
        spine_offset, new = _tail_append_only(spine_path, spine_offset)
        for rec in _parse_jsonl_lines(new):
            ep = rec.get("execution_point") or ""
            if ep in _LIVE_SOP_EP_SUPPRESS:
                continue
            if not ep.startswith(_LIVE_SOP_EP_PREFIXES):
                continue
            payload = rec.get("payload") or {}
            on_event(ep, payload)
            streamed += 1
            if ep == "kernel.run.stop":
                outcome = payload.get("outcome")
                if isinstance(outcome, str):
                    terminal = outcome
                    # Drain a final tail (exceptions may have flushed
                    # in the same fsync batch as kernel.run.stop).
                    sidecar_offset, new = _tail_append_only(sidecar_path, sidecar_offset)
                    for rec2 in _parse_jsonl_lines(new):
                        p = rec2.get("payload") or rec2
                        cls = p.get("exception_class") or "?"
                        src = p.get("source_location") or {}
                        try:
                            line = int(src.get("line") or 0)
                        except (TypeError, ValueError):
                            line = 0
                        key = (p.get("boundary") or "?", line, cls)
                        if key in seen_exc:
                            continue
                        seen_exc.add(key)
                        msg = (p.get("exception_message") or "").splitlines()[0]
                        on_exception(cls, msg, src)
                        surfaced += 1
                    return streamed, terminal, surfaced

        time.sleep(_LIVE_SOP_POLL_INTERVAL_S)

    return streamed, terminal, surfaced


def _format_spine_event(ep: str, payload: dict) -> str:
    """Compact one-line EP summary for live SOP output."""
    if ep == "phase_graph.node.start":
        node = payload.get("node_id") or "?"
        binding = payload.get("binding") or ""
        # `phase` is the field that broke NodeEnter validation in
        # run_5b0a6d0e69d5 — surface it explicitly so the agent sees
        # `phase=None` immediately rather than digging into payload.
        phase = payload.get("phase")
        phase_tag = f" phase={phase!r}" if phase is not None else " phase=None ⚠"
        return f"▶ phase_graph.node.start  {node}  [{binding}]{phase_tag}"
    if ep == "phase_graph.node.end":
        node = payload.get("node_id") or "?"
        ms = payload.get("elapsed_ms") or 0
        outcome = payload.get("outcome") or ""
        return f"■ phase_graph.node.end    {node}  {ms}ms  outcome={outcome}"
    if ep == "phase_graph.subgraph.enter":
        node = payload.get("node_id") or "?"
        sub = (payload.get("subgraph_plan_ref") or "").split("/")[-1]
        return f"↪ phase_graph.subgraph.enter {node} → {sub}"
    if ep == "phase_graph.subgraph.exit":
        node = payload.get("node_id") or "?"
        return f"↩ phase_graph.subgraph.exit  {node}"
    if ep == "phase_graph.edge.transit":
        edge = payload.get("edge_id") or "?"
        return f"→ phase_graph.edge.transit  {edge}"
    if ep == "llm.call.start":
        model = payload.get("model") or "?"
        return f"▶ llm.call.start          model={model}"
    if ep == "llm.call.end":
        ms = payload.get("latency_ms") or 0
        outcome = payload.get("outcome") or "?"
        prompt = payload.get("prompt_tokens") or 0
        comp = payload.get("completion_tokens") or 0
        return (
            f"■ llm.call.end            {ms}ms outcome={outcome} "
            f"tokens={prompt}+{comp}"
        )
    if ep == "body.tool.execute.start":
        tool = payload.get("tool_name") or "?"
        return f"▶ body.tool.execute.start  tool={tool}"
    if ep == "body.tool.execute.end":
        tool = payload.get("tool_name") or "?"
        outcome = payload.get("outcome") or "?"
        return f"■ body.tool.execute.end    tool={tool} outcome={outcome}"
    if ep == "phase.tool.call.start":
        tool = payload.get("tool_name") or "?"
        return f"▶ phase.tool.call.start    tool={tool}"
    if ep == "phase.tool.call.end":
        tool = payload.get("tool_name") or "?"
        ms = payload.get("latency_ms") or 0
        outcome = payload.get("outcome") or "?"
        return f"■ phase.tool.call.end      tool={tool} {ms}ms outcome={outcome}"
    if ep == "exception.caught":
        # In-line first-line traceback so the agent sees it in the
        # spine stream without waiting for the sidecar poll. The
        # sidecar poller is the second source of truth.
        msg = (payload.get("exception_message") or "").splitlines()[0]
        cls = payload.get("exception_class") or "?"
        src = payload.get("source_location") or {}
        loc = f"{src.get('file', '?')}:{src.get('line', '?')}"
        return f"✗ exception.caught         {cls}: {msg}  at {loc}"
    if ep == "kernel.run.start":
        return "▶ kernel.run.start"
    if ep == "kernel.run.stop":
        return f"■ kernel.run.stop          outcome={payload.get('outcome', '?')}"
    if ep == "lifecycle.finally":
        return f"■ lifecycle.finally        outcome={payload.get('outcome', '?')}"
    if ep == "body.sandbox.enter":
        tool = payload.get("tool_name") or "?"
        return f"  ↳ body.sandbox.enter    tool={tool}"
    if ep == "body.sandbox.exit":
        tool = payload.get("tool_name") or "?"
        outcome = payload.get("outcome") or "?"
        return f"  ↲ body.sandbox.exit     tool={tool} outcome={outcome}"
    return f"· {ep}"


def _run_journal_exceptions_json(run_id: str, traces_root: Path) -> dict | None:
    """Invoke ``lca-ops journal exceptions --json`` and parse its output.

    Returning the parsed dict keeps the post-create SOP consistent
    with the canonical sidecar reader (ADR-2026-09-03). We never
    inline-parse ``<run_id>.exceptions.jsonl`` here — single SSOT.
    """
    try:
        proc = subprocess.run(  # operator-trusted local CLI to local CLI.
            [
                sys.executable,
                "-m",
                "lca.infrastructure.cli.cli",
                "journal",
                "exceptions",
                run_id,
                "--json",
                "--traces-root",
                str(traces_root),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": f"journal exceptions subprocess failed: {exc}"}
    if proc.returncode != 0:
        # journal exceptions returns 0 even on empty; non-zero = real failure.
        return {
            "error": f"journal exceptions exit={proc.returncode}",
            "stderr": (proc.stderr or "")[-400:],
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"error": f"journal exceptions output not JSON: {exc}"}


def _build_post_create_report(run_id: str, base_url: str) -> dict:
    """Live SOP: tail spine + sidecar until ``kernel.run.stop`` lands.

    Architecture: one tight loop, two append-only files, zero
    threads. ``FileSink`` flushes spine / sidecar per-EP, so a
    200ms poll tick surfaces:

    - ``phase_graph.node.start phase=None ⚠`` — root-cause field
      of the NodeEnter ValidationError, in real time;
    - ``exception.caught`` traceback — within ~200ms of being
      written, well before run terminal;
    - ``kernel.run.stop outcome=…`` — durable terminal signal.

    When terminal lands the loop returns and we delegate the final
    summary to ``journal exceptions --json`` (the canonical sidecar
    reader, single SSOT). ``base_url`` is accepted for signature
    parity but no longer polled — the spine is the truth.
    """
    del base_url  # spine stream is the truth; no HTTP polling

    started = time.monotonic()
    typer.echo("[live SOP] streaming phase_graph / llm / tool / exception events…")

    def on_ep(ep: str, payload: dict) -> None:
        typer.echo(f"  [event] {_format_spine_event(ep, payload)}")

    def on_exc(cls: str, msg: str, src: dict) -> None:
        loc = f"{src.get('file', '?')}:{src.get('line', '?')}"
        typer.echo(f"  [exception] {cls}: {msg}")
        typer.echo(f"             at {loc}")

    streamed, spine_terminal, new_excs = _live_sop_run(run_id, on_ep, on_exc)
    elapsed = time.monotonic() - started

    if spine_terminal is None:
        typer.echo(
            f"[lca-ops runs create] hit {_LIVE_SOP_TAIL_CAP_S}s cap without "
            f"seeing kernel.run.stop for {run_id}; reporting partial SOP.",
            err=True,
        )

    exc_payload = _run_journal_exceptions_json(run_id, _DEFAULT_TRACES_ROOT)
    summary: dict = {
        "terminal_status": spine_terminal or "timeout",
        "elapsed_s": round(elapsed, 1),
        "tail_cap_s": _LIVE_SOP_TAIL_CAP_S,
        "events_streamed": streamed,
        "new_exceptions_streamed": new_excs,
    }
    if exc_payload is None:
        summary["exceptions"] = {"error": "subprocess returned no payload"}
    elif "error" in exc_payload:
        summary["exceptions"] = exc_payload
    else:
        records = exc_payload.get("records") or []
        first = records[0].get("payload") if records else {}
        first_msg = (first.get("exception_message") or "").splitlines()[0] if first else ""
        summary["exceptions"] = {
            "count": exc_payload.get("count", len(records)),
            "source": exc_payload.get("source"),
            "sidecar_path": exc_payload.get("exceptions_path"),
            "first_class": first.get("exception_class") if first else None,
            "first_message_head": first_msg,
        }
    return summary


def _render_post_create_report(run_id: str, report: dict) -> None:
    """Human-friendly SOP summary for non-JSON output."""
    typer.echo("")
    typer.echo("[post-create SOP summary]")
    terminal = report.get("terminal_status") or "unknown"
    elapsed = report.get("elapsed_s")
    streamed = report.get("events_streamed", 0)
    new_excs = report.get("new_exceptions_streamed", 0)
    typer.echo(f"  terminal status : {terminal}  ({elapsed}s)")
    typer.echo(f"  events streamed : {streamed} spine EPs printed live")
    typer.echo(f"  new exceptions  : {new_excs} surfaced live (≤200ms)")

    exc = report.get("exceptions") or {}
    if "error" in exc:
        typer.echo(f"  sidecar total   : error ({exc['error']})")
    else:
        count = exc.get("count", 0)
        sidecar = exc.get("sidecar_path") or "(no sidecar)"
        if count:
            cls = exc.get("first_class") or "?"
            head = exc.get("first_message_head") or ""
            typer.echo(f"  sidecar total   : {count} caught  ({cls}: {head})")
            typer.echo(f"                    sidecar: {sidecar}")
            typer.echo("                    ⚠ run outcome may look healthy (observer")
            typer.echo("                      failures are contained per AGENTS §C9).")
        else:
            typer.echo(f"  sidecar total   : 0 caught  ({exc.get('source', '?')})")
            typer.echo(f"                    sidecar: {sidecar}")

    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  lca-ops debug-run {run_id}")
    typer.echo(f"  lca-ops timeline {run_id}            # phase_graph tree")
    typer.echo(f"  lca-ops journal trace {run_id}        # default --human tree view")
    typer.echo(f"  lca-ops journal exceptions {run_id}    # ← REQUIRED after every run")
    if terminal != "success":
        typer.echo(f"  lca-ops explain {run_id}               # ← recommended (non-success)")


__all__ = ("CLIInProcessDispatcher", "register")
