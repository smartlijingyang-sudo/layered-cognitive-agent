"""Record one closed-template episode from the user utterance.

A tool turn often ends at act, or at an approval interrupt, before reflect
runs. Perceive already holds the task and the assistant home, so the
utterance is recorded there. Reflect still records corrections and errors.
"""

from __future__ import annotations

import time
from pathlib import Path

from lca.cognition.memory.govern import govern
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer


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


def _runtime_get(runtime: object, key: str) -> object:
    getter = getattr(runtime, "get", None)
    if callable(getter):
        return getter(key)
    return None


__all__ = ["episode_home", "record_task_episode"]
