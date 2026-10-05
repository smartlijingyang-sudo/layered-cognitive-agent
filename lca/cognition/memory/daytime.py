"""Record the user utterance from perceive, as evidence and as a residual.

A tool turn often ends at act, or at an approval interrupt, before reflect
runs. Perceive already holds the task and the assistant home, so the utterance
is recorded there. Reflect still records corrections and errors.

Two records come out of one utterance and neither gates the other. The trail is
raw evidence, written for every turn. The episode is a structured residual,
written only when ``govern()`` matches a closed template.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from lca.cognition.memory.govern import govern
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.curated import contains_secret
from lca.infrastructure.memory.contextfiles.service.indexing import index_trail_file
from lca.infrastructure.memory.contextfiles.service.trail import TrailWriter
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer

#: One trail line covers one utterance. The bound keeps a pasted document from
#: inflating the day's file, which ``run_dream`` maps line by line into facts.
_MAX_TRAIL_LINE_CHARS = 200


def episode_home(runtime: object) -> Path | None:
    """Home directory bound to this turn, or None when the run has no assistant home."""
    raw_home = _runtime_get(runtime, "assistant_home_path")
    if isinstance(raw_home, Path):
        return raw_home if str(raw_home).strip() else None
    if isinstance(raw_home, str) and raw_home.strip():
        return Path(raw_home)
    memory = _runtime_get(runtime, "memory")
    bound = getattr(memory, "home_path", None)
    if isinstance(bound, Path):
        return bound
    if isinstance(bound, str) and bound.strip():
        return Path(bound)
    return None


def record_task_episode(
    runtime: object,
    state: object,
    *,
    now_ms: int | None = None,
) -> bool:
    """Append the user utterance when it matches a closed template.

    Missing home, empty trace, or no template match returns False.
    Disk and template failures return False and do not propagate.
    """
    try:
        home = episode_home(runtime)
        if home is None or state is None:
            return False
        fact = govern(
            task=str(getattr(state, "task", "") or ""),
            trace_id=str(getattr(state, "trace_id", "") or ""),
            lesson=None,
            observation_success=None,
            observation_error=None,
            last_error=None,
            now_ms=int(time.time() * 1000) if now_ms is None else now_ms,
        )
        if fact is None:
            return False
        EpisodeBuffer(home).append(fact)
    except Exception:
        return False
    return True


def record_turn_trail(
    runtime: object,
    state: object,
    *,
    now_ms: int | None = None,
) -> bool:
    """Append the user utterance to the day's trail as raw evidence.

    Not gated by ``govern()``. A turn that matches no closed template still
    lands here, and ``run_dream`` decides what it is worth; that split is what
    lets an implicit preference such as 还是简洁一点好 survive until the offline
    pass instead of being dropped at the template gate.

    Credential-shaped content is refused before the write (ADR-0260 C3-3).
    Private personal material is not filtered here, because the trail is
    evidence and ``memory_search`` filters on the read side.

    The day's index document is refreshed once the append is durable, so the
    line is reachable by ``memory_search`` in the same turn instead of only
    after the next ``run_dream``. Index failure does not change the result.

    Missing home, empty utterance, disk failure, and a concurrent append that
    trips the trail's append-only narrow gate all return False and do not
    propagate. A lost line costs one turn of evidence; a raised error would
    fail the turn the user is waiting on.
    """
    try:
        home = episode_home(runtime)
        if home is None or state is None:
            return False
        text = str(getattr(state, "task", "") or "").strip()
        if not text or contains_secret(text):
            return False
        moment = int(time.time() * 1000) if now_ms is None else now_ms
        date = datetime.fromtimestamp(moment / 1000, tz=UTC).strftime("%Y-%m-%d")
        store = DiskFileStore(home)
        TrailWriter(store).append(date, text[:_MAX_TRAIL_LINE_CHARS])
    except Exception:
        return False
    # The evidence is durable at this point, so indexing sits outside the guard
    # above and cannot flip the result. index_trail_file contains its own
    # failures; run_dream's full rebuild is the backstop.
    index_trail_file(home, store, date)
    return True


def _runtime_get(runtime: object, key: str) -> object:
    getter = getattr(runtime, "get", None)
    if callable(getter):
        return getter(key)
    return None


__all__ = ["episode_home", "record_task_episode", "record_turn_trail"]
