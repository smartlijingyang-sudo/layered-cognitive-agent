"""PresetAuthoring —— Creator promote(release) 的唯一 I/O 入口（L4 组合根）。

Plugin-thinking
---------------
§13.3 流程的 Step 6「把 plugin 源码 + bundle 写到 preset 目录」必须落到磁盘，
但本目标坚持「纯逻辑 / I-O 分离」：

- ``CordisComposer``（Tier-2 provider）只操作 cordis Context，**不写文件**。
- ``PresetAuthoring``（L4 组合根）是**唯一**写盘的协调者；它由
  :class:`cordis_control` 的 release promote 成功后调用，把 plugin 源码与
  bundle YAML 落盘。

为什么这样切：unit test 可以用 in-memory ctx + in-memory journal 跑全部
Creator 四面闭环，只有 release promote 的 preset 写入触真实磁盘（也可通过
显式 ``root`` 参数注入 tmp 路径）。

Preset 目录结构
---------------
::

    ${LCA_AGENT_PRESETS_HOME:-~/.agent-presets}/<preset_id>/
        bundle.yaml           # 复用 base.yaml 的 entry 风格，可直接被 boot 加载
        plugins/
            <plugin_name>.py   # plugin 源文件（factory 函数）

下次 boot 时，若加载了该 preset bundle，plugin 会在 boot 期自动挂入
Context，**无需任何 Creator control 调用**——这就是「可复用 preset」
语义（§13.3.4 流程后的关键收益）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from lca.contracts.models.observability.diagnostic import (
    DiagnosticCategory,
    DiagnosticStatus,
)
from lca.contracts.models.observability.journal import PresetPublished
from lca.layer0_infra.observability import record, record_runtime

_log = structlog.get_logger("lca.preset_authoring")


_DEFAULT_PRESETS_HOME = "~/.agent-presets"


@dataclass(frozen=True)
class PresetLayout:
    """一次 preset publish 写入的文件布局。"""

    preset_id: str
    preset_root: Path
    bundle_path: Path
    plugin_path: Path

    def relative_paths(self) -> dict[str, str]:
        """把绝对路径压成相对 preset_root 的 POSIX 字符串（journal payload）。"""
        return {
            "preset_root": str(self.preset_root),
            "bundle_path": self.bundle_path.relative_to(self.preset_root).as_posix(),
            "plugin_path": self.plugin_path.relative_to(self.preset_root).as_posix(),
        }


class PresetAuthoring:
    """release promote 的唯一 I/O 入口；类级别静态方法，无 module singleton。"""

    @staticmethod
    def presets_home(*, override: Path | None = None) -> Path:
        """返回当前 preset 根目录。优先级：override > $LCA_AGENT_PRESETS_HOME > default。"""
        if override is not None:
            return override.expanduser().resolve()
        env = os.environ.get("LCA_AGENT_PRESETS_HOME")
        if env:
            return Path(env).expanduser().resolve()
        return Path(_DEFAULT_PRESETS_HOME).expanduser().resolve()

    @classmethod
    def list_visible_presets(cls, *, root: Path | None = None) -> tuple[str, ...]:
        """列出 root 下所有包含 ``bundle.yaml`` 的 preset id。

        返回 id 的字符串 tuple，按字母序排序。PresetAuthoring 本身不维护
        索引，每次按需扫目录——避免组件层单例（plugin-thinking 一以贯之）。
        """
        home = cls.presets_home(override=root)
        if not home.exists() or not home.is_dir():
            return ()
        ids: list[str] = []
        for entry in sorted(home.iterdir()):
            if not entry.is_dir():
                continue
            bundle = entry / "bundle.yaml"
            if bundle.is_file():
                ids.append(entry.name)
        return tuple(ids)

    @classmethod
    def publish(
        cls,
        *,
        preset_id: str,
        plugin_name: str,
        plugin_id: str,
        plugin_source: str,
        plugin_meta: dict[str, Any],
        actor_role: str = "",
        step: int = 0,
        root: Path | None = None,
    ) -> PresetLayout:
        """把 plugin 源 + bundle YAML 写到 ``root/<preset_id>/``。

        - ``plugin_source`` 写入 ``plugins/<plugin_name>.py``；
        - bundle YAML 写入 ``bundle.yaml``，引用同目录 plugin 模块路径。
        - 函数本身**幂等**：重新写入会覆盖同名文件（plugin 升级语义）。
        - 成功后落 :class:`PresetPublished` + ``RuntimeObserved`` 两条事件。

        Raises:
            ValueError: ``preset_id`` 非法（含 ``/`` 或 ``..``）。
            OSError: 磁盘写入失败（透传）。
        """
        if not preset_id or not _SAFE_ID.fullmatch(preset_id):
            raise ValueError(f"preset_id 非法：{preset_id!r}（仅允许字母/数字/中划线/下划线/点）")
        home = cls.presets_home(override=root)
        preset_root = home / preset_id
        plugins_dir = preset_root / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        plugin_path = plugins_dir / f"{plugin_name}.py"
        plugin_path.write_text(plugin_source, encoding="utf-8")

        # bundle.yaml 引用 plugin 模块：``lca_agent_presets.<preset_id>.plugins.<name>``
        # （LCA boot 时可通过 patch 把这个 module path 注入 sys.path，详见 test_e2e）
        bundle_yaml = _build_bundle_yaml(
            preset_id=preset_id,
            plugin_name=plugin_name,
            plugin_id=plugin_id,
            plugin_meta=plugin_meta,
            plugin_path=plugin_path,
            preset_root=preset_root,
        )
        bundle_path = preset_root / "bundle.yaml"
        bundle_path.write_text(bundle_yaml, encoding="utf-8")

        layout = PresetLayout(
            preset_id=preset_id,
            preset_root=preset_root,
            bundle_path=bundle_path,
            plugin_path=plugin_path,
        )

        record_runtime(
            DiagnosticCategory.PLUGIN,
            "preset.published",
            plugin=plugin_name,
            attributes={
                "actor_role": actor_role,
                "actor_step": step,
                "preset_id": preset_id,
                "preset_root": str(preset_root),
            },
            status=DiagnosticStatus.SUCCEEDED,
        )
        relative = layout.relative_paths()
        record(
            PresetPublished(
                preset_id=preset_id,
                plugin_name=plugin_name,
                plugin_id=plugin_id,
                preset_root=relative["preset_root"],
                bundle_path=relative["bundle_path"],
                plugin_path=relative["plugin_path"],
                actor_role=actor_role,
                step=step,
            )
        )
        _log.info(
            "preset.published",
            preset_id=preset_id,
            plugin_name=plugin_name,
            plugin_path=str(plugin_path),
        )
        return layout

    @classmethod
    def read_plugin_source(
        cls, *, preset_id: str, plugin_name: str, root: Path | None = None
    ) -> str:
        """读已发布 preset 的 plugin 源码（preset 复用测试用）。"""
        home = cls.presets_home(override=root)
        plugin_path = home / preset_id / "plugins" / f"{plugin_name}.py"
        return plugin_path.read_text(encoding="utf-8")

    @classmethod
    def read_bundle_yaml(cls, *, preset_id: str, root: Path | None = None) -> str:
        """读已发布 preset 的 bundle.yaml（preset 复用测试用）。"""
        home = cls.presets_home(override=root)
        return (home / preset_id / "bundle.yaml").read_text(encoding="utf-8")


# preset_id / plugin_name 允许字符：字母数字 + 中划线/下划线/点（避免路径穿越）
_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-\.]{1,64}$")


def _build_bundle_yaml(
    *,
    preset_id: str,
    plugin_name: str,
    plugin_id: str,
    plugin_meta: dict[str, Any],
    plugin_path: Path,
    preset_root: Path,
) -> str:
    """生成 preset 的 bundle YAML。

    格式与 ``bundles/*.yaml`` 一致：
        entries:
          - id: <plugin_id>
            name: <plugin_name>
            $module: <plugin module path>
            config:
              plugin_meta: {...}
              source_path: ...
              preset_id: ...

    下次 boot 时加载这个 bundle 即可让 plugin 自动挂入（无需 cordis_control 调用）。
    """
    module = f"lca_agent_presets.{preset_id}.plugins.{plugin_name}"
    meta_yaml_lines: list[str] = []
    for key in sorted(plugin_meta.keys()):
        value = plugin_meta[key]
        # 不做 YAML 转义——plugin_meta 的 value 通常是字符串/list/dict，统一交给 yaml.dump 处理
        meta_yaml_lines.append(f"        {key}: {_yaml_scalar(value)}")
    meta_block = "\n".join(meta_yaml_lines) if meta_yaml_lines else "        {}"
    return (
        "# Auto-generated by CordisComposer + PresetAuthoring (Creator §13.3).\n"
        "# Re-loading this bundle auto-mounts the plugin without any cordis_control call.\n"
        "entries:\n"
        f"  - id: {plugin_id}\n"
        f"    name: {plugin_name}\n"
        f"    $module: {module}\n"
        "    config:\n"
        "      plugin_meta:\n"
        f"{meta_block}\n"
        f"      source_path: {plugin_path.relative_to(preset_root).as_posix()}\n"
        f"      preset_id: {preset_id}\n"
    )


def _yaml_scalar(value: Any) -> str:
    """把 plugin_meta 的 leaf value 序列化为 YAML scalar（最小实现）。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_yaml_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        # 行内 dict 不常用，落到一行 YAML 表示
        return "{" + ", ".join(f"{k}: {_yaml_scalar(v)}" for k, v in value.items()) + "}"
    text = str(value)
    # 简单引号：含特殊字符就用双引号转义
    if any(c in text for c in (":", "#", "\n", '"', "'")):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


__all__ = ["PresetAuthoring", "PresetLayout"]
