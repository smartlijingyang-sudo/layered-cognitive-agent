"""lobehub-stack CLI — commands come from YAML, steps from the registry."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from deploy.lobehub.stack.config import DEFAULT_YAML_PATH, StackConfig
from deploy.lobehub.stack.inspect import build_delta, restart_reason
from deploy.lobehub.stack.ops import (
    inspect_gateway,
    inspect_host,
    inspect_infra,
    inspect_lobehub,
    inspect_patches,
    provision_host,
    restart_gateway,
    snapshot_gateway,
    start_gateway,
    start_infra,
    start_lobehub_dev,
    stop_stack,
    sync_lobehub,
)
from deploy.lobehub.stack.report import banner, render_report
from deploy.lobehub.stack.session import StackSession
from deploy.lobehub.stack.types import ProcessSnapshot, StackReport, Status

ROOT = Path(__file__).resolve().parents[3]

StepFn = Callable[[StackSession], None]

STEPS: dict[str, StepFn] = {
    "gateway.snapshot": snapshot_gateway,
    "gateway.start": start_gateway,
    "gateway.restart": restart_gateway,
    "gateway.inspect": inspect_gateway,
    "patches.inspect": inspect_patches,
    "host.provision": provision_host,
    "host.inspect": inspect_host,
    "lobehub.inspect": inspect_lobehub,
    "lobehub.dev": start_lobehub_dev,
    "lobehub.sync": sync_lobehub,
    "infra.inspect": inspect_infra,
    "infra.start": start_infra,
    "stack.stop": stop_stack,
}


def _verdict(session: StackSession) -> str:
    if session.failed:
        return "failed"
    mutating = session.command in {"restart-gateway", "gateway", "dev", "restart"}
    if mutating and (session.current is None or not session.current.alive):
        return "failed"
    if any(not surface.classified or surface.probe_status is Status.ERROR for surface in session.surfaces):
        return "degraded"
    for section in session.sections:
        if any(check.status in {Status.ERROR, Status.MISSING} for check in section.checks):
            return "degraded"
    if session.current is not None and not session.current.alive:
        return "degraded"
    return "ready"


def run_command(session: StackSession) -> int:
    spec = session.config.commands.get(session.command)
    if spec is None:
        session.stream.write(f"unknown command: {session.command}\n")
        return 2
    session.emit(banner(session.command, spec.description))
    for step in spec.steps:
        fn = STEPS.get(step)
        if fn is None:
            session.stream.write(f"unregistered step: {step}\n")
            return 2
        fn(session)
    current = session.current or ProcessSnapshot(port=session.config.gateway.port)
    reason = restart_reason(
        force=session.command in {"restart-gateway", "restart"},
        previous=session.previous,
        newer=session.newer,
    )
    report = StackReport(
        command=session.command,
        verdict=_verdict(session),  # type: ignore[arg-type]
        process=current,
        surfaces=session.surfaces,
        sections=session.sections,
        delta=build_delta(
            previous=session.previous,
            current=current,
            newer=session.newer,
            root=session.root,
            reason=reason,
        )
        if session.previous is not None or session.newer
        else None,
    )
    if session.json_mode:
        session.stream.write(report.model_dump_json(indent=2) + "\n")
    else:
        session.stream.write(render_report(report))
    return 0 if report.verdict != "failed" else 1


def build_parser() -> argparse.ArgumentParser:
    commands = ", ".join(StackConfig().commands)
    parser = argparse.ArgumentParser(
        prog="lobehub-stack",
        description="LCA + LobeHub stack — YAML-driven, inspectable, step-registered",
    )
    parser.add_argument("command", nargs="?", default="dev", help=f"one of: {commands}")
    parser.add_argument("--config", "-c", default=str(DEFAULT_YAML_PATH), help="stack.yaml path")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = StackConfig.from_yaml_or_default(args.config).apply_environ()
    if args.command not in config.commands:
        parser.print_help()
        return 2
    session = StackSession(
        root=ROOT,
        config=config,
        command=args.command,
        json_mode=bool(args.json),
    )
    return run_command(session)


if __name__ == "__main__":
    sys.exit(main())
