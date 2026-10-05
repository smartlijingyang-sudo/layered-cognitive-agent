"""Periodic offline memory consolidation across assistant homes (ADR-0287 Phase 0).

The loop is plugin-hosted rather than cron-hosted. ``CronJob.execution`` is a
closed union that can only deliver a chat card or an avatar artifact, and
``next_run`` decides ``due`` by exact ``datetime`` equality that a discrete tick
never satisfies. Neither is changeable without an ADR.

Shape follows ``lca/plugins/avatar/plugin.py``, which already runs a background
scheduler in this process under this profile. One difference from that template
is load-bearing. ``layer`` is L4, not the avatar's L1, because
``_validate_layer_edges`` rejects a consumer whose layer rank is below its
provider's and ``assistant.catalog`` is provided at L4.

Dispose only signals ``DreamScheduler.stop``. A pass already inside ``run_dream``
runs to completion on its executor thread, because cancelling that await would
release the home's lock while ``run_dream`` still held it. A shutdown landing
mid-pass therefore waits for it, and nothing bounds that wait: executor threads
are non-daemon and are joined at loop shutdown. A healthy pass costs 11-30ms per
home, so the wait is normally invisible. A hung pass blocks the shutdown for as
long as it hangs. The 900s reclaim bound says when another process may take that
home's lock, not when this shutdown gives up.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lca.application.memory.dream_scheduler import (
    DreamScheduler,
    make_dream_callbacks,
    write_dream_evidence,
)
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import utc_now_ms
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.assistant.catalog import AssistantCatalog
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.path.locator import get_lca_home

__all__ = ["Config", "setup"]

# Strong references, so the sweep's task is not collected mid-pass (RUF006).
_scheduler_tasks: set[asyncio.Task[None]] = set()


class Config(BaseModel):
    """The cadence upper bound ADR-0287 §4 wants in configuration, not in prose."""

    model_config = ConfigDict(extra="forbid")

    tick_seconds: int = Field(default=300, gt=0)
    enabled: bool = True


def _homes(catalog: AssistantCatalog) -> Sequence[Path]:
    """Every catalogued home that has a memory tree, resolved, in catalog order.

    ``AssistantSummary.home_path`` is a ``str``. It is resolved here rather than
    per lock acquisition because ``_dream_lock_id`` hashes the path string while
    ``DiskFileStore`` writes through ``Path.resolve()``: one home reachable by
    two spellings would take two locks and could be dreamed twice at once.

    A home with no ``memory/`` is skipped rather than consolidated, so the sweep
    never manufactures a memory tree in a home that never had one. The ``is_dir``
    stat can raise ``OSError``, and ``run_forever``'s handler is what contains
    it; that handler is this callable's only supervisor.
    """
    homes: list[Path] = []
    for summary in catalog.list():
        home = Path(summary.home_path).resolve()
        if (home / "memory").is_dir():
            homes.append(home)
    return homes


@plugin(
    id="lca-memory-dream-scheduler",
    provides=(),
    requires=(ASSISTANT_CATALOG.key,),
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects="filesystem",
    description="Periodic offline memory consolidation across assistant homes (ADR-0287 Phase 0).",
    test_suite="tests/plugins/test_dream_scheduler_plugin_shape.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key,),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Start the sweep. A disabled config starts nothing and requires nothing."""
    if not config.enabled:
        return
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    if not isinstance(catalog, AssistantCatalog):
        raise TypeError(
            f"lca-memory-dream-scheduler requires {ASSISTANT_CATALOG.key} to be an "
            f"AssistantCatalog, got {type(catalog).__name__}"
        )
    scheduler = DreamScheduler(
        homes=lambda: _homes(catalog),
        # The host routine lock directory, the one the cron daemon already
        # holds ``cron.lock`` in. Dream lock ids are ``memory_dream:<digest>``,
        # so the two routines share a directory without sharing a lock.
        lock_dir=get_lca_home() / "locks",
        tick_seconds=config.tick_seconds,
        # The clock RoutineFileLock reads staleness from. Injecting a second
        # spelling of wall-clock milliseconds here would make the 900s reclaim
        # bound a comparison between two different clocks.
        now_ms=utc_now_ms,
        evidence_writer=write_dream_evidence,
        callbacks=make_dream_callbacks(catalog),
    )
    task = asyncio.create_task(scheduler.run_forever())
    _scheduler_tasks.add(task)
    task.add_done_callback(_scheduler_tasks.discard)
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]
    inner.effect(scheduler.stop, label="memory:dream-scheduler")
