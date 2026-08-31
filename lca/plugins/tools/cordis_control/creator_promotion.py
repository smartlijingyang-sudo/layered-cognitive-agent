"""Promotion and retirement effects for the Creator four-face lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.application.preset_authoring import PresetAuthoring
from lca.contracts.atoms.artifact_state import ArtifactState
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.journal.artifact import (
    artifact_with_scope,
    capability_artifact_to_dict,
    migrate_to_active,
    migrate_to_retired,
)
from lca.contracts.mechanisms.composition import (
    ComposerError,
    ComposerErrorCode,
    InvariantViolation,
    PluginFactory,
)
from lca.contracts.models.observability.diagnostic import DiagnosticCategory, DiagnosticStatus
from lca.contracts.models.observability.journal import (
    PluginMounted,
    PluginMountRejected,
    PluginUnmounted,
)
from lca.infrastructure.observability import record, record_runtime
from lca.plugins.tools.cordis_control.creator_artifacts import (
    AuthoredPlugin,
    require_artifact,
    with_artifact,
)

if TYPE_CHECKING:
    from lca.plugins.tools.cordis_control.tool import CordisControlTool


def promote(
    tool: CordisControlTool,
    authored: dict[str, AuthoredPlugin],
    *,
    name: str,
    target_scope: str | None,
    rollback: bool,
    preset_id: str | None,
) -> dict[str, Any]:
    """Promote VERIFIED to ACTIVE or retire ACTIVE through the Composer boundary."""

    item = require_artifact(
        authored, name, ArtifactState.ACTIVE if rollback else ArtifactState.VERIFIED
    )
    if rollback:
        return _retire(tool, authored, item)

    resolved_scope = Scope(target_scope or Scope.RUN.value)
    if resolved_scope is Scope.EXPERIMENT and item.metadata.get("side_effects") != "none":
        error = InvariantViolation(
            f"experiment promotion for plugin {name!r} requires side_effects='none'",
            plugin_name=name,
            check_name="experiment_effect_boundary",
        )
        _record_rejected(tool, name, error, item.metadata)
        raise error

    factory = PluginFactory(
        name=name,
        factory=item.factory,
        plugin_meta=item.metadata,
        source_path=item.path,
    )
    try:
        mounted = tool._composer.mount(
            factory,
            caller_grant=tool._caller_grant,
            actor_role=tool._actor_role,
        )
    except ComposerError as exc:
        _record_rejected(tool, name, exc, item.metadata)
        raise
    artifact = artifact_with_scope(migrate_to_active(item.artifact), resolved_scope)
    authored[name] = with_artifact(item, artifact)
    if tool._on_mounted is not None:
        instance = tool._composer._ctx.own_bindings.get(mounted.context_key)
        tool._on_mounted(mounted.plugin_name, instance, item.metadata)
    stamped = record(
        PluginMounted(
            plugin_name=mounted.plugin_name,
            plugin_id=mounted.plugin_id,
            capabilities=mounted.capabilities,
            capability_grant=mounted.capability_grant,
            meta=mounted.meta_snapshot,
            actor_role=tool._actor_role,
        )
    )
    layout = _publish_release(tool, item, mounted.plugin_id, target_scope, preset_id)
    record_runtime(
        DiagnosticCategory.TOOL,
        "creator.promote",
        plugin=name,
        attributes={
            "actor_role": tool._actor_role,
            "target_scope": resolved_scope.value,
        },
        status=DiagnosticStatus.SUCCEEDED,
    )
    return {
        "face": "promote",
        "artifact": capability_artifact_to_dict(artifact),
        "context_key": mounted.context_key,
        "capabilities": list(mounted.capabilities),
        "target_scope": resolved_scope.value,
        "mount_event_seq": stamped.seq if stamped else None,
        "preset_layout": layout.relative_paths() if layout else None,
    }


def _publish_release(
    tool: CordisControlTool,
    item: AuthoredPlugin,
    plugin_id: str,
    target_scope: str | None,
    preset_id: str | None,
) -> Any | None:
    if target_scope != Scope.RELEASE.value:
        return None
    return PresetAuthoring.publish(
        preset_id=preset_id or item.artifact.logical_id,
        plugin_name=item.artifact.logical_id,
        plugin_id=plugin_id,
        plugin_source=item.source,
        plugin_meta=item.metadata,
        actor_role=tool._actor_role,
        root=tool._preset_root,
    )


def _retire(
    tool: CordisControlTool, authored: dict[str, AuthoredPlugin], item: AuthoredPlugin
) -> dict[str, Any]:
    unmounted = tool._composer.unmount(
        plugin_name=item.artifact.logical_id,
        actor_role=tool._actor_role,
    )
    artifact = migrate_to_retired(item.artifact)
    authored[artifact.logical_id] = with_artifact(item, artifact)
    stamped = record(
        PluginUnmounted(
            plugin_name=unmounted.plugin_name,
            plugin_id=unmounted.plugin_name,
            actor_role=tool._actor_role,
        )
    )
    record_runtime(
        DiagnosticCategory.TOOL,
        "creator.promote",
        plugin=artifact.logical_id,
        attributes={"actor_role": tool._actor_role, "rollback": True},
        status=DiagnosticStatus.SUCCEEDED,
    )
    return {
        "face": "promote",
        "artifact": capability_artifact_to_dict(artifact),
        "context_key": unmounted.context_key,
        "unmount_event_seq": stamped.seq if stamped else None,
    }


def _record_rejected(
    tool: CordisControlTool, name: str, error: ComposerError, metadata: dict[str, Any]
) -> None:
    record_runtime(
        DiagnosticCategory.TOOL,
        "creator.promote_rejected",
        plugin=name,
        attributes={"actor_role": tool._actor_role, "reason_code": error.code.value},
        status=DiagnosticStatus.FAILED,
    )
    record(
        PluginMountRejected(
            plugin_name=name,
            reason_code=error.code.value,
            reason_message=str(error),
            plugin_meta_present=error.code is not ComposerErrorCode.PLUGIN_META_MISSING,
            capability_grant=tool._caller_grant,
            requested_capabilities=tuple(metadata.get("capabilities") or ()),
            actor_role=tool._actor_role,
        )
    )


__all__ = ["promote"]
