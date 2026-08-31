"""Creator §13.3 preset 复用：下一个 session boot 期自动挂入上次发布的 plugin。

Plan step 3 —— preset reuse test：
- 复用第 2 步落盘的 preset 目录，boot 一个新的 mock session；
- **不调用任何 cordis_control** —— 直接走 preset bundle 的加载路径；
- 断言新工具在 boot 后的 ToolRegistry / cordis Context 里已存在并能直接调用
  （证明 preset 在 boot 阶段被自动挂入，而非依赖 Creator control 调用）。

Preset bundle 加载约定
----------------------
``PresetAuthoring.publish`` 生成的 ``bundle.yaml`` 形如：

    entries:
      - id: <plugin_id>
        name: <plugin_name>
        $module: lca_agent_presets.<preset_id>.plugins.<plugin_name>
        config:
          plugin_meta: {...}
          source_path: plugins/<plugin_name>.py
          preset_id: <preset_id>

``bundle_replayer``（本测试文件实现）解析 bundle + 动态 import 每个 entry，
把 ``plugin_meta`` 注入 factory 模块，运行 ``factory()`` 拿实例，调用
``ctx.provide('plugin:<name>', instance)``。这是「plugin 复用」的最小
boot 钩子，不引入 cordis boot 路径的依赖（让 unit test 跑得起来）。
"""

from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.journal_backend import MemoryJournal

from lca.infrastructure.observability.facade import BoundObservability, bind_backends
from lca.plugins.providers.think.composition_composer import (
    CordisComposer,
    build_default_invariant_checker,
)
from lca.plugins.tools.cordis_control import build_cordis_control_tool
from tests.test_cordis_creator_e2e import SCRATCH, _plugin_source


@contextmanager
def bind_journal():
    journal = MemoryJournal()
    with bind_backends(BoundObservability(journal=journal)):
        yield journal


def _new_composer() -> CordisComposer:
    from cordis import Context

    ctx = Context()
    return CordisComposer(ctx, invariant_checker=build_default_invariant_checker())


def _bootstrap_preset_into_context(
    *,
    preset_id: str,
    preset_root: Path,
    composer: CordisComposer,
    ctx: Any,
    caller_grant: tuple[str, ...] = (),
) -> tuple[str, Any]:
    """模拟 boot 期 preset 加载：读 bundle.yaml → dynamic import → 通过 Composer.mount 挂入 ctx。

    返回 ``(plugin_name, instance)``；走 composer.mount 而非直接 ctx.provide，
    让 §13.3.1 五条硬约束（C3/C4/C5/PR12/§23.2）在 boot 路径上同样适用——
    不允许 preset 加载跳过 invariant 检查。
    """
    from lca.contracts.mechanisms.composition import PluginFactory

    bundle_path = preset_root / preset_id / "bundle.yaml"
    text = bundle_path.read_text(encoding="utf-8")
    entries = _parse_bundle_entries(text)
    assert len(entries) == 1, f"preset 应只有一个 entry；got {entries}"

    entry = entries[0]
    plugin_name = entry["name"]
    plugin_path = preset_root / preset_id / entry["config"]["source_path"]
    assert plugin_path.is_file(), f"plugin 源不存在：{plugin_path}"

    preset_root_str = str(preset_root)
    sys.path.insert(0, preset_root_str)
    try:
        module_name = entry["$module"]
        spec = importlib.util.spec_from_file_location(module_name, str(plugin_path))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        factory = getattr(module, "factory", None) or getattr(
            module, f"{plugin_name}_factory", None
        )
        assert callable(factory), "factory() 函数未找到"

        # 从 module 取 plugin_meta（preset bundle 里也有，但运行时 module 是真相源）
        plugin_meta = dict(getattr(module, "plugin_meta", {}) or {})
        plugin_meta.setdefault("name", plugin_name)

        result = composer.mount(  # noqa: F841 — 调用 composer.mount 走 C5/PR12/§23.2 闸
            PluginFactory(
                name=plugin_name,
                factory=factory,
                plugin_meta=plugin_meta,
                source_path=str(plugin_path),
            ),
            caller_grant=caller_grant,
            actor_role="preset-bootstrap",
        )
        instance = ctx.own_bindings.get(f"plugin:{plugin_name}")
        return plugin_name, instance
    finally:
        with suppress(ValueError):
            sys.path.remove(preset_root_str)


def _parse_bundle_entries(text: str) -> list[dict[str, Any]]:
    """解析 PresetAuthoring 生成的 bundle.yaml；用 PyYAML（stdlib 替代品无歧义）。"""
    import yaml

    data = yaml.safe_load(text) or {}
    entries = data.get("entries") or []
    return entries


