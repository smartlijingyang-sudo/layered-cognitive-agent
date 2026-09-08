"""Adapter: agent_lab mv.assemble ↔ LCA DefaultModelContextAssembler.

LCA contracts consumed (read-only):
  - lca.contracts.protocols.session.model.context.SessionReader
  - lca.contracts.protocols.session.model.context.ModelVisibleRequest
  - lca.infrastructure.session.context.model_context_assembler.DefaultModelContextAssembler

agent_lab provides (this file):
  - SessionReaderAdapter: implements SessionReader by reading agent_lab
    artifact inputs (messages, system, config, tools).
  - LcaMvProvider: wraps DefaultModelContextAssembler.assemble(...) and
    returns an agent_lab Artifact that mirrors ModelVisibleRequest's shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_text


@dataclass(frozen=True)
class SessionReaderAdapter:
    """Concrete SessionReader backed by agent_lab artifact inputs.

    LCA's SessionReader is a runtime Protocol — this object satisfies it
    structurally without inheriting, because SessionReader is
    @runtime_checkable.
    """

    _messages: tuple[dict[str, Any], ...]
    _system: str | None
    _config: dict[str, Any] | None
    _tools: tuple[dict[str, Any], ...]

    def derive_messages(self) -> list[dict[str, Any]]:
        return [dict(m) for m in self._messages]

    def request_header(self) -> object | None:
        if self._system is None and self._config is None and not self._tools:
            return None
        return {
            "system": self._system,
            "config": self._config,
            "tools": list(self._tools),
        }

    def snapshot_events(self, from_seq: int = 0, to_seq_exclusive: int | None = None) -> tuple:
        # agent_lab adapter has no event log; return empty slice.
        return ()


class LcaMvProvider:
    """Wraps DefaultModelContextAssembler and returns agent_lab Artifact.

    The returned artifact carries a dict shaped like ModelVisibleRequest
    (messages / system / config / tools) so downstream consumers can
    inspect it without depending on LCA dataclasses.
    """

    def __init__(self) -> None:
        # Late import so agent_lab can boot without lca being importable
        # (e.g. for ad-hoc mock demos). When unavailable, raises at .assemble() time.
        from lca.contracts.protocols.session.model.context import (
            ModelContextAssembler,
        )
        from lca.infrastructure.session.context.model_context_assembler import (
            DefaultModelContextAssembler,
        )

        self._assembler: ModelContextAssembler = DefaultModelContextAssembler()

    @staticmethod
    def from_artifacts(
        *,
        messages_artifact: Artifact | None,
        system_artifact: Artifact | None,
        config_artifact: Artifact | None,
        tools_artifact: Artifact | None,
    ) -> SessionReaderAdapter:
        messages: list[dict[str, Any]] = []
        if messages_artifact is not None and isinstance(messages_artifact.content, list):
            for m in messages_artifact.content:
                if isinstance(m, dict):
                    messages.append(dict(m))
        system = None
        if system_artifact is not None and isinstance(system_artifact.content, str):
            system = system_artifact.content or None
        config = None
        if config_artifact is not None and isinstance(config_artifact.content, dict):
            config = dict(config_artifact.content)
        tools: list[dict[str, Any]] = []
        if tools_artifact is not None and isinstance(tools_artifact.content, (list, tuple)):
            for t in tools_artifact.content:
                if isinstance(t, dict):
                    tools.append(dict(t))
        return SessionReaderAdapter(
            _messages=tuple(messages),
            _system=system,
            _config=config,
            _tools=tuple(tools),
        )

    def assemble(
        self,
        *,
        messages_artifact: Artifact | None,
        system_artifact: Artifact | None,
        config_artifact: Artifact | None,
        tools_artifact: Artifact | None,
        step: int = 0,
    ) -> Artifact:
        """Build a SessionReader from agent_lab artifacts, run LCA assembler, wrap result."""
        reader = self.from_artifacts(
            messages_artifact=messages_artifact,
            system_artifact=system_artifact,
            config_artifact=config_artifact,
            tools_artifact=tools_artifact,
        )
        # DefaultModelContextAssembler.assemble(session, step=step) -> ModelVisibleRequest
        req = self._assembler.assemble(reader, step=step)
        # Convert ModelVisibleRequest -> agent_lab Manifest artifact.
        return Artifact(
            kind=ArtifactKind.MANIFEST,
            content={
                "messages": list(req.messages),
                "system": req.system,
                "config": req.config,
                "tools": list(req.tools),
            },
            schema_ref="context.manifest.v1",
        )


def make_text_artifact(s: str) -> Artifact:
    return make_text(s, schema_ref="system.v1")
