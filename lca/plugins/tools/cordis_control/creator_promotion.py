"""Promotion and retirement effects for the Creator four-face lifecycle."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, cast

from lca.application.authoring.preset_authoring import PresetAuthoring
from lca.contracts.atoms.artifact.state import ArtifactState
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_meta import PluginMeta
from lca.contracts.harness.journal.artifact import (
    artifact_with_scope,
    capability_artifact_to_dict,
    migrate_to_active,
    migrate_to_retired,
)
from lca.contracts.mechanisms.composition.composition import (
    ComposerError,
    ComposerErrorCode,
    InvariantViolation,
    PluginFactory,
)
from lca.contracts.models.observability.diagnostic.diagnostic import (
    DiagnosticCategory,
    DiagnosticStatus,
)
from lca.contracts.models.observability.journal.journal import (
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
        plugin_meta=cast("PluginMeta", item.metadata),
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

    # DynamicToolBridge integration: auto-bridge active tools into runtime ToolsService & SafeExecutor
    tools_svc = getattr(tool, "_tools_service", None)
    safe_exec = getattr(tool, "_safe_executor", None)
    if tools_svc is not None or safe_exec is not None:
        from lca.infrastructure.tools.dynamic.bridge import DynamicToolBridge

        instance = tool._composer._ctx.own_bindings.get(mounted.context_key)
        if instance is not None:
            bridged = DynamicToolBridge.bridge_instance(
                mounted.plugin_name, instance, item.metadata
            )
            DynamicToolBridge.register_tool(
                bridged,
                tools_service=tools_svc,
                safe_executor=safe_exec,
            )

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
    if target_scope not in (Scope.RELEASE.value, Scope.AGENT.value):
        return None
    root = tool._preset_root
    asst_home = getattr(tool, "_assistant_home", None)
    if root is None and asst_home is not None:
        root = asst_home / "presets"

    effective_preset_id = preset_id or item.artifact.logical_id
    layout = PresetAuthoring.publish(
        preset_id=effective_preset_id,
        plugin_name=item.artifact.logical_id,
        plugin_id=plugin_id,
        plugin_source=item.source,
        plugin_meta=item.metadata,
        actor_role=tool._actor_role,
        root=root,
    )
    if asst_home is not None:
        from lca.infrastructure.preset.fs_repository import _atomic_write_text

        preset_dir = (root or (asst_home / "presets")) / effective_preset_id
        meta_file = preset_dir / "preset.json"
        metadata = {
            "preset_id": effective_preset_id,
            "scope": target_scope or "agent",
            "assistant_id": getattr(asst_home, "name", "") or "",
            "description": item.metadata.get("description", ""),
            "created_at": time.time(),
            "plugins": [
                {
                    "name": item.artifact.logical_id,
                    "capabilities": list(item.metadata.get("capabilities", ())),
                    "side_effects": item.metadata.get("side_effects", "none"),
                    "policy_class": item.metadata.get("policy_class", "execute"),
                    "implements": list(item.metadata.get("implements", ())),
                }
            ],
        }
        _atomic_write_text(meta_file, json.dumps(metadata, ensure_ascii=False, indent=2))

        direct_plugins = asst_home / "plugins"
        direct_plugins.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(direct_plugins / f"{item.artifact.logical_id}.py", item.source)
    return layout


def _retire(
    tool: CordisControlTool, authored: dict[str, AuthoredPlugin], item: AuthoredPlugin
) -> dict[str, Any]:
    unmounted = tool._composer.unmount(
        plugin_name=item.artifact.logical_id,
        actor_role=tool._actor_role,
    )
    artifact = migrate_to_retired(item.artifact)
    authored[artifact.logical_id] = with_artifact(item, artifact)

    # DynamicToolBridge unregister
    tools_svc = getattr(tool, "_tools_service", None)
    safe_exec = getattr(tool, "_safe_executor", None)
    if tools_svc is not None or safe_exec is not None:
        from lca.infrastructure.tools.dynamic.bridge import DynamicToolBridge

        DynamicToolBridge.unregister_tool(
            item.artifact.logical_id,
            tools_service=tools_svc,
            safe_executor=safe_exec,
        )

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
