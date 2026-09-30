"""``lca.harness.plugin_api`` 显式再出口门面的架构回归测试。

防止门面退回 ``from lca.harness.plugin import *``：公开面必须与
``lca.harness.plugin.__all__`` 完全一致，且每个名字都真实可解析。
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from lca.harness import plugin, plugin_api

REPO = Path(__file__).resolve().parents[2]


def test_plugin_api_all_matches_plugin_public_surface() -> None:
    """门面公开面与插件包 ``__all__`` 完全一致，不增不减。"""

    assert hasattr(plugin, "__all__")
    assert set(plugin_api.__all__) == set(plugin.__all__)


def test_every_plugin_api_export_resolves_to_plugin_origin() -> None:
    """门面每个公开名都真实可解析，且与插件包中的对象同一。"""

    assert plugin_api.__all__
    for name in plugin_api.__all__:
        assert hasattr(plugin_api, name), f"plugin_api.{name} 缺失"
        assert getattr(plugin_api, name) is getattr(plugin, name), (
            f"plugin_api.{name} 与 lca.harness.plugin.{name} 不是同一对象"
        )


def test_plugin_api_has_no_star_import() -> None:
    """门面不得再使用 ``import *``（公开面必须显式可审计）。"""

    source = (REPO / "lca" / "harness" / "plugin_api.py").read_text(encoding="utf-8")
    assert "import *" not in source
    assert re.search(r"^from lca\.harness\.plugin import \*", source, re.MULTILINE) is None


def test_plugin_api_all_is_explicit_and_sorted() -> None:
    """``__all__`` 必须显式书写（不能依赖 ``plugin.__all__`` 动态注入）。"""

    source = (REPO / "lca" / "harness" / "plugin_api.py").read_text(encoding="utf-8")
    assert "__all__ = [" in source
    assert "from lca.harness.plugin import __all__" not in source
    assert plugin_api.__all__ == sorted(plugin_api.__all__)


def test_all_plugin_api_consumers_import_cleanly() -> None:
    """每个从 ``lca.harness.plugin_api`` 导入的模块都必须能加载。"""

    consumers: list[str] = []
    for path in (REPO / "lca").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(
            r"(from lca\.harness\.plugin_api import|import lca\.harness\.plugin_api)", text
        ):
            rel = path.relative_to(REPO).with_suffix("")
            consumers.append(".".join(rel.parts))
    assert consumers, "expected at least one plugin_api consumer"
    for module_name in consumers:
        importlib.import_module(module_name)


def test_plugin_api_is_thin_facade() -> None:
    """门面不应定义自己的业务符号（只做再出口）。"""

    source = (REPO / "lca" / "harness" / "plugin_api.py").read_text(encoding="utf-8")
    for name in plugin_api.__all__:
        # Every public name must come from an import, not a local definition.
        assert re.search(rf"^{name} =", source, re.MULTILINE) is None, f"{name} 是本地定义"
