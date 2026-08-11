"""Artifact respond injector — append authoritative file list to respond text (ADR-0051).

Design principle: *system facts do not transit through the LLM.*  File URLs,
MIME types, and sizes are system facts produced by the file store.  The LLM
composes narrative; the system attaches the deliverable manifest.

When the LLM chooses ``respond`` and the workspace has registered artifacts,
this gate:
1. Strips any ``/files/file_<hex>`` references from the LLM text (hallucinated)
2. Appends the authoritative ``closure_text()`` from the artifact ledger

This ensures the user always sees correct download links regardless of what
the LLM generates.
"""

from __future__ import annotations

import re

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.layer0_infra.workspace import get_run_workspace
from lca.layer0_infra.workspace.artifact_ledger import artifact_closure_text

# Matches hallucinated file URLs like /files/file_a1b2c3d4e5f6
_HALLUCINATED_FILE_URL_RE = re.compile(r"\[([^\]]*)\]\(/files/file_[a-f0-9]+\)")
_BARE_FILE_URL_RE = re.compile(r"(?<!\w)/files/file_[a-f0-9]+\b")


class ArtifactRespondInjector:
    """Post-process respond decisions: append authoritative artifact block.

    The LLM never needs to know or reproduce file URLs — the system injects
    them from the workspace artifact ledger.
    """

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
        cleaned_text = _strip_hallucinated_file_urls(original_text)
        closure = artifact_closure_text(snapshot)

        if not closure:
            return decision

        merged = f"{cleaned_text}\n\n{closure}" if cleaned_text.strip() else closure

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


def _strip_hallucinated_file_urls(text: str) -> str:
    """Remove LLM-hallucinated /files/file_<hex> references.

    Handles both markdown links ``[label](/files/file_xxx)`` and bare URLs.
    """
    result = _HALLUCINATED_FILE_URL_RE.sub(r"\1", text)
    result = _BARE_FILE_URL_RE.sub("", result)
    return result
