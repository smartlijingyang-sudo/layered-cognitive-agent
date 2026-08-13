"""Artifact respond injector — append authoritative file list to respond text (ADR-0051).

Design principle: *system facts do not transit through the LLM.*  File URLs,
MIME types, and sizes are system facts produced by the file store.  The LLM
composes narrative; the system attaches the deliverable manifest.

When the LLM chooses ``respond`` and the workspace has registered artifacts,
this gate:
1. Rewrites relative markdown hrefs (``](01_foo.png)``) to ledger URLs
2. Strips ``/files/file_<hex>`` references that are *not* on the ledger
3. Appends the authoritative ``closure_text()`` if it is not already present
"""

from __future__ import annotations

import re

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.layer0_infra.workspace import get_run_workspace
from lca.layer0_infra.workspace.artifact_ledger import (
    artifact_closure_text,
    rewrite_artifact_markdown,
)

_FILE_MD_RE = re.compile(r"\[([^\]]*)\]\((/files/file_[a-f0-9]+)\)")
_BARE_FILE_URL_RE = re.compile(r"(?<!\w)(/files/file_[a-f0-9]+)\b")


class ArtifactRespondInjector:
    """Post-process respond decisions: rewrite paths and append the ledger."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.RESPOND:
            return decision

        workspace = get_run_workspace()
        if workspace is None:
            return decision

        snapshot = workspace.artifacts.snapshot()
        if not snapshot.artifacts:
            return decision

        original_text = decision.response_text or ""
        rewritten = rewrite_artifact_markdown(original_text, snapshot)
        known = {art.url for art in snapshot.artifacts if art.url}
        cleaned = _strip_unknown_file_urls(rewritten, known)
        closure = artifact_closure_text(snapshot)
        if closure and closure not in cleaned:
            merged = f"{cleaned.rstrip()}\n\n{closure}" if cleaned.strip() else closure
        else:
            merged = cleaned

        return Decision(
            decision_id=decision.decision_id,
            action_type=decision.action_type,
            rationale=decision.rationale,
            confidence=decision.confidence,
            response_text=merged,
            tool_calls=decision.tool_calls,
            delegations=decision.delegations,
            degraded_from=decision.degraded_from,
            extra=decision.extra,
        )


def _strip_unknown_file_urls(text: str, known_urls: set[str]) -> str:
    """Drop hallucinated /files/file_<hex> that the ledger does not own."""

    def keep_md(match: re.Match[str]) -> str:
        url = match.group(2)
        return match.group(0) if url in known_urls else match.group(1)

    def keep_bare(match: re.Match[str]) -> str:
        url = match.group(1)
        return url if url in known_urls else ""

    result = _FILE_MD_RE.sub(keep_md, text)
    return _BARE_FILE_URL_RE.sub(keep_bare, result)
