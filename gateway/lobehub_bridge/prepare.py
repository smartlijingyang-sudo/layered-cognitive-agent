"""Orchestrate LobeHub OpenAI messages → LCA run session input."""

from __future__ import annotations

from typing import Any

from gateway.lobehub_bridge.file_ingest import FileFetcher, ingest_file_refs
from gateway.lobehub_bridge.models import LobeHubRunInput
from gateway.lobehub_bridge.parser import parse_messages
from gateway.run_prompt import compose_run_question
from lca.layer0_infra.file_store import FileStore


async def prepare_run_from_messages(
    messages: list[Any],
    store: FileStore,
    *,
    fetcher: FileFetcher | None = None,
) -> LobeHubRunInput:
    """Parse, ingest attachments, and compose the LCA run task (last user turn only)."""
    parsed = parse_messages(messages)
    if not parsed.user_text:
        return LobeHubRunInput(user_text="", question="")

    ingest = await ingest_file_refs(parsed.file_refs, store, fetcher=fetcher)
    question = compose_run_question(parsed.user_text, ingest.attachment_ids, store)
    return LobeHubRunInput(
        user_text=parsed.user_text,
        question=question,
        prior_turns=parsed.prior_turns,
        attachment_ids=ingest.attachment_ids,
        skipped_files=ingest.skipped,
    )
