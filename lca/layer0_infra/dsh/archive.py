"""Append-only raw DSH notification log."""

from __future__ import annotations

from pathlib import Path

from lca.layer0_infra.dsh.models import DshNotification


class JsonlEventArchive:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, notification: DshNotification) -> None:
        line = notification.model_dump_json()
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")
