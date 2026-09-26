"""``lca-ops memory dream`` — offline episode consolidation (ADR-0249).

Invocation is the enable. The command does not read ``os.environ``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path

import typer

from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.dream import run_dream

_Render = Callable[[Sequence[MemoryRecord]], str]
_Backfill = Callable[[str, list[MemoryRecord]], object]


def register(app: typer.Typer) -> None:
    """Register the ``memory`` command group."""
    memory_app = typer.Typer(help="Offline memory consolidation.", no_args_is_help=True)
    memory_app.command("dream")(_dream)
    app.add_typer(memory_app, name="memory")


def _dream_callbacks(home: Path) -> tuple[_Render, _Backfill]:
    from lca.plugins.assistant.profile.profile import (
        ProfileBackfillService,
        render_user_profile,
    )

    if not (home / "manifest.json").is_file():

        def _write_user_md(assistant_id: str, records: list[MemoryRecord]) -> None:
            del assistant_id
            (home / "USER.md").write_text(render_user_profile(records), encoding="utf-8")

        return render_user_profile, _write_user_md
    from lca.plugins.domain.assistant.catalog.plugin import _AssistantCatalogImpl

    catalog = _AssistantCatalogImpl(root=home.parent)
    service = ProfileBackfillService(catalog)

    def _backfill(assistant_id: str, records: list[MemoryRecord]) -> object:
        return service.backfill_from_records(assistant_id, records)

    return render_user_profile, _backfill


def _dream(
    home: Path = typer.Option(
        ...,
        "--home",
        help="Assistant home directory.",
    ),
    now_ms: int | None = typer.Option(
        None,
        "--now-ms",
        help="Epoch milliseconds. Default is the wall clock.",
    ),
) -> None:
    """Consolidate episode files into semantic memory."""
    clock = int(time.time() * 1000) if now_ms is None else now_ms
    render, backfill = _dream_callbacks(home)
    report = run_dream(home, now_ms=clock, backfill=backfill, render=render)
    typer.echo(report.model_dump_json())


__all__ = ["register"]
