"""cordis_control Tool 的 mount action：§13.3.4 Step 4-6 全流程。

文件组织
--------
mount 是 4 个 action 中最复杂的：含 PR12 闸提取、C5 grant 子集校验、
Composer 三道闸、PluginMounted / PluginMountRejected 事件落盘、preset
写入（PresetPublished）等。本文件单独承载这些职责。

事件链
------
mount success → :class:`PluginAuthored` → :class:`PluginMounted` →
:class:`PresetPublished`
mount failure → :class:`PluginAuthored` → :class:`PluginMountRejected`（reason_code）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.harness.plugin_meta import PluginMeta
from lca.contracts.mechanisms.composition import (
    ComposerError,
    ComposerErrorCode,
    MountResult,
    PluginFactory,
    PluginMetaMissing,
)
from lca.contracts.models.observability.diagnostic import (
    DiagnosticCategory,
    DiagnosticStatus,
)
from lca.contracts.models.observability.journal import (
    PluginAuthored,
    PluginMounted,
    PluginMountRejected,
)
from lca.layer0_infra.observability import record, record_runtime
from lca.plugins.tools.cordis_control.loader import (
    extract_plugin_factory,
    load_plugin_source,
)

if TYPE_CHECKING:
    from lca.plugins.tools.cordis_control.tool import CordisControlTool


def do_mount(tool: CordisControlTool, *, name: str, path: str) -> dict[str, Any]:
    """mount action：§13.3.4 Step 4-6 全流程。"""
    source_text, language, size = load_plugin_source(path)
    record_runtime(
        DiagnosticCategory.TOOL,
        "plugin.authored",
        plugin=name,
        attributes={
            "actor_role": tool._actor_role,
            "path": path,
            "language": language,
            "size_bytes": size,
        },
        status=DiagnosticStatus.SUCCEEDED,
    )
    record(
        PluginAuthored(
            plugin_name=name,
            path=path,
            language=language,
            size_bytes=size,
            actor_role=tool._actor_role,
        )
    )

    try:
        factory_callable, plugin_meta = extract_plugin_factory(
            source_path=path,
            source_text=source_text,
            plugin_name=name,
            preset_root=tool._preset_root,
        )
    except PluginMetaMissing as exc:
        _emit_mount_rejected(
            tool,
            plugin_name=name,
            reason_code=exc.code,
            reason_message=str(exc),
            plugin_meta_present=False,
            requested_capabilities=(),
        )
        raise

    factory = PluginFactory(
        name=name,
        factory=factory_callable,
        plugin_meta=plugin_meta,
        source_path=path,
    )
    try:
        result: MountResult = tool._composer.mount(
            factory,
            caller_grant=tool._caller_grant,
            actor_role=tool._actor_role,
        )
    except ComposerError as exc:
        _emit_mount_rejected(
            tool,
            plugin_name=name,
            reason_code=exc.code,
            reason_message=str(exc),
            plugin_meta_present=exc.code is not ComposerErrorCode.PLUGIN_META_MISSING,
            requested_capabilities=tuple(plugin_meta.get("capabilities") or ()),
        )
        raise

    record_runtime(
        DiagnosticCategory.TOOL,
        "plugin.mounted",
        plugin=name,
        attributes={
            "actor_role": tool._actor_role,
            "plugin_id": result.plugin_id,
            "context_key": result.context_key,
            "capabilities": list(result.capabilities),
            "capability_grant": list(result.capability_grant),
        },
        status=DiagnosticStatus.SUCCEEDED,
    )
    stamped_mounted = record(
        PluginMounted(
            plugin_name=result.plugin_name,
            plugin_id=result.plugin_id,
            capabilities=result.capabilities,
            capability_grant=result.capability_grant,
            meta=result.meta_snapshot,
            actor_role=tool._actor_role,
        )
    )

    # mount 成功后回调：让上层把 plugin 注册到 ToolsService（agent 的
    # 下一次 use_tool 调用能命中）。失败时回调不调用。
    if tool._on_mounted is not None:
        # 从 composer 持有的 ctx 取 instance（MountResult 不直接带 instance，
        # 走 ctx.own_bindings[result.context_key] 是稳定契约）
        mounted_instance = tool._composer._ctx.own_bindings.get(result.context_key)
        tool._on_mounted(result.plugin_name, mounted_instance, plugin_meta)

    layout, publish_error = _publish_to_preset(
        tool,
        plugin_name=name,
        plugin_source=source_text,
        plugin_meta=plugin_meta,
    )
    return {
        "action": "mount",
        "plugin_name": result.plugin_name,
        "context_key": result.context_key,
        "capabilities": list(result.capabilities),
        "capability_grant": list(result.capability_grant),
        "meta": dict(result.meta_snapshot),
        "mount_event_seq": stamped_mounted.seq if stamped_mounted else None,
        "plugin_source_path": path,
        "preset_layout": layout.relative_paths() if layout else None,
        "publish_error": publish_error,
    }


def _emit_mount_rejected(
    tool: CordisControlTool,
    *,
    plugin_name: str,
    reason_code: ComposerErrorCode,
    reason_message: str,
    plugin_meta_present: bool,
    requested_capabilities: tuple[str, ...],
) -> None:
    """落 :class:`PluginMountRejected` 事件 + 解释性 RuntimeObserved。"""
    record_runtime(
        DiagnosticCategory.TOOL,
        "plugin.mount_rejected",
        plugin=plugin_name,
        attributes={
            "actor_role": tool._actor_role,
            "reason_code": reason_code.value,
            "source": "cordis_control_tool",
        },
        status=DiagnosticStatus.FAILED,
    )
    record(
        PluginMountRejected(
            plugin_name=plugin_name,
            reason_code=reason_code.value,
            reason_message=reason_message,
            plugin_meta_present=plugin_meta_present,
            capability_grant=tool._caller_grant,
            requested_capabilities=requested_capabilities,
            actor_role=tool._actor_role,
        )
    )


def _publish_to_preset(
    tool: CordisControlTool,
    *,
    plugin_name: str,
    plugin_source: str,
    plugin_meta: PluginMeta,
) -> tuple[Any | None, str | None]:
    """mount 成功后自动调用，把 plugin 源码写到 preset 目录。

    失败时返回 ``(None, error_message)``；调用方把 error_message 放进 payload，
    避免 mount 成功但 preset 写入失败时的状态错位。
    """
    from lca.layer4_app.preset_authoring import PresetAuthoring

    try:
        layout = PresetAuthoring.publish(
            preset_id=plugin_name,
            plugin_name=plugin_name,
            plugin_id=plugin_name,
            plugin_source=plugin_source,
            plugin_meta=dict(plugin_meta),
            actor_role=tool._actor_role,
            root=tool._preset_root,
        )
        return layout, None
    except Exception as exc:
        return None, f"preset publish 失败：{type(exc).__name__}: {exc}"


__all__ = ["_emit_mount_rejected", "_publish_to_preset", "do_mount"]
