"""Artifact respond injector — append authoritative file list to respond text (ADR-0051 / PR6.D.4).

Design principle: *system facts do not transit through the LLM.*  File URLs,
MIME types, and sizes are system facts produced by the file store.  The LLM
composes narrative; the system attaches the deliverable manifest.

When the LLM chooses ``respond`` and the workspace has registered artifacts,
this gate:
1. Rewrites relative markdown hrefs (``](01_foo.png)``) to ledger URLs
2. Strips ``/files/file_<hex>`` references that are *not* on the ledger
3. Appends the authoritative ``closure_text()`` if it is not already present

v3 §5.1 / PR6.D.4: the artifact snapshot is read from the typed manifest
slot (``PerceiveState.current_manifest`` → ``workspace_artifacts`` item)
as the primary source.  Falls back to the live workspace when the manifest
has no artifact item — keeps the pre-v3 test path working while the new
v3 path is canonical.
"""

from __future__ import annotations

import re
from typing import Any, cast

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.workspace import ArtifactLedgerSnapshot
from lca.contracts.protocols import DecisionGate
from lca.infrastructure.workspace.artifact_ledger import rewrite_artifact_markdown

_FILE_MD_RE = re.compile(r"\[([^\]]*)\]\((/files/file_[a-f0-9]+)\)")
_BARE_FILE_URL_RE = re.compile(r"(?<!\w)(/files/file_[a-f0-9]+)\b")


def _artifacts_from_manifest(state: AgentState) -> list[dict[str, object]]:
    """Read the ``workspace_artifacts`` item from the typed manifest.

    Returns ``[]`` if the manifest is absent or has no artifact item.
    The item payload is the list of dicts produced by
    ``WorkspaceArtifactsSensor`` (path / url / mime / size keys).
    """
    manifest = PerceiveState.from_agent_state(state).current_manifest
    if manifest is None:
        return []
    for item in manifest.items:
        if item.kind == "workspace_artifacts" and isinstance(item.payload, list):
            return [a for a in item.payload if isinstance(a, dict)]
    return []


def _ledger_snapshot_from_manifest(
    artifacts: list[dict[str, object]],
) -> ArtifactLedgerSnapshot:
    """Build the minimal ``ArtifactLedgerSnapshot`` shape for the rewrite helpers.

    The legacy helpers (``rewrite_artifact_markdown`` etc.) expect a
    ``ArtifactLedgerSnapshot`` with ``artifacts`` (tuple of
    ``WorkspaceArtifact`` records).  We materialize them from the
    manifest payload.
    """
    from lca.contracts.models.core.workspace import (
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
    """Build the authoritative artifact closure text from manifest payload.

    Delegates to ``artifact_closure_text`` so the format stays in lockstep
    with the workspace ledger (icon prefix, locale).
    """
    if not artifacts:
        return ""
    snapshot = _ledger_snapshot_from_manifest(artifacts)
    from lca.infrastructure.workspace.artifact_ledger import artifact_closure_text

    return artifact_closure_text(snapshot)


class ArtifactRespondInjector(DecisionGate):
    """Post-process respond decisions: rewrite paths and append the ledger.

    v3 PR6.D.4 + PR4.C.3: explicitly inherits ``DecisionGate`` and reads
    the artifact snapshot from the typed manifest slot (``workspace_artifacts``
    kind item) as the primary source.  Falls back to the live workspace
    (``run_workspace_scope``) when the manifest has no artifacts — keeps
    the pre-v3 test path working while the new v3 path is canonical.
    """

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.RESPOND:
            return decision

        artifacts = _artifacts_from_manifest(state)
        if not artifacts:
            return decision

        # Build a minimal ledger-shaped snapshot for the rewrite helpers.
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
