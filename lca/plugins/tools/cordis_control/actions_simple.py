"""cordis_control Tool 的简单 action：inspect / unmount / publish。

文件组织
--------
4 个 action 中 inspect / unmount / publish 三个相对独立，单独抽到本文件；
mount 因含 PR12 闸 + preset 写入 + 三类事件链，单独放 :mod:`actions_mount`。

事件链
------
- inspect  → :class:`PluginInspected` + 解释性 RuntimeObserved
- unmount  → :class:`PluginUnmounted`（失败 → RuntimeObserved FAILED）
- publish  → :class:`PluginAuthored` + :class:`PresetPublished`
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.mechanisms.composition import (
    ComposerErrorCode,
    InspectResult,
    NotMounted,
    UnmountResult,
)
from lca.contracts.models.observability.diagnostic import (
    DiagnosticCategory,
    DiagnosticStatus,
)
from lca.contracts.models.observability.journal import (
    PluginAuthored,
    PluginInspected,
    PluginUnmounted,
)
from lca.layer0_infra.observability import record, record_runtime
from lca.plugins.tools.cordis_control.loader import (
    extract_plugin_factory,
    load_plugin_source,
)

if TYPE_CHECKING:
    from lca.plugins.tools.cordis_control.tool import CordisControlTool


def do_inspect(tool: CordisControlTool) -> dict[str, Any]:
    """inspect action：返回当前 Context 派生能力图 + 落 PluginInspected。"""
    result: InspectResult = tool._composer.inspect(actor_role=tool._actor_role)
    record_runtime(
        DiagnosticCategory.TOOL,
        "cordis_control.inspect",
        plugin=tool.name,
        attributes={
            "actor_role": tool._actor_role,
            "mounted_count": result.mounted_count,
        },
        status=DiagnosticStatus.SUCCEEDED,
    )
    stamped = record(
        PluginInspected(
            actor_role=tool._actor_role,
            mounted_count=result.mounted_count,
            plugin_names=tuple(e.name for e in result.entries),
            plugins_summary=tuple(
                {
                    "name": e.name,
                    "context_key": e.context_key,
                    "implements": list(e.implements),
                    "capabilities": list(e.capabilities),
                    "policy_class": e.policy_class,
                    "side_effects": e.side_effects,
                }
                for e in result.entries
            ),
        )
    )
    return {
        "action": "inspect",
        "mounted_count": result.mounted_count,
        "plugin_names": [e.name for e in result.entries],
        "context_keys": list(result.context_keys),
        "entries": [
            {
                "name": e.name,
                "context_key": e.context_key,
                "implements": list(e.implements),
                "capabilities": list(e.capabilities),
                "policy_class": e.policy_class,
                "side_effects": e.side_effects,
            }
            for e in result.entries
        ],
        "event_seq": stamped.seq if stamped else None,
    }


def do_unmount(tool: CordisControlTool, *, name: str) -> dict[str, Any]:
    """unmount action：失败时只落 RuntimeObserved（PluginUnmounted 不发）。"""
    try:
        result: UnmountResult = tool._composer.unmount(
            plugin_name=name,
            actor_role=tool._actor_role,
        )
    except NotMounted:
        record_runtime(
            DiagnosticCategory.TOOL,
            "plugin.unmount_rejected",
            plugin=name,
            attributes={
                "actor_role": tool._actor_role,
                "reason_code": ComposerErrorCode.NOT_MOUNTED.value,
                "source": "cordis_control_tool",
            },
            status=DiagnosticStatus.FAILED,
        )
        raise
    record_runtime(
        DiagnosticCategory.TOOL,
        "plugin.unmounted",
        plugin=name,
        attributes={
            "actor_role": tool._actor_role,
            "context_key": result.context_key,
        },
        status=DiagnosticStatus.SUCCEEDED,
    )
    stamped = record(
        PluginUnmounted(
            plugin_name=result.plugin_name,
            plugin_id=result.plugin_name,
            actor_role=tool._actor_role,
        )
    )
    return {
        "action": "unmount",
        "plugin_name": result.plugin_name,
        "context_key": result.context_key,
        "unmount_event_seq": stamped.seq if stamped else None,
    }


def do_publish(tool: CordisControlTool, *, name: str, path: str, preset_id: str) -> dict[str, Any]:
    """publish action：仅写 preset 目录，不挂载（与 mount 的副作用不同）。"""
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
    _, plugin_meta = extract_plugin_factory(
        source_path=path,
        source_text=source_text,
        plugin_name=name,
        preset_root=tool._preset_root,
    )
    from lca.layer4_app.preset_authoring import PresetAuthoring

    layout = PresetAuthoring.publish(
        preset_id=preset_id,
        plugin_name=name,
        plugin_id=name,
        plugin_source=source_text,
        plugin_meta=dict(plugin_meta),
        actor_role=tool._actor_role,
        root=tool._preset_root,
    )
    return {
        "action": "publish",
        "plugin_name": name,
        "preset_layout": layout.relative_paths(),
    }


__all__ = ["do_inspect", "do_publish", "do_unmount"]
