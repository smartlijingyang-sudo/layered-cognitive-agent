"""In-memory reaction store with optional JSON persistence.

Reactions are keyed by message_id. A message can carry multiple reactions
(e.g. 🎉 from naming celebration plus 👍 from a later acknowledgement).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from lca.contracts.models.messaging.reaction import MessageReaction


class ReactionStore:
    """Thread-safe reaction storage.

    - 进程内 dict 为主存储，读写立即可见；
    - persist_path 指定时，每次写入后原子落盘 JSON，进程重启可恢复。
    """

    def __init__(self, persist_path: Path | str | None = None) -> None:
        self._lock = threading.Lock()
        self._reactions: dict[str, list[MessageReaction]] = {}
        self._persist_path = Path(persist_path) if persist_path else None
        if self._persist_path is not None and self._persist_path.is_file():
            self._load()

    def add(self, reaction: MessageReaction) -> MessageReaction:
        """写入一条 reaction（同一消息可贴多个）。"""
        with self._lock:
            self._reactions.setdefault(reaction.message_id, []).append(reaction)
            self._save_locked()
        return reaction

    def list_for(self, message_id: str) -> tuple[MessageReaction, ...]:
        """按 message_id 取出该消息的全部 reaction（按写入顺序）。"""
        with self._lock:
            return tuple(self._reactions.get(message_id, ()))

    def remove(self, message_id: str, emoji: str) -> bool:
        """撤回某条消息上的指定 emoji。返回是否命中。"""
        with self._lock:
            items = self._reactions.get(message_id)
            if not items:
                return False
            kept = [r for r in items if r.emoji != emoji]
            if len(kept) == len(items):
                return False
            if kept:
                self._reactions[message_id] = kept
            else:
                del self._reactions[message_id]
            self._save_locked()
            return True

    # ── persistence ──────────────────────────────────────────────

    def _load(self) -> None:
        assert self._persist_path is not None
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        for message_id, items in raw.items():
            if not isinstance(items, list):
                continue
            parsed: list[MessageReaction] = []
            for item in items:
                try:
                    parsed.append(MessageReaction.model_validate(item))
                except Exception:
                    continue
            if parsed:
                self._reactions[str(message_id)] = parsed

    def _save_locked(self) -> None:
        if self._persist_path is None:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                message_id: [r.model_dump(mode="json") for r in items]
                for message_id, items in self._reactions.items()
            }
            tmp = self._persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._persist_path)
        except Exception:
            # 落盘失败不炸主流程：内存数据仍有效
            pass
