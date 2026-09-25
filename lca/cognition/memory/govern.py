"""Closed-template governor for one daytime episode fact (ADR-0249).

No disk and no model call. At most one fact, instruction then correction then error.
"""

from __future__ import annotations

import hashlib
import re

from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.memory.episode import (
    EpisodeFact,
    ResidualClass,
    canonical_dedupe_key,
)

_ROLE = re.compile(r"我是(.+)")
_NAME = re.compile(r"我叫(.+)|叫我(.+)")
_QUOTES = "\"'「」"
_VERBOSITY = ("简洁", "啰嗦", "详细")
_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _clean_capture(raw: str) -> str | None:
    cleaned = "".join(char for char in raw if char not in _QUOTES).strip()
    if not cleaned:
        return None
    return cleaned[:40]


def _match_template(text: str) -> tuple[MemoryCategory, str, str, bool] | None:
    if not text.strip():
        return None
    role = _ROLE.search(text)
    if role:
        captured = _clean_capture(role.group(1))
        if captured:
            return (
                MemoryCategory.IDENTITY,
                "identity:role",
                f"用户身份：{captured}",
                True,
            )
    name = _NAME.search(text)
    if name:
        captured = _clean_capture(name.group(1) or name.group(2) or "")
        if captured:
            return (
                MemoryCategory.IDENTITY,
                "identity:name",
                f"用户身份：{captured}",
                True,
            )
    if ("记住" in text or "以后" in text) and any(token in text for token in _VERBOSITY):
        for token in _VERBOSITY:
            if token in text:
                return (
                    MemoryCategory.PREFERENCE,
                    "preference:verbosity",
                    f"用户偏好：{token}",
                    False,
                )
    return None


def _exception_token(text: str) -> str:
    raw = text.strip()
    if not raw:
        return "Error"
    cut = len(raw)
    for index, char in enumerate(raw):
        if char.isspace() or char == ":":
            cut = index
            break
    token = raw[:cut]
    if token and _TOKEN.fullmatch(token):
        return token
    return "Error"


def _error_text(
    *,
    observation_success: bool | None,
    observation_error: str | None,
    last_error: str | None,
) -> str | None:
    observed = (observation_error or "").strip()
    last = (last_error or "").strip()
    if observation_success is not False and not last:
        return None
    if observation_success is False and observed:
        return observed
    if last:
        return last
    return observed


def _fact_id(trace_id: str, dedupe_key: str, content: str, residual: ResidualClass) -> str:
    payload = f"{trace_id}\n{dedupe_key}\n{content}\n{residual.value}".encode()
    return "ep_" + hashlib.sha256(payload).hexdigest()[:16]


def govern(
    *,
    task: str,
    trace_id: str,
    lesson: str | None,
    observation_success: bool | None,
    observation_error: str | None,
    last_error: str | None,
    now_ms: int,
) -> EpisodeFact | None:
    """Return one episode fact, or None when the turn has no closed-template residual."""
    if not trace_id.strip():
        return None
    matched = _match_template(task)
    residual = ResidualClass.instruction
    if matched is None and lesson is not None:
        matched = _match_template(lesson)
        residual = ResidualClass.correction
    if matched is None:
        error_text = _error_text(
            observation_success=observation_success,
            observation_error=observation_error,
            last_error=last_error,
        )
        if error_text is None:
            return None
        category = MemoryCategory.FACT
        dedupe_key = "fact:execution_error"
        content = _exception_token(error_text)
        explicit = False
        residual = ResidualClass.error
    else:
        category, dedupe_key, content, explicit = matched
    key = canonical_dedupe_key(dedupe_key, category.value) or dedupe_key
    return EpisodeFact(
        fact_id=_fact_id(trace_id, key, content, residual),
        dedupe_key=key,
        category=category,
        content=content,
        residual=residual,
        explicit_user_authority=explicit,
        source_trace_id=trace_id,
        observed_at_ms=now_ms,
    )


__all__ = ["govern"]
