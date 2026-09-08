"""Unified meta-event emission — Session catalog + spine structural dual path.

Run-bound catalog facts and spine EPs both route through ``FactGateway``
(``append_catalog_bound`` / ``publish_ep_bound``; ADR-0195 P1-17).
Unbound session: structured ``structlog`` INFO (never silent).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any

import structlog

from lca.contracts.harness.memory.events import (
    AssistantRunBound,
    AttachmentCommitted,
    CommandRejected,
    ContextInjected,
    FeedbackRecord,
    InboxSpliced,
    PromptSectionPublished,
    SkillActivated,
    SkillCatalogPublished,
    SkillLoaded,
    SkillRouted,
    SkillSearched,
    SkillUserInvoked,
    ToolSchemaPublished,
)
from lca.contracts.harness.memory.skill import SkillCatalogEntry
from lca.contracts.observability.closure.skill_meta_ep_closure import (
    SKILL_PACKAGE_ACTIVATED,
    SKILL_PACKAGE_INSTALL_FAILED,
    SKILL_PACKAGE_INSTALLED,
    SKILL_PACKAGE_SEARCHED,
)
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.infrastructure.session._overflow_0.bindings import resolve_session_reader
from lca.loop.fact_gateway import append_catalog_bound, publish_ep_bound

log = structlog.get_logger(__name__)

_META_ACTOR = "meta"


def _emit_session(
    event_data: Any,
    *,
    actor: str = "agent",
    session: Any | None = None,
) -> AppendReceipt | None:
    writer = session if session is not None else resolve_session_reader()
    if writer is None:
        from lca.contracts.harness.tasks.session import event_type_of

        log.info(
            "meta_event.no_session",
            event_type=event_type_of(event_data),
            payload=asdict(event_data),
        )
        return None
    return append_catalog_bound(event_data, session=writer, actor=actor)


def _emit_skill_spine(
    execution_point: str,
    payload: dict[str, Any],
    *,
    actor: str = _META_ACTOR,
) -> AppendReceipt | None:
    writer = resolve_session_reader()
    if writer is None:
        log.info(
            "meta_event.no_session",
            execution_point=execution_point,
            payload=payload,
        )
        return None
    return publish_ep_bound(execution_point, payload, session=writer, actor=actor)


def tool_registry_digest(tool_names: tuple[str, ...]) -> str:
    """Stable digest for ``tool.schema.published.v1``."""
    body = json.dumps(sorted(tool_names), separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{sha256(body.encode()).hexdigest()}"


def emit_tool_schema_published(tool_names: tuple[str, ...]) -> Any | None:
    """Emit run-resolved tool manifest (``ToolsService.materialize`` boundary)."""
    names = tuple(sorted({n for n in tool_names if n}))
    if not names:
        return None
    return _emit_session(
        ToolSchemaPublished(tool_names=names, digest=tool_registry_digest(names)),
        actor="system",
    )


def emit_skill_loaded(
    *,
    skill_id: str,
    content_hash: str,
    invocation: str = "tool:import_skill",
    actor: str = "agent",
) -> Any | None:
    session_ref = _emit_session(
        SkillLoaded(skill_id=skill_id, content_hash=content_hash, invocation=invocation),
        actor=actor,
    )
    _emit_skill_spine(
        SKILL_PACKAGE_INSTALLED,
        {"skill_id": skill_id, "content_hash": content_hash, "invocation": invocation},
    )
    return session_ref


def emit_skill_install_failed(*, reason: str, source: str = "") -> None:
    _emit_skill_spine(
        SKILL_PACKAGE_INSTALL_FAILED,
        {"reason": reason, "source": source, "skill_id": ""},
    )


def emit_skill_activated(
    *,
    skill_id: str,
    name: str,
    content_hash: str = "",
    source: str = "tool:activate_skill",
    actor: str = "agent",
) -> Any | None:
    session_ref = _emit_session(
        SkillActivated(
            skill_id=skill_id,
            name=name,
            content_hash=content_hash,
            source=source,
            effect_kind="stateful_once",
        ),
        actor=actor,
    )
    _emit_skill_spine(
        SKILL_PACKAGE_ACTIVATED,
        {"skill_id": skill_id, "name": name, "content_hash": content_hash, "source": source},
    )
    return session_ref


def emit_skill_searched(
    *,
    query: str,
    result_count: int,
    source: str = "tool:search_skill",
    page: int = 1,
    page_size: int = 20,
) -> Any | None:
    session_ref = _emit_session(
        SkillSearched(
            query=query,
            result_count=result_count,
            source=source,
            page=page,
            page_size=page_size,
        ),
        actor="agent",
    )
    _emit_skill_spine(
        SKILL_PACKAGE_SEARCHED,
        {
            "query": query,
            "result_count": result_count,
            "source": source,
            "page": page,
            "page_size": page_size,
        },
    )
    return session_ref


def emit_skill_catalog_published(
    *,
    entries: tuple[SkillCatalogEntry, ...],
    digest: str,
    source: str = "perceive",
) -> Any | None:
    return _emit_session(
        SkillCatalogPublished(entries=entries, digest=digest, source=source),
        actor="system",
    )


def emit_skill_routed(
    *,
    template_id: str,
    decision_path: str,
    source: str = "skill_router",
    actor: str = "system",
) -> Any | None:
    return _emit_session(
        SkillRouted(template_id=template_id, decision_path=decision_path, source=source),
        actor=actor,
    )


def emit_skill_user_invoked(*, skill_id: str, raw_text: str, actor: str = "user") -> Any | None:
    return _emit_session(
        SkillUserInvoked(skill_id=skill_id, raw_text=raw_text),
        actor=actor,
    )


def emit_context_injected(
    *,
    source: str,
    content_ref: str,
    model_visible: bool = True,
    actor: str = "system",
) -> Any | None:
    return _emit_session(
        ContextInjected(source=source, content_ref=content_ref, model_visible=model_visible),
        actor=actor,
    )


def emit_attachment_committed(
    *,
    attachment_id: str,
    name: str,
    size_bytes: int,
    mime_type: str,
    actor: str = "system",
    session: Any | None = None,
) -> Any | None:
    return _emit_session(
        AttachmentCommitted(
            attachment_id=attachment_id,
            name=name,
            size_bytes=size_bytes,
            mime_type=mime_type,
        ),
        actor=actor,
        session=session,
    )


def emit_inbox_spliced(
    *,
    op: str,
    target: str,
    message_ids: tuple[str, ...],
    messages: tuple[dict[str, str], ...] = (),
    actor: str = "user",
    session: Any | None = None,
) -> Any | None:
    return _emit_session(
        InboxSpliced(op=op, target=target, message_ids=message_ids, messages=messages),
        actor=actor,
        session=session,
    )


def emit_command_rejected(
    *,
    command_type: str,
    reason: str,
    actor: str = "system",
    session: Any | None = None,
) -> Any | None:
    return _emit_session(
        CommandRejected(command_type=command_type, reason=reason),
        actor=actor,
        session=session,
    )


def emit_feedback_record(
    *,
    text: str | None = None,
    rating: str | None = None,
    tags: tuple[str, ...] = (),
    message_seqs: tuple[int, ...] = (),
    actor: str = "user",
    session: Any | None = None,
) -> Any | None:
    return _emit_session(
        FeedbackRecord(
            text=text,
            rating=rating,
            tags=tags,
            message_seqs=message_seqs,
        ),
        actor=actor,
        session=session,
    )


def emit_prompt_section_published(
    *,
    section_key: str,
    digest: str,
    template_id: str = "",
    text_chars: int = 0,
) -> Any | None:
    return _emit_session(
        PromptSectionPublished(
            section_key=section_key,
            digest=digest,
            template_id=template_id,
            text_chars=text_chars,
        ),
        actor="system",
    )


def emit_prompt_sections_from_trace(
    *,
    template_id: str,
    sections: list[dict[str, Any]],
) -> None:
    for section in sections:
        name = str(section.get("name") or "")
        digest = str(section.get("content_digest") or "")
        if not name or not digest:
            continue
        emit_prompt_section_published(
            section_key=name,
            digest=digest,
            template_id=template_id,
            text_chars=int(section.get("text_chars") or 0),
        )


def emit_assistant_run_bound(
    *,
    assistant_id: str,
    run_id: str,
    profile: str = "",
) -> Any | None:
    return _emit_session(
        AssistantRunBound(assistant_id=assistant_id, run_id=run_id, profile=profile),
        actor="system",
    )


__all__ = [
    "emit_assistant_run_bound",
    "emit_attachment_committed",
    "emit_command_rejected",
    "emit_context_injected",
    "emit_feedback_record",
    "emit_inbox_spliced",
    "emit_prompt_section_published",
    "emit_prompt_sections_from_trace",
    "emit_skill_activated",
    "emit_skill_catalog_published",
    "emit_skill_install_failed",
    "emit_skill_loaded",
    "emit_skill_routed",
    "emit_skill_searched",
    "emit_skill_user_invoked",
    "emit_tool_schema_published",
    "tool_registry_digest",
]