class TestPresetReuse:
    """Boot 阶段自动挂入 preset —— 不调用 Creator control。"""

    def test_preset_publish_then_reuse_in_new_session(self) -> None:
        """Happy path：先经 author、validate、release promote 发布 plugin，
        再开一个全新 session boot preset，断言 plugin 已挂入 Context。
        """
        from cordis import Context

        # ── 阶段 1：Creator 四面流程发布 plugin 到 preset ──
        preset_root = SCRATCH / "preset_reuse"
        preset_root.mkdir(parents=True, exist_ok=True)

        with bind_journal():
            composer = _new_composer()
            tool = build_cordis_control_tool(
                composer=composer,
                caller_grant=(
                    "cordis_control.author",
                    "cordis_control.validate",
                    "cordis_control.promote",
                    "tool_fs.read",
                ),
                actor_role="cordis-creator",
                preset_root=preset_root,
            )

            plugin_path = preset_root / "json_keys.py"
            plugin_path.write_text(_plugin_source("json_keys"), encoding="utf-8")

            import asyncio

            assert asyncio.run(
                tool.execute({"action": "author", "name": "json_keys", "path": str(plugin_path)})
            ).success
            assert asyncio.run(tool.execute({"action": "validate", "name": "json_keys"})).success
            r = asyncio.run(
                tool.execute({"action": "promote", "name": "json_keys", "target_scope": "release"})
            )
            assert r.success, f"creator promote 失败：{r.error}"

        # ── 阶段 2：全新 session，boot 加载 preset，不调用 cordis_control ──
        new_ctx = Context()
        new_composer = CordisComposer(new_ctx, invariant_checker=build_default_invariant_checker())

        with bind_journal():
            plugin_name, instance = _bootstrap_preset_into_context(
                preset_id="json_keys",
                preset_root=preset_root,
                composer=new_composer,
                ctx=new_ctx,
                caller_grant=("tool_fs.read",),
            )
            assert plugin_name == "json_keys"
            assert instance is not None

            # 关键断言：新 session 不需要任何 Creator control 调用，
            # plugin 已经直接可用
            assert new_ctx.own_bindings.get("plugin:json_keys") is instance

            # 直接调用 factory 返回的 callable，行为正确
            result = instance('{"hello": 1, "world": 2}')
            assert result == ["hello", "world"]

            # inspect 也直接看到这条挂入
            inspect_result = new_composer.inspect()
            assert inspect_result.mounted_count == 1
            assert inspect_result.entries[0].name == "json_keys"

    def test_preset_reuse_provides_full_meta_to_composer(self) -> None:
        """Preset 重用时，Composer 持有完整 plugin_meta，可用于后续 inspect / C5 校验。"""
        from cordis import Context

        preset_root = SCRATCH / "preset_reuse_meta"
        preset_root.mkdir(parents=True, exist_ok=True)

        with bind_journal():
            composer = _new_composer()
            tool = build_cordis_control_tool(
                composer=composer,
                caller_grant=(
                    "cordis_control.author",
                    "cordis_control.validate",
                    "cordis_control.promote",
                    "tool_fs.read",
                ),
                actor_role="cordis-creator",
                preset_root=preset_root,
            )

            plugin_path = preset_root / "meta_plugin.py"
            plugin_path.write_text(_plugin_source("meta_plugin"), encoding="utf-8")

            import asyncio

            assert asyncio.run(
                tool.execute({"action": "author", "name": "meta_plugin", "path": str(plugin_path)})
            ).success
            assert asyncio.run(tool.execute({"action": "validate", "name": "meta_plugin"})).success
            r = asyncio.run(
                tool.execute(
                    {"action": "promote", "name": "meta_plugin", "target_scope": "release"}
                )
            )
            assert r.success

        # 重启 session，bootstrap 后 inspect 应返回完整 meta
        new_ctx = Context()
        new_composer = CordisComposer(new_ctx, invariant_checker=build_default_invariant_checker())

        with bind_journal():
            _bootstrap_preset_into_context(
                preset_id="meta_plugin",
                preset_root=preset_root,
                composer=new_composer,
                ctx=new_ctx,
                caller_grant=("tool_fs.read",),
            )

            inspect_result = new_composer.inspect()
            entry = inspect_result.entries[0]
            assert entry.name == "meta_plugin"
            assert "tool_fs.read" in entry.capabilities
            assert entry.policy_class == "execute"
            assert entry.side_effects == "none"
            assert "Plugin" in entry.implements
