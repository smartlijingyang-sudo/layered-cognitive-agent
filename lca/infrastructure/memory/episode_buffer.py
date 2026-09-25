"""Append-only episode files under ``{home}/memory/episodes`` (ADR-0249).

No cap: dropping a file would change a later recurrence count.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from lca.contracts.models.memory.episode import EpisodeFact


@dataclass(frozen=True, slots=True)
class EpisodeRead:
    facts: tuple[EpisodeFact, ...]
    skipped: int


class EpisodeBuffer:
    """One JSON file per fact. Corrupt files are skipped, never deleted."""

    def __init__(self, home: Path) -> None:
        self._home = Path(home)

    @property
    def directory(self) -> Path:
        return self._home / "memory" / "episodes"

    def append(self, fact: EpisodeFact) -> Path:
        directory = self.directory
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{fact.fact_id}.json"
        temporary = directory / f".{fact.fact_id}.tmp"
        temporary.write_text(fact.model_dump_json(), encoding="utf-8")
        try:
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def read_all(self) -> EpisodeRead:
        directory = self.directory
        if not directory.is_dir():
            return EpisodeRead(facts=(), skipped=0)
        facts: list[EpisodeFact] = []
        skipped = 0
        for path in directory.glob("*.json"):
            try:
                facts.append(EpisodeFact.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValidationError, ValueError):
                skipped += 1
        facts.sort(key=lambda fact: fact.fact_id)
        return EpisodeRead(facts=tuple(facts), skipped=skipped)


__all__ = ["EpisodeBuffer", "EpisodeRead"]
