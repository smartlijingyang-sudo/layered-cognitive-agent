"""Service for deterministic Markdown edit event parsing and writeback to semantic store.

Implements the "one source of truth, stateless lens" architecture for MEMORY.md:
User Markdown edits are parsed as discrete input events (ADD, SUPERSEDE, DELETE)
and dispatched to AssistantMemory, after which the stateless projection refreshes.
"""

from __future__ import annotations

import logging
import re

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory

_log = logging.getLogger(__name__)

_ID_RE = re.compile(r"<!--\s*id:([A-Za-z0-9_.-]+)\s*-->")
_SECTION_RE = re.compile(r"^##\s+(Preferences|Facts)\s*$", re.IGNORECASE)
_PLACEHOLDERS = ("暂无偏好记录", "暂无事实记录", "（空）")


def _clean_body(text: str) -> str:
    """Extract clean claim body from rendered bullet text."""
    no_id = _ID_RE.sub("", text).strip()
    if " This came from " in no_id:
        body = no_id.split(" This came from ")[0].strip()
    else:
        body = no_id.strip()
    return body.rstrip("。").rstrip(".")


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

        if current_category is None:
            continue

        if not (line_stripped.startswith("- ") or line_stripped.startswith("* ")):
            continue

        bullet_content = line_stripped[2:].strip()
        if any(ph in bullet_content for ph in _PLACEHOLDERS):
            continue

        id_match = _ID_RE.search(bullet_content)
        record_id = id_match.group(1) if id_match else None
        body = _clean_body(bullet_content)

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
        if hasattr(self._memory, "_project_curated"):
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


__all__ = [
    "MemoryEditSyncService",
    "parse_memory_markdown_claims",
]
