"""Journal log following: tail the spine SSOT for the most recent run.

ADR-2026-09-02-i17-stream-align §A — the legacy v2 stream envelope
(``record_to_stamped`` / ``FactStreamProjector``) is retired (ADR-0164 Phase 7).
The CLI now reads the spine SSOT directly: ``traces/runs/<run_id>/events.jsonl``.
Live mode tails the most recent run's file; ``--replay`` re-reads a specific
run from disk.
"""

from __future__ import annotations

import json
import time as _time
from collections.abc import Iterator
from pathlib import Path

import typer

from lca.infrastructure.cli.commands._shared import find_latest_run_id
from lca.infrastructure.cli.config import OpsConfig

# Refusal codes returned by the kernel_serve HTTP layer when it explicitly
# refuses a journal subscription. We surface these verbatim so operators
# don't chase ghosts.
_KERNEL_SERVE_REFUSAL_CODES = {
    "legacy_process_journal_unavailable": (
        "Session Spine 已不再暴露全局 /journal/live；请改用下列任一路径查看 journal 事实：",
        [
            "./scripts/lca-ops journal logs           # tail 最新 run 的 events.jsonl",
            "./scripts/lca-ops journal logs --replay <run_id>  # 离线回放",
            "tail -f traces/runs/$(ls -t traces/runs | head -1)/events.jsonl",
        ],
    ),
}


def create_journal_group(app: typer.Typer) -> typer.Typer:
    """Create the ``journal`` sub-Typer and attach it to ``app``.

    Returns the journal Typer so other modules can register commands on the
    same group (e.g. ``journal_steps`` adds ``steps`` / ``narrative`` / ``raw``).
    """
    journal_app = typer.Typer(help="Journal facts / steps / narrative viewer")
    app.add_typer(journal_app, name="journal")
    return journal_app


