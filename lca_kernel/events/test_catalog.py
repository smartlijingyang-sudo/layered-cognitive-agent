"""PR-5 测试辅助：catalog 构造器。

生产路径下 ``EventRegistry`` 的 catalog 由 profile resolve → setup_bus 注入；
测试路径下没有 profile，需要手动注入。本模块提供 ``build_test_catalog``
与 ``build_test_bus`` 两个公开 helper，被 conftest.py 与各测试文件的
fixture 复用。

详见 :mod:`tests.lca_kernel.events.conftest`。
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from lca_kernel.events.bus import EventBus
from lca_kernel.events.registry import EventRegistry


def build_test_catalog() -> dict[str, type]:
    """构造测试用的 marker catalog（id → marker class）。

    与生产路径等价：枚举 ``lca.plugins.events`` 下所有带 marker 的组件。
    任意组件 import 失败 → 跳过该项（不影响其他项）；catalog 用于事件
    yaml ``publishers:`` / ``subscribers:`` id-form token 解析。
    """
    catalog: dict[str, type] = {}
    pairs: tuple[tuple[str, str, str], ...] = (
        # (marker_id, module_path, class_name)
        (
            "delegation_cache",
            "lca.plugins.events.publishers.delegation_cache.plugin",
            "DelegationCachePlugin",
        ),
        (
            "events.spine.reflector.cognition",
            "lca.plugins.events.publishers.spine_reflector_cognition.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.body_llm",
            "lca.plugins.events.publishers.spine_reflector_body_llm.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.runtime",
            "lca.plugins.events.publishers.spine_reflector_runtime.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.transport",
            "lca.plugins.events.publishers.spine_reflector_transport.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.kernel_loop",
            "lca.plugins.events.publishers.spine_reflector_kernel_loop.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.agent_spawn",
            "lca.plugins.events.publishers.spine_reflector_agent_spawn.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.writable",
            "lca.plugins.events.publishers.spine_reflector_writable.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.phase",
            "lca.plugins.events.publishers.spine_reflector_phase.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.phase_graph",
            "lca.plugins.events.publishers.spine_reflector_phase_graph.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.perception",
            "lca.plugins.events.publishers.spine_reflector_perception.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.team",
            "lca.plugins.events.publishers.spine_reflector_team.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.control",
            "lca.plugins.events.publishers.spine_reflector_control.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.reflector.boot",
            "lca.plugins.events.publishers.spine_reflector_boot.plugin",
            "ReflectorClass",
        ),
        (
            "events.spine.writable_matrix",
            "lca.plugins.events.publishers.spine_writable_matrix.plugin",
            "WritableMatrixPlugin",
        ),
        (
            "events.spine.loop_cursor",
            "lca.plugins.events.publishers.spine_loop_cursor.plugin",
            "LoopCursorPlugin",
        ),
        (
            "events.model_visible.publisher",
            "lca.plugins.events.publishers.model_visible.publisher",
            "ModelVisiblePublisher",
        ),
    )
    for marker_id, module_path, class_name in pairs:
        try:
            module = import_module(module_path)
        except ImportError:  # pragma: no cover - 模块可选
            continue
        cls = getattr(module, class_name, None)
        if cls is None:
            continue
        catalog[marker_id] = cls
    return catalog


def build_test_bus(config_dir: Path | None = None) -> EventBus:
    """PR-5：测试路径下构造 catalog 已注入的 EventBus。

    1. 构造 :data:`build_test_catalog`（id → marker class）；
    2. :class:`EventRegistry.load` 装载 yaml，注入 catalog（让 id 与
       class-path 双形态 token 都能解析）；
    3. 返回 :class:`EventBus`。

    与生产路径（profile resolve → setup_bus → catalog 注入）等价。
    """
    from lca_kernel.events import _DEFAULT_CONFIG_DIR

    cfg = config_dir if config_dir is not None else _DEFAULT_CONFIG_DIR
    catalog = build_test_catalog()
    registry = EventRegistry.load(cfg, catalog=catalog)
    # 把 catalog 也同步进 registry（生产路径由 setup_bus.register_marker 注入；
    # 此处 load 已注入，所以 _plugins 已就位,refresh 不必重跑；但保险起见
    # 跑一次让 consumer_rules raw tokens 重新物化）。
    registry.refresh()
    return EventBus(registry)


__all__ = ["build_test_bus", "build_test_catalog"]
