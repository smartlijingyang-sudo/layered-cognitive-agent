"""Creator inspect, author and validate runtime backed by four-state Artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.artifact_state import ArtifactState
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.artifact import (
    capability_artifact_to_dict,
    make_capability_artifact,
    migrate_to_verified,
)
from lca.contracts.models.observability.diagnostic import DiagnosticCategory, DiagnosticStatus
from lca.contracts.models.observability.journal import PluginAuthored, PluginInspected
from lca.layer0_infra.observability import record, record_runtime
from lca.plugins.tools.cordis_control.creator_artifacts import (
    AuthoredPlugin,
    require_artifact,
    with_artifact,
)
from lca.plugins.tools.cordis_control.creator_promotion import promote
from lca.plugins.tools.cordis_control.loader import extract_plugin_factory, load_plugin_source

if TYPE_CHECKING:
    from lca.plugins.tools.cordis_control.tool import CordisControlTool


class CreatorRuntime:
    """Execute the closed Creator faces against one Composer scope."""

    def __init__(self, tool: CordisControlTool) -> None:
        self._tool = tool
        self._authored: dict[str, AuthoredPlugin] = {}

    def inspect(self, *, target: str | None = None) -> dict[str, Any]:
        result = self._tool._composer.inspect(actor_role=self._tool._actor_role)
        stamped = record(
            PluginInspected(
                actor_role=self._tool._actor_role,
                mounted_count=result.mounted_count,
                plugin_names=tuple(entry.name for entry in result.entries),
                plugins_summary=tuple(
                    {
                        "name": entry.name,
                        "context_key": entry.context_key,
                        "implements": list(entry.implements),
                        "capabilities": list(entry.capabilities),
                        "policy_class": entry.policy_class,
                        "side_effects": entry.side_effects,
                    }
                    for entry in result.entries
                ),
            )
        )
        record_runtime(
            DiagnosticCategory.TOOL,
            "creator.inspect",
            plugin=self._tool.name,
            attributes={
                "actor_role": self._tool._actor_role,
                "mounted_count": result.mounted_count,
            },
            status=DiagnosticStatus.SUCCEEDED,
        )
        artifacts = self._authored.values()
        if target:
            artifacts = (item for name, item in self._authored.items() if name == target)
        return {
            "face": "inspect",
            "mounted_count": result.mounted_count,
            "entries": [
                {
                    "name": entry.name,
                    "context_key": entry.context_key,
                    "implements": list(entry.implements),
                    "capabilities": list(entry.capabilities),
                }
                for entry in result.entries
            ],
            "artifacts": [capability_artifact_to_dict(item.artifact) for item in artifacts],
            "event_seq": stamped.seq if stamped else None,
        }

    def author(self, *, name: str, path: str) -> dict[str, Any]:
        source, language, size = load_plugin_source(path)
        factory, metadata = extract_plugin_factory(
            source_path=path,
            source_text=source,
            plugin_name=name,
            preset_root=self._tool._preset_root,
        )
        artifact = make_capability_artifact(
            name,
            source,
            scope=Scope.RUN,
            grants=self._tool._caller_grant,
            metadata={"path": path, "language": language, "plugin_meta": dict(metadata)},
        )
        self._authored[name] = AuthoredPlugin(
            artifact=artifact,
            source=source,
            path=path,
            language=language,
            factory=factory,
            metadata=dict(metadata),
        )
        stamped = record(
            PluginAuthored(
                plugin_name=name,
                path=path,
                language=language,
                size_bytes=size,
                actor_role=self._tool._actor_role,
            )
        )
        record_runtime(
            DiagnosticCategory.TOOL,
            "creator.author",
            plugin=name,
            attributes={"actor_role": self._tool._actor_role, "path": path, "size_bytes": size},
            status=DiagnosticStatus.SUCCEEDED,
        )
        return {
            "face": "author",
            "artifact": capability_artifact_to_dict(artifact),
            "authored_event_seq": stamped.seq if stamped else None,
        }

    def validate(self, *, name: str) -> dict[str, Any]:
        authored = require_artifact(self._authored, name, ArtifactState.DRAFT)
        artifact = migrate_to_verified(authored.artifact)
        self._authored[name] = with_artifact(authored, artifact)
        return {
            "face": "validate",
            "artifact": capability_artifact_to_dict(artifact),
            "checks": ("source_loaded", "plugin_metadata", "factory_extractable"),
        }

    def promote(
        self,
        *,
        name: str,
        target_scope: str | None = None,
        rollback: bool = False,
        preset_id: str | None = None,
    ) -> dict[str, Any]:
        return promote(
            self._tool,
            self._authored,
            name=name,
            target_scope=target_scope,
            rollback=rollback,
            preset_id=preset_id,
        )


__all__ = ["CreatorRuntime"]
