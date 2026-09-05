"""ProjectionCache write-behind persistence tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lca.contracts.protocols.session.projection_unit import ProjectionCheckpoint
from lca.infrastructure.persistence.atomic_json_sink import AtomicJsonFileSink, AtomicJsonSnapshot
from lca.plugins.session.projection_cache.projection_cache import ProjectionCache
from lca.plugins.session.runtime.session import Session


class _StubRegistry:
    def checkpoint(self, session: Any) -> dict[str, ProjectionCheckpoint]:
        return {
            "stats": ProjectionCheckpoint(version=1, seq=session.seq, state={"n": session.seq}),
        }

    def state_version_of(self, key: str) -> int | None:
        return 1 if key == "stats" else None

    def restore(self, rows: dict[str, Any], events: tuple[Any, ...], header: Any) -> Any:
        del rows, events, header
        return type("R", (), {"snapshot": object()})()


def test_projection_cache_save_enqueues_and_flush_writes(tmp_path: Path) -> None:
    cache = ProjectionCache(_StubRegistry(), cache_root=tmp_path)
    session = Session("run_proj_1")
    assert cache.save(session) is True
    assert not cache.path_for("run_proj_1").exists()
    cache.flush_sync()
    doc = json.loads(cache.path_for("run_proj_1").read_text(encoding="utf-8"))
    assert doc["stats"]["seq"] == 0


def test_atomic_json_sink_coalesces_duplicate_paths(tmp_path: Path) -> None:
    path = tmp_path / "a.projcache.json"
    sink = AtomicJsonFileSink()
    sink.append_batch(
        [
            AtomicJsonSnapshot(path=path, encoded='{"v":1}'),
            AtomicJsonSnapshot(path=path, encoded='{"v":2}'),
        ]
    )
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 2}


def test_projection_cache_close_disposes_pending(tmp_path: Path) -> None:
    cache = ProjectionCache(_StubRegistry(), cache_root=tmp_path)
    session = Session("run_proj_close")
    cache.register_to(session)
    assert cache.save(session) is True
    cache.close()
    assert cache.path_for("run_proj_close").exists()
