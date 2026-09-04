"""Diagnostics + boot-time snapshot writes for legacy run session creation.

ADR-0096 MVA-3: ``RuntimeObserved plugin.inventory`` events are filtered out of
the journal stream (see RunStore.append plugin.inventory filter). Their
canonical source moves to ``traces/runs/<id>/profile_snapshot.json``, written
once at run boot via ``RunBootSnapshot``.

This module still owns:
- ``plugin_inventory_from_boot_products`` — pure projection helper (used by
  architecture tests and the snapshot payload). P3 slim:返回 ``{id, layer,
  kind, effects}`` 列表而不是 ``"id|requires=...|provides=..."`` 拼接字符串;
  详细元数据随 ResolvedProfile 走 SSOT。
- ``RunBootSnapshotRecorder`` — invokes ``RunBootSnapshot.write`` at run
  creation time. Uses the same path resolver as the GET endpoint
  (``_profile_snapshot_path``) so reader and writer always agree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.observability.run_locator import RunLocator
from lca.harness.profile.boot_products import resolved_profile_from_scope
from lca.plugins.observability.profile_snapshot_run_boot_provider import (
    PluginSnapshotEntry,
    RunBootSnapshot,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession

_log = structlog.get_logger(__name__)

# Duplicated with lca.plugins.transport.webserver.handlers.runs.api.routes.query_endpoints; keep both in lockstep (MVA-3).
_PROFILE_SNAPSHOT_NAME = "profile_snapshot.json"
_DEFAULT_PROFILE_SNAPSHOT_ROOT = Path("traces") / "runs"


def plugin_inventory_from_boot_products(ctx: Any) -> list[PluginSnapshotEntry]:
    """Project active plugin declarations from immutable Profile boot products.

    P3 slim:返回 ``{id, layer, kind, effects}`` slim 形态,弃用旧 ``"|"`` 拼接串;
    description / config 详情在 ResolvedProfile 里(SSOT),不复制到 snapshot。
    """
    resolved = resolved_profile_from_scope(ctx)
    if resolved is None:
        return []
    entries: list[PluginSnapshotEntry] = []
    for entry in resolved.plugins:
        if entry.disabled:
            continue
        spec = entry.definition.spec
        # kind 在 PluginSpec 里是 PluginSpecKind(str Enum);effects 是 tuple[str]
        entries.append(
            PluginSnapshotEntry(
                id=entry.id,
                layer=spec.layer,
                kind=str(spec.kind.value if hasattr(spec.kind, "value") else spec.kind),
                effects=tuple(spec.effects),
            )
        )
    return entries


def _snapshot_outdir_for(run_id: str, ctx: Any) -> Path:
    """Resolve the snapshot outdir using the same locator as the GET endpoint.

    Reader path is ``outdir / profile_snapshot.json``
    (``query_endpoints._profile_snapshot_path``). Writer appends
    ``_PROFILE_SNAPSHOT_NAME`` inside ``RunBootSnapshot.write``.
    """
    if ctx is None:
        return _DEFAULT_PROFILE_SNAPSHOT_ROOT / run_id
    try:
        locator = require_capability(ctx, "run_locator")
    except MissingCapabilityError:
        locator = None
    if isinstance(locator, RunLocator):
        return locator.run_dir(run_id)
    return _DEFAULT_PROFILE_SNAPSHOT_ROOT / run_id


class RunBootSnapshotRecorder:
    """Write the boot-time profile snapshot JSON once per run session creation.

    Replaces ``RunPluginInventoryRecorder`` (ADR-0096 MVA-3 §13.4 V18):
    the previous recorder emitted journal events that are now filtered.
    """

    def __init__(self, *, ctx: Any) -> None:
        self._ctx = ctx

    def record(self, session: RunSession) -> None:
        plugins = plugin_inventory_from_boot_products(self._ctx)
        # Capability map: best-effort; consumers should treat missing keys as False
        capabilities: dict[str, bool] = {}
        for entry in plugins:
            capabilities[str(entry["id"])] = True
        outdir = _snapshot_outdir_for(str(session.run_id), self._ctx)
        try:
            RunBootSnapshot().write(
                run_id=str(session.run_id),
                outdir=outdir,
                # ADR-0068 §决策二:RunSession.plan_ref 由 builder 阶段 _compute_plan_ref
                # 填好,字段已固化(2026-09 引入)。这里直接读,不再 ``getattr`` 兜底,
                # 因为缺字段应 fail-loud 而不是 silent 默认 "" —— silent 默认会让
                # "session.plan_ref 没被 builder 填" 这类回归永远藏起来。
                plan_ref=str(session.plan_ref),
                plugins=plugins,
                capabilities=capabilities,
                control_plan={
                    "version": "v3",
                    "phases": ["perceive", "think", "gate", "act", "reflect", "remember", "stop"],
                },
            )
        except Exception:
            # Snapshot write is diagnostic, not blocking.
            _log.warning(
                "profile_snapshot_write_failed",
                run_id=str(session.run_id),
                snapshot=_PROFILE_SNAPSHOT_NAME,
                exc_info=True,
            )


__all__ = ["RunBootSnapshotRecorder", "plugin_inventory_from_boot_products"]
