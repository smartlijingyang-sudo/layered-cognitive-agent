"""CLI entry point — thin shell that delegates to focused command modules.

Responsibilities:
- Construct the typer app with the operator-facing ``GUIDE`` banner.
- Register every command group via its ``register(app)`` entry point.
- Forward ``lca-ops logs`` to ``journal logs`` (legacy alias kept for
  documentation and tests that still reference the old name; see
  ``logs_alias``).

The banner text itself lives in :mod:`lca.infrastructure.cli.guide`.
Command surface lives in :mod:`lca.infrastructure.cli.commands`.

Backward compatibility: ``from lca.infrastructure.cli.cli import app``
still works — tests and scripts import ``app`` directly.
"""

from __future__ import annotations

from pathlib import Path

import typer

# Side-effect import: ``lca.infrastructure.cli.steps`` populates the global
# step registry that ``commands.workflow`` and ``commands.services``
# look up via ``build_pipeline``. The modules themselves never reference
# step functions by name; the import here is the only place that wires
# the registry before any command runs.
import lca.infrastructure.cli.steps  # noqa: F401  -- step registration
from lca.infrastructure.cli.commands import (
    audit,
    creator_plan,
    declarative,
    diagnostics,
    events_delivery,
    journal,
    journal_exceptions,
    journal_replay,
    journal_step,
    journal_steps,
    journal_trace,
    kernel,
    notes,
    package_organization,
    profile_inspect,
    runs,
    services,
    tools,
    workflow,
)
from lca.infrastructure.cli.guide import GUIDE

app = typer.Typer(
    name="lca-ops",
    help=GUIDE,
    rich_markup_mode=None,
    add_completion=False,
    invoke_without_command=True,
    context_settings={"help_option_names": ["--help", "-h"]},
)


@app.callback()
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(GUIDE)
        raise typer.Exit(0)


# Register all command groups
workflow.register(app)
services.register(app)
journal.register(app)
runs.register(app)
tools.register(app)
profile_inspect.register(app)
diagnostics.register(app)
events_delivery.register(app)
package_organization.register(app)
audit.register(app)
creator_plan.register(app)
declarative.register(app)
# ``journal`` owns the ``journal`` typer group; the four siblings below
# add their subcommands to that same group rather than calling
# add_typer again (typer would create a duplicate group entry).
_journal_group = journal.create_journal_group(app)
journal.register(app, group=_journal_group)
journal_steps.register(_journal_group)
journal_trace.register(_journal_group)
journal_replay.register(_journal_group)
journal_exceptions.register(_journal_group)
journal_step.register(_journal_group)
kernel.register(app)
notes.register(app)


# ── legacy alias: `lca-ops logs` → `journal logs` ──────────────────
# Kept because the canonical name changed and external references
# (kernel boot trace docstring, agent runbook examples, tests
# test_plugin_tree_single_owner.py) still spell ``lca-ops logs``. The
# handler is a one-line forward — no flag duplication.


@app.command(
    name="logs",
    help="(alias for `journal logs`) tail the spine SSOT of the latest run.",
)
def logs_alias(
    target: str = typer.Argument(
        "",
        help="空=tail 最新 run；lobehub | daemon = 进程日志(同 journal logs)",
    ),
    replay: str = typer.Option("", "--replay", "-r", help="(同 -r) 离线回放指定 run_id"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="(同 -v) 显示完整 payload + sidecar traceback"
    ),
    config: Path | None = typer.Option(  # noqa: B008 — typer Option sentinel
        None, "--config", "-c", help="(同 -c) 配置文件"
    ),
) -> None:
    """Forward all args to ``journal logs``. See ``journal logs --help``."""
    from lca.infrastructure.cli.commands.journal import _follow_spine_ssot

    _follow_spine_ssot(replay=replay, verbose=verbose)


def main() -> None:
    """Entry point for scripts/lca-ops."""
    app()


if __name__ == "__main__":
    main()