def register(app: typer.Typer, group: typer.Typer | None = None) -> None:
    """Register the ``logs`` command under the ``journal`` group.

    ``group`` 应是 ``create_journal_group(app)`` 的返回值。 兼容旧签名:
    传 ``app`` 时自动 add_typer 一次(单文件测试场景)。
    """
    if group is None:
        group = create_journal_group(app)

    @group.command(name="logs")
    def logs(
        target: str = typer.Argument(
            "",
            help="空=tail 最新 run 的 spine SSOT；lobehub | daemon = 进程日志",
        ),
        replay: str = typer.Option(
            "",
            "--replay",
            "-r",
            help="离线回放指定 run_id(读 traces/runs/<id>/events.jsonl)",
        ),
        verbose: bool = typer.Option(
            False, "--verbose", "-v", help="显示完整 payload（默认仅控制点 + channel + outcome）"
        ),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """事实流。默认 follow 最新 run 的 spine SSOT(events.jsonl),不是 kernel_serve.log。"""
        ops_config = OpsConfig.load(config)
        if target in {"", "journal", "kernel_serve"}:
            _follow_spine_ssot(replay=replay, verbose=verbose)
            return
        import subprocess

        log_map = {
            "lobehub": ops_config.state_dir / "lobehub.log",
            "daemon": Path(f"/home/{ops_config.daemon.user}/.lca/daemon.log"),
        }
        if target not in log_map:
            print(f"Unknown target: {target}. Use: journal, lobehub, daemon")
            raise typer.Exit(1)
        log_file = log_map[target]
        if not log_file.exists():
            print(f"No log yet: {log_file}")
            raise typer.Exit(1)
        subprocess.run(["/usr/bin/tail", "-f", str(log_file)])  # noqa: S603


# ────────────────────────── spine SSOT projection ──────────────────────────


def _find_latest_run_dir() -> Path | None:
    """Pick the most recently mutated run directory under ``traces/runs/``.

    Thin wrapper around :func:`lca.infrastructure.cli.commands._shared.find_latest_run_id`
    that returns the directory (not just the run_id) so callers that
    already operate on paths don't have to re-glue ``traces/runs``.
    """
    run_id = find_latest_run_id()
    if run_id is None:
        return None
    return Path("traces/runs") / run_id


def _events_jsonl_for(run_dir: Path) -> Path | None:
    """Return the events.jsonl under a run directory if present."""
    candidate = run_dir / "events.jsonl"
    return candidate if candidate.exists() else None


def _iter_jsonl(path: Path) -> Iterator[dict[str, object]]:
    """Yield non-empty JSON lines from a jsonl file (tolerant to mid-write)."""
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                # Mid-write partial line — skip and retry on next pass.
                continue
            if isinstance(obj, dict):
                yield obj


def _render_event(event: dict[str, object], *, verbose: bool, run_dir: Path | None = None) -> str:
    """One-line human rendering of a spine event."""
    when = str(event.get("when") or event.get("when_corrected") or "")
    seq = event.get("sequence", 0)
    ep = str(event.get("execution_point", "?"))
    channel = str(event.get("channel", "?"))
    outcome = event.get("outcome")
    line = f"{when[:23]}  seq={seq:<3} ch={channel:<8} ep={ep}"
    if outcome:
        line += f"  outcome={outcome}"
    if not verbose:
        return line

    # Spine v3: large events get offloaded to ``<sha256>.json`` and the
    # in-place line is a 2-field placeholder. ``journal logs -v`` must
    # follow the sidecar so the operator sees the actual traceback,
    # not the bare ``{offloaded: <digest>}`` line (Bug D consumer side).
    offloaded = event.get("offloaded")
    if isinstance(offloaded, str) and offloaded and run_dir is not None:
        sidecar = run_dir / f"{offloaded}.json"
        if sidecar.is_file():
            try:
                full = json.loads(sidecar.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                full = {}
            if isinstance(full, dict):
                tb = _extract_traceback(full) or json.dumps(full, ensure_ascii=False, default=str)
                line += (
                    "\n    [offloaded payload from " + offloaded + ".json]:\n" + _indent(tb, "    ")
                )
                return line

    payload = event.get("payload")
    if isinstance(payload, dict) and payload:
        line += "\n    payload: " + json.dumps(payload, ensure_ascii=False, default=str)
    if channel == "error":
        tb = _extract_traceback(event)
        if tb:
            line += "\n    traceback:\n" + _indent(tb, "    ")
    return line


def _extract_traceback(event: dict[str, object]) -> str:
    """Pull the most informative failure detail from an error-channel event."""
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return ""
    tb = payload.get("traceback_text")
    if isinstance(tb, str) and tb.strip():
        return tb.rstrip()
    # Fall back to producer-side exception text when the wrap-layer didn't pass one.
    exc_type = payload.get("exception_class") or payload.get("exc_type")
    message = payload.get("exception_message") or payload.get("reason")
    if exc_type or message:
        return f"{exc_type or 'Exception'}: {message or ''}"
    return ""


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _tail_events_jsonl(path: Path, *, verbose: bool, run_dir: Path | None = None) -> None:
    """Follow a jsonl file and render new lines as they are appended."""
    if run_dir is None:
        run_dir = path.parent
    print(f"[journal] tail {path}")
    last_size = path.stat().st_size
    while True:
        try:
            current_size = path.stat().st_size
            if current_size < last_size:
                # Truncation / rotation — restart from beginning.
                last_size = 0
            if current_size > last_size:
                with path.open("r", encoding="utf-8") as handle:
                    handle.seek(last_size)
                    new_text = handle.read(current_size - last_size)
                for line in new_text.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        obj = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict):
                        print(_render_event(obj, verbose=verbose, run_dir=run_dir))
                last_size = current_size
        except FileNotFoundError:
            # Run rotated out — try to recover.
            new_dir = _find_latest_run_dir()
            new_path = new_dir / "events.jsonl" if new_dir else None
            if new_path is None or not new_path.exists():
                _time.sleep(1.0)
                continue
            print(f"[journal] switch tail → {new_path}")
            path = new_path
            run_dir = new_dir
            last_size = 0
        _time.sleep(0.2)


def _replay_events_jsonl(path: Path, *, verbose: bool, run_dir: Path | None = None) -> None:
    """One-shot read of a jsonl file and render each line."""
    if run_dir is None:
        run_dir = path.parent
    if not path.exists():
        print(f"No journal file at {path}")
        raise typer.Exit(1)
    total = 0
    rendered = 0
    for event in _iter_jsonl(path):
        total += 1
        print(_render_event(event, verbose=verbose, run_dir=run_dir))
        rendered += 1
    print(f"\n── replay done: {rendered}/{total} events ──")


def _follow_spine_ssot(*, replay: str, verbose: bool) -> None:
    """Top-level entry for ``journal logs``.

    With ``--replay <run_id>`` (or first positional) → one-shot replay of
    that run's events.jsonl. Otherwise tail the latest run.
    """
    if replay:
        run_dir = Path("traces/runs") / replay
        path = _events_jsonl_for(run_dir)
        if path is None:
            print(f"No events.jsonl under {run_dir}")
            raise typer.Exit(1)
        _replay_events_jsonl(path, verbose=verbose, run_dir=run_dir)
        return

    latest = _find_latest_run_dir()
    if latest is None:
        print("No runs under traces/runs/. Start a run first.")
        raise typer.Exit(1)
    path = _events_jsonl_for(latest)
    if path is None:
        print(f"No events.jsonl under {latest}")
        raise typer.Exit(1)
    try:
        _replay_events_jsonl(path, verbose=verbose, run_dir=latest)
        # After replay we drop into tail mode so the operator can keep watching.
        _tail_events_jsonl(path, verbose=verbose, run_dir=latest)
    except KeyboardInterrupt:
        raise typer.Exit(0) from None
