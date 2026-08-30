"""State management — change detection and process tracking.

Two responsibilities:
1. Change detection — what source files changed since last snapshot?
2. Process tracking — where are the PID files?

Change detection returns ``ChangeReport`` — not a bare bool.
Every service sees the same shape: what changed, summary line, file list.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChangeReport:
    """What changed in a source tree since the last snapshot.

    Unified output for every service's status display.
    """

    modified: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    @property
    def has_changes(self) -> bool:
        return bool(self.modified or self.added or self.removed)

    @property
    def summary(self) -> str:
        if not self.has_changes:
            return "up-to-date"
        parts: list[str] = []
        if self.modified:
            parts.append(f"{len(self.modified)} modified")
        if self.added:
            parts.append(f"{len(self.added)} added")
        if self.removed:
            parts.append(f"{len(self.removed)} removed")
        return ", ".join(parts)

    def detail_lines(self, limit: int = 5) -> list[str]:
        """Human-readable file list, capped."""
        all_files = [
            *(f"  M {p}" for p in self.modified),
            *(f"  + {p}" for p in self.added),
            *(f"  - {p}" for p in self.removed),
        ]
        shown = all_files[:limit]
        if len(all_files) > limit:
            shown.append(f"  … and {len(all_files) - limit} more")
        return shown


class StateStore:
    """Manages runtime state: manifests for change detection, paths for PIDs.

    Design: filesystem-based, no database. Simple, debuggable, git-ignorable.
    """

    def __init__(self, state_dir: Path) -> None:
        self._dir = state_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Change Detection (unified) ────────────────────────────────────

    def detect_changes(self, key: str, paths: list[Path], pattern: str = "*") -> ChangeReport:
        """Compare current source tree against last snapshot.

        Returns ``ChangeReport`` with modified/added/removed file lists.
        If no snapshot exists yet, saves one immediately (first-run baseline)
        and returns an empty report — the running process IS the baseline.
        """
        manifest_path = self._manifest_file(key)
        if not manifest_path.exists():
            self.save_snapshot(key, paths, pattern)
            return ChangeReport()

        previous = self._load_manifest(manifest_path)
        current = self._scan(paths, pattern)

        modified: list[str] = []
        added: list[str] = []
        removed: list[str] = []

        for rel_path in sorted(current):
            _, content_hash = current[rel_path]
            if rel_path not in previous:
                added.append(rel_path)
            else:
                _, prev_hash = previous[rel_path]
                if content_hash != prev_hash:
                    modified.append(rel_path)

        for rel_path in sorted(previous):
            if rel_path not in current:
                removed.append(rel_path)

        return ChangeReport(
            modified=tuple(modified),
            added=tuple(added),
            removed=tuple(removed),
        )

    def save_snapshot(self, key: str, paths: list[Path], pattern: str = "*") -> None:
        """Save current source tree state as the new baseline."""
        manifest_path = self._manifest_file(key)
        current = self._scan(paths, pattern)
        manifest_path.write_text(json.dumps(current, indent=None, sort_keys=True))

    def has_snapshot(self, key: str) -> bool:
        """Whether a baseline snapshot exists for this key."""
        return self._manifest_file(key).exists()

    # ── Backward compat ───────────────────────────────────────────────

    def has_changed(self, key: str, paths: list[Path], pattern: str = "*.py") -> bool:
        """Bool-only check. Prefer ``detect_changes`` for rich output."""
        return self.detect_changes(key, paths, pattern).has_changes

    def save_stamp(self, key: str, paths: list[Path], pattern: str = "*.py") -> None:
        """Alias for save_snapshot with legacy signature."""
        self.save_snapshot(key, paths, pattern)

    # ── PID Files ─────────────────────────────────────────────────────

    def pid_file(self, service_name: str) -> Path:
        return self._dir / f"{service_name}.pid"

    def read_pid(self, service_name: str) -> int | None:
        pid_file = self.pid_file(service_name)
        if not pid_file.exists():
            return None
        try:
            return int(pid_file.read_text().strip())
        except (ValueError, OSError):
            return None

    def write_pid(self, service_name: str, pid: int) -> None:
        self.pid_file(service_name).write_text(str(pid))

    def remove_pid(self, service_name: str) -> None:
        self.pid_file(service_name).unlink(missing_ok=True)

    # ── Log Files ─────────────────────────────────────────────────────

    def log_file(self, service_name: str) -> Path:
        return self._dir / f"{service_name}.log"

    # ── Internals ─────────────────────────────────────────────────────

    def _manifest_file(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace(".", "_")
        return self._dir / f"{safe_key}.manifest.json"

    def _load_manifest(self, path: Path) -> dict[str, tuple[float, str]]:
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text())
            return {k: (float(v[0]), str(v[1])) for k, v in raw.items()}
        except (json.JSONDecodeError, TypeError, KeyError):
            return {}

    @staticmethod
    def _scan(paths: list[Path], pattern: str) -> dict[str, tuple[float, str]]:
        """Scan source tree: relative_path → (mtime, content_hash)."""
        result: dict[str, tuple[float, str]] = {}
        for base in paths:
            if not base.exists():
                continue
            files = [base] if base.is_file() else sorted(base.rglob(pattern))
            for f in files:
                if not f.is_file():
                    continue
                rel = str(f.relative_to(base.parent))
                stat = f.stat()
                content_hash = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
                result[rel] = (stat.st_mtime, content_hash)
        return result
