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

from lca_kernel.events.bus import EnvelopeBus, EventBus
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


def build_test_bus(config_dir: Path | None = None) -> EnvelopeBus:
    """PR-5：测试路径下构造 catalog 已注入的 EnvelopeBus。

    1. 构造 :data:`build_test_catalog`（id → marker class）；
    2. :class:`EventRegistry.load` 装载 yaml，注入 catalog（让 id 与
       class-path 双形态 token 都能解析）；
    3. 返回 :class:`EnvelopeBus`（实例为 EventBus compat 子类）。

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
