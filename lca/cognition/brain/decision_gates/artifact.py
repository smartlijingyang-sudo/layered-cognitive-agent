"""Artifact respond injector — append authoritative file list to respond text (ADR-0051 / PR6.D.4)."""

from __future__ import annotations

import re
from typing import Any, cast

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.perceive.projection import current_manifest_from_state
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.core.workspace.workspace import ArtifactLedgerSnapshot
from lca.contracts.protocols import DecisionGate
from lca.infrastructure.workspace.artifact_ledger import rewrite_artifact_markdown

_FILE_MD_RE = re.compile(r"\[([^\]]*)\]\((/files/file_[a-f0-9]+)\)")
_BARE_FILE_URL_RE = re.compile(r"(?<!\w)(/files/file_[a-f0-9]+)\b")


def _artifacts_from_manifest(state: AgentState) -> list[dict[str, object]]:
    """Read the ``workspace_artifacts`` item from the typed manifest."""
    manifest = current_manifest_from_state(state)
    if manifest is None:
        return []
    for item in manifest.items:
        if item.kind == "workspace_artifacts" and isinstance(item.payload, list):
            return [a for a in item.payload if isinstance(a, dict)]
    return []


def _ledger_snapshot_from_manifest(
    artifacts: list[dict[str, object]],
) -> ArtifactLedgerSnapshot:
    """Build the minimal ``ArtifactLedgerSnapshot`` shape for the rewrite helpers."""
    from lca.contracts.models.core.workspace.workspace import (
        ArtifactLedgerSnapshot,
        WorkspaceArtifact,
    )

    artifact_objs = tuple(
        WorkspaceArtifact(
            name=str(a.get("name") or a.get("path") or ""),
            mime_type=str(a.get("mime", "")),
            url=str(a.get("url", "")),
            size_bytes=int(cast("Any", a).get("size", 0) or 0),
        )
        for a in artifacts
    )
    return ArtifactLedgerSnapshot(artifacts=artifact_objs)


def _format_closure(artifacts: list[dict[str, object]]) -> str:
    """Build the authoritative artifact closure text from manifest payload."""
    if not artifacts:
        return ""
    snapshot = _ledger_snapshot_from_manifest(artifacts)
    from lca.infrastructure.workspace.artifact_ledger import artifact_closure_text

    return artifact_closure_text(snapshot)


class ArtifactRespondInjector(DecisionGate):
    """Post-process respond decisions: rewrite paths and append the ledger."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.RESPOND:
            return decision

        artifacts = _artifacts_from_manifest(state)
        if not artifacts:
            return decision

        snapshot = _ledger_snapshot_from_manifest(artifacts)

        original_text = decision.response_text or ""
        rewritten = rewrite_artifact_markdown(original_text, snapshot)
        known = {str(art.get("url")) for art in artifacts if art.get("url")}
        cleaned = _strip_unknown_file_urls(rewritten, known)
        closure = _format_closure(artifacts)
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


__all__ = ["ArtifactRespondInjector"]
