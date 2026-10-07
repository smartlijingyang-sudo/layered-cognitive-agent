"""Unified memory edit synchronization, staleness detection, and diffing (INV-ARCH-06).

Consolidates diff generation, read-before-write freshness verification,
and semantic memory markdown edit event reconciliation.
Operates directly without referencing hypothetical file store port abstractions.
"""

from __future__ import annotations

import difflib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.memory import MemoryRecord

if TYPE_CHECKING:
    from lca.infrastructure.memory.assistant_memory import AssistantMemory

_log = logging.getLogger(__name__)

# --- Diff Utilities ---


def unified_diff(path: str, before: str, after: str) -> str:
    """Return a unified diff, or an empty string when the texts match."""
    if before == after:
        return ""
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=path,
        tofile=path,
        n=2,
    )
    return "".join(lines)


def render_standing_diff(changes: Sequence[tuple[str, str]]) -> str:
    """Render non-empty diffs as one note. ``changes`` is ``(path, diff)``."""
    visible = [(path, diff) for path, diff in changes if diff.strip()]
    if not visible:
        return ""
    parts = ["常驻文件有更新。以下是相对上一份副本的差异。"]
    for _path, diff in visible:
        parts.append(diff.rstrip())
    return "\n".join(parts)


# --- Read-Before-Write Staleness Guard ---


class StaleSnapshotOperationError(RuntimeError):
    """Raised when a memory edit targets a file that changed since the read."""


@dataclass(frozen=True, slots=True)
class FileVersion:
    """One file's identity: path and mtime ns."""

    path: str
    mtime_ns: int


def require_fresh(expected: FileVersion | None, current: FileVersion | None) -> None:
    """Raise when ``current`` differs from the version ``expected`` was read at.

    A missing file at either side is treated as an empty version and only
    conflicts when the other side reports a real file.
    """
    if current is None:
        if expected is None:
            return
        raise StaleSnapshotOperationError(f"file disappeared during edit: {expected.path}")
    if expected is None:
        raise StaleSnapshotOperationError(f"file appeared during edit: {current.path}")
    if expected.path != current.path or expected.mtime_ns != current.mtime_ns:
        raise StaleSnapshotOperationError(
            f"file changed during edit: {expected.path} (mtime {expected.mtime_ns} -> {current.mtime_ns})"
        )


# --- Memory Markdown Claim Reconciliation ---

_ID_RE = re.compile(r"<!--\s*id:([A-Za-z0-9_.-]+)\s*-->")
_SECTION_RE = re.compile(r"^##\s+(Preferences|Facts)\s*$", re.IGNORECASE)
_PLACEHOLDERS = ("暂无偏好记录", "暂无事实记录")


def _clean_body(text: str) -> tuple[str, str | None]:
    """Extract (clean claim body, embedded record id) from rendered bullet text."""
    record_id: str | None = None

    def _capture_id(m: re.Match) -> str:
        nonlocal record_id
        record_id = m.group(1)
        return ""

    no_id = _ID_RE.sub(_capture_id, text).strip()
    body = no_id.split(" This came from ")[0].strip() if " This came from " in no_id else no_id
    return body.rstrip("。").rstrip("."), record_id


def parse_memory_markdown_claims(
    markdown_text: str,
) -> list[tuple[MemoryCategory, str, str | None]]:
    """Parse a MEMORY.md string into structured (category, body, record_id) tuples."""
    items: list[tuple[MemoryCategory, str, str | None]] = []
    current_category: MemoryCategory = MemoryCategory.FACT

    for line in markdown_text.splitlines():
        line_stripped = line.strip()
        sec_match = _SECTION_RE.match(line_stripped)
        if sec_match:
            sec_name = sec_match.group(1).lower()
            current_category = (
                MemoryCategory.PREFERENCE if "pref" in sec_name else MemoryCategory.FACT
            )
            continue

        if not line_stripped.startswith(("- ", "* ")):
            continue

        bullet_content = line_stripped[2:].strip()
        if any(ph in bullet_content for ph in _PLACEHOLDERS):
            continue

        body, record_id = _clean_body(bullet_content)

        if body:
            items.append((current_category, body, record_id))

    return items


class MemoryEditSyncService:
    """Coordinates parsing of MEMORY.md edits and atomic writeback to AssistantMemory."""

    def __init__(self, memory: AssistantMemory) -> None:
        self._memory = memory

    def apply_markdown_edit(self, markdown_text: str) -> dict[str, int]:
        """Parse incoming Markdown and reconcile with active semantic records.

        Returns a dictionary with operation counts: {"added": N, "superseded": N, "deleted": N}.
        """
        parsed_items = parse_memory_markdown_claims(markdown_text)

        all_records = self._memory.query(MemoryLayer.SEMANTIC)
        active_records = [
            r
            for r in all_records
            if not r.deleted and r.category in (MemoryCategory.PREFERENCE, MemoryCategory.FACT)
        ]
        active_by_id = {r.record_id: r for r in active_records}

        seen_record_ids: set[str] = set()
        added_count = 0
        superseded_count = 0
        deleted_count = 0

        for category, body, parsed_id in parsed_items:
            if parsed_id and parsed_id in active_by_id:
                old = active_by_id[parsed_id]
                seen_record_ids.add(parsed_id)
                if old.content.strip() != body or old.category != category:
                    replacement = MemoryRecord(
                        record_id=new_id("mem"),
                        content=body,
                        category=category,
                        memory_type=MemoryLayer.SEMANTIC,
                        importance=old.importance,
                        dedupe_key=old.dedupe_key,
                        confidence=1.0,
                        metadata={"source": "user_edit"},
                        revision_of=old.record_id,
                    )
                    self._memory.supersede(old.record_id, replacement, reason="user_edit")
                    superseded_count += 1
            else:
                # Content fallback match for un-annotated bullets
                matched_existing = None
                for candidate in active_records:
                    if (
                        candidate.record_id not in seen_record_ids
                        and candidate.category == category
                        and candidate.content.strip() == body
                    ):
                        matched_existing = candidate
                        break

                if matched_existing is not None:
                    seen_record_ids.add(matched_existing.record_id)
                else:
                    new_rec = MemoryRecord(
                        record_id=new_id("mem"),
                        content=body,
                        category=category,
                        memory_type=MemoryLayer.SEMANTIC,
                        importance=0.9,
                        dedupe_key=new_id("key"),
                        confidence=1.0,
                        metadata={"source": "user_edit"},
                    )
                    self._memory.upsert(new_rec)
                    added_count += 1

        # Delete any active records not present in the new markdown
        for old_id in active_by_id:
            if old_id not in seen_record_ids:
                self._memory.remove(old_id)
                deleted_count += 1

        # Ensure projection is always fresh on disk even if 0 claim deltas occurred
        self._memory._project_curated(())

        _log.info(
            "MemoryEditSync applied: added=%d superseded=%d deleted=%d",
            added_count,
            superseded_count,
            deleted_count,
        )
        return {
            "added": added_count,
            "superseded": superseded_count,
            "deleted": deleted_count,
        }


def sync_memory_markdown(memory: AssistantMemory, markdown_text: str) -> dict[str, int]:
    """Convenience helper to apply a markdown edit to an AssistantMemory instance."""
    return MemoryEditSyncService(memory).apply_markdown_edit(markdown_text)


__all__ = [
    "FileVersion",
    "MemoryEditSyncService",
    "StaleSnapshotOperationError",
    "parse_memory_markdown_claims",
    "render_standing_diff",
    "require_fresh",
    "sync_memory_markdown",
    "unified_diff",
]
