"""Backend-owned per-topic conversation log: cross-run session self-healing.

The carrier client only persists assistant rows on terminal-success runs and
deliberately drops placeholder rows (ADR-0244 D1), so the ``messages[]`` it
sends on later runs can silently miss assistant turns. The backend keeps its
own second source of truth:

- **write**: on run terminal success, append the (last user text, final
  assistant text) pair to ``{assistant_home}/conversations/{topic_id}.jsonl``
  (JSON Lines, newest last, capped at the most recent 50 pairs).
- **read**: gap-fill — when ``extract_prior_turns`` sees two consecutive user
  turns with no assistant turn between them, the missing assistant reply is
  restored by normalized user-text lookup.

All disk I/O is warn-only: a logging failure must never fail or stall a run.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from lca.contracts.models.core.conversation.conversation import ConversationTurn

log = logging.getLogger(__name__)

MAX_STORED_PAIRS = 50
"""Cap per-topic pairs; older pairs are dropped from the head on append."""

_TOPIC_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def normalize_text(text: str) -> str:
    """Collapse all whitespace runs for stable cross-run matching."""
    return " ".join(text.split())


def conversation_log_path(assistant_home: Path, topic_id: str) -> Path:
    """Return the JSONL path for one topic (topic id sanitized for safety)."""
    safe_topic = _TOPIC_SAFE_RE.sub("_", topic_id.strip()).strip("._") or "untitled"
    return assistant_home / "conversations" / f"{safe_topic}.jsonl"


def _read_pairs(path: Path) -> list[dict[str, str]]:
    """Read stored pairs, newest last; corrupt lines are skipped, never fatal."""
    pairs: list[dict[str, str]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(obj, dict)
                    and isinstance(obj.get("user"), str)
                    and isinstance(obj.get("assistant"), str)
                ):
                    pairs.append({"user": obj["user"], "assistant": obj["assistant"]})
    except FileNotFoundError:
        pass
    return pairs


def append_conversation_turn(
    *,
    assistant_home: Path,
    topic_id: str,
    user_text: str,
    assistant_text: str,
    max_pairs: int = MAX_STORED_PAIRS,
) -> None:
    """Append one (user, assistant) pair to the per-topic log.

    Never raises: every I/O failure is logged as a warning and swallowed so
    the run's terminal transition is never held hostage by history logging.
    """
    try:
        path = conversation_log_path(assistant_home, topic_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        pairs = _read_pairs(path)
        pairs.append({"user": user_text, "assistant": assistant_text})
        pairs = pairs[-max(1, max_pairs) :]
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for pair in pairs:
                fh.write(json.dumps(pair, ensure_ascii=False) + "\n")
        tmp.replace(path)
    except Exception as exc:
        log.warning("conversation_log.append_failed topic_id=%s error=%s", topic_id, exc)


def find_assistant_reply(
    *,
    assistant_home: Path,
    topic_id: str,
    user_text: str,
) -> str | None:
    """Return the newest logged assistant reply for a normalized user text."""
    want = normalize_text(user_text)
    if not want:
        return None
    try:
        pairs = _read_pairs(conversation_log_path(assistant_home, topic_id))
    except Exception as exc:
        log.warning("conversation_log.read_failed topic_id=%s error=%s", topic_id, exc)
        return None
    for pair in reversed(pairs):
        if normalize_text(pair["user"]) == want:
            return pair["assistant"]
    return None


def fill_history_gaps(
    turns: list[ConversationTurn],
    *,
    assistant_home: Path,
    topic_id: str,
) -> list[ConversationTurn]:
    """Restore assistant turns the client failed to persist.

    A user turn directly followed by another user turn is the signature of a
    dropped assistant row (defect-1). The missing reply is looked up by
    normalized user text; each restoration is logged as a warning so the
    self-healing stays observable instead of silent.
    """
    if not turns:
        return list(turns)
    filled: list[ConversationTurn] = []
    for index, turn in enumerate(turns):
        if turn.role == "user" and index + 1 < len(turns) and turns[index + 1].role == "user":
            reply = find_assistant_reply(
                assistant_home=assistant_home,
                topic_id=topic_id,
                user_text=turn.content,
            )
            if reply:
                log.warning(
                    "conversation_log.gap_filled topic_id=%s user_text=%.60s",
                    topic_id,
                    turn.content,
                )
                filled.append(turn)
                filled.append(ConversationTurn(role="assistant", content=reply))
            else:
                log.warning(
                    "conversation_log.orphan_dropped topic_id=%s user_text=%.60s",
                    topic_id,
                    turn.content,
                )
        else:
            filled.append(turn)
    return filled


__all__ = [
    "MAX_STORED_PAIRS",
    "append_conversation_turn",
    "conversation_log_path",
    "fill_history_gaps",
    "find_assistant_reply",
    "normalize_text",
]
